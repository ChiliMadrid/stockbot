"""Local Ollama client for headline classification and email chatbot replies."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from rss_monitor import Article


class OllamaClient:
    """Small client for the local Ollama generate API."""

    def __init__(self, base_url: str, model: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)

    def test_connection(self) -> dict[str, Any]:
        """Send a small health-check prompt to Ollama."""
        payload = {
            "model": self.model,
            "prompt": "Return only this JSON: {\"status\":\"ok\"}",
            "stream": False,
            "format": "json",
        }
        response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def classify_headline(self, article: Article) -> dict[str, Any]:
        """Classify a financial headline into a structured signal."""
        prompt = self._classification_prompt(article)
        raw_response = self._generate(prompt, json_mode=True)
        parsed = self._parse_json_response(raw_response)

        if parsed is None:
            self.logger.warning("Could not parse Ollama JSON response: %s", raw_response)
            return {
                "sentiment": "neutral",
                "confidence": 0,
                "action": "ignore",
                "urgency": "low",
                "reason": "Model response could not be parsed.",
                "risk_warning": "No actionable conclusion. Needs manual review.",
                "raw_model_response": raw_response,
            }

        return self._normalize_signal(parsed, raw_response)

    def summarize_sec_filing(self, filing: dict[str, Any], filing_text: str) -> dict[str, Any]:
        """Summarize and classify extracted SEC filing text."""
        prompt = self._sec_summary_prompt(filing, filing_text)
        raw_response = self._generate(prompt, json_mode=True)
        parsed = self._parse_json_response(raw_response)

        if parsed is None:
            self.logger.warning("Could not parse SEC summary JSON response: %s", raw_response)
            return {
                "summary": "SEC filing summary unavailable because the model response could not be parsed.",
                "key_points": [],
                "potential_opportunities": [],
                "potential_risks": ["Manual review needed."],
                "sentiment": "neutral",
                "confidence": 0,
                "action": "ignore",
                "urgency": "low",
                "risk_warning": "Model response could not be parsed. Needs manual review.",
                "raw_model_response": raw_response,
            }

        signal = self._normalize_signal(parsed, raw_response)
        summary_text = str(parsed.get("summary", ""))
        return {
            **signal,
            "summary": summary_text,
            "key_points": self._normalize_list(parsed.get("key_points", [])),
            "potential_opportunities": self._normalize_list(parsed.get("potential_opportunities", [])),
            "potential_risks": self._normalize_list(parsed.get("potential_risks", [])),
            "reason": signal.get("reason") or summary_text,
        }

    def analyze_ipo(self, ipo: dict[str, Any]) -> dict[str, Any]:
        """Generate a conservative IPO watchlist prediction."""
        prompt = self._ipo_prompt(ipo)
        raw_response = self._generate(prompt, json_mode=True)
        parsed = self._parse_json_response(raw_response)

        if parsed is None:
            self.logger.warning("Could not parse IPO JSON response: %s", raw_response)
            return {
                "prediction_summary": "IPO prediction unavailable because the model response could not be parsed.",
                "prediction_score": 0,
                "expected_direction": "uncertain",
                "watch_action": "watch",
                "key_drivers": [],
                "risks": ["Manual review needed."],
                "confidence": 0,
                "raw_model_response": raw_response,
            }

        return self._normalize_ipo_prediction(parsed, raw_response)

    def answer_email_reply(self, user_message: str, recent_context: str) -> str:
        """Ask Ollama to answer a user's email reply with a cautious market tone."""
        prompt = f"""
You are StockBot, a local financial news assistant. Answer the user's email reply.

Rules:
- Be direct.
- Keep the answer short but useful.
- Mention uncertainty where appropriate.
- Do not claim certainty.
- Do not say "you should buy".
- Use phrases such as "watch", "possible setup", "risk", and "needs confirmation".
- Do not invent facts that are not in the context.
- This is not financial advice.

Recent context from SQLite:
{recent_context}

User reply:
{user_message}
""".strip()

        response = self._generate(prompt, json_mode=False)
        return response.strip() or "I could not generate a useful answer. This needs manual review."

    def _classification_prompt(self, article: Article) -> str:
        """Build the JSON-only classification prompt."""
        return f"""
You are a careful financial headline classifier. Return only valid JSON.

Allowed JSON shape:
{{
  "sentiment": "bullish | bearish | neutral",
  "confidence": 0,
  "action": "ignore | watch | possible_buy | possible_sell",
  "urgency": "low | medium | high",
  "reason": "short explanation",
  "risk_warning": "short risk warning"
}}

Classification rules:
- Use possible_buy only for potentially bullish setups with strong relevance.
- Use possible_sell only for potentially bearish setups with strong relevance.
- Use watch when the headline matters but needs confirmation.
- Use ignore when the headline is weak, unrelated, or too vague.
- Confidence is 0 to 100.
- Never give guaranteed financial advice.

Headline: {article.headline}
Source: {article.source}
Matched symbol: {article.matched_symbol or ""}
Matched category: {article.matched_category or ""}
URL: {article.url}
""".strip()

    def _sec_summary_prompt(self, filing: dict[str, Any], filing_text: str) -> str:
        """Build the JSON-only SEC filing summary prompt."""
        return f"""
You are a conservative primary-source SEC filing analyst. Return only valid JSON.

Allowed JSON shape:
{{
  "summary": "",
  "key_points": [],
  "potential_opportunities": [],
  "potential_risks": [],
  "sentiment": "bullish | bearish | neutral",
  "confidence": 0,
  "action": "ignore | watch | possible_buy | possible_sell",
  "urgency": "low | medium | high",
  "risk_warning": ""
}}

Rules:
- Be conservative.
- Do not give guaranteed financial advice.
- Do not say "you should buy".
- Do not call normal routine filings bullish unless substance supports it.
- Use possible_buy or possible_sell only when the filing text contains meaningful substance.
- Use watch when the item matters but needs confirmation.
- Confidence is 0 to 100.

Filing metadata:
Ticker: {filing.get("ticker", "")}
Form: {filing.get("form", "")}
Filing date: {filing.get("filing_date", "")}
Report date: {filing.get("report_date", "")}
URL: {filing.get("filing_url", "")}

Extracted filing text:
{filing_text}
""".strip()

    def _ipo_prompt(self, ipo: dict[str, Any]) -> str:
        """Build the JSON-only IPO prediction prompt."""
        return f"""
You are a conservative IPO watchlist analyst. Return only valid JSON.

Allowed JSON shape:
{{
  "prediction_summary": "",
  "prediction_score": 0,
  "expected_direction": "bullish|bearish|neutral|uncertain",
  "watch_action": "ignore|watch|high_priority_watch",
  "key_drivers": [],
  "risks": [],
  "confidence": 0
}}

Rules:
- Watchlist language only.
- Do not say "buy" or recommend buying.
- Use low confidence when data is weak or incomplete.
- Be conservative with new IPOs and S-1-only candidates.
- Prediction score is 0 to 100 and should reflect watchlist priority, not guaranteed upside.

IPO candidate:
Company: {ipo.get("company_name", "")}
Ticker: {ipo.get("ticker", "")}
Exchange: {ipo.get("exchange", "")}
IPO date: {ipo.get("ipo_date", "")}
Expected price range: {ipo.get("expected_price_range", "")}
Final IPO price: {ipo.get("final_ipo_price", "")}
Opening price: {ipo.get("opening_price", "")}
Current price: {ipo.get("current_price", "")}
Status: {ipo.get("status", "")}
Source: {ipo.get("source", "")}
Source quality: {ipo.get("source_quality", "")}/10
Headline: {ipo.get("headline", "")}
Notes: {ipo.get("notes", "")}
URL: {ipo.get("source_url", "")}
""".strip()

    def _generate(self, prompt: str, json_mode: bool) -> str:
        """Call Ollama and return the raw text response."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            return str(response.json().get("response", ""))
        except requests.RequestException as exc:
            self.logger.error("Ollama request failed: %s", exc)
        except json.JSONDecodeError as exc:
            self.logger.error("Ollama HTTP response was not valid JSON: %s", exc)
        return ""

    def _parse_json_response(self, raw_response: str) -> dict[str, Any] | None:
        """Parse JSON and try a small safe repair when the model adds extra text."""
        if not raw_response:
            return None

        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
        if not match:
            return None

        repaired = match.group(0).replace("\n", " ").strip()
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            return None

        return parsed if isinstance(parsed, dict) else None

    def _normalize_signal(self, parsed: dict[str, Any], raw_response: str) -> dict[str, Any]:
        """Normalize model output into the database signal shape."""
        sentiment = str(parsed.get("sentiment", "neutral")).lower()
        if sentiment not in {"bullish", "bearish", "neutral"}:
            sentiment = "neutral"

        action = str(parsed.get("action", "ignore")).lower()
        if action not in {"ignore", "watch", "possible_buy", "possible_sell"}:
            action = "ignore"

        urgency = str(parsed.get("urgency", "low")).lower()
        if urgency not in {"low", "medium", "high"}:
            urgency = "low"

        try:
            confidence = int(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0

        return {
            "sentiment": sentiment,
            "confidence": max(0, min(100, confidence)),
            "action": action,
            "urgency": urgency,
            "reason": str(parsed.get("reason", "")),
            "risk_warning": str(parsed.get("risk_warning", "Needs confirmation.")),
            "raw_model_response": raw_response,
        }

    def _normalize_list(self, value: Any) -> list[str]:
        """Normalize model list fields."""
        if isinstance(value, list):
            return [str(item) for item in value]
        if value in (None, ""):
            return []
        return [str(value)]

    def _normalize_ipo_prediction(self, parsed: dict[str, Any], raw_response: str) -> dict[str, Any]:
        """Normalize IPO model output."""
        expected_direction = str(parsed.get("expected_direction", "uncertain")).lower()
        if expected_direction not in {"bullish", "bearish", "neutral", "uncertain"}:
            expected_direction = "uncertain"

        watch_action = str(parsed.get("watch_action", "watch")).lower()
        if watch_action not in {"ignore", "watch", "high_priority_watch"}:
            watch_action = "watch"

        try:
            prediction_score = int(parsed.get("prediction_score", 0))
        except (TypeError, ValueError):
            prediction_score = 0

        try:
            confidence = int(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0

        return {
            "prediction_summary": str(parsed.get("prediction_summary", "")),
            "prediction_score": max(0, min(100, prediction_score)),
            "expected_direction": expected_direction,
            "watch_action": watch_action,
            "key_drivers": self._normalize_list(parsed.get("key_drivers", [])),
            "risks": self._normalize_list(parsed.get("risks", [])),
            "confidence": max(0, min(100, confidence)),
            "raw_model_response": raw_response,
        }
