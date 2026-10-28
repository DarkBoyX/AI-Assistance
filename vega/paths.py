"""Filesystem locations and Windows known-folder helpers."""
from __future__ import annotations

import ctypes
import os
import sys
import uuid
from pathlib import Path

APP_NAME = "Vega"


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(str(Path.home()), ".config")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_subdir(name: str) -> Path:
    p = app_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_path(rel: str) -> Path:
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
    return Path(base) / rel


_KF = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-83DAA02FCD58",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


def known_folder(name: str) -> Path:
    """Real location of Desktop/Documents/... (honours OneDrive redirection)."""
    name = name.lower()
    if sys.platform == "win32" and name in _KF:
        try:
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            u = uuid.UUID(_KF[name])
            g = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
            buf = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(buf)) == 0:
                path = buf.value
                ctypes.windll.ole32.CoTaskMemFree(buf)
                if path:
                    return Path(path)
        except Exception:
            pass
    return Path.home() / name.capitalize()


_ALIASES = {"desktop": "desktop", "documents": "documents", "docs": "documents", "my documents": "documents",
            "downloads": "downloads", "pictures": "pictures", "photos": "pictures", "music": "music",
            "videos": "videos", "home": "home"}


def resolve_path(text: str) -> Path:
    """'Desktop/Projects', '~/x', '%USERPROFILE%\\y' or absolute -> Path. Relative paths are under home."""
    t = os.path.expandvars(str(text).strip().strip("\"'"))
    if t.startswith("~"):
        return Path(t).expanduser()
    parts = t.replace("\\", "/").split("/")
    head = parts[0].lower()
    if head in _ALIASES:
        base = Path.home() if _ALIASES[head] == "home" else known_folder(_ALIASES[head])
        return base.joinpath(*[p for p in parts[1:] if p])
    p = Path(t)
    return p if p.is_absolute() or (len(t) > 1 and t[1] == ":") else Path.home() / p
