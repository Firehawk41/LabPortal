from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.auth import auth_bp
from app.extensions import bcrypt
from app.models import User


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("main.index"))

        error = "Invalid email or password."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
