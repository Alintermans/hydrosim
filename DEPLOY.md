# Deploying HydroSim on Coolify

Target: **https://sim.hydroteam.be**, built from this repo with the
**Dockerfile** build pack, behind Coolify's reverse proxy — the same recipe as
HydroApps (app.hydroteam.be), only smaller.

| | |
|---|---|
| Container port | `8000` |
| Data directory in container | `/data` (SQLite db — the whole backup surface) |
| Health check path | `/healthz` → `200 {"status": "ok"}` |
| Container user | non-root, uid `10001` |

## 1. DNS

| Type | Name | Value |
|---|---|---|
| `A` | `sim` | the Coolify server's IPv4 (same as `app`) |

A `CNAME sim → app.hydroteam.be` works too. Verify with
`dig +short sim.hydroteam.be` before adding the domain in Coolify.

## 2. Create the application

1. **+ New** → **Application** → your connected GitHub App →
   `Alintermans/hydrosim` (private), branch `main`.
2. **Build Pack: Dockerfile**, Base Directory `/`.
3. **Port**: `8000`.
4. **Domain**: `https://sim.hydroteam.be` (with the scheme, so Coolify issues
   a certificate and redirects HTTP→HTTPS).
5. Don't deploy yet — storage and env vars first.

## 3. Persistent storage — before the first deploy

**Storages** → **+ Add** → **Volume Mount**: name `hydrosim_data`, destination
`/data`. Use a **named volume**, not a host bind mount (the container runs as
uid 10001; a bind mount arrives root-owned and the entrypoint refuses to start).

## 4. Environment variables

| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | *generate* | `python -c "import secrets; print(secrets.token_urlsafe(48))"` — the app refuses to boot on the default. |
| `ADMIN_PASSWORD` | *generate* | `/admin` on the cloud instance (rarely needed — the sim PC is where events are managed). Required to boot. |
| `API_TOKEN` | *generate* | What the sim PC's relay authenticates with. **Copy this value into `UPSTREAM_TOKEN` in the sim PC's `.env`.** Required to boot. |
| `TRUST_PROXY` | `1` | Honour `X-Forwarded-*` from Coolify's proxy. |
| `PREFERRED_URL_SCHEME` | `https` | Secure session cookies. |
| `FLASK_DEBUG` | `0` | |

Mark the three secrets as secret/non-build. `DATA_DIR=/data` is baked into the
image. `KIOSK_OPEN` stays unset on the cloud: `/kiosk` then sits behind the
admin login (the popup normally lives on the sim PC's screen anyway).

## 5. Health check

Enable, path `/healthz`, port `8000`, expect `200`. No login, no database.

## 6. Deploy & verify

Hit **Deploy**, enable **Auto Deploy** on push to `main` if wanted (CI runs
pytest but Coolify does not gate on it). Then:

1. `https://sim.hydroteam.be/healthz` → `{"status": "ok"}`.
2. `https://sim.hydroteam.be/` → "No active event" screen (until the sim PC
   syncs its first event, or you create one under `/admin`).
3. On the sim PC: set `UPSTREAM_URL=https://sim.hydroteam.be` and
   `UPSTREAM_TOKEN=<the API_TOKEN from step 4>` in `.env`, restart
   `windows\start.bat`, drive (or demo) a lap — it appears on the public board
   within ~5 s. The event itself is auto-created on first sync.

## 7. Backups

The `hydrosim_data` volume holds one SQLite database (WAL mode — copy
`hydrosim.db` + `-wal` + `-shm` together, or snapshot while stopped). Lap data
also lives on the sim PC and in CSV exports, so the cloud db is the least
precious copy in the system.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Container exits: `DATA_DIR=/data is not writable` | Storage is a bind mount, not a named volume (step 3). |
| Boot fails naming `SECRET_KEY`/`ADMIN_PASSWORD`/`API_TOKEN` | The production guard — set the variable, don't set `FLASK_DEBUG=1` to silence it. |
| Sim PC logs `sync: upstream unreachable` | DNS/certificate not ready, or `UPSTREAM_URL` typo. Laps are queued locally, nothing is lost. |
| Site is empty after a redeploy | The `/data` volume mount is missing (step 3), so the redeploy discarded the database. Add the volume. The sim PC notices the loss and re-pushes the whole board within ~1 minute (`sync: upstream is missing N lap(s)` in its server window) — but without the volume this repeats on every redeploy, and anything only the cloud knew (e.g. names typed on the site that hadn't been pulled yet) is gone for good. |
| Sync delivers nothing, server logs 401 | `UPSTREAM_TOKEN` on the sim PC ≠ `API_TOKEN` on Coolify. |
| Board doesn't update live but does on refresh | SSE blocked by a proxy — the page still polls every 5 s, so this degrades, never breaks. Check `THREADS` (default 32) if many viewers. |
