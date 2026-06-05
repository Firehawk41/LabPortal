# FlaskTestingRequest — Lab Testing Request Form

A web application for submitting laboratory testing requests. Customers fill out a multi-section form to specify their company info, payment method, email distribution lists, and one or more sample analysis requests. On submission the data is saved server-side as JSON.

---

## Current State

### Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3 / Flask |
| Frontend | HTML5, vanilla JS |
| UI helpers | jQuery 3.6.0, Select2 4.1.0, Tagify (CDN) |
| Data storage | Flat JSON files (`submitted_request.json`) |

No database, no authentication, no requirements file. Dependencies are Flask (backend) and three CDN-loaded JS libraries.

### File Structure

```
FlaskTestingRequest/
├── app.py                      # Flask server — two routes
├── templates/
│   └── form.html               # Full multi-section form UI
├── static/
│   ├── js/
│   │   └── script.js           # Client-side form logic
│   └── data/
│       └── analyses.json       # Catalog of available analyses
├── submitted_request.json      # Latest submission (overwritten each time)
└── submissions.txt             # Manual log of past raw submissions
```

### Routes

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves `form.html` |
| POST | `/submit` | Accepts JSON body, writes to `submitted_request.json`, returns `{"message": "..."}` |

### Form Sections

1. **Customer Info** — company name, full address, contact name, phone
2. **Email Distribution** — Results (main + CC) and Invoice (main + CC) lists, validated via Tagify with regex `^[^\s@]+@[^\s@]+\.[^\s@]+$`
3. **Payment** — radio toggle between Purchase Order (PO number field) and Credit Card (card number field)
4. **Samples** — dynamic rows, each containing:
   - Sample ID
   - Chemical Matrix (free text, e.g. "IPA")
   - Sample Type (`chemical` | `water` | `wafer`)
   - Analyses (multi-select via Select2, filtered from `analyses.json` by sample type)
   - Processing Time (`Standard` | `Next Day` | `Rush`)

A modal shows a JSON preview before final submission.

### Analysis Catalog (`analyses.json`)

Seven groups with a total of ~43 options:

| Group | # Options | Notable sample-type restrictions |
|---|---|---|
| Metals | 12 | all types |
| Anions | 10 | all types |
| Cations | 3 | all types |
| Organics | 4 | all types |
| Physical Properties | 11 | all types |
| Microbiology | 1 | water only |
| Assay | 2 | all types |

Each entry has `id`, `label`, `short_description`, `long_description`, and `sample_types`.

### Submitted JSON Shape

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
  "results_cc_list": "",
  "payment_method": "po",
  "po_number": "PO-9876",
  "cc_number": "",
  "invoice_list": "[{\"value\":\"ap@acme.com\"}]",
  "invoice_cc_list": "",
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

Note: `results_list` and `invoice_list` are stored as raw Tagify JSON strings, not parsed arrays.

---

## How to Run

```bash
pip install flask
python app.py
# Visit http://localhost:5000
```

Runs in Flask debug mode on `0.0.0.0:5000`.

---

## Known Gaps / Planning Notes

These are areas that are incomplete or missing — useful context for planning the next phase:

- **No `requirements.txt`** — dependencies are undocumented.
- **No database** — every submission overwrites `submitted_request.json`; `submissions.txt` is a manual scratch file.
- **No authentication** — the form and submit endpoint are fully public.
- **No server-side validation** — `/submit` writes whatever JSON it receives with no schema check.
- **Tagify email lists stored as raw strings** — the backend receives them as unparsed Tagify JSON; they need to be decoded before use.
- **No email/notification sending** — submission is saved to disk only; no confirmation email to customer or lab staff.
- **No admin/review UI** — no way to view, search, or manage past submissions from the browser.
- **No unique submission IDs** — requests cannot be referenced or tracked.
- **No file/attachment support** — customers cannot attach COAs, SDSs, or other documents.
- **CDN dependencies** — jQuery, Select2, Tagify are loaded from external CDNs; offline use fails.
- **`processing_time` not in `analyses.json`** — it is a free-form field per sample, not validated against a fixed set of options (though the UI restricts it to Standard/Next Day/Rush).

---

## Potential Next Steps (for planning discussion)

- Add `requirements.txt` (Flask, and optionally SQLAlchemy, Flask-WTF, etc.)
- Replace flat-file storage with a proper database (SQLite for simple, PostgreSQL for production)
- Add server-side validation / schema enforcement on `/submit`
- Parse Tagify email strings server-side into proper lists
- Generate a unique submission ID (UUID) per request and return it to the client
- Add a confirmation email to the customer and a notification to lab staff
- Build a read-only admin page to list and view past submissions
- Add authentication (at minimum HTTP Basic Auth or a simple login for the admin view)
- Bundle JS dependencies locally instead of relying on CDNs
- Add a `requirements.txt` and a `Makefile` or `run.sh` for easier local setup
