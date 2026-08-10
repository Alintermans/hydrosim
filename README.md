# HydroSim Timing

Live lap timing for the HydroTeam Assetto Corsa simulator. One codebase, two
deployments:

- **The sim PC (Windows)** runs the *collector* (reads Assetto Corsa shared
  memory) plus a *local timing server*. The second screen next to the rig shows
  `/kiosk`: the live leaderboard, and **after every completed lap a popup asks
  who drove it**. Everything works with zero internet.
- **The cloud (Coolify, [sim.hydroteam.be](https://sim.hydroteam.be))** runs the
  same app as the public live view. The sim PC relays every lap (and every
  name correction) upstream; visitors and people at home watch the board live.

Events are **data, not code**: create one in `/admin` (name, track filter, kind,
validity rules), activate it, done. Next year's fair or a Tuesday-evening
in-house session is a new row, not a new deployment.

```text
┌───────────────  sim PC (Windows)  ───────────────┐      ┌────── Coolify ──────┐
│ Assetto Corsa                                    │      │  sim.hydroteam.be   │
│   └─ shared memory                               │      │                     │
│        └─ collector (python -m collector)        │      │   same Flask app    │
│             └─ POST /api/laps ─┐ (queued if down)│      │   public board /e/… │
│                                ▼                 │ sync │         ▲           │
│ local server (serve_windows.py, waitress :8088) ─┼──────┼─────────┘           │
│   └─ second screen: /kiosk  (board + name popup) │      │  POST /api/sync/laps│
└──────────────────────────────────────────────────┘      └─────────────────────┘
```

## Event kinds

| | `event` (public) | `inhouse` (team timing) |
|---|---|---|
| Board shows | rank, name, time, gap | + car, tyre compound, aids chips, car filter |
| Name entry | popup after each lap | popup, **or** set "driver in the seat" once |
| Meant for | fairs, open days | practice evenings, driver comparison |

Both kinds capture the **full sim context on every lap** — car, track + layout,
tyre compound, ABS/TC engagement, stability %, auto-clutch/blip, ideal line,
fuel/tyre/damage multipliers, air & road temperature, surface grip, session
type. The in-house views surface it; the CSV export (`/admin`) carries all of
it for later analysis. Filters (`track_filter`, `car_filter`), a minimum lap
time and an allowed-cuts count are set per event in the admin.

## Lap validity

The collector counts *cuts* (an excursion with ≥ `tyres_out_threshold` tyres
off track — default 4, see `collector/collector.example.ini`) and flags
ABS/TC as "used" when the aid actually engaged during the lap. The server
marks a lap invalid when it has more cuts than the event allows or is faster
than the event's minimum lap time. Invalid laps never prompt for a name and
never reach the board, but stay visible in the admin and the CSV.

## Sim PC install (Windows)

1. Install Python 3.12+ ([python.org](https://www.python.org/downloads/), tick
   *Add python.exe to PATH*).
2. Clone this repo, then run once:

   ```powershell
   powershell -ExecutionPolicy Bypass -File windows\install.ps1
   ```

   This creates the venv, installs dependencies and generates `.env`
   (fresh `SECRET_KEY`, `API_TOKEN`, `ADMIN_PASSWORD`) plus
   `collector\collector.ini` with the matching token.
3. Fill in `UPSTREAM_TOKEN` in `.env` — it's the `API_TOKEN` configured on the
   Coolify app (see [DEPLOY.md](DEPLOY.md)). Leave it empty to run fully
   offline.
4. Start everything: `windows\start.bat` — server, collector and the Edge
   kiosk window (drag it to the second screen once; Windows remembers).
5. Open `http://127.0.0.1:8088/admin`, create an event (e.g. track filter
   `spa`) and activate it.

**Entering names from a second laptop** — two ways:

- **Via the site (normal case)**: open `https://sim.hydroteam.be/kiosk` on
  any laptop, sign in with the cloud instance's `ADMIN_PASSWORD`. Pending
  laps sync up unnamed; a name typed there travels back to the sim PC on the
  next sync cycle (~3 s) and closes the popup on the big screen too. Both
  kiosks may be open at once — assignments are last-write-wins on a per-lap
  clock (`Lap.assigned_at`), so the later answer sticks everywhere.
- **Via the venue LAN (offline fallback)**: the server binds `0.0.0.0`, so a
  laptop on the same network can open `http://<sim-pc-ip>:8088/kiosk` and
  sign in with the sim PC's `ADMIN_PASSWORD`. `KIOSK_OPEN=1` skips the login
  for loopback requests only, so the venue Wi-Fi never gets the token-holding
  page for free. `install.ps1` adds the Windows-firewall rule (run as
  administrator if that step warns).

`windows\start-demo.bat` does the same with a **demo collector** that invents
a lap every ~25 s — test the popup, the board and the sync without Assetto
Corsa running (works on any OS: `python -m collector --demo`).

If the venue network blocks the sync, nothing is lost: laps queue in SQLite
and ship when the connection returns. If the *local server* itself is down,
the collector queues laps in `collector/queue.jsonl` and replays them in order.

## Cloud deploy

See [DEPLOY.md](DEPLOY.md) — Coolify, Dockerfile build pack, one `/data`
volume, three env vars. The sim PC's relay auto-creates its event on the cloud
instance, so a new event needs zero Coolify clicks.

## Event-day runbook (Dutch)

Zie [EVENTDAY.md](EVENTDAY.md) — stappenplan voor wie de stand bemant.

## Local development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app init-db
FLASK_DEBUG=1 flask --app app run       # http://localhost:5000
pytest                                   # test suite
python -m collector --demo               # needs collector/collector.ini
```

The UI chrome is English (data — names, event titles — is whatever the team
types, usually Dutch). Styling implements the Claude Design prototype
(`HydroSim Timing.dc.html`, project `hydrosim design`) on the HydroTeam design
system tokens in `static/ds/tokens/` — use `var(--ht-blue)` etc., no ad-hoc
colors.

## Repository layout

| Path | What |
|---|---|
| `app.py`, `config.py`, `models.py` | Flask factory, env config, Event/Lap schema |
| `api.py` | collector ingest, sync upsert, popup assign, state + SSE |
| `timing.py` | board, kiosk, admin screens, CSV export |
| `live.py` | in-process SSE broadcaster (why gunicorn runs 1 worker) |
| `sync.py` | background relay: local laps → sim.hydroteam.be |
| `collector/` | AC shared-memory reader + lap detector (+ `--demo`) |
| `serve_windows.py`, `windows/` | waitress runner, install/start scripts |
| `Dockerfile`, `entrypoint.sh`, `gunicorn.conf.py` | Coolify deployment |
