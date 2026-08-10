"""Configuration — everything comes from the environment (12-factor, like hydroapps).

Two deployment shapes share this file:
  - Coolify (sim.hydroteam.be): Dockerfile sets DATA_DIR=/data, gunicorn binds :8000.
  - The sim PC (Windows): windows/install.ps1 writes a .env next to this file,
    waitress binds 127.0.0.1:8088 and UPSTREAM_URL points at the Coolify app.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-not-secret")
    DEBUG = _bool("FLASK_DEBUG")

    DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")  # filled in create_app
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Admin UI (event management) — one shared password, kiosk-style product.
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # Bearer token the collector and the sync relay authenticate with.
    API_TOKEN = os.environ.get("API_TOKEN", "")

    # Local install: 1 exposes /kiosk without an admin login (the server binds
    # 127.0.0.1 there, so "open" means "open to the sim PC itself").
    KIOSK_OPEN = _bool("KIOSK_OPEN")

    # When set, a background thread relays every lap to this base URL
    # (the Coolify instance). Empty on the cloud instance itself.
    UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "").rstrip("/")
    UPSTREAM_TOKEN = os.environ.get("UPSTREAM_TOKEN", "")

    # Honour X-Forwarded-* from exactly one proxy hop (Coolify's Traefik).
    TRUST_PROXY = _bool("TRUST_PROXY")
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")

    TIMEZONE = os.environ.get("TIMEZONE", "Europe/Brussels")

    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True

    @property
    def SESSION_COOKIE_SECURE(self):  # pragma: no cover - trivial
        return self.PREFERRED_URL_SCHEME == "https"
