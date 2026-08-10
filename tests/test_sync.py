"""The cloud half of the relay: /api/sync/laps upserts verbatim."""

from tests.conftest import lap_payload


def sync_payload(laps, **event_overrides):
    event = {"slug": "expo-2026", "name": "Open Bedrijvendag", "kind": "event",
             "track_filter": "spa", "car_filter": "", "min_lap_s": 60,
             "max_cuts": 0}
    event.update(event_overrides)
    return {"event": event, "laps": laps}


def test_sync_creates_event_and_laps(client, auth):
    lap = lap_payload(driver_name="Anton", valid=True)
    resp = client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["stored"] == 1

    state = client.get("/api/state?event=expo-2026").get_json()
    assert state["event"]["name"] == "Open Bedrijvendag"
    assert state["leaderboard"][0]["driver_name"] == "Anton"


def test_sync_upsert_carries_corrections(client, auth):
    lap = lap_payload(driver_name=None, valid=True)
    client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    state = client.get("/api/state?event=expo-2026").get_json()
    assert state["leaderboard"] == []  # unnamed: not on the board yet

    # The name arrives on a later sync of the same client_id.
    lap["driver_name"] = "Anton"
    client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    state = client.get("/api/state?event=expo-2026").get_json()
    assert state["leaderboard"][0]["driver_name"] == "Anton"
    assert len(state["recent"]) == 1  # upsert, not a second row

    # A discard travels too.
    lap["discarded"] = True
    client.post("/api/sync/laps", json=sync_payload([lap]), headers=auth)
    state = client.get("/api/state?event=expo-2026").get_json()
    assert state["leaderboard"] == [] and state["recent"] == []


def test_sync_mirrors_event_metadata(client, auth):
    client.post("/api/sync/laps", json=sync_payload([]), headers=auth)
    client.post("/api/sync/laps",
                json=sync_payload([], name="Renamed", kind="inhouse"),
                headers=auth)
    state = client.get("/api/state?event=expo-2026").get_json()
    assert state["event"]["name"] == "Renamed"
    assert state["event"]["kind"] == "inhouse"


def test_first_synced_event_becomes_active(client, auth):
    client.post("/api/sync/laps", json=sync_payload([]), headers=auth)
    # The cloud instance had no event; the synced one is now what / shows.
    resp = client.get("/", follow_redirects=False)
    assert "/e/expo-2026" in resp.headers["Location"]
