"""autopilot.ini -> one flat dict. Every key has a default except the ones
that must be site-specific (token, car, admin code)."""

import configparser
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _xy(raw: str):
    """'960,540' -> (960, 540); anything else -> None."""
    parts = raw.replace(" ", "").split(",")
    if len(parts) == 2 and all(p.lstrip("-").isdigit() for p in parts):
        return int(parts[0]), int(parts[1])
    return None


def load(path: Path) -> dict:
    cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
    # utf-8-sig: Windows PowerShell writes a BOM; plain utf-8 chokes on it.
    cp.read(path, encoding="utf-8-sig")

    def s(sec, key, default=""):
        return cp.get(sec, key, fallback=default).strip()

    def i(sec, key, default):
        try:
            return int(cp.get(sec, key, fallback=str(default)).strip() or default)
        except ValueError:
            return default

    def ints(sec, key):
        raw = s(sec, key)
        return [int(p) for p in raw.replace(" ", "").split(",") if p.isdigit()]

    pos = s("screen", "position", "1920,0").replace(" ", "").split(",")
    main_pos = _xy(s("screen", "main_position", "0,0")) or (0, 0)
    return {
        "url": s("server", "url", "http://127.0.0.1:8088").rstrip("/"),
        "token": s("server", "token"),

        "ac_dir": s("ac", "install_dir",
                    r"C:\Program Files (x86)\Steam\steamapps\common\assettocorsa"),
        "cfg_dir": s("ac", "cfg_dir"),
        "car": s("ac", "car"),
        "skin": s("ac", "skin"),
        "track": s("ac", "track", "spa"),
        "track_config": s("ac", "track_config"),
        "session": s("ac", "session", "hotlap").lower(),
        "start_click": _xy(s("ac", "start_click")),
        "start_click_delay": i("ac", "start_click_delay", 3),

        "assists": {
            "auto_shifter": i("assists", "auto_shifter", 1),
            "auto_clutch": i("assists", "auto_clutch", 1),
            "auto_blip": i("assists", "auto_blip", 1),
            "abs": i("assists", "abs", 1),
            "traction_control": i("assists", "traction_control", 1),
            "stability": i("assists", "stability", 0),
            "ideal_line": i("assists", "ideal_line", 0),
            "damage": i("assists", "damage", 0),
        },
        "weather": s("conditions", "weather", "3_clear"),
        "ambient": i("conditions", "ambient", 22),
        "road": i("conditions", "road", 28),
        "sun_angle": i("conditions", "sun_angle", 16),

        "start_timeout": i("run", "start_timeout", 120),
        "max_run": i("run", "max_run", 420),
        "idle_abort": i("run", "idle_abort", 45),
        "finish_hold": i("run", "finish_hold", 5),
        "name_timeout": i("run", "name_timeout", 90),
        "result": i("run", "result", 25),
        "result_min": i("run", "result_min", 6),
        "message": i("run", "message", 8),

        "joystick": (int(s("wheel", "joystick")) if s("wheel", "joystick").isdigit()
                     else None),
        "buttons": ints("wheel", "buttons"),

        "lock": i("keyboard", "lock", 1) == 1,
        "admin_code": s("keyboard", "admin_code").lower(),
        "admin_minutes": i("keyboard", "admin_minutes", 10),
        "start_key": s("keyboard", "start_key").upper(),

        "manage_browser": i("screen", "manage_browser", 1) == 1,
        "browser": s("screen", "browser", "auto"),
        "screen_url": s("screen", "url", "http://127.0.0.1:8088/expo"),
        "main_screen": i("screen", "main_screen", 1) == 1,
        "main_url": s("screen", "main_url", "http://127.0.0.1:8088/expo/main"),
        "main_position": main_pos,
        "position": (int(pos[0]), int(pos[1])) if len(pos) == 2
                    and all(p.lstrip("-").isdigit() for p in pos) else (1920, 0),
    }
