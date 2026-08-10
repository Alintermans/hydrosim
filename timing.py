"""Web screens.

  /                -> the active event's leaderboard (what sim.hydroteam.be shows)
  /e/<slug>        -> a specific event's leaderboard (past events stay linkable)
  /kiosk           -> the event-stand screen: leaderboard + name popup + driver
                      picker. Renders only for an admin or when KIOSK_OPEN=1.
  /admin/…         -> event management (create/edit/activate), lap corrections,
                      CSV export. One shared password.
"""

import csv
import hmac
import io
from datetime import timezone as tz
from zoneinfo import ZoneInfo

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)

from models import KINDS, KIND_EVENT, Event, Lap, db
from security import admin_required, kiosk_allowed

timing_bp = Blueprint("timing", __name__)


# ---------------------------------------------------------------- public ----

@timing_bp.get("/")
def home():
    event = Event.active_event()
    if event is None:
        return render_template("no_event.html")
    return redirect(url_for("timing.board", slug=event.slug))


@timing_bp.get("/e/<slug>")
def board(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    return render_template("board.html", event=event, operator=False,
                           api_token="", qr=None, show_driverbox=False)


@timing_bp.get("/kiosk")
def kiosk():
    if not kiosk_allowed():
        return redirect(url_for("timing.login", next="/kiosk"))
    event = Event.active_event()
    if event is None:
        return render_template("no_event.html")
    # The kiosk JS talks to the operator API with the bearer token. This page
    # only renders on the sim PC itself (127.0.0.1 + KIOSK_OPEN) or behind the
    # admin login, so handing it the token is deliberate.
    # "Driver in the seat" pre-assigns at INGEST, which only happens on the
    # instance the collector posts to — on the cloud kiosk the box would be a
    # dead control, so it only renders where laps actually arrive.
    ingests = bool(current_app.config.get("KIOSK_OPEN")
                   or current_app.config.get("UPSTREAM_URL"))
    return render_template("board.html", event=event, operator=True,
                           api_token=current_app.config["API_TOKEN"],
                           qr=_public_board_qr(event), show_driverbox=ingests)


def _public_board_qr(event):
    """Data-URI QR for the public live view — the 'follow along on your phone'
    box on the kiosk. Only exists when this instance relays somewhere public."""
    base = current_app.config.get("UPSTREAM_URL")
    if not base or event.kind != KIND_EVENT:
        return None
    try:
        import segno
    except ImportError:
        return None
    url = f"{base}/e/{event.slug}"
    return {"img": segno.make(url, error="m").svg_data_uri(dark="#021E37",
                                                           border=0),
            "url": base.replace("https://", "").replace("http://", "")}


# ----------------------------------------------------------------- admin ----

@timing_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        configured = current_app.config["ADMIN_PASSWORD"]
        given = request.form.get("password", "")
        if configured and hmac.compare_digest(given, configured):
            session["admin"] = True
            session.permanent = True
            target = request.form.get("next") or url_for("timing.admin_events")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("timing.admin_events")
            return redirect(target)
        flash("Wrong password.", "error")
    return render_template("login.html", next=request.args.get("next", ""))


@timing_bp.post("/admin/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("timing.home"))


@timing_bp.get("/admin")
@admin_required
def admin_events():
    events = Event.query.order_by(Event.active.desc(), Event.id.desc()).all()
    counts = {e.id: e.laps.count() for e in events}
    return render_template("admin/events.html", events=events, counts=counts)


def _apply_event(event: Event) -> str | None:
    """Read the event form onto `event`. Returns an error sentence or None."""
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip().lower().replace(" ", "-")
    if not name or not slug:
        return "Name and slug are both required."
    clash = Event.query.filter(Event.slug == slug, Event.id != event.id).first()
    if clash:
        return f"Slug '{slug}' is already used by event '{clash.name}'."
    kind = request.form.get("kind", KIND_EVENT)
    event.name, event.slug = name[:120], slug[:64]
    event.kind = kind if kind in KINDS else KIND_EVENT
    event.track_filter = request.form.get("track_filter", "").strip()[:120]
    event.car_filter = request.form.get("car_filter", "").strip()[:120]
    try:
        event.min_lap_s = max(0, int(request.form.get("min_lap_s") or 60))
        event.max_cuts = max(0, int(request.form.get("max_cuts") or 0))
    except ValueError:
        return "Minimum lap time and allowed cuts must be whole numbers."
    return None


@timing_bp.route("/admin/events/new", methods=["GET", "POST"])
@admin_required
def event_new():
    # Column defaults only apply at flush; the form renders this unsaved
    # instance, so give it real values instead of None-shaped fields.
    event = Event(name="", slug="", kind=KIND_EVENT, track_filter="",
                  car_filter="", min_lap_s=60, max_cuts=0)
    if request.method == "POST":
        error = _apply_event(event)
        if error:
            flash(error, "error")
        else:
            if request.form.get("activate"):
                Event.query.update({Event.active: False})
                event.active = True
            db.session.add(event)
            db.session.commit()
            flash(f"Event '{event.name}' created.", "ok")
            return redirect(url_for("timing.admin_events"))
    return render_template("admin/event_form.html", event=event, is_new=True)


@timing_bp.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@admin_required
def event_edit(event_id):
    event = db.session.get(Event, event_id) or abort(404)
    if request.method == "POST":
        error = _apply_event(event)
        if error:
            flash(error, "error")
        else:
            db.session.commit()
            flash("Saved.", "ok")
            return redirect(url_for("timing.admin_events"))
    return render_template("admin/event_form.html", event=event, is_new=False)


@timing_bp.post("/admin/events/<int:event_id>/activate")
@admin_required
def event_activate(event_id):
    event = db.session.get(Event, event_id) or abort(404)
    Event.query.update({Event.active: False})
    event.active = True
    db.session.commit()
    flash(f"'{event.name}' is now the active event.", "ok")
    return redirect(url_for("timing.admin_events"))


@timing_bp.post("/admin/events/<int:event_id>/delete")
@admin_required
def event_delete(event_id):
    event = db.session.get(Event, event_id) or abort(404)
    if event.laps.count():
        flash("This event has laps — it can't be deleted. "
              "Deactivate it instead; the board stays reachable on /e/"
              f"{event.slug}.", "error")
    else:
        db.session.delete(event)
        db.session.commit()
        flash("Event deleted.", "ok")
    return redirect(url_for("timing.admin_events"))


@timing_bp.get("/admin/events/<int:event_id>/laps")
@admin_required
def admin_laps(event_id):
    event = db.session.get(Event, event_id) or abort(404)
    laps = event.laps.order_by(Lap.id.desc()).limit(500).all()
    return render_template("admin/laps.html", event=event, laps=laps)


@timing_bp.post("/admin/laps/<int:lap_id>/update")
@admin_required
def admin_lap_update(lap_id):
    """Rename / discard / restore a lap after the fact (typos happen)."""
    lap = db.session.get(Lap, lap_id) or abort(404)
    action = request.form.get("action", "rename")
    if action == "discard":
        lap.discarded = True
    elif action == "restore":
        lap.discarded = False
    else:
        lap.driver_name = request.form.get("driver_name", "").strip()[:80] or None
    from models import utcnow
    lap.assigned_at = utcnow()
    lap.synced = False
    db.session.commit()
    import live
    live.publish("name", lap.event.slug)
    return redirect(url_for("timing.admin_laps", event_id=lap.event_id))


@timing_bp.get("/admin/events/<int:event_id>/laps.csv")
@admin_required
def laps_csv(event_id):
    event = db.session.get(Event, event_id) or abort(404)
    zone = ZoneInfo(current_app.config["TIMEZONE"])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["recorded_at", "driver", "lap_time", "lap_ms", "valid", "cuts",
                "discarded", "car", "track", "track_config", "tyre_compound",
                "abs", "tc", "stability", "auto_clutch", "auto_blip",
                "ideal_line", "fuel_rate", "tyre_rate", "damage_rate",
                "air_temp", "road_temp", "grip", "session_type"])
    from models import format_ms
    for lap in event.laps.order_by(Lap.id):
        local = lap.recorded_at.replace(tzinfo=tz.utc).astimezone(zone)
        w.writerow([local.strftime("%Y-%m-%d %H:%M:%S"), lap.driver_name or "",
                    format_ms(lap.lap_ms), lap.lap_ms, int(lap.valid), lap.cuts,
                    int(lap.discarded), lap.car, lap.track, lap.track_config,
                    lap.tyre_compound, int(lap.abs_used), int(lap.tc_used),
                    lap.stability, int(lap.auto_clutch), int(lap.auto_blip),
                    int(lap.ideal_line), lap.fuel_rate, lap.tyre_rate,
                    lap.damage_rate, lap.air_temp or "", lap.road_temp or "",
                    lap.grip or "", lap.session_type])
    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = \
        f"attachment; filename={event.slug}-laps.csv"
    return resp
