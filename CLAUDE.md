# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Live lap timing for the HydroTeam Assetto Corsa simulator. One Flask codebase,
two instances of the *same app*:

- **sim PC (Windows)**: waitress (`serve_windows.py`, 127.0.0.1:8088) +
  the collector (`python -m collector`) + an Edge kiosk window on `/kiosk`.
- **cloud (Coolify, sim.hydroteam.be)**: gunicorn, Dockerfile build pack,
  `/data` volume. Public live view only.

The local instance is authoritative for LAPS during an event; `sync.py`
relays them upstream, idempotent on `Lap.client_id`, and the cloud's
`/api/sync/laps` upserts and auto-creates unknown events. NAMES flow both
ways: the popup can be answered on the sim PC's kiosk or on
sim.hydroteam.be/kiosk (admin session). Assignments are last-write-wins on
`Lap.assigned_at`; `synced=False` marks "this instance changed it, the other
hasn't seen it" on BOTH sides — the local relay pushes its unsynced rows and
pulls the cloud's via `/api/sync/pull` each cycle. Don't break that clock:
every write to driver_name/discarded must stamp `assigned_at`.

## Commands

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app init-db
FLASK_DEBUG=1 flask --app app run        # http://localhost:5000
pytest                                    # full suite
python -m collector --demo                # fake laps (any OS; needs collector.ini)
```

Windows: `windows\install.ps1` once, then `windows\start.bat`
(or `start-demo.bat` to rehearse without AC).

## Architecture rules — keep these

- **Events are data.** A new fair/track/season is an `Event` row created in
  `/admin`, never a code change. Ingest rules (track/car filter, min lap,
  max cuts) live on the event.
- **Every lap stores the full sim context** (car, tyres, aids, temps, grip —
  see `Lap`). Public boards just don't render most of it; in-house boards and
  the CSV do. Don't strip columns to "simplify" the public event.
- **Ingest judges, sync doesn't.** `/api/laps` (collector) applies the event's
  rules; `/api/sync/laps` (relay) stores verbatim — the local instance already
  judged. Don't make the cloud re-validate.
- **`live.py` is in-process**, hence `gunicorn.conf.py` pins `workers = 1`
  (threads carry SSE). SSE messages are only "something changed" pings; clients
  refetch `/api/state`. The kiosk also polls every 5 s — updates degrade,
  never break. Don't put state in the stream.
- **Offline is a feature.** Collector → local server has a `queue.jsonl`
  fallback; local → cloud has `Lap.synced` + retry. Nothing may require the
  venue's network.
- **Auth**: admin = one shared `ADMIN_PASSWORD` session; machine calls =
  `API_TOKEN` bearer (compare_digest). The api blueprint is CSRF-exempt and
  must therefore never trust a cookie. `/kiosk` holds the token in-page — only
  rendered when `KIOSK_OPEN=1` (sim PC binds 127.0.0.1) or behind admin login.
  `security.py`'s boot guard refuses production defaults; don't weaken it.
- **Windows-compatible server code only** (the sim PC runs waitress): nothing
  Unix-only outside `gunicorn.conf.py`/`entrypoint.sh`.
- **Style**: the UI implements the Claude Design prototype (project
  claude.ai/design/p/79407d43-…, file `HydroSim Timing.dc.html`) on the
  HydroTeam DS tokens (`static/ds/tokens/`). The prototype is a fixed
  1920×1080 canvas; `app.css` clamps every size from those pixels
  (px/19.2 = vw), so the kiosk at 1080p matches the design 1:1. Dark navy +
  water texture for kiosk/in-house, warm sand for the public event board and
  admin. Button variants mirror the DS `Button.jsx`. Design changes start in
  that project, then get re-implemented here — don't invent new styling
  ad hoc.
- Collector structs in `collector/ac_shared_memory.py` are AC 1.16 layouts,
  `_pack_ = 4` — verify against real AC before "fixing" field order. Cut
  detection and aid usage are aggregated per lap in `collector/__main__.py`.

## Testing

`tests/conftest.py` builds an isolated app per test (tmp SQLite, CSRF off,
token `test-token`, admin `test-admin`). `lap_payload()` is the canonical
collector payload. The sync tests drive the *cloud* half through the public
endpoint; `smoke`-style two-instance testing is manual (see git history).
CI (`.github/workflows/ci.yml`) runs pytest on Python 3.12.
