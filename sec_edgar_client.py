"""SEC EDGAR submissions client for StockBot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"


@dataclass(frozen=True)
class SECFiling:
    """Normalized SEC filing metadata."""

    ticker: str
    cik: str
    form: str
    accession: str
    filing_date: str
    report_date: str | None
    primary_document: str
    filing_url: str
    headline: str
    processed: bool
    created_at: str


class SECEdgarClient:
    """Fetch recent company submissions from the SEC EDGAR data API."""

    def __init__(self, config) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def fetch_recent_filings(self, ticker: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch recent tracked SEC filings for a ticker."""
        ticker = ticker.upper()
        cik = self.config.sec_cik_map.get(ticker)
        if not cik:
            self.logger.warning("No SEC CIK configured for %s", ticker)
            return []

        url = SEC_SUBMISSIONS_URL.format(cik=cik.zfill(10))
        try:
            response = self.session.get(url, timeout=self.config.http_timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            self.logger.error("SEC request failed for %s: %s", ticker, exc)
            return []
        except ValueError as exc:
            self.logger.error("SEC response was not valid JSON for %s: %s", ticker, exc)
            return []

        return [filing.__dict__ for filing in self._parse_recent_filings(ticker, cik, data, limit)]

    def _parse_recent_filings(
        self,
        ticker: str,
        cik: str,
        data: dict[str, Any],
        limit: int,
    ) -> list[SECFiling]:
        """Parse the SEC submissions recent arrays."""
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_documents = recent.get("primaryDocument", [])

        filings: list[SECFiling] = []
        tracked_forms = set(self.config.sec_forms_to_track)

        for index, form in enumerate(forms):
            form = str(form).upper()
            if form not in tracked_forms:
                continue

            accession = str(accession_numbers[index])
            primary_document = str(primary_documents[index] or "")
            filing_date = str(filing_dates[index] or "")
            report_date = str(report_dates[index] or "") or None
            filing_url = self._filing_url(cik, accession, primary_document)
            headline = f"{ticker} SEC filing: {form} filed {filing_date}"

            filings.append(
                SECFiling(
                    ticker=ticker,
                    cik=cik.zfill(10),
                    form=form,
                    accession=accession,
                    filing_date=filing_date,
                    report_date=report_date,
                    primary_document=primary_document,
                    filing_url=filing_url,
                    headline=headline,
                    processed=False,
                    created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                )
            )

            if len(filings) >= limit:
                break

        return filings

    def _filing_url(self, cik: str, accession: str, primary_document: str) -> str:
        """Build a browser URL for the primary filing document."""
        cik_int = str(int(cik))
        accession_path = accession.replace("-", "")
        if primary_document:
            return f"{SEC_ARCHIVES_BASE_URL}/{cik_int}/{accession_path}/{primary_document}"
        return f"{SEC_ARCHIVES_BASE_URL}/{cik_int}/{accession_path}/"
