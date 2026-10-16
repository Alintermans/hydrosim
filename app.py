"""App factory. `flask --app app init-db` creates the schema (idempotent);
gunicorn serves wsgi:app in the container, waitress serves it on the sim PC.
"""

import logging
import os
from datetime import timedelta

import click
from flask import Flask, jsonify
from flask_wtf import CSRFProtect
from sqlalchemy import event as sa_event

from config import Config
from models import db, format_ms

csrf = CSRFProtect()


def _sqlite_uri(app) -> str:
    data_dir = app.config["DATA_DIR"]
    os.makedirs(data_dir, exist_ok=True)
    return f"sqlite:///{data_dir / 'hydrosim.db'}"


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object())
    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        app.config["SQLALCHEMY_DATABASE_URI"] = _sqlite_uri(app)
    app.permanent_session_lifetime = timedelta(hours=12)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if app.config["TRUST_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        with app.app_context():
            @sa_event.listens_for(db.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()

    from api import api_bp
    from expo import expo_bp
    from timing import timing_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(expo_bp)
    app.register_blueprint(timing_bp)
    csrf.exempt(api_bp)  # bearer-token authed; nothing in it trusts a cookie
    csrf.exempt(expo_bp)  # same: its one POST is the autopilot, bearer-authed

    from security import init_security
    init_security(app)

    app.jinja_env.filters["laptime"] = format_ms

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.cli.command("init-db")
    def init_db():
        """Create tables. Idempotent — runs on every container start."""
        ensure_schema(app)
        click.echo("Database ready.")

    @app.cli.command("create-expo")
    @click.option("--name", default="FTI 2026")
    @click.option("--slug", default="fti-2026")
    @click.option("--car", default="radical", help="car filter (substring of the AC car folder)")
    @click.option("--track", default="spa")
    @click.option("--min-lap", default=100, type=int, help="seconds; shorter laps don't count")
    def create_expo(name, slug, car, track, min_lap):
        """Create (or update) the expo event and make it the active one — so
        setting up the unmanned stand needs no clicking in /admin."""
        from models import KIND_EXPO, Event
        ensure_schema(app)
        event = Event.query.filter_by(slug=slug).first() or Event(slug=slug)
        event.name, event.kind = name, KIND_EXPO
        event.car_filter, event.track_filter = car, track
        event.min_lap_s, event.max_cuts = min_lap, 0
        Event.query.update({Event.active: False})
        event.active = True
        db.session.add(event)
        db.session.commit()
        click.echo(f"Active event: {name} ({slug}) — expo, {car} @ {track}, "
                   f"min lap {min_lap}s.")

    import sync
    sync.start(app)

    return app


def ensure_schema(app) -> None:
    """create_all plus the additive columns it can't add to existing SQLite
    tables (hydroapps' _ensure_columns pattern, one entry so far)."""
    from sqlalchemy import text
    db.create_all()
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    with db.engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(laps)"))}
        for name, ddl in [("assigned_at", "DATETIME"), ("trace", "TEXT")]:
            if name not in cols:
                conn.execute(text(f"ALTER TABLE laps ADD COLUMN {name} {ddl}"))
        conn.commit()
