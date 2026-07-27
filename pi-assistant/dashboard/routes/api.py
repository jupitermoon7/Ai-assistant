"""
dashboard/routes/api.py — REST API Routes
==========================================
JSON API consumed by:
- The dashboard chat UI (via fetch)
- Android client (future)
- Plugin-to-plugin calls via HTTP
- Automation tools (curl, Tasker, Shortcuts, etc.)

All routes require a valid session (login_required).

Base URL: /api

Routes
------
GET  /api/status            — Full assistant status
POST /api/chat              — Send a message to the betting assistant ★ NEW
GET  /api/history           — Conversation history
POST /api/history/clear     — Clear conversation history
GET  /api/plugins           — Plugin list and health
GET  /api/memory            — List memory entries
POST /api/memory            — Store a memory entry
DELETE /api/memory/<key>    — Delete a memory entry
GET  /api/bankroll          — Current bankroll state
POST /api/bankroll          — Update bankroll
GET  /api/bets              — List all tracked bets
POST /api/bets              — Track a new bet
GET  /api/scheduler/jobs    — List scheduled jobs
POST /api/command           — Execute any registered command
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.logger import get_logger

log = get_logger(__name__)

api_bp = Blueprint("api", __name__)


def _get_assistant():
    return current_app.config.get("ASSISTANT")


def _ok(data: dict | list) -> tuple:
    return jsonify({"ok": True, "data": data}), 200


def _err(message: str, code: int = 400) -> tuple:
    return jsonify({"ok": False, "error": message}), code


# ── Status ─────────────────────────────────────────────────────────────────────

@api_bp.route("/status")
@login_required
def status():
    """Return the full assistant status snapshot as JSON."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    return _ok(assistant.status())


# ── Chat (conversation loop) ───────────────────────────────────────────────────

@api_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    """Send a message to the betting assistant (Data legacy endpoint)."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    body    = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return _err("'message' is required")
    result = assistant.execute_command("chat", message=message)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)
    return _ok(result)


@api_bp.route("/chat/data", methods=["POST"])
@login_required
def chat_data():
    """Send a message to the Data analytics agent."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    body    = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return _err("'message' is required")
    result = assistant.execute_command("chat_data", message=message)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)
    return _ok(result)


@api_bp.route("/chat/cortona", methods=["POST"])
@login_required
def chat_cortona():
    """Send a message to Cortona (intuitive general intelligence)."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    body    = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return _err("'message' is required")
    result = assistant.execute_command("chat_cortona", message=message)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)
    return _ok(result)


@api_bp.route("/chat/jarvis", methods=["POST"])
@login_required
def chat_jarvis():
    """Send a message to Jarvis (full-spectrum intelligence)."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    body    = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return _err("'message' is required")
    result = assistant.execute_command("chat_jarvis", message=message)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)
    return _ok(result)


@api_bp.route("/chat/council", methods=["POST"])
@login_required
def chat_council():
    """
    Run a full Council session — two rounds of inter-agent deliberation.

    Round 1: Data, Cortona, and Jarvis each answer independently (parallel).
    Round 2: Each agent reads the other two's answers and reacts (parallel).

    Returns structured JSON with both rounds for all three agents.
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    body    = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return _err("'message' is required")
    result = assistant.execute_command("council", message=message)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)
    return _ok(result)


# ── Task queue ────────────────────────────────────────────────────────────────

@api_bp.route("/tasks", methods=["GET"])
@login_required
def get_tasks():
    """List all tasks with counts."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("list_tasks", limit=int(request.args.get("limit", 100)))
    return _ok(result)


@api_bp.route("/tasks", methods=["POST"])
@login_required
def create_task():
    """
    Queue a new task for an agent.

    Body: { "agent": "jarvis", "description": "...", "title": "...", "priority": 5, "notify": true }
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    body = request.get_json(silent=True) or {}
    if not body.get("agent"):
        return _err("'agent' is required")
    if not body.get("description"):
        return _err("'description' is required")
    result = assistant.execute_command(
        "queue_task",
        agent       = body["agent"],
        description = body["description"],
        title       = body.get("title", ""),
        priority    = int(body.get("priority", 5)),
        notify      = bool(body.get("notify", True)),
    )
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"])
    return _ok(result)


@api_bp.route("/tasks/<task_id>", methods=["GET"])
@login_required
def get_task(task_id: str):
    """Get a single task by ID, including its full result."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("task_result", task_id=task_id)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 404)
    return _ok(result)


@api_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
@login_required
def cancel_task(task_id: str):
    """Cancel a pending task."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("cancel_task", task_id=task_id)
    return _ok(result)


@api_bp.route("/tasks/<task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id: str):
    """Delete a task entirely."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    # Access queue directly via the agents plugin
    agents_plugin = assistant.plugins._plugins.get("agents")
    if not agents_plugin:
        return _err("Agents plugin not loaded", 503)
    ok = agents_plugin._task_queue.delete(task_id)
    return _ok({"deleted": ok, "task_id": task_id})


@api_bp.route("/tasks/clear", methods=["POST"])
@login_required
def clear_tasks():
    """Clear all completed/failed/cancelled tasks."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("clear_tasks")
    return _ok(result)


@api_bp.route("/tasks/status", methods=["GET"])
@login_required
def tasks_status():
    """Worker health + counts."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("tasks_status")
    return _ok(result)


# ── Conversation history ───────────────────────────────────────────────────────

@api_bp.route("/history")
@login_required
def history():
    """
    Return conversation history.

    Query params: limit (default 50), plugin (filter by plugin name).
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    limit = int(request.args.get("limit", 50))
    plugin = request.args.get("plugin")
    entries = assistant.memory.get_history(limit=limit, plugin=plugin)
    return _ok(entries)


@api_bp.route("/history/clear", methods=["POST"])
@login_required
def clear_history():
    """Delete all conversation history entries."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("clear_history")
    return _ok(result)


# ── Plugins ────────────────────────────────────────────────────────────────────

@api_bp.route("/plugins")
@login_required
def plugins():
    """Return health status for all loaded plugins."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    return _ok(assistant.plugins.status_report())


# ── Memory ─────────────────────────────────────────────────────────────────────

@api_bp.route("/memory", methods=["GET"])
@login_required
def list_memory():
    """
    List memory entries.

    Query params: category (filter), limit (default 50).
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    category = request.args.get("category")
    limit = int(request.args.get("limit", 50))
    memories = assistant.memory.list_memories(category=category, limit=limit)
    return _ok(memories)


@api_bp.route("/memory", methods=["POST"])
@login_required
def store_memory():
    """
    Store a memory entry.

    Body: { "key": "...", "value": ..., "category": "..." (optional) }
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    body = request.get_json(silent=True) or {}
    key = body.get("key", "").strip()
    value = body.get("value")
    category = body.get("category")

    if not key:
        return _err("'key' is required")
    if value is None:
        return _err("'value' is required")

    assistant.memory.store(key=key, value=value, category=category)
    return _ok({"stored": key})


@api_bp.route("/memory/<key>", methods=["DELETE"])
@login_required
def delete_memory(key: str):
    """Delete a single memory entry by key."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    deleted = assistant.memory.forget(key)
    if not deleted:
        return _err(f"Key {key!r} not found", 404)
    return _ok({"deleted": key})


# ── Bankroll ───────────────────────────────────────────────────────────────────

@api_bp.route("/bankroll", methods=["GET"])
@login_required
def get_bankroll():
    """Return current bankroll state."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    result = assistant.execute_command("bankroll", action="view")
    return _ok(result)


@api_bp.route("/bankroll", methods=["POST"])
@login_required
def update_bankroll():
    """
    Update the bankroll.

    Body: { "action": "set"|"add"|"subtract", "amount": 1000.00 }
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    body = request.get_json(silent=True) or {}
    action = body.get("action", "set")
    amount = float(body.get("amount", 0))

    result = assistant.execute_command("bankroll", action=action, amount=amount)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"])
    return _ok(result)


# ── Bet tracking ───────────────────────────────────────────────────────────────

@api_bp.route("/bets", methods=["GET"])
@login_required
def get_bets():
    """
    Return tracked bets.

    Query params: today=1 (only today's bets, default), all=1 (all bets).
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    if request.args.get("all"):
        bets = assistant.memory.list_memories(category="bet", limit=500)
        return _ok([b["value"] for b in bets])

    result = assistant.execute_command("bets_today")
    return _ok(result)


@api_bp.route("/bets", methods=["POST"])
@login_required
def track_bet():
    """
    Track a new bet.

    Body:
    {
        "sport":    "NBA",
        "game":     "Lakers vs Warriors",
        "bet_type": "spread",
        "line":     "-4.5",
        "odds":     "-110",
        "stake":    50.00,
        "result":   "pending",
        "notes":    "Optional notes"
    }
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    body = request.get_json(silent=True) or {}
    if not body.get("game"):
        return _err("'game' is required")

    result = assistant.execute_command("track_bet", **body)
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"])
    return _ok(result)


# ── Scheduler ─────────────────────────────────────────────────────────────────

@api_bp.route("/scheduler/jobs")
@login_required
def scheduler_jobs():
    """Return all currently scheduled jobs."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    return _ok(assistant.scheduler.list_jobs())


# ── Generic command dispatch ───────────────────────────────────────────────────

@api_bp.route("/command", methods=["POST"])
@login_required
def execute_command():
    """
    Execute any registered plugin command by name.

    Body: { "command": "ping", "args": {} }
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    body = request.get_json(silent=True) or {}
    command = body.get("command", "").strip()
    args = body.get("args", {})

    if not command:
        return _err("'command' is required")

    result = assistant.execute_command(command, **args)

    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)

    return _ok(result if isinstance(result, (dict, list)) else {"response": result})
