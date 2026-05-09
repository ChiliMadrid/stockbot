"""SMTP email sender for StockBot alerts and chatbot replies."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from config import AppConfig


class EmailClient:
    """Send StockBot emails through SMTP."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.enabled = bool(config.email_address and config.email_app_password and config.email_to)

        if not self.enabled:
            self.logger.warning(
                "Email is disabled. Set EMAIL_ADDRESS, EMAIL_APP_PASSWORD, and EMAIL_TO to enable alerts."
            )

    def send_email(self, subject: str, body: str, to_address: str | None = None) -> bool:
        """Send a plain-text email. Returns False instead of crashing when disabled."""
        recipient = to_address or self.config.email_to
        if not self.enabled or not recipient:
            self.logger.warning("Email not sent because email credentials or recipient are missing.")
            return False

        message = EmailMessage()
        message["From"] = self.config.email_address
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30) as server:
                server.starttls(context=context)
                server.login(self.config.email_address, self.config.email_app_password)
                server.send_message(message)
            self.logger.info("Email sent to %s: %s", recipient, subject)
            return True
        except (OSError, smtplib.SMTPException) as exc:
            self.logger.error("Email send failed: %s", exc)
            return False

    def send_signal_alert(self, signal: dict) -> bool:
        """Send a formatted signal alert email."""
        label = signal.get("matched_symbol") or signal.get("matched_category") or "Market"
        action = signal.get("action", "watch")
        confidence = int(signal.get("confidence", 0))
        subject = f"StockBot Alert — {label} {action} {confidence}%"
        body = format_signal_alert_body(signal)
        return self.send_email(subject, body)

    def send_chatbot_reply(self, original_subject: str, reply_body: str, to_address: str) -> bool:
        """Send a reply from the email chatbot."""
        subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
        return self.send_email(subject, reply_body, to_address=to_address)

    def send_daily_report(self, report_body: str) -> bool:
        """Send a daily report email."""
        return self.send_email("StockBot Daily Report", report_body)


def format_signal_alert_subject(signal: dict) -> str:
    """Build the required StockBot alert subject."""
    label = signal.get("matched_symbol") or signal.get("matched_category") or "Market"
    action = signal.get("action", "watch")
    confidence = int(signal.get("confidence", 0))
    return f"StockBot Alert — {label} {action} {confidence}%"


def format_signal_alert_body(signal: dict) -> str:
    """Build the required StockBot alert body."""
    label = signal.get("matched_symbol") or signal.get("matched_category") or "Market"
    action = signal.get("action", "watch")
    confidence = int(signal.get("confidence", 0))
    return (
            f"Ticker/Category: {label}\n"
            f"Headline: {signal.get('headline', '')}\n"
            f"Sentiment: {signal.get('sentiment', '')}\n"
            f"Action: {action}\n"
            f"Confidence: {confidence}%\n"
            f"Urgency: {signal.get('urgency', '')}\n"
            f"Reason: {signal.get('reason', '')}\n"
            f"Risk Warning: {signal.get('risk_warning', '')}\n"
            f"Source: {signal.get('source', '')}\n"
            f"URL: {signal.get('url', '')}\n"
            f"Timestamp: {signal.get('created_at', '')}\n"
    )


def send_email(subject: str, body: str, to_address: str | None = None) -> bool:
    """Convenience function using config from the environment."""
    from config import load_config

    return EmailClient(load_config()).send_email(subject, body, to_address)


def send_signal_alert(signal: dict) -> bool:
    """Convenience function for sending a signal alert."""
    from config import load_config

    return EmailClient(load_config()).send_signal_alert(signal)


def send_chatbot_reply(original_subject: str, reply_body: str, to_address: str) -> bool:
    """Convenience function for sending a chatbot reply."""
    from config import load_config

    return EmailClient(load_config()).send_chatbot_reply(original_subject, reply_body, to_address)


def send_daily_report(report_body: str) -> bool:
    """Convenience function for sending a daily report."""
    from config import load_config

    return EmailClient(load_config()).send_daily_report(report_body)
