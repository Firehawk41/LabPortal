# PRECILAB Testing Request Form — Claude Context

## What This Is

A Flask web app for submitting laboratory testing requests. Customers fill out a multi-section form (company info, payment, email distribution lists, sample details) and the submission is saved server-side. Internal project name: PRECILAB.

## How to Run

```bash
pip install flask
python app.py
# http://127.0.0.1:5000
```

## File Map

```
app.py                        # Flask server — validation, storage, security headers
templates/form.html           # Full multi-section form UI
static/js/script.js           # Client-side form logic (Select2, Tagify, modal)
static/data/analyses.json     # Catalog of ~43 analyses in 7 groups
requirements.txt              # Flask>=3.0,<4.0
submissions.jsonl             # Append-only submission log (gitignored)
submitted_request.json        # Latest submission snapshot (gitignored)
```

## Current Architecture

- **Backend:** Flask only — no database, flat-file storage
- **Storage:** `submissions.jsonl` (one JSON object per line, append-only); `submitted_request.json` is a latest-submission snapshot kept for backwards compatibility
- **Frontend:** Vanilla JS + jQuery 3.7.1 + Select2 4.0.13 + Tagify 4.31.3 (all CDN, pinned)
- **Auth:** None — form is fully public
- **No email sending, no admin view, no user accounts**

## Key Backend Facts

- `validate_submission()` in `app.py` validates every field server-side and returns a `(normalized_dict, errors_list)` tuple
- Tagify email fields arrive as raw JSON strings (`'[{"value":"a@b.com"}]'`) and are parsed by `parse_tagify()`
- Every submission gets a UUID `submission_id` and UTC ISO `submitted_at` timestamp injected by the server
- Security headers set via `@app.after_request`: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- 1 MB request cap via `MAX_CONTENT_LENGTH`
- Returns 201 on success, 422 with `{"errors": [...]}` on validation failure, 415/400/500 for other cases
- `VALID_SAMPLE_TYPES = {"chemical", "water", "wafer"}`
- `VALID_PROCESSING_TIMES = {"Standard", "Next Day", "Rush"}`

## Key Frontend Facts

- `sampleCounter` is a module-level monotonic int used to namespace `analysis[N][]` select names — never reset, never based on DOM children count
- `showFormError(message)` writes to `#form-error` (role="alert") instead of alert()
- Confirmation modal has `role="dialog"`, `aria-modal`, `aria-labelledby`; ESC key and backdrop click close it
- `createAnalysisDropdown()` returns a disabled placeholder `<select>` on fetch failure (never returns undefined)
- Processing time is a `<select>` restricted to Standard / Next Day / Rush
- All 11 customer-info inputs have matching `id` and `for` attributes for label linkage

## Submitted JSON Shape

```json
{
  "submission_id": "uuid",
  "submitted_at": "2025-01-01T00:00:00+00:00",
  "customer_name": "Acme Corp",
  "street_address": "123 Main St",
  "city": "Springfield",
  "state": "IL",
  "country": "USA",
  "customer_contact": "Jane Doe",
  "customer_phone": "555-1234",
  "results_list": ["jane@acme.com"],
  "results_cc_list": [],
  "invoice_list": ["ap@acme.com"],
  "invoice_cc_list": [],
  "payment_method": "po",
  "po_number": "PO-9876",
  "cc_number": "",
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

---

## Suggested Improvements

### High Priority

- **SQLite database** (Flask-SQLAlchemy) — replace JSONL flat-file storage; enables searching, filtering, pagination, status updates, and linking submissions to customers
- **Admin dashboard** (`/admin`) — password-protected view for lab staff to see all submissions, filter by date/status/customer, view full detail per submission
- **Customer accounts** — registration/login so customers can see their own submission history; requires user table, Flask-Login, session management
- **Submission status tracking** — `Received → In Progress → Complete → Reported`; lab staff update it from the admin view; customer can see their submission's status
- **Email confirmation** — auto-send confirmation to customer and notification to lab staff on each new submission (Flask-Mail + SMTP or SendGrid)

### Medium Priority

- **Delete sample button** — users currently cannot remove a sample row without refreshing the page; add an ✕ button per row that removes it from the DOM and destroys its Select2 instance
- **Notes / special instructions** — free-text textarea per submission for special handling; very common on lab request forms
- **Flask Blueprints** — split into `main` (customer form) and `admin` (staff dashboard) blueprints once admin routes are added
- **CSS / visual design** — no stylesheet currently; bare HTML; needs styling before any external demo
- **SRI hashes on CDN links** — all five CDN tags need `integrity="sha384-..."` `crossorigin="anonymous"` attributes; compute at srihash.org

### Lower Priority

- **"Copy last sample" button** — duplicate a row for high-throughput submissions
- **Billing code / cost center field** — common in enterprise lab requests
- **File attachments** — let customers upload COAs, SDSs, or protocols
- **Analysis descriptions shown in UI** — `long_description` and `short_description` exist in analyses.json but only appear as hover tooltips; a side panel or expandable detail would be more discoverable
- **Self-host CDN dependencies** — bundle jQuery/Select2/Tagify locally so the app works offline and CDN outages don't break it
- **gunicorn / WSGI deploy instructions** — `python app.py` is not production-safe; add a `Procfile` or deployment note

### Already Done (do not re-suggest)

- Server-side validation with descriptive error messages
- Tagify email field parsing on the backend
- UUID submission IDs and UTC timestamps
- Security headers (CSP, X-Frame-Options, nosniff, Referrer-Policy)
- 1 MB request size cap
- Append-only JSONL storage
- All input `id` / `for` label linkage
- Pinned CDN versions (Select2 RC → stable)
- Accessible modal (role, aria-modal, ESC, backdrop click)
- Debug defaults and console logs removed
- Processing time restricted to valid enum values
- Loading/disabled state during submission fetch
- Inline error display via `#form-error`
- Clear hidden payment field on toggle
