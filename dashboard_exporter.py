"""Offline dashboard exports for broker-free StockBot review."""

from __future__ import annotations

import csv
import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from config import AppConfig, load_config
from database import (
    get_recent_ipos,
    get_recent_price_confirmations,
    get_recent_sec_filings,
    get_recent_signal_outcomes,
    get_recent_signals,
    initialize_database,
    log_run_event,
)
from source_verifier import label_verification, score_source


SIGNALS_LOOKBACK_HOURS = 72
PERFORMANCE_LOOKBACK_HOURS = 24 * 30


def export_dashboard(config: AppConfig | None = None) -> dict[str, Path]:
    """Export dashboard CSV and HTML files and return their paths."""
    config = config or load_config()
    initialize_database(config.database_path)
    config.dashboard_dir.mkdir(parents=True, exist_ok=True)

    signals = _enrich_signals(get_recent_signals(config.database_path, SIGNALS_LOOKBACK_HOURS, 0))
    price_confirmations = get_recent_price_confirmations(config.database_path, SIGNALS_LOOKBACK_HOURS)
    ipos = _decode_json_fields(get_recent_ipos(config.database_path, config.ipo_lookahead_days * 24))
    sec_filings = get_recent_sec_filings(config.database_path, SIGNALS_LOOKBACK_HOURS)
    performance = get_recent_signal_outcomes(config.database_path, PERFORMANCE_LOOKBACK_HOURS)
    watchlist = build_watchlist_summary(config, signals)
    risks = build_top_risks(signals, sec_filings, ipos)

    paths = {
        "watchlist_summary": config.dashboard_dir / "watchlist_summary.csv",
        "signals_latest": config.dashboard_dir / "signals_latest.csv",
        "ipo_watchlist": config.dashboard_dir / "ipo_watchlist.csv",
        "signal_performance": config.dashboard_dir / "signal_performance.csv",
        "dashboard_latest": config.dashboard_dir / "dashboard_latest.html",
    }

    _write_csv(paths["watchlist_summary"], watchlist)
    _write_csv(paths["signals_latest"], _signal_rows(signals))
    _write_csv(paths["ipo_watchlist"], _ipo_rows(ipos))
    _write_csv(paths["signal_performance"], performance)
    _write_html(paths["dashboard_latest"], watchlist, signals, price_confirmations, ipos, sec_filings, performance, risks)

    log_run_event(config.database_path, "dashboard_exported", f"Dashboard exported to {paths['dashboard_latest']}")
    logging.getLogger(__name__).info("Dashboard exported to %s", paths["dashboard_latest"])
    return paths


def build_watchlist_summary(config: AppConfig, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a compact watchlist view from configured tickers/categories and recent signals."""
    rows: list[dict[str, Any]] = []
    signal_counts: dict[str, int] = {}
    highest_scores: dict[str, int] = {}

    for signal in signals:
        label = signal.get("matched_symbol") or signal.get("matched_category")
        if not label:
            continue
        label = str(label).upper() if signal.get("matched_symbol") else str(label).lower()
        signal_counts[label] = signal_counts.get(label, 0) + 1
        highest_scores[label] = max(highest_scores.get(label, 0), _safe_int(signal.get("final_signal_score")))

    for ticker in config.watchlist_tickers:
        rows.append(
            {
                "type": "ticker",
                "value": ticker,
                "recent_signal_count": signal_counts.get(ticker, 0),
                "highest_final_score": highest_scores.get(ticker, 0),
                "notes": "watchlist",
            }
        )

    for category in config.watchlist_categories:
        key = category.lower()
        rows.append(
            {
                "type": "category",
                "value": category,
                "recent_signal_count": signal_counts.get(key, 0),
                "highest_final_score": highest_scores.get(key, 0),
                "notes": "watchlist",
            }
        )

    for ticker, cik in config.sec_cik_map.items():
        rows.append(
            {
                "type": "sec_cik",
                "value": ticker,
                "recent_signal_count": "",
                "highest_final_score": "",
                "notes": f"CIK {cik}",
            }
        )

    return rows


def build_top_risks(
    signals: list[dict[str, Any]],
    sec_filings: list[dict[str, Any]],
    ipos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collect unverified and risk-heavy items for the dashboard."""
    rows: list[dict[str, Any]] = []
    for signal in signals:
        verification = signal.get("verification_label", "")
        risk_warning = signal.get("risk_warning", "")
        if verification == "RUMOR_OR_UNVERIFIED" or risk_warning:
            rows.append(
                {
                    "type": "signal",
                    "label": signal.get("matched_symbol") or signal.get("matched_category") or "Market",
                    "risk": risk_warning or verification,
                    "score": signal.get("final_signal_score") or signal.get("confidence"),
                    "source": signal.get("source"),
                    "url": signal.get("url"),
                }
            )

    for filing in sec_filings:
        if filing.get("filing_risks"):
            rows.append(
                {
                    "type": "sec_filing",
                    "label": f"{filing.get('ticker')} {filing.get('form')}",
                    "risk": filing.get("filing_risks"),
                    "score": filing.get("confidence"),
                    "source": "SEC EDGAR",
                    "url": filing.get("filing_url"),
                }
            )

    for ipo in ipos:
        if ipo.get("risks"):
            rows.append(
                {
                    "type": "ipo",
                    "label": ipo.get("ticker") or ipo.get("company_name"),
                    "risk": _join_listish(ipo.get("risks")),
                    "score": ipo.get("prediction_score"),
                    "source": ipo.get("source"),
                    "url": ipo.get("source_url"),
                }
            )

    return sorted(rows, key=lambda row: _safe_int(row.get("score")), reverse=True)[:25]


def _enrich_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add source score and verification labels for dashboard use."""
    enriched = []
    for signal in signals:
        row = dict(signal)
        source_score = score_source(str(row.get("source") or ""), row.get("url"))
        row["source_score"] = source_score
        row["verification_label"] = label_verification(source_score, 1)
        enriched.append(row)
    return enriched


def _signal_rows(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape signal rows for CSV export."""
    fields = [
        "signal_id",
        "matched_symbol",
        "matched_category",
        "headline",
        "sentiment",
        "action",
        "confidence",
        "final_signal_score",
        "source_score",
        "price_volume_score",
        "risk_penalty",
        "current_price",
        "percent_move",
        "volume",
        "trend_confirmed",
        "verification_label",
        "urgency",
        "reason",
        "risk_warning",
        "source",
        "url",
        "signal_created_at",
    ]
    return [{field: signal.get(field, "") for field in fields} for signal in signals]


def _ipo_rows(ipos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape IPO rows for CSV export."""
    fields = [
        "id",
        "company_name",
        "ticker",
        "exchange",
        "ipo_date",
        "expected_price_range",
        "final_ipo_price",
        "opening_price",
        "current_price",
        "status",
        "prediction_score",
        "expected_direction",
        "watch_action",
        "confidence",
        "source",
        "source_quality",
        "source_url",
        "prediction_summary",
        "key_drivers",
        "risks",
        "notes",
        "updated_at",
    ]
    return [{field: _join_listish(ipo.get(field, "")) for field in fields} for ipo in ipos]


def _decode_json_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decode list fields stored as JSON strings when possible."""
    decoded = []
    for row in rows:
        item = dict(row)
        for key in ("key_drivers", "risks"):
            if isinstance(item.get(key), str):
                try:
                    item[key] = json.loads(item[key])
                except json.JSONDecodeError:
                    pass
        decoded.append(item)
    return decoded


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a CSV file, preserving headers even when there are no rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        else:
            writer.writerow({"status": "no rows"})


def _write_html(
    path: Path,
    watchlist: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    price_confirmations: list[dict[str, Any]],
    ipos: list[dict[str, Any]],
    sec_filings: list[dict[str, Any]],
    performance: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> None:
    """Write the offline HTML dashboard."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    body = "\n".join(
        [
            _section("Watchlist Summary", watchlist[:80]),
            _section("Latest Signals", _signal_rows(signals[:50])),
            _section("Price/Volume Confirmations", price_confirmations[:50]),
            _section("IPO Watchlist", _ipo_rows(ipos[:50])),
            _section("SEC/IR Updates", sec_filings[:50]),
            _section("Signal Performance", performance[:50]),
            _section("Top Risks/Unverified Items", risks[:25]),
        ]
    )
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StockBot Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101215;
      --panel: #171b21;
      --text: #e8edf2;
      --muted: #9aa7b4;
      --line: #2a3038;
      --accent: #6ec6a4;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Segoe UI, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px 18px 48px;
    }}
    h1, h2 {{
      margin: 0;
      font-weight: 650;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 28px;
    }}
    h2 {{
      margin-top: 30px;
      margin-bottom: 10px;
      font-size: 18px;
      color: var(--accent);
    }}
    .meta {{
      margin-top: 6px;
      color: var(--muted);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    td {{
      max-width: 360px;
      overflow-wrap: anywhere;
    }}
    a {{
      color: #8ecfff;
    }}
  </style>
</head>
<body>
  <main>
    <h1>StockBot Dashboard</h1>
    <div class="meta">Generated {html.escape(generated_at)}. Broker-free local export. Decision-support only, not financial advice.</div>
    {body}
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def _section(title: str, rows: list[dict[str, Any]]) -> str:
    """Render one HTML table section."""
    return f"<h2>{html.escape(title)}</h2>\n{_table(rows)}"


def _table(rows: list[dict[str, Any]]) -> str:
    """Render rows as a simple HTML table."""
    if not rows:
        return "<table><tbody><tr><td>No rows</td></tr></tbody></table>"
    headers = list(rows[0].keys())[:12]
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_cell(row.get(header))}</td>" for header in headers)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _cell(value: Any) -> str:
    """Escape a value for HTML, linking URLs when useful."""
    text = _join_listish(value)
    escaped = html.escape(text)
    if text.startswith(("http://", "https://")):
        return f'<a href="{escaped}">{escaped}</a>'
    return escaped


def _join_listish(value: Any) -> str:
    """Make lists, dicts, and None safe for CSV/HTML display."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _safe_int(value: Any) -> int:
    """Convert numeric-ish values for sorting and summary."""
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    exported = export_dashboard()
    for name, path in exported.items():
        print(f"{name}: {path}")
