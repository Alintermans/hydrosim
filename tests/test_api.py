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


def test_driver_laps_detail(client, auth, event):
    for name, ms in [("Anton", 141_000), ("Anton", 139_500), ("anton", 143_000)]:
        client.post("/api/current-driver", json={"name": name}, headers=auth)
        client.post("/api/laps", json=lap_payload(lap_ms=ms), headers=auth)
    resp = client.get("/api/driver-laps?event=spa-test&name=Anton").get_json()
    assert resp["ok"] and len(resp["laps"]) == 3  # case-insensitive match
    assert client.get("/api/driver-laps?event=spa-test&name=").status_code == 404
    assert client.get("/api/driver-laps?event=nope&name=Anton").status_code == 404
    empty = client.get("/api/driver-laps?event=spa-test&name=Niemand").get_json()
    assert empty["laps"] == []


def test_trace_roundtrip(client, auth, event):
    trace = {"t": list(range(0, 120000, 1000)),
             "x": [float(i) for i in range(120)],
             "z": [float(i % 7) for i in range(120)]}
    client.post("/api/current-driver", json={"name": "Anton"}, headers=auth)
    client.post("/api/laps", json=lap_payload(trace=trace), headers=auth)

    state = client.get("/api/state").get_json()
    assert "trace" not in state["leaderboard"][0]  # board payload stays light
    laps = client.get("/api/driver-laps?event=spa-test&name=Anton").get_json()["laps"]
    assert len(laps[0]["trace"]["t"]) == 120

    # Malformed traces are dropped, never stored.
    client.post("/api/laps",
                json=lap_payload(trace={"t": [1], "x": [1], "z": [1]},
                                 recorded_at="2026-08-29T15:00:00+00:00"),
                headers=auth)
    laps = client.get("/api/driver-laps?event=spa-test&name=Anton").get_json()["laps"]
    assert "trace" not in laps[0]  # newest first: the malformed one
