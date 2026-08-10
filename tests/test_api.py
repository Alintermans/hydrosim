from tests.conftest import lap_payload


def test_api_requires_token(client, event):
    assert client.post("/api/laps", json=lap_payload()).status_code == 401
    assert client.post("/api/laps", json=lap_payload(),
                       headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_ingest_and_name_flow(client, auth, event):
    payload = lap_payload()
    resp = client.post("/api/laps", json=payload, headers=auth)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["accepted"] and body["valid"] and body["needs_name"]

    # Anonymous state: lap is pending, so not on the board, and the pending
    # queue is not exposed.
    state = client.get("/api/state").get_json()
    assert state["leaderboard"] == []
    assert "pending" not in state

    # Operator state sees it and answers the popup.
    state = client.get("/api/state", headers=auth).get_json()
    assert len(state["pending"]) == 1
    client_id = state["pending"][0]["client_id"]
    resp = client.post(f"/api/laps/{client_id}/assign",
                       json={"driver_name": "Anton"}, headers=auth)
    assert resp.status_code == 200

    state = client.get("/api/state").get_json()
    assert state["leaderboard"][0]["driver_name"] == "Anton"
    assert state["leaderboard"][0]["lap_time"] == "2:20.000"


def test_ingest_is_idempotent(client, auth, event):
    payload = lap_payload()
    assert client.post("/api/laps", json=payload, headers=auth).status_code == 200
    resp = client.post("/api/laps", json=payload, headers=auth)
    assert resp.get_json()["duplicate"] is True
    state = client.get("/api/state", headers=auth).get_json()
    assert len(state["pending"]) == 1


def test_track_filter_refuses_other_track(client, auth, event):
    resp = client.post("/api/laps", json=lap_payload(track="monza"), headers=auth)
    body = resp.get_json()
    assert body["ok"] and body["accepted"] is False
    assert "monza" in body["reason"]
    state = client.get("/api/state", headers=auth).get_json()
    assert state["pending"] == [] and state["recent"] == []


def test_cut_and_too_fast_laps_are_invalid(client, auth, event):
    r1 = client.post("/api/laps", json=lap_payload(cuts=2), headers=auth).get_json()
    assert r1["valid"] is False
    r2 = client.post("/api/laps", json=lap_payload(lap_ms=30_000), headers=auth).get_json()
    assert r2["valid"] is False
    # Invalid laps never prompt for a name and never reach the board.
    state = client.get("/api/state", headers=auth).get_json()
    assert state["pending"] == []
    assert len(state["recent"]) == 2


def test_discard_from_popup(client, auth, event):
    client.post("/api/laps", json=lap_payload(), headers=auth)
    state = client.get("/api/state", headers=auth).get_json()
    client_id = state["pending"][0]["client_id"]
    client.post(f"/api/laps/{client_id}/assign", json={"discard": True}, headers=auth)
    state = client.get("/api/state", headers=auth).get_json()
    assert state["pending"] == [] and state["recent"] == []


def test_current_driver_auto_assigns(client, auth, event):
    client.post("/api/current-driver", json={"name": "Lotte"}, headers=auth)
    resp = client.post("/api/laps", json=lap_payload(), headers=auth).get_json()
    assert resp["needs_name"] is False
    state = client.get("/api/state", headers=auth).get_json()
    assert state["pending"] == []
    assert state["leaderboard"][0]["driver_name"] == "Lotte"
    # Clearing goes back to popup mode.
    client.post("/api/current-driver", json={"name": ""}, headers=auth)
    client.post("/api/laps", json=lap_payload(), headers=auth)
    state = client.get("/api/state", headers=auth).get_json()
    assert len(state["pending"]) == 1


def test_leaderboard_best_lap_per_driver(client, auth, event):
    for name, ms in [("Anton", 141_000), ("Anton", 139_500), ("Lotte", 140_200)]:
        client.post("/api/current-driver", json={"name": name}, headers=auth)
        client.post("/api/laps", json=lap_payload(lap_ms=ms), headers=auth)
    board = client.get("/api/state").get_json()["leaderboard"]
    assert [(l["driver_name"], l["lap_ms"]) for l in board] == \
        [("Anton", 139_500), ("Lotte", 140_200)]
    assert board[0]["rank"] == 1


def test_no_active_event_409(client, auth):
    resp = client.post("/api/laps", json=lap_payload(), headers=auth)
    assert resp.status_code == 409
