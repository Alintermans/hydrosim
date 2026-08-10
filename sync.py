"""Upstream relay: the sim PC pushes its laps to sim.hydroteam.be.

Design:
  - The LOCAL instance is authoritative during an event (venue Wi-Fi drops are
    a given). Laps land locally first; this thread ships anything with
    synced=False to `{UPSTREAM_URL}/api/sync/laps` and marks it synced on 200.
  - Assigning/erasing a name or discarding a lap flips synced back to False,
    so corrections travel too — the endpoint upserts by client_id.
  - Each batch carries its event (slug/name/kind/filters); the cloud creates
    unknown events on the fly, so a new event set up on the sim PC needs zero
    clicks in Coolify.
  - Plain stdlib urllib (hydroapps house rule: no vendor SDKs); failures back
    off and never crash the thread. Losing the network loses nothing — laps
    wait in SQLite until it returns.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request

from models import Lap, db

log = logging.getLogger(__name__)

INTERVAL_S = 3.0
BACKOFF_MAX_S = 60.0
BATCH = 50


def _push(url: str, token: str, payload: dict) -> bool:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url + "/api/sync/laps",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status == 200


def _run(app) -> None:
    url = app.config["UPSTREAM_URL"]
    token = app.config["UPSTREAM_TOKEN"]
    backoff = INTERVAL_S
    log.info("sync: relaying laps to %s", url)
    while True:
        time.sleep(backoff)
        try:
            with app.app_context():
                laps = (Lap.query.filter_by(synced=False)
                        .order_by(Lap.id).limit(BATCH).all())
                if not laps:
                    backoff = INTERVAL_S
                    continue
                ev = laps[0].event  # batch per event, keeps the payload simple
                batch = [l for l in laps if l.event_id == ev.id]
                payload = {
                    "event": {
                        "slug": ev.slug, "name": ev.name, "kind": ev.kind,
                        "track_filter": ev.track_filter, "car_filter": ev.car_filter,
                        "min_lap_s": ev.min_lap_s, "max_cuts": ev.max_cuts,
                    },
                    "laps": [l.as_dict() for l in batch],
                }
                if _push(url, token, payload):
                    for l in batch:
                        l.synced = True
                    db.session.commit()
                    log.info("sync: delivered %d lap(s)", len(batch))
                    backoff = 0.5 if len(batch) == BATCH else INTERVAL_S
                else:
                    backoff = min(backoff * 2, BACKOFF_MAX_S)
        except (urllib.error.URLError, OSError) as exc:
            log.warning("sync: upstream unreachable (%s) — retrying in %.0fs",
                        exc, min(backoff * 2, BACKOFF_MAX_S))
            backoff = min(backoff * 2, BACKOFF_MAX_S)
        except Exception:  # noqa: BLE001 — the relay must never die
            log.exception("sync: unexpected error")
            backoff = min(backoff * 2, BACKOFF_MAX_S)


def start(app) -> None:
    if not app.config["UPSTREAM_URL"]:
        return
    if not app.config["UPSTREAM_TOKEN"]:
        log.warning("sync: UPSTREAM_URL set but UPSTREAM_TOKEN empty — not starting")
        return
    t = threading.Thread(target=_run, args=(app,), name="upstream-sync", daemon=True)
    t.start()
