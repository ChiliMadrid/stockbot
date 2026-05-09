"""Track alert outcomes after fixed time horizons."""

from __future__ import annotations

from database import get_due_signal_outcomes, update_signal_outcome
from market_data_client import MarketDataClient


class PerformanceTracker:
    """Update signal outcome rows with future prices."""

    def __init__(self, config, market_data: MarketDataClient) -> None:
        self.config = config
        self.market_data = market_data

    def check_outcomes(self) -> int:
        """Update due outcomes. Returns number updated."""
        updated = 0
        for outcome in get_due_signal_outcomes(self.config.database_path):
            ticker = outcome.get("ticker")
            quote = self.market_data.get_quote(ticker)
            future_price = quote.get("current_price")
            if future_price is None:
                continue
            alert_price = outcome.get("alert_price")
            percent_change = None
            if alert_price:
                percent_change = ((future_price - alert_price) / alert_price) * 100
            update_signal_outcome(
                self.config.database_path,
                outcome_id=int(outcome["id"]),
                future_price=future_price,
                percent_change=percent_change,
                outcome=_classify_outcome(percent_change),
            )
            updated += 1
        return updated


def _classify_outcome(percent_change: float | None) -> str:
    """Classify an outcome from price change."""
    if percent_change is None:
        return "unknown"
    if percent_change >= 2:
        return "positive"
    if percent_change <= -2:
        return "negative"
    return "flat"
