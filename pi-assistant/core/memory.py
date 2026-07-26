"""
core/memory.py — Long-Term Memory System
==========================================
Provides a persistent key-value and semantic memory store backed by SQLite.

Design
------
- **Flat key-value store** (``MemoryEntry`` table) for structured facts:
  e.g. preferences, user profile, named facts ("user's name is Alice").
- **Conversation log** (``ConversationEntry`` table) for rolling chat history.
- Both tables are easily queryable; schema is managed with SQLAlchemy so
  you can later migrate to PostgreSQL or add vector columns without
  rewriting the memory layer.

Upgrade path
------------
To add vector search later, install ``pgvector`` (for PostgreSQL) or
``sqlite-vss`` and add an ``embedding`` column to ``MemoryEntry``.  The
``MemoryManager`` class exposes a ``search_similar()`` stub ready for that.

Usage
-----
    from core.memory import MemoryManager

    mem = MemoryManager(db_path)
    mem.store("user_name", "Alice")
    mem.recall("user_name")          # → "Alice"
    mem.log_message("user", "Hello")
    mem.get_history(limit=20)        # → list of ConversationEntry dicts
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    select,
    delete,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.logger import get_logger

log = get_logger(__name__)


# ── ORM Models ────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class MemoryEntry(Base):
    """
    A single long-term memory fact.

    key     : Unique string identifier, e.g. "user_name" or "home_city".
    value   : JSON-encoded value so any Python primitive/dict/list can be stored.
    category: Optional grouping label, e.g. "preference", "fact", "skill".
    updated : Timestamp of last write (UTC).
    """
    __tablename__ = "memory_entries"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    key      = Column(String(256), unique=True, nullable=False, index=True)
    value    = Column(Text, nullable=False)
    category = Column(String(64), nullable=True, index=True)
    updated  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                      onupdate=lambda: datetime.now(timezone.utc))


class ConversationEntry(Base):
    """
    One turn of the conversation log.

    role    : "user" | "assistant" | "system"
    content : The raw message text.
    plugin  : Optional name of the plugin that generated the message.
    ts      : Timestamp (UTC).
    """
    __tablename__ = "conversation_log"

    id      = Column(Integer, primary_key=True, autoincrement=True)
    role    = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    plugin  = Column(String(128), nullable=True)
    ts      = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# ── MemoryManager ─────────────────────────────────────────────────────────────

class MemoryManager:
    """
    High-level interface to the assistant's long-term memory.

    Parameters
    ----------
    db_path : Path
        Absolute path to the SQLite database file.
        Created automatically if it doesn't exist.
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self._Session = sessionmaker(bind=engine, expire_on_commit=False)
        log.info(f"Memory initialised → {db_path}")

    # ── Key-value memory ───────────────────────────────────────────────────────

    def store(self, key: str, value: Any, category: str | None = None) -> None:
        """
        Persist a fact under *key*.  Overwrites existing value if the key
        already exists.

        Parameters
        ----------
        key      : Unique identifier string.
        value    : Any JSON-serialisable Python value.
        category : Optional label for grouping related facts.
        """
        with self._Session() as session:
            existing = session.scalars(
                select(MemoryEntry).where(MemoryEntry.key == key)
            ).first()
            if existing:
                existing.value = json.dumps(value)
                existing.category = category
                existing.updated = datetime.now(timezone.utc)
            else:
                session.add(MemoryEntry(
                    key=key,
                    value=json.dumps(value),
                    category=category,
                ))
            session.commit()
        log.debug(f"Memory stored: {key!r}")

    def recall(self, key: str, default: Any = None) -> Any:
        """
        Retrieve the value stored under *key*.

        Returns *default* (None by default) if the key doesn't exist.
        """
        with self._Session() as session:
            entry = session.scalars(
                select(MemoryEntry).where(MemoryEntry.key == key)
            ).first()
            if entry is None:
                return default
            return json.loads(entry.value)

    def forget(self, key: str) -> bool:
        """
        Delete a memory entry.  Returns True if the entry existed, else False.
        """
        with self._Session() as session:
            rows = session.execute(
                delete(MemoryEntry).where(MemoryEntry.key == key)
            ).rowcount
            session.commit()
        return rows > 0

    def list_memories(
        self,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Return all memory entries, optionally filtered by *category*.

        Returns a list of dicts with keys: id, key, value, category, updated.
        """
        with self._Session() as session:
            stmt = select(MemoryEntry)
            if category:
                stmt = stmt.where(MemoryEntry.category == category)
            stmt = stmt.order_by(MemoryEntry.updated.desc()).limit(limit)
            rows = session.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "key": r.key,
                "value": json.loads(r.value),
                "category": r.category,
                "updated": r.updated.isoformat() if r.updated else None,
            }
            for r in rows
        ]

    def search_similar(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Placeholder for future vector similarity search.

        Currently returns entries whose key contains the query string
        (case-insensitive substring match).  Replace this body with a
        vector index call when you add embeddings.
        """
        q = query.lower()
        with self._Session() as session:
            rows = session.scalars(
                select(MemoryEntry).limit(limit * 5)   # over-fetch then filter
            ).all()
        return [
            {
                "key": r.key,
                "value": json.loads(r.value),
                "category": r.category,
            }
            for r in rows
            if q in r.key.lower() or q in r.value.lower()
        ][:limit]

    # ── Conversation log ───────────────────────────────────────────────────────

    def log_message(
        self,
        role: str,
        content: str,
        plugin: str | None = None,
    ) -> None:
        """
        Append one conversational turn to the persistent log.

        Parameters
        ----------
        role    : "user" | "assistant" | "system"
        content : Message text.
        plugin  : Name of the originating plugin (optional, for attribution).
        """
        with self._Session() as session:
            session.add(ConversationEntry(role=role, content=content, plugin=plugin))
            session.commit()

    def get_history(
        self,
        limit: int = 20,
        plugin: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return the most recent *limit* conversation turns, newest-last.

        Parameters
        ----------
        limit  : Maximum number of entries to return.
        plugin : If set, only return entries for that plugin.
        """
        with self._Session() as session:
            stmt = select(ConversationEntry)
            if plugin:
                stmt = stmt.where(ConversationEntry.plugin == plugin)
            # Fetch newest first, then reverse so callers get oldest-first order
            stmt = stmt.order_by(ConversationEntry.ts.desc()).limit(limit)
            rows = list(reversed(session.scalars(stmt).all()))
        return [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "plugin": r.plugin,
                "ts": r.ts.isoformat() if r.ts else None,
            }
            for r in rows
        ]

    def clear_history(self) -> int:
        """Delete all conversation log entries. Returns the count deleted."""
        with self._Session() as session:
            count = session.execute(delete(ConversationEntry)).rowcount
            session.commit()
        log.warning(f"Conversation history cleared ({count} entries deleted)")
        return count
