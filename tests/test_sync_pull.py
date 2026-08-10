"""Two-way name flow: the cloud kiosk (admin on sim.hydroteam.be) answers the
popup, /api/sync/pull hands it back, sync.apply_assignments lands it locally.
Last-write-wins on Lap.assigned_at in both directions."""

import sync
from tests.conftest import lap_payload
from tests.test_sync import sync_payload


def test_pull_returns_cloud_assignments_once(client, auth):
    lap = lap_payload()
    client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    # The cloud-side popup answers.
    client.post(f"/api/laps/{lap['client_id']}/assign",
                json={"driver_name": "Ward"}, headers=auth)

    pulled = client.post("/api/sync/pull", json={}, headers=auth).get_json()
    assert [a["driver_name"] for a in pulled["assignments"]] == ["Ward"]
    assert pulled["assignments"][0]["client_id"] == lap["client_id"]
    assert pulled["assignments"][0]["assigned_at"]

    # Delivered once — the next pull is empty.
    pulled = client.post("/api/sync/pull", json={}, headers=auth).get_json()
    assert pulled["assignments"] == []


def test_apply_assignments_names_pending_lap(client, auth, event, app):
    client.post("/api/laps", json=lap_payload(client_id="pull1"), headers=auth)
    with app.app_context():
        changed = sync.apply_assignments([
            {"client_id": "pull1", "driver_name": "Ward", "discarded": False,
             "assigned_at": "2026-08-29T14:05:00Z"}])
        assert changed == 1
    state = client.get("/api/state", headers=auth).get_json()
    assert state["pending"] == []  # the local popup closes
    assert state["leaderboard"][0]["driver_name"] == "Ward"


def test_last_write_wins_local_over_stale_cloud(client, auth, event, app):
    """The on-site operator answered later than the cloud admin: the cloud's
    older answer must not overwrite it when pulled."""
    client.post("/api/laps", json=lap_payload(client_id="pull2"), headers=auth)
    client.post("/api/laps/pull2/assign", json={"driver_name": "Anton"},
                headers=auth)  # local answer, stamped now
    with app.app_context():
        changed = sync.apply_assignments([
            {"client_id": "pull2", "driver_name": "Verkeerd", "discarded": False,
             "assigned_at": "2020-01-01T00:00:00Z"}])  # stale cloud answer
        assert changed == 0
    state = client.get("/api/state").get_json()
    assert state["leaderboard"][0]["driver_name"] == "Anton"


def test_push_upsert_respects_newer_cloud_assignment(client, auth):
    """Cloud half: a pushed lap carrying an older assigned_at must not clobber
    a name the cloud admin fixed more recently."""
    lap = lap_payload(driver_name="Anton", valid=True,
                      assigned_at="2026-01-01T10:00:00Z")
    client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    client.post(f"/api/laps/{lap['client_id']}/assign",
                json={"driver_name": "Anton Lintermans"}, headers=auth)

    # The sim PC re-pushes its (older) state — e.g. a queued retry.
    client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    state = client.get("/api/state?event=expo-2026").get_json()
    assert state["leaderboard"][0]["driver_name"] == "Anton Lintermans"
    # And the fix is still queued for the sim PC to pull.
    pulled = client.post("/api/sync/pull", json={}, headers=auth).get_json()
    assert [a["driver_name"] for a in pulled["assignments"]] == ["Anton Lintermans"]


def test_pull_discard_closes_local_popup(client, auth, event, app):
    client.post("/api/laps", json=lap_payload(client_id="pull3"), headers=auth)
    with app.app_context():
        sync.apply_assignments([
            {"client_id": "pull3", "driver_name": None, "discarded": True,
             "assigned_at": "2026-08-29T14:05:00Z"}])
    state = client.get("/api/state", headers=auth).get_json()
    assert state["pending"] == [] and state["recent"] == []
