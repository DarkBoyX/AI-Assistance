"""Run approved scripts and (confirmed) commands, install software with winget."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys

from ..paths import data_subdir
from .base import P, tool

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
# Things an assistant must never do, even if the user clicks Allow.
_FORBIDDEN = re.compile(
    r"(set-mppreference|disable-?realtime|disablerealtimemonitoring|add-mppreference.*exclusion|enablelua|"
    r"consentpromptbehavior|bcdedit|vssadmin\s+delete|cipher\s+/w|format\s+[a-z]:|"
    r"net\s+user\s+\S+\s+\S+\s*/add|reg\s+(add|delete).*\\(policies|windows defender)|"
    r"(invoke-webrequest|iwr|curl|wget)[^|;]*\|\s*(iex|invoke-expression)|-encodedcommand)", re.I)


def scripts_dir():
    return data_subdir("scripts")


@tool("Run a PowerShell or cmd command and return its output. ALWAYS asks the user to approve the exact command.",
      {"command": P("string", "The command"), "shell": P("string", "powershell or cmd", enum=["powershell", "cmd"]),
       "timeout": P("integer", "Seconds, default 30")}, ["command"], category="commands",
      confirm=lambda a: f"Run this {a.get('shell', 'powershell')} command?  {a['command']}")
def run_command(ctx, command: str, shell: str = "powershell", timeout: int = 30):
    if _FORBIDDEN.search(command):
        return "ERROR: that command touches security protections or is on the blocked list; I won't run it."
    argv = (["powershell", "-NoProfile", "-NonInteractive", "-Command", command] if shell == "powershell"
            else ["cmd", "/c", command])
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=max(1, min(int(timeout), 300)), creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return "ERROR: the command timed out."
    out = (r.stdout + ("\n" + r.stderr if r.stderr.strip() else "")).strip()
    return f"{'OK' if r.returncode == 0 else 'ERROR'} (exit {r.returncode})\n{out}"[:5000]


@tool("List the approved scripts in the Vega scripts folder (.ps1, .bat, .cmd, .py).", category="commands")
def list_scripts(ctx):
    names = sorted(p.name for p in scripts_dir().iterdir() if p.suffix.lower() in (".ps1", ".bat", ".cmd", ".py"))
    return "\n".join(names) or f"No scripts yet. Put them in {scripts_dir()}"


@tool("Run an approved script from the Vega scripts folder (asks the user first).",
      {"name": P("string", "Script file name"), "args": P("string", "Arguments")}, ["name"], category="commands",
      confirm=lambda a: f"Run the script {a['name']} {a.get('args', '')}?")
def run_script(ctx, name: str, args: str = ""):
    p = (scripts_dir() / name).resolve()
    if p.parent != scripts_dir().resolve() or not p.is_file():
        return "ERROR: only scripts inside the Vega scripts folder can be run (see list_scripts)."
    ext = p.suffix.lower()
    if ext == ".ps1":
        argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "RemoteSigned", "-File", str(p)]
    elif ext in (".bat", ".cmd"):
        argv = ["cmd", "/c", str(p)]
    elif ext == ".py":
        py = shutil.which("python") or shutil.which("py")
        if not py:
            return "ERROR: Python isn't on PATH."
        argv = [py, str(p)]
    else:
        return "ERROR: unsupported script type."
    try:
        r = subprocess.run(argv + (args.split() if args else []), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120, creationflags=NO_WINDOW, cwd=str(p.parent))
    except subprocess.TimeoutExpired:
        return "ERROR: the script timed out after 120 seconds."
    return f"{'OK' if r.returncode == 0 else 'ERROR'} (exit {r.returncode})\n{(r.stdout + r.stderr).strip()}"[:5000]


@tool("Search for installable software with winget.", {"query": P("string", "Software name")}, ["query"],
      category="commands")
def search_software(ctx, query: str):
    r = subprocess.run(["winget", "search", query, "--accept-source-agreements"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, creationflags=NO_WINDOW)
    return (r.stdout or r.stderr).strip()[-3000:]


@tool("Install software with winget in a visible window (Windows may show its own UAC prompt, which the user answers). "
      "ALWAYS asks the user first.", {"package": P("string", "winget package id (preferred) or exact name")},
      ["package"], category="commands", confirm=lambda a: f"Install {a['package']} using winget?")
def install_software(ctx, package: str):
    if not shutil.which("winget"):
        return "ERROR: winget isn't available on this PC."
    if not re.fullmatch(r"[\w .+\-]+", package):
        return "ERROR: invalid package name."
    subprocess.Popen(["winget", "install", package, "--accept-source-agreements", "--accept-package-agreements"],
                     creationflags=NEW_CONSOLE)
    return f"OK: installation of {package} started in a new window."
