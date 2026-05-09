"""SQLite database setup and persistence helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from rss_monitor import Article


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

CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(confidence);
CREATE INDEX IF NOT EXISTS idx_email_messages_created_at ON email_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_created_at ON chatbot_conversations(created_at);
"""


def initialize_database(database_path: Path) -> None:
    """Create the database and all required tables."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)


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
