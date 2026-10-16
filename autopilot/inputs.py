"""What the visitor can touch: the wheel's buttons and the keyboard.

WindowsInputs
  - Keyboard: a low-level hook (WH_KEYBOARD_LL) sees every key before any
    window does. While locked it swallows ALL of them — Alt+Tab, Alt+F4, the
    Windows key, Esc, Ctrl+Shift+Esc never reach Windows — and hands the
    autopilot only what a name needs. Ctrl+Alt+Del and Win+L are handled by
    Windows itself below any hook; windows\\lockdown.ps1 disables what they
    offer.
  - Wheel: winmm joyGetPosEx, polled. No extra dependencies; works for any
    DirectInput wheel/button box (buttons 1–32).

ConsoleInputs (--demo, any OS): Enter on an empty line = the wheel button,
any text + Enter = typed into the name.

Both produce the same events: ("button",), ("char", c), ("backspace",),
("enter",).
"""

import queue
import sys
import threading
import time

NAME_PUNCT = " -.'"


def name_char(c: str) -> bool:
    return len(c) == 1 and (c.isalnum() or c in NAME_PUNCT)


VK_NAMES = {f"F{i}": 0x6F + i for i in range(1, 13)}
VK_NAMES.update({"PAUSE": 0x13, "SCROLL": 0x91, "INSERT": 0x2D, "HOME": 0x24})


class WindowsInputs:
    def __init__(self, cfg: dict, log=print):
        self.cfg, self.log = cfg, log
        self.locked = cfg["lock"]
        self._relock_at = None
        self._keys: queue.Queue = queue.Queue()
        self._shift = set()
        self._caps = False
        self._start_vk = VK_NAMES.get(cfg["start_key"]) if cfg["start_key"] else None
        self._prev_buttons: dict[int, int] = {}
        self._joy_ids = None
        self._joy_rescan = 0.0
        self._setup_joystick()
        threading.Thread(target=self._hook_thread, daemon=True,
                         name="keyboard-hook").start()

    # ---------------------------------------------------------- keyboard --
    def _hook_thread(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int,
                                      wintypes.WPARAM, wintypes.LPARAM)

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC,
                                             wintypes.HINSTANCE, wintypes.DWORD)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int,
                                          wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = LRESULT
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        LLKHF_INJECTED, LLKHF_UP = 0x10, 0x80

        def proc(n_code, w_param, l_param):
            if n_code == 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if kb.flags & LLKHF_INJECTED:  # synthetic (ours): let it through
                    return user32.CallNextHookEx(None, n_code, w_param, l_param)
                # Decide fast (Windows drops slow hooks); translate later.
                self._keys.put((kb.vkCode, kb.scanCode, not kb.flags & LLKHF_UP))
                if self.locked:
                    return 1  # swallowed: no window ever sees this key
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)  # keep a reference: GC'd callbacks crash
        hook = user32.SetWindowsHookExW(13, self._proc,  # WH_KEYBOARD_LL
                                        kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self.log(f"KEYBOARD HOOK FAILED (error {ctypes.get_last_error()}) — "
                     "the keyboard is NOT locked")
            return
        self.log("keyboard hook active" + (" — keyboard locked" if self.locked else ""))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _translate(self, vk: int, scan: int) -> str:
        """vk -> character on the PC's own layout (AZERTY!), with our own
        shift/caps state: swallowed keys never update Windows' key state."""
        import ctypes
        state = (ctypes.c_ubyte * 256)()
        if self._shift:
            state[0x10] = 0x80
        if self._caps:
            state[0x14] = 0x01
        buf = ctypes.create_unicode_buffer(8)
        user32 = ctypes.windll.user32
        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        user32.ToUnicodeEx.argtypes = (ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                       ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint,
                                       ctypes.c_void_p)
        layout = user32.GetKeyboardLayout(0)
        # wFlags 4: don't disturb the dead-key state of the real keyboard.
        n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 4, layout)
        return buf.value[:n] if n == 1 else ""

    def _keyboard_events(self) -> list:
        out = []
        while True:
            try:
                vk, scan, down = self._keys.get_nowait()
            except queue.Empty:
                return out
            if vk in (0x10, 0xA0, 0xA1):           # shift
                (self._shift.add if down else self._shift.discard)(vk)
                continue
            if not down:
                continue
            if vk == 0x14:                          # caps lock
                self._caps = not self._caps
            elif vk == 0x08:
                out.append(("backspace",))
            elif vk == 0x0D:
                out.append(("enter",))
            elif self._start_vk and vk == self._start_vk:
                out.append(("button",))
            else:
                c = self._translate(vk, scan)
                if name_char(c):
                    out.append(("char", c))

    def unlock(self, seconds: float) -> None:
        self.locked = False
        self._relock_at = time.monotonic() + seconds

    def lock(self) -> None:
        self.locked = self.cfg["lock"]
        self._relock_at = None

    # ------------------------------------------------------------- wheel --
    def _setup_joystick(self) -> None:
        import ctypes
        from ctypes import wintypes

        class JOYINFOEX(ctypes.Structure):
            _fields_ = [(n, wintypes.DWORD) for n in (
                "dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos",
                "dwUpos", "dwVpos", "dwButtons", "dwButtonNumber", "dwPOV",
                "dwReserved1", "dwReserved2")]

        self._winmm = ctypes.WinDLL("winmm")
        self._JOYINFOEX = JOYINFOEX

    def read_buttons(self) -> dict[int, int]:
        """{joystick id: button bitmask} for every connected controller."""
        import ctypes
        now = time.monotonic()
        ids = range(16) if self._joy_ids is None or now > self._joy_rescan \
            else self._joy_ids
        out, found = {}, []
        for jid in ids:
            info = self._JOYINFOEX()
            info.dwSize = ctypes.sizeof(info)
            info.dwFlags = 0x80  # JOY_RETURNBUTTONS
            if self._winmm.joyGetPosEx(jid, ctypes.byref(info)) == 0:
                out[jid] = info.dwButtons
                found.append(jid)
        if self._joy_ids is None or now > self._joy_rescan:
            self._joy_ids, self._joy_rescan = found, now + 10  # replugs show up
        return out

    def _button_events(self) -> list:
        out = []
        for jid, mask in self.read_buttons().items():
            prev = self._prev_buttons.get(jid, mask)
            self._prev_buttons[jid] = mask
            if self.cfg["joystick"] is not None and jid != self.cfg["joystick"]:
                continue
            rising = mask & ~prev
            if not rising:
                continue
            wanted = self.cfg["buttons"]
            if not wanted or any(rising & (1 << (b - 1)) for b in wanted):
                out.append(("button",))
        return out

    # ------------------------------------------------------------------ --
    def poll(self) -> list:
        if self._relock_at and time.monotonic() > self._relock_at:
            self.lock()
            self.log("ADMIN: time is up — keyboard locked again")
        return self._keyboard_events() + self._button_events()


class ConsoleInputs:
    """--demo: the console stands in for wheel and keyboard."""

    def __init__(self, cfg: dict, log=print):
        self.cfg, self.log = cfg, log
        self.locked = True
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        log("DEMO input: press Enter = wheel button; type a name + Enter = name")

    def _read(self) -> None:
        for line in sys.stdin:
            line = line.rstrip("\r\n")
            if not line:
                self._q.put(("button",))
                self._q.put(("enter",))
                continue
            for c in line:
                if name_char(c):
                    self._q.put(("char", c))
            self._q.put(("enter",))

    def unlock(self, seconds: float) -> None:
        self.locked = False

    def lock(self) -> None:
        self.locked = True

    def poll(self) -> list:
        out = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                return out
