"""JSON API. Three callers, three shapes:

  - the collector on the sim PC   -> POST /api/laps        (judged: filters apply)
  - the local instance's relay    -> POST /api/sync/laps   (verbatim upsert)
  - the kiosk / leaderboard JS    -> GET  /api/state, /api/stream,
                                     POST /api/laps/<id>/assign, /api/current-driver

All POSTs are bearer-token authed (the kiosk page is only served where it may
hold the token — see security.kiosk_allowed). CSRF is exempted for this
blueprint because nothing in it trusts a cookie.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request, stream_with_context

import live
from models import KIND_EVENT, KINDS, Event, Lap, db, format_ms, leaderboard
from security import kiosk_allowed, token_ok, token_required

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _parse_recorded_at(value) -> datetime:
    from models import utcnow
    return _parse_dt(value) or utcnow()


def _incoming_wins(incoming_at: datetime | None, stored_at: datetime | None) -> bool:
    """Last write wins; an unstamped side loses to a stamped one; a push of
    the very same assignment (equal stamps) is accepted as a no-op."""
    if incoming_at is None:
        return stored_at is None
    return stored_at is None or incoming_at >= stored_at


def _lap_fields(data: dict) -> dict:
    """The sim-context columns, straight from the payload with safe defaults."""
    def f(key, default=None, cast=None):
        v = data.get(key, default)
        if v is None:
            return default
        if cast:
            try:
                return cast(v)
            except (TypeError, ValueError):
                return default
        return v

    return {
        "car": str(f("car", ""))[:120],
        "track": str(f("track", ""))[:120],
        "track_config": str(f("track_config", ""))[:120],
        "tyre_compound": str(f("tyre_compound", ""))[:80],
        "abs_used": bool(f("abs_used", False)),
        "tc_used": bool(f("tc_used", False)),
        "stability": f("stability", 0.0, float) or 0.0,
        "auto_clutch": bool(f("auto_clutch", False)),
        "auto_blip": bool(f("auto_blip", False)),
        "ideal_line": bool(f("ideal_line", False)),
        "fuel_rate": f("fuel_rate", 1.0, float),
        "tyre_rate": f("tyre_rate", 1.0, float),
        "damage_rate": f("damage_rate", 1.0, float),
        "air_temp": f("air_temp", None, float),
        "road_temp": f("road_temp", None, float),
        "grip": f("grip", None, float),
        "session_type": str(f("session_type", ""))[:24],
        "recorded_at": _parse_recorded_at(data.get("recorded_at")),
    }


@api_bp.post("/laps")
@token_required
def ingest_lap():
    """Collector -> local instance. The event's rules decide validity here."""
    data = request.get_json(silent=True) or {}
    client_id = str(data.get("client_id", ""))[:40]
    lap_ms = data.get("lap_ms")
    if not client_id or not isinstance(lap_ms, int) or lap_ms <= 0:
        return jsonify({"ok": False, "error": "client_id and positive lap_ms required"}), 400

    if Lap.query.filter_by(client_id=client_id).first():
        return jsonify({"ok": True, "duplicate": True})  # collector retry — already stored

    event = None
    if data.get("event_slug"):
        event = Event.query.filter_by(slug=data["event_slug"]).first()
    event = event or Event.active_event()
    if event is None:
        return jsonify({"ok": False, "error": "no active event"}), 409

    fields = _lap_fields(data)
    accepted, reason = event.accepts(fields["track"], fields["car"])
    if not accepted:
        log.info("lap refused: %s", reason)
        return jsonify({"ok": True, "accepted": False, "reason": reason})

    from models import utcnow
    cuts = int(data.get("cuts") or 0)
    valid = cuts <= event.max_cuts and lap_ms >= event.min_lap_s * 1000
    lap = Lap(client_id=client_id, event_id=event.id, lap_ms=lap_ms, cuts=cuts,
              valid=valid, driver_name=event.current_driver or None,
              assigned_at=utcnow() if event.current_driver else None, **fields)
    db.session.add(lap)
    db.session.commit()
    live.publish("lap", event.slug)
    log.info("lap stored: %s %s cuts=%d valid=%s driver=%s",
             format_ms(lap_ms), fields["car"], cuts, valid, lap.driver_name)
    return jsonify({"ok": True, "accepted": True, "valid": valid,
                    "needs_name": lap.driver_name is None and valid})


@api_bp.post("/sync/laps")
@token_required
def sync_laps():
    """Local instance -> cloud. Verbatim upsert; unknown events are created."""
    data = request.get_json(silent=True) or {}
    ev_data = data.get("event") or {}
    slug = str(ev_data.get("slug", ""))[:64]
    if not slug:
        return jsonify({"ok": False, "error": "event.slug required"}), 400

    event = Event.query.filter_by(slug=slug).first()
    if event is None:
        event = Event(slug=slug, active=Event.active_event() is None)
        db.session.add(event)
    # The sim PC is authoritative for event metadata — mirror it.
    event.name = str(ev_data.get("name") or slug)[:120]
    kind = ev_data.get("kind")
    event.kind = kind if kind in KINDS else KIND_EVENT
    event.track_filter = str(ev_data.get("track_filter", ""))[:120]
    event.car_filter = str(ev_data.get("car_filter", ""))[:120]
    event.min_lap_s = int(ev_data.get("min_lap_s") or 60)
    event.max_cuts = int(ev_data.get("max_cuts") or 0)
    db.session.flush()

    stored = 0
    for lap_data in data.get("laps") or []:
        client_id = str(lap_data.get("client_id", ""))[:40]
        lap_ms = lap_data.get("lap_ms")
        if not client_id or not isinstance(lap_ms, int) or lap_ms <= 0:
            continue
        lap = Lap.query.filter_by(client_id=client_id).first()
        if lap is None:
            lap = Lap(client_id=client_id, event_id=event.id, lap_ms=lap_ms,
                      **_lap_fields(lap_data))
            db.session.add(lap)
        lap.cuts = int(lap_data.get("cuts") or 0)
        lap.valid = bool(lap_data.get("valid", True))
        # The assignment half (name / discard) is last-write-wins: this
        # instance's kiosk may have answered the popup *after* the sim PC's
        # push was queued — then our answer stands (and synced stays False, so
        # /api/sync/pull still hands it back to the sim PC).
        incoming_at = _parse_dt(lap_data.get("assigned_at"))
        if _incoming_wins(incoming_at, lap.assigned_at):
            lap.driver_name = (str(lap_data["driver_name"])[:80]
                               if lap_data.get("driver_name") else None)
            lap.discarded = bool(lap_data.get("discarded", False))
            lap.assigned_at = incoming_at
            lap.synced = True  # matches the sim PC again; nothing to pull
        stored += 1
    db.session.commit()
    live.publish("lap", event.slug)
    return jsonify({"ok": True, "stored": stored})


@api_bp.post("/laps/<client_id>/assign")
@token_required
def assign_lap(client_id):
    """The name popup's answer: a driver name, or 'ignore this lap'. Runs on
    the sim PC's kiosk AND on sim.hydroteam.be (admin session there)."""
    lap = Lap.query.filter_by(client_id=client_id).first()
    if lap is None:
        return jsonify({"ok": False, "error": "unknown lap"}), 404
    data = request.get_json(silent=True) or {}
    if data.get("discard"):
        lap.discarded = True
    else:
        name = str(data.get("driver_name", "")).strip()[:80]
        if not name:
            return jsonify({"ok": False, "error": "driver_name required"}), 400
        lap.driver_name = name
        lap.discarded = False
    from models import utcnow
    lap.assigned_at = utcnow()
    lap.synced = False  # the correction must travel to the other instance
    db.session.commit()
    live.publish("name", lap.event.slug)
    return jsonify({"ok": True, "lap": lap.as_dict()})


@api_bp.post("/sync/pull")
@token_required
def sync_pull():
    """The other direction: the sim PC collects assignments made on THIS
    instance (names typed on sim.hydroteam.be by a signed-in admin). Rows with
    synced=False here are exactly the ones this instance changed itself;
    handing them over marks them synced."""
    laps = Lap.query.filter_by(synced=False).order_by(Lap.id).limit(200).all()
    out = []
    for lap in laps:
        out.append({"client_id": lap.client_id,
                    "driver_name": lap.driver_name,
                    "discarded": lap.discarded,
                    "assigned_at": (lap.assigned_at.isoformat() + "Z"
                                    if lap.assigned_at else None)})
        lap.synced = True
    db.session.commit()
    return jsonify({"ok": True, "assignments": out})


@api_bp.post("/current-driver")
@token_required
def set_current_driver():
    """In-house: pre-assign incoming laps to whoever is in the seat."""
    event = Event.active_event()
    if event is None:
        return jsonify({"ok": False, "error": "no active event"}), 409
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:80]
    event.current_driver = name or None
    db.session.commit()
    live.publish("driver", event.slug)
    return jsonify({"ok": True, "current_driver": event.current_driver})


@api_bp.get("/state")
def state():
    """Everything a screen needs, in one fetch. Pending laps (the popup queue)
    are included only where the popup may exist."""
    slug = request.args.get("event", "")
    event = (Event.query.filter_by(slug=slug).first() if slug
             else Event.active_event())
    if event is None:
        return jsonify({"ok": True, "event": None})

    car = request.args.get("car") or None
    board = leaderboard(event, car=car)
    recent = (Lap.query.filter_by(event_id=event.id, discarded=False)
              .order_by(Lap.id.desc()).limit(12).all())
    cars = sorted({l.car for l in
                   Lap.query.filter_by(event_id=event.id, discarded=False)
                   if l.car})

    from flask import current_app

    from models import local_zone
    zone = local_zone(current_app.config["TIMEZONE"])
    today = datetime.now(zone).date()
    all_laps = Lap.query.filter_by(event_id=event.id, discarded=False).all()
    drivers = {l.driver_name.strip().casefold() for l in all_laps if l.driver_name}
    laps_today = sum(
        1 for l in all_laps
        if l.recorded_at.replace(tzinfo=timezone.utc).astimezone(zone).date() == today)

    payload = {
        "ok": True,
        "event": {"slug": event.slug, "name": event.name, "kind": event.kind,
                  "current_driver": event.current_driver,
                  "track_filter": event.track_filter,
                  "car_filter": event.car_filter},
        "stats": {"laps_today": laps_today, "drivers": len(drivers)},
        "leaderboard": [
            {**lap.as_dict(), "rank": i + 1} for i, lap in enumerate(board)
        ],
        "recent": [l.as_dict() for l in recent],
        "cars": cars,
        "car": car or "",
    }
    if kiosk_allowed() or token_ok():
        pending = (Lap.query.filter_by(event_id=event.id, valid=True,
                                       discarded=False, driver_name=None)
                   .order_by(Lap.id).all())
        payload["pending"] = [l.as_dict() for l in pending]
    return jsonify(payload)


@api_bp.get("/stream")
def stream():
    resp = Response(stream_with_context(live.stream()),
                    mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp
