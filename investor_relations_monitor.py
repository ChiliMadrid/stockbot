"""Investor-relations RSS monitor for primary company updates."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import feedparser

from rss_monitor import Article


class InvestorRelationsMonitor:
    """Poll configured investor-relations RSS feeds."""

    def __init__(self, feeds: list[str], tickers: list[str], categories: list[str]) -> None:
        self.feeds = feeds
        self.tickers = [ticker.upper() for ticker in tickers]
        self.categories = [category.lower() for category in categories]
        self.logger = logging.getLogger(__name__)

    def poll(self) -> list[Article]:
        """Return IR feed entries as primary-source articles."""
        articles: list[Article] = []
        for feed_url in self.feeds:
            try:
                parsed_feed = feedparser.parse(feed_url)
            except Exception:
                self.logger.exception("Failed to parse IR feed: %s", feed_url)
                continue

            source = f"Investor Relations - {parsed_feed.feed.get('title', feed_url)}"
            for entry in parsed_feed.entries:
                article = self._entry_to_article(entry, source)
                if article is not None:
                    articles.append(article)
        return articles

    def _entry_to_article(self, entry: object, source: str) -> Article | None:
        """Normalize an IR RSS entry."""
        headline = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", "").strip()
        published_at = getattr(entry, "published", None)
        if not headline or not url:
            return None

        text = f"{headline} {summary}"
        matched_symbol = self._match_symbol(text)
        matched_category = self._match_category(text)

        return Article(
            headline=headline,
            url=url,
            source=source,
            published_at=published_at,
            matched_symbol=matched_symbol,
            matched_category=matched_category,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def _match_symbol(self, text: str) -> str | None:
        """Find a watched symbol in text."""
        upper_text = text.upper()
        for ticker in self.tickers:
            if ticker in upper_text:
                return ticker
        return None

    def _match_category(self, text: str) -> str | None:
        """Find a watched category in text."""
        lower_text = text.lower()
        for category in self.categories:
            if category in lower_text:
                return category
        return None
