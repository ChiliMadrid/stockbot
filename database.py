"""SQLite database setup and persistence helpers."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any

from rss_monitor import Article
from sec_edgar_client import SECFiling


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    headline TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source TEXT,
    published_at TEXT,
    matched_symbol TEXT,
    matched_category TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    sentiment TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    action TEXT NOT NULL,
    urgency TEXT NOT NULL,
    reason TEXT,
    risk_warning TEXT,
    raw_model_response TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(article_id) REFERENCES articles(id)
);

CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,
    from_address TEXT,
    to_address TEXT,
    subject TEXT,
    body TEXT,
    related_signal_id INTEGER,
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(related_signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS chatbot_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_message_id INTEGER,
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(email_message_id) REFERENCES email_messages(id)
);

CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL UNIQUE,
    report_path TEXT NOT NULL,
    emailed INTEGER DEFAULT 0,
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sec_filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    cik TEXT NOT NULL,
    form TEXT NOT NULL,
    accession TEXT NOT NULL UNIQUE,
    filing_date TEXT,
    report_date TEXT,
    primary_document TEXT,
    filing_url TEXT NOT NULL,
    headline TEXT NOT NULL,
    processed INTEGER DEFAULT 0,
    filing_text_path TEXT,
    filing_summary TEXT,
    filing_key_points TEXT,
    filing_risks TEXT,
    text_extracted INTEGER DEFAULT 0,
    summarized_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ipos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT,
    ticker TEXT,
    exchange TEXT,
    ipo_date TEXT,
    expected_price_range TEXT,
    final_ipo_price REAL,
    opening_price REAL,
    current_price REAL,
    source_url TEXT NOT NULL,
    source TEXT,
    source_quality INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    prediction_summary TEXT,
    prediction_score INTEGER DEFAULT 0,
    expected_direction TEXT,
    watch_action TEXT,
    key_drivers TEXT,
    risks TEXT,
    confidence INTEGER DEFAULT 0,
    raw_model_response TEXT,
    notes TEXT,
    alerted INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_url, ticker, ipo_date)
);

CREATE TABLE IF NOT EXISTS ipo_price_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ipo_id INTEGER NOT NULL,
    ticker TEXT,
    final_ipo_price REAL,
    opening_price REAL,
    current_price REAL,
    provider TEXT,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(ipo_id) REFERENCES ipos(id)
);

CREATE TABLE IF NOT EXISTS price_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    ticker TEXT,
    current_price REAL,
    prior_close REAL,
    percent_move REAL,
    volume REAL,
    gap_percent REAL,
    trend_confirmed INTEGER DEFAULT 0,
    provider TEXT,
    model_confidence INTEGER DEFAULT 0,
    source_score INTEGER DEFAULT 0,
    price_volume_score INTEGER DEFAULT 0,
    risk_penalty INTEGER DEFAULT 0,
    final_signal_score INTEGER DEFAULT 0,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    ticker TEXT,
    horizon TEXT NOT NULL,
    alert_price REAL,
    future_price REAL,
    percent_change REAL,
    outcome TEXT,
    due_at TEXT NOT NULL,
    checked_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_id, horizon),
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(confidence);
CREATE INDEX IF NOT EXISTS idx_email_messages_created_at ON email_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_created_at ON chatbot_conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_daily_reports_report_date ON daily_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_sec_filings_accession ON sec_filings(accession);
CREATE INDEX IF NOT EXISTS idx_sec_filings_created_at ON sec_filings(created_at);
CREATE INDEX IF NOT EXISTS idx_ipos_status ON ipos(status);
CREATE INDEX IF NOT EXISTS idx_ipos_ipo_date ON ipos(ipo_date);
CREATE INDEX IF NOT EXISTS idx_ipo_price_checks_checked_at ON ipo_price_checks(checked_at);
CREATE INDEX IF NOT EXISTS idx_price_confirmations_signal_id ON price_confirmations(signal_id);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_due_at ON signal_outcomes(due_at);
"""


def initialize_database(database_path: Path) -> None:
    """Create the database and all required tables."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)
        _migrate_sec_filings(connection)
        _migrate_ipos(connection)


def _migrate_sec_filings(connection: sqlite3.Connection) -> None:
    """Add SEC text extraction columns to existing databases."""
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(sec_filings);").fetchall()
    }
    migrations = {
        "filing_text_path": "ALTER TABLE sec_filings ADD COLUMN filing_text_path TEXT;",
        "filing_summary": "ALTER TABLE sec_filings ADD COLUMN filing_summary TEXT;",
        "filing_key_points": "ALTER TABLE sec_filings ADD COLUMN filing_key_points TEXT;",
        "filing_risks": "ALTER TABLE sec_filings ADD COLUMN filing_risks TEXT;",
        "text_extracted": "ALTER TABLE sec_filings ADD COLUMN text_extracted INTEGER DEFAULT 0;",
        "summarized_at": "ALTER TABLE sec_filings ADD COLUMN summarized_at TEXT;",
    }
    for column, sql in migrations.items():
        if column not in existing_columns:
            connection.execute(sql)


def _migrate_ipos(connection: sqlite3.Connection) -> None:
    """Add IPO columns to existing databases when needed."""
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(ipos);").fetchall()
    }
    migrations = {
        "raw_model_response": "ALTER TABLE ipos ADD COLUMN raw_model_response TEXT;",
        "alerted": "ALTER TABLE ipos ADD COLUMN alerted INTEGER DEFAULT 0;",
        "updated_at": "ALTER TABLE ipos ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP;",
        "exchange": "ALTER TABLE ipos ADD COLUMN exchange TEXT;",
        "expected_price_range": "ALTER TABLE ipos ADD COLUMN expected_price_range TEXT;",
        "source": "ALTER TABLE ipos ADD COLUMN source TEXT;",
        "source_quality": "ALTER TABLE ipos ADD COLUMN source_quality INTEGER DEFAULT 0;",
        "notes": "ALTER TABLE ipos ADD COLUMN notes TEXT;",
    }
    for column, sql in migrations.items():
        if column not in existing_columns:
            connection.execute(sql)


def save_article(database_path: Path, article: Article) -> int | None:
    """Save an article and return its row ID."""
    sql = """
    INSERT OR IGNORE INTO articles (
        headline, url, source, published_at, matched_symbol, matched_category, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            sql,
            (
                article.headline,
                article.url,
                article.source,
                article.published_at,
                article.matched_symbol,
                article.matched_category,
                article.created_at,
            ),
        )
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)

        existing = connection.execute("SELECT id FROM articles WHERE url = ?", (article.url,)).fetchone()
        return int(existing[0]) if existing else None


def save_signal(database_path: Path, article_id: int, signal: dict[str, Any]) -> int:
    """Save a model signal for an article."""
    sql = """
    INSERT INTO signals (
        article_id, sentiment, confidence, action, urgency, reason, risk_warning, raw_model_response
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            sql,
            (
                article_id,
                signal.get("sentiment", "neutral"),
                int(signal.get("confidence", 0)),
                signal.get("action", "ignore"),
                signal.get("urgency", "low"),
                signal.get("reason", ""),
                signal.get("risk_warning", ""),
                signal.get("raw_model_response", ""),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def save_price_confirmation(
    database_path: Path,
    signal_id: int,
    confirmation: dict[str, Any],
    score: dict[str, int],
) -> int:
    """Save price confirmation and scoring details."""
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO price_confirmations (
                signal_id, ticker, current_price, prior_close, percent_move, volume,
                gap_percent, trend_confirmed, provider, model_confidence, source_score,
                price_volume_score, risk_penalty, final_signal_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                signal_id,
                confirmation.get("ticker"),
                _clean_optional_float(confirmation.get("current_price")),
                _clean_optional_float(confirmation.get("prior_close")),
                _clean_optional_float(confirmation.get("percent_move")),
                _clean_optional_float(confirmation.get("volume")),
                _clean_optional_float(confirmation.get("gap_percent")),
                1 if confirmation.get("trend_confirmed") else 0,
                confirmation.get("provider", ""),
                score.get("model_confidence", 0),
                score.get("source_score", 0),
                score.get("price_volume_score", 0),
                score.get("risk_penalty", 0),
                score.get("final_signal_score", 0),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def create_signal_outcome_rows(database_path: Path, signal_id: int, ticker: str | None, alert_price: float | None) -> None:
    """Create future outcome rows for an alerted signal."""
    horizons = {
        "1h": "+1 hours",
        "4h": "+4 hours",
        "1d": "+1 days",
        "5d": "+5 days",
    }
    with sqlite3.connect(database_path) as connection:
        for horizon, offset in horizons.items():
            connection.execute(
                """
                INSERT OR IGNORE INTO signal_outcomes (signal_id, ticker, horizon, alert_price, due_at)
                VALUES (?, ?, ?, ?, datetime('now', ?));
                """,
                (signal_id, ticker, alert_price, horizon, offset),
            )
        connection.commit()


def get_due_signal_outcomes(database_path: Path) -> list[dict]:
    """Return due signal outcomes that have not been checked."""
    sql = """
    SELECT id, signal_id, ticker, horizon, alert_price, due_at
    FROM signal_outcomes
    WHERE checked_at IS NULL AND datetime(due_at) <= datetime('now')
    ORDER BY due_at ASC
    LIMIT 100;
    """
    keys = ["id", "signal_id", "ticker", "horizon", "alert_price", "due_at"]
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(sql).fetchall()
    return [dict(zip(keys, row)) for row in rows]


def update_signal_outcome(
    database_path: Path,
    outcome_id: int,
    future_price: float | None,
    percent_change: float | None,
    outcome: str,
) -> None:
    """Update a signal outcome row."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE signal_outcomes
            SET future_price = ?, percent_change = ?, outcome = ?, checked_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (future_price, percent_change, outcome, outcome_id),
        )
        connection.commit()


def signal_already_exists(database_path: Path, url: str) -> bool:
    """Return True when a URL already has a saved signal."""
    sql = """
    SELECT signals.id
    FROM signals
    JOIN articles ON articles.id = signals.article_id
    WHERE articles.url = ?
    LIMIT 1;
    """
    with sqlite3.connect(database_path) as connection:
        return connection.execute(sql, (url,)).fetchone() is not None


def save_sec_filing(database_path: Path, filing: SECFiling | dict[str, Any]) -> int | None:
    """Save a SEC filing and return its row ID. Existing accessions are ignored."""
    data = filing if isinstance(filing, dict) else filing.__dict__
    sql = """
    INSERT OR IGNORE INTO sec_filings (
        ticker, cik, form, accession, filing_date, report_date, primary_document,
        filing_url, headline, processed, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            sql,
            (
                data.get("ticker"),
                data.get("cik"),
                data.get("form"),
                data.get("accession"),
                data.get("filing_date"),
                data.get("report_date"),
                data.get("primary_document"),
                data.get("filing_url"),
                data.get("headline"),
                1 if data.get("processed") else 0,
                data.get("created_at"),
            ),
        )
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        return None


def sec_filing_exists(database_path: Path, accession: str) -> bool:
    """Return True when a SEC accession is already stored."""
    with sqlite3.connect(database_path) as connection:
        return (
            connection.execute(
                "SELECT id FROM sec_filings WHERE accession = ? LIMIT 1;",
                (accession,),
            ).fetchone()
            is not None
        )


def mark_sec_filing_processed(database_path: Path, accession: str) -> None:
    """Mark a SEC filing as processed."""
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE sec_filings SET processed = 1 WHERE accession = ?;", (accession,))
        connection.commit()


def update_sec_filing_text_summary(
    database_path: Path,
    accession: str,
    filing_text_path: str | None,
    summary: dict[str, Any],
) -> None:
    """Save extracted SEC text metadata and summary fields."""
    key_points = summary.get("key_points", [])
    opportunities = summary.get("potential_opportunities", [])
    risks = summary.get("potential_risks", [])
    if opportunities:
        key_points = [*key_points, *[f"Opportunity: {item}" for item in opportunities]]

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE sec_filings
            SET filing_text_path = ?,
                filing_summary = ?,
                filing_key_points = ?,
                filing_risks = ?,
                text_extracted = ?,
                summarized_at = CURRENT_TIMESTAMP
            WHERE accession = ?;
            """,
            (
                filing_text_path,
                summary.get("summary", ""),
                json.dumps(key_points),
                json.dumps(risks),
                1 if filing_text_path else 0,
                accession,
            ),
        )
        connection.commit()


def log_run_event(database_path: Path, event_type: str, message: str) -> None:
    """Add a simple operational log event to SQLite."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO run_logs (event_type, message) VALUES (?, ?);",
            (event_type, message),
        )
        connection.commit()


def save_email_message(
    database_path: Path,
    direction: str,
    from_address: str,
    to_address: str,
    subject: str,
    body: str,
    related_signal_id: int | None,
    processed: bool,
) -> int:
    """Save an inbound or outbound email message."""
    sql = """
    INSERT INTO email_messages (
        direction, from_address, to_address, subject, body, related_signal_id, processed
    )
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            sql,
            (
                direction,
                from_address,
                to_address,
                subject,
                body,
                related_signal_id,
                1 if processed else 0,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def save_chatbot_conversation(
    database_path: Path,
    email_message_id: int,
    user_message: str,
    bot_response: str,
) -> int:
    """Save a chatbot conversation turn."""
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO chatbot_conversations (email_message_id, user_message, bot_response)
            VALUES (?, ?, ?);
            """,
            (email_message_id, user_message, bot_response),
        )
        connection.commit()
        return int(cursor.lastrowid)


def mark_email_processed(database_path: Path, email_message_id: int) -> None:
    """Mark an email message row as processed."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE email_messages SET processed = 1 WHERE id = ?;",
            (email_message_id,),
        )
        connection.commit()


def get_recent_signals(database_path: Path, lookback_hours: int, min_confidence: int) -> list[dict]:
    """Return recent signals with article metadata for daily reports."""
    sql = """
    SELECT
        signals.id,
        articles.id,
        articles.headline,
        articles.url,
        articles.source,
        articles.published_at,
        articles.matched_symbol,
        articles.matched_category,
        articles.created_at,
        signals.sentiment,
        signals.confidence,
        signals.action,
        signals.urgency,
        signals.reason,
        signals.risk_warning,
        signals.raw_model_response,
        signals.created_at,
        pc.current_price,
        pc.percent_move,
        pc.volume,
        pc.trend_confirmed,
        pc.final_signal_score,
        pc.price_volume_score,
        pc.risk_penalty
    FROM signals
    JOIN articles ON articles.id = signals.article_id
    LEFT JOIN (
        SELECT *
        FROM price_confirmations
        WHERE id IN (
            SELECT MAX(id)
            FROM price_confirmations
            GROUP BY signal_id
        )
    ) pc ON pc.signal_id = signals.id
    WHERE signals.confidence >= ?
      AND datetime(signals.created_at) >= datetime('now', ?)
    ORDER BY signals.confidence DESC, signals.created_at DESC;
    """
    lookback = f"-{int(lookback_hours)} hours"
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(sql, (int(min_confidence), lookback)).fetchall()

    keys = [
        "signal_id",
        "article_id",
        "headline",
        "url",
        "source",
        "published_at",
        "matched_symbol",
        "matched_category",
        "article_created_at",
        "sentiment",
        "confidence",
        "action",
        "urgency",
        "reason",
        "risk_warning",
        "raw_model_response",
        "signal_created_at",
        "current_price",
        "percent_move",
        "volume",
        "trend_confirmed",
        "final_signal_score",
        "price_volume_score",
        "risk_penalty",
    ]
    return [dict(zip(keys, row)) for row in rows]


def get_recent_price_confirmations(database_path: Path, lookback_hours: int = 24) -> list[dict]:
    """Return recent price confirmations."""
    sql = """
    SELECT signal_id, ticker, current_price, percent_move, volume, trend_confirmed,
           price_volume_score, risk_penalty, final_signal_score, checked_at
    FROM price_confirmations
    WHERE datetime(checked_at) >= datetime('now', ?)
    ORDER BY final_signal_score DESC, checked_at DESC
    LIMIT 50;
    """
    keys = [
        "signal_id",
        "ticker",
        "current_price",
        "percent_move",
        "volume",
        "trend_confirmed",
        "price_volume_score",
        "risk_penalty",
        "final_signal_score",
        "checked_at",
    ]
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(sql, (f"-{int(lookback_hours)} hours",)).fetchall()
    return [dict(zip(keys, row)) for row in rows]


def get_recent_signal_outcomes(database_path: Path, lookback_hours: int = 168) -> list[dict]:
    """Return recent checked signal outcomes."""
    sql = """
    SELECT signal_id, ticker, horizon, alert_price, future_price, percent_change, outcome, checked_at
    FROM signal_outcomes
    WHERE checked_at IS NOT NULL AND datetime(checked_at) >= datetime('now', ?)
    ORDER BY checked_at DESC
    LIMIT 50;
    """
    keys = ["signal_id", "ticker", "horizon", "alert_price", "future_price", "percent_change", "outcome", "checked_at"]
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(sql, (f"-{int(lookback_hours)} hours",)).fetchall()
    return [dict(zip(keys, row)) for row in rows]


def get_recent_sec_filings(database_path: Path, lookback_hours: int) -> list[dict]:
    """Return recent SEC filings for daily reports."""
    sql = """
    SELECT
        sec_filings.id,
        sec_filings.ticker,
        sec_filings.cik,
        sec_filings.form,
        sec_filings.accession,
        sec_filings.filing_date,
        sec_filings.report_date,
        sec_filings.primary_document,
        sec_filings.filing_url,
        sec_filings.headline,
        sec_filings.processed,
        sec_filings.filing_text_path,
        sec_filings.filing_summary,
        sec_filings.filing_key_points,
        sec_filings.filing_risks,
        sec_filings.text_extracted,
        sec_filings.summarized_at,
        sec_filings.created_at,
        signals.sentiment,
        signals.confidence,
        signals.action,
        signals.urgency,
        signals.risk_warning
    FROM sec_filings
    LEFT JOIN articles ON articles.url = sec_filings.filing_url
    LEFT JOIN signals ON signals.article_id = articles.id
    WHERE datetime(sec_filings.created_at) >= datetime('now', ?)
    ORDER BY sec_filings.filing_date DESC, sec_filings.created_at DESC;
    """
    keys = [
        "id",
        "ticker",
        "cik",
        "form",
        "accession",
        "filing_date",
        "report_date",
        "primary_document",
        "filing_url",
        "headline",
        "processed",
        "filing_text_path",
        "filing_summary",
        "filing_key_points",
        "filing_risks",
        "text_extracted",
        "summarized_at",
        "created_at",
        "sentiment",
        "confidence",
        "action",
        "urgency",
        "risk_warning",
    ]
    lookback = f"-{int(lookback_hours)} hours"
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(sql, (lookback,)).fetchall()
    return [dict(zip(keys, row)) for row in rows]


def save_or_update_ipo(database_path: Path, ipo: dict[str, Any], prediction: dict[str, Any]) -> tuple[int, bool, bool]:
    """Insert or update an IPO row. Returns row ID, created flag, and materially changed flag."""
    company_name = _clean_optional_text(ipo.get("company_name"))
    ticker = _clean_optional_text(ipo.get("ticker"))
    source_url = str(ipo.get("source_url", "")).strip()
    ipo_date = _clean_optional_text(ipo.get("ipo_date"))
    existing = None
    with sqlite3.connect(database_path) as connection:
        if ticker or company_name or ipo_date:
            existing = connection.execute(
                """
                SELECT id, final_ipo_price, opening_price, current_price, status, prediction_score
                FROM ipos
                WHERE COALESCE(ipo_date, '') = COALESCE(?, '')
                  AND (
                    (COALESCE(ticker, '') <> '' AND COALESCE(ticker, '') = COALESCE(?, ''))
                    OR (COALESCE(company_name, '') <> '' AND lower(COALESCE(company_name, '')) = lower(COALESCE(?, '')))
                  )
                LIMIT 1;
                """,
                (ipo_date, ticker, company_name),
            ).fetchone()

        values = (
            company_name,
            ticker,
            _clean_optional_text(ipo.get("exchange")),
            ipo_date,
            _clean_optional_text(ipo.get("expected_price_range")),
            _clean_optional_float(ipo.get("final_ipo_price")),
            _clean_optional_float(ipo.get("opening_price")),
            _clean_optional_float(ipo.get("current_price")),
            source_url,
            _clean_optional_text(ipo.get("source")),
            int(ipo.get("source_quality", 0)),
            str(ipo.get("status", "watching")),
            prediction.get("prediction_summary", ""),
            int(prediction.get("prediction_score", 0)),
            prediction.get("expected_direction", "uncertain"),
            prediction.get("watch_action", "watch"),
            json.dumps(prediction.get("key_drivers", [])),
            json.dumps(prediction.get("risks", [])),
            int(prediction.get("confidence", 0)),
            prediction.get("raw_model_response", ""),
            _clean_optional_text(ipo.get("notes")),
        )

        if existing is None:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO ipos (
                    company_name, ticker, exchange, ipo_date, expected_price_range,
                    final_ipo_price, opening_price, current_price, source_url, source,
                    source_quality, status, prediction_summary, prediction_score,
                    expected_direction, watch_action, key_drivers, risks, confidence,
                    raw_model_response, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                values,
            )
            connection.commit()
            if cursor.lastrowid:
                return int(cursor.lastrowid), True, True

        row = connection.execute(
            """
            SELECT id, final_ipo_price, opening_price, current_price, status, prediction_score
            FROM ipos
            WHERE COALESCE(ipo_date, '') = COALESCE(?, '')
              AND (
                (COALESCE(ticker, '') <> '' AND COALESCE(ticker, '') = COALESCE(?, ''))
                OR (COALESCE(company_name, '') <> '' AND lower(COALESCE(company_name, '')) = lower(COALESCE(?, '')))
              )
            LIMIT 1;
            """,
            (ipo_date, ticker, company_name),
        ).fetchone()
        if row is None:
            row = connection.execute("SELECT id, final_ipo_price, opening_price, current_price, status, prediction_score FROM ipos WHERE source_url = ? LIMIT 1;", (source_url,)).fetchone()
        if row is None:
            return 0, False, False

        changed = _ipo_materially_changed(row, ipo, prediction)
        connection.execute(
            """
            UPDATE ipos
            SET company_name = ?,
                ticker = ?,
                exchange = ?,
                ipo_date = ?,
                expected_price_range = ?,
                final_ipo_price = ?,
                opening_price = ?,
                current_price = ?,
                source_url = ?,
                source = ?,
                source_quality = ?,
                status = ?,
                prediction_summary = ?,
                prediction_score = ?,
                expected_direction = ?,
                watch_action = ?,
                key_drivers = ?,
                risks = ?,
                confidence = ?,
                raw_model_response = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (*values, row[0]),
        )
        connection.commit()
        return int(row[0]), False, changed


def save_ipo_price_check(database_path: Path, ipo_id: int, ticker: str | None, prices: dict[str, Any]) -> None:
    """Save a market-data price check for an IPO."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO ipo_price_checks (
                ipo_id, ticker, final_ipo_price, opening_price, current_price, provider
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                ipo_id,
                ticker,
                _clean_optional_float(prices.get("final_ipo_price")),
                _clean_optional_float(prices.get("opening_price")),
                _clean_optional_float(prices.get("current_price")),
                prices.get("provider", ""),
            ),
        )
        connection.commit()


def mark_ipo_alerted(database_path: Path, ipo_id: int) -> None:
    """Mark an IPO row as alerted."""
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE ipos SET alerted = 1 WHERE id = ?;", (ipo_id,))
        connection.commit()


def get_recent_ipos(database_path: Path, lookback_hours: int = 720) -> list[dict]:
    """Return recent IPO watch rows for reports."""
    sql = """
    SELECT id, company_name, ticker, exchange, ipo_date, expected_price_range,
           final_ipo_price, opening_price, current_price, source_url, source,
           source_quality, status, prediction_summary, prediction_score,
           expected_direction, watch_action, key_drivers, risks, confidence,
           notes, alerted, created_at, updated_at
    FROM ipos
    WHERE datetime(updated_at) >= datetime('now', ?)
       OR status IN ('upcoming', 'priced', 'opened', 'watching')
    ORDER BY prediction_score DESC, confidence DESC, updated_at DESC
    LIMIT 50;
    """
    keys = [
        "id",
        "company_name",
        "ticker",
        "exchange",
        "ipo_date",
        "expected_price_range",
        "final_ipo_price",
        "opening_price",
        "current_price",
        "source_url",
        "source",
        "source_quality",
        "status",
        "prediction_summary",
        "prediction_score",
        "expected_direction",
        "watch_action",
        "key_drivers",
        "risks",
        "confidence",
        "notes",
        "alerted",
        "created_at",
        "updated_at",
    ]
    lookback = f"-{int(lookback_hours)} hours"
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(sql, (lookback,)).fetchall()
    return [dict(zip(keys, row)) for row in rows]


def save_daily_report_record(database_path: Path, report_date: str, report_path: str, emailed: bool) -> int:
    """Save or update a daily report record."""
    sql = """
    INSERT INTO daily_reports (report_date, report_path, emailed)
    VALUES (?, ?, ?)
    ON CONFLICT(report_date) DO UPDATE SET
        report_path = excluded.report_path,
        emailed = excluded.emailed,
        generated_at = CURRENT_TIMESTAMP;
    """
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(sql, (report_date, report_path, 1 if emailed else 0))
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = connection.execute("SELECT id FROM daily_reports WHERE report_date = ?", (report_date,)).fetchone()
        return int(row[0]) if row else 0


def daily_report_already_sent(database_path: Path, report_date: str) -> bool:
    """Return True when the report for a date has already been generated."""
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT id FROM daily_reports WHERE report_date = ? LIMIT 1;",
            (report_date,),
        ).fetchone()
    return row is not None


def get_recent_conversation_context(database_path: Path, limit: int = 10) -> str:
    """Return recent signals and conversation turns as compact text context."""
    with sqlite3.connect(database_path) as connection:
        signal_rows = connection.execute(
            """
            SELECT articles.headline, articles.matched_symbol, articles.matched_category,
                   signals.sentiment, signals.confidence, signals.action, signals.reason,
                   signals.created_at
            FROM signals
            JOIN articles ON articles.id = signals.article_id
            ORDER BY signals.created_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

        conversation_rows = connection.execute(
            """
            SELECT user_message, bot_response, created_at
            FROM chatbot_conversations
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

    lines = ["Recent signals:"]
    for row in signal_rows:
        headline, symbol, category, sentiment, confidence, action, reason, created_at = row
        label = symbol or category or "market"
        lines.append(f"- {created_at} | {label} | {sentiment} | {confidence}% | {action} | {headline} | {reason}")

    lines.append("Recent conversation:")
    for user_message, bot_response, created_at in conversation_rows:
        lines.append(f"- {created_at} user: {user_message[:300]}")
        lines.append(f"  bot: {bot_response[:300]}")

    return "\n".join(lines)


def _clean_optional_text(value: Any) -> str | None:
    """Normalize optional text for SQLite."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_optional_float(value: Any) -> float | None:
    """Normalize optional float values."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ipo_materially_changed(row: tuple, ipo: dict[str, Any], prediction: dict[str, Any]) -> bool:
    """Return True when IPO alert-worthy fields changed."""
    _, old_final, old_open, old_current, old_status, old_score = row
    return (
        old_final != _clean_optional_float(ipo.get("final_ipo_price"))
        or old_open != _clean_optional_float(ipo.get("opening_price"))
        or old_current != _clean_optional_float(ipo.get("current_price"))
        or old_status != str(ipo.get("status", "watching"))
        or int(old_score or 0) != int(prediction.get("prediction_score", 0))
    )
