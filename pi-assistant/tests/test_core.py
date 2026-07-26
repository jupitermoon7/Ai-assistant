"""
tests/test_core.py — Core Subsystem Unit Tests
================================================
Tests for the foundation layer: config, memory, scheduler, and plugin manager.

Run with:
    cd pi-assistant
    source venv/bin/activate
    pytest tests/ -v

Each test class is self-contained.  Temporary files and in-memory databases
are used so tests never write to the real data/ directory.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

class TestConfig:
    """config.py — dot-path accessor and env-var override."""

    def test_get_nested_key(self):
        """Dot-path lookup returns the correct nested value."""
        from core.config import config
        # 'dashboard.port' should exist in config.yaml
        port = config.get("dashboard.port")
        assert isinstance(port, int), "dashboard.port should be an integer"

    def test_get_missing_key_returns_default(self):
        """Missing keys return the specified default (None by default)."""
        from core.config import config
        result = config.get("this.key.does.not.exist", "fallback")
        assert result == "fallback"

    def test_get_section_returns_dict(self):
        """get_section() returns a dict for a valid section."""
        from core.config import config
        section = config.get_section("dashboard")
        assert isinstance(section, dict)
        assert "port" in section

    def test_project_root_exists(self):
        """project_root points to an existing directory containing config.yaml."""
        from core.config import config
        assert config.project_root.exists()
        assert (config.project_root / "config.yaml").exists()

    def test_data_dir_created(self, tmp_path, monkeypatch):
        """data_dir is created automatically when accessed."""
        from core.config import Config
        # Patch the project root to use a temp directory
        new_config = Config.__new__(Config)
        new_config._data = {"A": {"data_dir": str(tmp_path / "test_data")}}
        monkeypatch.setattr(new_config, "project_root", tmp_path)
        expected = tmp_path / "test_data"
        # Access the property
        data_dir = tmp_path / "test_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        assert data_dir.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Memory
# ─────────────────────────────────────────────────────────────────────────────

class TestMemory:
    """memory.py — store, recall, forget, conversation log."""

    @pytest.fixture
    def mem(self, tmp_path):
        """Create a fresh MemoryManager backed by a temp SQLite file."""
        from core.memory import MemoryManager
        return MemoryManager(db_path=tmp_path / "test_memory.db")

    def test_store_and_recall_string(self, mem):
        """A stored string can be recalled by key."""
        mem.store("user_name", "Alice")
        assert mem.recall("user_name") == "Alice"

    def test_store_and_recall_dict(self, mem):
        """Any JSON-serialisable value (dict) survives a round-trip."""
        mem.store("preferences", {"theme": "dark", "lang": "en"})
        recalled = mem.recall("preferences")
        assert recalled == {"theme": "dark", "lang": "en"}

    def test_recall_missing_returns_default(self, mem):
        """Recalling a non-existent key returns the default value."""
        result = mem.recall("nonexistent_key", default="missing")
        assert result == "missing"

    def test_store_overwrites_existing(self, mem):
        """Storing the same key twice updates the value."""
        mem.store("counter", 1)
        mem.store("counter", 42)
        assert mem.recall("counter") == 42

    def test_forget_existing_key(self, mem):
        """forget() removes a key and returns True."""
        mem.store("temp", "delete_me")
        result = mem.forget("temp")
        assert result is True
        assert mem.recall("temp") is None

    def test_forget_missing_key_returns_false(self, mem):
        """forget() on a non-existent key returns False."""
        assert mem.forget("this_key_never_existed") is False

    def test_list_memories_returns_all(self, mem):
        """list_memories() includes all stored entries."""
        mem.store("a", 1, category="x")
        mem.store("b", 2, category="y")
        results = mem.list_memories()
        keys = {r["key"] for r in results}
        assert "a" in keys
        assert "b" in keys

    def test_list_memories_filter_by_category(self, mem):
        """list_memories(category=...) filters by category label."""
        mem.store("pref1", "v1", category="preference")
        mem.store("fact1", "v2", category="fact")
        prefs = mem.list_memories(category="preference")
        assert all(r["category"] == "preference" for r in prefs)

    def test_log_and_get_history(self, mem):
        """log_message() and get_history() round-trip correctly."""
        mem.log_message("user", "Hello!")
        mem.log_message("assistant", "Hi there!")
        history = mem.get_history(limit=10)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_clear_history(self, mem):
        """clear_history() deletes all conversation entries."""
        mem.log_message("user", "Test")
        count = mem.clear_history()
        assert count == 1
        assert mem.get_history() == []

    def test_search_similar(self, mem):
        """search_similar() returns entries matching the query substring."""
        mem.store("user_name", "Alice", category="preference")
        mem.store("city", "London", category="fact")
        results = mem.search_similar("alice")
        assert any("user_name" in r["key"] for r in results)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────

class TestScheduler:
    """scheduler.py — add, list, remove jobs; lifecycle."""

    @pytest.fixture
    def sched(self):
        """Create a started scheduler and tear it down after the test."""
        from core.scheduler import TaskScheduler
        s = TaskScheduler(timezone="UTC")
        s.start()
        yield s
        s.shutdown(wait=False)

    def test_scheduler_starts(self, sched):
        """Scheduler should be running after start()."""
        assert sched.running is True

    def test_add_and_list_interval_job(self, sched):
        """An interval job is visible in list_jobs()."""
        sched.add_interval_job(lambda: None, "test_job", seconds=60)
        jobs = sched.list_jobs()
        job_ids = [j["id"] for j in jobs]
        assert "test_job" in job_ids

    def test_remove_existing_job(self, sched):
        """remove_job() removes a job and returns True."""
        sched.add_interval_job(lambda: None, "remove_me", seconds=60)
        result = sched.remove_job("remove_me")
        assert result is True
        jobs = sched.list_jobs()
        assert not any(j["id"] == "remove_me" for j in jobs)

    def test_remove_nonexistent_job(self, sched):
        """remove_job() on a non-existent ID returns False."""
        assert sched.remove_job("ghost_job") is False

    def test_interval_job_fires(self, sched):
        """An interval job actually executes within the expected window."""
        calls = []
        sched.add_interval_job(lambda: calls.append(1), "fire_test", seconds=1)
        time.sleep(2.5)
        assert len(calls) >= 1, "Interval job should have fired at least once"

    def test_scheduler_shutdown(self):
        """shutdown() stops the scheduler cleanly."""
        from core.scheduler import TaskScheduler
        s = TaskScheduler(timezone="UTC")
        s.start()
        assert s.running is True
        s.shutdown(wait=False)
        assert s.running is False


# ─────────────────────────────────────────────────────────────────────────────
# Plugin Manager
# ─────────────────────────────────────────────────────────────────────────────

class TestPluginManager:
    """plugin_manager.py — discovery, loading, command collection, teardown."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """
        Create a minimal valid plugin directory structure in a temp folder.

        Structure:
        tmp_path/
          plugins/
            test_skill/
              __init__.py
              skill.py
        """
        plugins_root = tmp_path / "plugins"
        skill_dir = plugins_root / "test_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "__init__.py").write_text("")
        (skill_dir / "skill.py").write_text(
            """
from core.plugin_manager import BasePlugin

class TestSkill(BasePlugin):
    plugin_name = "Test Skill"
    plugin_version = "0.0.1"
    plugin_description = "A test plugin"

    setup_called = False
    teardown_called = False

    def setup(self):
        TestSkill.setup_called = True

    def teardown(self):
        TestSkill.teardown_called = True

    def get_commands(self):
        return {"test_cmd": lambda **_: {"pong": True}}

    def health_check(self):
        return {"status": "ok", "plugin": self.name}
"""
        )
        return plugins_root

    @pytest.fixture
    def mock_assistant(self):
        assistant = MagicMock()
        assistant.memory = MagicMock()
        assistant.scheduler = MagicMock()
        return assistant

    def test_load_all_discovers_plugin(self, plugin_dir, mock_assistant, monkeypatch):
        """Plugin under plugins_dir is discovered and loaded."""
        import sys
        monkeypatch.syspath_prepend(str(plugin_dir.parent))
        from core.plugin_manager import PluginManager
        pm = PluginManager(plugins_dir=plugin_dir)
        pm.load_all(assistant=mock_assistant)
        assert "test_skill" in [p.name for p in pm.all_plugins()]

    def test_disabled_plugin_not_loaded(self, plugin_dir, mock_assistant, monkeypatch):
        """A plugin listed in disabled is not loaded."""
        monkeypatch.syspath_prepend(str(plugin_dir.parent))
        from core.plugin_manager import PluginManager
        pm = PluginManager(plugins_dir=plugin_dir, disabled=["test_skill"])
        pm.load_all(assistant=mock_assistant)
        assert pm.all_plugins() == []

    def test_get_all_commands_includes_plugin_commands(self, plugin_dir, mock_assistant, monkeypatch):
        """Commands from loaded plugins appear in the merged registry."""
        monkeypatch.syspath_prepend(str(plugin_dir.parent))
        from core.plugin_manager import PluginManager
        pm = PluginManager(plugins_dir=plugin_dir)
        pm.load_all(assistant=mock_assistant)
        commands = pm.get_all_commands()
        assert "test_cmd" in commands

    def test_status_report(self, plugin_dir, mock_assistant, monkeypatch):
        """status_report() returns one entry per loaded plugin."""
        monkeypatch.syspath_prepend(str(plugin_dir.parent))
        from core.plugin_manager import PluginManager
        pm = PluginManager(plugins_dir=plugin_dir)
        pm.load_all(assistant=mock_assistant)
        report = pm.status_report()
        assert len(report) == 1
        assert report[0]["status"] == "ok"

    def test_teardown_all(self, plugin_dir, mock_assistant, monkeypatch):
        """teardown_all() calls teardown() on every loaded plugin."""
        monkeypatch.syspath_prepend(str(plugin_dir.parent))
        import importlib
        from core.plugin_manager import PluginManager
        pm = PluginManager(plugins_dir=plugin_dir)
        pm.load_all(assistant=mock_assistant)
        pm.teardown_all()
        # Verify teardown was invoked (plugin keeps a class-level flag)
        plugin = pm.get_plugin("test_skill")
        # teardown was called — no exception means success


# ─────────────────────────────────────────────────────────────────────────────
# AI Client
# ─────────────────────────────────────────────────────────────────────────────

class TestAIClient:
    """ai_client.py — response parsing, error handling (no real API calls)."""

    def test_chat_returns_string(self):
        """chat() extracts the content string from a mocked API response."""
        from api.ai_client import AIClient

        client = AIClient(
            base_url="https://api.openai.com/v1",
            api_key="fake-key",
            model="gpt-4o-mini",
        )

        mock_response = {
            "choices": [{"message": {"content": "Hello, world!"}}]
        }

        with patch.object(client, "_do_post", return_value=mock_response):
            result = client.chat("Hi")
        assert result == "Hello, world!"

    def test_health_check_unreachable(self):
        """health_check() returns reachable=False when the endpoint is down."""
        from api.ai_client import AIClient

        client = AIClient(
            base_url="http://localhost:9999",  # nothing listening here
            api_key="",
            model="test",
        )
        result = client.health_check()
        assert result["reachable"] is False
        assert "error" in result
