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

DEFAULT_TICKERS = [
    "AIP",
    "PLTR",
    "INTC",
    "SMR",
    "OKLO",
    "NVDA",
    "ALAB",
    "TEM",
    "STX",
    "MAGS",
    "XE",
    "PSMT",
    "QCOM",
    "SMCI",
    "BE",
    "LUMI.ST",
    "AEM",
    "SPY",
    "VRT",
    "KLAC",
    "ASML",
    "SOXX",
    "SMH",
    "CLS",
    "VMAV",
    "GLNG",
    "FLNG",
    "LNG",
    "AMZN",
    "SIL=F",
    "ACB",
    "TSLA",
    "COST",
    "META",
    "ARM",
    "AMD",
    "HG=F",
    "AEP",
]

DEFAULT_SEC_CIK_MAP = {
    "NVDA": "0001045810",
    "AMD": "0000002488",
    "TSLA": "0001318605",
    "MSFT": "0000789019",
    "AAPL": "0000320193",
    "META": "0001326801",
    "GOOGL": "0001652044",
    "AVGO": "0001730168",
    "PLTR": "0001321655",
    "SMCI": "0001375365",
}

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

DEFAULT_IPO_FEEDS = [
    "https://www.nasdaq.com/market-activity/ipos",
    "https://www.marketwatch.com/tools/ipo-calendar",
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
    enable_sec_monitor: bool
    sec_user_agent: str
    sec_check_interval_seconds: int
    sec_forms_to_track: list[str]
    sec_cik_map: dict[str, str]
    investor_relations_feeds: list[str]
    enable_sec_text_extraction: bool
    sec_text_max_chars: int
    sec_summary_min_confidence: int
    enable_ipo_monitor: bool
    ipo_check_interval_seconds: int
    ipo_lookahead_days: int
    ipo_alert_min_score: int
    market_data_provider: str
    ipo_feeds: list[str]
    ipo_calendar_sources: list[str]
    ipo_manual_csv_path: Path


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

    tickers = _normalize_tickers(watchlist.get("tickers", DEFAULT_TICKERS))
    categories = [category.lower() for category in watchlist.get("categories", DEFAULT_CATEGORIES)]
    feeds = watchlist.get("rss_feeds", DEFAULT_RSS_FEEDS)
    sec_cik_map = {
        str(ticker).upper(): str(cik).zfill(10)
        for ticker, cik in watchlist.get("sec_cik_map", DEFAULT_SEC_CIK_MAP).items()
    }
    ir_feeds = watchlist.get("investor_relations_feeds", [])
    ipo_feeds = watchlist.get("ipo_feeds", DEFAULT_IPO_FEEDS)
    ipo_calendar_sources = [
        source.strip().lower()
        for source in os.getenv("IPO_CALENDAR_SOURCES", "nasdaq_api,stockanalysis_csv,manual_csv").split(",")
        if source.strip()
    ]
    forms_to_track = [
        form.strip().upper()
        for form in os.getenv("SEC_FORMS_TO_TRACK", "8-K,10-Q,10-K,S-1,SC 13G,SC 13D,4").split(",")
        if form.strip()
    ]

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
        enable_sec_monitor=_get_bool("ENABLE_SEC_MONITOR", True),
        sec_user_agent=os.getenv("SEC_USER_AGENT", "StockBot/0.1 contact:madridchili96@gmail.com"),
        sec_check_interval_seconds=_get_int("SEC_CHECK_INTERVAL_SECONDS", 900),
        sec_forms_to_track=forms_to_track,
        sec_cik_map=sec_cik_map,
        investor_relations_feeds=ir_feeds,
        enable_sec_text_extraction=_get_bool("ENABLE_SEC_TEXT_EXTRACTION", True),
        sec_text_max_chars=_get_int("SEC_TEXT_MAX_CHARS", 12000),
        sec_summary_min_confidence=_get_int("SEC_SUMMARY_MIN_CONFIDENCE", 50),
        enable_ipo_monitor=_get_bool("ENABLE_IPO_MONITOR", True),
        ipo_check_interval_seconds=_get_int("IPO_CHECK_INTERVAL_SECONDS", 3600),
        ipo_lookahead_days=_get_int("IPO_LOOKAHEAD_DAYS", 30),
        ipo_alert_min_score=_get_int("IPO_ALERT_MIN_SCORE", 70),
        market_data_provider=os.getenv("MARKET_DATA_PROVIDER", "stooq").lower(),
        ipo_feeds=ipo_feeds,
        ipo_calendar_sources=ipo_calendar_sources,
        ipo_manual_csv_path=Path(os.getenv("IPO_MANUAL_CSV_PATH", ROOT_DIR / "config" / "ipo_calendar.csv")),
    )


def _normalize_tickers(tickers: list[str]) -> list[str]:
    """Deduplicate and normalize tickers while preserving futures/suffix symbols."""
    normalized = []
    seen = set()
    for ticker in tickers:
        value = str(ticker).strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
