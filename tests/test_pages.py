"""Server-rendered pages: request list/detail, staff actions, users."""

import re
from datetime import date, timedelta

import pytest

from tests.conftest import csrf_from, login, login_api
from tests.test_api_submissions import payload


@pytest.fixture
def submitted(client, staff_user, customer_user):
    """TR00001 for customer A (id 1), submitted by the customer; client left logged out."""
    login_api(client, "jane@acme.example")
    assert client.post("/api/submissions", json=payload()).status_code == 201
    client.post("/logout", data={"csrf_token": client.headers.pop("X-CSRF-Token")})
    return client


def _post_status(client, page_path, **data):
    token = csrf_from(client.get(page_path).text)
    return client.post(f"{page_path}/status", data={"csrf_token": token, **data})


def test_customer_list_and_detail(submitted):
    login(submitted, "jane@acme.example")
    listing = submitted.get("/").text
    assert "TR00001" in listing and "Submitted" in listing
    detail = submitted.get("/requests/TR00001").text
    assert "S-001" in detail and "36 Elements" in detail and "Fe" in detail  # names, not IDs
    assert "Report by 15:00" in detail.replace("report by", "Report by")
    assert "Cancel request" in detail and "Mark received" not in detail


def test_new_request_page_loads_form_script(client, customer_user):
    login(client, "jane@acme.example")
    page = client.get("/requests/new").text
    assert 'id="request-form"' in page
    assert "/static/js/request_form.js" in page
    assert "<script>" not in page  # CSP: no inline scripts


def test_customer_cannot_open_other_customers_request(client, staff_user, customer_user, db):
    login_api(client, "staff@lab.example")
    client.post("/api/submissions", json=payload(customer_id=2, location="SX5N"))
    client.post("/logout", data={"csrf_token": client.headers.pop("X-CSRF-Token")})
    login(client, "jane@acme.example")
    assert client.get("/requests/TR00001").status_code == 404


def test_staff_receives_and_progresses(submitted):
    login(submitted, "staff@lab.example")
    detail = submitted.get("/requests/TR00001").text
    assert "Mark received" in detail and 'name="received_by" value="JM"' in detail
    response = _post_status(submitted, "/requests/TR00001", to_status="2",
                            date_received=date.today().isoformat(), received_by="JM", note="2 bottles")
    assert "TR00001 is now received." in response.text
    assert "2 bottles" in response.text
    response = _post_status(submitted, "/requests/TR00001", to_status="3")
    assert "is now in progress" in response.text


def test_bad_status_change_is_flashed_not_500(submitted):
    login(submitted, "staff@lab.example")
    future = (date.today() + timedelta(days=3)).isoformat()
    response = _post_status(submitted, "/requests/TR00001", to_status="2", date_received=future, received_by="JM")
    assert response.status_code == 200 and "future" in response.text
    response = _post_status(submitted, "/requests/TR00001", to_status="6")
    assert "cannot move" in response.text


def test_customer_cancels_from_page(submitted):
    login(submitted, "jane@acme.example")
    response = _post_status(submitted, "/requests/TR00001", to_status="7", note="sent twice")
    assert "is now cancelled" in response.text and "Cancel request" not in response.text


def test_staff_home_filters(submitted):
    login(submitted, "staff@lab.example")
    assert "TR00001" in submitted.get("/admin?status=1").text
    assert "TR00001" not in submitted.get("/admin?status=7").text
    assert "TR00001" in submitted.get("/admin?status=&request_type=bogus").text  # junk filters ignored


def test_staff_creates_and_deactivates_users(client, staff_user):
    login(client, "staff@lab.example")
    page = client.get("/admin/users").text
    token = csrf_from(page)
    form = {"csrf_token": token, "email": "New@B.example", "role": "customer", "password": "x" * 12}
    assert "must already exist in SLIM" in client.post("/admin/users", data={**form, "customer_id": "99"}).text
    assert "Created customer user new@b.example" in client.post("/admin/users", data={**form, "customer_id": "2"}).text
    assert "already exists" in client.post("/admin/users", data={**form, "customer_id": "2"}).text
    assert "need initials" in client.post("/admin/users", data={**form, "email": "s@lab.example", "role": "staff"}).text
    page = client.get("/admin/users").text
    assert "new@b.example" in page and ">B<" in page.replace("<td>B</td>", ">B<")

    user_id = re.search(r'/admin/users/([0-9a-f-]{36})/active', page).group(1)
    assert "deactivated" in client.post(f"/admin/users/{user_id}/active", data={"csrf_token": token}).text


def test_customers_cannot_open_staff_pages(client, customer_user):
    login(client, "jane@acme.example")
    assert client.get("/admin/users").status_code == 403
