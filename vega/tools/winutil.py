"""Thin, lazy wrappers around pywin32 so the rest of the code imports cleanly on any OS."""
from __future__ import annotations

import ctypes
import difflib
import os
import re
import sys
import threading
import time
from dataclasses import dataclass

IS_WIN = sys.platform == "win32"
_SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}
_last_external: int | None = None


def require_windows():
    if not IS_WIN:
        raise RuntimeError("This action only works on Windows.")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def score(query: str, name: str) -> float:
    q, n = norm(query), norm(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if n.startswith(q) or q.startswith(n):
        return 0.92
    if q in n or set(q.split()) <= set(n.split()):
        return 0.85
    return difflib.SequenceMatcher(None, q, n).ratio() * 0.8


@dataclass
class WinInfo:
    hwnd: int
    title: str
    pid: int
    exe: str


def list_windows() -> list[WinInfo]:
    require_windows()
    import psutil
    import win32con
    import win32gui
    import win32process

    out: list[WinInfo] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or title in ("Program Manager", "Windows Input Experience"):
            return
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return
        try:  # skip "cloaked" UWP ghosts
            c = ctypes.c_int(0)
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(c), ctypes.sizeof(c))
            if c.value:
                return
        except Exception:
            pass
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == os.getpid():
            return
        try:
            exe = psutil.Process(pid).name()
        except Exception:
            exe = ""
        out.append(WinInfo(hwnd, title, pid, exe))

    win32gui.EnumWindows(cb, None)
    return out


def find_window(query: str) -> WinInfo | None:
    best, best_s = None, 0.0
    for w in list_windows():
        stem = os.path.splitext(w.exe)[0]
        s = max(score(query, w.title), score(query, stem), 0.9 * (norm(query) in norm(w.title)))
        if s > best_s:
            best, best_s = w, s
    return best if best_s >= 0.6 else None


def focus(hwnd: int) -> None:
    require_windows()
    import win32api
    import win32con
    import win32gui
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32api.keybd_event(0x12, 0, 0, 0)  # tap ALT so Windows allows the focus change
    win32api.keybd_event(0x12, 0, 2, 0)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(hwnd)


def close_window(hwnd: int) -> None:
    import win32con
    import win32gui
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)  # graceful: app may ask to save


def window_title(hwnd: int) -> str:
    import win32gui
    return win32gui.GetWindowText(hwnd)


def last_external_window() -> WinInfo | None:
    """The window the user was in before talking to the assistant."""
    if not IS_WIN or not _last_external:
        return None
    for w in list_windows():
        if w.hwnd == _last_external:
            return w
    return None


def start_foreground_tracker() -> None:
    if not IS_WIN:
        return

    def loop():
        global _last_external
        import win32gui
        import win32process
        while True:
            try:
                h = win32gui.GetForegroundWindow()
                if h and win32gui.GetClassName(h) not in _SKIP_CLASSES and win32gui.GetWindowText(h):
                    if win32process.GetWindowThreadProcessId(h)[1] != os.getpid():
                        _last_external = h
            except Exception:
                pass
            time.sleep(0.4)

    threading.Thread(target=loop, daemon=True, name="fg-tracker").start()
