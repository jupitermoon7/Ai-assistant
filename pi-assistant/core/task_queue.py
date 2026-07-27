"""
core/task_queue.py — Persistent Agent Task Queue
=================================================
Lets you assign tasks to any agent (Data, Cortona, Jarvis, or Council).
Tasks are stored in SQLite and processed one at a time by a background
worker thread — so the Pi keeps working while you sleep.

Task lifecycle
--------------
  pending → running → completed
                    → failed

Worker behaviour
----------------
  - Wakes every POLL_INTERVAL seconds to check for pending tasks.
  - Picks the highest-priority task (lowest priority number wins).
  - Runs it by calling the registered agent callable.
  - Stores the result (or error) and marks it done.
  - Posts a Discord notification after each completion.
  - Processes one task at a time — keeps the Pi cool.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.logger import get_logger

log = get_logger(__name__)

POLL_INTERVAL = 6  # seconds between queue checks
DB_TIMEOUT    = 10  # sqlite busy timeout


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Task:
    id:           str
    agent:        str          # data | cortona | jarvis | council
    title:        str
    description:  str
    priority:     int = 5      # 1 = highest, 10 = lowest
    status:       str = "pending"   # pending | running | completed | failed
    result:       str | None = None
    error:        str | None = None
    notify:       bool = True  # Discord notification on completion
    created_at:   str = field(default_factory=lambda: _now())
    started_at:   str | None = None
    completed_at: str | None = None


# ── Task Queue (SQLite-backed) ────────────────────────────────────────────────

class TaskQueue:
    """
    SQLite-backed persistent task queue.

    Thread-safe: all writes use the same connection serialised through
    check_same_thread=False + WAL mode.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()
        log.info(f"[task_queue] Initialised → {db_path}")

    # ── Connection ─────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(str(self._db_path), timeout=DB_TIMEOUT,
                                   check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        c = self._conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id           TEXT PRIMARY KEY,
                agent        TEXT NOT NULL,
                title        TEXT NOT NULL,
                description  TEXT NOT NULL,
                priority     INTEGER DEFAULT 5,
                status       TEXT DEFAULT 'pending',
                result       TEXT,
                error        TEXT,
                notify       INTEGER DEFAULT 1,
                created_at   TEXT NOT NULL,
                started_at   TEXT,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_status_priority
                ON tasks (status, priority, created_at);
        """)
        c.commit()

    # ── Write operations ───────────────────────────────────────────────────────

    def add(
        self,
        agent:       str,
        description: str,
        title:       str | None = None,
        priority:    int = 5,
        notify:      bool = True,
    ) -> Task:
        task = Task(
            id          = str(uuid.uuid4())[:8],
            agent       = agent.lower(),
            title       = title or description[:60],
            description = description,
            priority    = max(1, min(10, priority)),
            notify      = notify,
        )
        self._conn().execute(
            """INSERT INTO tasks
               (id, agent, title, description, priority, status, notify, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (task.id, task.agent, task.title, task.description,
             task.priority, int(task.notify), task.created_at),
        )
        self._conn().commit()
        log.info(f"[task_queue] Task queued: [{task.id}] {task.title!r} → {task.agent}")
        return task

    def _set_running(self, task_id: str) -> None:
        self._conn().execute(
            "UPDATE tasks SET status='running', started_at=? WHERE id=?",
            (_now(), task_id),
        )
        self._conn().commit()

    def _set_done(self, task_id: str, result: str) -> None:
        self._conn().execute(
            "UPDATE tasks SET status='completed', result=?, completed_at=? WHERE id=?",
            (result, _now(), task_id),
        )
        self._conn().commit()

    def _set_failed(self, task_id: str, error: str) -> None:
        self._conn().execute(
            "UPDATE tasks SET status='failed', error=?, completed_at=? WHERE id=?",
            (error, _now(), task_id),
        )
        self._conn().commit()

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task. Running/completed tasks cannot be cancelled."""
        cur = self._conn().execute(
            "UPDATE tasks SET status='cancelled', completed_at=? "
            "WHERE id=? AND status='pending'",
            (_now(), task_id),
        )
        self._conn().commit()
        return cur.rowcount > 0

    def delete(self, task_id: str) -> bool:
        cur = self._conn().execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self._conn().commit()
        return cur.rowcount > 0

    def clear_completed(self) -> int:
        cur = self._conn().execute(
            "DELETE FROM tasks WHERE status IN ('completed', 'failed', 'cancelled')"
        )
        self._conn().commit()
        return cur.rowcount

    # ── Read operations ────────────────────────────────────────────────────────

    def next_pending(self) -> Task | None:
        row = self._conn().execute(
            "SELECT * FROM tasks WHERE status='pending' "
            "ORDER BY priority ASC, created_at ASC LIMIT 1"
        ).fetchone()
        return _row_to_task(row) if row else None

    def get(self, task_id: str) -> Task | None:
        row = self._conn().execute(
            "SELECT * FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        return _row_to_task(row) if row else None

    def list_all(self, limit: int = 100) -> list[Task]:
        rows = self._conn().execute(
            "SELECT * FROM tasks ORDER BY "
            "CASE status WHEN 'running' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, "
            "priority ASC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def counts(self) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT status, COUNT(*) as n FROM tasks GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


# ── Background worker ─────────────────────────────────────────────────────────

class TaskWorker:
    """
    Daemon thread that drains the task queue one task at a time.

    Parameters
    ----------
    queue       : The TaskQueue to pull from.
    agent_fns   : Dict mapping agent name → callable(description) → str.
                  e.g. {"data": data_mgr.consult, "jarvis": jarvis_mgr.consult}
    notifier    : Optional callable(title, body) for Discord notifications.
    """

    def __init__(
        self,
        queue:     TaskQueue,
        agent_fns: dict[str, Callable[[str], Any]],
        notifier:  Callable[[str, str], None] | None = None,
    ) -> None:
        self._queue     = queue
        self._agent_fns = agent_fns
        self._notifier  = notifier
        self._stop      = threading.Event()
        self._thread    = threading.Thread(target=self._loop, daemon=True,
                                           name="task-worker")

    def start(self) -> None:
        self._thread.start()
        log.info("[task_worker] Background worker started.")

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        log.info("[task_worker] Worker stopped.")

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    # ── Internal loop ──────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                task = self._queue.next_pending()
                if task:
                    self._run(task)
            except Exception:
                log.exception("[task_worker] Unexpected error in worker loop")
            self._stop.wait(POLL_INTERVAL)

    def _run(self, task: Task) -> None:
        log.info(f"[task_worker] Starting task [{task.id}] '{task.title}' → {task.agent}")
        self._queue._set_running(task.id)

        try:
            fn = self._agent_fns.get(task.agent)
            if fn is None:
                raise ValueError(f"No agent registered for '{task.agent}'")

            result = fn(task.description)
            if not isinstance(result, str):
                result = str(result)

            self._queue._set_done(task.id, result)
            log.info(f"[task_worker] Task [{task.id}] completed ({len(result)} chars)")

            if task.notify and self._notifier:
                snippet = result[:400] + ("…" if len(result) > 400 else "")
                self._notifier(
                    f"✅ Task done [{task.agent.upper()}]: {task.title}",
                    snippet,
                )

        except Exception as exc:
            error = str(exc)
            self._queue._set_failed(task.id, error)
            log.exception(f"[task_worker] Task [{task.id}] failed: {error}")
            if task.notify and self._notifier:
                self._notifier(
                    f"❌ Task failed [{task.agent.upper()}]: {task.title}",
                    f"Error: {error}",
                )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id           = row["id"],
        agent        = row["agent"],
        title        = row["title"],
        description  = row["description"],
        priority     = row["priority"],
        status       = row["status"],
        result       = row["result"],
        error        = row["error"],
        notify       = bool(row["notify"]),
        created_at   = row["created_at"],
        started_at   = row["started_at"],
        completed_at = row["completed_at"],
    )
