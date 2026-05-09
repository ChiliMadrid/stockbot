"""SQLite database setup and persistence helpers."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from rss_monitor import Article


SCHEMA = """
CREATE TABLE IF NOT EXISTS article_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    summary TEXT,
    source TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    matched_tickers TEXT NOT NULL,
    matched_categories TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    importance_score INTEGER NOT NULL,
    reason TEXT,
    action TEXT,
    raw_analysis TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(link, title)
);

CREATE INDEX IF NOT EXISTS idx_article_analysis_created_at
ON article_analysis(created_at);

CREATE INDEX IF NOT EXISTS idx_article_analysis_importance
ON article_analysis(importance_score);
"""


def initialize_database(database_path: Path) -> None:
    """Create the SQLite database and tables when needed."""
    logger = logging.getLogger(__name__)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)

    logger.info("SQLite database initialized at %s", database_path)


def save_article_analysis(database_path: Path, article: Article, analysis: dict[str, Any]) -> int | None:
    """Insert an analyzed article and return its row ID."""
    logger = logging.getLogger(__name__)

    sql = """
    INSERT OR IGNORE INTO article_analysis (
        title,
        link,
        summary,
        source,
        published_at,
        fetched_at,
        matched_tickers,
        matched_categories,
        sentiment,
        importance_score,
        reason,
        action,
        raw_analysis
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    values = (
        article.title,
        article.link,
        article.summary,
        article.source,
        article.published_at,
        article.fetched_at,
        json.dumps(article.matched_tickers),
        json.dumps(article.matched_categories),
        analysis.get("sentiment", "unknown"),
        int(analysis.get("importance_score", 0)),
        analysis.get("reason", ""),
        analysis.get("action", "watch"),
        json.dumps(analysis),
    )

    try:
        with sqlite3.connect(database_path) as connection:
            cursor = connection.execute(sql, values)
            connection.commit()
            if cursor.lastrowid == 0:
                logger.info("Article already exists in database: %s", article.link)
                return None
            return cursor.lastrowid
    except sqlite3.Error as exc:
        logger.error("Failed to save article analysis: %s", exc)
        return None
