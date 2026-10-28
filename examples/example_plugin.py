"""Drop a file like this into %APPDATA%\Vega\plugins\ (Settings > Startup & data > Plugins folder) and restart.
Every function decorated with @tool becomes something the assistant can call."""
from vega.tools import P, tool


@tool("Roll a die with the given number of sides.", {"sides": P("integer", "Number of sides, default 6")},
      category="system")          # category: apps/files/web/input/messaging/commands are switchable in Settings
def roll_die(ctx, sides: int = 6):
    import random
    return f"OK: rolled {random.randint(1, int(sides))}"


@tool("Wipe a scratch folder.", {"path": P("string", "Folder")}, ["path"], category="files",
      confirm=lambda a: f"Really wipe {a['path']}?")      # confirm=... makes Vega ask the user first
def wipe(ctx, path: str):
    return "OK: (example only)"
