"""HydroSim collector — watches Assetto Corsa, reports finished laps.

    python -m collector            # real mode, reads AC shared memory (Windows)
    python -m collector --demo     # fabricates a lap every ~25 s (any OS)

Every completed lap becomes one POST to the local timing server, carrying the
time, the cut count and the full sim context (car, track, tyres, aids,
temperatures). If the server is unreachable the lap is appended to
queue.jsonl and re-sent later — a lap is never lost.

Configuration: collector.ini next to this package (see collector.example.ini).
"""

import argparse
import configparser
import json
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ config --

def load_config(path: Path) -> dict:
    cp = configparser.ConfigParser()
    # utf-8-sig: Windows PowerShell writes a BOM; plain utf-8 chokes on it.
    cp.read(path, encoding="utf-8-sig")
    return {
        "url": cp.get("server", "url", fallback="http://127.0.0.1:8088").rstrip("/"),
        "token": cp.get("server", "token", fallback=""),
        "poll_hz": cp.getfloat("timing", "poll_hz", fallback=20.0),
        # A "cut" = an excursion with at least this many tyres off track.
        "tyres_out_threshold": cp.getint("timing", "tyres_out_threshold", fallback=4),
        "queue_file": Path(cp.get("server", "queue_file",
                                  fallback=str(HERE / "queue.jsonl"))),
    }


# ----------------------------------------------------------------- sending --

def post_lap(cfg: dict, payload: dict) -> bool:
    req = urllib.request.Request(
        cfg["url"] + "/api/laps",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['token']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode() or "{}")
            if body.get("accepted") is False:
                log(f"server refused lap: {body.get('reason')}")
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log(f"server unreachable ({exc}) — lap queued")
        return False


def enqueue(cfg: dict, payload: dict) -> None:
    with cfg["queue_file"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def flush_queue(cfg: dict) -> None:
    qf = cfg["queue_file"]
    if not qf.exists():
        return
    lines = [l for l in qf.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        qf.unlink(missing_ok=True)
        return
    remaining = []
    sent = 0
    for i, line in enumerate(lines):
        payload = json.loads(line)
        if remaining or not post_lap(cfg, payload):  # keep order: stop at first failure
            remaining.append(line)
        else:
            sent += 1
    if sent:
        log(f"flushed {sent} queued lap(s)")
    if remaining:
        qf.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    else:
        qf.unlink(missing_ok=True)


def submit(cfg: dict, payload: dict) -> None:
    flush_queue(cfg)  # older laps first, so the board fills in order
    if not post_lap(cfg, payload):
        enqueue(cfg, payload)


# ---------------------------------------------------------------- real run --

def run_real(cfg: dict) -> None:
    from collector.ac_shared_memory import (AC_LIVE, SESSION_NAMES,
                                            SharedMemory)

    sm = SharedMemory()
    log("watching Assetto Corsa shared memory "
        f"(poll {cfg['poll_hz']:.0f} Hz, cut threshold "
        f"{cfg['tyres_out_threshold']} tyres out)")

    interval = 1.0 / cfg["poll_hz"]
    baseline_laps = None      # completedLaps at the start of the lap we watch
    was_live = False
    # Per-lap aggregates
    cuts = 0
    off_track = False
    abs_used = tc_used = False
    ai_seen = False

    def reset_aggregates():
        nonlocal cuts, off_track, abs_used, tc_used, ai_seen
        cuts, off_track, abs_used, tc_used, ai_seen = 0, False, False, False, False

    while True:
        time.sleep(interval)
        g = sm.graphics.read()

        if g.status != AC_LIVE:
            if was_live:
                log("session left live state — waiting")
            was_live = False
            continue
        if not was_live:
            log(f"live: {SESSION_NAMES.get(g.session, g.session)} session")
            was_live = True
            baseline_laps = g.completedLaps
            reset_aggregates()
            continue

        p = sm.physics.read()

        # Session restarted or a new session loaded: counter went backwards.
        if baseline_laps is not None and g.completedLaps < baseline_laps:
            baseline_laps = g.completedLaps
            reset_aggregates()
            continue

        # Aggregate within the current lap.
        if p.isAIControlled:
            ai_seen = True
        if p.abs > 0.0:
            abs_used = True
        if p.tc > 0.0:
            tc_used = True
        now_off = p.numberOfTyresOut >= cfg["tyres_out_threshold"]
        if now_off and not off_track:
            cuts += 1
        off_track = now_off

        if g.completedLaps > baseline_laps:
            lap_ms = int(g.iLastTime)
            s = sm.static.read()
            lap_cuts, lap_abs, lap_tc, lap_ai = cuts, abs_used, tc_used, ai_seen
            baseline_laps = g.completedLaps
            reset_aggregates()

            if lap_ms <= 5000:
                log(f"ignoring implausible lap time {lap_ms} ms")
                continue
            if lap_ai:
                log("ignoring AI-driven lap")
                continue

            payload = {
                "client_id": uuid.uuid4().hex,
                "lap_ms": lap_ms,
                "cuts": lap_cuts,
                "car": s.carModel,
                "track": s.track,
                "track_config": s.trackConfiguration,
                "tyre_compound": g.tyreCompound,
                "abs_used": lap_abs,
                "tc_used": lap_tc,
                "stability": round(float(s.aidStability), 3),
                "auto_clutch": bool(s.aidAutoClutch),
                "auto_blip": bool(s.aidAutoBlip),
                "ideal_line": bool(g.idealLineOn),
                "fuel_rate": round(float(s.aidFuelRate), 3),
                "tyre_rate": round(float(s.aidTireRate), 3),
                "damage_rate": round(float(s.aidMechanicalDamage), 3),
                "air_temp": round(float(p.airTemp), 1),
                "road_temp": round(float(p.roadTemp), 1),
                "grip": round(float(g.surfaceGrip), 3),
                "session_type": SESSION_NAMES.get(g.session, ""),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            mins, rest = divmod(lap_ms, 60_000)
            log(f"LAP {mins}:{rest // 1000:02d}.{rest % 1000:03d}  "
                f"{s.carModel} @ {s.track} cuts={lap_cuts}")
            submit(cfg, payload)


# ---------------------------------------------------------------- demo run --

def run_demo(cfg: dict) -> None:
    """No AC needed: a plausible Spa lap every ~25 s. For testing the whole
    pipeline (popup, board, sync) on any machine."""
    log("DEMO mode — fabricating laps, no Assetto Corsa needed")
    while True:
        time.sleep(random.uniform(18, 30))
        lap_ms = random.randint(138_000, 172_000)
        payload = {
            "client_id": uuid.uuid4().hex,
            "lap_ms": lap_ms,
            "cuts": random.choices([0, 1], weights=[0.85, 0.15])[0],
            "car": "demo_formula_hydro",
            "track": "spa",
            "track_config": "",
            "tyre_compound": "Soft (S)",
            "abs_used": random.random() < 0.5,
            "tc_used": random.random() < 0.5,
            "stability": random.choice([0.0, 0.0, 0.5]),
            "auto_clutch": True,
            "auto_blip": True,
            "ideal_line": random.random() < 0.3,
            "fuel_rate": 1.0, "tyre_rate": 1.0, "damage_rate": 0.0,
            "air_temp": 21.0, "road_temp": 27.0, "grip": 0.98,
            "session_type": "practice",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        mins, rest = divmod(lap_ms, 60_000)
        log(f"DEMO LAP {mins}:{rest // 1000:02d}.{rest % 1000:03d}")
        submit(cfg, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true",
                        help="fabricate laps instead of reading AC")
    parser.add_argument("--config", type=Path, default=HERE / "collector.ini")
    args = parser.parse_args()

    if not args.config.exists():
        sys.exit(f"Config not found: {args.config}\n"
                 f"Copy collector.example.ini to collector.ini and fill in the token.")
    cfg = load_config(args.config)
    if not cfg["token"]:
        sys.exit("collector.ini has no [server] token — copy it from the server's .env (API_TOKEN).")

    try:
        if args.demo:
            run_demo(cfg)
        else:
            if sys.platform != "win32":
                sys.exit("Real mode reads Windows shared memory — on this OS use --demo.")
            run_real(cfg)
    except KeyboardInterrupt:
        log("bye")


if __name__ == "__main__":
    main()
