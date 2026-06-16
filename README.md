# LabPortal — Lab Testing Request Portal

A Flask web application for an ISO 17025 accredited analytical chemistry lab. Customers log in to submit multi-section laboratory testing requests (company info, payment, email distribution lists, and one or more samples with analysis selections). Lab staff use an admin dashboard to review submissions, update their status, and manage customer accounts.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 / Flask (application factory + Blueprints) |
| Database | PostgreSQL via SQLAlchemy ORM |
| Auth | Flask-Login + Flask-Bcrypt |
| Validation | marshmallow |
| Frontend | HTML5, vanilla JS, jQuery, Select2, Tagify (CDN, unchanged) |
| Production server | gunicorn |

## Architecture

```
app/
├── __init__.py        # create_app() factory
├── extensions.py      # db, bcrypt, login_manager
├── domain.py           # Pure dataclasses (Sample, TestingRequest) — no Flask/SQLAlchemy
├── models.py            # SQLAlchemy models — User, Submission, Sample, AuditLog
├── schemas.py            # marshmallow schemas — validate/deserialize JSON into domain objects
├── repositories.py        # SubmissionRepository — translates domain objects <-> ORM models
├── auth/                    # Login/logout blueprint
├── main/                    # Customer-facing form + /submit blueprint
├── admin/                   # Admin dashboard blueprint
└── templates/               # Jinja2 templates (base, login, form, admin/*)
static/                       # CSS, JS, analyses.json (unchanged)
wsgi.py                       # WSGI entry point (`app = create_app()`)
seed.py                       # Creates tables + demo data
```

Routes never touch the ORM directly for submissions — they call `SubmissionRepository`, which translates between the pure `TestingRequest`/`Sample` dataclasses in `domain.py` and the SQLAlchemy models in `models.py`.

---

## Setup

### Option 1: Docker Compose (recommended for local dev)

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# edit .env and set FLASK_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
docker compose up --build
```

This starts a `web` service (the Flask app via gunicorn) and a `db` service (PostgreSQL 15) with a named volume for persistence. The app is available at `http://localhost:5000`.

To create the database tables and load demo data:

```bash
docker compose exec web python seed.py
```

### Option 2: Manual local dev (no Docker)

Requires Python 3.11 and a running PostgreSQL server.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create a database and user matching your DATABASE_URL, e.g.:
#   createuser postgres
#   createdb labportal

cp .env.example .env
# edit .env: set FLASK_SECRET_KEY, DATABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD

python seed.py        # creates tables + demo data
python wsgi.py        # http://127.0.0.1:5000
```

### Option 3: Deploy to Render

This repo includes a `render.yaml` blueprint that provisions a web service and a managed PostgreSQL database.

1. Push this repository to GitHub.
2. In Render, create a new **Blueprint** from the repository — Render will read `render.yaml` and provision both the web service and the database automatically.
3. Set the `ADMIN_EMAIL` and `ADMIN_PASSWORD` environment variables on the web service (marked `sync: false` in `render.yaml`, so Render will prompt for them).
4. After the first deploy, open a shell on the web service (or use Render's one-off job feature) and run:
   ```bash
   python seed.py
   ```
   to create tables and load demo data.
5. Visit the deployed URL and log in with the admin credentials you set.

`FLASK_SECRET_KEY` and `DATABASE_URL` are populated automatically by Render (`generateValue` and `fromDatabase` respectively).

---

## Seeding Demo Data

`seed.py`:

- Creates all database tables (`users`, `submissions`, `samples`, `audit_log`).
- Creates one **admin** account from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (prints a warning if these env vars are unset and falls back to `admin@example.com` / `changeme` — change these immediately in any shared environment).
- Creates three **customer** accounts for realistic analytical-chemistry companies (Apex Analytics Inc., Silver Creek Materials, Northwind Semiconductor).
- Creates five sample **submissions** across the customer accounts with varied statuses (`received`, `in_progress`, `complete`), each with one to three samples drawn from realistic chemical matrices (IPA, DI Water, Silicon Wafer, HCl, NaOH) and analyses from `static/data/analyses.json`.

Re-running `seed.py` is safe — it skips users/submissions that already exist.

---

## Roles & Routes

| Role | Access |
|---|---|
| `customer` | `/` (testing request form), `/submit` |
| `admin` | Everything a customer can access, plus `/admin/submissions`, `/admin/submissions/<id>`, `/admin/users` |

There is no public self-registration — admins create customer accounts via `/admin/users/create`.

---

## License

MIT — see [LICENSE](LICENSE).
