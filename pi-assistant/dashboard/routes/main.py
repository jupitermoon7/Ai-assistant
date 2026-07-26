"""
dashboard/routes/main.py — Dashboard UI Routes
================================================
Serves the HTML pages of the web dashboard.

Routes
------
GET /           — Redirect to /chat (chat is now the primary view)
GET /chat       — Live chat interface with the betting assistant ★ NEW
GET /overview   — System status overview
GET /memory     — Browse long-term memory entries
GET /scheduler  — View scheduled jobs
GET /plugins    — Plugin status and health
"""

from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, url_for
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
    """Root — redirect to chat (the primary interface)."""
    return redirect(url_for("main.chat"))


@main_bp.route("/chat")
@login_required
def chat():
    """
    Live chat interface.

    Loads recent conversation history so the UI shows the last session.
    """
    assistant = _get_assistant()
    history = []
    if assistant and assistant.memory:
        history = assistant.memory.get_history(limit=50)
    return render_template("chat.html", history=history)


@main_bp.route("/overview")
@login_required
def overview():
    """System status overview — scheduler, plugins, commands."""
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
