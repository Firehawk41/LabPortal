# YourLab Testing Request Portal — Claude Context

## What This Is

A Flask web app for an ISO 17025 accredited analytical chemistry lab. Authenticated customers fill out a multi-section testing request form (company info, payment, email distribution lists, sample details); lab staff (admins) review submissions and update their status from a dashboard.

## How to Run

```bash
cp .env.example .env   # set FLASK_SECRET_KEY, DATABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD
pip install -r requirements.txt
python seed.py          # creates tables + demo admin/customer/submission data
python wsgi.py          # http://127.0.0.1:5000
```

Or via Docker Compose: `docker compose up --build`.

## File Map

```
wsgi.py                       # WSGI entry point — `app = create_app()`
seed.py                        # Creates tables + demo data (admin, 3 customers, 5 submissions)
app/
├── __init__.py                # create_app() application factory, blueprint registration, security headers
├── extensions.py              # db (SQLAlchemy), bcrypt, login_manager — shared singletons
├── domain.py                  # Pure dataclasses: Sample, TestingRequest (no Flask/SQLAlchemy imports)
├── models.py                  # SQLAlchemy models: User, Submission, Sample, AuditLog
├── schemas.py                 # marshmallow schemas: SampleSchema, SubmissionSchema; parse_tagify()
├── repositories.py            # SubmissionRepository — translates domain objects <-> ORM models
├── auth/                       # Blueprint: /login, /logout
│   ├── decorators.py           # login_required (re-export), admin_required
│   └── routes.py
├── main/                        # Blueprint: / (customer form), /new-submission (admin form), /submit
│   └── routes.py
├── admin/                        # Blueprint: /admin/* (dashboard, submissions, users)
│   └── routes.py
└── templates/
    ├── base.html                  # Shared layout (header/nav/footer blocks)
    ├── login.html
    ├── form.html                   # Full multi-section form UI (moved here, minimal nav changes)
    └── admin/
        ├── submissions.html        # Paginated submission list + inline status update
        ├── submission_detail.html  # Full submission detail incl. samples/analyses
        └── users.html               # User list + create-customer form
static/
├── css/style.css               # Corporate light theme (unchanged)
├── css/admin.css                # Dark theme overrides for admin pages (.admin-theme)
├── js/script.js                # Client-side form logic — tagifyMap, populateFromProfile(), Select2, Tagify, modal
└── data/analyses.json          # Catalog of ~43 analyses in 7 groups — unchanged
```

## Current Architecture

- **Backend:** Flask application factory + Blueprints (`auth`, `main`, `admin`)
- **Database:** PostgreSQL via Flask-SQLAlchemy. Tables: `users`, `submissions`, `samples`, `audit_log` (audit_log table now written on admin submissions; no UI yet)
- **Three-layer separation, strictly enforced:**
  - `domain.py` — pure dataclasses (`Sample`, `TestingRequest`), zero framework imports
  - `schemas.py` — marshmallow boundary: validates/deserializes incoming JSON into domain objects, rejects bad input with 400 + descriptive JSON errors (never 500)
  - `repositories.py` — `SubmissionRepository` is the only place that converts domain objects <-> ORM models; route handlers never touch `db.session` for submissions/samples directly
- **Auth:** Flask-Login + Flask-Bcrypt. Single `users` table with `role` column (`customer` | `admin`). No self-registration — admins create customer accounts via `/admin/users/create`
- **Frontend:** Vanilla JS + jQuery 3.7.1 + Select2 4.0.13 + Tagify 4.31.3 (all CDN, pinned) — unchanged from prior phase
- **Security headers** set via `@app.after_request` in `app/__init__.py`: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- **1 MB request cap** via `MAX_CONTENT_LENGTH`

## Key Backend Facts

- `parse_tagify()` and `EMAIL_RE` live in `app/schemas.py`; Tagify email fields arrive as raw JSON strings (`'[{"value":"a@b.com"}]'`) and are parsed/validated by the custom `TagifyEmailList` marshmallow field
- `SubmissionSchema.load()` returns a `TestingRequest` domain object (via `@post_load`), not a dict; `SampleSchema` likewise returns `Sample`
- `SubmissionSchema` has `class Meta: unknown = EXCLUDE` — extra keys in the POST body (e.g. `behalf_customer_id`) are silently dropped by the schema so the route can read them from the raw `data` dict after validation without triggering a 400
- `GET /` redirects unauthenticated users to login; redirects admins to `/admin/submissions`; renders the form for customers
- `GET /new-submission` (`@admin_required`) renders `form.html` with the full `customers` list (all `role="customer"` users ordered by `company_name`); form fields start blank
- `GET /admin/api/customer/<id>/profile` (`@admin_required`) returns a customer's saved profile fields as JSON for JS pre-fill
- `POST /submit` is `@login_required`; for customers, stamps `current_user.id` as `user_id`; for admins, reads `behalf_customer_id` from JSON body, validates it is a real customer UUID, attributes the submission to that customer, and writes an `AuditLog` entry (`field_name="submitted_by_admin"`, `changed_by=<admin_id>`, `new_value=<customer_id>`). Returns 201 `{"message": "Submission received", "submission_id": "<uuid>"}` on success; 400 on validation error.
- `VALID_SAMPLE_TYPES` (schemas.py): `chemical`, `water`, `wafer`
- `VALID_PROCESSING_TIMES` (schemas.py): `Standard`, `Next Day`, `Rush`
- `VALID_ROLES` (models.py): `customer`, `admin`
- `VALID_STATUSES` (models.py): `received`, `in_progress`, `complete`
- All primary keys are UUIDs (`UUID(as_uuid=True), default=uuid.uuid4`)
- `@admin_required` (app/auth/decorators.py) wraps `@login_required` and aborts 403 for non-admins

## Key Frontend Facts

- `sampleCounter` is a module-level monotonic int used to namespace `analysis[N][]` select names — never reset, never based on DOM children count
- `showFormError(message)` writes to `#form-error` (role="alert") instead of alert()
- Confirmation modal has `role="dialog"`, `aria-modal`, `aria-labelledby`; ESC key and backdrop click close it
- `createAnalysisDropdown()` returns a disabled placeholder `<select>` on fetch failure (never returns undefined)
- Processing time is a `<select>` restricted to Standard / Next Day / Rush
- All 11 customer-info inputs have matching `id` and `for` attributes for label linkage
- `form.html` conditionally loads `admin.css` and applies `class="admin-theme"` to `<body>` when the viewer is an admin, giving the form the same dark theme as the rest of the admin UI
- `tagifyMap` (module-level object in `script.js`) stores Tagify instances keyed by input element ID so they can be reset programmatically
- `populateFromProfile(profile)` fills all plain inputs, Tagify email fields, payment-method radio, and PO number from a profile object — used both for saved-profile pre-fill on page load and for admin customer-select pre-fill via fetch
- Customer profile data is injected server-side as a `data-profile='...'` attribute on `#sampleForm` (JSON-encoded); `script.js` reads it via `document.getElementById("sampleForm").dataset.profile` and parses with `JSON.parse()`. **Do not use an inline `<script>` tag for this** — the CSP `script-src` does not include `'unsafe-inline'`, so inline scripts are blocked by every browser and the profile would never load
- Admin form shows a "Submit on Behalf Of" `<select>` (populated server-side) and a hidden `#behalf-customer-id` input; selecting a customer fetches `/admin/api/customer/<id>/profile` and calls `populateFromProfile()`

## Submitted JSON Shape (POST /submit)

```json
{
  "customer_name": "Acme Corp",
  "street_address": "123 Main St",
  "city": "Springfield",
  "state": "IL",
  "country": "USA",
  "customer_contact": "Jane Doe",
  "customer_phone": "555-1234",
  "results_list": "[{\"value\":\"jane@acme.com\"}]",
  "results_cc_list": "[]",
  "invoice_list": "[{\"value\":\"ap@acme.com\"}]",
  "invoice_cc_list": "[]",
  "payment_method": "po",
  "po_number": "PO-9876",
  "cc_number": "",
  "behalf_customer_id": "",
  "samples": [
    {
      "sample_id": "S-001",
      "chemical_matrix": "IPA",
      "sample_type": "chemical",
      "processing_time": "Next Day",
      "analyses": ["36_elements_icpms", "toc"]
    }
  ]
}
```

`results_list`/`results_cc_list`/`invoice_list`/`invoice_cc_list` arrive as raw Tagify JSON strings and are parsed server-side into plain email lists by `TagifyEmailList`.

`behalf_customer_id`: UUID string of the selected customer when submitted by an admin; empty string for customer self-submissions (field is ignored server-side for non-admins).

---

## Suggested Improvements

### Already Done (do not re-suggest)

- SQLite/PostgreSQL database via SQLAlchemy (replaced flat-file JSONL storage)
- Admin dashboard (`/admin/submissions`, `/admin/submissions/<id>`, `/admin/users`)
- Customer accounts with login (Flask-Login + bcrypt); admin-created, no self-registration
- Submission status tracking (`received` / `in_progress` / `complete`), updatable from admin view
- Flask Blueprints (`auth`, `main`, `admin`)
- Dark admin theme (`admin.css`, `.admin-theme`) consistent with corporate palette
- Server-side validation with descriptive error messages (marshmallow)
- Tagify email field parsing on the backend
- UUID primary keys throughout
- Security headers (CSP, X-Frame-Options, nosniff, Referrer-Policy)
- 1 MB request size cap
- All input `id` / `for` label linkage
- Pinned CDN versions
- Accessible modal (role, aria-modal, ESC, backdrop click)
- Processing time restricted to valid enum values
- Inline error display via `#form-error`
- Docker Compose, Dockerfile, render.yaml, seed.py for deployment/demo data
- Admin submit on behalf of customer — `/new-submission` route, customer selector with JS pre-fill, server-side attribution, audit log entry
- Dark admin theme applied to `form.html` when viewed by an admin
- `SubmissionSchema` ignores unknown fields (`Meta.unknown = EXCLUDE`) so `behalf_customer_id` in the POST body doesn't cause a 400
- Customer profile pre-fill via `data-profile` attribute (not inline script) to comply with CSP

### Explicitly Out of Scope (do not build without a new spec)

- Copy sample / copy submission / edit submission UI
- Email notifications (confirmation to customer, alert to lab staff) — `# TODO` markers exist in `app/main/routes.py`
- Audit log UI — table exists, repository has `# TODO` markers for writes, but no routes/templates
- "Reported" status (only `received` / `in_progress` / `complete` exist)

### Lower Priority (still open)

- **Delete sample button** — users currently cannot remove a sample row without refreshing the page
- **Notes / special instructions** — free-text textarea per submission
- **SRI hashes on CDN links** — compute at srihash.org
- **"Copy last sample" button** — duplicate a row for high-throughput submissions
- **Billing code / cost center field**
- **File attachments** — COAs, SDSs, protocols
- **Analysis descriptions in UI** — `long_description`/`short_description` exist but only as tooltips
- **Self-host CDN dependencies**
