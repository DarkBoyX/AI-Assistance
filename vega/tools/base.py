"""Tool framework. Add a tool anywhere with the @tool decorator - see README 'Writing tools'."""
from __future__ import annotations

import inspect
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

PERMISSION_CATEGORIES = {"apps", "files", "web", "input", "messaging", "commands"}
MAX_RESULT = 6000


def P(type_: str, description: str, **extra) -> dict:
    """Shorthand for a JSON-schema property."""
    return {"type": type_, "description": description, **extra}


class ToolContext:
    """Passed to every tool. `confirm` blocks until the user allows/denies."""

    def __init__(self, settings, confirm: Callable[[str, str], bool], cancel: threading.Event | None = None,
                 services: dict | None = None):
        self.settings, self._confirm = settings, confirm
        self.cancel = cancel or threading.Event()
        self.services = services or {}

    def confirm(self, question: str, detail: str = "") -> bool:
        return bool(self._confirm(question, detail))


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    required: list
    func: Callable
    category: str
    confirm: Callable[[dict], str | None] | None

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "parameters": {"type": "object", "properties": self.properties, "required": self.required}}


class Registry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def tool(self, description: str, params: dict | None = None, required: list | None = None,
             category: str = "system", confirm: Callable[[dict], str | None] | None = None, name: str | None = None):
        def deco(fn):
            t = Tool(name or fn.__name__, description, params or {}, required or [], fn, category, confirm)
            self.tools[t.name] = t
            return fn
        return deco

    def allowed(self, tool: Tool, settings) -> bool:
        return tool.category not in PERMISSION_CATEGORIES or bool(settings.get(f"permissions.{tool.category}", True))

    def schemas(self, settings=None) -> list[dict]:
        return [t.schema() for t in self.tools.values() if settings is None or self.allowed(t, settings)]

    def execute(self, name: str, args: dict, ctx: ToolContext) -> str:
        t = self.tools.get(name)
        if not t:
            return f"ERROR: unknown tool '{name}'."
        if not self.allowed(t, ctx.settings):
            return (f"ERROR: the '{t.category}' permission is switched off in Settings > Permissions, "
                    f"so I can't use {name}.")
        args = dict(args or {})
        sig = inspect.signature(t.func)
        if not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            args = {k: v for k, v in args.items() if k in sig.parameters}
        missing = [r for r in t.required if r not in args]
        if missing:
            return f"ERROR: missing required argument(s): {', '.join(missing)}."
        if t.confirm:
            try:
                question = t.confirm(args)
            except Exception:
                question = f"Run {name}?"
            if question and not ctx.confirm(question, name):
                return "DENIED: the user declined this action. Do not retry it."
        try:
            res = t.func(ctx, **args)
        except Exception as e:  # tools must never crash the agent
            log.exception("tool %s failed", name)
            return f"ERROR: {type(e).__name__}: {e}"
        return _format(res)


def _format(res: Any) -> str:
    if res is None:
        s = "OK"
    elif isinstance(res, str):
        s = res
    else:
        s = json.dumps(res, ensure_ascii=False, default=str)
    return s if len(s) <= MAX_RESULT else s[:MAX_RESULT] + "\n...[truncated]"


registry = Registry()
tool = registry.tool
