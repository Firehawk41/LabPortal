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
    """Demo rules published; JM supervisor (staff_user), RV reviewer, AN analyst; TR00001 received (2 samples on 10 Elements), TR00002 only
    submitted, TR00003 received on 36 Elements (no ruleset)."""
    publish_demo_rules(db, reference)
    for initials, lab_role in (("AN", LAB_ROLE_ANALYST), ("RV", LAB_ROLE_REVIEWER)):
        db.add(User(email=f"{initials.lower()}@lab.example", password_hash=hash_password(PASSWORD), role=ROLE_STAFF,
                    initials=initials, lab_role=lab_role))
    repo = TRSubmissionRepository(db)
    for analysis, receive in ((TEN, True), (TEN, False), (THIRTY_SIX, True)):
        tr = repo.add(submission(samples=(sample(1, analysis_ids=(analysis,)), sample(2, analysis_ids=(analysis,)))))
        if receive:
            repo.record_transition(tr, transition(tr, TRStatus.RECEIVED, actor=STAFF_ACTOR, at=NOW,
                                                  date_received=date(2026, 10, 9), received_by="JM"))
    db.commit()
    return db


def csv(tr="TR00001", analysis="10_elements_icpms", analyst="AN", batch="PB-1", run="RUN-1",
        spike="29.90", mdl_2="0.05") -> bytes:
    """Sample 1: cups agree, spiked (recovery ~0.99 by default); sample 2: cups agree, MDL `mdl_2`."""
    rows = [
        (f"{tr}-01", "Fe", "CUP", 1, "10.10", "", "0.05"), (f"{tr}-01", "Fe", "CUP", 2, "10.00", "", "0.05"),
        (f"{tr}-01", "Fe", "SPIKE", 1, spike, "20", "0.05"),
        (f"{tr}-02", "Fe", "CUP", 1, "5.10", "", mdl_2), (f"{tr}-02", "Fe", "CUP", 2, "5.00", "", mdl_2),
        ("BLANK", "Fe", "BLANK", 1, "0.010", "", "0.05"),
    ]
    lines = [HEADER] + [
        f"{s},{analysis},{code},{role},{rep},{value},ppb,{mdl},1,{run},ICP-MS 1,{analyst},"
        f"2026-10-10T09:00:00+00:00,{batch},microwave HNO3,{added},,"
        for s, code, role, rep, value, added, mdl in rows
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
    assert set(view["results"][0]["analyst_ids"]) == {
        str(u.id) for u in lab.scalars(select(User).where(User.initials.in_(["AN", "JM"])))
    }

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


# ---------------------------------------------------------------- slice 2: decisions on results

def staff_api(app, initials: str) -> TestClient:
    client = TestClient(app)
    login_api(client, f"{initials.lower()}@lab.example" if initials != "JM" else "staff@lab.example")
    return client


def tr_status(client, tr="TR00001") -> int:
    return client.get(f"/api/submissions/{tr}").json()["status"]


SAMPLE_1 = "/api/results/samples/TR00001-01/analyses/5"
SAMPLE_2 = "/api/results/samples/TR00001-02/analyses/5"


def test_first_readings_start_work_on_the_tr(app, lab):
    with staff_api(app, "AN") as an:
        assert upload(an, csv()).json()["started"] == ["TR00001"]
        assert tr_status(an) == TRStatus.IN_PROGRESS
        history = an.get("/api/submissions/TR00001").json()["status_history"]
        assert history[-1]["note"] == "first results imported"
        # Forward only: a later file for the same TR starts nothing.
        assert upload(an, csv(run="RUN-2", batch="PB-2"), name="run2.csv").json()["started"] == []


def test_review_and_release_with_roles_and_four_eyes(app, lab):
    with staff_api(app, "AN") as an, staff_api(app, "RV") as rv, staff_api(app, "JM") as jm:
        upload(jm, csv())  # JM uploads AN's file: both entered the readings
        refused = an.post("/api/results/batches/PB-1/review", json={})
        assert refused.status_code == 409 and "needs REVIEWER" in " ".join(refused.json()["problems"])
        refused = jm.post("/api/results/batches/PB-1/review", json={})
        assert refused.status_code == 409 and "entered readings" in " ".join(refused.json()["problems"])

        assert rv.post("/api/results/batches/PB-1/review", json={"note": "ok"}).json() == {"reviewed": 2}
        released = rv.post(f"{SAMPLE_1}/release", json={})
        assert released.status_code == 200 and released.json()["released"] == ["Fe"]
        assert tr_status(rv) == TRStatus.IN_PROGRESS  # a release moves results, not the TR (D-71)
        again = rv.post(f"{SAMPLE_1}/release", json={})
        assert again.status_code == 409


def test_needs_supervisor_is_accepted_by_a_supervisor(app, lab):
    with staff_api(app, "AN") as an, staff_api(app, "RV") as rv, staff_api(app, "JM") as jm:
        upload(an, csv(mdl_2=""))
        assert rv.post("/api/results/batches/PB-1/review", json={}).status_code == 200
        waiting = rv.post(f"{SAMPLE_2}/release", json={})
        assert waiting.status_code == 409 and "acceptance" in waiting.json()["waiting"][0]
        assert rv.post(f"{SAMPLE_2}/analytes/Fe/accept", json={"reason_category": "MDL from validation"}).status_code == 409
        assert jm.post(f"{SAMPLE_2}/analytes/Fe/accept", json={}).status_code == 422  # needs a category
        accepted = jm.post(f"{SAMPLE_2}/analytes/Fe/accept", json={"reason_category": "MDL from validation"})
        assert accepted.status_code == 200 and accepted.json()["event"] == "accepted"
        assert rv.post(f"{SAMPLE_2}/release", json={}).json()["released"] == ["Fe"]


def test_rerun_results_need_a_rerun_or_a_supervisors_exception(app, lab):
    with staff_api(app, "AN") as an, staff_api(app, "RV") as rv, staff_api(app, "JM") as jm:
        upload(an, csv(spike="60"))
        body = {"reason_category": "Recovery outside window", "note": "matrix interference, confirmed"}
        assert rv.post(f"{SAMPLE_1}/analytes/Fe/exception", json=body).status_code == 409
        assert jm.post(f"{SAMPLE_1}/analytes/Fe/exception", json={"reason_category": "x"}).status_code == 422
        assert jm.post(f"{SAMPLE_1}/analytes/Fe/exception", json=body).json()["event"] == "exception"
        assert rv.post(f"{SAMPLE_2}/analytes/Fe/rerun", json={"note": "spike again"}).json()["event"] == "rerun_requested"
        # Waiting on its rerun, sample 2 is left out of the review; sample 1 is reviewed and released.
        assert rv.post("/api/results/batches/PB-1/review", json={}).json() == {"reviewed": 1}
        assert rv.post(f"{SAMPLE_1}/release", json={}).json()["released"] == ["Fe"]


def test_reject_and_correct_need_a_reason(app, lab):
    with staff_api(app, "AN") as an, staff_api(app, "RV") as rv:
        upload(an, csv())
        assert rv.post(f"{SAMPLE_2}/analytes/Fe/reject", json={}).status_code == 422
        assert rv.post(f"{SAMPLE_2}/analytes/Fe/reject", json={"note": "broken vial"}).json()["event"] == "rejected"
        rv.post("/api/results/batches/PB-1/review", json={})
        rv.post(f"{SAMPLE_1}/release", json={})
        corrected = an.post(f"{SAMPLE_1}/analytes/Fe/correct", json={"note": "wrong dilution"})
        assert corrected.status_code == 200 and corrected.json()["event"] == "correction_started"
        assert an.post("/api/results/batches/PB-1/re-evaluate", json={}).json()["new_versions"] == 1


def test_unknown_results_and_batches_are_404(app, lab):
    with staff_api(app, "RV") as rv:
        assert rv.post("/api/results/batches/PB-404/review", json={}).status_code == 404
        assert rv.post("/api/results/samples/nonsense/analyses/5/release", json={}).status_code == 404
        assert rv.post(f"{SAMPLE_1}/analytes/Fe/accept", json={"reason_category": "x"}).status_code == 404


def test_decisions_are_staff_only(app, lab, customer_user):
    with TestClient(app) as client:
        login_api(client, "jane@acme.example")
        assert client.post("/api/results/batches/PB-1/review", json={}).status_code == 403
        assert client.post(f"{SAMPLE_1}/release", json={}).status_code == 403


def test_batch_page_actions(app, lab):
    with staff_api(app, "AN") as an:
        upload(an, csv())
        page = an.get("/results/batches/PB-1")
        assert "Review every draft" in page.text and "Request a rerun" in page.text and "Release" in page.text
        token = csrf_from(page.text)
        refused = an.post("/results/batches/PB-1/review", data={"csrf_token": token})
        assert "Nothing was reviewed" in refused.text and "needs REVIEWER" in refused.text
    with staff_api(app, "RV") as rv:
        token = csrf_from(rv.get("/results/batches/PB-1").text)
        assert "Reviewed 2 result(s)" in rv.post("/results/batches/PB-1/review", data={"csrf_token": token}).text
        released = rv.post("/results/batches/PB-1/release",
                           data={"csrf_token": token, "sample": "TR00001-01", "analysis_id": TEN})
        assert "Released TR00001-01: [&#39;Fe&#39;]" in released.text
        rejected = rv.post("/results/batches/PB-1/act", data={
            "csrf_token": token, "sample": "TR00001-02", "analysis_id": TEN, "analyte": "Fe",
            "action": "reject", "note": "broken vial"})
        assert "TR00001-02 Fe: rejected." in rejected.text
        reevaluated = rv.post("/results/batches/PB-1/re-evaluate", data={"csrf_token": token})
        assert "Re-evaluated: 0 new version(s)" in reevaluated.text
