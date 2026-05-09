"""Telegram alert delivery."""

from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError


class TelegramAlertClient:
    """Small wrapper around python-telegram-bot for sending alerts."""

    def __init__(self, bot_token: str | None, chat_id: str | None, enabled: bool = False) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    def send_message(self, message: str) -> bool:
        """Send a Telegram message when alerts are enabled and configured."""
        if not self.enabled:
            self.logger.info("Telegram disabled; alert not sent")
            return False

        if not self.bot_token or not self.chat_id:
            self.logger.warning("Telegram enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")
            return False

        try:
            asyncio.run(self._send_message_async(message))
            self.logger.info("Telegram alert sent")
            return True
        except TelegramError as exc:
            self.logger.error("Telegram send failed: %s", exc)
        except RuntimeError as exc:
            self.logger.error("Telegram async runtime error: %s", exc)

        return False

    async def _send_message_async(self, message: str) -> None:
        """Send a Telegram message with the async Bot API."""
        bot = Bot(token=self.bot_token)
        await bot.send_message(chat_id=self.chat_id, text=message, disable_web_page_preview=False)
