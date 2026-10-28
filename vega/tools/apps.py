"""Open, switch, close and manage applications."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from . import winutil as W
from .base import P, tool

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ALIASES = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe", "file explorer": "explorer.exe",
    "explorer": "explorer.exe", "windows explorer": "explorer.exe", "task manager": "taskmgr.exe",
    "command prompt": "cmd.exe", "cmd": "cmd.exe", "powershell": "powershell.exe", "paint": "mspaint.exe",
    "control panel": "control.exe", "settings": "ms-settings:", "windows settings": "ms-settings:",
}
_cache: dict = {"t": 0.0, "apps": []}


def _start_menu_dirs():
    return [os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]


def installed_apps(refresh: bool = False) -> list[dict]:
    """Everything in the Start menu (classic + Store apps): [{'name', 'id'|'path'}]."""
    if not refresh and _cache["apps"] and time.time() - _cache["t"] < 600:
        return _cache["apps"]
    apps: list[dict] = []
    try:
        ps = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30,
                             creationflags=NO_WINDOW).stdout
        data = json.loads(out) if out.strip() else []
        data = [data] if isinstance(data, dict) else data
        apps += [{"name": d["Name"], "id": d["AppID"]} for d in data if d.get("Name") and d.get("AppID")]
    except Exception:
        pass
    for base in _start_menu_dirs():
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk"):
                    apps.append({"name": f[:-4], "path": os.path.join(root, f)})
    _cache.update(t=time.time(), apps=apps)
    return apps


def _best_app(query: str):
    scored = []
    for a in installed_apps():
        s = W.score(query, a["name"]) - (0.3 if "uninstall" in a["name"].lower() else 0) + (0.01 if "id" in a else 0)
        scored.append((s, a))
    scored.sort(key=lambda x: -x[0])
    return scored


def _app_paths_registry(name: str) -> str | None:
    if not W.IS_WIN:
        return None
    import winreg
    exe = name if name.lower().endswith(".exe") else name + ".exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                return winreg.QueryValue(k, None)
        except OSError:
            continue
    return None


def launch_app(name: str) -> str:
    """Returns a description of what was launched or raises RuntimeError."""
    W.require_windows()
    n = W.norm(name)
    if n in _ALIASES:
        os.startfile(_ALIASES[n])
        return name
    scored = _best_app(name)
    if scored and scored[0][0] >= 0.6:
        a = scored[0][1]
        if "id" in a:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{a['id']}"])
        else:
            os.startfile(a["path"])
        return a["name"]
    exe = shutil.which(name) or _app_paths_registry(name)
    if exe:
        subprocess.Popen([exe])
        return exe
    close = ", ".join(dict.fromkeys(a["name"] for _, a in scored[:5]))
    raise RuntimeError(f"no installed app matches '{name}'. Closest: {close or 'none found'}")


@tool("Launch an installed Windows application by name, e.g. Chrome, Roblox Studio, Discord, Notepad, Spotify.",
      {"name": P("string", "Application name")}, ["name"], category="apps")
def open_app(ctx, name: str):
    return f"OK: launched {launch_app(name)}"


@tool("List the windows currently open on the desktop (title and program).", category="apps")
def list_open_windows(ctx):
    W.require_windows()
    ws = W.list_windows()
    return "\n".join(f"{w.title}  [{w.exe}]" for w in ws) or "No visible windows."


@tool("Bring an already-open application window to the front (switch to it). Matches window title or program name.",
      {"name": P("string", "Part of the window title or the program name, e.g. 'chrome', 'discord'")},
      ["name"], category="apps")
def switch_to_app(ctx, name: str):
    W.require_windows()
    w = W.find_window(name)
    if not w:
        return f"ERROR: no open window matches '{name}'. Use open_app to launch it."
    W.focus(w.hwnd)
    return f"OK: switched to '{w.title}'"


def _confirm_force(a):
    return f"Force-quit {a.get('name') or 'the current application'}? Unsaved work will be lost." if a.get("force") else None


@tool("Close an application window. With no name, closes the window the user was last using (the 'current' app). "
      "A normal close lets the app ask to save; force=true kills the process (needs confirmation).",
      {"name": P("string", "Window title/program to close; empty = the application the user was just using"),
       "force": P("boolean", "Kill the process instead of closing politely")}, category="apps", confirm=_confirm_force)
def close_app(ctx, name: str = "", force: bool = False):
    W.require_windows()
    w = W.find_window(name) if name else W.last_external_window()
    if not w:
        return "ERROR: couldn't find that window." if name else "ERROR: I don't know which window you mean; say its name."
    if force:
        import psutil
        psutil.Process(w.pid).terminate()
        return f"OK: terminated {w.exe}"
    W.close_window(w.hwnd)
    return f"OK: asked '{w.title}' to close"


@tool("Minimize, maximize or restore a window. With no name, uses the window the user was just using.",
      {"action": P("string", "What to do", enum=["minimize", "maximize", "restore"]),
       "name": P("string", "Window title/program; empty = current app")}, ["action"], category="apps")
def window_action(ctx, action: str, name: str = ""):
    W.require_windows()
    import win32con
    import win32gui
    w = W.find_window(name) if name else W.last_external_window()
    if not w:
        return "ERROR: couldn't find that window."
    cmd = {"minimize": win32con.SW_MINIMIZE, "maximize": win32con.SW_MAXIMIZE, "restore": win32con.SW_RESTORE}[action]
    win32gui.ShowWindow(w.hwnd, cmd)
    return f"OK: {action}d '{w.title}'"
