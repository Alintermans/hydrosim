"""Windows runner — waitress instead of gunicorn (which is Unix-only).

Binds 127.0.0.1 by default: the kiosk browser runs on the same PC. Set
HOST=0.0.0.0 in .env if a second laptop on the venue network should reach it.
"""

import os

from waitress import serve

from app import create_app
from models import db

app = create_app()
with app.app_context():
    db.create_all()

host = os.environ.get("HOST", "127.0.0.1")
port = int(os.environ.get("PORT", "8088"))
print(f"HydroSim timing server on http://{host}:{port}  (kiosk: /kiosk)")
serve(app, host=host, port=port, threads=16, channel_timeout=300)
