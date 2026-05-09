# StockBot

StockBot is a local AI stock intelligence system for Windows. It watches RSS/news feeds, classifies financial headlines with a local Ollama model, saves signals to SQLite, emails important alerts, and can answer your email replies with a cautious local chatbot.

It does not use LangChain, a vector database, a frontend, cloud AI APIs, broker integrations, or automatic trading.

## Install

Use Python 3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ollama Setup

Install Ollama from:

```text
https://ollama.com/download
```

Start Ollama:

```powershell
ollama serve
```

Pull the default local model:

```powershell
ollama pull qwen2.5:3b
```

StockBot uses:

```text
http://localhost:11434/api/generate
```

## Gmail App Password Setup

For Gmail, enable 2-Step Verification on your Google account, then create an App Password:

1. Open your Google Account.
2. Go to Security.
3. Enable 2-Step Verification if needed.
4. Create an App Password for Mail.
5. Use that app password as `EMAIL_APP_PASSWORD`.

Do not use your normal Gmail password.

## Environment Setup

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` with your real values:

```text
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate

EMAIL_ADDRESS=your_email@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_TO=your_email@gmail.com

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
IMAP_HOST=imap.gmail.com
IMAP_PORT=993

ENABLE_INBOX_MONITOR=true
EMAIL_CHECK_INTERVAL_SECONDS=120
NEWS_CHECK_INTERVAL_SECONDS=300

ENABLE_DAILY_REPORT=true
DAILY_REPORT_HOUR=7
DAILY_REPORT_MINUTE=30
DAILY_REPORT_LOOKBACK_HOURS=24
DAILY_REPORT_MIN_CONFIDENCE=50
DAILY_REPORT_TO=your_email@gmail.com

ENABLE_SEC_MONITOR=true
SEC_USER_AGENT=StockBot/0.1 contact:madridchili96@gmail.com
SEC_CHECK_INTERVAL_SECONDS=900
SEC_FORMS_TO_TRACK=8-K,10-Q,10-K,S-1,SC 13G,SC 13D,4
ENABLE_SEC_TEXT_EXTRACTION=true
SEC_TEXT_MAX_CHARS=12000
SEC_SUMMARY_MIN_CONFIDENCE=50

ENABLE_IPO_MONITOR=true
IPO_CHECK_INTERVAL_SECONDS=3600
IPO_LOOKAHEAD_DAYS=30
IPO_ALERT_MIN_SCORE=70
MARKET_DATA_PROVIDER=stooq
IPO_CALENDAR_SOURCES=nasdaq_api,stockanalysis_csv,manual_csv
IPO_MANUAL_CSV_PATH=config/ipo_calendar.csv

ENABLE_PRICE_CONFIRMATION=true
PRICE_CHECK_INTERVAL_SECONDS=300
ALERT_FINAL_SCORE_MIN=80
ENABLE_PERFORMANCE_TRACKING=true
PERFORMANCE_CHECK_INTERVAL_SECONDS=900
MORNING_BRIEF_MODE=true

ENABLE_DASHBOARD_EXPORT=true
DASHBOARD_EXPORT_INTERVAL_SECONDS=1800
DASHBOARD_INCLUDE_CHARTS=true
ENABLE_DASHBOARD_AUTO_REFRESH=true
DASHBOARD_AUTO_REFRESH_SECONDS=300

ENABLE_TRAY_APP=false

ENABLE_BACKUPS=true
BACKUP_INTERVAL_HOURS=24
BACKUP_KEEP_DAYS=14
```

You can also set values directly in Windows PowerShell:

```powershell
$env:OLLAMA_MODEL="qwen2.5:3b"
$env:OLLAMA_URL="http://localhost:11434/api/generate"
$env:EMAIL_ADDRESS="your_email@gmail.com"
$env:EMAIL_APP_PASSWORD="your_gmail_app_password"
$env:EMAIL_TO="your_email@gmail.com"
$env:ENABLE_INBOX_MONITOR="true"
$env:ENABLE_DAILY_REPORT="true"
$env:DAILY_REPORT_HOUR="7"
$env:DAILY_REPORT_MINUTE="30"
$env:ENABLE_SEC_MONITOR="true"
$env:SEC_USER_AGENT="StockBot/0.1 contact:madridchili96@gmail.com"
$env:ENABLE_SEC_TEXT_EXTRACTION="true"
$env:ENABLE_IPO_MONITOR="true"
$env:ENABLE_DASHBOARD_EXPORT="true"
$env:DASHBOARD_INCLUDE_CHARTS="true"
$env:ENABLE_DASHBOARD_AUTO_REFRESH="true"
$env:ENABLE_BACKUPS="true"
```

## Run

```powershell
python main.py
```

The app runs continuously until you press `Ctrl+C`.

## Health Checks

Run diagnostics before leaving StockBot running:

```powershell
python health_check.py
python main.py --health
```

The health check prints `PASS`, `WARN`, and `FAIL` lines for `.env`, email settings, Ollama, SQLite, RSS, SEC, IPO calendar sources, and runtime folders. It does not print secrets.

Filtered Python syntax check:

```powershell
$files = Get-ChildItem -Path . -Recurse -Filter *.py -File | Where-Object { $_.FullName -notmatch '\\.git\\|\\.venv\\|\\logs\\|\\database\\|\\reports\\' } | ForEach-Object { $_.FullName }
python -m py_compile @files
```

For a full MVP readiness pass, use [STABILITY_CHECKLIST.md](STABILITY_CHECKLIST.md). For setup on an older Windows PC, use [DEPLOYMENT.md](DEPLOYMENT.md).

## Signal Scoring And Performance

StockBot can confirm signals with lightweight price/volume data, calculate a final score, and track alert outcomes.

```text
ENABLE_PRICE_CONFIRMATION=true
PRICE_CHECK_INTERVAL_SECONDS=300
ALERT_FINAL_SCORE_MIN=80
ENABLE_PERFORMANCE_TRACKING=true
PERFORMANCE_CHECK_INTERVAL_SECONDS=900
MORNING_BRIEF_MODE=true
```

Final signal score:

```text
final_signal_score = model_confidence + source_score + price_volume_score - risk_penalty
```

Email alerts are sent only when the final score is at least `ALERT_FINAL_SCORE_MIN`. Alert performance is tracked at `1h`, `4h`, `1d`, and `5d` horizons.

Test scoring:

```powershell
python -c "from signal_scoring import build_price_confirmation, final_signal_score; s={'confidence':70,'action':'possible_buy','sentiment':'bullish','source':'SEC EDGAR','matched_symbol':'NVDA'}; q={'current_price':100,'opening_price':98,'percent_move':2.04,'volume':1000000,'provider':'test'}; c=build_price_confirmation(s,q); print(c); print(final_signal_score(s,c))"
```

Test performance tracking:

```powershell
python -c "from config import load_config; from database import initialize_database, create_signal_outcome_rows, get_due_signal_outcomes; c=load_config(); initialize_database(c.database_path); create_signal_outcome_rows(c.database_path, 1, 'NVDA', 100); print(get_due_signal_outcomes(c.database_path))"
```

## Email Watchlist Commands

Reply to a StockBot alert or report email with one command on the first line:

```text
watchlist show
watchlist add NVDA
watchlist remove NVDA
category add artificial intelligence
category remove artificial intelligence
```

The commands update `config/watchlist.json`, deduplicate values, and normalize tickers to uppercase while preserving suffix/futures forms such as `LUMI.ST` and `SIL=F`.

## Dashboard Exports

StockBot can export a broker-free local dashboard on a schedule. It writes offline CSV and HTML files under `reports/dashboard/` with no external scripts, CDNs, credentials, or broker integration.

```text
ENABLE_DASHBOARD_EXPORT=true
DASHBOARD_EXPORT_INTERVAL_SECONDS=1800
DASHBOARD_INCLUDE_CHARTS=true
ENABLE_DASHBOARD_AUTO_REFRESH=true
DASHBOARD_AUTO_REFRESH_SECONDS=300
```

Generated files:

```text
reports/dashboard/dashboard_latest.html
reports/dashboard/watchlist_summary.csv
reports/dashboard/signals_latest.csv
reports/dashboard/ipo_watchlist.csv
reports/dashboard/signal_performance.csv
reports/dashboard/dashboard_summary.json
```

The HTML dashboard uses a simple dark theme, table sections, inline offline charts, optional browser auto-refresh, and the latest bot status from `logs/stockbot_status.json`. Charts include final signal score trend, signal count by ticker, action counts, price/volume confirmation summary, alert performance summary, IPO status counts, and SEC filing form counts. Set `DASHBOARD_INCLUDE_CHARTS=false` to keep the HTML tables-only, or `ENABLE_DASHBOARD_AUTO_REFRESH=false` to disable meta refresh.

For simple email support, `EmailClient.send_dashboard_link()` can send the local dashboard path to `EMAIL_TO`; attachments are not required for the default workflow.

Manually export the dashboard:

```powershell
python dashboard_exporter.py
start reports\dashboard\dashboard_latest.html
```

Test through the Python API:

```powershell
python -c "from config import load_config; from dashboard_exporter import export_dashboard; c=load_config(); print(export_dashboard(c)['dashboard_latest'])"
```

## Tray Controls

`tray_app.py` provides optional local controls. It can open the dashboard, run health checks, export the dashboard, pause/resume monitoring, open the logs folder, and quit the tray app. The main bot reads `logs/stockbot_pause.flag`, so pausing does not require editing `.env`.

```text
ENABLE_TRAY_APP=false
```

Run manually:

```powershell
python tray_app.py
```

If `pystray` and `Pillow` are not installed, it falls back to a console menu instead of crashing.

## Backups

StockBot can back up the SQLite database, `config/watchlist.json`, and generated reports to `backups/YYYY-MM-DD/HHMMSS/`. It does not copy `.env`, logs, `.git`, or `.venv`.

```text
ENABLE_BACKUPS=true
BACKUP_INTERVAL_HOURS=24
BACKUP_KEEP_DAYS=14
```

Run a manual backup:

```powershell
python backup_manager.py
```

## SEC EDGAR And Investor Relations

StockBot can monitor SEC EDGAR company submissions and optional investor-relations RSS feeds as primary-source inputs. SEC and IR items are classified with the same Ollama JSON signal format as news headlines, stored in SQLite, and included in daily reports.

SEC settings:

```text
ENABLE_SEC_MONITOR=true
SEC_USER_AGENT=StockBot/0.1 contact:madridchili96@gmail.com
SEC_CHECK_INTERVAL_SECONDS=900
SEC_FORMS_TO_TRACK=8-K,10-Q,10-K,S-1,SC 13G,SC 13D,4
```

The SEC asks API clients to send a descriptive user agent with contact information. Change `SEC_USER_AGENT` to your preferred contact address before running long term.

The watchlist supports `sec_cik_map` and `investor_relations_feeds`:

```json
{
  "sec_cik_map": {
    "NVDA": "0001045810",
    "AAPL": "0000320193"
  },
  "investor_relations_feeds": [
    "https://investor.nvidia.com/rss/news-releases.xml"
  ]
}
```

SEC filings are tracked by accession number in the `sec_filings` table. New important filings are alerted when model confidence is at least `60`. SEC EDGAR, investor relations, company press releases, and earnings transcripts are treated as primary sources in source verification.

When `ENABLE_SEC_TEXT_EXTRACTION=true`, StockBot downloads the filing document, strips scripts/styles/HTML with lightweight stdlib parsing, saves readable text under `reports/sec_filings/`, and asks Ollama for a conservative primary-source summary. The summary captures key points, potential opportunities, potential risks, sentiment, action, urgency, confidence, and a risk warning.

SEC text extraction settings:

```text
ENABLE_SEC_TEXT_EXTRACTION=true
SEC_TEXT_MAX_CHARS=12000
SEC_SUMMARY_MIN_CONFIDENCE=50
```

Download or parsing failures are logged and do not stop the app.

## IPO Monitoring

StockBot can monitor configurable IPO sources, recent SEC S-1 filings, and basic post-listing prices. IPO rows are stored in SQLite and scored by Ollama using watchlist-only language.

IPO settings:

```text
ENABLE_IPO_MONITOR=true
IPO_CHECK_INTERVAL_SECONDS=3600
IPO_LOOKAHEAD_DAYS=30
IPO_ALERT_MIN_SCORE=70
MARKET_DATA_PROVIDER=stooq
IPO_CALENDAR_SOURCES=nasdaq_api,stockanalysis_csv,manual_csv
DISABLE_NASDAQ_IPO_SOURCE=false
IPO_MANUAL_CSV_PATH=config/ipo_calendar.csv
```

StockBot loads IPOs from multiple structured or best-effort calendar sources. Source failures are logged and do not stop the app.

Health checks report IPO source status source-by-source. If one IPO source passes, StockBot shows a warning for failed optional sources but can continue. If every enabled IPO source fails, the health check fails. Set `DISABLE_NASDAQ_IPO_SOURCE=true` to skip Nasdaq checks entirely when that public endpoint is noisy or blocked.

Supported `IPO_CALENDAR_SOURCES` values:

- `nasdaq_api`: best-effort Nasdaq IPO calendar API.
- `stockanalysis_csv`: best-effort StockAnalysis calendar table parser.
- `manual_csv`: local CSV fallback.

Manual CSV path defaults to:

```text
config/ipo_calendar.csv
```

Manual CSV columns:

```text
company_name,ticker,exchange,ipo_date,expected_price_range,source_url,notes
```

Example row:

```csv
company_name,ticker,exchange,ipo_date,expected_price_range,source_url,notes
Example Robotics,EXRB,NASDAQ,2026-06-15,$18-$20,https://example.com/ipo,Manual test row
```

The watchlist still supports `ipo_feeds` for additional RSS/URL sources:

```json
{
  "ipo_feeds": [
    "https://www.nasdaq.com/market-activity/ipos",
    "https://www.marketwatch.com/tools/ipo-calendar"
  ]
}
```

IPO alerts are sent for new IPO candidates, final price/opening price changes when detected, and high-priority watch scores. Alerts are watchlist notes only and do not recommend buying.

Quick tests:

```powershell
python -c "from config import load_config; c=load_config(); print(c.watchlist_tickers)"
python -c "from config import load_config; from ipo_calendar_client import IPOCalendarClient; c=load_config(); print(IPOCalendarClient(c).fetch_calendar_items()[:3])"
python -c "from market_data_client import MarketDataClient; print(MarketDataClient().get_quote('NVDA'))"
python -c "from config import load_config; from database import initialize_database, get_recent_ipos; c=load_config(); initialize_database(c.database_path); print(get_recent_ipos(c.database_path)[:3])"
```

Manual CSV ingestion test:

```powershell
Set-Content -Path config\ipo_calendar.csv -Value "company_name,ticker,exchange,ipo_date,expected_price_range,source_url,notes`nExample Robotics,EXRB,NASDAQ,2026-06-15,`$18-`$20,https://example.com/ipo,Manual test row"
python -c "from config import load_config; from ipo_calendar_client import IPOCalendarClient; c=load_config(); print(IPOCalendarClient(c).fetch_calendar_items())"
```

IPO dedupe test:

```powershell
python -c "from config import load_config; from database import initialize_database, save_or_update_ipo, get_recent_ipos; c=load_config(); initialize_database(c.database_path); ipo={'company_name':'Example Robotics','ticker':'EXRB','exchange':'NASDAQ','ipo_date':'2026-06-15','expected_price_range':'18-20','source_url':'manual:test','source':'manual_csv','source_quality':7,'status':'upcoming'}; p={'prediction_summary':'watch only','prediction_score':71,'expected_direction':'uncertain','watch_action':'watch','key_drivers':[],'risks':['limited data'],'confidence':50}; print(save_or_update_ipo(c.database_path, ipo, p)); print(save_or_update_ipo(c.database_path, {**ipo, 'source_url':'manual:test2', 'source_quality':8}, p)); print([row for row in get_recent_ipos(c.database_path) if row.get('ticker')=='EXRB'])"
```

Daily report IPO inclusion test:

```powershell
python -c "from config import load_config; from database import initialize_database; from report_generator import build_report_context; c=load_config(); initialize_database(c.database_path); ctx=build_report_context(c); print(ctx['ipos'][:5])"
```

Quick SEC fetch test:

```powershell
python -c "from config import load_config; from sec_edgar_client import SECEdgarClient; c=load_config(); client=SECEdgarClient(c); print(client.fetch_recent_filings('NVDA')[:3])"
```

## Replying To StockBot Emails

When StockBot sends an alert, reply directly to the email. The inbox monitor processes unread replies only when the subject contains `StockBot`, `Re:`, and either `Alert` or `Report`.

Example questions:

- Why did you flag this as bullish?
- Summarize today's alerts.
- Show me all NVDA signals from today.
- Was this confirmed by multiple sources?
- Should I watch this or ignore it?
- Generate my morning report.
- What were the highest confidence bearish signals?

The chatbot is intentionally cautious. It may suggest a `watch`, `possible setup`, `risk`, or `needs confirmation`, but it should not claim certainty or tell you to buy.

## Daily Reports

StockBot can generate one daily market intelligence report per calendar day. The report reviews recent SQLite signals, groups them by ticker/category, ranks the most important items, adds approximate source verification labels, asks Ollama to write an email-friendly report, saves the report to `reports/`, logs it in SQLite, and emails it.

Daily reports include `Primary-source filings/company updates`, `SEC Filing Summaries`, and `IPO Watchlist` sections when relevant rows are available.

Default schedule:

```text
ENABLE_DAILY_REPORT=true
DAILY_REPORT_HOUR=7
DAILY_REPORT_MINUTE=30
DAILY_REPORT_LOOKBACK_HOURS=24
DAILY_REPORT_MIN_CONFIDENCE=50
```

If `DAILY_REPORT_TO` is missing, StockBot sends the report to `EMAIL_TO`.

To test the daily report scheduler, set the hour and minute to the current local time or a minute from now, then run:

```powershell
python main.py
```

To manually generate a report without waiting for the scheduler, run:

```powershell
python -c "from config import load_config; from database import initialize_database; from ollama_client import OllamaClient; from report_generator import generate_daily_report; c=load_config(); initialize_database(c.database_path); o=OllamaClient(c.ollama_url, c.ollama_model, c.http_timeout_seconds); r=generate_daily_report(c, o); print(r['report_path'])"
```

## Source Verification Labels

StockBot assigns source reliability scores and labels:

- `CONFIRMED`: high-quality source, or multiple approximate independent reputable sources.
- `PARTIALLY_CONFIRMED`: reputable source or multiple approximate independent sources, but still needs confirmation.
- `RUMOR_OR_UNVERIFIED`: low-source support, unclear source, social/rumor source, or insufficient corroboration.

This version is approximate. It uses source names and simple lowercase keyword overlap between similar headlines for the same ticker/category. It is not a paid news API, not full source tracing, and not true real-time cross-source verification.

## Troubleshooting

### Ollama Not Running

If logs show Ollama connection errors, start Ollama and verify the model exists:

```powershell
ollama serve
ollama list
ollama pull qwen2.5:3b
```

### Gmail App Password Wrong

If email sending fails with authentication errors, create a new Gmail App Password and update `.env`.

### IMAP Not Enabled

In Gmail settings, make sure IMAP access is enabled. Without IMAP, StockBot can send alerts but cannot read replies.

### No Emails Being Sent

StockBot only sends alerts when:

- `action` is `possible_buy` or `possible_sell`
- `confidence` is at least `70`

Also check that `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, and `EMAIL_TO` are set.

Daily reports use `DAILY_REPORT_TO` when present, otherwise `EMAIL_TO`.

### Bot Replies Going To Spam

Check your spam folder and mark StockBot replies as not spam. If you use a custom domain, make sure SPF, DKIM, and DMARC are configured.

## Data

SQLite database:

```text
database/stockbot.sqlite3
```

Primary-source SEC filings are stored in:

```text
sec_filings
```

IPO watch data is stored in:

```text
ipos
ipo_price_checks
```

Extracted SEC filing text files are saved under:

```text
reports/sec_filings/
```

Logs:

```text
logs/stockbot.log
```

Saved daily reports:

```text
reports/daily_report_YYYY-MM-DD.txt
```

Dashboard exports:

```text
reports/dashboard/dashboard_latest.html
reports/dashboard/*.csv
reports/dashboard/dashboard_summary.json
```

Local secrets in `.env`, SQLite files, and log files are ignored by git.
