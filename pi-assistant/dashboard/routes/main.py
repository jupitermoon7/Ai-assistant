"""
dashboard/routes/main.py — Dashboard UI Routes
================================================
Serves the HTML pages of the web dashboard.

Routes
------
GET /          — Main dashboard page (status overview)
GET /memory    — Browse long-term memory entries
GET /scheduler — View scheduled jobs
GET /plugins   — Plugin status and health
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template
from flask_login import login_required

from core.logger import get_logger

log = get_logger(__name__)

main_bp = Blueprint("main", __name__)


def _get_assistant():
    """Helper: retrieve the Assistant instance from app config."""
    return current_app.config.get("ASSISTANT")


@main_bp.route("/")
@login_required
def index():
    """
    Main dashboard overview.

    Passes assistant status (scheduler state, plugin list, command count)
    to the template.
    """
    assistant = _get_assistant()
    status = assistant.status() if assistant else {}
    return render_template("index.html", status=status)


@main_bp.route("/memory")
@login_required
def memory():
    """Browse all long-term memory entries stored by the assistant."""
    assistant = _get_assistant()
    memories = []
    if assistant and assistant.memory:
        memories = assistant.memory.list_memories(limit=100)
    return render_template("memory.html", memories=memories)


@main_bp.route("/scheduler")
@login_required
def scheduler():
    """View all currently scheduled jobs."""
    assistant = _get_assistant()
    jobs = []
    if assistant and assistant.scheduler:
        jobs = assistant.scheduler.list_jobs()
    return render_template("scheduler.html", jobs=jobs)


@main_bp.route("/plugins")
@login_required
def plugins():
    """Plugin status and health report."""
    assistant = _get_assistant()
    plugin_status = []
    if assistant and assistant.plugins:
        plugin_status = assistant.plugins.status_report()
    return render_template("plugins.html", plugins=plugin_status)
