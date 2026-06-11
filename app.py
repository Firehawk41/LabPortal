import json
import os
import re
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # auto-413 on oversized bodies

SUBMISSIONS_FILE = "submissions.jsonl"
LATEST_FILE = "submitted_request.json"


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://code.jquery.com https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self'; "
        "img-src 'self' data:;"
    )
    return response


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

VALID_SAMPLE_TYPES = {"chemical", "water", "wafer"}
VALID_PROCESSING_TIMES = {"Standard", "Next Day", "Rush"}


def parse_tagify(raw):
    """
    Tagify serializes tags as '[{"value":"a@b.com"},...]'.
    An empty input arrives as empty string "". Returns a list of email strings.
    """
    if not raw:
        return []
    try:
        tags = json.loads(raw)
        if isinstance(tags, list):
            return [t["value"] for t in tags if isinstance(t, dict) and "value" in t]
    except (json.JSONDecodeError, KeyError):
        pass
    return []


def validate_email(addr):
    return bool(EMAIL_RE.match(addr))


def validate_submission(data):
    """
    Returns (normalized_data, list_of_error_strings).
    Never mutates the input dict.
    """
    errors = []

    def require_str(key, label, max_len=200):
        val = data.get(key, "")
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{label} is required.")
            return ""
        if len(val) > max_len:
            errors.append(f"{label} must be {max_len} characters or fewer.")
            return val.strip()[:max_len]
        return val.strip()

    customer_name    = require_str("customer_name",    "Company name")
    street_address   = require_str("street_address",   "Street address")
    city             = require_str("city",             "City")
    state            = require_str("state",            "State")
    country          = require_str("country",          "Country")
    customer_contact = require_str("customer_contact", "Contact name")
    customer_phone   = require_str("customer_phone",   "Phone number")

    results_list    = parse_tagify(data.get("results_list", ""))
    results_cc_list = parse_tagify(data.get("results_cc_list", ""))
    invoice_list    = parse_tagify(data.get("invoice_list", ""))
    invoice_cc_list = parse_tagify(data.get("invoice_cc_list", ""))

    if not results_list:
        errors.append("At least one results distribution email is required.")
    else:
        bad = [e for e in results_list if not validate_email(e)]
        if bad:
            errors.append(f"Invalid results email(s): {', '.join(bad)}")

    for addr in results_cc_list:
        if not validate_email(addr):
            errors.append(f"Invalid results CC email: {addr}")

    if not invoice_list:
        errors.append("At least one invoice distribution email is required.")
    else:
        bad = [e for e in invoice_list if not validate_email(e)]
        if bad:
            errors.append(f"Invalid invoice email(s): {', '.join(bad)}")

    for addr in invoice_cc_list:
        if not validate_email(addr):
            errors.append(f"Invalid invoice CC email: {addr}")

    payment_method = data.get("payment_method", "")
    if payment_method not in ("po", "cc"):
        errors.append("Payment method must be 'po' or 'cc'.")

    po_number = ""
    cc_number = ""
    if payment_method == "po":
        po_number = require_str("po_number", "PO number", max_len=100)
    elif payment_method == "cc":
        cc_number = require_str("cc_number", "Credit card info", max_len=100)

    raw_samples = data.get("samples", [])
    if not isinstance(raw_samples, list) or len(raw_samples) == 0:
        errors.append("At least one sample is required.")
        raw_samples = []

    samples = []
    for i, s in enumerate(raw_samples):
        if not isinstance(s, dict):
            errors.append(f"Sample {i + 1}: invalid format.")
            continue
        s_errors = []

        sample_id = s.get("sample_id", "").strip()
        if not sample_id:
            s_errors.append("Sample ID is required.")
        elif len(sample_id) > 100:
            s_errors.append("Sample ID must be 100 characters or fewer.")

        matrix = s.get("chemical_matrix", "").strip()
        if not matrix:
            s_errors.append("Chemical matrix is required.")
        elif len(matrix) > 200:
            s_errors.append("Chemical matrix must be 200 characters or fewer.")

        sample_type = s.get("sample_type", "")
        if sample_type not in VALID_SAMPLE_TYPES:
            s_errors.append(
                f"Sample type must be one of: {', '.join(sorted(VALID_SAMPLE_TYPES))}."
            )

        processing_time = s.get("processing_time", "").strip()
        if processing_time not in VALID_PROCESSING_TIMES:
            s_errors.append(
                f"Processing time must be one of: {', '.join(sorted(VALID_PROCESSING_TIMES))}."
            )

        analyses = s.get("analyses", [])
        if not isinstance(analyses, list):
            s_errors.append("Analyses must be a list.")
            analyses = []
        if len(analyses) == 0:
            s_errors.append("At least one analysis must be selected.")

        for e in s_errors:
            errors.append(f"Sample {i + 1}: {e}")

        samples.append({
            "sample_id": sample_id,
            "chemical_matrix": matrix,
            "sample_type": sample_type,
            "processing_time": processing_time,
            "analyses": analyses,
        })

    normalized = {
        "submission_id": str(uuid.uuid4()),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "customer_name": customer_name,
        "street_address": street_address,
        "city": city,
        "state": state,
        "country": country,
        "customer_contact": customer_contact,
        "customer_phone": customer_phone,
        "results_list": results_list,
        "results_cc_list": results_cc_list,
        "invoice_list": invoice_list,
        "invoice_cc_list": invoice_cc_list,
        "payment_method": payment_method,
        "po_number": po_number,
        "cc_number": cc_number,
        "samples": samples,
    }

    return normalized, errors


@app.route("/")
def index():
    return render_template("form.html")


@app.route("/submit", methods=["POST"])
def submit():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body is not valid JSON."}), 400

    normalized, errors = validate_submission(data)

    if errors:
        return jsonify({"errors": errors}), 422

    try:
        # O_APPEND writes are atomic on Linux for lines well under PIPE_BUF (~4 KB).
        with open(SUBMISSIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(normalized) + "\n")

        with open(LATEST_FILE, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

    except OSError as e:
        app.logger.error("Failed to write submission: %s", e)
        return jsonify({"error": "Server storage error. Please try again."}), 500

    return jsonify({
        "message": "Submission received and saved.",
        "submission_id": normalized["submission_id"],
        "submitted_at": normalized["submitted_at"],
    }), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
