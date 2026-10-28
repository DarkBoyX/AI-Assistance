"""Messaging apps, driven through their real desktop UI (keyboard automation of YOUR logged-in client).

No tokens, no unofficial APIs. Always requires confirmation before anything is sent.
"""
from __future__ import annotations

import time

from . import winutil as W
from .apps import launch_app
from .base import P, tool
from .input_tools import paste_text, press
from .web import open_url

# search shortcut = keyboard shortcut that focuses the app's "find a conversation" box
_APPS = {
    "discord": {"launch": "Discord", "search": "ctrl+k", "title": "discord", "home": "discord://-/channels/@me"},
    "slack": {"launch": "Slack", "search": "ctrl+k", "title": "slack"},
    "whatsapp": {"launch": "WhatsApp", "search": "ctrl+f", "title": "whatsapp", "home": "whatsapp://"},
    "teams": {"launch": "Microsoft Teams", "search": "ctrl+e", "title": "teams"},
    "telegram": {"launch": "Telegram", "search": "ctrl+f", "title": "telegram"},
}


def _front(app: str, wait: float = 6.0):
    cfg = _APPS[app]
    w = W.find_window(cfg["title"])
    if not w:
        launch_app(cfg["launch"])
        end = time.time() + wait * 2
        while time.time() < end and not w:
            time.sleep(0.5)
            w = W.find_window(cfg["title"])
    if not w:
        raise RuntimeError(f"couldn't get a {app} window; is it installed and logged in?")
    W.focus(w.hwnd)
    time.sleep(0.6)


@tool("Open a messaging app and show the user's messages/conversations. app: discord, slack, whatsapp, teams, telegram.",
      {"app": P("string", "Messaging app", enum=list(_APPS))}, ["app"], category="messaging")
def open_messages(ctx, app: str):
    app = app.lower()
    if app not in _APPS:
        return f"ERROR: unsupported app. Supported: {', '.join(_APPS)}."
    cfg = _APPS[app]
    if cfg.get("home") and app == "discord":
        open_url(ctx, cfg["home"])  # deep-link straight to Direct Messages
        time.sleep(1.0)
    else:
        _front(app)
    return f"OK: opened {app} messages"


@tool("Send a message to a person/channel in a desktop messaging app by searching for them in the app's quick "
      "switcher and typing the text. The user always confirms first. Best effort - tell the user to glance at the app.",
      {"app": P("string", "discord, slack, whatsapp, teams or telegram", enum=list(_APPS)),
       "recipient": P("string", "Contact, DM or channel name to search for"),
       "text": P("string", "Message text")}, ["app", "recipient", "text"], category="messaging",
      confirm=lambda a: f"Send \"{a['text']}\" to {a['recipient']} on {a['app'].title()}?")
def send_message(ctx, app: str, recipient: str, text: str):
    app = app.lower()
    if app not in _APPS:
        return f"ERROR: unsupported app. Supported: {', '.join(_APPS)}."
    _front(app)
    press(_APPS[app]["search"])
    time.sleep(0.5)
    paste_text(recipient)
    time.sleep(1.2)  # let search results populate
    press("enter")
    time.sleep(0.9)
    paste_text(text)
    time.sleep(0.2)
    press("enter")
    return f"OK: sent your message to '{recipient}' on {app}. (Sent via the app's own UI; verify on screen.)"
