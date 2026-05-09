"""RSS feed polling and article filtering."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser


@dataclass(frozen=True)
class Article:
    """A normalized RSS article that matched the watchlist."""

    title: str
    link: str
    summary: str
    source: str
    published_at: str | None
    matched_tickers: list[str]
    matched_categories: list[str]
    fetched_at: str


class RSSMonitor:
    """Poll RSS feeds and keep only articles matching configured interests."""

    def __init__(self, feeds: list[str], tickers: list[str], categories: list[str]) -> None:
        self.feeds = feeds
        self.tickers = [ticker.upper() for ticker in tickers]
        self.categories = [category.lower() for category in categories]
        self.logger = logging.getLogger(__name__)

    def poll(self) -> list[Article]:
        """Poll every configured feed and return matching articles."""
        articles: list[Article] = []

        for feed_url in self.feeds:
            try:
                parsed_feed = feedparser.parse(feed_url)
            except Exception:
                self.logger.exception("Failed to parse feed: %s", feed_url)
                continue

            if parsed_feed.bozo:
                self.logger.warning("Feed returned parse warning: %s", feed_url)

            source = parsed_feed.feed.get("title", feed_url)

            for entry in parsed_feed.entries:
                article = self._entry_to_article(entry, source)
                if article is not None:
                    articles.append(article)

        return articles

    def _entry_to_article(self, entry: object, source: str) -> Article | None:
        """Normalize a feed entry when it matches tickers or categories."""
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", "").strip()
        published_at = getattr(entry, "published", None)

        search_text = f"{title} {summary}".upper()
        category_text = f"{title} {summary}".lower()

        matched_tickers = [
            ticker for ticker in self.tickers if ticker in search_text or f"${ticker}" in search_text
        ]
        matched_categories = [category for category in self.categories if category in category_text]

        if not matched_tickers and not matched_categories:
            return None

        return Article(
            title=title,
            link=link,
            summary=summary,
            source=source,
            published_at=published_at,
            matched_tickers=matched_tickers,
            matched_categories=matched_categories,
            fetched_at=datetime.now(UTC).isoformat(),
        )
