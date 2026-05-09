"""Download and parse SEC filing documents with stdlib tools."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path

import requests


SCRIPT_STYLE_RE = re.compile(r"<(script|style).*?>.*?</\1>", flags=re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


class SECFilingParser:
    """Fetch SEC filing documents and extract readable text."""

    def __init__(self, user_agent: str, timeout_seconds: int = 30) -> None:
        self.logger = logging.getLogger(__name__)
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def download_filing(self, filing_url: str) -> str:
        """Download a SEC filing document."""
        try:
            response = self.session.get(filing_url, timeout=self.timeout_seconds)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            self.logger.error("Failed to download SEC filing %s: %s", filing_url, exc)
            return ""

    def extract_text(self, raw_document: str, max_chars: int) -> str:
        """Strip HTML/scripts/styles and return readable filing text."""
        if not raw_document:
            return ""

        without_scripts = SCRIPT_STYLE_RE.sub(" ", raw_document)
        with_line_breaks = re.sub(r"</(p|div|tr|li|h[1-6]|br)>", "\n", without_scripts, flags=re.IGNORECASE)
        without_tags = TAG_RE.sub(" ", with_line_breaks)
        decoded = html.unescape(without_tags)
        normalized = WHITESPACE_RE.sub(" ", decoded)
        normalized = BLANK_LINES_RE.sub("\n\n", normalized)
        lines = [line.strip() for line in normalized.splitlines()]
        text = "\n".join(line for line in lines if line)
        return text[:max_chars]

    def save_text(self, text: str, reports_dir: Path, accession: str) -> Path:
        """Save extracted filing text under reports/sec_filings."""
        output_dir = reports_dir / "sec_filings"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_accession = re.sub(r"[^A-Za-z0-9_-]", "_", accession)
        output_path = output_dir / f"{safe_accession}.txt"
        output_path.write_text(text, encoding="utf-8")
        return output_path

    def download_extract_and_save(self, filing: dict, reports_dir: Path, max_chars: int) -> tuple[Path | None, str]:
        """Download, extract, truncate, and save filing text."""
        raw_document = self.download_filing(str(filing.get("filing_url", "")))
        text = self.extract_text(raw_document, max_chars)
        if not text:
            return None, ""
        path = self.save_text(text, reports_dir, str(filing.get("accession", "filing")))
        return path, text
