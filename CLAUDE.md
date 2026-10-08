# slim-lab-portal — Claude Context

> ## ⚠️ OSS ONLY — read first
> This portal is a **portfolio demo** that attaches to the **open-source** SLIM repos only:
> `slim-domain-oss`, `slim-report-engine-oss`, `slim-lims-oss` and their fictional demo data.
> **Never connect it to PreciLab (or any real lab) production databases, shares or services.**
> Enforced in code: `slim_lab_portal/oss_guard.py` refuses any database URL containing
> "precilab" (no override) and any host other than localhost / 127.0.0.1 / `db` / `postgres`
> unless listed in `PORTAL_ALLOWED_DB_HOSTS`. Every connection goes through `db.make_engine`;
> `tests/test_oss_guard.py` fails if anything calls `create_engine` elsewhere. `.env` is read
> from the current directory only. Do not weaken any of this.
>
> **Scope:** modular but narrow. Don't modify slim-domain / slim-report-engine / slim-lims yet —
> the portal must fit them, not the other way round. Ideas worth having later go in the spec's
> "Parked ideas" list (docs/SLIM_DOMAIN_V2.md §11) and get raised with the user, not built.

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
3. ✅ Domain objects (pydantic, per spec §3–4), input models, repository, TR number counter, JSON API
4. ✅ Reference-data cache over SLIM tables, analysis catalog, `scripts/seed_demo.py` (OSS demo data)
5. ⬜ Port form + JS (per-request-type fields, catalog from cache), receipt, statuses, JSON view
6. ⬜ Admin: customers (pick existing SLIM customers only), users (many per customer), profiles
7. ⬜ Ecosystem docker-compose (portal + slim-lims + Postgres + Caddy) for the portfolio VPS; README

## How to Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                     # DATABASE_URL defaults to sqlite:///slim_lab_portal.db
pip install -e ../slim-domain-oss[postgres] -e ../slim-report-engine-oss   # OSS repos, for the demo seed
python scripts/seed_demo.py              # migrations + OSS demo SLIM data + analysis_catalog
PORTAL_PASSWORD='at-least-12-chars' python -m slim_lab_portal.cli create-staff --email you@lab.example --initials JM
uvicorn --factory slim_lab_portal.main:create_app --reload   # http://127.0.0.1:8000, API docs at /api/docs
pytest                                   # TEST_DATABASE_URL=postgresql+psycopg2://... pytest  to run on Postgres
```

Or `docker compose up --build` (portal + Postgres 16 on :8000).

## File Map

```
slim_lab_portal/
├── main.py          # create_app(settings, engine): middleware, routers, exception handlers, /health
├── config.py        # Settings from env (APP_ENV, SECRET_KEY, DATABASE_URL, ...)
├── db.py            # Base (portal-owned tables only), make_engine (the only way to connect), get_db
├── oss_guard.py     # OSS-ONLY guard: refuses "precilab" URLs and non-demo hosts (called by make_engine)
├── domain/          # Spec §3–4: enums.py, tr.py (TRSubmission, TRSample, ...), workflow.py (transitions)
├── models.py        # SQLAlchemy models: User + TR tables (tr_submissions, tr_samples, ...)
├── repositories.py  # TRSubmissionRepository: domain <-> rows, gapless TR numbers, stale-update check
├── schemas.py       # Input models (SubmissionIn, SampleIn, StatusChangeIn) — shape/type validation only
├── services.py      # SubmissionService: reference-data rules, access rules, submit/list/get/change_status
├── reference.py     # ReferenceData protocol, StaticReferenceData (snapshot + form choices)
├── reference_cache.py  # ReferenceCache: loads SLIM tables + analysis_catalog, TTL refresh, keeps last good copy
├── slim_tables.py   # Read-only Core defs of SLIM's customers/chemicals/elements/analyses (own MetaData)
├── catalog.py       # sync_analysis_catalog: data/analysis_catalog.csv -> analysis_catalog, matched by SLIM name
├── data/analysis_catalog.csv  # Spec §8 code/group/request-type table
├── api.py           # /api/submissions JSON API; maps service errors to 422/403/404/409
├── security.py      # bcrypt hashing, CSRF (csrf_token / csrf_protect), headers + body-size middleware
├── auth.py          # current_user / require_user / require_staff deps; /login, /logout
├── routes.py        # Page routes: / , /admin, /api/me (placeholders until steps 5–6)
├── web.py           # Jinja2 templates, render(), flash()
├── cli.py           # create-staff, create-customer-user, sync-analysis-catalog
├── alembic.ini, migrations/   # Alembic; only manages tables on db.Base
├── templates/       # base, login, index, error, admin/home
└── static/          # css/style.css, css/admin.css (.admin-theme), js/script.js (old form JS, to port)
scripts/seed_demo.py # Demo DB only: runs slim-report-engine-oss demo seed() if SLIM tables are empty, syncs catalog
tests/               # pytest; SQLite per test, or Postgres via TEST_DATABASE_URL; factories.py builds domain objects
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
- **API:** `POST /api/submissions` (201), `GET /api/submissions[?status&request_type&page]`,
  `GET /api/submissions/{tr_number}`, `POST /api/submissions/{tr_number}/status`. Responses are
  `TRSubmission.model_dump(mode="json")` — enums as ints. Customers only see their own customer's
  TRs (others → 404). Business-rule failures → 422 with `loc` pointing at the field; disallowed or
  concurrent status changes → 409.
- **Reference data:** `app.state.reference` is a `ReferenceCache` (TTL `REFERENCE_CACHE_TTL_SECONDS`,
  default 300 s; staff can force a reload on /admin). A failed refresh keeps the previous snapshot.
  SLIM analyses with no `analysis_catalog` row are never offered. `GET /api/reference` gives the
  form its choices (customers only for staff).
- **OSS only:** see the banner at the top. `PORTAL_ALLOWED_DB_HOSTS` is for other *demo* hosts.
- **Dates:** "today" means the lab's local date (`LAB_TIMEZONE`, default America/Chicago). Expected
  arrival (optional, customer) can't be in the past; `date_received` (staff) can't be in the future.
- **Demo data only:** dev, tests and the portfolio use the OSS repos' fictional data
  (`slim-report-engine-oss/demo/demo.py`). `scripts/seed_demo.py` never writes into SLIM tables
  that already hold data. Never point the portal at the lab's production database from here.
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

## Backlog

See "Parked ideas" in docs/SLIM_DOMAIN_V2.md §11.
