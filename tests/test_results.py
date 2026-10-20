"""slim-data in the portal (D-70, M6 part 2 slice 1): upload -> preview / import -> evaluate -> batch."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from slim_data.domain.enums import IdentitySource, Role
from slim_data.domain.values import AnalyteRef, SampleRef
from slim_data.persistence import migrate
from slim_data.persistence.rulesets import current_policy, ruleset_for

from slim_lab_portal.domain import RequestType, TRStatus, transition
from slim_lab_portal.models import LAB_ROLE_ANALYST, LAB_ROLE_REVIEWER, ROLE_STAFF, User
from slim_lab_portal.reference import AnalysisRef, ChemicalRef, CustomerRef, ElementRef, StaticReferenceData
from slim_lab_portal.repositories import TRSubmissionRepository
from slim_lab_portal.results import (
    SpecReader,
    StaffDirectory,
    TrSampleTables,
    actor_for,
    publish_demo_rules,
    reference_lookup,
)
from slim_lab_portal.security import hash_password
from slim_lab_portal import slim_tables as t
from tests.conftest import PASSWORD, csrf_from, login, login_api
from tests.factories import NOW, STAFF_ACTOR, sample, submission
from tests.slim_fixtures import create_slim_tables

TEN, THIRTY_SIX = 5, 1  # analysis IDs: 10 Elements has the demo ruleset, 36 Elements has none
HEADER = ("lab_sample_id,analysis_code,analyte,role,replicate,value,unit,mdl,dilution_factor,run_code,"
          "instrument,analyst,analyzed_at,prep_batch,prep_method,spike_added,rejected,note")


@pytest.fixture
def reference():
    C = RequestType.CHEMICAL
    return StaticReferenceData.of(
        customers=[CustomerRef(1, "A")],
        chemicals=[ChemicalRef(2, "Chemical 01")],
        elements=[ElementRef(26, "Fe", "Iron"), ElementRef(29, "Cu", "Copper")],
        analyses=[
            AnalysisRef(THIRTY_SIX, "36 Elements", "36_elements_icpms", "Metals", request_types=frozenset({C})),
            AnalysisRef(TEN, "10 Elements", "10_elements_icpms", "Metals", request_types=frozenset({C})),
        ],
    )


SPECS = {(1, 2, ""): {"Fe": 50.0}}


@pytest.fixture
def app(engine, reference):
    from slim_lab_portal.main import create_app
    from tests.conftest import make_settings

    with engine.begin() as connection:  # slim-data's own tables, fresh (Postgres keeps them otherwise)
        migrate.downgrade(connection)
        migrate.upgrade(connection)
    return create_app(make_settings(str(engine.url)), engine=engine, reference=reference,
                      specs=lambda customer, chemical, location: SPECS.get((customer, chemical, location), {}))


@pytest.fixture
def lab(app, db, reference, staff_user):
    """Demo rules published; analyst AN; TR00001 received (2 samples on 10 Elements), TR00002 only
    submitted, TR00003 received on 36 Elements (no ruleset)."""
    publish_demo_rules(db, reference)
    db.add(User(email="an@lab.example", password_hash=hash_password(PASSWORD), role=ROLE_STAFF, initials="AN",
                lab_role=LAB_ROLE_ANALYST))
    repo = TRSubmissionRepository(db)
    for analysis, receive in ((TEN, True), (TEN, False), (THIRTY_SIX, True)):
        tr = repo.add(submission(samples=(sample(1, analysis_ids=(analysis,)), sample(2, analysis_ids=(analysis,)))))
        if receive:
            repo.record_transition(tr, transition(tr, TRStatus.RECEIVED, actor=STAFF_ACTOR, at=NOW,
                                                  date_received=date(2026, 10, 9), received_by="JM"))
    db.commit()
    return db


def csv(tr="TR00001", analysis="10_elements_icpms", analyst="AN", batch="PB-1", run="RUN-1") -> bytes:
    rows = [
        (f"{tr}-01", "Fe", "CUP", 1, "10.10", ""), (f"{tr}-01", "Fe", "CUP", 2, "10.00", ""),
        (f"{tr}-01", "Fe", "SPIKE", 1, "29.90", "20"),
        (f"{tr}-02", "Fe", "CUP", 1, "5.10", ""), (f"{tr}-02", "Fe", "CUP", 2, "5.00", ""),
        ("BLANK", "Fe", "BLANK", 1, "0.010", ""),
    ]
    lines = [HEADER] + [
        f"{s},{analysis},{code},{role},{rep},{value},ppb,0.05,1,{run},ICP-MS 1,{analyst},"
        f"2026-10-10T09:00:00+00:00,{batch},microwave HNO3,{spike},,"
        for s, code, role, rep, value, spike in rows
    ]
    return ("\n".join(lines) + "\n").encode()


def upload(client, content: bytes, preview: bool = False, name: str = "run1.csv"):
    return client.post(f"/api/results/imports{'?preview=true' if preview else ''}",
                       files={"file": (name, content, "text/csv")})


# ---------------------------------------------------------------- data in, through the API

def test_preview_checks_without_writing(client, lab):
    login_api(client, "staff@lab.example")
    plan = upload(client, csv(), preview=True).json()
    assert plan["ok"] and plan["readings"] == 6 and plan["new_batches"] == ["PB-1"]
    assert plan["run"]["analyst"] == "AN" and plan["errors"] == []
    assert client.get("/api/results/batches").json() == []


def test_import_evaluates_the_batch_and_is_idempotent(client, lab):
    login_api(client, "staff@lab.example")
    response = upload(client, csv())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["readings"] == 6 and body["batches_registered"] == ["PB-1"]
    assert body["evaluated"]["PB-1"]["new_versions"] == 2

    assert [(b["code"], b["analysis"]) for b in client.get("/api/results/batches").json()] == [("PB-1", "10 Elements")]
    view = client.get("/api/results/batches/PB-1").json()
    assert {(r["sample"]["position"], r["analyte"]["code"]) for r in view["results"]} == {(1, "Fe"), (2, "Fe")}
    # Entered by AN (the file's analyst) and JM (who uploaded it): neither may review them (D-66).
    assert set(view["results"][0]["analyst_ids"]) == {str(u.id) for u in lab.scalars(select(User)) if u.initials}

    again = upload(client, csv())
    assert again.status_code == 422 and "already imported" in again.json()["plan"]["errors"][0]["message"]


@pytest.mark.parametrize("content, column, message", [
    (csv(analyst="ZZ"), "analyst", "no staff member"),
    (csv(tr="TR00002"), "lab_sample_id", ""),  # submitted, not received: no readings yet
    (csv(analysis="no_such_analysis"), "analysis_code", ""),
])
def test_a_refused_file_writes_nothing(client, lab, content, column, message):
    login_api(client, "staff@lab.example")
    response = upload(client, content)
    assert response.status_code == 422
    errors = response.json()["plan"]["errors"]
    assert any(e["column"] == column and message in e["message"] for e in errors), errors
    assert client.get("/api/results/batches").json() == []


def test_no_published_ruleset_rolls_the_whole_upload_back(client, lab):
    login_api(client, "staff@lab.example")
    response = upload(client, csv(tr="TR00003", analysis="36_elements_icpms"))
    assert response.status_code == 422 and "no published ruleset" in response.json()["detail"]
    assert client.get("/api/results/batches").json() == []


def test_unknown_batch_is_404(client, lab):
    login_api(client, "staff@lab.example")
    assert client.get("/api/results/batches/PB-404").status_code == 404


def test_results_are_staff_only(client, lab, customer_user):
    login_api(client, "jane@acme.example")
    assert client.get("/api/results/batches").status_code == 403
    assert upload(client, csv(), preview=True).status_code == 403
    assert client.get("/results", headers={"accept": "text/html"}).status_code == 403


# ---------------------------------------------------------------- pages

def test_upload_page_previews_then_imports(client, lab):
    login(client, "staff@lab.example")
    token = csrf_from(client.get("/results").text)
    files = {"file": ("run1.csv", csv(), "text/csv")}
    preview = client.post("/results/upload", data={"csrf_token": token, "action": "preview"}, files=files)
    assert preview.status_code == 200 and "ready to import" in preview.text and "PB-1" in preview.text

    imported = client.post("/results/upload", data={"csrf_token": token, "action": "import"}, files=files)
    assert imported.status_code == 200 and "Imported run1.csv: 6 readings" in imported.text  # followed the 303
    batch = client.get("/results/batches/PB-1")
    assert batch.status_code == 200 and "TR00001-01" in batch.text and "10 Elements" in batch.text

    refused = client.post("/results/upload", data={"csrf_token": token, "action": "import"}, files=files)
    assert refused.status_code == 422 and "already imported" in refused.text


def test_unknown_batch_page_is_404(client, lab):
    login(client, "staff@lab.example")
    assert client.get("/results/batches/PB-404").status_code == 404


# ---------------------------------------------------------------- the ports

def test_tr_samples_only_from_received_trs(lab):
    samples = TrSampleTables(lab)
    info = samples.find(SampleRef(tr_number="TR00001", position=2))
    assert (info.customer_id, info.chemical_id, info.analysis_ids) == (1, 2, frozenset({TEN}))
    assert samples.find(SampleRef(tr_number="TR00002", position=1)) is None
    assert samples.find(SampleRef(tr_number="TR00001", position=9)) is None


def test_lookup_resolves_catalog_codes_and_specs(lab, reference):
    lookup = reference_lookup(lab, reference, lambda c, ch, loc: SPECS.get((c, ch, loc), {}))
    assert lookup.analysis_id("10_elements_icpms") == TEN and lookup.analysis_id("ph") is None
    ref = SampleRef(tr_number="TR00001", position=1)
    assert lookup.sample_requests(ref, TEN) and not lookup.sample_requests(ref, THIRTY_SIX)
    assert str(lookup.limits_for(ref, AnalyteRef(analysis_id=TEN, code="Fe")).high) == "50.0"


def test_staff_directory_finds_active_staff_by_initials(lab):
    staff = StaffDirectory(lab)
    actor = staff.find("an ")
    assert actor.display == "AN" and actor.roles == {Role.ANALYST}
    assert actor.identity_source == IdentitySource.AUTHENTICATED
    lab.scalars(select(User).where(User.initials == "AN")).one().is_active = False
    assert staff.find("AN") is None and staff.find("XX") is None


def test_actor_is_the_user_id(staff_user):
    actor = actor_for(staff_user)
    assert actor.id == str(staff_user.id) and actor.roles == {Role.SUPERVISOR}


def test_spec_reader_reads_slim_specifications(engine):
    create_slim_tables(engine)
    with engine.begin() as conn:
        conn.execute(t.specifications.insert(), [
            dict(id=1, kind="specification", customer_id=1, chemical_id=2, element_symbol="Fe", value=0.3, location=""),
            dict(id=2, kind="warning_limit", customer_id=1, chemical_id=2, element_symbol="Fe", value=0.1, location=""),
            dict(id=3, kind="specification", customer_id=1, chemical_id=2, element_symbol="Na", value=1.0,
                 location="SX5N"),
        ])
    specs = SpecReader(engine)
    assert specs(1, 2, "") == {"Fe": 0.3}
    assert specs(1, 2, "SX5N") == {"Na": 1.0}
    assert specs(9, 2, "") == {}


def test_demo_rules_bind_to_ten_elements_by_code(app, db, reference):
    assert publish_demo_rules(db, reference) == TEN
    assert publish_demo_rules(db, reference) == TEN  # content-hashed: nothing new
    assert ruleset_for(db, TEN, "microwave HNO3").ruleset.analysis_id == TEN
    assert current_policy(db).policy.name == "demo"


def test_demo_rules_refuse_a_catalog_without_ten_elements(app, db):
    with pytest.raises(LookupError, match="10_elements_icpms"):
        publish_demo_rules(db, StaticReferenceData.of())


# ---------------------------------------------------------------- lab roles

def _users_form(client):
    return csrf_from(client.get("/admin/users").text)


def test_supervisor_sets_lab_roles(client, lab):
    login(client, "staff@lab.example")
    analyst_id = lab.scalars(select(User.id).where(User.initials == "AN")).one()
    lab.rollback()  # end the read: on SQLite an open transaction would block the app's write
    response = client.post(f"/admin/users/{analyst_id}/lab-role",
                           data={"csrf_token": _users_form(client), "lab_role": LAB_ROLE_REVIEWER})
    assert "is now reviewer" in response.text
    assert lab.get(User, analyst_id).lab_role == LAB_ROLE_REVIEWER


def test_only_a_supervisor_changes_lab_roles(app, lab):
    with TestClient(app) as client:
        login(client, "an@lab.example")
        boss = lab.scalars(select(User).where(User.initials == "JM")).one()
        response = client.post(f"/admin/users/{boss.id}/lab-role",
                               data={"csrf_token": _users_form(client), "lab_role": LAB_ROLE_ANALYST})
        assert "Only a supervisor" in response.text
        form = {"csrf_token": _users_form(client), "email": "new@lab.example", "role": "staff",
                "password": PASSWORD, "initials": "NW", "lab_role": LAB_ROLE_REVIEWER}
        assert "Only a supervisor" in client.post("/admin/users", data=form).text


def test_staff_initials_are_unique(client, lab):
    login(client, "staff@lab.example")
    form = {"csrf_token": _users_form(client), "email": "dup@lab.example", "role": "staff",
            "password": PASSWORD, "initials": "an"}
    assert "Initials AN are taken" in client.post("/admin/users", data=form).text
