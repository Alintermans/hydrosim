from models import Event, db
from tests.conftest import ADMIN_PW, lap_payload


def test_admin_requires_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]


def test_admin_login_wrong_password(client):
    client.post("/admin/login", data={"password": "nope", "next": ""})
    assert client.get("/admin").status_code == 302


def test_admin_create_edit_activate_event(admin_client, app):
    resp = admin_client.post("/admin/events/new", data={
        "name": "Spa Challenge", "slug": "spa-2026", "kind": "event",
        "track_filter": "spa", "car_filter": "", "min_lap_s": "80",
        "max_cuts": "0", "activate": "1",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        ev = Event.query.filter_by(slug="spa-2026").one()
        assert ev.active and ev.min_lap_s == 80

    # A second event takes over the active flag on activate.
    admin_client.post("/admin/events/new", data={
        "name": "Werkplaats", "slug": "werkplaats", "kind": "inhouse",
        "track_filter": "", "car_filter": "", "min_lap_s": "60",
        "max_cuts": "1", "activate": "1",
    })
    with app.app_context():
        assert Event.query.filter_by(active=True).count() == 1
        assert Event.active_event().slug == "werkplaats"


def test_duplicate_slug_refused(admin_client, app):
    form = {"name": "A", "slug": "same", "kind": "event", "track_filter": "",
            "car_filter": "", "min_lap_s": "60", "max_cuts": "0"}
    admin_client.post("/admin/events/new", data=form)
    resp = admin_client.post("/admin/events/new",
                             data={**form, "name": "B"}, follow_redirects=True)
    assert b"already used" in resp.data
    with app.app_context():
        assert Event.query.filter_by(slug="same").count() == 1


def test_kiosk_closed_without_flag(client, event):
    resp = client.get("/kiosk")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]


def test_kiosk_open_on_sim_pc(app, event):
    app.config["KIOSK_OPEN"] = True
    client = app.test_client()
    resp = client.get("/kiosk")
    assert resp.status_code == 200
    assert b"popup" in resp.data  # the operator overlay is in the page


def test_public_board_renders(client, event):
    resp = client.get("/e/spa-test")
    assert resp.status_code == 200
    assert b"Spa Test" in resp.data
    assert b'"operator": false' in resp.data or b"popup" not in resp.data


def test_csv_export(admin_client, client, auth, event, app):
    client.post("/api/current-driver", json={"name": "Anton"}, headers=auth)
    client.post("/api/laps", json=lap_payload(), headers=auth)
    with app.app_context():
        ev = Event.query.filter_by(slug="spa-test").one()
    resp = admin_client.get(f"/admin/events/{ev.id}/laps.csv")
    assert resp.status_code == 200
    assert b"Anton" in resp.data and b"2:20.000" in resp.data


def test_healthz(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
