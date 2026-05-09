"""Main loop for the local email-based StockBot system."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from config import AppConfig, load_config
from database import (
    initialize_database,
    log_run_event,
    save_article,
    save_email_message,
    save_signal,
    signal_already_exists,
)
from email_client import EmailClient, format_signal_alert_body, format_signal_alert_subject
from inbox_monitor import InboxMonitor
from ollama_client import OllamaClient
from report_generator import generate_daily_report, record_daily_report, should_send_daily_report
from rss_monitor import RSSMonitor
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

    next_news_check = 0.0
    next_email_check = 0.0

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
