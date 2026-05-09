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
    summary = build_dashboard_summary(signals, price_confirmations, ipos, sec_filings, performance)
    bot_status = read_bot_status(config)

    paths = {
        "watchlist_summary": config.dashboard_dir / "watchlist_summary.csv",
        "signals_latest": config.dashboard_dir / "signals_latest.csv",
        "ipo_watchlist": config.dashboard_dir / "ipo_watchlist.csv",
        "signal_performance": config.dashboard_dir / "signal_performance.csv",
        "dashboard_summary": config.dashboard_dir / "dashboard_summary.json",
        "dashboard_latest": config.dashboard_dir / "dashboard_latest.html",
    }

    _write_csv(paths["watchlist_summary"], watchlist)
    _write_csv(paths["signals_latest"], _signal_rows(signals))
    _write_csv(paths["ipo_watchlist"], _ipo_rows(ipos))
    _write_csv(paths["signal_performance"], performance)
    _write_json(paths["dashboard_summary"], summary)
    _write_html(
        paths["dashboard_latest"],
        watchlist,
        signals,
        price_confirmations,
        ipos,
        sec_filings,
        performance,
        risks,
        summary,
        config.dashboard_include_charts,
        bot_status,
        config.enable_dashboard_auto_refresh,
        config.dashboard_auto_refresh_seconds,
    )

    log_run_event(config.database_path, "dashboard_exported", f"Dashboard exported to {paths['dashboard_latest']}")
    logging.getLogger(__name__).info("Dashboard exported to %s", paths["dashboard_latest"])
    return paths


def build_dashboard_summary(
    signals: list[dict[str, Any]],
    price_confirmations: list[dict[str, Any]],
    ipos: list[dict[str, Any]],
    sec_filings: list[dict[str, Any]],
    performance: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build aggregate chart data for JSON and HTML dashboard rendering."""
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "final_signal_score_trend": _score_trend(signals),
        "signal_count_by_ticker": _count_by(signals, "matched_symbol", limit=15),
        "action_counts": _count_by(signals, "action"),
        "price_volume_confirmation_summary": _price_confirmation_summary(price_confirmations),
        "alert_performance_summary": _performance_summary(performance),
        "ipo_status_counts": _count_by(ipos, "status"),
        "sec_filing_form_counts": _count_by(sec_filings, "form"),
    }


def read_bot_status(config: AppConfig) -> dict[str, Any]:
    """Read the optional runtime status file for dashboard display."""
    if not config.bot_status_file.exists():
        return {
            "status": "unknown",
            "message": "Status file has not been written yet.",
            "updated_at": "",
            "paused": False,
        }
    try:
        return json.loads(config.bot_status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "error",
            "message": "Status file could not be read.",
            "updated_at": "",
            "paused": False,
        }


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


def _score_trend(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Average final score by signal date for a compact trend chart."""
    buckets: dict[str, list[int]] = {}
    for signal in signals:
        created_at = str(signal.get("signal_created_at") or signal.get("created_at") or "")
        bucket = created_at[:10] if len(created_at) >= 10 else "unknown"
        score = _safe_int(signal.get("final_signal_score") or signal.get("confidence"))
        buckets.setdefault(bucket, []).append(score)

    rows = []
    for bucket in sorted(buckets):
        scores = buckets[bucket]
        rows.append(
            {
                "period": bucket,
                "average_final_score": round(sum(scores) / max(len(scores), 1), 1),
                "signal_count": len(scores),
            }
        )
    return rows[-14:]


def _count_by(rows: list[dict[str, Any]], key: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Count non-empty values in a row list."""
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value is None or value == "":
            value = "unknown"
        label = str(value).upper() if key in {"matched_symbol", "form"} else str(value).lower()
        counts[label] = counts.get(label, 0) + 1
    sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    if limit is not None:
        sorted_counts = sorted_counts[:limit]
    return [{"label": label, "count": count} for label, count in sorted_counts]


def _price_confirmation_summary(price_confirmations: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize price/volume confirmation state."""
    total = len(price_confirmations)
    confirmed = sum(1 for row in price_confirmations if _safe_int(row.get("trend_confirmed")) == 1)
    scores = [_safe_int(row.get("price_volume_score")) for row in price_confirmations]
    final_scores = [_safe_int(row.get("final_signal_score")) for row in price_confirmations]
    return {
        "total_checks": total,
        "trend_confirmed": confirmed,
        "not_confirmed": max(total - confirmed, 0),
        "average_price_volume_score": round(sum(scores) / max(len(scores), 1), 1) if scores else 0,
        "average_final_signal_score": round(sum(final_scores) / max(len(final_scores), 1), 1) if final_scores else 0,
    }


def _performance_summary(performance: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize checked alert outcomes."""
    by_outcome: dict[str, int] = {}
    by_horizon: dict[str, int] = {}
    changes = []
    for row in performance:
        outcome = str(row.get("outcome") or "unknown").lower()
        horizon = str(row.get("horizon") or "unknown").lower()
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_horizon[horizon] = by_horizon.get(horizon, 0) + 1
        try:
            changes.append(float(row.get("percent_change") or 0))
        except (TypeError, ValueError):
            continue
    return {
        "total_checked": len(performance),
        "by_outcome": [{"label": key, "count": value} for key, value in sorted(by_outcome.items())],
        "by_horizon": [{"label": key, "count": value} for key, value in sorted(by_horizon.items())],
        "average_percent_change": round(sum(changes) / max(len(changes), 1), 2) if changes else 0,
    }


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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write dashboard summary JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_html(
    path: Path,
    watchlist: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    price_confirmations: list[dict[str, Any]],
    ipos: list[dict[str, Any]],
    sec_filings: list[dict[str, Any]],
    performance: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    summary: dict[str, Any],
    include_charts: bool,
    bot_status: dict[str, Any],
    enable_auto_refresh: bool,
    auto_refresh_seconds: int,
) -> None:
    """Write the offline HTML dashboard."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    charts = _charts_section(summary) if include_charts else ""
    refresh_tag = (
        f'  <meta http-equiv="refresh" content="{max(int(auto_refresh_seconds), 30)}">\n'
        if enable_auto_refresh
        else ""
    )
    status_label = str(bot_status.get("status") or "unknown")
    status_message = str(bot_status.get("message") or "")
    status_updated = str(bot_status.get("updated_at") or "")
    body = "\n".join(
        [
            charts,
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
{refresh_tag}  <meta name="generator" content="StockBot local dashboard">
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
    .status-line {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
      color: var(--muted);
    }}
    .status-pill {{
      display: inline-block;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--accent);
      padding: 4px 8px;
      font-size: 12px;
      text-transform: uppercase;
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
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .chart {{
      background: var(--panel);
      border: 1px solid var(--line);
      padding: 14px;
    }}
    .chart h3 {{
      margin: 0 0 12px;
      font-size: 14px;
      color: var(--text);
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(78px, 130px) 1fr 48px;
      gap: 8px;
      align-items: center;
      margin: 8px 0;
    }}
    .bar-label, .bar-value {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .bar-track {{
      height: 12px;
      background: #222831;
      border: 1px solid var(--line);
    }}
    .bar-fill {{
      height: 100%;
      background: var(--accent);
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      margin: 8px 0;
      color: var(--muted);
    }}
    svg {{
      display: block;
      width: 100%;
      height: 180px;
      background: #12161b;
      border: 1px solid var(--line);
    }}
  </style>
</head>
<body>
  <main>
    <h1>StockBot Dashboard</h1>
    <div class="meta">Generated {html.escape(generated_at)}. Broker-free local export. Decision-support only, not financial advice.</div>
    <div class="status-line">
      <span class="status-pill">{html.escape(status_label)}</span>
      <span>{html.escape(status_message)}</span>
      <span>Last status update: {html.escape(status_updated or "unknown")}</span>
      <span>Auto-refresh: {html.escape(str(max(int(auto_refresh_seconds), 30)) + "s" if enable_auto_refresh else "off")}</span>
    </div>
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


def _charts_section(summary: dict[str, Any]) -> str:
    """Render dashboard charts with inline SVG and CSS-only bars."""
    return "\n".join(
        [
            "<h2>Dashboard Charts</h2>",
            '<div class="chart-grid">',
            _line_chart(
                "Final Signal Score Trend",
                summary.get("final_signal_score_trend", []),
                "period",
                "average_final_score",
            ),
            _bar_chart("Signal Count By Ticker", summary.get("signal_count_by_ticker", [])),
            _bar_chart("Buy/Watch/Sell Action Counts", summary.get("action_counts", [])),
            _metrics_chart(
                "Price/Volume Confirmation Summary",
                summary.get("price_volume_confirmation_summary", {}),
            ),
            _performance_chart("Alert Performance Summary", summary.get("alert_performance_summary", {})),
            _bar_chart("IPO Status Counts", summary.get("ipo_status_counts", [])),
            _bar_chart("SEC Filing Form Counts", summary.get("sec_filing_form_counts", [])),
            "</div>",
        ]
    )


def _line_chart(title: str, rows: list[dict[str, Any]], label_key: str, value_key: str) -> str:
    """Render a small inline SVG line chart."""
    if not rows:
        return _empty_chart(title)
    values = [float(row.get(value_key) or 0) for row in rows]
    max_value = max(max(values), 1)
    width = 520
    height = 180
    pad = 24
    step = (width - pad * 2) / max(len(values) - 1, 1)
    points = []
    for index, value in enumerate(values):
        x = pad + index * step
        y = height - pad - ((value / max_value) * (height - pad * 2))
        points.append((x, y))
    point_string = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#6ec6a4"><title>{html.escape(str(rows[index].get(label_key)))}: {values[index]:.1f}</title></circle>'
        for index, (x, y) in enumerate(points)
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="170" fill="#9aa7b4" font-size="10" text-anchor="middle">{html.escape(str(rows[index].get(label_key))[-5:])}</text>'
        for index, (x, _) in enumerate(points)
        if index == 0 or index == len(points) - 1 or len(points) <= 6
    )
    return (
        f'<div class="chart"><h3>{html.escape(title)}</h3>'
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
        f'<polyline points="{point_string}" fill="none" stroke="#6ec6a4" stroke-width="3"/>'
        f'{circles}{labels}</svg></div>'
    )


def _bar_chart(title: str, rows: list[dict[str, Any]]) -> str:
    """Render a CSS bar chart from label/count rows."""
    if not rows:
        return _empty_chart(title)
    max_count = max(_safe_int(row.get("count")) for row in rows) or 1
    bars = []
    for row in rows[:12]:
        label = str(row.get("label") or "unknown")
        count = _safe_int(row.get("count"))
        width = max((count / max_count) * 100, 2)
        bars.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{html.escape(label)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value">{count}</div>'
            '</div>'
        )
    return f'<div class="chart"><h3>{html.escape(title)}</h3>{"".join(bars)}</div>'


def _metrics_chart(title: str, metrics: dict[str, Any]) -> str:
    """Render a compact metric panel."""
    if not metrics:
        return _empty_chart(title)
    rows = "".join(
        f'<div class="metric-row"><span>{html.escape(str(key).replace("_", " ").title())}</span><strong>{html.escape(str(value))}</strong></div>'
        for key, value in metrics.items()
    )
    return f'<div class="chart"><h3>{html.escape(title)}</h3>{rows}</div>'


def _performance_chart(title: str, summary: dict[str, Any]) -> str:
    """Render performance metrics and outcome bars."""
    if not summary:
        return _empty_chart(title)
    metrics = {
        "total_checked": summary.get("total_checked", 0),
        "average_percent_change": summary.get("average_percent_change", 0),
    }
    return (
        '<div class="chart">'
        f'<h3>{html.escape(title)}</h3>'
        f'{_metrics_inner(metrics)}'
        f'{_bars_inner(summary.get("by_outcome", []))}'
        '</div>'
    )


def _metrics_inner(metrics: dict[str, Any]) -> str:
    """Render metrics without an outer chart wrapper."""
    return "".join(
        f'<div class="metric-row"><span>{html.escape(str(key).replace("_", " ").title())}</span><strong>{html.escape(str(value))}</strong></div>'
        for key, value in metrics.items()
    )


def _bars_inner(rows: list[dict[str, Any]]) -> str:
    """Render bars without an outer chart wrapper."""
    if not rows:
        return ""
    max_count = max(_safe_int(row.get("count")) for row in rows) or 1
    bars = []
    for row in rows:
        count = _safe_int(row.get("count"))
        width = max((count / max_count) * 100, 2)
        bars.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{html.escape(str(row.get("label") or "unknown"))}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value">{count}</div>'
            '</div>'
        )
    return "".join(bars)


def _empty_chart(title: str) -> str:
    """Render an empty chart placeholder."""
    return f'<div class="chart"><h3>{html.escape(title)}</h3><div class="meta">No data yet</div></div>'


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
