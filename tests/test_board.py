"""The lab board (spec §13), on the seeded demo scenarios: columns follow what happened, chips say
what each sample × analysis needs, and each role sees less than the supervisor."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from slim_lab_portal import board as b
from slim_lab_portal.domain import TRStatus
from slim_lab_portal.models import User
from slim_lab_portal.repositories import TRSubmissionRepository
from tests.conftest import make_settings
from tests.factories import sample, submission
from tests.test_demo_scenarios import TEN, reference, seeded, specs  # noqa: F401 (fixtures)


def persona(db, email):
    return db.scalars(select(User).where(User.email == email)).one()


def where(columns, tr_number):
    return next((key, card) for key, _, cards in columns for card in cards if card.tr.tr_number == tr_number)


def test_columns_follow_what_happened(db, seeded, reference):
    TRSubmissionRepository(db).add(submission(samples=(sample(1, analysis_ids=(TEN,)),)))  # TR00010: expected
    db.commit()
    columns = b.board(db, persona(db, "sue@demo.example"), reference)
    assert where(columns, "TR00010")[0] == "expected"
    assert where(columns, "TR00010")[1].chips[0].state == "expected"
    assert where(columns, seeded["scale_fault"])[0] == "in_analysis"  # nothing reviewed yet
    assert {c.state for c in where(columns, seeded["scale_fault"])[1].chips} == {"to_review"}
    assert where(columns, seeded["cups_disagree"])[0] == "ready_to_report"  # released, never issued
    assert where(columns, seeded["line_by_line"])[0] == "ready_to_report"  # sample 1 could go out now
    states = [c.state for c in where(columns, seeded["line_by_line"])[1].chips]
    assert states == ["released", "to_review"]
    clean = where(columns, seeded["clean_pass"])
    assert clean[0] == "to_invoice" and {c.state for c in clean[1].chips} == {"reported"}
    assert clean[1].batches == [f"PB-{seeded['clean_pass'][2:]}"]


def test_needs_me_narrows_by_lab_role(db, seeded, reference):
    def mine(email):
        return {card.tr.tr_number for _, _, cards in b.board(db, persona(db, email), reference, mine=True)
                for card in cards}

    assert seeded["scale_fault"] in mine("rob@demo.example")  # reviews it
    assert seeded["clean_pass"] not in mine("rob@demo.example")
    assert {seeded["clean_pass"], seeded["scale_fault"]} <= mine("sue@demo.example")  # invoice, review
    assert mine("ana@demo.example") == set()  # nothing awaits readings in the demo


def test_supervisor_board_has_every_action_and_marks_invoiced(engine, db, seeded, reference):
    from slim_lab_portal.main import create_app

    app = create_app(make_settings(str(engine.url), demo_personas=True), engine=engine, reference=reference,
                     specs=specs)
    sue = str(persona(db, "sue@demo.example").id)
    db.rollback()  # end this session's read: SQLite would lock the app's write
    with TestClient(app) as client:
        page = client.get("/demo/personas").text
        token = page.split('name="csrf_token" value="')[1].split('"')[0]
        client.post("/demo/continue-as", data={"csrf_token": token, "user_id": sue})
        board = client.get("/").text
        for label in ("Lab board", "Issue report", "Open report", "Mark invoiced", "Upload results", "To review"):
            assert label in board, label
        token = board.split('name="csrf_token" value="')[1].split('"')[0]
        tr = seeded["clean_pass"]
        response = client.post(f"/requests/{tr}/status", data={"csrf_token": token, "to_status": TRStatus.INVOICED.value,
                                                               "back_to_board": "1"}, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/"
    db.expire_all()
    assert TRSubmissionRepository(db).get_by_tr_number(tr).status == TRStatus.INVOICED
    assert where(b.board(db, persona(db, "sue@demo.example"), reference), tr)[0] == "invoiced"


def test_customers_see_their_own_requests_in_plain_columns(engine, db, seeded, reference):
    from slim_lab_portal.main import create_app

    app = create_app(make_settings(str(engine.url), demo_personas=True), engine=engine, reference=reference,
                     specs=specs)
    customer = db.scalars(select(User).where(User.is_persona.is_(True), User.customer_id.is_not(None))).one()
    columns = b.board(db, customer, reference)
    assert [title for _, title, _ in columns] == ["Submitted", "In the lab", "Partial report", "Complete", "Invoiced"]
    shown = {card.tr.tr_number for _, _, cards in columns for card in cards}
    assert seeded["cups_disagree"] not in shown  # customer B's
    assert seeded["clean_pass"] in shown
    with TestClient(app) as client:
        page = client.get("/demo/personas").text
        token = page.split('name="csrf_token" value="')[1].split('"')[0]
        client.post("/demo/continue-as", data={"csrf_token": token, "user_id": str(customer.id)})
        board = client.get("/").text
        assert "My requests" in board and "Mark invoiced" not in board and "chip--" not in board
        assert "Upload results" not in board and seeded["cups_disagree"] not in board
