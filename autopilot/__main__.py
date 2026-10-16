"""HydroSim autopilot — runs the unmanned expo stand (FTI).

    python -m autopilot            # the real stand (Windows, Assetto Corsa)
    python -m autopilot --learn    # show which wheel button / key you press
    python -m autopilot --demo     # whole flow without AC, on any OS

The timing server and the collector run next to it, as always (see
windows\\start-fti.bat); this process adds: start AC on the wheel button,
end the session after one lap, own the keyboard for the name, keep the expo
screen open and the PC awake. Configuration: autopilot\\autopilot.ini.
"""

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from autopilot import config
from autopilot.pilot import Pilot
from autopilot.server import Server

HERE = Path(__file__).resolve().parent


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------ expo screen --

def find_browser(setting: str) -> str | None:
    if setting and setting.lower() != "auto":
        return setting
    for candidate in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(candidate).exists():
            return candidate
    return shutil.which("msedge") or shutil.which("chrome")


class Screen:
    """One full-screen kiosk browser window on one monitor. A private profile
    per window: no "restore pages?" bubbles, no sign-in prompts, and two
    instances that don't merge into one. Restarted if it ever closes."""

    def __init__(self, cfg: dict, url: str, position, name: str):
        self.cfg, self.url, self.position, self.name = cfg, url, position, name
        self.exe = find_browser(cfg["browser"])
        self.profile = HERE / f".browser-profile-{name}"
        self.proc = None
        self.launches: list[float] = []

    def args(self) -> list[str]:
        x, y = self.position
        return [self.exe, f"--user-data-dir={self.profile}",
                "--kiosk", self.url, "--edge-kiosk-type=fullscreen",
                f"--window-position={x},{y}", "--no-first-run",
                "--no-default-browser-check", "--disable-pinch",
                "--overscroll-history-navigation=0", "--disable-session-crashed-bubble",
                "--disable-features=Translate,msEdgeSidebarV2,msHubApps"]

    def keep_open(self) -> None:
        if not self.exe or (self.proc and self.proc.poll() is None):
            return
        now = time.monotonic()
        self.launches = [t for t in self.launches if now - t < 120]
        if len(self.launches) >= 4:  # it keeps exiting: don't spam windows
            return
        if self.launches:
            log(f"{self.name} screen closed — reopening")
        self.launches.append(now)
        self.proc = subprocess.Popen(self.args())

    def close(self) -> None:
        """Deliberate close (not a crash): the whole browser process tree."""
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc = None
        self.launches = []


# While Assetto Corsa is on the main monitor, the branding page must be gone
# (else AC may open BEHIND it); between runs it covers the bare desktop.
AC_PHASES = ("starting", "driving", "finished")


class MainScreenSim:
    """Hands the main monitor over between the HydroTeam page and AC with no
    Windows desktop in between:
      start: AC launches while the page stays up; as soon as AC has a window
             it is pulled in front, and the page only closes once AC is
             fully loaded (live), after which AC is pulled in front again.
      stop:  the page opens first and we wait until it is really on screen;
             only then AC is closed."""

    HANDOVER_TIMEOUT = 90

    def __init__(self, sim, main: Screen):
        self.sim, self.main = sim, main
        self._waiting = None
        self._fronted = False
        self._last_check = 0.0

    def start(self) -> None:
        self.sim.start()
        self._waiting, self._fronted = time.monotonic(), False

    def stop(self) -> None:
        from autopilot.sim import find_ac_window
        if self.sim.running():
            self.main.keep_open()
            x, y = self.cfg_main_point()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if find_ac_window("msedge.exe", (x, y)) or \
                        find_ac_window("chrome.exe", (x, y)):
                    break
                time.sleep(0.2)
            else:
                log("main screen did not appear within 10 s")
            time.sleep(1.5)  # let it paint
        self.sim.stop()
        self._waiting = None

    def cfg_main_point(self):
        x, y = self.main.position
        return x + 20, y + 20

    def poll(self) -> None:
        if self._waiting is None:
            return
        now = time.monotonic()
        if now - self._last_check < 0.25:
            return
        self._last_check = now
        from autopilot.sim import bring_to_front, find_ac_window
        hwnd = find_ac_window()
        if hwnd and not self._fronted:
            log("AC window is there — bringing it to the front")
            bring_to_front(hwnd)
            self._fronted = True
        tel = self.sim.telemetry() or {}
        if tel.get("live") or now - self._waiting > self.HANDOVER_TIMEOUT:
            self.main.close()
            hwnd = find_ac_window()
            if hwnd:
                time.sleep(0.3)
                bring_to_front(hwnd)
            log("AC loaded — HydroTeam screen closed" if tel.get("live")
                else "AC not live after 90 s — HydroTeam screen closed anyway")
            self._waiting = None

    def __getattr__(self, name):
        return getattr(self.sim, name)


def keep_awake() -> None:
    """No screensaver, no display sleep while the stand runs."""
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM, ES_DISPLAY = 0x80000000, 0x1, 0x2
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM | ES_DISPLAY)
    except Exception:
        pass


# ------------------------------------------------------------------ learn --

def learn(cfg: dict) -> None:
    """Print every wheel button and key press — to fill in [wheel] buttons."""
    from autopilot.inputs import WindowsInputs
    cfg = dict(cfg, lock=False, buttons=[], joystick=None)
    inputs = WindowsInputs(cfg, log=log)
    log("press wheel buttons / keys — Ctrl+C to stop")
    prev = {}
    while True:
        for jid, mask in inputs.read_buttons().items():
            rising = mask & ~prev.get(jid, mask)
            prev[jid] = mask
            for b in range(32):
                if rising & (1 << b):
                    log(f"controller {jid}: button {b + 1}   "
                        f"-> [wheel] joystick = {jid}, buttons = {b + 1}")
        for ev in inputs._keyboard_events():
            log(f"key: {ev}")
        time.sleep(0.03)


def where(cfg_path: Path) -> None:
    """Record where to click on AC's start menu: the next left click is
    written to autopilot.ini as [ac] start_click."""
    import ctypes
    import re
    from ctypes import wintypes
    u = ctypes.windll.user32
    log("Start nu een rit (knop op het stuur) en klik in Assetto Corsa op het")
    log("stuur-icoon linksboven. Die klik wordt opgeslagen. (max. 5 minuten)")
    while u.GetAsyncKeyState(0x01) & 0x8000:
        time.sleep(0.02)
    end = time.monotonic() + 300
    while time.monotonic() < end:
        if u.GetAsyncKeyState(0x01) & 0x8000:
            pt = wintypes.POINT()
            u.GetCursorPos(ctypes.byref(pt))
            text = cfg_path.read_text(encoding="utf-8-sig")
            line = f"start_click = {pt.x},{pt.y}"
            if re.search(r"(?m)^start_click\s*=.*$", text):
                text = re.sub(r"(?m)^start_click\s*=.*$", line, text)
            else:
                text = re.sub(r"(?m)^(session\s*=.*)$", r"\1\n" + line, text, count=1)
            cfg_path.write_text(text, encoding="utf-8")
            log(f"opgeslagen: {line}  — herstart de stand (STOP-STAND, START-STAND)")
            return
        time.sleep(0.02)
    log("geen klik gezien — niets veranderd")


# ------------------------------------------------------------------- main --

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="no AC, console as input")
    parser.add_argument("--learn", action="store_true", help="show button/key numbers")
    parser.add_argument("--where", action="store_true",
                        help="record the click on AC's start menu into autopilot.ini")
    parser.add_argument("--config", type=Path, default=HERE / "autopilot.ini")
    args = parser.parse_args()

    if not args.config.exists():
        sys.exit(f"Config not found: {args.config}\n"
                 "Copy autopilot.example.ini to autopilot.ini (or run windows\\install-fti.ps1).")
    cfg = config.load(args.config)
    windows = sys.platform == "win32"

    if args.where:
        if not windows:
            sys.exit("--where records a Windows mouse click.")
        where(args.config)
        return

    if args.learn:
        if not windows:
            sys.exit("--learn reads Windows controllers.")
        try:
            learn(cfg)
        except KeyboardInterrupt:
            return

    if not cfg["token"] or cfg["token"] == "CHANGE-ME":
        sys.exit("autopilot.ini: [server] token is empty — use API_TOKEN from .env.")
    if cfg["lock"] and not args.demo and cfg["admin_code"] in ("", "change-me"):
        sys.exit("autopilot.ini: set [keyboard] admin_code — without it nobody "
                 "can ever release the locked keyboard.")

    server = Server(cfg["url"], cfg["token"], log=log)
    if args.demo:
        from autopilot.inputs import ConsoleInputs
        from autopilot.sim import DemoSim
        sim, inputs = DemoSim(cfg, server, log=log), ConsoleInputs(cfg, log=log)
        screen = main = None
    else:
        if not windows:
            sys.exit("The real stand runs on Windows — on this OS use --demo.")
        from autopilot.inputs import WindowsInputs
        from autopilot.sim import RealSim
        sim = RealSim(cfg, log=log)
        problems = sim.check()
        if problems:
            sys.exit("Assetto Corsa setup problems:\n  - " + "\n  - ".join(problems))
        try:
            skins = sim.install_skins()
            if skins:
                log("livery installed in AC: " + ", ".join(skins))
        except OSError as exc:
            log(f"could not install the livery ({exc}) — AC uses its own skin")
        sim.stop()  # a leftover AC from before a restart
        inputs = WindowsInputs(cfg, log=log)
        screen = main = None
        if cfg["manage_browser"]:
            screen = Screen(cfg, cfg["screen_url"], cfg["position"], "board")
            if cfg["main_screen"]:
                main = Screen(cfg, cfg["main_url"], cfg["main_position"], "main")
                sim = MainScreenSim(sim, main)
        keep_awake()

    if not args.demo and not cfg["start_click"]:
        log("NOTE: [ac] start_click is empty — if AC opens on its start menu, "
            "run AC-KLIK-INSTELLEN once")
    elif cfg["start_click"]:
        log(f"will click AC's start menu at {cfg['start_click']}")
    pilot = Pilot(cfg, server, sim, inputs, log=log)
    log(f"autopilot ready — {cfg['car'] or 'demo car'} @ {cfg['track']}, "
        f"session {cfg['session']}")
    pilot._post(force=True)
    last_screen = 0.0
    try:
        while True:
            pilot.tick()
            if main:
                sim.poll()
            if time.monotonic() - last_screen > 1:
                if screen:
                    screen.keep_open()
                if main and pilot.phase not in AC_PHASES and sim._waiting is None:
                    main.keep_open()
                last_screen = time.monotonic()
            time.sleep(0.05)
    except KeyboardInterrupt:
        log("bye")
    finally:
        sim.stop()


if __name__ == "__main__":
    main()
