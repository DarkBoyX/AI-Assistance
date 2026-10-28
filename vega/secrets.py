"""API keys live in the Windows Credential Manager (via keyring) - never in files or source code."""
from __future__ import annotations

import logging
import os

SERVICE = "Vega Assistant"
_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def get_api_key(provider: str) -> str:
    try:
        import keyring
        key = keyring.get_password(SERVICE, provider)
        if key:
            return key
    except Exception:
        logging.getLogger(__name__).debug("keyring unavailable", exc_info=True)
    return os.environ.get(_ENV.get(provider, ""), "") if provider in _ENV else ""


def set_api_key(provider: str, key: str) -> None:
    import keyring
    if key:
        keyring.set_password(SERVICE, provider, key)
    else:
        try:
            keyring.delete_password(SERVICE, provider)
        except Exception:
            pass


def has_api_key(provider: str) -> bool:
    return bool(get_api_key(provider))
