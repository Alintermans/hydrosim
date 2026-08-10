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
    from timing import timing_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(timing_bp)
    csrf.exempt(api_bp)  # bearer-token authed; nothing in it trusts a cookie

    from security import init_security
    init_security(app)

    app.jinja_env.filters["laptime"] = format_ms

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.cli.command("init-db")
    def init_db():
        """Create tables. Idempotent — runs on every container start."""
        db.create_all()
        click.echo("Database ready.")

    import sync
    sync.start(app)

    return app
