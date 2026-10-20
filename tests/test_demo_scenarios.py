"""slim-data's named demo scenarios on real portal TRs (slim-data D-75)."""

import pytest
from fastapi.testclient import TestClient
from slim_data.persistence import migrate
from slim_data.persistence.results import issues_for_tr
from slim_data.service.views import batch_view, report_view

from slim_lab_portal.demo_scenarios import seed_scenarios
from slim_lab_portal.domain import RequestType, TRStatus
from slim_lab_portal.personas import sync_personas
from slim_lab_portal.reference import AnalysisRef, ChemicalRef, CustomerRef, ElementRef, StaticReferenceData
from slim_lab_portal.repositories import TRSubmissionRepository
from slim_lab_portal.results import document_sha256, publish_demo_rules, report_document
from tests.conftest import make_settings

ELEMENTS = {26: "Fe", 29: "Cu", 30: "Zn", 28: "Ni", 24: "Cr", 25: "Mn"}
SPECS = {(2, 2, ""): {"Zn": 0.2}}  # customer B, Chemical 01, as in the OSS demo data


@pytest.fixture
def reference():
    return StaticReferenceData.of(
        customers=[CustomerRef(1, "A", "1 A Street"), CustomerRef(2, "B", "2 B Street")],
        chemicals=[ChemicalRef(2, "Chemical 01")],
        elements=[ElementRef(i, s, s) for i, s in ELEMENTS.items()],
        analyses=[AnalysisRef(1, "10 Elements", "10_elements_icpms", "Metals",
                              request_types=frozenset({RequestType.CHEMICAL}))],
    )


def specs(customer, chemical, location):
    return SPECS.get((customer, chemical, location), {})


@pytest.fixture
def seeded(engine, db, reference):
    with engine.begin() as connection:
        migrate.downgrade(connection)
        migrate.upgrade(connection)
    publish_demo_rules(db, reference)
    sync_personas(db)
    trs = seed_scenarios(db, reference, specs)
    db.commit()
    return trs


def test_every_scenario_runs_on_its_own_received_tr(db, seeded):
    assert list(seeded) == ["clean_pass", "cups_disagree", "scale_fault", "pooled_spike", "below_mdl",
                            "rerun_exception", "accepted", "amended", "line_by_line"]
    assert list(seeded.values()) == [f"TR{n:05d}" for n in range(1, 10)]
    tr = TRSubmissionRepository(db).get_by_tr_number(seeded["cups_disagree"])
    assert tr.customer_id == 2 and tr.samples[0].analysis_ids == (1,)


def test_statuses_follow_d71(db, seeded):
    status = {name: TRSubmissionRepository(db).get_by_tr_number(tr).status for name, tr in seeded.items()}
    assert status["clean_pass"] == status["amended"] == status["rerun_exception"] == TRStatus.COMPLETE_REPORT
    assert status["scale_fault"] == status["line_by_line"] == status["accepted"] == TRStatus.IN_PROGRESS


def test_results_and_issues_are_the_portals(db, seeded):
    assert report_view(db, seeded["cups_disagree"]).lines[0].shown_flags == ("ABOVE_SPEC",)
    issues = issues_for_tr(db, seeded["amended"])
    assert [i.amends for i in issues] == [None, issues[0].id]
    # The last issue's hash is what "Issue report" would record for the report as it stands (D-73).
    assert issues[-1].file_sha256 == document_sha256(report_document(report_view(db, seeded["amended"])))
    analysts = {r.analyst_ids for r in batch_view(db, f"PB-{seeded['clean_pass'][2:]}").results}
    assert len(analysts) == 1  # the analyst persona (file analyst and uploader)


def test_runs_once(db, seeded, reference):
    assert seed_scenarios(db, reference, specs) == {}


def test_a_visitor_sees_the_history(engine, reference, seeded):
    from slim_lab_portal.main import create_app

    app = create_app(make_settings(str(engine.url), demo_personas=True), engine=engine, reference=reference,
                     specs=specs)
    with TestClient(app) as client:
        page = client.get("/demo/personas").text
        rob = page.split('name="user_id" value="')[2].split('"')[0]  # customer, ana, rob, sue
        token = page.split('name="csrf_token" value="')[1].split('"')[0]
        client.post("/demo/continue-as", data={"csrf_token": token, "user_id": rob})
        assert "PB-00009" in client.get("/results").text
        report = client.get(f"/results/reports/{seeded['amended']}").text
        assert "Amended" in report and "(amends" in report
