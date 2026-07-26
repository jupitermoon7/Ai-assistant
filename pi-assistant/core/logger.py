"""
core/logger.py — Centralised Structured Logging
=================================================
Sets up a single logger used throughout the whole application.

Features
--------
- Console output with Rich for readable, colour-coded development logs.
- Rotating file handler so logs don't fill the Pi's SD card.
- Log level controlled by ``config.yaml`` (or ``LOG_LEVEL`` env var).
- Single ``get_logger(name)`` factory so every module gets a properly
  named child logger without duplicating setup code.

Usage
-----
    from core.logger import get_logger

    log = get_logger(__name__)
    log.info("Assistant started")
    log.error("Something went wrong", exc_info=True)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

# We import config lazily inside setup_logging() to avoid circular imports
# (config.py imports nothing from core/).

_SETUP_DONE = False


def setup_logging(log_level: str = "INFO", log_dir: Path | None = None) -> None:
    """
    Configure the root logger.  Call this once at startup (main.py does this).

    Parameters
    ----------
    log_level : str
        One of DEBUG | INFO | WARNING | ERROR | CRITICAL.
    log_dir : Path | None
        Directory for the rotating log file.  If None, file logging is skipped.
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # ── Console handler (Rich for pretty output in dev; plain in production) ──
    try:
        from rich.logging import RichHandler
        console_handler: logging.Handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            log_time_format="[%H:%M:%S]",
        )
        console_fmt = "%(message)s"
    except ImportError:  # graceful fallback if Rich isn't installed yet
        console_handler = logging.StreamHandler()
        console_fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"

    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter(console_fmt))
    root.addHandler(console_handler)

    # ── Rotating file handler ─────────────────────────────────────────────────
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "assistant.log"

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=5,               # keep the 5 most recent files
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_fmt = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
        file_handler.setFormatter(logging.Formatter(file_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "werkzeug", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _SETUP_DONE = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a named child logger.

    Always call this at module level::

        log = get_logger(__name__)

    This ensures the logger name matches the module path, making it easy to
    trace where a log message came from.
    """
    return logging.getLogger(name)
