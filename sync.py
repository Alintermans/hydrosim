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
RECONCILE_EVERY = 20  # cycles (~1 min): compare inventories, re-push gaps


def _post(url: str, token: str, path: str, payload: dict):
    req = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        # An HTTP answer IS a reachable upstream — e.g. a cloud still running
        # older code without this endpoint. Skip the step, don't abort the
        # whole cycle (connection errors still bubble up to the backoff).
        log.warning("sync: %s answered %s", path, exc.code)
        return None


def apply_assignments(assignments: list) -> int:
    """Apply name/discard decisions pulled from the cloud onto local rows.
    Same last-write-wins clock as the push direction (api._incoming_wins);
    a row the local operator answered later keeps its answer and will
    overwrite the cloud on the next push. Returns how many rows changed."""
    from api import _incoming_wins, _parse_dt
    changed = 0
    for a in assignments:
        lap = Lap.query.filter_by(client_id=str(a.get("client_id", ""))).first()
        if lap is None:
            continue
        incoming_at = _parse_dt(a.get("assigned_at"))
        if not _incoming_wins(incoming_at, lap.assigned_at):
            continue
        name = (str(a["driver_name"])[:80] if a.get("driver_name") else None)
        discarded = bool(a.get("discarded", False))
        if (name, discarded, incoming_at) == (lap.driver_name, lap.discarded,
                                              lap.assigned_at):
            continue
        lap.driver_name = name
        lap.discarded = discarded
        lap.assigned_at = incoming_at
        lap.synced = True  # this IS the cloud's state; nothing new to push
        changed += 1
    if changed:
        db.session.commit()
    return changed


def mark_missing_unsynced(upstream_ids: set) -> int:
    """Self-healing half: any local lap the upstream doesn't hold goes back to
    synced=False so the push loop re-delivers it (with its name — assigned_at
    makes that a clean last-write-wins upsert). This is what repopulates the
    site after a redeploy without a persisted volume, a wipe, or a migration."""
    relapsed = 0
    for lap in Lap.query.filter_by(synced=True):
        if lap.client_id not in upstream_ids:
            lap.synced = False
            relapsed += 1
    if relapsed:
        db.session.commit()
    return relapsed


def _run(app) -> None:
    from models import Event

    url = app.config["UPSTREAM_URL"]
    token = app.config["UPSTREAM_TOKEN"]
    backoff = INTERVAL_S
    cycle = 0
    log.info("sync: relaying laps to %s", url)
    while True:
        time.sleep(backoff)
        try:
            with app.app_context():
                # 0. periodically: does the upstream still have everything?
                #    (first cycle too, so a reconnect heals immediately)
                if cycle % RECONCILE_EVERY == 0:
                    slugs = [e.slug for e in Event.query.all()]
                    inv = _post(url, token, "/api/sync/inventory",
                                {"events": slugs})
                    if inv is not None:
                        relapsed = mark_missing_unsynced(
                            set(inv.get("client_ids") or []))
                        if relapsed:
                            log.warning("sync: upstream is missing %d lap(s) "
                                        "— re-pushing everything it lost",
                                        relapsed)
                cycle += 1

                # 1. pull: names typed on sim.hydroteam.be come home first, so
                #    the kiosk popup here closes within one cycle.
                pulled = _post(url, token, "/api/sync/pull", {})
                if pulled and pulled.get("assignments"):
                    changed = apply_assignments(pulled["assignments"])
                    if changed:
                        import live
                        live.publish("name", "")
                        log.info("sync: applied %d assignment(s) from upstream",
                                 changed)

                # 2. push: everything local that the cloud hasn't seen yet.
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
                if _post(url, token, "/api/sync/laps", payload) is not None:
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
