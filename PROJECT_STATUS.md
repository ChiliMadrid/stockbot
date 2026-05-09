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

## Current Implemented Features

- RSS/news feed polling for configured tickers and categories.
- Local Ollama headline classification using JSON output.
- SQLite persistence for articles and model signals.
- Email alerts for high-confidence `possible_buy` and `possible_sell` signals.
- Inbox reply detection for StockBot alert/report threads.
- Context-aware chatbot replies using recent SQLite signals and conversations.
- Daily email reports with grouped/ranked signals, source notes, and risk notes.
- Source verification labels: `CONFIRMED`, `PARTIALLY_CONFIRMED`, and `RUMOR_OR_UNVERIFIED`.
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

## Known Limitations

- No paid news APIs yet.
- Source verification uses simple source-name scoring and headline keyword overlap only.
- This is not true real-time cross-source verification yet.
- RSS feeds can be delayed, duplicated, or missing key primary-source context.

## Next Recommended Step

Add SEC EDGAR and company investor relations source ingestion.
