"""Keyboard, clipboard and screenshots (permission category: input)."""
from __future__ import annotations

import datetime as dt
import io
import time

from ..paths import known_folder
from . import winutil as W
from .base import P, tool

_KEYMAP = {"windows": "win", "super": "win", "control": "ctrl", "return": "enter", "escape": "esc", "del": "delete",
           "pgup": "pageup", "pgdn": "pagedown", "plus": "+"}


def _gui():
    import pyautogui
    pyautogui.FAILSAFE = True  # slam the mouse into a screen corner to abort
    pyautogui.PAUSE = 0.03
    return pyautogui


def paste_text(text: str) -> None:
    """Type arbitrary unicode by pasting, then restore the user's clipboard."""
    import pyperclip
    g = _gui()
    try:
        old = pyperclip.paste()
    except Exception:
        old = None
    pyperclip.copy(text)
    time.sleep(0.05)
    g.hotkey("ctrl", "v")
    time.sleep(0.15)
    if old is not None:
        try:
            pyperclip.copy(old)
        except Exception:
            pass


def press(combo: str) -> None:
    keys = [_KEYMAP.get(k.strip().lower(), k.strip().lower()) for k in combo.split("+") if k.strip()]
    _gui().hotkey(*keys)


@tool("Type text into whichever window currently has keyboard focus (use switch_to_app first if needed).",
      {"text": P("string", "Text to type"), "press_enter": P("boolean", "Press Enter afterwards")}, ["text"],
      category="input")
def type_text(ctx, text: str, press_enter: bool = False):
    paste_text(text)
    if press_enter:
        press("enter")
    return f"OK: typed {len(text)} characters"


@tool("Press a keyboard shortcut or key in the focused window, e.g. 'ctrl+t', 'alt+tab', 'win+d', 'enter', "
      "'ctrl+shift+esc'. Use commas for a sequence: 'ctrl+l, enter'.",
      {"keys": P("string", "Key combination(s)")}, ["keys"], category="input")
def press_keys(ctx, keys: str):
    for combo in keys.split(","):
        press(combo)
        time.sleep(0.12)
    return f"OK: pressed {keys}"


@tool("Read the current text on the clipboard.", category="input")
def get_clipboard(ctx):
    import pyperclip
    t = pyperclip.paste()
    return t if t else "(clipboard is empty or holds non-text)"


@tool("Put text on the clipboard.", {"text": P("string", "Text to copy")}, ["text"], category="input")
def set_clipboard(ctx, text: str):
    import pyperclip
    pyperclip.copy(text)
    return "OK: copied to clipboard"


@tool("Take a screenshot and save it to Pictures/Vega Screenshots. region: full (all monitors), or window "
      "(the app the user was just using). Optionally also copy it to the clipboard.",
      {"region": P("string", "full or window", enum=["full", "window"]),
       "copy_to_clipboard": P("boolean", "Also put the image on the clipboard")}, category="input")
def take_screenshot(ctx, region: str = "full", copy_to_clipboard: bool = False):
    import mss
    from PIL import Image
    with mss.mss() as sct:
        box = sct.monitors[0]
        if region == "window":
            w = W.last_external_window()
            if w:
                import win32gui
                l, t, r, b = win32gui.GetWindowRect(w.hwnd)
                box = {"left": l, "top": t, "width": r - l, "height": b - t}
        shot = sct.grab(box)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    folder = known_folder("pictures") / "Vega Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{dt.datetime.now():%Y%m%d_%H%M%S}.png"
    img.save(path)
    if copy_to_clipboard and W.IS_WIN:
        import win32clipboard
        buf = io.BytesIO()
        img.save(buf, "BMP")
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, buf.getvalue()[14:])
        finally:
            win32clipboard.CloseClipboard()
    return f"OK: screenshot saved to {path}"


@tool("Change the system volume or mute. action: up, down, mute (toggle). steps = how many presses (each ~2%).",
      {"action": P("string", "up, down or mute", enum=["up", "down", "mute"]), "steps": P("integer", "Default 5")},
      ["action"], category="input")
def volume(ctx, action: str, steps: int = 5):
    g = _gui()
    key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}[action]
    for _ in range(1 if action == "mute" else max(1, min(50, int(steps)))):
        g.press(key)
    return f"OK: volume {action}"


@tool("Control media playback in whatever is playing: playpause, next, previous.",
      {"action": P("string", "Media key", enum=["playpause", "next", "previous"])}, ["action"], category="input")
def media(ctx, action: str):
    _gui().press({"playpause": "playpause", "next": "nexttrack", "previous": "prevtrack"}[action])
    return f"OK: {action}"
