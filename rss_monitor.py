"""RSS/news feed polling and watchlist filtering."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser


@dataclass(frozen=True)
class Article:
    """A normalized RSS article that matched the watchlist."""

    headline: str
    url: str
    source: str
    published_at: str | None
    matched_symbol: str | None
    matched_category: str | None
    created_at: str


class RSSMonitor:
    """Poll RSS feeds and return articles that match symbols or categories."""

    def __init__(self, feeds: list[str], tickers: list[str], categories: list[str]) -> None:
        self.feeds = feeds
        self.tickers = [ticker.upper() for ticker in tickers]
        self.categories = [category.lower() for category in categories]
        self.logger = logging.getLogger(__name__)

    def poll(self) -> list[Article]:
        """Poll every configured RSS feed."""
        articles: list[Article] = []

        for feed_url in self.feeds:
            try:
                parsed_feed = feedparser.parse(feed_url)
            except Exception:
                self.logger.exception("Failed to parse feed: %s", feed_url)
                continue

            if parsed_feed.bozo:
                self.logger.warning("Feed parse warning for %s: %s", feed_url, parsed_feed.bozo_exception)

            source = parsed_feed.feed.get("title", feed_url)
            for entry in parsed_feed.entries:
                article = self._entry_to_article(entry, source)
                if article is not None:
                    articles.append(article)

        return articles

    def _entry_to_article(self, entry: object, source: str) -> Article | None:
        """Normalize an RSS entry when it matches the configured watchlist."""
        headline = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", "").strip()
        published_at = getattr(entry, "published", None)

        if not headline or not url:
            return None

        search_text = f"{headline} {summary}"
        matched_symbol = self._match_symbol(search_text)
        matched_category = self._match_category(search_text)

        if not matched_symbol and not matched_category:
            return None

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
        """Find the first ticker symbol in the text."""
        for ticker in self.tickers:
            pattern = rf"(?<![A-Z0-9])\$?{re.escape(ticker)}(?![A-Z0-9])"
            if re.search(pattern, text.upper()):
                return ticker
        return None

    def _match_category(self, text: str) -> str | None:
        """Find the first watchlist category in the text."""
        lowered = text.lower()
        for category in self.categories:
            if category.lower() in lowered:
                return category
        return None
