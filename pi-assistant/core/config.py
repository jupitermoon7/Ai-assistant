"""
core/config.py — Configuration Loader
======================================
Loads config.yaml and merges in environment variables from .env.

Environment variables always take precedence over config.yaml values,
so you can safely deploy config.yaml to version control and keep secrets
in .env on the device.

Usage
-----
    from core.config import config

    port = config.get("dashboard.port")           # nested dot-path lookup
    key  = config.get("dashboard.secret_key")     # returns env override if set
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# ── Locate project root relative to this file ─────────────────────────────────
# This file is at  <project_root>/core/config.py
# Project root is one level up.
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_CONFIG_FILE = _PROJECT_ROOT / "config.yaml"
_ENV_FILE = _PROJECT_ROOT / ".env"


class Config:
    """
    Thin wrapper around the merged YAML + env-var configuration.

    Dot-path accessor (``config.get("a.b.c")``) walks the nested dict so
    callers never need to deal with raw dict access.
    """

    def __init__(self) -> None:
        # Load .env first so os.environ is populated before we read YAML
        if _ENV_FILE.exists():
            load_dotenv(_ENV_FILE)

        self._data: dict[str, Any] = self._load_yaml()
        self._apply_env_overrides()

    # ── Public interface ───────────────────────────────────────────────────────

    def get(self, path: str, default: Any = None) -> Any:
        """
        Retrieve a value using dot-separated key path.

        Examples
        --------
        config.get("dashboard.port")      → 8080
        config.get("ai.default_model")    → "gpt-4o-mini"
        config.get("missing.key", "x")    → "x"
        """
        keys = path.split(".")
        node: Any = self._data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def get_section(self, section: str) -> dict[str, Any]:
        """Return an entire top-level section as a dict (empty dict if missing)."""
        return self._data.get(section, {})

    @property
    def project_root(self) -> Path:
        """Absolute path to the project root directory."""
        return _PROJECT_ROOT

    @property
    def data_dir(self) -> Path:
        """Absolute path to the data directory (created on first access)."""
        data_dir = _PROJECT_ROOT / self.get("A.data_dir", "data")
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_yaml(self) -> dict[str, Any]:
        if not _CONFIG_FILE.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {_CONFIG_FILE}\n"
                "Make sure config.yaml exists in the project root."
            )
        with open(_CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}

    def _apply_env_overrides(self) -> None:
        """
        Map well-known environment variables into the config dict.

        Adding a new env-var override: add a line here following the pattern
        ``self._set("section.key", os.getenv("ENV_VAR_NAME"))``.
        """
        self._set("dashboard.secret_key",   os.getenv("DASHBOARD_SECRET_KEY"))
        self._set("auth.username",          os.getenv("DASHBOARD_USERNAME"))
        self._set("auth.password_hash",     os.getenv("DASHBOARD_PASSWORD_HASH"))
        self._set("ai.base_url",            os.getenv("AI_BASE_URL"))
        self._set("ai.default_model",       os.getenv("AI_DEFAULT_MODEL"))
        self._set("ai.api_key",             os.getenv("OPENAI_API_KEY"))

    def _set(self, path: str, value: Any) -> None:
        """Write *value* into the nested dict at *path*. Skips None values."""
        if value is None:
            return
        keys = path.split(".")
        node = self._data
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value


# ── Module-level singleton ─────────────────────────────────────────────────────
# Import this object everywhere rather than instantiating Config() repeatedly.
config = Config()
