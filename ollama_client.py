"""Local Ollama API client."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from rss_monitor import Article


class OllamaClient:
    """Client for local Ollama text generation."""

    def __init__(self, base_url: str, model: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)

    def test_connection(self) -> dict[str, Any]:
        """Send a small test request to Ollama."""
        payload = {
            "model": self.model,
            "prompt": "Reply with valid JSON only: {\"status\":\"ok\"}",
            "stream": False,
        }
        response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def analyze_headline(self, article: Article) -> dict[str, Any]:
        """Ask Ollama for structured sentiment and importance analysis."""
        prompt = self._build_analysis_prompt(article)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
            raw_text = data.get("response", "{}")
            return self._parse_analysis(raw_text)
        except requests.RequestException as exc:
            self.logger.error("Ollama request failed: %s", exc)
        except json.JSONDecodeError as exc:
            self.logger.error("Ollama returned invalid JSON: %s", exc)

        return {
            "sentiment": "unknown",
            "importance_score": 0,
            "reason": "Analysis unavailable",
            "action": "watch",
        }

    def _build_analysis_prompt(self, article: Article) -> str:
        """Build a compact prompt for financial sentiment analysis."""
        return f"""
You are a cautious financial news analyst. Analyze this RSS article for stock market relevance.

Return valid JSON only with these keys:
- sentiment: one of bullish, bearish, neutral, unknown
- importance_score: integer from 0 to 10
- reason: short plain-English explanation
- action: one of ignore, watch, alert

Title: {article.title}
Summary: {article.summary}
Source: {article.source}
Matched tickers: {", ".join(article.matched_tickers)}
Matched categories: {", ".join(article.matched_categories)}
""".strip()

    def _parse_analysis(self, raw_text: str) -> dict[str, Any]:
        """Parse and normalize Ollama analysis JSON."""
        analysis = json.loads(raw_text)

        sentiment = str(analysis.get("sentiment", "unknown")).lower()
        action = str(analysis.get("action", "watch")).lower()

        try:
            importance_score = int(analysis.get("importance_score", 0))
        except (TypeError, ValueError):
            importance_score = 0

        return {
            "sentiment": sentiment,
            "importance_score": max(0, min(10, importance_score)),
            "reason": str(analysis.get("reason", "")),
            "action": action,
        }
