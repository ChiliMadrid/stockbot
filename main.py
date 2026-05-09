"""Application entry point for the local stock intelligence system."""

from __future__ import annotations

import logging
import time

from config import AppConfig, load_config
from database import initialize_database, save_article_analysis
from ollama_client import OllamaClient
from rss_monitor import RSSMonitor
from telegram_alerts import TelegramAlertClient
from utils import configure_logging, is_important_signal


def run_once(config: AppConfig) -> None:
    """Poll feeds once, analyze matched items, store results, and send alerts."""
    logger = logging.getLogger(__name__)

    initialize_database(config.database_path)

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
    telegram = TelegramAlertClient(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        enabled=config.telegram_enabled,
    )

    logger.info("Polling RSS feeds")
    articles = rss_monitor.poll()
    logger.info("Matched %s article(s)", len(articles))

    for article in articles:
        logger.info("Analyzing article: %s", article.title)
        analysis = ollama.analyze_headline(article)
        article_id = save_article_analysis(config.database_path, article, analysis)

        if is_important_signal(analysis, config.alert_score_threshold):
            message = (
                f"Stock intelligence alert\n\n"
                f"Ticker(s): {', '.join(article.matched_tickers) or 'N/A'}\n"
                f"Sentiment: {analysis.get('sentiment', 'unknown')}\n"
                f"Importance: {analysis.get('importance_score', 'unknown')}\n"
                f"Title: {article.title}\n"
                f"URL: {article.link}\n"
                f"Database ID: {article_id}"
            )
            telegram.send_message(message)


def main() -> None:
    """Run the stock intelligence worker."""
    config = load_config()
    configure_logging(config.log_file)
    logger = logging.getLogger(__name__)

    logger.info("Starting local stock intelligence system")

    if config.poll_once:
        run_once(config)
        logger.info("Finished one-shot run")
        return

    while True:
        try:
            run_once(config)
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
            break
        except Exception:
            logger.exception("Unexpected error during polling cycle")

        logger.info("Sleeping for %s seconds", config.poll_interval_seconds)
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()
