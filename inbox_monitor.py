"""IMAP inbox monitor for StockBot email replies."""

from __future__ import annotations

import email
import imaplib
import logging
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr

from config import AppConfig
from database import (
    get_recent_conversation_context,
    mark_email_processed,
    save_chatbot_conversation,
    save_email_message,
)
from email_client import EmailClient
from ollama_client import OllamaClient


class InboxMonitor:
    """Read unread email replies, ask Ollama for a response, and reply by email."""

    def __init__(self, config: AppConfig, ollama: OllamaClient, emailer: EmailClient) -> None:
        self.config = config
        self.ollama = ollama
        self.emailer = emailer
        self.logger = logging.getLogger(__name__)

    def check_inbox(self) -> None:
        """Connect to IMAP and process unread StockBot replies."""
        if not self._enabled():
            self.logger.warning("Inbox monitor disabled because email credentials are missing.")
            return

        try:
            with imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port) as mailbox:
                mailbox.login(self.config.email_address, self.config.email_app_password)
                mailbox.select("INBOX")

                status, data = mailbox.search(None, "UNSEEN")
                if status != "OK":
                    self.logger.warning("IMAP search failed with status: %s", status)
                    return

                for message_id in data[0].split():
                    self._process_message(mailbox, message_id)
        except (OSError, imaplib.IMAP4.error) as exc:
            self.logger.error("Inbox check failed: %s", exc)

    def _process_message(self, mailbox: imaplib.IMAP4_SSL, message_id: bytes) -> None:
        """Process one unread email and mark it read after handling."""
        status, data = mailbox.fetch(message_id, "(RFC822)")
        if status != "OK" or not data or not isinstance(data[0], tuple):
            self.logger.warning("Could not fetch email id %s", message_id)
            return

        message = email.message_from_bytes(data[0][1])
        subject = self._decode_header_value(message.get("Subject", ""))
        from_address = parseaddr(message.get("From", ""))[1]
        to_address = parseaddr(message.get("To", ""))[1]

        if not self._is_allowed_sender(from_address):
            self.logger.info("Skipping unread email from unapproved sender: %s", from_address)
            return

        if not self._is_stockbot_reply(subject):
            self.logger.info("Skipping unread non-StockBot email: %s", subject)
            return

        body = self._extract_plain_text(message)
        if not body:
            self.logger.warning("Skipping email with no plain text body: %s", subject)
            mailbox.store(message_id, "+FLAGS", "\\Seen")
            return

        email_message_id = save_email_message(
            self.config.database_path,
            direction="inbound",
            from_address=from_address,
            to_address=to_address,
            subject=subject,
            body=body,
            related_signal_id=None,
            processed=False,
        )

        context = get_recent_conversation_context(self.config.database_path)
        bot_response = self.ollama.answer_email_reply(body, context)
        sent = self.emailer.send_chatbot_reply(subject, bot_response, from_address)

        save_chatbot_conversation(self.config.database_path, email_message_id, body, bot_response)
        mark_email_processed(self.config.database_path, email_message_id)
        save_email_message(
            self.config.database_path,
            direction="outbound",
            from_address=self.config.email_address or "",
            to_address=from_address,
            subject=f"Re: {subject}" if not subject.lower().startswith("re:") else subject,
            body=bot_response,
            related_signal_id=None,
            processed=True,
        )

        mailbox.store(message_id, "+FLAGS", "\\Seen")
        self.logger.info("Processed StockBot reply from %s; response sent=%s", from_address, sent)

    def _enabled(self) -> bool:
        """Return True when IMAP credentials are configured."""
        return bool(self.config.email_address and self.config.email_app_password)

    def _is_allowed_sender(self, from_address: str) -> bool:
        """Only process replies from the configured user or StockBot mailbox."""
        allowed = {self.config.email_to, self.config.email_address}
        return from_address.lower() in {address.lower() for address in allowed if address}

    def _is_stockbot_reply(self, subject: str) -> bool:
        """Detect replies to StockBot alert or report emails."""
        lowered = subject.lower()
        return "stockbot" in lowered and "re:" in lowered and ("alert" in lowered or "report" in lowered)

    def _decode_header_value(self, value: str) -> str:
        """Decode MIME-encoded headers."""
        parts = decode_header(value)
        decoded = ""
        for content, charset in parts:
            if isinstance(content, bytes):
                decoded += content.decode(charset or "utf-8", errors="replace")
            else:
                decoded += content
        return decoded.strip()

    def _extract_plain_text(self, message: Message) -> str:
        """Extract the plain-text body from an email message."""
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", "")).lower()
                if content_type == "text/plain" and "attachment" not in disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
            return ""

        payload = message.get_payload(decode=True)
        if payload:
            return payload.decode(message.get_content_charset() or "utf-8", errors="replace").strip()
        return str(message.get_payload()).strip()
