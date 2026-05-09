"""Configuration loading for the local stock intelligence system."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = ROOT_DIR / "config"
DEFAULT_WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration values."""

    database_path: Path
    log_file: Path
    watchlist_path: Path
    watchlist_tickers: list[str]
    watchlist_categories: list[str]
    rss_feeds: list[str]
    ollama_url: str
    ollama_model: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    telegram_enabled: bool
    poll_interval_seconds: int
    poll_once: bool
    http_timeout_seconds: int
    alert_score_threshold: int


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file and return an empty dictionary when it is missing."""
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean from an environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    """Load configuration from environment variables and the watchlist file."""
    watchlist_path = Path(os.getenv("STOCKBOT_WATCHLIST_PATH", DEFAULT_WATCHLIST_PATH))
    watchlist = _read_json(watchlist_path)

    tickers = [ticker.upper() for ticker in watchlist.get("tickers", [])]
    categories = [category.lower() for category in watchlist.get("categories", [])]
    feeds = watchlist.get("rss_feeds", [])

    return AppConfig(
        database_path=Path(os.getenv("STOCKBOT_DATABASE_PATH", ROOT_DIR / "database" / "stockbot.sqlite3")),
        log_file=Path(os.getenv("STOCKBOT_LOG_FILE", ROOT_DIR / "logs" / "stockbot.log")),
        watchlist_path=watchlist_path,
        watchlist_tickers=tickers,
        watchlist_categories=categories,
        rss_feeds=feeds,
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        telegram_enabled=_get_bool("TELEGRAM_ENABLED", False),
        poll_interval_seconds=int(os.getenv("STOCKBOT_POLL_INTERVAL_SECONDS", "900")),
        poll_once=_get_bool("STOCKBOT_POLL_ONCE", True),
        http_timeout_seconds=int(os.getenv("STOCKBOT_HTTP_TIMEOUT_SECONDS", "30")),
        alert_score_threshold=int(os.getenv("STOCKBOT_ALERT_SCORE_THRESHOLD", "7")),
    )
