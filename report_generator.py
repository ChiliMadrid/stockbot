"""Daily report generation and source verification for StockBot."""

from __future__ import annotations

import logging
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from database import (
    daily_report_already_sent,
    get_recent_ipos,
    get_recent_sec_filings,
    get_recent_signals,
    save_daily_report_record,
)
from source_verifier import explain_verification, label_verification, score_source


KEYWORD_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def should_send_daily_report(config, database_path: Path) -> bool:
    """Return True when today's report is enabled, due, and not already generated."""
    if not config.enable_daily_report:
        return False

    now = datetime.now()
    report_time_reached = (now.hour, now.minute) >= (config.daily_report_hour, config.daily_report_minute)
    if not report_time_reached:
        return False

    return not daily_report_already_sent(database_path, now.date().isoformat())


def generate_daily_report(config, ollama_client) -> dict:
    """Build context, ask Ollama for a report, save it, and return report metadata."""
    logger = logging.getLogger(__name__)
    context = build_report_context(config)
    prompt = _build_report_prompt(context)

    try:
        report_text = ollama_client._generate(prompt, json_mode=False).strip()
    except Exception as exc:
        logger.error("Daily report Ollama call failed: %s", exc)
        report_text = ""

    if not report_text:
        report_text = _build_fallback_report(context)

    report_path = save_report(report_text, config.reports_dir)
    return {
        "report_text": report_text,
        "report_path": report_path,
        "report_date": date.today().isoformat(),
        "context": context,
    }


def build_report_context(config) -> dict:
    """Collect recent signals and add source verification metadata."""
    signals = get_recent_signals(
        config.database_path,
        lookback_hours=config.daily_report_lookback_hours,
        min_confidence=config.daily_report_min_confidence,
    )
    sec_filings = [
        filing
        for filing in get_recent_sec_filings(config.database_path, config.daily_report_lookback_hours)
        if _sec_summary_confidence(filing) >= config.sec_summary_min_confidence or not filing.get("filing_summary")
    ]
    ipos = get_recent_ipos(config.database_path, lookback_hours=24 * max(config.ipo_lookahead_days, 30))

    enriched = []
    for signal in signals:
        independent_count = _independent_source_count(signal, signals)
        source_score = score_source(signal.get("source", ""), signal.get("url"))
        enriched_signal = dict(signal)
        enriched_signal["source_score"] = source_score
        enriched_signal["independent_source_count"] = independent_count
        enriched_signal["verification_label"] = label_verification(source_score, independent_count)
        enriched_signal["verification_note"] = explain_verification(source_score, independent_count)
        enriched.append(enriched_signal)

    ranked = rank_signals(enriched)
    labels = Counter(signal["verification_label"] for signal in ranked)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in ranked:
        groups[_signal_group(signal)].append(signal)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "lookback_hours": config.daily_report_lookback_hours,
        "min_confidence": config.daily_report_min_confidence,
        "signals": ranked,
        "primary_source_filings": sec_filings,
        "ipos": ipos,
        "groups": dict(groups),
        "trending": Counter(_signal_group(signal) for signal in ranked).most_common(10),
        "verification_counts": dict(labels),
    }


def rank_signals(signals: list[dict]) -> list[dict]:
    """Rank signals by action importance, confidence, urgency, verification, and recency."""
    action_weight = {"possible_buy": 30, "possible_sell": 30, "watch": 10, "ignore": 0}
    urgency_weight = {"high": 15, "medium": 8, "low": 0}

    def score(signal: dict) -> tuple[int, int, int, int, str]:
        confidence = int(signal.get("confidence", 0))
        action = action_weight.get(str(signal.get("action", "")).lower(), 0)
        urgency = urgency_weight.get(str(signal.get("urgency", "")).lower(), 0)
        source = int(signal.get("source_score", 0))
        created_at = str(signal.get("signal_created_at", ""))
        return (action + confidence + urgency + source, confidence, source, urgency, created_at)

    return sorted(signals, key=score, reverse=True)


def save_report(report_text: str, reports_dir: Path) -> Path:
    """Save a report text file under the reports folder."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"daily_report_{date.today().isoformat()}.txt"
    report_path.write_text(report_text, encoding="utf-8")
    return report_path


def record_daily_report(config, report_date: str, report_path: Path, emailed: bool) -> int:
    """Persist report generation status in SQLite."""
    return save_daily_report_record(config.database_path, report_date, str(report_path), emailed)


def _build_report_prompt(context: dict) -> str:
    """Create the Ollama report prompt."""
    signals_text = _format_signals_for_prompt(context["signals"])
    return f"""
Write a plain-text email report titled:
Daily StockBot Market Intelligence Report

Use this recent signal context:
Generated at: {context["generated_at"]}
Lookback hours: {context["lookback_hours"]}
Minimum confidence: {context["min_confidence"]}
Trending tickers/categories: {context["trending"]}
Verification counts: {context["verification_counts"]}

Signals:
{signals_text}

Primary-source filings/company updates:
{_format_primary_sources_for_prompt(context["primary_source_filings"])}

SEC Filing Summaries:
{_format_sec_summaries_for_prompt(context["primary_source_filings"])}

IPO Watchlist:
{_format_ipos_for_prompt(context["ipos"])}

Required sections:
1. Title: Daily StockBot Market Intelligence Report
2. Date/time generated
3. Executive summary
4. Highest-confidence possible buy watches
5. Highest-confidence possible sell watches
6. Trending tickers/categories
7. Confirmed items
8. Partially confirmed items
9. Rumors/unverified items
10. Risk notes
11. Source notes
12. Reminder: "This report is decision-support only, not financial advice."

Also include a short section named:
Primary-source filings/company updates

Also include a short section named:
SEC Filing Summaries

Also include a short section named:
IPO Watchlist

Tone rules:
- Direct and practical.
- Not hype.
- Not too long.
- Include uncertainty clearly.
- Do not phrase anything as guaranteed financial advice.
- Do not say "you should buy".
- Use "watch", "possible setup", "risk", "needs confirmation", and "monitor".
""".strip()


def _build_fallback_report(context: dict) -> str:
    """Create a deterministic report if Ollama is unavailable."""
    signals = context["signals"]
    buys = [signal for signal in signals if signal.get("action") == "possible_buy"][:5]
    sells = [signal for signal in signals if signal.get("action") == "possible_sell"][:5]
    confirmed = [signal for signal in signals if signal.get("verification_label") == "CONFIRMED"][:8]
    partial = [signal for signal in signals if signal.get("verification_label") == "PARTIALLY_CONFIRMED"][:8]
    rumors = [signal for signal in signals if signal.get("verification_label") == "RUMOR_OR_UNVERIFIED"][:8]

    lines = [
        "Daily StockBot Market Intelligence Report",
        f"Date/time generated: {context['generated_at']}",
        "",
        "Executive summary",
        f"- Reviewed {len(signals)} signal(s) from the last {context['lookback_hours']} hour(s).",
        "- Treat this as a watchlist and risk-monitoring report, not a trading instruction.",
        "",
        "Primary-source filings/company updates",
        *_format_primary_source_items(context["primary_source_filings"]),
        "",
        "SEC Filing Summaries",
        *_format_sec_summary_items(context["primary_source_filings"]),
        "",
        "IPO Watchlist",
        *_format_ipo_items(context["ipos"]),
        "",
        "Highest-confidence possible buy watches",
        *_format_section_items(buys),
        "",
        "Highest-confidence possible sell watches",
        *_format_section_items(sells),
        "",
        "Trending tickers/categories",
        *[f"- {label}: {count} signal(s)" for label, count in context["trending"]],
        "",
        "Confirmed items",
        *_format_section_items(confirmed),
        "",
        "Partially confirmed items",
        *_format_section_items(partial),
        "",
        "Rumors/unverified items",
        *_format_section_items(rumors),
        "",
        "Risk notes",
        "- Headlines can be incomplete, late, duplicated, or contradicted by later reports.",
        "- Possible setups need confirmation from price action, filings, company sources, or multiple reliable outlets.",
        "",
        "Source notes",
        "- Source verification is approximate and uses source names plus simple headline overlap.",
        "",
        'Reminder: "This report is decision-support only, not financial advice."',
    ]
    return "\n".join(lines)


def _format_section_items(signals: list[dict]) -> list[str]:
    """Format report section items."""
    if not signals:
        return ["- None found."]
    return [
        (
            f"- {_signal_group(signal)} | {signal.get('action')} | {signal.get('confidence')}% | "
            f"{signal.get('verification_label')} | {signal.get('headline')} | "
            f"Risk: {signal.get('risk_warning') or 'needs confirmation'}"
        )
        for signal in signals
    ]


def _format_primary_source_items(filings: list[dict]) -> list[str]:
    """Format SEC filings for fallback reports."""
    if not filings:
        return ["- None found in the lookback window."]
    return [
        (
            f"- {filing.get('ticker')} | {filing.get('form')} | filed {filing.get('filing_date')} | "
            f"CONFIRMED | {filing.get('headline')} | {filing.get('filing_url')}"
        )
        for filing in filings[:10]
    ]


def _format_sec_summary_items(filings: list[dict]) -> list[str]:
    """Format SEC summaries for fallback reports."""
    summarized = [filing for filing in filings if filing.get("filing_summary")]
    if not summarized:
        return ["- None available yet."]
    lines = []
    for filing in summarized[:10]:
        risks = _json_list(filing.get("filing_risks"))
        risk_text = "; ".join(risks[:3]) if risks else filing.get("risk_warning") or "needs confirmation"
        lines.append(
            f"- {filing.get('ticker')} | {filing.get('form')} | filed {filing.get('filing_date')} | "
            f"{filing.get('action') or 'watch'} | {filing.get('confidence') or 0}% | "
            f"{filing.get('filing_summary')} | Key risks: {risk_text} | {filing.get('filing_url')}"
        )
    return lines


def _format_ipo_items(ipos: list[dict]) -> list[str]:
    """Format IPO rows for fallback reports."""
    if not ipos:
        return ["- None found."]
    lines = []
    for ipo in ipos[:12]:
        risks = _json_list(ipo.get("risks"))
        risk_text = "; ".join(risks[:3]) if risks else "needs confirmation"
        lines.append(
            f"- {ipo.get('ticker') or 'N/A'} | {ipo.get('company_name') or 'N/A'} | "
            f"{ipo.get('status')} | score {ipo.get('prediction_score') or 0} | "
            f"{ipo.get('expected_direction') or 'uncertain'} | {ipo.get('prediction_summary') or ''} | "
            f"Risks: {risk_text} | {ipo.get('source_url')}"
        )
    return lines


def _format_primary_sources_for_prompt(filings: list[dict]) -> str:
    """Format SEC filings compactly for the report prompt."""
    if not filings:
        return "No primary-source filings found."
    return "\n".join(
        (
            f"- ticker={filing.get('ticker')} | form={filing.get('form')} | "
            f"filing_date={filing.get('filing_date')} | report_date={filing.get('report_date')} | "
            f"verification=CONFIRMED | headline={filing.get('headline')} | url={filing.get('filing_url')}"
        )
        for filing in filings[:20]
    )


def _format_sec_summaries_for_prompt(filings: list[dict]) -> str:
    """Format SEC filing summaries compactly for Ollama."""
    summarized = [filing for filing in filings if filing.get("filing_summary")]
    if not summarized:
        return "No SEC filing summaries available yet."
    lines = []
    for filing in summarized[:20]:
        risks = _json_list(filing.get("filing_risks"))
        key_points = _json_list(filing.get("filing_key_points"))
        lines.append(
            f"- ticker={filing.get('ticker')} | form={filing.get('form')} | "
            f"filing_date={filing.get('filing_date')} | action={filing.get('action')} | "
            f"confidence={filing.get('confidence')} | summary={filing.get('filing_summary')} | "
            f"key_points={key_points[:4]} | risks={risks[:4]} | url={filing.get('filing_url')}"
        )
    return "\n".join(lines)


def _format_ipos_for_prompt(ipos: list[dict]) -> str:
    """Format IPO watch rows compactly for Ollama."""
    if not ipos:
        return "No IPO watchlist rows found."
    lines = []
    for ipo in ipos[:20]:
        lines.append(
            f"- ticker={ipo.get('ticker')} | company={ipo.get('company_name')} | "
            f"status={ipo.get('status')} | ipo_date={ipo.get('ipo_date')} | "
            f"final_price={ipo.get('final_ipo_price')} | opening={ipo.get('opening_price')} | "
            f"current={ipo.get('current_price')} | score={ipo.get('prediction_score')} | "
            f"direction={ipo.get('expected_direction')} | action={ipo.get('watch_action')} | "
            f"summary={ipo.get('prediction_summary')} | risks={_json_list(ipo.get('risks'))[:4]} | "
            f"url={ipo.get('source_url')}"
        )
    return "\n".join(lines)


def _format_signals_for_prompt(signals: list[dict]) -> str:
    """Format signal dictionaries compactly for Ollama."""
    if not signals:
        return "No qualifying signals found."

    lines = []
    for signal in signals[:30]:
        lines.append(
            f"- label={_signal_group(signal)} | action={signal.get('action')} | "
            f"sentiment={signal.get('sentiment')} | confidence={signal.get('confidence')} | "
            f"urgency={signal.get('urgency')} | verification={signal.get('verification_label')} | "
            f"source_score={signal.get('source_score')} | independent_sources={signal.get('independent_source_count')} | "
            f"headline={signal.get('headline')} | source={signal.get('source')} | "
            f"reason={signal.get('reason')} | risk={signal.get('risk_warning')}"
        )
    return "\n".join(lines)


def _independent_source_count(target: dict, signals: list[dict]) -> int:
    """Approximate independent coverage with keyword overlap from different sources."""
    target_label = _signal_group(target)
    target_source = str(target.get("source", "")).strip().lower()
    target_keywords = _keywords(str(target.get("headline", "")))
    sources = set()

    for signal in signals:
        if _signal_group(signal) != target_label:
            continue
        source = str(signal.get("source", "")).strip().lower()
        if not source or source == target_source:
            continue
        overlap = target_keywords.intersection(_keywords(str(signal.get("headline", ""))))
        if len(overlap) >= 2:
            sources.add(source)

    return len(sources)


def _keywords(text: str) -> set[str]:
    """Extract simple lowercase keywords from a headline."""
    words = [word.strip(".,:;!?()[]{}\"'").lower() for word in text.split()]
    return {word for word in words if len(word) > 3 and word not in KEYWORD_STOPWORDS}


def _signal_group(signal: dict) -> str:
    """Return the ticker/category grouping label for a signal."""
    return signal.get("matched_symbol") or signal.get("matched_category") or "Market"


def _json_list(value: object) -> list[str]:
    """Parse a JSON list stored in SQLite."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return [str(value)]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [str(parsed)]


def _sec_summary_confidence(filing: dict) -> int:
    """Return SEC summary confidence, defaulting unsummarized filings into the report."""
    try:
        return int(filing.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0
