"""
dashboard/routes/auth_routes.py — Login / Logout Routes
========================================================
Handles the login form, session creation, and logout.

Routes
------
GET  /login  — Render the login form
POST /login  — Validate credentials and start a session
GET  /logout — Destroy the session and redirect to /login
"""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_user, logout_user, current_user
from core.logger import get_logger
from dashboard.auth import User, check_password

log = get_logger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    GET  — Render the login page.
    POST — Validate username + password; set session on success.
    """
    # Already logged in → redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        client_ip = request.remote_addr

        expected_username = current_app.config.get("AUTH_USERNAME", "admin")
        password_hash = current_app.config.get("AUTH_PASSWORD_HASH", "")

        if (
            username == expected_username
            and password_hash
            and check_password(password, password_hash)
        ):
            user = User(username=username)
            login_user(user, remember=False)
            log.info(f"Dashboard login success: {username!r} from {client_ip}")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.index"))
        else:
            log.warning(f"Dashboard login failed: {username!r} from {client_ip}")
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    """Destroy the current session and redirect to the login page."""
    username = getattr(current_user, "username", "unknown")
    logout_user()
    log.info(f"Dashboard logout: {username!r}")
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
