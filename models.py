"""Data model: events and laps.

An Event is one leaderboard — the expo stand at a fair, or an in-house session
at the workshop. Exactly one event is *active* at a time per instance: that is
the one the collector's laps land in and the one `/` shows. Future events are
new rows, not code changes.

A Lap always carries the full sim context (car, track, tyres, aids, weather) —
the public leaderboard simply doesn't render most of it, the in-house view
does. `client_id` is the idempotency key that lets the local instance re-send
a lap to the cloud instance any number of times.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

KIND_EVENT = "event"      # public expo leaderboard: big names, no telemetry noise
KIND_INHOUSE = "inhouse"  # team timing: settings columns + filters
KINDS = (KIND_EVENT, KIND_INHOUSE)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default=KIND_EVENT)

    # Ingest rules, applied when the collector submits a lap (never on sync —
    # the local instance already judged the lap, the cloud stores it verbatim).
    track_filter = db.Column(db.String(120), nullable=False, default="")  # substring, "" = any
    car_filter = db.Column(db.String(120), nullable=False, default="")    # substring, "" = any
    min_lap_s = db.Column(db.Integer, nullable=False, default=60)         # reject glitches/shortcuts
    max_cuts = db.Column(db.Integer, nullable=False, default=0)           # more cuts -> lap invalid

    active = db.Column(db.Boolean, nullable=False, default=False)

    # In-house convenience: when set, incoming laps are assigned to this driver
    # immediately and no name popup appears. Cleared from the kiosk.
    current_driver = db.Column(db.String(80), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    laps = db.relationship("Lap", backref="event", lazy="dynamic",
                           cascade="all, delete-orphan")

    @staticmethod
    def active_event():
        return Event.query.filter_by(active=True).order_by(Event.id.desc()).first()

    def accepts(self, track: str, car: str) -> tuple[bool, str]:
        """Ingest filter. Returns (accepted, reason-when-refused)."""
        t = (track or "").lower()
        c = (car or "").lower()
        if self.track_filter and self.track_filter.lower() not in t:
            return False, f"track {track!r} does not match filter {self.track_filter!r}"
        if self.car_filter and self.car_filter.lower() not in c:
            return False, f"car {car!r} does not match filter {self.car_filter!r}"
        return True, ""


class Lap(db.Model):
    __tablename__ = "laps"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(40), unique=True, nullable=False)  # uuid from the collector
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)

    driver_name = db.Column(db.String(80), nullable=True)  # NULL = waiting for the popup
    lap_ms = db.Column(db.Integer, nullable=False)
    cuts = db.Column(db.Integer, nullable=False, default=0)
    valid = db.Column(db.Boolean, nullable=False, default=True)
    discarded = db.Column(db.Boolean, nullable=False, default=False)  # operator pressed "ignore"

    # Sim context — captured on every lap, rendered on the in-house views.
    car = db.Column(db.String(120), nullable=False, default="")
    track = db.Column(db.String(120), nullable=False, default="")
    track_config = db.Column(db.String(120), nullable=False, default="")
    tyre_compound = db.Column(db.String(80), nullable=False, default="")
    abs_used = db.Column(db.Boolean, nullable=False, default=False)
    tc_used = db.Column(db.Boolean, nullable=False, default=False)
    stability = db.Column(db.Float, nullable=False, default=0.0)   # 0..1 aid strength
    auto_clutch = db.Column(db.Boolean, nullable=False, default=False)
    auto_blip = db.Column(db.Boolean, nullable=False, default=False)
    ideal_line = db.Column(db.Boolean, nullable=False, default=False)
    fuel_rate = db.Column(db.Float, nullable=False, default=1.0)
    tyre_rate = db.Column(db.Float, nullable=False, default=1.0)
    damage_rate = db.Column(db.Float, nullable=False, default=1.0)
    air_temp = db.Column(db.Float, nullable=True)
    road_temp = db.Column(db.Float, nullable=True)
    grip = db.Column(db.Float, nullable=True)
    session_type = db.Column(db.String(24), nullable=False, default="")

    recorded_at = db.Column(db.DateTime, nullable=False, default=utcnow)  # when driven (UTC)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)   # when stored here

    # Local instance only: False until the upstream relay has delivered this
    # row (again). Assigning a name flips it back to False so the update ships.
    synced = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def counts(self) -> bool:
        """On the board: named, clean, not thrown away."""
        return self.valid and not self.discarded and bool(self.driver_name)

    @property
    def aids(self) -> list[str]:
        out = []
        if self.abs_used:
            out.append("ABS")
        if self.tc_used:
            out.append("TC")
        if self.stability and self.stability > 0:
            out.append(f"STAB {round(self.stability * 100)}%")
        if self.auto_clutch:
            out.append("A-CLUTCH")
        if self.auto_blip:
            out.append("BLIP")
        if self.ideal_line:
            out.append("LINE")
        return out

    def as_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "driver_name": self.driver_name,
            "lap_ms": self.lap_ms,
            "lap_time": format_ms(self.lap_ms),
            "cuts": self.cuts,
            "valid": self.valid,
            "discarded": self.discarded,
            "car": self.car,
            "track": self.track,
            "track_config": self.track_config,
            "tyre_compound": self.tyre_compound,
            "aids": self.aids,
            "abs_used": self.abs_used,
            "tc_used": self.tc_used,
            "stability": self.stability,
            "auto_clutch": self.auto_clutch,
            "auto_blip": self.auto_blip,
            "ideal_line": self.ideal_line,
            "fuel_rate": self.fuel_rate,
            "tyre_rate": self.tyre_rate,
            "damage_rate": self.damage_rate,
            "air_temp": self.air_temp,
            "road_temp": self.road_temp,
            "grip": self.grip,
            "session_type": self.session_type,
            "recorded_at": self.recorded_at.isoformat() + "Z",
        }


def format_ms(ms) -> str:
    """83467 -> "1:23.467". The one lap-time formatter (Jinja filter + JSON)."""
    if ms is None or ms <= 0:
        return "–"
    ms = int(ms)
    minutes, rest = divmod(ms, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def leaderboard(event, car: str | None = None):
    """Best counting lap per driver, fastest first.

    `car` narrows to one car (the in-house comparison must be like-for-like;
    on a public event there is normally only one car anyway).
    """
    q = Lap.query.filter_by(event_id=event.id, valid=True, discarded=False)
    q = q.filter(Lap.driver_name.isnot(None))
    if car:
        q = q.filter(Lap.car == car)
    best: dict[str, Lap] = {}
    for lap in q:
        key = lap.driver_name.strip().casefold()
        if key not in best or lap.lap_ms < best[key].lap_ms:
            best[key] = lap
    return sorted(best.values(), key=lambda l: l.lap_ms)
