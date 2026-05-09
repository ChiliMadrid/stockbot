# Project Status

## What Changed

- Replaced the default Telegram alert workflow with email alerts through SMTP.
- Added IMAP inbox monitoring for replies to StockBot alert and report emails.
- Added an Ollama-powered email chatbot response flow.
- Updated SQLite storage with articles, signals, run logs, email messages, and chatbot conversations.
- Added `.env.example` and `.gitignore` so secrets and local runtime files stay out of git.
- Added daily market intelligence report generation.
- Added approximate source verification labels and reliability scoring.
- Added `daily_reports` SQLite tracking and report file output under `reports/`.
- Added SEC EDGAR submissions ingestion for tracked CIKs/forms.
- Added investor-relations RSS ingestion for optional company feeds.
- Added `sec_filings` SQLite tracking by accession number.
- Added SEC filing text extraction and primary-source summary generation.

## Current Implemented Features

- RSS/news feed polling for configured tickers and categories.
- Local Ollama headline classification using JSON output.
- SQLite persistence for articles and model signals.
- Email alerts for high-confidence `possible_buy` and `possible_sell` signals.
- Inbox reply detection for StockBot alert/report threads.
- Context-aware chatbot replies using recent SQLite signals and conversations.
- Daily email reports with grouped/ranked signals, source notes, and risk notes.
- Source verification labels: `CONFIRMED`, `PARTIALLY_CONFIRMED`, and `RUMOR_OR_UNVERIFIED`.
- SEC filings and investor-relations updates treated as primary-source inputs.
- Daily report section for primary-source filings/company updates.
- SEC filing summaries with extracted text paths, key points, risks, action, and confidence.
- Continuous Windows-compatible main loop with Ctrl+C shutdown.

## How To Test Email Sending

1. Copy `.env.example` to `.env`.
2. Fill in `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, and `EMAIL_TO`.
3. Run `python main.py`.
4. Watch `logs/stockbot.log` for `Email sent` entries when high-confidence signals appear.

## How To Test Inbox Reply Chatbot

1. Start the app with `ENABLE_INBOX_MONITOR=true`.
2. Reply to a StockBot alert or report email.
3. Make sure the subject includes `Re:`, `StockBot`, and either `Alert` or `Report`.
4. Ask a question such as `Why did you flag this as bullish?`.
5. Watch for an emailed response and a row in `chatbot_conversations`.

## How To Test Daily Reports

1. Set `ENABLE_DAILY_REPORT=true`.
2. Set `DAILY_REPORT_HOUR` and `DAILY_REPORT_MINUTE` to the current local time or a minute from now.
3. Run `python main.py`.
4. Watch for a saved report in `reports/` and a row in `daily_reports`.
5. If email credentials are configured, watch `logs/stockbot.log` for the daily report email send result.

## How To Test SEC EDGAR

Run:

```powershell
python -c "from config import load_config; from sec_edgar_client import SECEdgarClient; c=load_config(); client=SECEdgarClient(c); print(client.fetch_recent_filings('NVDA')[:3])"
```

To test the live app path, set `ENABLE_SEC_MONITOR=true`, confirm `SEC_USER_AGENT` includes contact info, then run `python main.py`.

## How To Test SEC Text Extraction

Run:

```powershell
python -m compileall .
python -c "from config import load_config; from sec_edgar_client import SECEdgarClient; c=load_config(); client=SECEdgarClient(c); f=client.fetch_recent_filings('NVDA')[0]; print(f['filing_url'])"
```

For the full summary path, make sure Ollama is running and `ENABLE_SEC_TEXT_EXTRACTION=true`, then run `python main.py`.

## Known Limitations

- No paid news APIs yet.
- Source verification uses simple source-name scoring and headline keyword overlap only.
- This is not true real-time cross-source verification yet.
- RSS feeds can be delayed, duplicated, or missing key primary-source context.
- SEC filing text extraction is lightweight and does not parse XBRL tables deeply yet.
- Investor-relations feeds must be configured manually in `config/watchlist.json`.

## Next Recommended Step

Add deeper XBRL/financial table extraction for SEC filings.
