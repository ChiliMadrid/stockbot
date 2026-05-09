"""IPO monitoring and prediction workflow."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import feedparser

from database import (
    get_recent_sec_filings,
    mark_ipo_alerted,
    save_ipo_price_check,
    save_or_update_ipo,
)
from email_client import EmailClient
from ipo_calendar_client import IPOCalendarClient
from market_data_client import MarketDataClient
from ollama_client import OllamaClient


@dataclass(frozen=True)
class IPOCandidate:
    """Normalized IPO watch candidate."""

    company_name: str | None
    ticker: str | None
    exchange: str | None
    ipo_date: str | None
    expected_price_range: str | None
    final_ipo_price: float | None
    opening_price: float | None
    current_price: float | None
    source_url: str
    status: str
    source: str
    source_quality: int
    headline: str
    notes: str | None


class IPOMonitor:
    """Find IPO candidates, score them with Ollama, and send watchlist alerts."""

    def __init__(self, config, ollama: OllamaClient, market_data: MarketDataClient, emailer: EmailClient) -> None:
        self.config = config
        self.ollama = ollama
        self.market_data = market_data
        self.emailer = emailer
        self.calendar_client = IPOCalendarClient(config)
        self.logger = logging.getLogger(__name__)

    def check_ipos(self) -> None:
        """Poll IPO sources and process candidates."""
        candidates = self._collect_candidates()
        self.logger.info("Found %s IPO candidate(s)", len(candidates))

        for candidate in candidates:
            enriched = self._with_market_data(candidate)
            prediction = self.ollama.analyze_ipo(enriched.__dict__)
            ipo_id, created, changed = save_or_update_ipo(self.config.database_path, enriched.__dict__, prediction)
            if ipo_id and enriched.ticker:
                save_ipo_price_check(self.config.database_path, ipo_id, enriched.ticker, enriched.__dict__)

            if ipo_id and self._should_alert(enriched, prediction, created, changed):
                if self._send_ipo_alert(enriched, prediction):
                    mark_ipo_alerted(self.config.database_path, ipo_id)

    def _collect_candidates(self) -> list[IPOCandidate]:
        """Collect candidates from configured IPO feeds and SEC S-1 filings."""
        candidates = []
        candidates.extend(self._from_calendar_sources())
        candidates.extend(self._from_ipo_feeds())
        candidates.extend(self._from_sec_s1_filings())
        return self._dedupe(candidates)

    def _from_calendar_sources(self) -> list[IPOCandidate]:
        """Load structured IPO calendar candidates."""
        candidates = []
        for item in self.calendar_client.fetch_calendar_items():
            candidates.append(
                IPOCandidate(
                    company_name=item.get("company_name"),
                    ticker=item.get("ticker"),
                    exchange=item.get("exchange"),
                    ipo_date=item.get("ipo_date"),
                    expected_price_range=item.get("expected_price_range"),
                    final_ipo_price=item.get("final_ipo_price"),
                    opening_price=item.get("opening_price"),
                    current_price=item.get("current_price"),
                    source_url=item.get("source_url", ""),
                    status=item.get("status", "upcoming"),
                    source=item.get("source", "ipo_calendar"),
                    source_quality=int(item.get("source_quality", 5)),
                    headline=item.get("headline", "IPO calendar item"),
                    notes=item.get("notes"),
                )
            )
        return candidates

    def _from_ipo_feeds(self) -> list[IPOCandidate]:
        """Parse configured IPO RSS/URL sources."""
        candidates = []
        for feed_url in self.config.ipo_feeds:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception:
                self.logger.exception("IPO feed failed: %s", feed_url)
                continue
            source = parsed.feed.get("title", feed_url) if parsed.feed else feed_url
            for entry in parsed.entries:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", feed_url).strip()
                summary = getattr(entry, "summary", "").strip()
                if not title:
                    continue
                candidates.append(
                    IPOCandidate(
                        company_name=self._guess_company(title),
                        ticker=self._guess_ticker(f"{title} {summary}"),
                        exchange=None,
                        ipo_date=self._guess_date(f"{title} {summary}"),
                        expected_price_range=None,
                        final_ipo_price=self._guess_price(f"{title} {summary}"),
                        opening_price=None,
                        current_price=None,
                        source_url=link,
                        status=self._guess_status(f"{title} {summary}"),
                        source=source,
                        source_quality=4,
                        headline=title,
                        notes=None,
                    )
                )
        return candidates

    def _from_sec_s1_filings(self) -> list[IPOCandidate]:
        """Treat recent S-1 filings as IPO watch candidates."""
        candidates = []
        filings = get_recent_sec_filings(self.config.database_path, lookback_hours=24 * max(self.config.ipo_lookahead_days, 30))
        for filing in filings:
            if str(filing.get("form", "")).upper() != "S-1":
                continue
            candidates.append(
                IPOCandidate(
                    company_name=filing.get("ticker"),
                    ticker=filing.get("ticker"),
                    exchange=None,
                    ipo_date=filing.get("filing_date"),
                    expected_price_range=None,
                    final_ipo_price=None,
                    opening_price=None,
                    current_price=None,
                    source_url=filing.get("filing_url", ""),
                    status="upcoming",
                    source="SEC EDGAR S-1",
                    source_quality=10,
                    headline=filing.get("headline", "SEC S-1 filing"),
                    notes="SEC S-1 filing detected",
                )
            )
        return candidates

    def _with_market_data(self, candidate: IPOCandidate) -> IPOCandidate:
        """Attach available market quote data."""
        quote = self.market_data.get_quote(candidate.ticker)
        current_price = quote.get("current_price") or candidate.current_price
        opening_price = quote.get("opening_price") or candidate.opening_price
        status = candidate.status
        if opening_price and status == "priced":
            status = "opened"
        elif current_price and status == "upcoming":
            status = "watching"

        return IPOCandidate(
            company_name=candidate.company_name,
            ticker=candidate.ticker,
            exchange=candidate.exchange,
            ipo_date=candidate.ipo_date,
            expected_price_range=candidate.expected_price_range,
            final_ipo_price=candidate.final_ipo_price,
            opening_price=opening_price,
            current_price=current_price,
            source_url=candidate.source_url,
            status=status,
            source=candidate.source,
            source_quality=candidate.source_quality,
            headline=candidate.headline,
            notes=candidate.notes,
        )

    def _should_alert(self, candidate: IPOCandidate, prediction: dict[str, Any], created: bool, changed: bool) -> bool:
        """Return True when an IPO event deserves an email alert."""
        if created:
            return True
        if changed and candidate.status in {"priced", "opened", "watching"}:
            return True
        return int(prediction.get("prediction_score", 0)) >= self.config.ipo_alert_min_score

    def _send_ipo_alert(self, candidate: IPOCandidate, prediction: dict[str, Any]) -> bool:
        """Send an IPO watchlist alert."""
        label = candidate.ticker or candidate.company_name or "IPO"
        subject = f"StockBot IPO Watch - {label} {candidate.status} score {prediction.get('prediction_score', 0)}"
        body = (
            "IPO Watchlist Alert\n\n"
            f"Ticker: {candidate.ticker or 'N/A'}\n"
            f"Company: {candidate.company_name or 'N/A'}\n"
            f"Exchange: {candidate.exchange or 'N/A'}\n"
            f"Status: {candidate.status}\n"
            f"IPO Date: {candidate.ipo_date or 'N/A'}\n"
            f"Expected Price Range: {candidate.expected_price_range or 'N/A'}\n"
            f"Final IPO Price: {candidate.final_ipo_price or 'N/A'}\n"
            f"Opening Price: {candidate.opening_price or 'N/A'}\n"
            f"Current Price: {candidate.current_price or 'N/A'}\n"
            f"Source Quality: {candidate.source_quality}/10\n"
            f"Prediction Score: {prediction.get('prediction_score', 0)}\n"
            f"Expected Direction: {prediction.get('expected_direction', 'uncertain')}\n"
            f"Watch Action: {prediction.get('watch_action', 'watch')}\n"
            f"Summary: {prediction.get('prediction_summary', '')}\n"
            f"Key Drivers: {', '.join(prediction.get('key_drivers', []))}\n"
            f"Risks: {', '.join(prediction.get('risks', []))}\n"
            f"Confidence: {prediction.get('confidence', 0)}\n"
            f"Source: {candidate.source}\n"
            f"URL: {candidate.source_url}\n\n"
            "Reminder: watchlist only, not financial advice."
        )
        return self.emailer.send_email(subject, body)

    def _dedupe(self, candidates: list[IPOCandidate]) -> list[IPOCandidate]:
        """Deduplicate IPO candidates by URL/ticker/date."""
        best: dict[tuple[str, str, str], IPOCandidate] = {}
        for candidate in candidates:
            key = (
                (candidate.ticker or "").upper(),
                (candidate.company_name or "").lower(),
                candidate.ipo_date or "",
            )
            existing = best.get(key)
            if existing is None or candidate.source_quality > existing.source_quality:
                best[key] = candidate
        return list(best.values())

    def _guess_company(self, text: str) -> str | None:
        """Best-effort company name from a headline."""
        cleaned = re.split(r"\bIPO\b|\bprices\b|\bfiles\b", text, flags=re.IGNORECASE)[0].strip(" -:")
        return cleaned or None

    def _guess_ticker(self, text: str) -> str | None:
        """Best-effort ticker extraction."""
        match = re.search(r"\(([A-Z][A-Z0-9.\-=]{0,9})\)", text)
        if match:
            return match.group(1).upper()
        for ticker in self.config.watchlist_tickers:
            if re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", text.upper()):
                return ticker
        return None

    def _guess_date(self, text: str) -> str | None:
        """Best-effort ISO-like date extraction."""
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if match:
            return match.group(1)
        return None

    def _guess_price(self, text: str) -> float | None:
        """Best-effort IPO price extraction."""
        if not re.search(r"\b(price|priced|prices|offering)\b", text, flags=re.IGNORECASE):
            return None
        match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", text)
        if not match:
            return None
        return float(match.group(1))

    def _guess_status(self, text: str) -> str:
        """Infer IPO status from source text."""
        lowered = text.lower()
        if "opened" in lowered or "debut" in lowered or "begins trading" in lowered:
            return "opened"
        if "priced" in lowered or "prices" in lowered:
            return "priced"
        if "file" in lowered or "expected" in lowered or "upcoming" in lowered:
            return "upcoming"
        return "watching"
