"""
core/plugin_manager.py — Plugin Discovery & Lifecycle Manager
==============================================================
Automatically discovers, loads, validates, and manages the lifecycle of all
plugins (skills) found under the configured plugins directory.

Plugin contract
---------------
Every plugin MUST:
1. Live in its own sub-directory under ``plugins/``.
2. Contain a ``skill.py`` module.
3. Expose a class that inherits from ``BasePlugin`` in that module.

The plugin manager imports ``skill.py``, finds the first ``BasePlugin``
subclass, instantiates it, and calls ``setup()`` on it.  On shutdown it calls
``teardown()`` on every loaded plugin in reverse load order.

Adding a new skill
------------------
1. Create ``plugins/my_skill/__init__.py`` and ``plugins/my_skill/skill.py``.
2. Implement a class that subclasses ``BasePlugin``.
3. Restart the assistant — the plugin manager discovers it automatically.

Disabling a skill
-----------------
Add its folder name to ``plugins.disabled`` in ``config.yaml``.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.logger import get_logger

if TYPE_CHECKING:
    from core.assistant import Assistant

log = get_logger(__name__)


# ── Base Plugin Interface ──────────────────────────────────────────────────────

class BasePlugin:
    """
    Abstract base class that every plugin must inherit from.

    Attributes (set automatically by the plugin manager)
    -----------------------------------------------------
    name        : The plugin's folder name (e.g. "example_skill").
    config      : The plugin-specific config dict from config.yaml.
    assistant   : Reference to the running Assistant instance, so plugins
                  can access memory, the scheduler, other plugins, etc.
    """

    # Subclasses may set these as class attributes to provide metadata.
    plugin_name: str = ""          # Human-readable name shown in the dashboard
    plugin_version: str = "0.1.0"
    plugin_description: str = ""

    def __init__(self) -> None:
        # Set by the plugin manager after instantiation
        self.name: str = ""
        self.config: dict[str, Any] = {}
        self.assistant: "Assistant | None" = None

    # ── Lifecycle hooks ────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Called once when the plugin is loaded.

        Register scheduled jobs, subscribe to events, initialise external
        connections, etc.  Keep this fast — it blocks startup.
        """

    def teardown(self) -> None:
        """
        Called once when the assistant is shutting down.

        Close connections, flush buffers, cancel scheduled jobs.
        """

    # ── Command interface ──────────────────────────────────────────────────────

    def get_commands(self) -> dict[str, Any]:
        """
        Return a mapping of command names to handler functions.

        The returned dict is merged into the assistant's global command
        registry so the dashboard and API can invoke plugin commands by name.

        Example
        -------
        def get_commands(self):
            return {
                "greet": self.handle_greet,
                "status": self.handle_status,
            }
        """
        return {}

    # ── Status / health ────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """
        Return a status dict for the dashboard health panel.

        Override to report plugin-specific health (e.g. API reachability).
        """
        return {"status": "ok", "plugin": self.name}

    def __repr__(self) -> str:
        return f"<Plugin {self.name!r} v{self.plugin_version}>"


# ── Plugin Manager ─────────────────────────────────────────────────────────────

class PluginManager:
    """
    Discovers, loads, and manages all plugins for the assistant.

    Parameters
    ----------
    plugins_dir : Path to the plugins root directory.
    disabled    : List of plugin folder names to skip.
    """

    def __init__(
        self,
        plugins_dir: Path,
        disabled: list[str] | None = None,
    ) -> None:
        self._plugins_dir = plugins_dir
        self._disabled: set[str] = set(disabled or [])
        self._plugins: dict[str, BasePlugin] = {}   # name → instance

    # ── Public interface ───────────────────────────────────────────────────────

    def load_all(
        self,
        assistant: "Assistant",
        plugin_configs: dict[str, Any] | None = None,
    ) -> None:
        """
        Discover and load every plugin in the plugins directory.

        Parameters
        ----------
        assistant      : The running Assistant instance passed to each plugin.
        plugin_configs : Dict of plugin_name → config dict from config.yaml.
        """
        plugin_configs = plugin_configs or {}

        if not self._plugins_dir.exists():
            log.warning(f"Plugins directory not found: {self._plugins_dir}")
            return

        for candidate in sorted(self._plugins_dir.iterdir()):
            if not candidate.is_dir():
                continue
            if candidate.name.startswith("_"):
                continue
            if candidate.name in self._disabled:
                log.info(f"Plugin disabled (config): {candidate.name!r}")
                continue

            skill_file = candidate / "skill.py"
            if not skill_file.exists():
                log.debug(f"Skipping {candidate.name!r} — no skill.py found")
                continue

            self._load_plugin(
                folder_name=candidate.name,
                skill_file=skill_file,
                assistant=assistant,
                plugin_config=plugin_configs.get(candidate.name, {}),
            )

        log.info(f"Loaded {len(self._plugins)} plugin(s): {list(self._plugins.keys())}")

    def teardown_all(self) -> None:
        """Call teardown() on every loaded plugin (reverse load order)."""
        for name, plugin in reversed(list(self._plugins.items())):
            try:
                plugin.teardown()
                log.debug(f"Plugin torn down: {name!r}")
            except Exception:
                log.exception(f"Error during teardown of plugin {name!r}")

    def get_plugin(self, name: str) -> BasePlugin | None:
        """Return a loaded plugin by its folder name, or None."""
        return self._plugins.get(name)

    def all_plugins(self) -> list[BasePlugin]:
        """Return all loaded plugin instances."""
        return list(self._plugins.values())

    def get_all_commands(self) -> dict[str, Any]:
        """
        Collect and merge all plugin command registries into one dict.

        On collision, the last-loaded plugin wins and a warning is logged.
        """
        commands: dict[str, Any] = {}
        for plugin in self._plugins.values():
            for cmd_name, handler in plugin.get_commands().items():
                if cmd_name in commands:
                    log.warning(
                        f"Command conflict: {cmd_name!r} defined by multiple plugins. "
                        f"Using the version from {plugin.name!r}."
                    )
                commands[cmd_name] = handler
        return commands

    def status_report(self) -> list[dict[str, Any]]:
        """Return health status for all loaded plugins."""
        report = []
        for plugin in self._plugins.values():
            try:
                health = plugin.health_check()
            except Exception as exc:
                health = {"status": "error", "error": str(exc)}
            health["plugin"] = plugin.name
            report.append(health)
        return report

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_plugin(
        self,
        folder_name: str,
        skill_file: Path,
        assistant: "Assistant",
        plugin_config: dict[str, Any],
    ) -> None:
        """Import a single plugin module and instantiate its plugin class."""
        module_path = f"plugins.{folder_name}.skill"
        try:
            # Force re-import in case of hot-reload scenarios
            if module_path in sys.modules:
                module = importlib.reload(sys.modules[module_path])
            else:
                module = importlib.import_module(module_path)

            plugin_class = self._find_plugin_class(module, folder_name)
            if plugin_class is None:
                log.warning(
                    f"No BasePlugin subclass found in {module_path!r} — skipping"
                )
                return

            instance: BasePlugin = plugin_class()
            instance.name = folder_name
            instance.config = plugin_config
            instance.assistant = assistant

            instance.setup()

            self._plugins[folder_name] = instance
            log.info(
                f"Plugin loaded: {folder_name!r} "
                f"({plugin_class.plugin_description or 'no description'})"
            )
        except Exception:
            log.exception(f"Failed to load plugin {folder_name!r}")

    @staticmethod
    def _find_plugin_class(module: Any, folder_name: str) -> type[BasePlugin] | None:
        """Return the first BasePlugin subclass defined in *module*."""
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BasePlugin)
                and obj is not BasePlugin
                and obj.__module__ == module.__name__
            ):
                return obj
        return None
