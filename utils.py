"""Shared utilities for StockBot."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


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


def should_send_signal_alert(signal: dict) -> bool:
    """Return True when a signal qualifies for an email alert."""
    action = str(signal.get("action", "")).lower()
    try:
        confidence = int(signal.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0

    return action in {"possible_buy", "possible_sell"} and confidence >= 70
