from __future__ import annotations

import importlib.util
import logging

from .base import P, Registry, Tool, ToolContext, registry, tool  # noqa: F401

log = logging.getLogger(__name__)


def load_all(plugins_dir=None) -> Registry:
    """Import every built-in tool module (they self-register) plus user plugins from the plugins folder."""
    from . import apps, files, input_tools, messaging, shell, system_tools, web  # noqa: F401
    if plugins_dir is None:
        from ..paths import data_subdir
        plugins_dir = data_subdir("plugins")
    for f in sorted(plugins_dir.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"vega_plugin_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # plugins use `from vega.tools import tool`
            log.info("loaded plugin %s", f.name)
        except Exception:
            log.exception("failed to load plugin %s", f.name)
    return registry
