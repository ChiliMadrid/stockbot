"""Diagnostics and health checks for StockBot."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from config import load_config


@dataclass(frozen=True)
class HealthResult:
    """One health-check result."""

    status: str
    name: str
    message: str


def run_health_checks() -> list[HealthResult]:
    """Run StockBot diagnostics."""
    env_loaded = load_dotenv()
    config = load_config()

    results = [
        _check_env_loaded(env_loaded),
        _check_email_config(config),
        _check_ollama(config),
        _check_sqlite(config),
        _check_rss(config),
        _check_sec(config),
        _check_ipo_sources(config),
        _check_runtime_dirs(config),
    ]
    return results


def print_health_report(results: list[HealthResult]) -> None:
    """Print a concise health report."""
    print("StockBot Health Check")
    print("=====================")
    for result in results:
        print(f"{result.status}: {result.name} - {result.message}")


def has_failures(results: list[HealthResult]) -> bool:
    """Return True when any health check failed."""
    return any(result.status == "FAIL" for result in results)


def _check_env_loaded(env_loaded: bool) -> HealthResult:
    if env_loaded:
        return HealthResult("PASS", ".env", ".env file loaded")
    return HealthResult("WARN", ".env", ".env file not found; using environment variables and defaults")


def _check_email_config(config) -> HealthResult:
    missing = []
    if not config.email_address:
        missing.append("EMAIL_ADDRESS")
    if not config.email_app_password:
        missing.append("EMAIL_APP_PASSWORD")
    if not config.email_to:
        missing.append("EMAIL_TO")
    if missing:
        return HealthResult("WARN", "email config", f"Missing {', '.join(missing)}; email delivery disabled")
    return HealthResult("PASS", "email config", "Required email settings are present")


def _check_ollama(config) -> HealthResult:
    tags_url = _ollama_tags_url(config.ollama_url)
    try:
        response = requests.get(tags_url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return HealthResult("FAIL", "Ollama", f"Could not reach Ollama tags endpoint: {exc}")

    model_names = {model.get("name") for model in data.get("models", [])}
    if config.ollama_model in model_names:
        return HealthResult("PASS", "Ollama", f"Ollama reachable and model '{config.ollama_model}' is installed")
    return HealthResult("WARN", "Ollama", f"Ollama reachable but model '{config.ollama_model}' was not listed")


def _check_sqlite(config) -> HealthResult:
    try:
        config.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(config.database_path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS health_check_probe (id INTEGER PRIMARY KEY);")
            connection.execute("INSERT INTO health_check_probe DEFAULT VALUES;")
            connection.execute("DELETE FROM health_check_probe;")
            connection.commit()
    except sqlite3.Error as exc:
        return HealthResult("FAIL", "SQLite", f"Database is not writable: {exc}")
    return HealthResult("PASS", "SQLite", "Database is writable")


def _check_rss(config) -> HealthResult:
    if not config.rss_feeds:
        return HealthResult("WARN", "RSS", "No RSS feeds configured")
    feed_url = config.rss_feeds[0]
    try:
        response = requests.get(feed_url, timeout=15, headers={"User-Agent": "StockBot/0.1"})
        response.raise_for_status()
    except requests.RequestException as exc:
        return HealthResult("WARN", "RSS", f"First RSS feed was not reachable: {exc}")
    return HealthResult("PASS", "RSS", "First RSS feed is reachable")


def _check_sec(config) -> HealthResult:
    if not config.sec_user_agent:
        return HealthResult("FAIL", "SEC", "SEC_USER_AGENT is missing")
    if not config.sec_cik_map:
        return HealthResult("WARN", "SEC", "No SEC CIK map configured")

    ticker, cik = next(iter(config.sec_cik_map.items()))
    url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": config.sec_user_agent, "Accept-Encoding": "gzip, deflate"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return HealthResult("WARN", "SEC", f"SEC submissions endpoint check failed for {ticker}: {exc}")
    return HealthResult("PASS", "SEC", f"SEC reachable with configured User-Agent for {ticker}")


def _check_ipo_sources(config) -> HealthResult:
    if not config.ipo_calendar_sources:
        return HealthResult("WARN", "IPO calendar", "No IPO calendar sources configured")

    source_results = []
    passes = 0
    for source in config.ipo_calendar_sources:
        if source == "manual_csv":
            if config.ipo_manual_csv_path.exists():
                passes += 1
                source_results.append("manual_csv=PASS")
            else:
                source_results.append("manual_csv=FAIL file missing")
        elif source == "nasdaq_api":
            if getattr(config, "disable_nasdaq_ipo_source", False):
                source_results.append("nasdaq_api=SKIP disabled")
                continue
            if _url_reachable("https://api.nasdaq.com/api/ipo/calendar"):
                passes += 1
                source_results.append("nasdaq_api=PASS")
            else:
                source_results.append("nasdaq_api=FAIL unreachable")
        elif source == "stockanalysis_csv":
            if _url_reachable("https://stockanalysis.com/ipos/calendar/"):
                passes += 1
                source_results.append("stockanalysis_csv=PASS")
            else:
                source_results.append("stockanalysis_csv=FAIL unreachable")
        else:
            source_results.append(f"{source}=FAIL unknown source")

    details = "; ".join(source_results)
    failures = len([result for result in source_results if "=FAIL" in result])
    if passes and failures == 0:
        return HealthResult("PASS", "IPO calendar", f"Configured IPO calendar sources are usable: {details}")
    if passes:
        return HealthResult(
            "WARN",
            "IPO calendar",
            f"At least one IPO source passed, so the system can continue. Source status: {details}",
        )
    return HealthResult("FAIL", "IPO calendar", f"All enabled IPO calendar sources failed. Source status: {details}")


def _check_runtime_dirs(config) -> HealthResult:
    dirs = [
        config.reports_dir,
        config.dashboard_dir,
        config.log_file.parent,
        config.database_path.parent,
        config.backups_dir,
    ]
    failures = []
    for directory in dirs:
        if not _dir_writable(directory):
            failures.append(str(directory))
    if failures:
        return HealthResult("FAIL", "runtime dirs", f"Not writable: {', '.join(failures)}")
    return HealthResult("PASS", "runtime dirs", "reports, dashboard, logs, database, and backups directories are writable")


def _ollama_tags_url(generate_url: str) -> str:
    parsed = urlparse(generate_url)
    return f"{parsed.scheme}://{parsed.netloc}/api/tags"


def _url_reachable(url: str) -> bool:
    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "StockBot/0.1"})
        return response.status_code < 500
    except requests.RequestException:
        return False


def _dir_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".health_check_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def main() -> int:
    """Run health checks from the command line."""
    results = run_health_checks()
    print_health_report(results)
    return 1 if has_failures(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
