from datetime import datetime, timedelta, timezone

from autopilot.pilot import Pilot
from autopilot.sim import assists_ini, race_ini

CFG = {"start_timeout": 120, "max_run": 420, "idle_abort": 45, "finish_hold": 5,
       "name_timeout": 90, "result": 25, "result_min": 6, "message": 8,
       "admin_code": "hydroadmin", "admin_minutes": 10, "lock": True,
       "car": "radical_sr3", "track": "spa", "track_config": "", "session": "hotlap",
       "weather": "3_clear", "ambient": 22, "road": 28, "sun_angle": 16,
       "assists": {"auto_shifter": 1, "auto_clutch": 1, "auto_blip": 1, "abs": 1,
                   "traction_control": 1, "stability": 0, "ideal_line": 0,
                   "damage": 0}}

T0 = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeServer:
    def __init__(self):
        self.posts, self.laps, self.assigned = [], [], {}

    def state(self):
        return {"pending": [l for l in self.laps if not l.get("driver_name")],
                "recent": list(self.laps)}

    def phase(self, body):
        self.posts.append(body)

    def assign(self, client_id, name):
        self.assigned[client_id] = name
        return True


class FakeSim:
    def __init__(self):
        self.on, self.live, self.speed, self.starts = False, False, 100.0, 0

    def start(self):
        self.on, self.starts = True, self.starts + 1

    def stop(self):
        self.on = self.live = False

    def running(self):
        return self.on

    def telemetry(self):
        if not self.on:
            return None
        return {"live": self.live, "speed": self.speed, "progress": 0.5,
                "elapsed_ms": 60_000}


class FakeInputs:
    def __init__(self):
        self.queue, self.locked = [], True

    def poll(self):
        out, self.queue = self.queue, []
        return out

    def unlock(self, s):
        self.locked = False

    def lock(self):
        self.locked = True

    def type(self, text):
        self.queue += [("char", c) for c in text]


def make():
    clock, server, sim, inputs = Clock(), FakeServer(), FakeSim(), FakeInputs()
    pilot = Pilot(CFG, server, sim, inputs, clock=clock, wall=lambda: T0,
                  log=lambda m: None)
    return pilot, clock, server, sim, inputs


def step(pilot, clock, seconds=1.0, n=1):
    for _ in range(n):
        clock.t += seconds
        pilot.tick()


def lap(ms=140_000, valid=True, at=T0 + timedelta(minutes=2), cid="L1"):
    return {"client_id": cid, "lap_ms": ms, "valid": valid, "discarded": False,
            "driver_name": None, "recorded_at": at.isoformat()}


def drive_to_naming(pilot, clock, server, sim, inputs):
    inputs.queue.append(("button",))
    step(pilot, clock)
    assert pilot.phase == "starting" and sim.starts == 1
    sim.live = True
    step(pilot, clock)
    assert pilot.phase == "driving"
    server.laps.append(lap())
    step(pilot, clock, 1.1)
    assert pilot.phase == "finished"
    step(pilot, clock, 6)
    assert pilot.phase == "naming" and not sim.on  # AC closed after the hold


def test_full_run():
    pilot, clock, server, sim, inputs = make()
    drive_to_naming(pilot, clock, server, sim, inputs)
    inputs.type("  Lotte")
    inputs.queue.append(("backspace",))
    inputs.type("e V.")
    inputs.queue.append(("enter",))
    step(pilot, clock)
    assert server.assigned == {"L1": "Lotte V."}
    assert pilot.phase == "result"
    step(pilot, clock, 26)
    assert pilot.phase == "idle"
    assert {"idle", "starting", "driving", "finished", "naming", "result"} <= \
        {p["phase"] for p in server.posts}


def test_short_or_old_laps_do_not_end_the_run():
    pilot, clock, server, sim, inputs = make()
    inputs.queue.append(("button",))
    step(pilot, clock)
    sim.live = True
    step(pilot, clock)
    server.laps += [lap(valid=False, cid="runup"),                  # hotlap run-up
                    lap(at=T0 - timedelta(minutes=5), cid="old")]   # previous visitor
    step(pilot, clock, 1.1, n=3)
    assert pilot.phase == "driving"


def test_idle_car_aborts_and_returns_to_idle():
    pilot, clock, server, sim, inputs = make()
    inputs.queue.append(("button",))
    step(pilot, clock)
    sim.live, sim.speed = True, 0.0
    step(pilot, clock)
    step(pilot, clock, 1, n=50)
    assert pilot.phase == "message" and not sim.on
    step(pilot, clock, 9)
    assert pilot.phase == "idle"


def test_name_timeout_keeps_half_typed_name_or_goes_idle():
    pilot, clock, server, sim, inputs = make()
    drive_to_naming(pilot, clock, server, sim, inputs)
    inputs.type("Jo")
    step(pilot, clock, 91)
    assert server.assigned == {"L1": "Jo"} and pilot.phase == "result"

    pilot, clock, server, sim, inputs = make()
    drive_to_naming(pilot, clock, server, sim, inputs)
    step(pilot, clock, 91)
    assert server.assigned == {} and pilot.phase == "idle"


def test_admin_code_releases_keyboard_and_never_becomes_a_name():
    pilot, clock, server, sim, inputs = make()
    drive_to_naming(pilot, clock, server, sim, inputs)
    inputs.type("hydroadmin")
    step(pilot, clock)
    assert inputs.locked is False and pilot.name == ""
    inputs.type("hydroadmin")
    step(pilot, clock)
    assert inputs.locked is True


def test_wheel_button_during_naming_does_nothing():
    pilot, clock, server, sim, inputs = make()
    drive_to_naming(pilot, clock, server, sim, inputs)
    inputs.queue.append(("button",))
    step(pilot, clock)
    assert pilot.phase == "naming" and sim.starts == 1


def test_next_visitor_can_start_from_result_after_minimum():
    pilot, clock, server, sim, inputs = make()
    drive_to_naming(pilot, clock, server, sim, inputs)
    inputs.type("Zoe")
    inputs.queue.append(("enter",))
    step(pilot, clock)
    inputs.queue.append(("button",))
    step(pilot, clock)
    assert pilot.phase == "result"        # too soon: still reading their place
    step(pilot, clock, 6)
    inputs.queue.append(("button",))
    step(pilot, clock)
    assert pilot.phase == "starting" and sim.starts == 2


def test_race_ini_sessions():
    hot = race_ini(CFG, "red")
    assert "MODEL=radical_sr3" in hot and "SKIN=red" in hot
    assert "TYPE=4" in hot and "SPAWN_SET=HOTLAP_START" in hot
    race = race_ini(dict(CFG, session="race"), "red")
    assert "TYPE=3" in race and "LAPS=1" in race and "SPAWN_SET=START" in race
    assert "AUTO_SHIFTER=1" in assists_ini(CFG)


def test_runup_lap_after_crossing_is_ignored():
    pilot, clock, server, sim, inputs = make()
    inputs.queue.append(("button",))
    step(pilot, clock)
    sim.live = True
    step(pilot, clock)
    crossed = T0 + timedelta(minutes=1)
    pilot.wall = lambda: crossed
    sim.telemetry = lambda: {"live": True, "speed": 150, "started": True,
                             "progress": 0.01, "elapsed_ms": 500}
    step(pilot, clock)
    assert pilot.crossed_at == crossed
    # start menu + run-up, reported as a "lap" right at the line: not theirs
    server.laps.append(lap(ms=101_000, at=crossed + timedelta(seconds=1), cid="menu"))
    step(pilot, clock, 1.1)
    assert pilot.phase == "driving"
    server.laps.append(lap(at=crossed + timedelta(minutes=2, seconds=20), cid="real"))
    step(pilot, clock, 1.1)
    assert pilot.phase == "finished" and pilot.lap["client_id"] == "real"
