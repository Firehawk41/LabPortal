# slim-lab-portal — Claude Context

## What This Is

The sample submission portal for the SLIM LIMS ecosystem (slim-domain, slim-report-engine,
slim-lims), built for an ISO 17025 accredited analytical chemistry lab. Customers log in and
submit Testing Requests (TRs); lab staff receive samples and move TRs through their statuses.
The portal replaces the Excel Testing Request form as the primary intake path; emailed `.xlsx`
forms stay supported by slim-domain's parsers for back-compatibility. The portal never produces
Excel — it produces TR domain objects.

**The domain spec is `docs/SLIM_DOMAIN_V2.md`. Read it before changing anything under
`slim_lab_portal/domain/`, the TR tables, enums or statuses.**

## Rebuild status (branch `claude/slim-lab-portal-rebuild`)

The repo was a Flask app ("LabPortal"); it is being rebuilt on FastAPI. Old code is in git
history (`main` before the rebuild) — e.g. `git show main:app/templates/form.html`.

1. ✅ Spec: `docs/SLIM_DOMAIN_V2.md`
2. ✅ FastAPI skeleton: config, SQLAlchemy 2, Alembic, session auth, CSRF, security headers, pytest
3. ⬜ Domain objects (pydantic, per spec §3–4), input models, repositories, TR number counter
4. ⬜ Reference-data cache over SLIM tables; `scripts/seed_reference.py` with demo data
5. ⬜ Port form + JS (per-request-type fields, catalog from cache), receipt, statuses, JSON view
6. ⬜ Admin: customers (pick existing SLIM customers only), users (many per customer), profiles
7. ⬜ Ecosystem docker-compose (portal + slim-lims + Postgres + Caddy) for the portfolio VPS; README

## How to Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                     # DATABASE_URL defaults to sqlite:///slim_lab_portal.db
alembic -c slim_lab_portal/alembic.ini upgrade head
PORTAL_PASSWORD='at-least-12-chars' python -m slim_lab_portal.cli create-staff --email you@lab.example --initials JM
uvicorn --factory slim_lab_portal.main:create_app --reload   # http://127.0.0.1:8000, API docs at /api/docs
pytest
```

Or `docker compose up --build` (portal + Postgres 16 on :8000).

## File Map

```
slim_lab_portal/
├── main.py          # create_app(settings, engine): middleware, routers, exception handlers, /health
├── config.py        # Settings from env (APP_ENV, SECRET_KEY, DATABASE_URL, ...)
├── db.py            # Base (portal-owned tables only), make_engine, get_db dependency
├── models.py        # SQLAlchemy models: User
├── security.py      # bcrypt hashing, CSRF (csrf_token / csrf_protect), headers + body-size middleware
├── auth.py          # current_user / require_user / require_staff deps; /login, /logout
├── routes.py        # Page routes: / , /admin, /api/me (placeholders until steps 5–6)
├── web.py           # Jinja2 templates, render(), flash()
├── cli.py           # create-staff, create-customer-user
├── alembic.ini, migrations/   # Alembic; only manages tables on db.Base
├── templates/       # base, login, index, error, admin/home
└── static/          # css/style.css, css/admin.css (.admin-theme), js/script.js (old form JS, to port)
tests/               # pytest; SQLite per test via conftest.py
docs/SLIM_DOMAIN_V2.md
```

## Architecture Rules

- **Layers:** `domain/` (pure pydantic + stdlib, liftable into slim-domain unchanged) ← input
  models validate HTTP input ← repositories are the only code that touches the DB for TRs.
- **Data ownership:** one Postgres shared with SLIM. The portal only READS SLIM reference tables
  (customers, chemicals, elements, analyses) and never declares them on `db.Base`; Alembic must
  never create/alter them. No FKs from portal tables into SLIM tables.
- **Portable schema:** must run on SQLite and Postgres (as slim-domain does) — no ARRAY columns,
  enums stored as ints. Portal-owned TR tables use integer keys; `users` uses UUIDs.
- **Auth:** Starlette signed-cookie sessions (`SameSite=Lax`, `Secure` in production), bcrypt.
  Roles: `customer` (must have `customer_id`, a SLIM customer ID) and `staff` (must have
  `initials`). No self-registration; staff create users. Customers must already exist in SLIM.
- **CSRF:** every router is created with `dependencies=[Depends(csrf_protect)]`. Forms send
  `csrf_token`; fetch/JSON sends the `X-CSRF-Token` header (token in `<meta name="csrf-token">`).
  `tests/test_app.py` fails if any state-changing route accepts a request without a token.
- **CSP:** no `'unsafe-inline'` — never add inline `<script>`; pass server data via `data-*`
  attributes. Allowed script hosts: code.jquery.com, cdn.jsdelivr.net.
- **Errors:** invalid input → 422 with per-field detail (FastAPI default). HTML routes render
  `error.html`; `/api/*` and `Accept: application/json` get JSON. Unauthenticated: HTML → 303 to
  `/login?next=...`, API → 401. Non-staff on staff routes → 403.
- **Routes are plain `def`** (sync SQLAlchemy), not `async def`.
- 1 MB request cap (`MAX_BODY_BYTES`), enforced with or without Content-Length.

## Key Decisions (see the spec for detail)

- One request type (Chemical / Water / Wafer) per submission; per-type sample fields.
- TR numbers `TR00001`… from a gapless counter row locked in the submit transaction.
- Statuses: submitted → received → in progress → partial report (repeatable) → complete report
  → invoiced (terminal, staff only); cancelled (customer may cancel only while submitted).
- Payment: purchase order (PO number, also used for billing codes) or credit card (lab calls;
  no card data stored).
- Call-in RUSH = outside business hours. Wafer sizes 200 / 300 mm; units atoms/cm² or
  10¹⁰ atoms/cm². Water packages exist in the shape but are not offered yet.
- Hosting target: portfolio VPS running the whole ecosystem via Docker Compose. `render.yaml`
  keeps the old Render resource names so Render doesn't create a new empty database.

## Backlog (carried over, still open)

- SRI hashes on CDN links / self-host CDN dependencies
- File attachments (COAs, SDSs, protocols)
- Email notifications (confirmation to customer, alert to lab) — out of scope until specced
- Login rate limiting
