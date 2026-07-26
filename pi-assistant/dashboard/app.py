"""
dashboard/app.py — Flask Application Factory
=============================================
Creates and configures the Flask web application for the secure dashboard.

Pattern used: Application Factory
----------------------------------
``create_app()`` returns a fully configured Flask app without running it.
The assistant calls this from a background thread (core/assistant.py) and
passes the ``assistant`` instance so routes can access the running subsystems.

Blueprints registered
----------------------
- ``auth``   : /login, /logout
- ``main``   : / (dashboard UI pages)
- ``api_bp`` : /api/* (REST API for the Android client and plugins)

Security features
-----------------
- CSRF protection on all forms (Flask-WTF)
- Session secret key loaded from .env
- HttpOnly + SameSite=Lax cookies
- Login required on all non-auth routes
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from core.config import config
from core.logger import get_logger
from dashboard.auth import init_auth

if TYPE_CHECKING:
    from core.assistant import Assistant

log = get_logger(__name__)

# Flask-WTF CSRF protection (applied globally)
csrf = CSRFProtect()


def create_app(assistant: "Assistant | None" = None) -> Flask:
    """
    Flask application factory.

    Parameters
    ----------
    assistant : The running Assistant instance.  Stored on ``app.config``
                so blueprints/routes can access it via ``current_app.config``.

    Returns
    -------
    A fully configured Flask application ready to serve.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    # ── Core Flask configuration ───────────────────────────────────────────────
    secret_key = config.get("dashboard.secret_key", "change-me")
    if secret_key == "change-me" or secret_key == "change-me-in-env":
        log.warning(
            "SECURITY: Dashboard secret key is not set. "
            "Set DASHBOARD_SECRET_KEY in your .env file!"
        )

    app.config.update(
        SECRET_KEY=secret_key,
        WTF_CSRF_ENABLED=True,

        # Session settings
        PERMANENT_SESSION_LIFETIME=timedelta(
            minutes=config.get("dashboard.session_lifetime_minutes", 60)
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.get("dashboard.session_cookie_secure", False),

        # Auth credentials (used by the user_loader in auth.py)
        AUTH_USERNAME=config.get("auth.username", "admin"),
        AUTH_PASSWORD_HASH=config.get("auth.password_hash", ""),

        # Expose the assistant to all request contexts
        ASSISTANT=assistant,
    )

    # ── Extensions ────────────────────────────────────────────────────────────
    csrf.init_app(app)
    init_auth(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    _register_blueprints(app)

    log.debug("Flask app created and configured")
    return app


def _register_blueprints(app: Flask) -> None:
    """Import and register all route blueprints."""
    from dashboard.routes.auth_routes import auth_bp
    from dashboard.routes.main import main_bp
    from dashboard.routes.api import api_bp

    app.register_blueprint(auth_bp)          # /login, /logout
    app.register_blueprint(main_bp)          # /
    app.register_blueprint(api_bp, url_prefix="/api")  # /api/*

    log.debug("Blueprints registered: auth, main, api")
