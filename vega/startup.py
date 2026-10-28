"""Start-with-Windows (HKCU Run key) and desktop shortcut creation."""
from __future__ import annotations

import sys
from pathlib import Path

from .paths import known_folder, resource_path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_target() -> tuple[str, str, str]:
    """(exe, args, working_dir) that start this app, packaged or from source."""
    if getattr(sys, "frozen", False):
        return sys.executable, "", str(Path(sys.executable).parent)
    root = Path(__file__).resolve().parent.parent
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return str(pyw if pyw.exists() else sys.executable), f'"{root / "main.py"}"', str(root)


def set_start_with_windows(enable: bool, minimized: bool = True) -> None:
    if sys.platform != "win32":
        return
    import winreg
    exe, args, _ = launch_target()
    cmd = f'"{exe}" {args} {"--minimized" if minimized else ""}'.strip()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enable:
            winreg.SetValueEx(k, "Vega", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, "Vega")
            except FileNotFoundError:
                pass


def create_desktop_shortcut() -> str:
    if sys.platform != "win32":
        raise RuntimeError("Shortcuts are only supported on Windows.")
    import win32com.client
    exe, args, cwd = launch_target()
    path = known_folder("desktop") / "Vega.lnk"
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortCut(str(path))
    sc.TargetPath, sc.Arguments, sc.WorkingDirectory = exe, args, cwd
    ico = resource_path("assets/vega.ico")
    sc.IconLocation = str(ico) if ico.exists() else exe
    sc.Description = "Vega - personal AI assistant"
    sc.save()
    return str(path)
