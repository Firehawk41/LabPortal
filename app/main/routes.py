from flask import jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from marshmallow import ValidationError

from app.main import main_bp
from app.repositories import SubmissionRepository
from app.schemas import SubmissionSchema

submission_repo = SubmissionRepository()


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return render_template("form.html")


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
