"""Configuration for the local email-based StockBot system."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = ROOT_DIR / "config"
DEFAULT_WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"


DEFAULT_RSS_FEEDS = [
    "https://finance.yahoo.com/rss/headline?s=NVDA",
    "https://finance.yahoo.com/rss/headline?s=TSLA",
    "https://finance.yahoo.com/rss/headline?s=AMD",
    "https://finance.yahoo.com/rss/headline?s=MSFT",
    "https://finance.yahoo.com/rss/headline?s=AAPL",
    "https://finance.yahoo.com/rss/headline?s=META",
    "https://finance.yahoo.com/rss/headline?s=GOOGL",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
]

DEFAULT_TICKERS = ["NVDA", "AMD", "TSLA", "MSFT", "AAPL", "PLTR", "SMCI", "GOOGL", "META", "AVGO"]

DEFAULT_CATEGORIES = [
    "artificial intelligence",
    "semiconductor",
    "chips",
    "data center",
    "GLP-1",
    "obesity drug",
    "defense",
    "energy",
    "interest rates",
    "inflation",
    "earnings",
    "guidance",
]


@dataclass(frozen=True)
class AppConfig:
    """Runtime settings loaded from .env, environment variables, and JSON config."""

    database_path: Path
    log_file: Path
    watchlist_path: Path
    watchlist_tickers: list[str]
    watchlist_categories: list[str]
    rss_feeds: list[str]
    ollama_model: str
    ollama_url: str
    email_address: str | None
    email_app_password: str | None
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    email_to: str | None
    enable_inbox_monitor: bool
    email_check_interval_seconds: int
    news_check_interval_seconds: int
    http_timeout_seconds: int
    enable_daily_report: bool
    daily_report_hour: int
    daily_report_minute: int
    daily_report_lookback_hours: int
    daily_report_min_confidence: int
    daily_report_to: str | None
    reports_dir: Path


def _read_json(path: Path) -> dict[str, Any]:
    """Read JSON config when present."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean value from the environment."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    """Read an integer value from the environment."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_config() -> AppConfig:
    """Load StockBot configuration."""
    load_dotenv()

    watchlist_path = Path(os.getenv("STOCKBOT_WATCHLIST_PATH", DEFAULT_WATCHLIST_PATH))
    watchlist = _read_json(watchlist_path)

    tickers = [ticker.upper() for ticker in watchlist.get("tickers", DEFAULT_TICKERS)]
    categories = [category.lower() for category in watchlist.get("categories", DEFAULT_CATEGORIES)]
    feeds = watchlist.get("rss_feeds", DEFAULT_RSS_FEEDS)

    return AppConfig(
        database_path=Path(os.getenv("STOCKBOT_DATABASE_PATH", ROOT_DIR / "database" / "stockbot.sqlite3")),
        log_file=Path(os.getenv("STOCKBOT_LOG_FILE", ROOT_DIR / "logs" / "stockbot.log")),
        watchlist_path=watchlist_path,
        watchlist_tickers=tickers,
        watchlist_categories=categories,
        rss_feeds=feeds,
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
        email_address=os.getenv("EMAIL_ADDRESS"),
        email_app_password=os.getenv("EMAIL_APP_PASSWORD"),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_get_int("SMTP_PORT", 587),
        imap_host=os.getenv("IMAP_HOST", "imap.gmail.com"),
        imap_port=_get_int("IMAP_PORT", 993),
        email_to=os.getenv("EMAIL_TO") or os.getenv("EMAIL_ADDRESS"),
        enable_inbox_monitor=_get_bool("ENABLE_INBOX_MONITOR", True),
        email_check_interval_seconds=_get_int("EMAIL_CHECK_INTERVAL_SECONDS", 120),
        news_check_interval_seconds=_get_int("NEWS_CHECK_INTERVAL_SECONDS", 300),
        http_timeout_seconds=_get_int("STOCKBOT_HTTP_TIMEOUT_SECONDS", 30),
        enable_daily_report=_get_bool("ENABLE_DAILY_REPORT", True),
        daily_report_hour=_get_int("DAILY_REPORT_HOUR", 7),
        daily_report_minute=_get_int("DAILY_REPORT_MINUTE", 30),
        daily_report_lookback_hours=_get_int("DAILY_REPORT_LOOKBACK_HOURS", 24),
        daily_report_min_confidence=_get_int("DAILY_REPORT_MIN_CONFIDENCE", 50),
        daily_report_to=os.getenv("DAILY_REPORT_TO") or os.getenv("EMAIL_TO") or os.getenv("EMAIL_ADDRESS"),
        reports_dir=Path(os.getenv("STOCKBOT_REPORTS_DIR", ROOT_DIR / "reports")),
    )
