"""
core/assistant.py — Main Orchestrator
=======================================
The ``Assistant`` class is the single source of truth for the running state
of the application.  It owns every subsystem and wires them together:

    Config → Logger → Memory → Scheduler → PluginManager → Dashboard

Startup sequence
----------------
1. ``Assistant.__init__``  — instantiate all subsystems (no I/O yet)
2. ``assistant.start()``   — start the scheduler, load plugins, start dashboard
3. ``assistant.run()``     — block until a shutdown signal is received
4. ``assistant.stop()``    — graceful teardown (called by signal handlers)

Usage
-----
    from core.assistant import Assistant

    assistant = Assistant()
    assistant.start()
    assistant.run()   # blocks forever (handles SIGINT / SIGTERM)
"""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any

from core.config import config
from core.logger import get_logger, setup_logging
from core.memory import MemoryManager
from core.plugin_manager import PluginManager
from core.scheduler import TaskScheduler

log = get_logger(__name__)


class Assistant:
    """
    Central orchestrator for the Pi Assistant.

    All subsystems are accessible as attributes so plugins can reach them
    via ``self.assistant.<subsystem>``.

    Attributes
    ----------
    memory    : Long-term memory manager (SQLite-backed)
    scheduler : Background task scheduler (APScheduler)
    plugins   : Plugin lifecycle manager
    commands  : Merged command registry from all loaded plugins
    """

    def __init__(self) -> None:
        # ── Configure logging first so every subsequent log is captured ────────
        setup_logging(
            log_level=config.get("A.log_level", "INFO"),
            log_dir=config.data_dir / "logs",
        )

        log.info(
            f"Initialising {config.get('A.name', 'Pi Assistant')} "
            f"v{config.get('A.version', '0.1.0')}"
        )

        # ── Memory ─────────────────────────────────────────────────────────────
        db_path = config.data_dir / config.get("memory.db_file", "memory/assistant.db")
        self.memory = MemoryManager(db_path=Path(db_path))

        # ── Scheduler ──────────────────────────────────────────────────────────
        self.scheduler = TaskScheduler(
            timezone=config.get("scheduler.timezone", "UTC"),
            misfire_grace_time=config.get("scheduler.misfire_grace_time", 60),
        )

        # ── Plugin manager ─────────────────────────────────────────────────────
        plugins_dir = config.project_root / config.get("plugins.directory", "plugins")
        self.plugins = PluginManager(
            plugins_dir=plugins_dir,
            disabled=config.get("plugins.disabled", []),
        )

        # Populated after plugins load
        self.commands: dict[str, Any] = {}

        # ── Internal state ─────────────────────────────────────────────────────
        self._stop_event = threading.Event()
        self._dashboard_thread: threading.Thread | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start all subsystems.

        Call this once before ``run()``.  Safe to call from any thread.
        """
        log.info("Starting subsystems…")

        # Start scheduler before plugins so plugins can register jobs in setup()
        if config.get("scheduler.enabled", True):
            self.scheduler.start()

        # Load all plugins — each plugin's setup() is called here
        self.plugins.load_all(
            assistant=self,
            plugin_configs=config.get("plugins.settings", {}),
        )

        # Build the merged command registry
        self.commands = self.plugins.get_all_commands()
        log.info(f"Commands registered: {list(self.commands.keys()) or 'none'}")

        # Start the web dashboard in a background thread
        if config.get("dashboard.enabled", True):
            self._start_dashboard()

        log.info("All subsystems started. Assistant is running.")

    def run(self) -> None:
        """
        Block the main thread until a shutdown signal is received.

        Installs SIGINT (Ctrl-C) and SIGTERM (systemd stop) handlers so the
        assistant shuts down cleanly in both development and production.
        """
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        log.info("Waiting for shutdown signal (SIGINT or SIGTERM)…")
        self._stop_event.wait()

    def stop(self) -> None:
        """
        Gracefully shut down every subsystem.

        Order matters: plugins first (they may flush data), then scheduler,
        then dashboard.
        """
        log.info("Shutting down…")

        self.plugins.teardown_all()

        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)

        self._stop_event.set()
        log.info("Shutdown complete.")

    # ── Command dispatch ───────────────────────────────────────────────────────

    def execute_command(self, command: str, **kwargs: Any) -> Any:
        """
        Execute a registered plugin command by name.

        Parameters
        ----------
        command : The command name (must match a key in self.commands).
        **kwargs : Arguments passed through to the command handler.

        Returns
        -------
        The return value of the handler, or an error dict on failure.
        """
        handler = self.commands.get(command)
        if handler is None:
            available = list(self.commands.keys())
            log.warning(f"Unknown command: {command!r}. Available: {available}")
            return {"error": f"Unknown command: {command!r}", "available": available}

        try:
            result = handler(**kwargs)
            log.debug(f"Command executed: {command!r}")
            return result
        except Exception as exc:
            log.exception(f"Command {command!r} raised an error")
            return {"error": str(exc), "command": command}

    # ── Status / health ────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """
        Return a full status snapshot for the dashboard API.

        Includes assistant metadata, scheduler state, and plugin health.
        """
        return {
            "name": config.get("A.name", "Pi Assistant"),
            "version": config.get("A.version", "0.1.0"),
            "scheduler": {
                "running": self.scheduler.running,
                "jobs": self.scheduler.list_jobs(),
            },
            "plugins": self.plugins.status_report(),
            "commands": list(self.commands.keys()),
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    def _start_dashboard(self) -> None:
        """Launch the Flask dashboard in a daemon background thread."""
        try:
            from dashboard.app import create_app

            app = create_app(assistant=self)
            host = config.get("dashboard.host", "0.0.0.0")
            port = int(config.get("dashboard.port", 8080))

            def _serve() -> None:
                try:
                    from waitress import serve as waitress_serve
                    log.info(f"Dashboard starting on http://{host}:{port} (Waitress)")
                    waitress_serve(app, host=host, port=port)
                except ImportError:
                    # Fallback to Flask dev server if Waitress isn't installed
                    log.warning("Waitress not found — using Flask dev server (not for production)")
                    app.run(host=host, port=port, use_reloader=False, debug=False)

            self._dashboard_thread = threading.Thread(
                target=_serve, name="dashboard", daemon=True
            )
            self._dashboard_thread.start()
            log.info(f"Dashboard thread started → http://{host}:{port}")
        except Exception:
            log.exception("Failed to start dashboard — continuing without it")

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        """Signal handler for SIGINT and SIGTERM."""
        sig_name = signal.Signals(signum).name
        log.info(f"Received {sig_name} — initiating graceful shutdown")
        # Run stop() in a separate thread so the signal handler returns quickly
        threading.Thread(target=self.stop, daemon=True).start()
