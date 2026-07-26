"""
dashboard/routes/api.py — REST API Routes
==========================================
JSON API consumed by:
- The Android client (future)
- Plugin-to-plugin calls via HTTP
- Any automation tools (curl, Shortcuts, Tasker, etc.)

All routes require a valid session (login_required) unless explicitly
exempted.  For API key auth (for Android client without a browser session),
the ``X-API-Key`` header check is stubbed and ready to extend.

Base URL: /api

Routes
------
GET  /api/status            — Full assistant status
GET  /api/plugins           — Plugin list and health
GET  /api/memory            — List memory entries
POST /api/memory            — Store a memory entry
DELETE /api/memory/<key>    — Delete a memory entry
GET  /api/scheduler/jobs    — List scheduled jobs
POST /api/command           — Execute a registered command
GET  /api/history           — Conversation history
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


# ── Plugins ────────────────────────────────────────────────────────────────────

@api_bp.route("/plugins")
@login_required
def plugins():
    """Return health status for all loaded plugins."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    return _ok(assistant.plugins.status_report())


# ── Memory ────────────────────────────────────────────────────────────────────

@api_bp.route("/memory", methods=["GET"])
@login_required
def list_memory():
    """
    List memory entries.

    Query parameters
    ----------------
    category : Filter by category label.
    limit    : Maximum entries to return (default 50).
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

    Request body (JSON)
    -------------------
    {
        "key":      "user_name",
        "value":    "Alice",
        "category": "preference"   (optional)
    }
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


# ── Scheduler ─────────────────────────────────────────────────────────────────

@api_bp.route("/scheduler/jobs")
@login_required
def scheduler_jobs():
    """Return all currently scheduled jobs."""
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)
    return _ok(assistant.scheduler.list_jobs())


# ── Commands ──────────────────────────────────────────────────────────────────

@api_bp.route("/command", methods=["POST"])
@login_required
def execute_command():
    """
    Execute a registered plugin command.

    Request body (JSON)
    -------------------
    {
        "command": "ping",
        "args":    {}          (optional extra arguments for the handler)
    }

    Response
    --------
    The handler's return value wrapped in the standard {"ok": true, "data": ...}
    envelope.
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

    # execute_command returns an error dict on failure
    if isinstance(result, dict) and "error" in result:
        return _err(result["error"], 400)

    return _ok(result if isinstance(result, (dict, list)) else {"response": result})


# ── Conversation history ───────────────────────────────────────────────────────

@api_bp.route("/history")
@login_required
def history():
    """
    Return conversation history.

    Query parameters
    ----------------
    limit  : Maximum entries (default 20).
    plugin : Filter by plugin name.
    """
    assistant = _get_assistant()
    if not assistant:
        return _err("Assistant not initialised", 503)

    limit = int(request.args.get("limit", 20))
    plugin = request.args.get("plugin")
    entries = assistant.memory.get_history(limit=limit, plugin=plugin)
    return _ok(entries)
