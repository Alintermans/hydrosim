import uuid

import pytest

from app import create_app
from config import Config
from models import Event, db

TOKEN = "test-token"
ADMIN_PW = "test-admin"


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SECRET_KEY = "test-secret"
    ADMIN_PASSWORD = ADMIN_PW
    API_TOKEN = TOKEN
    WTF_CSRF_ENABLED = False
    KIOSK_OPEN = False
    UPSTREAM_URL = ""
    UPSTREAM_TOKEN = ""


@pytest.fixture
def app(tmp_path):
    cfg = TestConfig()
    cfg.DATA_DIR = tmp_path
    cfg.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
    application = create_app(lambda: cfg)
    with application.app_context():
        db.create_all()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def event(app):
    with app.app_context():
        ev = Event(slug="spa-test", name="Spa Test", kind="event",
                   track_filter="spa", min_lap_s=60, max_cuts=0, active=True)
        db.session.add(ev)
        db.session.commit()
        return db.session.get(Event, ev.id)


def lap_payload(**overrides):
    payload = {
        "client_id": uuid.uuid4().hex,
        "lap_ms": 140_000,
        "cuts": 0,
        "car": "tatuus_fa01",
        "track": "spa",
        "track_config": "",
        "tyre_compound": "Slick (M)",
        "abs_used": False,
        "tc_used": True,
        "stability": 0.0,
        "auto_clutch": True,
        "auto_blip": True,
        "ideal_line": False,
        "fuel_rate": 1.0,
        "tyre_rate": 1.0,
        "damage_rate": 0.0,
        "air_temp": 20.5,
        "road_temp": 26.0,
        "grip": 0.98,
        "session_type": "practice",
        "recorded_at": "2026-08-29T14:00:00+00:00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def admin_client(client):
    client.post("/admin/login", data={"password": ADMIN_PW, "next": ""})
    return client
