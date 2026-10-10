# slim-lab-portal

The sample submission portal for the **SLIM** LIMS ecosystem
([slim-domain](https://github.com/Firehawk41/slim-domain-oss),
[slim-report-engine](https://github.com/Firehawk41/slim-report-engine-oss),
[slim-lims](https://github.com/Firehawk41/slim-lims-oss)), built for an ISO 17025 accredited
analytical chemistry lab.

Customers log in and submit Testing Requests; lab staff receive the samples and track each
request from submission to invoice. Submissions are stored as Testing Request domain objects in
the shape defined in [`docs/SLIM_DOMAIN_V2.md`](docs/SLIM_DOMAIN_V2.md), so the rest of the LIMS
can consume them directly — no Excel in between.

> **Status:** rebuilt from a standalone Flask form ("LabPortal") into a FastAPI module of the SLIM
> ecosystem. Submission, lab workflow and reference data work end to end on the OSS demo data, and
> received requests feed the OSS report engine (`slim_lab_portal/bridge.py`). See `CLAUDE.md` for
> what's next.

## What it does

- **Customers** submit Testing Requests: one request type (Chemical / Water / Wafer), a
  spreadsheet-like sample table (paste a column of IDs, Ctrl+D fills down), free-text chemical /
  matrix, and one analysis panel that applies to the ticked samples or to all of them. Each request
  gets a TR number (`TR00001`…) and its status is visible to the customer.
- **Lab staff** receive samples, move requests through submitted → received → in progress →
  partial report → complete report → invoiced (or cancelled), match free-text chemicals to SLIM,
  and manage users.
- **SLIM reference data** (customers, chemicals, elements, analyses) is read from the shared
  database through a periodically refreshed cache.
- **JSON API** at `/api/docs`; every request is also available as the TR domain object.

## OSS only

This is a portfolio module. It connects **only** to the open-source SLIM repos and their fictional
demo data — never to a real lab's systems. `slim_lab_portal/oss_guard.py` enforces it: database URLs
mentioning "precilab" are always refused, and only local/demo hosts are allowed unless explicitly
listed in `PORTAL_ALLOWED_DB_HOSTS`.

## Tech stack

| Layer | Technology |
|---|---|
| Web | Python 3.11+, FastAPI, Jinja2 (server-rendered pages) |
| Domain | pydantic v2 (frozen models, shared shape with slim-domain) |
| Database | PostgreSQL (shared with SLIM) or SQLite, SQLAlchemy 2, Alembic |
| Auth | Signed-cookie sessions, bcrypt, CSRF tokens |
| Frontend | Server-rendered pages + vanilla JS (no frameworks, no inline scripts) |

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Fictional SLIM reference data from the OSS repos (checked out next to this one):
pip install -e ../slim-domain-oss[postgres] -e ../slim-report-engine-oss
python scripts/seed_demo.py
PORTAL_PASSWORD='at-least-12-chars' python -m slim_lab_portal.cli create-staff --email you@lab.example --initials JM
uvicorn --factory slim_lab_portal.main:create_app --reload
```

Open http://127.0.0.1:8000 (API docs at `/api/docs`). Create a customer user with
`python -m slim_lab_portal.cli create-customer-user --email you@customer.example --customer-id 1`.
Run the tests with `pytest`; `e2e/request_flow.js` is a Playwright run-through of the form.

With Docker: `docker compose up --build`, then create a staff user with
`docker compose exec portal python -m slim_lab_portal.cli create-staff ...`.

## Security

- Content-Security-Policy without `'unsafe-inline'`, `X-Frame-Options: DENY`, `nosniff`,
  strict referrer policy; HSTS in production.
- CSRF tokens on every state-changing route (enforced by a test).
- `SameSite=Lax`, `HttpOnly` session cookies (`Secure` in production); session rotated on login.
- 1 MB request body cap.
