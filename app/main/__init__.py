from flask import Blueprint

main_bp = Blueprint("main", __name__, url_prefix="")

from app.main import routes  # noqa: E402,F401
