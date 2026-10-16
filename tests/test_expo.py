import pytest

import expo
from models import Event, db
from tests.conftest import lap_payload


@pytest.fixture
def expo_event(app):
    expo.reset()
    with app.app_context():
        ev = Event(slug="fti", name="FTI", kind="expo", track_filter="spa",
                   min_lap_s=100, max_cuts=0, active=True)
        db.session.add(ev)
        db.session.commit()
    yield
    expo.reset()


def name_lap(client, auth, ms, name):
    payload = lap_payload(lap_ms=ms)
    client.post("/api/laps", json=payload, headers=auth)
    client.post(f"/api/laps/{payload['client_id']}/assign",
                json={"driver_name": name}, headers=auth)
    return payload["client_id"]


def test_expo_ignores_cuts_but_not_min_time(client, auth, expo_event):
    r = client.post("/api/laps", json=lap_payload(cuts=7), headers=auth).get_json()
    assert r["valid"] is True
    r = client.post("/api/laps", json=lap_payload(lap_ms=40_000), headers=auth).get_json()
    assert r["valid"] is False


def test_phase_requires_token_and_valid_phase(client, auth, expo_event):
    assert client.post("/api/expo/phase", json={"phase": "idle"}).status_code == 401
    assert client.post("/api/expo/phase", json={"phase": "nope"},
                       headers=auth).status_code == 400
    assert client.get("/api/expo/state").status_code == 401  # not loopback/kiosk


def test_state_reports_rank_of_unnamed_lap(client, auth, expo_event):
    name_lap(client, auth, 130_000, "Anna")
    name_lap(client, auth, 150_000, "Bert")
    mine = lap_payload(lap_ms=140_000)
    client.post("/api/laps", json=mine, headers=auth)
    client.post("/api/expo/phase", headers=auth,
                json={"phase": "naming", "lap": mine["client_id"], "name": "Ce",
                      "deadline_s": 60})
    st = client.get("/api/expo/state", headers=auth).get_json()
    assert st["phase"] == "naming" and st["name"] == "Ce"
    assert 0 < st["deadline_s"] <= 60 and st["age_s"] is not None
    res = st["result"]
    assert (res["rank"], res["total"]) == (2, 3)
    assert res["gap_ms"] == 10_000 and res["record"] is False
    assert res["beaten_pct"] == 50


def test_returning_driver_is_not_compared_with_themselves(client, auth, expo_event):
    name_lap(client, auth, 130_000, "Anna")
    second = name_lap(client, auth, 135_000, "anna")
    client.post("/api/expo/phase", headers=auth,
                json={"phase": "result", "lap": second})
    res = client.get("/api/expo/state", headers=auth).get_json()["result"]
    assert (res["rank"], res["total"], res["record"]) == (1, 1, True)
    assert res["own_best"]["lap_ms"] == 130_000


def test_expo_screen_and_kiosk_redirect(admin_client, expo_event):
    assert admin_client.get("/expo").status_code == 200
    resp = admin_client.get("/kiosk")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/expo")


def test_main_screen_renders(admin_client, expo_event):
    resp = admin_client.get("/expo/main")
    assert resp.status_code == 200 and b"Druk op" in resp.data
