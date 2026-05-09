"""Main loop for the local email-based StockBot system."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from config import AppConfig, load_config
from database import (
    initialize_database,
    log_run_event,
    mark_sec_filing_processed,
    save_article,
    save_email_message,
    save_sec_filing,
    save_signal,
    sec_filing_exists,
    signal_already_exists,
    update_sec_filing_text_summary,
)
from email_client import EmailClient, format_signal_alert_body, format_signal_alert_subject
from inbox_monitor import InboxMonitor
from investor_relations_monitor import InvestorRelationsMonitor
from ipo_monitor import IPOMonitor
from market_data_client import MarketDataClient
from ollama_client import OllamaClient
from report_generator import generate_daily_report, record_daily_report, should_send_daily_report
from rss_monitor import Article, RSSMonitor
from sec_edgar_client import SECEdgarClient
from sec_filing_parser import SECFilingParser
from utils import configure_logging, should_send_signal_alert


def check_news(config: AppConfig, rss_monitor: RSSMonitor, ollama: OllamaClient, emailer: EmailClient) -> None:
    """Poll RSS feeds, classify new matches, save signals, and email important alerts."""
    logger = logging.getLogger(__name__)
    logger.info("Checking RSS/news feeds")
    log_run_event(config.database_path, "news_check_started", "Started RSS/news check")

    articles = rss_monitor.poll()
    logger.info("Matched %s article(s)", len(articles))

    for article in articles:
        if signal_already_exists(config.database_path, article.url):
            logger.debug("Skipping already processed URL: %s", article.url)
            continue

        article_id = save_article(config.database_path, article)
        if article_id is None:
            continue

        signal = ollama.classify_headline(article)
        signal_id = save_signal(config.database_path, article_id, signal)
        signal["id"] = signal_id
        signal["headline"] = article.headline
        signal["url"] = article.url
        signal["source"] = article.source
        signal["matched_symbol"] = article.matched_symbol
        signal["matched_category"] = article.matched_category
        signal["created_at"] = datetime.now().isoformat(timespec="seconds")

        if should_send_signal_alert(signal):
            sent = emailer.send_signal_alert(signal)
            save_email_message(
                config.database_path,
                direction="outbound",
                from_address=config.email_address or "",
                to_address=config.email_to or "",
                subject=format_signal_alert_subject(signal),
                body=format_signal_alert_body(signal),
                related_signal_id=signal_id,
                processed=sent,
            )
            log_run_event(
                config.database_path,
                "email_alert_sent" if sent else "email_alert_skipped",
                f"Signal {signal_id}: {article.headline}",
            )

    log_run_event(config.database_path, "news_check_finished", "Finished RSS/news check")


def check_sec_and_ir(
    config: AppConfig,
    sec_client: SECEdgarClient,
    sec_parser: SECFilingParser,
    ir_monitor: InvestorRelationsMonitor,
    ollama: OllamaClient,
    emailer: EmailClient,
) -> None:
    """Poll SEC EDGAR and investor-relations feeds as primary-source inputs."""
    logger = logging.getLogger(__name__)
    logger.info("Checking SEC filings and investor-relations feeds")
    log_run_event(config.database_path, "sec_check_started", "Started SEC/IR check")

    for ticker in config.sec_cik_map:
        filings = sec_client.fetch_recent_filings(ticker)
        for filing in filings:
            if sec_filing_exists(config.database_path, filing["accession"]):
                continue

            save_sec_filing(config.database_path, filing)
            article = _sec_filing_to_article(filing)
            summary = _extract_and_summarize_sec_filing(config, sec_parser, ollama, filing)
            stored_signal = _classify_and_store_primary_item(config, ollama, article, summary)
            mark_sec_filing_processed(config.database_path, filing["accession"])

            if stored_signal is not None:
                signal_id, signal_data = stored_signal
                signal = _signal_for_alert_payload(signal_id, article, signal_data)
                if _should_send_sec_alert(config, filing["form"], signal):
                    _send_and_log_alert(config, emailer, signal, signal_id, "sec_alert")

    for article in ir_monitor.poll():
        if signal_already_exists(config.database_path, article.url):
            continue
        signal = ollama.classify_headline(article)
        article_id = save_article(config.database_path, article)
        if article_id is None:
            continue
        signal_id = save_signal(config.database_path, article_id, signal)
        signal_payload = _signal_for_alert_payload(signal_id, article, signal)
        if should_send_signal_alert(signal_payload) or int(signal_payload.get("confidence", 0)) >= 60:
            _send_and_log_alert(config, emailer, signal_payload, signal_id, "ir_alert")

    log_run_event(config.database_path, "sec_check_finished", "Finished SEC/IR check")


def check_ipos(config: AppConfig, ipo_monitor: IPOMonitor) -> None:
    """Run the IPO monitor safely."""
    logger = logging.getLogger(__name__)
    logger.info("Checking IPO watch sources")
    log_run_event(config.database_path, "ipo_check_started", "Started IPO check")
    ipo_monitor.check_ipos()
    log_run_event(config.database_path, "ipo_check_finished", "Finished IPO check")


def _extract_and_summarize_sec_filing(
    config: AppConfig,
    sec_parser: SECFilingParser,
    ollama: OllamaClient,
    filing: dict,
) -> dict | None:
    """Extract SEC filing text and summarize it when enabled."""
    if not config.enable_sec_text_extraction:
        return None

    text_path, filing_text = sec_parser.download_extract_and_save(
        filing,
        reports_dir=config.reports_dir,
        max_chars=config.sec_text_max_chars,
    )
    if not filing_text:
        log_run_event(
            config.database_path,
            "sec_text_extraction_failed",
            f"Failed to extract text for {filing.get('accession')}",
        )
        return None

    summary = ollama.summarize_sec_filing(filing, filing_text)
    update_sec_filing_text_summary(
        config.database_path,
        accession=filing["accession"],
        filing_text_path=str(text_path) if text_path else None,
        summary=summary,
    )
    return summary


def _classify_and_store_primary_item(
    config: AppConfig,
    ollama: OllamaClient,
    article: Article,
    existing_signal: dict | None = None,
) -> tuple[int, dict] | None:
    """Classify and store a primary-source article-like item."""
    if signal_already_exists(config.database_path, article.url):
        return None
    article_id = save_article(config.database_path, article)
    if article_id is None:
        return None
    signal = existing_signal or ollama.classify_headline(article)
    signal_id = save_signal(config.database_path, article_id, signal)
    return signal_id, signal


def _sec_filing_to_article(filing: dict) -> Article:
    """Convert SEC filing metadata into the existing Article shape."""
    return Article(
        headline=filing["headline"],
        url=filing["filing_url"],
        source=f"SEC EDGAR {filing['form']}",
        published_at=filing.get("filing_date"),
        matched_symbol=filing.get("ticker"),
        matched_category="sec filing",
        created_at=filing.get("created_at") or datetime.now().isoformat(timespec="seconds"),
    )


def _signal_for_alert_payload(signal_id: int, article: Article, signal: dict) -> dict:
    """Attach article fields to a signal for email formatting."""
    payload = dict(signal)
    payload["id"] = signal_id
    payload["headline"] = article.headline
    payload["url"] = article.url
    payload["source"] = article.source
    payload["matched_symbol"] = article.matched_symbol
    payload["matched_category"] = article.matched_category
    payload["created_at"] = datetime.now().isoformat(timespec="seconds")
    return payload


def _should_send_sec_alert(config: AppConfig, form: str, signal: dict) -> bool:
    """Alert on important SEC forms when model confidence is high enough."""
    important_forms = {"8-K", "10-Q", "10-K", "S-1", "SC 13G", "SC 13D", "4"}
    try:
        confidence = int(signal.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    threshold = max(60, config.sec_summary_min_confidence)
    return form.upper() in important_forms and confidence >= threshold


def _send_and_log_alert(
    config: AppConfig,
    emailer: EmailClient,
    signal: dict,
    signal_id: int,
    event_type: str,
) -> None:
    """Send an alert email and persist the outbound email record."""
    sent = emailer.send_signal_alert(signal)
    save_email_message(
        config.database_path,
        direction="outbound",
        from_address=config.email_address or "",
        to_address=config.email_to or "",
        subject=format_signal_alert_subject(signal),
        body=format_signal_alert_body(signal),
        related_signal_id=signal_id,
        processed=sent,
    )
    log_run_event(
        config.database_path,
        f"{event_type}_sent" if sent else f"{event_type}_skipped",
        f"Signal {signal_id}: {signal.get('headline', '')}",
    )


def check_daily_report(config: AppConfig, ollama: OllamaClient, emailer: EmailClient) -> None:
    """Generate and send the daily report when it is due."""
    if not should_send_daily_report(config, config.database_path):
        return

    logger = logging.getLogger(__name__)
    report_date = datetime.now().date().isoformat()
    logger.info("Generating daily report for %s", report_date)
    log_run_event(config.database_path, "daily_report_started", f"Generating report for {report_date}")

    report = generate_daily_report(config, ollama)
    subject = f"StockBot Daily Report — {report_date}"
    emailed = emailer.send_daily_report(report["report_text"], subject=subject)
    record_daily_report(config, report["report_date"], report["report_path"], emailed)
    save_email_message(
        config.database_path,
        direction="outbound",
        from_address=config.email_address or "",
        to_address=config.daily_report_to or config.email_to or "",
        subject=subject,
        body=report["report_text"],
        related_signal_id=None,
        processed=emailed,
    )
    log_run_event(
        config.database_path,
        "daily_report_sent" if emailed else "daily_report_saved",
        f"Report saved to {report['report_path']}",
    )


def main() -> None:
    """Run StockBot until interrupted."""
    config = load_config()
    configure_logging(config.log_file)
    logger = logging.getLogger(__name__)

    initialize_database(config.database_path)
    log_run_event(config.database_path, "startup", "StockBot started")

    rss_monitor = RSSMonitor(
        feeds=config.rss_feeds,
        tickers=config.watchlist_tickers,
        categories=config.watchlist_categories,
    )
    ollama = OllamaClient(
        base_url=config.ollama_url,
        model=config.ollama_model,
        timeout_seconds=config.http_timeout_seconds,
    )
    emailer = EmailClient(config)
    inbox_monitor = InboxMonitor(config, ollama, emailer)
    market_data = MarketDataClient(
        provider=config.market_data_provider,
        timeout_seconds=config.http_timeout_seconds,
    )
    ipo_monitor = IPOMonitor(config, ollama, market_data, emailer)
    sec_client = SECEdgarClient(config)
    sec_parser = SECFilingParser(
        user_agent=config.sec_user_agent,
        timeout_seconds=config.http_timeout_seconds,
    )
    ir_monitor = InvestorRelationsMonitor(
        feeds=config.investor_relations_feeds,
        tickers=config.watchlist_tickers,
        categories=config.watchlist_categories,
    )

    next_news_check = 0.0
    next_email_check = 0.0
    next_sec_check = 0.0
    next_ipo_check = 0.0

    logger.info("StockBot running. Press Ctrl+C to stop.")

    try:
        while True:
            now = time.monotonic()

            if now >= next_news_check:
                try:
                    check_news(config, rss_monitor, ollama, emailer)
                except Exception:
                    logger.exception("News check failed")
                    log_run_event(config.database_path, "news_check_error", "News check failed")
                next_news_check = now + config.news_check_interval_seconds

            if config.enable_inbox_monitor and now >= next_email_check:
                try:
                    inbox_monitor.check_inbox()
                except Exception:
                    logger.exception("Inbox check failed")
                    log_run_event(config.database_path, "inbox_check_error", "Inbox check failed")
                next_email_check = now + config.email_check_interval_seconds

            if config.enable_sec_monitor and now >= next_sec_check:
                try:
                    check_sec_and_ir(config, sec_client, sec_parser, ir_monitor, ollama, emailer)
                except Exception:
                    logger.exception("SEC/IR check failed")
                    log_run_event(config.database_path, "sec_check_error", "SEC/IR check failed")
                next_sec_check = now + config.sec_check_interval_seconds

            if config.enable_ipo_monitor and now >= next_ipo_check:
                try:
                    check_ipos(config, ipo_monitor)
                except Exception:
                    logger.exception("IPO check failed")
                    log_run_event(config.database_path, "ipo_check_error", "IPO check failed")
                next_ipo_check = now + config.ipo_check_interval_seconds

            try:
                check_daily_report(config, ollama, emailer)
            except Exception:
                logger.exception("Daily report generation failed")
                log_run_event(config.database_path, "daily_report_error", "Daily report generation failed")

            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        log_run_event(config.database_path, "shutdown", "StockBot stopped by user")


if __name__ == "__main__":
    main()
