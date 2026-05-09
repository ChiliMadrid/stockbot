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
```

## Run

```powershell
python main.py
```

The app runs continuously until you press `Ctrl+C`.

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

Daily reports include `Primary-source filings/company updates` and `SEC Filing Summaries` sections when recent SEC filings or company updates are available.

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

Local secrets in `.env`, SQLite files, and log files are ignored by git.
