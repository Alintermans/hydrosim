"""Auth helpers + response headers. Two doors, both deliberately simple:

  - Admin session: one shared ADMIN_PASSWORD (kiosk product, not a user system).
  - API bearer token: the collector and the sync relay. Compared with
    hmac.compare_digest; an instance with no API_TOKEN set refuses the API
    outright rather than accepting everything.
"""

import hmac
from functools import wraps

from flask import current_app, jsonify, redirect, request, session, url_for


def token_ok() -> bool:
    configured = current_app.config.get("API_TOKEN", "")
    if not configured:
        return False
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip(), configured)


def is_admin() -> bool:
    return bool(session.get("admin"))


def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not token_ok():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def operator_required(f):
    """Kiosk actions (assign names, set driver): admin session OR api token."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (is_admin() or token_ok()):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("timing.login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def kiosk_allowed() -> bool:
    """/kiosk renders for an admin, or for anyone when KIOSK_OPEN=1 (the sim PC
    binds 127.0.0.1, so 'anyone' is the machine driving the second screen)."""
    return is_admin() or current_app.config.get("KIOSK_OPEN", False)


def init_security(app) -> None:
    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'",
        )
        return resp

    def _guard():  # production safety, hydroapps-style: refuse to boot unsafe
        if app.config["DEBUG"] or app.config.get("TESTING"):
            return
        problems = []
        if app.config["SECRET_KEY"] == "dev-not-secret":
            problems.append("SECRET_KEY is still the default")
        if not app.config["ADMIN_PASSWORD"]:
            problems.append("ADMIN_PASSWORD must be set")
        if not app.config["API_TOKEN"]:
            problems.append("API_TOKEN must be set")
        if problems:
            raise RuntimeError("Refusing to start: " + "; ".join(problems))

    _guard()
