"""System information, reminders and memory."""
from __future__ import annotations

import datetime as dt
import shutil
import time

from ..paths import data_subdir
from .base import P, tool


@tool("Get the current date, time and weekday.")
def get_time(ctx):
    n = dt.datetime.now().astimezone()
    return n.strftime("%A, %d %B %Y, %H:%M:%S ") + (n.tzname() or "")


@tool("Report CPU, memory, disk and battery status of this PC.")
def system_info(ctx):
    import psutil
    out = [f"CPU {psutil.cpu_percent(interval=0.5)}% on {psutil.cpu_count()} threads",
           f"RAM {psutil.virtual_memory().percent}% of {psutil.virtual_memory().total / 2**30:.0f} GB"]
    d = shutil.disk_usage(__import__('os').path.abspath(__import__('os').sep))
    out.append(f"Disk {d.used / d.total * 100:.0f}% used, {d.free / 2**30:.0f} GB free")
    b = psutil.sensors_battery()
    if b:
        out.append(f"Battery {b.percent:.0f}%{' (charging)' if b.power_plugged else ''}")
    return "; ".join(out)


@tool("Remember a lasting fact about the user or their preferences (shown to you in every future conversation).",
      {"fact": P("string", "A short, self-contained fact")}, ["fact"], category="system")
def remember(ctx, fact: str):
    ctx.services["storage"].add_fact(fact.strip())
    return "OK: remembered"


@tool("Forget remembered facts containing the given text.", {"text": P("string", "Text to match")}, ["text"],
      category="system")
def forget(ctx, text: str):
    n = ctx.services["storage"].remove_facts(text)
    return f"OK: forgot {n} item(s)" if n else "Nothing matched."


@tool("Set a reminder. Give either minutes_from_now, or an absolute local time 'at' as 'YYYY-MM-DD HH:MM'.",
      {"text": P("string", "What to remind the user about"),
       "minutes_from_now": P("number", "Delay in minutes"),
       "at": P("string", "Local date-time, e.g. 2026-10-29 09:30")}, ["text"], category="system")
def set_reminder(ctx, text: str, minutes_from_now: float | None = None, at: str = ""):
    if minutes_from_now is not None:
        due = time.time() + float(minutes_from_now) * 60
    elif at:
        try:
            due = dt.datetime.strptime(at.strip().replace("T", " ")[:16], "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            return "ERROR: 'at' must look like 2026-10-29 09:30."
    else:
        return "ERROR: give minutes_from_now or at."
    if due <= time.time():
        return "ERROR: that time has already passed."
    rid = ctx.services["reminders"].add(text, due)
    return f"OK: reminder #{rid} set for {dt.datetime.fromtimestamp(due):%A %H:%M} ({text})"


@tool("List pending reminders.", category="system")
def list_reminders(ctx):
    rows = ctx.services["storage"].pending_reminders()
    return "\n".join(f"#{r.id} {dt.datetime.fromtimestamp(r.due):%Y-%m-%d %H:%M} - {r.text}" for r in rows) or "No pending reminders."


@tool("Cancel a reminder by its number.", {"id": P("integer", "Reminder number")}, ["id"], category="system")
def cancel_reminder(ctx, id: int):
    return "OK: cancelled" if ctx.services["storage"].finish_reminder(int(id)) else "ERROR: no such pending reminder."
