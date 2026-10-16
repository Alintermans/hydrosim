"""Starting and stopping Assetto Corsa without its launcher.

AC's game executable (acs.exe) reads Documents\\Assetto Corsa\\cfg\\race.ini
and drops straight into that session — the same mechanism Content Manager
and every sim-centre tool uses. We write race.ini (+ assists.ini) for one
visitor's run, start acs.exe, and kill it when the run is over. Steam must be
running (offline mode is fine) because acs.exe checks for it.

DemoSim fakes all of it on any OS, so `python -m autopilot --demo` exercises
the full stand without AC.
"""

import os
import random
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Liveries shipped with HydroSim: skins/<car folder>/<skin folder>. Installed
# into AC's car folder automatically and used when [ac] skin is empty.
SKINS = Path(__file__).resolve().parent / "skins"

SESSION_TYPES = {  # race.ini SESSION_0 TYPE / spawn set per session kind
    "practice": (1, "PIT"),
    "race": (3, "START"),
    "hotlap": (4, "HOTLAP_START"),
}


def race_ini(cfg: dict, skin: str) -> str:
    kind = cfg["session"] if cfg["session"] in SESSION_TYPES else "hotlap"
    stype, spawn = SESSION_TYPES[kind]
    laps = 1 if kind == "race" else 0
    return f"""[HEADER]
VERSION=2

[RACE]
TRACK={cfg['track']}
CONFIG_TRACK={cfg['track_config']}
MODEL={cfg['car']}
MODEL_CONFIG=
CARS=1
AI_LEVEL=100
FIXED_SETUP=0
PENALTIES=0
JUMP_START_PENALTY=0
DRIFT_MODE=0
RACE_LAPS={laps}

[CAR_0]
SETUP=
SKIN={skin}
MODEL=-
MODEL_CONFIG=
BALLAST=0
RESTRICTOR=0
DRIVER_NAME=Bezoeker
NATIONALITY=BEL
NATION_CODE=BEL

[SESSION_0]
NAME={kind.title()}
TYPE={stype}
LAPS={laps}
DURATION_MINUTES=0
SPAWN_SET={spawn}

[GHOST_CAR]
RECORDING=0
PLAYING=0
LOAD=0
FILE=
ENABLED=0

[LIGHTING]
SUN_ANGLE={cfg['sun_angle']}
TIME_MULT=1
CLOUD_SPEED=0.2

[GROOVE]
VIRTUAL_LAPS=10
MAX_LAPS=30
STARTING_LAPS=0

[TEMPERATURE]
AMBIENT={cfg['ambient']}
ROAD={cfg['road']}

[WEATHER]
NAME={cfg['weather']}

[WIND]
SPEED_KMH_MIN=0
SPEED_KMH_MAX=0
DIRECTION_DEG=0

[DYNAMIC_TRACK]
SESSION_START=100
RANDOMNESS=0
LAP_GAIN=1
SESSION_TRANSFER=100

[BENCHMARK]
ACTIVE=0

[REPLAY]
ACTIVE=0

[REMOTE]
ACTIVE=0

[RESTART]
ACTIVE=0

[AUTOSPAWN]
ACTIVE=1
"""


def assists_ini(cfg: dict) -> str:
    a = cfg["assists"]
    return f"""[ASSISTS]
IDEAL_LINE={a['ideal_line']}
AUTO_BLIP={a['auto_blip']}
STABILITY_CONTROL={a['stability']}
AUTO_BRAKE=0
AUTO_SHIFTER={a['auto_shifter']}
ABS={a['abs']}
TRACTION_CONTROL={a['traction_control']}
AUTO_CLUTCH={a['auto_clutch']}
VISUALDAMAGE=0
DAMAGE={a['damage']}
FUEL_RATE=0
TYRE_WEAR=0
TYRE_BLANKETS=1
SLIPSTREAM=1
"""


def documents_cfg_dir() -> Path:
    """Documents\\Assetto Corsa\\cfg — Documents may be redirected (OneDrive),
    so ask Windows instead of assuming %USERPROFILE%\\Documents."""
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
        docs = Path(buf.value)
    except Exception:
        docs = Path.home() / "Documents"
    return docs / "Assetto Corsa" / "cfg"


class RealSim:
    EXE = "acs.exe"

    def __init__(self, cfg: dict, log=print):
        self.cfg, self.log = cfg, log
        self.ac_dir = Path(cfg["ac_dir"])
        self.cfg_dir = Path(cfg["cfg_dir"]) if cfg["cfg_dir"] else documents_cfg_dir()
        self.proc = None
        self._sm = None
        self._packet = None
        self._packet_seen = 0.0
        self._running_cache = (0.0, False)

    # -- checks once at startup, so a typo shows up before the doors open --
    def check(self) -> list[str]:
        problems = []
        if not (self.ac_dir / self.EXE).exists():
            problems.append(f"{self.EXE} not found in {self.ac_dir} — set [ac] install_dir")
        cars = self.ac_dir / "content" / "cars"
        if not self.cfg["car"]:
            problems.append("[ac] car is empty")
        elif cars.exists() and not (cars / self.cfg["car"]).is_dir():
            problems.append(f"car folder {self.cfg['car']!r} not in {cars}")
        if problems and cars.exists():
            radicals = sorted(p.name for p in cars.iterdir() if "radical" in p.name.lower())
            if radicals:
                problems.append("cars that look like a Radical: " + ", ".join(radicals))
        tracks = self.ac_dir / "content" / "tracks"
        if tracks.exists() and not (tracks / self.cfg["track"]).is_dir():
            problems.append(f"track folder {self.cfg['track']!r} not in {tracks}")
        if not self.cfg_dir.exists():
            problems.append(f"AC config folder {self.cfg_dir} missing — start AC once by hand")
        return problems

    def install_skins(self) -> list[str]:
        """Copy our liveries for this car into AC (new or changed files only)."""
        import shutil
        ours = SKINS / self.cfg["car"]
        target = self.ac_dir / "content" / "cars" / self.cfg["car"] / "skins"
        if not ours.is_dir() or not target.is_dir():
            return []
        installed = []
        for skin in sorted(p for p in ours.iterdir() if p.is_dir()):
            dst = target / skin.name
            dst.mkdir(exist_ok=True)
            for f in skin.iterdir():
                d = dst / f.name
                if not d.exists() or d.stat().st_size != f.stat().st_size \
                        or d.stat().st_mtime < f.stat().st_mtime:
                    shutil.copy2(f, d)
            installed.append(skin.name)
        return installed

    def _skin(self) -> str:
        if self.cfg["skin"]:
            return self.cfg["skin"]
        ours = SKINS / self.cfg["car"]
        if ours.is_dir():  # our own livery first (HydroTeam V0)
            names = sorted(p.name for p in ours.iterdir() if p.is_dir())
            if names:
                return names[0]
        skins = self.ac_dir / "content" / "cars" / self.cfg["car"] / "skins"
        try:
            return sorted(p.name for p in skins.iterdir() if p.is_dir())[0]
        except (OSError, IndexError):
            return ""

    def _write(self, name: str, content: str) -> None:
        path = self.cfg_dir / name
        backup = path.with_suffix(path.suffix + ".before-hydrosim")
        if path.exists() and not backup.exists():  # keep the owner's own file once
            backup.write_bytes(path.read_bytes())
        path.write_text(content, encoding="utf-8")

    def start(self) -> None:
        self.stop()
        self._write("race.ini", race_ini(self.cfg, self._skin()))
        self._write("assists.ini", assists_ini(self.cfg))
        # The shared memory still holds the LAST frame of the previous run
        # (status 'live'!). Remember that frame's packet id: only a packet id
        # that differs from it proves the NEW session is running.
        self._packet, self._packet_seen = "unset", 0.0
        self._lap = None          # lap-start detection, see telemetry()
        self._clicks, self._live_at = 0, None
        _allow_foreground()
        self.proc = subprocess.Popen([str(self.ac_dir / self.EXE)], cwd=str(self.ac_dir))
        self._running_cache = (time.monotonic(), True)
        self.log(f"Assetto Corsa started ({self.cfg['car']} @ {self.cfg['track']}, "
                 f"{self.cfg['session']})")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        # acs.exe can also have been (re)spawned by Steam: kill by name too.
        subprocess.run(["taskkill", "/F", "/IM", self.EXE],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc = None
        self._running_cache = (time.monotonic(), False)

    def running(self) -> bool:
        at, value = self._running_cache
        if time.monotonic() - at < 1.0:
            return value
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {self.EXE}", "/NH"],
                             capture_output=True, text=True).stdout
        value = self.EXE.lower() in out.lower()
        self._running_cache = (time.monotonic(), value)
        return value

    def telemetry(self):
        """Live = AC_LIVE *and* the graphics page is still ticking: after AC
        is killed the shared memory keeps its last frame (the collector holds
        it open), so a frozen 'live' status must not count."""
        from collector.ac_shared_memory import AC_LIVE, SharedMemory
        if self._sm is None:
            self._sm = SharedMemory()
        g = self._sm.graphics.read()
        now = time.monotonic()
        if self._packet == "unset":
            self._packet = g.packetId           # stale frame of the last run
        elif g.packetId != self._packet:
            self._packet, self._packet_seen = g.packetId, now
        ticking = now - self._packet_seen < 2.0 and self._packet_seen > 0
        if not (ticking and g.status == AC_LIVE):
            return {"live": False}
        p = self._sm.physics.read()
        speed = float(p.speedKmh)
        self._auto_click(now, speed)

        # AC's lap clock already runs on the start menu and during the hotlap
        # run-up to the line. The visitor's lap starts when they CROSS the
        # line: the lap counter goes up, or the current-lap clock resets.
        laps, cur = int(g.completedLaps), int(g.iCurrentTime)
        if self._lap is None:
            self._lap = {"base": laps, "prev": cur, "started": False, "laps0": None}
        st = self._lap
        if not st["started"] and (laps > st["base"] or cur + 1000 < st["prev"]):
            st["started"], st["laps0"] = True, laps
        st["prev"] = cur
        if not st["started"]:
            return {"live": True, "speed": speed, "progress": None,
                    "elapsed_ms": None, "started": False}
        # Over the line again = the visitor's one lap is done: stop at once,
        # don't wait for the server to have the lap.
        return {"live": True, "speed": speed, "started": True,
                "finished": laps > st["laps0"],
                "progress": float(g.normalizedCarPosition),
                "elapsed_ms": max(0, cur)}

    def _auto_click(self, now: float, speed: float) -> None:
        """Fallback when AC still opens on its start menu (rode zijbalk) even
        with AUTOSPAWN: click the configured 'drive' spot, a few times, only
        while the car hasn't moved yet. Off when [ac] start_click is empty."""
        spot = self.cfg.get("start_click")
        started = bool(self._lap and self._lap.get("started"))
        if not spot or self._clicks >= self.cfg.get("start_click_tries", 3) \
                or speed > 1 or started:
            return
        if self._live_at is None:
            self._live_at = now
        if now - self._live_at < self.cfg.get("start_click_delay", 3) + 3 * self._clicks:
            return
        self._clicks += 1
        hwnd = find_ac_window()
        if hwnd:  # the click must land on AC, not on whatever is in front
            bring_to_front(hwnd)
            time.sleep(0.3)
            if not is_foreground(hwnd):
                # Windows refused to hand AC the focus (nobody touched the PC
                # since it booted). A click ON the window always activates it,
                # so first click the middle of AC's screen, then the menu.
                self.log("AC is not the active window - activating it with a click")
                activate_by_click(hwnd)
                time.sleep(0.4)
        else:
            self.log("AC window not found for the start-menu click")
        click(*spot, hwnd=hwnd)
        self.log(f"clicked the AC start menu at {spot} (try {self._clicks}, "
                 f"window {'found' if hwnd else 'missing'})")


def _allow_foreground() -> None:
    """Let the AC window we start take the foreground (Windows otherwise
    may keep it behind the browser)."""
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:
        pass


def find_ac_window(exe: str = "acs.exe", point=None):
    """Handle of a visible, large top-level window of `exe` (default:
    Assetto Corsa), optionally one that covers screen `point`, or None."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    found = []

    def check(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        rect = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left < 640:
            return True
        if point and not (rect.left <= point[0] < rect.right
                          and rect.top <= point[1] < rect.bottom):
            return True
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if h:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                if buf.value.lower().endswith("\\" + exe):
                    found.append(hwnd)
            k.CloseHandle(h)
        return not found

    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(check)
    u.EnumWindows(proc, 0)
    return found[0] if found else None


def bring_to_front(hwnd) -> None:
    """Give AC the foreground. Windows only lets the foreground app hand
    focus over; a synthetic Alt tap lifts that lock (the keyboard hook lets
    our own synthetic keys through)."""
    import ctypes
    u = ctypes.windll.user32
    u.keybd_event(0x12, 0, 0, 0)        # Alt down
    u.keybd_event(0x12, 0, 0x0002, 0)   # Alt up
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)           # SW_RESTORE
    u.SetForegroundWindow(hwnd)
    u.SwitchToThisWindow(hwnd, True)


def is_foreground(hwnd) -> bool:
    import ctypes
    return ctypes.windll.user32.GetForegroundWindow() == hwnd


def activate_by_click(hwnd) -> None:
    """Click the centre of AC's window: the system itself then makes it the
    foreground window, foreground lock or not."""
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    click((r.left + r.right) // 2, (r.top + r.bottom) // 2)


def unlock_foreground() -> bool:
    """Turn off Windows' foreground lock for this session, so the autopilot
    may bring AC to the front without anyone having touched the PC."""
    try:
        import ctypes
        # SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001, value passed in pvParam
        return bool(ctypes.windll.user32.SystemParametersInfoW(0x2001, 0, ctypes.c_void_p(0), 0x2))
    except Exception:
        return False


def click(x: int, y: int, hwnd=None) -> None:
    """A left mouse click at screen pixel (x, y), robust without a mouse
    plugged in: absolute SendInput moves + clicks, and the same click is also
    posted to AC's window as window messages."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    # virtual-desktop coordinates normalised to 0..65535 (multi-monitor safe)
    vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
    vw, vh = max(1, u.GetSystemMetrics(78)), max(1, u.GetSystemMetrics(79))

    def send(flags, px=None, py=None):
        i = INPUT(type=0)
        if px is not None:
            i.mi.dx = int((px - vx) * 65535 / (vw - 1))
            i.mi.dy = int((py - vy) * 65535 / (vh - 1))
            flags |= 0x8000 | 0x4000 | 0x0001   # ABSOLUTE | VIRTUALDESK | MOVE
        i.mi.dwFlags = flags
        u.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))

    send(0, x + 4, y + 4); time.sleep(0.12)   # hover first: menus react to it
    send(0, x, y); time.sleep(0.15)
    send(0x0002); time.sleep(0.1)             # left down
    send(0x0004); time.sleep(0.1)             # left up
    if hwnd:  # belt and braces: the same click as window messages
        pt = wintypes.POINT(int(x), int(y))
        u.ScreenToClient(hwnd, ctypes.byref(pt))
        lp = (pt.y << 16) | (pt.x & 0xFFFF)
        u.PostMessageW(hwnd, 0x0200, 0, lp)      # WM_MOUSEMOVE
        u.PostMessageW(hwnd, 0x0201, 1, lp)      # WM_LBUTTONDOWN
        u.PostMessageW(hwnd, 0x0202, 0, lp)      # WM_LBUTTONUP
    time.sleep(0.05)
    # park the pointer mid-screen, away from AC's side bars
    u.SetCursorPos(u.GetSystemMetrics(0) // 2, u.GetSystemMetrics(1) // 2)


class DemoSim:
    """No AC: 'loads' for 3 s, 'drives' a lap of `lap_s` seconds, then posts
    it to the server exactly like the collector would."""

    def __init__(self, cfg: dict, server, lap_s: float = 20.0, log=print):
        self.cfg, self.server, self.lap_s, self.log = cfg, server, lap_s, log
        self.started = None
        self.posted = False

    def check(self) -> list[str]:
        return []

    def start(self) -> None:
        self.started, self.posted = time.monotonic(), False
        self.log("DEMO: simulator 'started'")

    def stop(self) -> None:
        if self.started:
            self.log("DEMO: simulator 'closed'")
        self.started = None

    def running(self) -> bool:
        return self.started is not None

    def telemetry(self):
        if self.started is None:
            return None
        t = time.monotonic() - self.started - 3
        if t < 0:
            return {"live": False}
        if t < 4:  # rolling to the line: the lap hasn't started
            return {"live": True, "speed": 120.0, "progress": None,
                    "elapsed_ms": None, "started": False}
        t -= 4
        frac = min(1.0, t / self.lap_s)
        if frac >= 1.0 and not self.posted:
            self.posted = True
            lap_ms = random.randint(138_000, 175_000)
            from collector.__main__ import demo_trace
            self.server.post_lap({
                "client_id": uuid.uuid4().hex, "lap_ms": lap_ms,
                "cuts": random.choice([0, 0, 1, 3]),
                "car": self.cfg["car"] or "demo_radical", "track": self.cfg["track"],
                "tyre_compound": "Slick", "abs_used": True, "tc_used": True,
                "auto_clutch": True, "auto_blip": True, "session_type": "hotlap",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "trace": demo_trace(lap_ms)})
            self.log("DEMO: lap posted")
        return {"live": True, "speed": 180.0, "progress": frac % 1.0,
                "elapsed_ms": int(frac * 150_000), "started": True}


def is_windows() -> bool:
    return os.name == "nt"
