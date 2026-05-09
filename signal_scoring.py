"""Price/volume confirmation and final signal scoring."""

from __future__ import annotations

from typing import Any

from source_verifier import score_source


def build_price_confirmation(signal: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    """Create a price/volume confirmation record for a signal."""
    current_price = quote.get("current_price")
    opening_price = quote.get("opening_price")
    prior_close = quote.get("prior_close")
    percent_move = quote.get("percent_move")
    volume = quote.get("volume")
    action = str(signal.get("action", "")).lower()
    sentiment = str(signal.get("sentiment", "")).lower()

    gap = None
    if opening_price is not None and prior_close:
        gap = ((opening_price - prior_close) / prior_close) * 100

    trend_confirmed = False
    if percent_move is not None:
        if action == "possible_buy" or sentiment == "bullish":
            trend_confirmed = percent_move > 0
        elif action == "possible_sell" or sentiment == "bearish":
            trend_confirmed = percent_move < 0

    return {
        "ticker": signal.get("matched_symbol"),
        "current_price": current_price,
        "prior_close": prior_close,
        "percent_move": percent_move,
        "volume": volume,
        "gap_percent": gap,
        "trend_confirmed": trend_confirmed,
        "provider": quote.get("provider", ""),
    }


def price_volume_score(confirmation: dict[str, Any]) -> int:
    """Score price/volume confirmation from 0 to 25."""
    score = 0
    if confirmation.get("current_price") is not None:
        score += 5
    move = confirmation.get("percent_move")
    if move is not None:
        if abs(move) >= 1:
            score += 8
        if abs(move) >= 3:
            score += 5
    if confirmation.get("trend_confirmed"):
        score += 7
    if confirmation.get("volume"):
        score += 5
    return min(score, 25)


def risk_penalty(signal: dict[str, Any]) -> int:
    """Calculate a simple risk penalty from model language."""
    text = f"{signal.get('risk_warning', '')} {signal.get('reason', '')}".lower()
    penalty = 0
    for word in ["rumor", "unverified", "lawsuit", "investigation", "debt", "dilution", "bankruptcy"]:
        if word in text:
            penalty += 5
    if str(signal.get("urgency", "")).lower() == "low":
        penalty += 3
    return min(penalty, 25)


def final_signal_score(signal: dict[str, Any], confirmation: dict[str, Any]) -> dict[str, int]:
    """Return final signal score components."""
    model_confidence = int(signal.get("confidence", 0))
    source = score_source(str(signal.get("source", "")), signal.get("url"))
    pv_score = price_volume_score(confirmation)
    penalty = risk_penalty(signal)
    final = max(0, min(150, model_confidence + source + pv_score - penalty))
    return {
        "model_confidence": model_confidence,
        "source_score": source,
        "price_volume_score": pv_score,
        "risk_penalty": penalty,
        "final_signal_score": final,
    }
