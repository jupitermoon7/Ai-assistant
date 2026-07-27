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
    """Root — redirect to Jarvis (primary interface)."""
    return redirect(url_for("main.agent_jarvis"))


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


# ── Agent pages ────────────────────────────────────────────────────────────────

def _agent_history(assistant, plugin_name: str, limit: int = 50):
    if assistant and assistant.memory:
        return assistant.memory.get_history(limit=limit, plugin=plugin_name)
    return []


@main_bp.route("/agents/data")
@login_required
def agent_data():
    assistant = _get_assistant()
    return render_template(
        "agent_chat.html",
        agent_name        = "Data",
        agent_emoji       = "📊",
        agent_avatar      = "/static/img/data-avatar.png",
        agent_color       = "#6aaa64",
        agent_color_dim   = "rgba(106,170,100,0.12)",
        agent_desc        = "Pure analytics — numbers, stats, structured intelligence reports",
        agent_placeholder = "Ask for a data report, stats breakdown, or analytical deep-dive…",
        api_endpoint      = "/api/chat/data",
        clear_command     = "clear_data",
        history           = _agent_history(assistant, "data"),
        chips             = [
            {"label": "📈 Best bets tonight",        "text": "Run a full analytics report on tonight's best betting opportunities"},
            {"label": "💹 Loan rate analysis",       "text": "Find me current personal loan rates and compare top lenders"},
            {"label": "🏥 Injury impact report",     "text": "Give me a structured injury impact report for tonight's NBA games"},
            {"label": "📊 Bankroll analytics",       "text": "Analyse my bankroll performance and give me statistical recommendations"},
            {"label": "⚾ MLB home run leaders",     "text": "Pull today's MLB stats and home run leaders"},
        ],
    )


@main_bp.route("/agents/cortona")
@login_required
def agent_cortona():
    assistant = _get_assistant()
    return render_template(
        "agent_chat.html",
        agent_name        = "Cortona",
        agent_emoji       = "🔮",
        agent_avatar      = "/static/img/cortona-avatar.png",
        agent_color       = "#38bdf8",
        agent_color_dim   = "rgba(56,189,248,0.12)",
        agent_desc        = "Intuitive general intelligence — engineering, loans, research, anything",
        agent_placeholder = "Ask me anything — engineering, finance, research, life questions…",
        api_endpoint      = "/api/chat/cortona",
        clear_command     = "clear_cortona",
        history           = _agent_history(assistant, "cortona"),
        chips             = [
            {"label": "🏠 Find me a loan",           "text": "Help me find the best personal loan options available right now"},
            {"label": "🔧 Engineering help",          "text": "I need help with an engineering problem — where do I start?"},
            {"label": "🎯 Betting strategy",          "text": "What betting strategy should I be using given my situation?"},
            {"label": "💡 Research a topic",          "text": "Research this topic for me and give me the key insights:"},
            {"label": "📱 Tech recommendation",      "text": "I need a tech recommendation — help me decide between options"},
        ],
    )


@main_bp.route("/agents/council")
@login_required
def agent_council():
    return render_template("council.html")


@main_bp.route("/agents/tasks")
@login_required
def agent_tasks():
    return render_template("tasks.html")


@main_bp.route("/agents/jarvis")
@login_required
def agent_jarvis():
    assistant = _get_assistant()
    return render_template(
        "agent_chat.html",
        agent_name        = "Jarvis",
        agent_emoji       = "🤖",
        agent_avatar      = "/static/img/jarvis-avatar.png",
        agent_color       = "#34d399",
        agent_color_dim   = "rgba(52,211,153,0.12)",
        agent_desc        = "Full-spectrum intelligence — analytics + intuition + live data, combined",
        agent_placeholder = "Give me a task — Jarvis handles anything at full depth…",
        api_endpoint      = "/api/chat/jarvis",
        clear_command     = "clear_jarvis",
        history           = _agent_history(assistant, "jarvis"),
        chips             = [
            {"label": "🎯 Full game report",          "text": "Give me a comprehensive report on tonight's best game to bet — data, experts, bots, everything"},
            {"label": "💰 Finance + betting plan",    "text": "Build me a combined financial and betting bankroll plan"},
            {"label": "🏗 Engineering + research",   "text": "I have an engineering challenge — research and solve it for me"},
            {"label": "📋 Full daily brief",          "text": "Give me my full daily intelligence brief — sports, news, anything relevant"},
            {"label": "🔍 Deep research task",        "text": "I need you to research something thoroughly and give me a complete report:"},
        ],
    )
