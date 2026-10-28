"""Agent loop: model <-> tools, narrating as it goes."""
from __future__ import annotations

import logging
from typing import Callable

from ..tools.base import Registry, ToolContext
from .prompts import build_system_prompt
from .providers import make_provider

log = logging.getLogger(__name__)


class Agent:
    def __init__(self, settings, storage, registry: Registry, provider_factory=make_provider):
        self.settings, self.storage, self.registry = settings, storage, registry
        self.provider_factory = provider_factory

    def run_turn(self, history: list[tuple[str, str]], ctx: ToolContext, cancel,
                 on_say: Callable[[str], None], on_tool: Callable[[str, dict, str], None]) -> str:
        provider = self.provider_factory(self.settings)
        system = build_system_prompt(self.settings, self.storage.facts())
        msgs: list[dict] = [{"role": r, "content": t} for r, t in history]
        tools = self.registry.schemas(self.settings)
        said: list[str] = []
        used_tool = False
        for _ in range(int(self.settings.get("ai.max_steps", 12))):
            if cancel.is_set():
                break
            resp = provider.chat(system, msgs, tools)
            if cancel.is_set():
                break
            if resp.text:
                said.append(resp.text)
                on_say(resp.text)
            if not resp.tool_calls:
                break
            used_tool = True
            msgs.append({"role": "assistant", "content": resp.text,
                         "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in resp.tool_calls]})
            for c in resp.tool_calls:
                result = "ERROR: cancelled by the user." if cancel.is_set() else self.registry.execute(c.name, c.arguments, ctx)
                on_tool(c.name, c.arguments, result)
                msgs.append({"role": "tool", "tool_call_id": c.id, "name": c.name, "content": result})
            if cancel.is_set():
                break
        else:
            on_say("I've hit my step limit on that one. Tell me if you'd like me to continue.")
        if used_tool and not said and not cancel.is_set():
            on_say("Done.")
        return " ".join(said)
