"""Shared utility functions."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


def configure_logging(log_file: Path) -> None:
    """Configure console and rotating file logging."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler], force=True)


def is_important_signal(analysis: dict[str, Any], threshold: int) -> bool:
    """Return True when an analysis should trigger an alert."""
    try:
        importance_score = int(analysis.get("importance_score", 0))
    except (TypeError, ValueError):
        importance_score = 0

    action = str(analysis.get("action", "")).lower()
    return importance_score >= threshold or action == "alert"
