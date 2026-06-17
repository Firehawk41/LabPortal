import re

from flask import jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from marshmallow import ValidationError

from app.extensions import db
from app.main import main_bp
from app.repositories import SubmissionRepository
from app.schemas import EMAIL_RE, SubmissionSchema

submission_repo = SubmissionRepository()


def _build_profile():
    return {
        "customer_name":    current_user.company_name or "",
        "street_address":   current_user.street_address or "",
        "city":             current_user.city or "",
        "state":            current_user.state or "",
        "country":          current_user.country or "",
        "customer_contact": current_user.customer_contact or "",
        "customer_phone":   current_user.customer_phone or "",
        "results_list":     list(current_user.results_list or []),
        "results_cc_list":  list(current_user.results_cc_list or []),
        "invoice_list":     list(current_user.invoice_list or []),
        "invoice_cc_list":  list(current_user.invoice_cc_list or []),
        "payment_method":   current_user.payment_method or "po",
        "po_number":        current_user.po_number or "",
    }


def _parse_email_list(raw):
    """Split a comma/newline/space-separated string into clean email strings."""
    if not raw:
        return []
    return [e for e in re.split(r"[\s,]+", raw.strip()) if e]


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return render_template("form.html", profile=_build_profile())


@main_bp.route("/submit", methods=["POST"])
@login_required
def submit():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body is not valid JSON."}), 400

    schema = SubmissionSchema()
    try:
        testing_request = schema.load(data)
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

    testing_request.user_id = current_user.id

    submission_id = submission_repo.save(testing_request)

    # TODO: send confirmation email to customer and notification to lab staff

    return jsonify({
        "message": "Submission received",
        "submission_id": submission_id,
    }), 201


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    errors = {}

    if request.method == "POST":
        company_name     = request.form.get("company_name", "").strip()
        street_address   = request.form.get("street_address", "").strip()
        city             = request.form.get("city", "").strip()
        state            = request.form.get("state", "").strip()
        country          = request.form.get("country", "").strip()
        customer_contact = request.form.get("customer_contact", "").strip()
        customer_phone   = request.form.get("customer_phone", "").strip()
        payment_method   = request.form.get("payment_method", "po")
        po_number        = request.form.get("po_number", "").strip()

        results_list    = _parse_email_list(request.form.get("results_list", ""))
        results_cc_list = _parse_email_list(request.form.get("results_cc_list", ""))
        invoice_list    = _parse_email_list(request.form.get("invoice_list", ""))
        invoice_cc_list = _parse_email_list(request.form.get("invoice_cc_list", ""))

        if not company_name:
            errors["company_name"] = "Company name is required."
        if payment_method not in ("po", "cc"):
            errors["payment_method"] = "Invalid payment method."
        if payment_method == "po" and not po_number:
            errors["po_number"] = "PO number is required for Purchase Order."
        if not results_list:
            errors["results_list"] = "At least one results email is required."
        else:
            bad = [e for e in results_list if not EMAIL_RE.match(e)]
            if bad:
                errors["results_list"] = f"Invalid email(s): {', '.join(bad)}"
        if not invoice_list:
            errors["invoice_list"] = "At least one invoice email is required."
        else:
            bad = [e for e in invoice_list if not EMAIL_RE.match(e)]
            if bad:
                errors["invoice_list"] = f"Invalid email(s): {', '.join(bad)}"
        for field, emails in [("results_cc_list", results_cc_list), ("invoice_cc_list", invoice_cc_list)]:
            bad = [e for e in emails if not EMAIL_RE.match(e)]
            if bad:
                errors[field] = f"Invalid email(s): {', '.join(bad)}"

        if not errors:
            current_user.company_name     = company_name
            current_user.street_address   = street_address
            current_user.city             = city
            current_user.state            = state
            current_user.country          = country
            current_user.customer_contact = customer_contact
            current_user.customer_phone   = customer_phone
            current_user.payment_method   = payment_method
            current_user.po_number        = po_number
            current_user.results_list     = results_list
            current_user.results_cc_list  = results_cc_list
            current_user.invoice_list     = invoice_list
            current_user.invoice_cc_list  = invoice_cc_list
            db.session.commit()
            return redirect(url_for("main.profile", saved=1))

        data = {
            "company_name":       company_name,
            "street_address":     street_address,
            "city":               city,
            "state":              state,
            "country":            country,
            "customer_contact":   customer_contact,
            "customer_phone":     customer_phone,
            "payment_method":     payment_method,
            "po_number":          po_number,
            "results_list_text":  request.form.get("results_list", ""),
            "results_cc_text":    request.form.get("results_cc_list", ""),
            "invoice_list_text":  request.form.get("invoice_list", ""),
            "invoice_cc_text":    request.form.get("invoice_cc_list", ""),
        }
        return render_template("profile.html", data=data, errors=errors, saved=False), 400

    # GET
    u = current_user
    data = {
        "company_name":       u.company_name or "",
        "street_address":     u.street_address or "",
        "city":               u.city or "",
        "state":              u.state or "",
        "country":            u.country or "",
        "customer_contact":   u.customer_contact or "",
        "customer_phone":     u.customer_phone or "",
        "payment_method":     u.payment_method or "po",
        "po_number":          u.po_number or "",
        "results_list_text":  "\n".join(u.results_list or []),
        "results_cc_text":    "\n".join(u.results_cc_list or []),
        "invoice_list_text":  "\n".join(u.invoice_list or []),
        "invoice_cc_text":    "\n".join(u.invoice_cc_list or []),
    }
    return render_template("profile.html", data=data, errors={}, saved=request.args.get("saved") == "1")
