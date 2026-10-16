"""Expo mode — the unmanned fair stand (FTI).

Nobody operates the sim: the autopilot (`python -m autopilot`, sim PC only)
starts Assetto Corsa when a visitor presses the wheel button, ends the session
after one lap, and owns the keyboard so the only thing it can do is type the
visitor's name. This module is the screen's half of that:

  POST /api/expo/phase   autopilot -> server: what the stand is doing now
  GET  /api/expo/state   expo screen -> server: that phase + this run's result
  GET  /expo             the second screen (kiosk rules: sim PC or admin)

The phase lives in memory on purpose — it describes the next two minutes, not
history. Laps themselves go through the normal collector -> /api/laps path,
names through /api/laps/<id>/assign; nothing here stores timing data.
"""

import threading
import time

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import live
from models import Event, Lap, leaderboard
from security import kiosk_allowed, token_ok, token_required

expo_bp = Blueprint("expo", __name__)

PHASES = ("idle", "starting", "driving", "finished", "naming", "result",
          "message")

_lock = threading.Lock()
_state = {"phase": "idle", "name": "", "lap": None, "progress": None,
          "elapsed_ms": None, "message": "", "deadline": None,
          "updated": 0.0}


def reset() -> None:
    """Tests: back to a fresh stand."""
    with _lock:
        _state.update(phase="idle", name="", lap=None, progress=None,
                      elapsed_ms=None, message="", deadline=None, updated=0.0)


def lap_result(event, lap) -> dict:
    """Where does this lap land? Ranked against every OTHER driver's best, so
    an unnamed lap (still waiting for its name) already gets its place, and a
    returning visitor isn't compared with themselves."""
    key = (lap.driver_name or "").strip().casefold()
    others = [l for l in leaderboard(event)
              if l.driver_name.strip().casefold() != key or not key]
    faster = sum(1 for l in others if l.lap_ms < lap.lap_ms)
    rank, total = faster + 1, len(others) + 1
    leader = others[0] if others else None
    own_best = None
    if key:
        mine = [l for l in leaderboard(event)
                if l.driver_name.strip().casefold() == key]
        if mine and mine[0].lap_ms < lap.lap_ms:
            own_best = mine[0].as_dict()
    return {
        "lap": lap.as_dict(),
        "rank": rank,
        "total": total,
        "beaten_pct": (round(100 * (total - rank) / (total - 1))
                       if total > 1 else 100),
        "gap_ms": lap.lap_ms - leader.lap_ms if leader else 0,
        "leader": leader.as_dict() if leader else None,
        "record": leader is None or lap.lap_ms < leader.lap_ms,
        "own_best": own_best,
    }


@expo_bp.post("/api/expo/phase")
@token_required
def set_phase():
    data = request.get_json(silent=True) or {}
    phase = data.get("phase")
    if phase not in PHASES:
        return jsonify({"ok": False, "error": f"phase must be one of {PHASES}"}), 400
    deadline_s = data.get("deadline_s")
    new = {
        "phase": phase,
        "name": str(data.get("name") or "")[:40],
        "lap": str(data.get("lap") or "")[:40] or None,
        "progress": (max(0.0, min(1.0, float(data["progress"])))
                     if isinstance(data.get("progress"), (int, float)) else None),
        "elapsed_ms": (int(data["elapsed_ms"])
                       if isinstance(data.get("elapsed_ms"), (int, float)) else None),
        "message": str(data.get("message") or "")[:200],
        "deadline": (time.time() + float(deadline_s)
                     if isinstance(deadline_s, (int, float)) else None),
    }
    with _lock:
        changed = any(_state[k] != v for k, v in new.items() if k != "deadline")
        changed = changed or (new["deadline"] is None) != (_state["deadline"] is None)
        _state.update(new, updated=time.time())
    if changed:  # heartbeats stay silent; real changes wake the screen
        live.publish("expo")
    return jsonify({"ok": True})


@expo_bp.get("/api/expo/state")
def get_state():
    if not (kiosk_allowed() or token_ok()):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    with _lock:
        st = dict(_state)
    now = time.time()
    out = {
        "ok": True,
        "phase": st["phase"],
        "name": st["name"],
        "progress": st["progress"],
        "elapsed_ms": st["elapsed_ms"],
        "message": st["message"],
        "deadline_s": (max(0.0, round(st["deadline"] - now, 1))
                       if st["deadline"] else None),
        # The autopilot heartbeats every few seconds; a long silence means it
        # isn't running and the screen should say so instead of freezing.
        "age_s": round(now - st["updated"], 1) if st["updated"] else None,
        "result": None,
    }
    event = Event.active_event()
    if st["lap"] and event is not None:
        lap = Lap.query.filter_by(client_id=st["lap"]).first()
        if lap is not None:
            out["result"] = lap_result(event, lap)
    return jsonify(out)


@expo_bp.get("/expo")
def screen():
    if not kiosk_allowed():
        return redirect(url_for("timing.login", next="/expo"))
    event = Event.active_event()
    if event is None:
        return render_template("no_event.html")
    from flask import current_app
    return render_template("expo.html", event=event,
                           api_token=current_app.config["API_TOKEN"])
