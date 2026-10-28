"""Settings persisted as JSON in %APPDATA%/Vega. API keys are NOT stored here (see secrets.py)."""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
from pathlib import Path

from .paths import app_dir

DEFAULTS: dict = {
    "assistant": {
        "name": "Vega",
        "user_name": "",
        "personality": ("Calm, composed and dry-witted, like a world-class British AI butler. Efficient, precise and "
                        "quietly confident, with occasional understated humour. Never gushing, never verbose."),
    },
    "ai": {
        "provider": "openai",
        "temperature": 0.5,
        "max_steps": 12,
        "context_messages": 24,
        "providers": {
            "openai": {"label": "OpenAI", "kind": "openai", "base_url": "https://api.openai.com/v1",
                       "model": "gpt-4o-mini", "needs_key": True},
            "anthropic": {"label": "Anthropic (Claude)", "kind": "anthropic", "base_url": "https://api.anthropic.com/v1",
                          "model": "claude-sonnet-5-5", "needs_key": True},
            "openrouter": {"label": "OpenRouter", "kind": "openai", "base_url": "https://openrouter.ai/api/v1",
                           "model": "openai/gpt-4o-mini", "needs_key": True},
            "ollama": {"label": "Ollama (local, no key)", "kind": "openai", "base_url": "http://localhost:11434/v1",
                       "model": "llama3.1", "needs_key": False},
            "custom": {"label": "Custom OpenAI-compatible", "kind": "openai", "base_url": "",
                       "model": "", "needs_key": True},
        },
    },
    "voice": {"engine": "edge", "voice": "en-GB-RyanNeural", "rate": 0, "pitch": 0, "volume": 85,
              "speak_responses": True},
    "mic": {"device": "", "sensitivity": 5, "silence_ms": 800, "allow_interrupt": True, "continuous": True,
            "wake_word": False, "wake_window_s": 45, "stt_model": "base.en", "stt_language": "en"},
    "permissions": {"apps": True, "files": True, "web": True, "input": True, "messaging": True, "commands": True},
    "startup": {"start_with_windows": False, "start_minimized": False, "minimize_to_tray_on_close": True},
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else app_dir() / "settings.json"
        self._lock = threading.RLock()
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            self.data = copy.deepcopy(DEFAULTS)
            try:
                if self.path.exists():
                    _merge(self.data, json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                logging.exception("Could not read settings; using defaults")

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def get(self, dotted: str, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, dotted: str, value) -> None:
        with self._lock:
            parts = dotted.split(".")
            cur = self.data
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = value

    @property
    def provider_name(self) -> str:
        return self.get("ai.provider", "openai")

    @property
    def provider_cfg(self) -> dict:
        return self.data["ai"]["providers"].setdefault(self.provider_name, {})

    @property
    def name(self) -> str:
        return self.get("assistant.name", "Vega") or "Vega"
