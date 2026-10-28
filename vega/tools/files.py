"""File and folder tools."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..paths import known_folder, resolve_path
from .base import P, tool

_SKIP = {"appdata", "node_modules", ".git", "$recycle.bin", "windows", "program files", "program files (x86)",
         "programdata", "__pycache__", ".venv", "venv"}
_TYPES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".ico"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".md"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv"},
    "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".msix", ".iso"},
    "Code": {".py", ".js", ".ts", ".lua", ".luau", ".rbxl", ".rbxlx", ".json", ".html", ".css", ".c", ".cpp", ".cs", ".java", ".bat", ".ps1"},
}


def _size(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def _open(p: Path):
    if sys.platform == "win32":
        os.startfile(str(p))
    else:
        subprocess.Popen(["xdg-open", str(p)])


@tool("Create a folder (and any missing parents). Paths may start with Desktop/, Documents/, Downloads/ or be absolute.",
      {"path": P("string", "Folder path, e.g. 'Desktop/My Project'")}, ["path"], category="files")
def create_folder(ctx, path: str):
    p = resolve_path(path)
    p.mkdir(parents=True, exist_ok=True)
    return f"OK: folder ready at {p}"


@tool("Create or overwrite a text file with the given content.",
      {"path": P("string", "File path"), "content": P("string", "Text to write"),
       "overwrite": P("boolean", "Replace the file if it exists")}, ["path"], category="files",
      confirm=lambda a: f"Overwrite {a['path']}?" if a.get("overwrite") and resolve_path(a["path"]).exists() else None)
def create_file(ctx, path: str, content: str = "", overwrite: bool = False):
    p = resolve_path(path)
    if p.exists() and not overwrite:
        return f"ERROR: {p} already exists (set overwrite=true to replace it)."
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} characters to {p}"


@tool("List files and folders in a directory.", {"path": P("string", "Directory path")}, ["path"], category="files")
def list_directory(ctx, path: str):
    p = resolve_path(path)
    if not p.is_dir():
        return f"ERROR: {p} is not a folder."
    rows = []
    for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:100]:
        try:
            rows.append(f"[dir] {e.name}" if e.is_dir() else f"{e.name}  ({_size(e.stat().st_size)})")
        except OSError:
            pass
    return "\n".join(rows) or "(empty)"


@tool("Search for files by name across Desktop, Documents, Downloads, Pictures, Videos, Music (or a given folder). "
      "All words in the query must appear in the file name. Newest first.",
      {"query": P("string", "Words from the file name"), "folder": P("string", "Optional folder to search in"),
       "max_results": P("integer", "Default 15")}, ["query"], category="files")
def find_files(ctx, query: str, folder: str = "", max_results: int = 15):
    words = [w for w in query.lower().split() if w]
    roots = [resolve_path(folder)] if folder else [known_folder(n) for n in
                                                    ("desktop", "documents", "downloads", "pictures", "videos", "music")]
    seen, hits, deadline = set(), [], time.time() + 20
    for root in roots:
        if str(root) in seen or not root.exists():
            continue
        seen.add(str(root))
        stack = [str(root)]
        while stack and time.time() < deadline and not ctx.cancel.is_set():
            d = stack.pop()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        n = e.name.lower()
                        if e.is_dir(follow_symlinks=False):
                            if n not in _SKIP:
                                stack.append(e.path)
                        if all(w in n for w in words):
                            hits.append(e.path)
            except OSError:
                continue
    def mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0
    hits = sorted(set(hits), key=mt, reverse=True)[: int(max_results)]
    if not hits:
        return f"No files found matching '{query}'."
    return "\n".join(f"{h}  ({time.strftime('%Y-%m-%d', time.localtime(mt(h)))})" for h in hits)


@tool("Open a file or folder with its default application (a folder opens in File Explorer).",
      {"path": P("string", "Path to open")}, ["path"], category="files")
def open_path(ctx, path: str):
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist."
    _open(p)
    return f"OK: opened {p}"


@tool("Open File Explorer with a file highlighted (or a folder shown).",
      {"path": P("string", "File or folder path")}, ["path"], category="files")
def reveal_in_explorer(ctx, path: str):
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist."
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{p}"] if p.is_file() else ["explorer", str(p)])
    else:
        _open(p.parent if p.is_file() else p)
    return f"OK: showing {p}"


@tool("Read a text file (first N characters).", {"path": P("string", "File path"),
                                                  "max_chars": P("integer", "Default 4000")}, ["path"], category="files")
def read_file(ctx, path: str, max_chars: int = 4000):
    p = resolve_path(path)
    if not p.is_file():
        return f"ERROR: {p} is not a file."
    raw = p.read_bytes()[: int(max_chars) * 4]
    if b"\x00" in raw[:2048]:
        return "ERROR: that looks like a binary file, I can only read text."
    return raw.decode("utf-8", errors="replace")[: int(max_chars)]


@tool("Copy a file or folder. Never overwrites; the copy gets a numbered name if needed.",
      {"source": P("string", "What to copy"), "destination": P("string", "Target folder or full target path")},
      ["source", "destination"], category="files")
def copy_path(ctx, source: str, destination: str):
    s, d = resolve_path(source), resolve_path(destination)
    if not s.exists():
        return f"ERROR: {s} does not exist."
    if d.is_dir():
        d = d / s.name
    n, base = 1, d
    while d.exists():
        d = base.with_name(f"{base.stem} ({n}){base.suffix}")
        n += 1
    shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
    return f"OK: copied to {d}"


@tool("Move or rename a file or folder.", {"source": P("string", "What to move"),
                                           "destination": P("string", "Target folder or full new path")},
      ["source", "destination"], category="files", confirm=lambda a: f"Move {a['source']} to {a['destination']}?")
def move_path(ctx, source: str, destination: str):
    s, d = resolve_path(source), resolve_path(destination)
    if not s.exists():
        return f"ERROR: {s} does not exist."
    if d.is_dir():
        d = d / s.name
    if d.exists():
        return f"ERROR: {d} already exists; not overwriting."
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return f"OK: moved to {d}"


@tool("Delete a file or folder by sending it to the Recycle Bin.", {"path": P("string", "What to delete")}, ["path"],
      category="files", confirm=lambda a: f"Send {a['path']} to the Recycle Bin?")
def delete_path(ctx, path: str):
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist."
    from send2trash import send2trash
    send2trash(str(p))
    return f"OK: {p} moved to the Recycle Bin"


@tool("Tidy a folder: move loose files into subfolders by type (Images, Documents, Videos, Audio, Archives, "
      "Installers, Code, Other). Top level only; nothing is overwritten.",
      {"folder": P("string", "Folder to organize, e.g. 'Downloads'")}, ["folder"], category="files",
      confirm=lambda a: f"Organize the files in {a['folder']} into subfolders by type?")
def organize_folder(ctx, folder: str):
    root = resolve_path(folder)
    if not root.is_dir():
        return f"ERROR: {root} is not a folder."
    counts: dict[str, int] = {}
    for f in [x for x in root.iterdir() if x.is_file() and not x.name.startswith(".")]:
        cat = next((c for c, exts in _TYPES.items() if f.suffix.lower() in exts), "Other")
        dest = root / cat
        dest.mkdir(exist_ok=True)
        target, n = dest / f.name, 1
        while target.exists():
            target = dest / f"{f.stem} ({n}){f.suffix}"
            n += 1
        shutil.move(str(f), str(target))
        counts[cat] = counts.get(cat, 0) + 1
    return "OK: " + (", ".join(f"{v} to {k}" for k, v in counts.items()) or "nothing to move")
