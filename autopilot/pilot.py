"""The stand's brain: one visitor = one run.

    idle ──button──▶ starting ──AC live──▶ driving ──valid lap──▶ finished
      ▲                 │                     │                      │ (hold, close AC)
      │              timeout              idle / timeout /           ▼
      │                 └──▶ message ◀──── AC closed          naming ──Enter──▶ result
      └───────────────────────(timer)──────────────────────────────┘ (timeout)   │
      ▲                                                                           │
      └────────────────────────────── timer, or next button ─────────────────────┘

Pure logic: the simulator, the inputs, the server and the clock are passed in,
so tests drive it with fakes and `--demo` runs it without Assetto Corsa.

A run ends on the first VALID lap the server stored since the run began — the
server, not the sim, judges laps (event rules: min lap time; expo ignores
cuts), so a hotlap's run-up to the line or a glitch never ends a run early.
"""

import time
from datetime import datetime, timedelta, timezone

NAME_MAX = 24
NAME_MIN = 2


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _parse_utc(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


class Pilot:
    def __init__(self, cfg, server, sim, inputs, clock=time.monotonic,
                 wall=lambda: datetime.now(timezone.utc), log=_log):
        self.cfg, self.server, self.sim, self.inputs = cfg, server, sim, inputs
        self.clock, self.wall, self.log = clock, wall, log
        self.phase = "idle"
        self.entered = clock()
        self.name = ""
        self.lap = None            # dict of the run's lap (from /api/state)
        self.message = ""
        self.run_started = None    # wall clock (UTC) when the run began
        self.crossed_at = None     # wall clock when the car crossed the line
        self.idle_since = None
        self.progress = None
        self.elapsed_ms = None
        self.typed = ""            # rolling buffer for the admin code
        self._last_post = -1e9
        self._last_sent = None
        self._last_lap_check = -1e9

    # ------------------------------------------------------------ helpers --
    def _goto(self, phase: str, **kw) -> None:
        self.log(f"→ {phase}" + (f" ({kw['message']})" if kw.get("message") else ""))
        self.phase = phase
        self.entered = self.clock()
        self.message = kw.get("message", "")
        if phase in ("idle", "starting"):
            self.name, self.lap = "", None
            self.progress = self.elapsed_ms = None
        self._post(force=True)

    def _in_phase(self) -> float:
        return self.clock() - self.entered

    def _post(self, force: bool = False) -> None:
        body = {"phase": self.phase, "name": self.name,
                "lap": self.lap["client_id"] if self.lap else None,
                "progress": self.progress, "elapsed_ms": self.elapsed_ms,
                "message": self.message}
        if self.phase == "naming":
            body["deadline_s"] = max(0, self.cfg["name_timeout"] - self._in_phase())
        now = self.clock()
        interval = 1.0 if self.phase == "driving" else 3.0
        changed = {k: v for k, v in body.items() if k != "deadline_s"} != self._last_sent
        if force or changed and self.phase != "driving" or now - self._last_post >= interval:
            self.server.phase(body)
            self._last_post = now
            self._last_sent = {k: v for k, v in body.items() if k != "deadline_s"}

    def _abort(self, why: str) -> None:
        self.sim.stop()
        self._goto("message", message=why)

    # --------------------------------------------------------------- input --
    def _handle_inputs(self) -> bool:
        """Returns True when the start button was pressed."""
        pressed = False
        for ev in self.inputs.poll():
            kind = ev[0]
            if kind == "button":
                pressed = True
            elif kind == "char":
                self.typed = (self.typed + ev[1].lower())[-40:]
                code = self.cfg.get("admin_code")
                if code and self.typed.endswith(code):
                    self.typed = ""
                    self._admin_toggle()
                    continue
                if self.inputs.locked and self.phase == "naming" \
                        and len(self.name) < NAME_MAX:
                    if ev[1] != " " or (self.name and not self.name.endswith(" ")):
                        self.name += ev[1]
            elif kind == "backspace" and self.phase == "naming" and self.inputs.locked:
                self.name = self.name[:-1]
            elif kind == "enter" and self.phase == "naming" and self.inputs.locked:
                self._submit_name()
        return pressed

    def _admin_toggle(self) -> None:
        if self.inputs.locked:
            self.inputs.unlock(self.cfg["admin_minutes"] * 60)
            self.log(f"ADMIN: keyboard released for {self.cfg['admin_minutes']} min")
        else:
            self.inputs.lock()
            self.log("ADMIN: keyboard locked again")
        if self.phase == "naming":  # the code itself must not become a name
            self.name = ""

    def _submit_name(self) -> bool:
        name = " ".join(self.name.split())
        if len(name) < NAME_MIN or self.lap is None:
            return False
        if self.server.assign(self.lap["client_id"], name):
            self.name = name
            self.lap = dict(self.lap, driver_name=name)
            self._goto("result")
            return True
        self.log("could not store the name — server unreachable?")
        return False

    # ---------------------------------------------------------------- run --
    def _start_run(self) -> None:
        self.run_started = self.wall()
        self.crossed_at = None
        self.idle_since = None
        self._last_lap_check = -1e9
        self._goto("starting")
        try:
            self.sim.start()
        except Exception as exc:  # misconfigured AC: say so on screen, recover
            self.log(f"could not start the simulator: {exc}")
            self._goto("message", message="De simulator kon niet starten")

    def _find_lap(self):
        """The first valid lap stored since this run began, or None."""
        now = self.clock()
        if now - self._last_lap_check < 1.0:
            return None
        self._last_lap_check = now
        state = self.server.state()
        if not state:
            return None
        # AC already counts on its start menu and during the run-up, so the
        # collector reports that bit as a "lap" when the car crosses the line.
        # Once we know when the line was crossed, only laps finishing well
        # after it are the visitor's.
        if self.crossed_at is not None:
            since = self.crossed_at + timedelta(seconds=20)
        else:
            since = self.run_started - timedelta(seconds=2)
        laps = (state.get("pending") or []) + (state.get("recent") or [])
        for lap in sorted(laps, key=lambda l: l.get("recorded_at", "")):
            at = _parse_utc(lap.get("recorded_at", ""))
            if lap.get("valid") and not lap.get("discarded") and at and at >= since:
                return lap
        return None

    def tick(self) -> None:
        pressed = self._handle_inputs()
        t = self._in_phase()
        cfg = self.cfg

        if self.phase == "idle":
            if pressed:
                self._start_run()

        elif self.phase == "starting":
            tel = self.sim.telemetry()
            if tel and tel.get("live"):
                self._goto("driving")
            elif t > 8 and not self.sim.running():
                self._goto("message", message="De simulator kon niet starten")
            elif t > cfg["start_timeout"]:
                self._abort("De simulator kon niet starten")

        elif self.phase == "driving":
            tel = self.sim.telemetry() or {}
            if tel.get("started") and self.crossed_at is None:
                self.crossed_at = self.wall()
            self.progress = tel.get("progress")
            self.elapsed_ms = tel.get("elapsed_ms")
            lap = self._find_lap()
            if lap:
                self.lap = lap
                self._goto("finished")
            elif not self.sim.running():
                self._goto("message", message="De rit is gestopt")
            elif t > cfg["max_run"]:
                self._abort("Tijd is om — de rit is gestopt")
            else:
                if (tel.get("speed") or 0) < 3:
                    self.idle_since = self.idle_since or self.clock()
                    if self.clock() - self.idle_since > cfg["idle_abort"]:
                        self._abort("Rit gestopt — de wagen stond stil")
                else:
                    self.idle_since = None

        elif self.phase == "finished":
            if t >= cfg["finish_hold"]:
                self.sim.stop()
                if self.lap.get("driver_name"):
                    self.name = self.lap["driver_name"]
                    self._goto("result")
                else:
                    self._goto("naming")

        elif self.phase == "naming":
            if t > cfg["name_timeout"]:
                if not self._submit_name():  # a half-typed name still counts
                    self._goto("idle")

        elif self.phase == "result":
            if pressed and t > cfg["result_min"]:
                self._start_run()
            elif t > cfg["result"]:
                self._goto("idle")

        elif self.phase == "message":
            if t > cfg["message"]:
                self._goto("idle")

        self._post()
