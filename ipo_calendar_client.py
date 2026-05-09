"""Structured and best-effort IPO calendar ingestion."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import requests


@dataclass(frozen=True)
class IPOCalendarItem:
    """Normalized IPO calendar row."""

    company_name: str | None
    ticker: str | None
    exchange: str | None
    ipo_date: str | None
    expected_price_range: str | None
    final_ipo_price: float | None
    opening_price: float | None
    current_price: float | None
    source_url: str
    source: str
    source_quality: int
    status: str
    headline: str
    notes: str | None


class IPOCalendarClient:
    """Load IPO candidates from multiple calendar sources without heavy dependencies."""

    NASDAQ_API_URL = "https://api.nasdaq.com/api/ipo/calendar"
    STOCKANALYSIS_CSV_URL = "https://stockanalysis.com/ipos/calendar/"

    def __init__(self, config) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "StockBot/0.1",
                "Accept": "application/json,text/csv,text/html;q=0.9,*/*;q=0.8",
            }
        )

    def fetch_calendar_items(self) -> list[dict[str, Any]]:
        """Fetch calendar rows from all configured sources."""
        items: list[IPOCalendarItem] = []
        for source in self.config.ipo_calendar_sources:
            try:
                if source == "nasdaq_api":
                    items.extend(self._fetch_nasdaq_api())
                elif source == "stockanalysis_csv":
                    items.extend(self._fetch_stockanalysis_csv())
                elif source == "manual_csv":
                    items.extend(self._load_manual_csv(self.config.ipo_manual_csv_path))
                else:
                    self.logger.warning("Unknown IPO calendar source: %s", source)
            except Exception:
                self.logger.exception("IPO calendar source failed: %s", source)
        return [item.__dict__ for item in self._dedupe(items)]

    def _fetch_nasdaq_api(self) -> list[IPOCalendarItem]:
        """Best-effort Nasdaq IPO API fetch."""
        params = {
            "date": date.today().isoformat(),
        }
        response = self.session.get(self.NASDAQ_API_URL, params=params, timeout=self.config.http_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        rows = data.get("data", {}).get("priced", {}).get("rows", [])
        rows += data.get("data", {}).get("upcoming", {}).get("rows", [])

        items = []
        for row in rows:
            company = self._clean(row.get("companyName") or row.get("name"))
            ticker = self._normalize_ticker(row.get("proposedTickerSymbol") or row.get("symbol"))
            ipo_date = self._normalize_date(row.get("expectedPriceDate") or row.get("pricedDate"))
            price_range = self._clean(row.get("priceRange") or row.get("proposedPriceRange"))
            status = "priced" if row.get("pricedDate") else "upcoming"
            items.append(
                IPOCalendarItem(
                    company_name=company,
                    ticker=ticker,
                    exchange=self._clean(row.get("exchange")),
                    ipo_date=ipo_date,
                    expected_price_range=price_range,
                    final_ipo_price=self._parse_price(row.get("price")),
                    opening_price=None,
                    current_price=None,
                    source_url=self.NASDAQ_API_URL,
                    source="nasdaq_api",
                    source_quality=8,
                    status=status,
                    headline=f"{company or ticker or 'IPO'} IPO calendar item",
                    notes=self._clean(row.get("sharesOffered")),
                )
            )
        return items

    def _fetch_stockanalysis_csv(self) -> list[IPOCalendarItem]:
        """Best-effort StockAnalysis calendar parsing.

        StockAnalysis exposes an HTML table rather than a stable public CSV. This parser is intentionally
        conservative and returns no rows if the page shape changes.
        """
        response = self.session.get(self.STOCKANALYSIS_CSV_URL, timeout=self.config.http_timeout_seconds)
        response.raise_for_status()
        text = response.text
        rows = []
        for line in text.splitlines():
            if "<tr" not in line.lower() or "<td" not in line.lower():
                continue
            cells = self._strip_html_cells(line)
            if len(cells) < 3:
                continue
            ipo_date = self._normalize_date(cells[0])
            ticker = self._normalize_ticker(cells[1])
            company = self._clean(cells[2])
            if not company and not ticker:
                continue
            rows.append(
                IPOCalendarItem(
                    company_name=company,
                    ticker=ticker,
                    exchange=None,
                    ipo_date=ipo_date,
                    expected_price_range=None,
                    final_ipo_price=None,
                    opening_price=None,
                    current_price=None,
                    source_url=self.STOCKANALYSIS_CSV_URL,
                    source="stockanalysis_csv",
                    source_quality=6,
                    status="upcoming",
                    headline=f"{company or ticker} IPO calendar item",
                    notes=None,
                )
            )
        return rows

    def _load_manual_csv(self, path: Path) -> list[IPOCalendarItem]:
        """Load manually maintained IPO calendar CSV rows."""
        if not path.exists():
            self.logger.info("Manual IPO calendar CSV not found: %s", path)
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

        items = []
        for row in rows:
            company = self._clean(row.get("company_name"))
            ticker = self._normalize_ticker(row.get("ticker"))
            ipo_date = self._normalize_date(row.get("ipo_date"))
            source_url = self._clean(row.get("source_url")) or f"manual_csv:{company or ticker or ipo_date}"
            if not company and not ticker:
                continue
            items.append(
                IPOCalendarItem(
                    company_name=company,
                    ticker=ticker,
                    exchange=self._clean(row.get("exchange")),
                    ipo_date=ipo_date,
                    expected_price_range=self._clean(row.get("expected_price_range")),
                    final_ipo_price=None,
                    opening_price=None,
                    current_price=None,
                    source_url=source_url,
                    source="manual_csv",
                    source_quality=7,
                    status="upcoming",
                    headline=f"{company or ticker} IPO calendar item",
                    notes=self._clean(row.get("notes")),
                )
            )
        return items

    def _dedupe(self, items: list[IPOCalendarItem]) -> list[IPOCalendarItem]:
        """Deduplicate by ticker/company/date while preferring higher source quality."""
        best: dict[tuple[str, str, str], IPOCalendarItem] = {}
        for item in items:
            key = (
                (item.ticker or "").upper(),
                (item.company_name or "").lower(),
                item.ipo_date or "",
            )
            existing = best.get(key)
            if existing is None or item.source_quality > existing.source_quality:
                best[key] = item
        return list(best.values())

    def _strip_html_cells(self, row_html: str) -> list[str]:
        """Extract simple table cells from a single HTML row."""
        cells = []
        for chunk in row_html.split("<td"):
            if "</td>" not in chunk:
                continue
            value = chunk.split(">", 1)[-1].split("</td>", 1)[0]
            cells.append(self._clean(value.replace("&amp;", "&").replace("&nbsp;", " ")) or "")
        return cells

    def _clean(self, value: Any) -> str | None:
        """Clean optional text."""
        if value is None:
            return None
        text = str(value)
        text = text.replace("\n", " ").replace("\r", " ").strip()
        while "  " in text:
            text = text.replace("  ", " ")
        return text or None

    def _normalize_ticker(self, value: Any) -> str | None:
        """Normalize optional ticker."""
        text = self._clean(value)
        return text.upper() if text else None

    def _normalize_date(self, value: Any) -> str | None:
        """Normalize date-like values to YYYY-MM-DD when possible."""
        text = self._clean(value)
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return text

    def _parse_price(self, value: Any) -> float | None:
        """Parse a price from a source value."""
        text = self._clean(value)
        if not text:
            return None
        text = text.replace("$", "").replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None
