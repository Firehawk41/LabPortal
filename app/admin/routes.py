from datetime import datetime

from flask import abort, jsonify, redirect, render_template, request, url_for

from app.admin import admin_bp
from app.auth.decorators import admin_required
from app.extensions import bcrypt, db
from app.models import VALID_ROLES, VALID_STATUSES, User
from app.repositories import SubmissionRepository

submission_repo = SubmissionRepository()

PER_PAGE = 20


def _parse_date(s):
    """Return a datetime.date from a YYYY-MM-DD string, or None on any error."""
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


@admin_bp.route("/")
@admin_required
def dashboard():
    return redirect(url_for("admin.submissions"))


@admin_bp.route("/submissions")
@admin_required
def submissions():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1

    status    = request.args.get("status", "").strip()
    customer  = request.args.get("customer", "").strip()
    date_from = _parse_date(request.args.get("from", ""))
    date_to   = _parse_date(request.args.get("to", ""))

    filters = {
        "status":   status,
        "customer": customer,
        "from":     request.args.get("from", ""),
        "to":       request.args.get("to", ""),
    }

    all_submissions = submission_repo.get_filtered(
        status=status or None,
        customer=customer or None,
        date_from=date_from,
        date_to=date_to,
    )
    total = len(all_submissions)
    start = (page - 1) * PER_PAGE
    page_items = all_submissions[start:start + PER_PAGE]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return render_template(
        "admin/submissions.html",
        submissions=page_items,
        page=page,
        total=total,
        total_pages=total_pages,
        filters=filters,
        valid_statuses=sorted(VALID_STATUSES),
    )


@admin_bp.route("/submissions/<submission_id>")
@admin_required
def submission_detail(submission_id):
    submission = submission_repo.get_by_id(submission_id)
    if submission is None:
        abort(404)

    return render_template(
        "admin/submission_detail.html",
        submission=submission,
        valid_statuses=sorted(VALID_STATUSES),
    )


@admin_bp.route("/submissions/<submission_id>/status", methods=["POST"])
@admin_required
def update_submission_status(submission_id):
    status = (request.form.get("status") or "").strip()

    if status not in VALID_STATUSES:
        return jsonify({"error": f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}."}), 400

    try:
        submission_repo.update_status(submission_id, status)
    except ValueError:
        abort(404)

    return redirect(url_for("admin.submission_detail", submission_id=submission_id))


@admin_bp.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users, valid_roles=sorted(VALID_ROLES))


@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    company_name = (request.form.get("company_name") or "").strip()
    role = (request.form.get("role") or "customer").strip()

    error = None
    if not email or not password:
        error = "Email and password are required."
    elif role not in VALID_ROLES:
        error = f"Role must be one of: {', '.join(sorted(VALID_ROLES))}."
    elif User.query.filter_by(email=email).first() is not None:
        error = f"A user with email {email} already exists."

    if error:
        all_users = User.query.order_by(User.created_at.desc()).all()
        return render_template(
            "admin/users.html", users=all_users, valid_roles=sorted(VALID_ROLES), error=error
        ), 400

    user = User(
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
        role=role,
        company_name=company_name,
    )
    db.session.add(user)
    db.session.commit()

    return redirect(url_for("admin.users"))
