"""Lightweight market data client for IPO price checks."""

from __future__ import annotations

import csv
import logging
from io import StringIO
from typing import Any

import requests


class MarketDataClient:
    """Fetch simple quote data from a configured lightweight provider."""

    def __init__(self, provider: str = "stooq", timeout_seconds: int = 30) -> None:
        self.provider = provider.lower()
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)

    def get_quote(self, ticker: str | None) -> dict[str, Any]:
        """Return current/open prices when available."""
        if not ticker:
            return {"provider": self.provider}
        if self.provider != "stooq":
            self.logger.warning("Unsupported market data provider: %s", self.provider)
            return {"provider": self.provider}
        return self._get_stooq_quote(ticker)

    def _get_stooq_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch a quote from Stooq CSV endpoint."""
        symbol = self._to_stooq_symbol(ticker)
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        try:
            response = requests.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.logger.error("Market data request failed for %s: %s", ticker, exc)
            return {"provider": self.provider}

        rows = list(csv.DictReader(StringIO(response.text)))
        if not rows:
            return {"provider": self.provider}

        row = rows[0]
        close = self._parse_float(row.get("Close"))
        open_price = self._parse_float(row.get("Open"))
        return {
            "provider": self.provider,
            "ticker": ticker,
            "symbol": symbol,
            "opening_price": open_price,
            "current_price": close,
        }

    def _to_stooq_symbol(self, ticker: str) -> str:
        """Convert common watchlist ticker forms to Stooq symbols."""
        value = ticker.strip().lower()
        if value.endswith("=f"):
            return value.replace("=f", ".f")
        if "." in value:
            return value
        return f"{value}.us"

    def _parse_float(self, value: str | None) -> float | None:
        """Parse numeric quote fields."""
        if not value or value.upper() == "N/D":
            return None
        try:
            return float(value)
        except ValueError:
            return None
