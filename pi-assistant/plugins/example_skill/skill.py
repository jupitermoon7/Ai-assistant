"""
plugins/example_skill/skill.py — Reference Plugin Implementation
=================================================================
This file is the canonical example for building a new skill.

It demonstrates every hook the plugin system supports:
- setup()         — called once on load; register scheduled jobs here
- teardown()      — called once on shutdown; clean up resources here
- get_commands()  — expose named commands to the assistant command registry
- health_check()  — return status info shown on the dashboard

To create your own skill:
1. Copy this folder to  plugins/your_skill_name/
2. Rename the class and update the metadata attributes
3. Implement your logic
4. Restart the assistant — it will be auto-discovered
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from core.logger import get_logger
from core.plugin_manager import BasePlugin

log = get_logger(__name__)


class ExampleSkill(BasePlugin):
    """
    A minimal, fully-documented reference plugin.

    Demonstrates:
    - Scheduled jobs (prints a heartbeat every minute in DEBUG mode)
    - Command registration (``ping``, ``hello``, ``status``)
    - Memory read/write via ``self.assistant.memory``
    - Health reporting for the dashboard
    """

    # ── Plugin metadata ────────────────────────────────────────────────────────
    plugin_name = "Example Skill"
    plugin_version = "0.1.0"
    plugin_description = "Reference implementation showing how to build a plugin"

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Called once when the assistant loads this plugin.

        Register a heartbeat job that fires every 5 minutes.
        The assistant's scheduler is available at this point.
        """
        log.info(f"[{self.name}] Setting up Example Skill")

        # Persist the plugin's load time in long-term memory
        if self.assistant and self.assistant.memory:
            self.assistant.memory.store(
                key="example_skill.last_loaded",
                value=datetime.now(timezone.utc).isoformat(),
                category="system",
            )

        # Register a scheduled heartbeat job
        if self.assistant and self.assistant.scheduler:
            self.assistant.scheduler.add_interval_job(
                func=self._heartbeat,
                job_id="example_skill.heartbeat",
                minutes=5,
            )

        log.info(f"[{self.name}] Ready")

    def teardown(self) -> None:
        """Called on shutdown. Remove scheduled jobs and clean up."""
        if self.assistant and self.assistant.scheduler:
            self.assistant.scheduler.remove_job("example_skill.heartbeat")
        log.info(f"[{self.name}] Torn down")

    # ── Commands ───────────────────────────────────────────────────────────────

    def get_commands(self) -> dict[str, Any]:
        """
        Expose three commands to the assistant's command registry.

        These can be triggered via:
        - The REST API:  POST /api/command  {"command": "ping"}
        - The dashboard: command input box
        - Other plugins: self.assistant.execute_command("ping")
        """
        return {
            "ping":   self.handle_ping,
            "hello":  self.handle_hello,
            "status": self.handle_status,
        }

    def handle_ping(self, **_kwargs: Any) -> dict[str, Any]:
        """
        Respond with a pong.  Used to test the command pipeline end-to-end.

        Returns
        -------
        dict with "response" key containing a pong message and timestamp.
        """
        return {
            "response": "pong",
            "plugin": self.name,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def handle_hello(self, name: str = "world", **_kwargs: Any) -> dict[str, Any]:
        """
        Return a personalised greeting.

        Parameters
        ----------
        name : Person or thing to greet (default: "world").

        Returns
        -------
        dict with "response" containing the greeting.
        """
        # Read a stored preference from long-term memory (if set)
        greeting = "Hello"
        if self.assistant and self.assistant.memory:
            preferred = self.assistant.memory.recall("example_skill.greeting")
            if preferred:
                greeting = preferred

        message = f"{greeting}, {name}! I'm your Pi Assistant."

        # Log this interaction to conversation history
        if self.assistant and self.assistant.memory:
            self.assistant.memory.log_message(
                role="assistant",
                content=message,
                plugin=self.name,
            )

        return {"response": message, "plugin": self.name}

    def handle_status(self, **_kwargs: Any) -> dict[str, Any]:
        """
        Return a detailed status report for this plugin.

        Returns
        -------
        dict with uptime info, scheduled jobs, and a random motivational tip.
        """
        tips = [
            "Add more skills to plugins/ to expand your assistant.",
            "Set a cron job in setup() for automated tasks.",
            "Use self.assistant.memory to persist data between sessions.",
            "Check the dashboard at http://your-pi-ip:8080 from your Android.",
        ]

        last_loaded = None
        if self.assistant and self.assistant.memory:
            last_loaded = self.assistant.memory.recall("example_skill.last_loaded")

        return {
            "plugin": self.name,
            "version": self.plugin_version,
            "description": self.plugin_description,
            "last_loaded": last_loaded,
            "tip": random.choice(tips),
        }

    # ── Health check ───────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """
        Report plugin health for the dashboard.

        Override this in real plugins to check connectivity, token validity,
        or any other required condition.
        """
        return {
            "status": "ok",
            "plugin": self.name,
            "version": self.plugin_version,
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    def _heartbeat(self) -> None:
        """
        Scheduled job that fires every 5 minutes.

        In a real plugin this could: poll a sensor, check for notifications,
        refresh a cached API response, etc.
        """
        log.debug(f"[{self.name}] Heartbeat — {datetime.now(timezone.utc).isoformat()}")
