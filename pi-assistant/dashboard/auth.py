"""
dashboard/auth.py — Authentication for the Web Dashboard
==========================================================
Provides username/password login backed by bcrypt password hashes.
Session management is handled by Flask-Login.

Security decisions
------------------
- Passwords are NEVER stored in plain text.  Only bcrypt hashes are kept in
  config/env.  Generate a hash with:
      python -c "import bcrypt; print(bcrypt.hashpw(b'yourpass', bcrypt.gensalt()).decode())"
- The login form is protected by Flask-WTF CSRF tokens.
- Session cookies use HttpOnly + SameSite=Lax by default.
  Set ``session_cookie_secure: true`` in config.yaml if you add HTTPS.
- All login attempts (success and failure) are logged with the client IP.

Usage
-----
    from dashboard.auth import init_auth, login_required

    init_auth(app)   # call once in the app factory

    @app.route("/protected")
    @login_required
    def protected():
        return "secret"
"""

from __future__ import annotations

import bcrypt
from flask import Flask, current_app
from flask_login import LoginManager, UserMixin, login_required  # re-exported
from core.logger import get_logger

log = get_logger(__name__)

# Re-export login_required so callers can import it from here
__all__ = ["init_auth", "login_required", "User", "check_password"]


# ── User model (single-user system) ───────────────────────────────────────────

class User(UserMixin):
    """
    Flask-Login user model.

    Pi Assistant is a single-user system, so there is exactly one user
    whose credentials are defined in config / .env.
    The ``id`` is always "1" — Flask-Login requires it.
    """
    id = "1"

    def __init__(self, username: str) -> None:
        self.username = username

    def get_id(self) -> str:
        return self.id


# ── bcrypt helpers ─────────────────────────────────────────────────────────────

def check_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain-text password against a bcrypt hash.

    Parameters
    ----------
    plain  : The password the user typed.
    hashed : The bcrypt hash from config / .env.

    Returns
    -------
    True if the password matches, False otherwise.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as exc:
        log.warning(f"Password check error: {exc}")
        return False


def hash_password(plain: str) -> str:
    """
    Hash a plain-text password with bcrypt.

    Use this in a one-off script to generate your .env password hash:
        python -c "from dashboard.auth import hash_password; print(hash_password('yourpassword'))"
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ── Flask-Login initialisation ─────────────────────────────────────────────────

def init_auth(app: Flask) -> None:
    """
    Attach Flask-Login to the Flask app.

    Call this once inside the application factory (``dashboard/app.py``).
    """
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"          # type: ignore[assignment]
    login_manager.login_message = "Please log in to access the dashboard."
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        """
        Reload the user from the session.

        Flask-Login calls this on every request with the stored user_id.
        We only have one user, so if the id matches we return the singleton.
        """
        if user_id == User.id:
            username = current_app.config.get("AUTH_USERNAME", "admin")
            return User(username=username)
        return None
