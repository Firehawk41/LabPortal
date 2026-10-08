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

> **Status:** being rebuilt from a standalone Flask form ("LabPortal") into a FastAPI module of
> the SLIM ecosystem. The skeleton (auth, CSRF, security headers, migrations, tests) is in place;
> the submission form and lab workflow are being ported. See `CLAUDE.md` for progress.

## Tech stack

| Layer | Technology |
|---|---|
| Web | Python 3.11+, FastAPI, Jinja2 (server-rendered pages) |
| Domain | pydantic v2 (frozen models, shared shape with slim-domain) |
| Database | PostgreSQL (shared with SLIM) or SQLite, SQLAlchemy 2, Alembic |
| Auth | Signed-cookie sessions, bcrypt, CSRF tokens |
| Frontend | Vanilla JS, jQuery, Select2, Tagify |

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

Open http://127.0.0.1:8000 (API docs at `/api/docs`). Run the tests with `pytest`.

With Docker: `docker compose up --build`, then create a staff user with
`docker compose exec portal python -m slim_lab_portal.cli create-staff ...`.

## Security

- Content-Security-Policy without `'unsafe-inline'`, `X-Frame-Options: DENY`, `nosniff`,
  strict referrer policy; HSTS in production.
- CSRF tokens on every state-changing route (enforced by a test).
- `SameSite=Lax`, `HttpOnly` session cookies (`Secure` in production); session rotated on login.
- 1 MB request body cap.
