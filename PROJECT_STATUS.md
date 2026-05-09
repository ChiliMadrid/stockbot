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
- Added IPO monitoring with configurable IPO feeds, S-1 candidates, Stooq price checks, email alerts, and daily report output.
- Added robust IPO calendar ingestion with Nasdaq API, StockAnalysis best-effort parsing, and manual CSV fallback.
- Added diagnostics and health checks through `health_check.py` and `python main.py --health`.
- Added price/volume confirmation, final signal scoring, alert performance tracking, email watchlist commands, and upgraded morning brief sections.
- Added broker-free dashboard exports with offline HTML and CSV files under `reports/dashboard/`.

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
- IPO watchlist rows with prediction summaries, scores, risks, and price checks.
- IPO source quality tracking, dedupe by ticker/company/date, and missing price warnings in reports.
- Health checks for env loading, email config, Ollama, SQLite, RSS, SEC, IPO sources, and runtime directories.
- Final signal scoring with `model_confidence + source_score + price_volume_score - risk_penalty`.
- Alert outcome tracking for 1h, 4h, 1d, and 5d horizons.
- Email commands for showing/updating tickers and categories.
- Scheduled dashboard export for watchlists, latest signals, final scores, price/volume confirmations, IPOs, SEC/IR updates, signal performance, and top risks.
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
$files = Get-ChildItem -Path . -Recurse -Filter *.py -File | Where-Object { $_.FullName -notmatch '\\.git\\|\\.venv\\|\\logs\\|\\database\\|\\reports\\' } | ForEach-Object { $_.FullName }
python -m py_compile @files
python -c "from config import load_config; from sec_edgar_client import SECEdgarClient; c=load_config(); client=SECEdgarClient(c); f=client.fetch_recent_filings('NVDA')[0]; print(f['filing_url'])"
```

For the full summary path, make sure Ollama is running and `ENABLE_SEC_TEXT_EXTRACTION=true`, then run `python main.py`.

## How To Test IPO Monitoring

Run:

```powershell
$files = Get-ChildItem -Path . -Recurse -Filter *.py -File | Where-Object { $_.FullName -notmatch '\\.git\\|\\.venv\\|\\logs\\|\\database\\|\\reports\\' } | ForEach-Object { $_.FullName }
python -m py_compile @files
python -c "from config import load_config; c=load_config(); print(c.watchlist_tickers)"
python -c "from config import load_config; from ipo_calendar_client import IPOCalendarClient; c=load_config(); print(IPOCalendarClient(c).fetch_calendar_items()[:3])"
python -c "from market_data_client import MarketDataClient; print(MarketDataClient().get_quote('NVDA'))"
python -c "from config import load_config; from database import initialize_database, get_recent_ipos; c=load_config(); initialize_database(c.database_path); print(get_recent_ipos(c.database_path)[:3])"
```

## How To Run Health Checks

```powershell
python health_check.py
python main.py --health
```

## How To Test Signal Scoring

```powershell
python -c "from signal_scoring import build_price_confirmation, final_signal_score; s={'confidence':70,'action':'possible_buy','sentiment':'bullish','source':'SEC EDGAR','matched_symbol':'NVDA'}; q={'current_price':100,'opening_price':98,'percent_move':2.04,'volume':1000000,'provider':'test'}; c=build_price_confirmation(s,q); print(c); print(final_signal_score(s,c))"
```

## How To Test Watchlist Email Commands

```powershell
python -c "from config import load_config; from inbox_monitor import InboxMonitor; from ollama_client import OllamaClient; from email_client import EmailClient; c=load_config(); m=InboxMonitor(c, OllamaClient(c.ollama_url,c.ollama_model), EmailClient(c)); print(m._handle_watchlist_command('watchlist show'))"
```

## How To Test Performance Tracking

```powershell
python -c "from config import load_config; from database import initialize_database, create_signal_outcome_rows, get_due_signal_outcomes; c=load_config(); initialize_database(c.database_path); create_signal_outcome_rows(c.database_path, 1, 'NVDA', 100); print(get_due_signal_outcomes(c.database_path))"
```

## How To Test Dashboard Exports

```powershell
python dashboard_exporter.py
python -c "from config import load_config; from dashboard_exporter import export_dashboard; c=load_config(); print(export_dashboard(c)['dashboard_latest'])"
```

Manual CSV ingestion:

```powershell
Set-Content -Path config\ipo_calendar.csv -Value "company_name,ticker,exchange,ipo_date,expected_price_range,source_url,notes`nExample Robotics,EXRB,NASDAQ,2026-06-15,`$18-`$20,https://example.com/ipo,Manual test row"
python -c "from config import load_config; from ipo_calendar_client import IPOCalendarClient; c=load_config(); print(IPOCalendarClient(c).fetch_calendar_items())"
```

IPO dedupe:

```powershell
python -c "from config import load_config; from database import initialize_database, save_or_update_ipo, get_recent_ipos; c=load_config(); initialize_database(c.database_path); ipo={'company_name':'Example Robotics','ticker':'EXRB','exchange':'NASDAQ','ipo_date':'2026-06-15','expected_price_range':'18-20','source_url':'manual:test','source':'manual_csv','source_quality':7,'status':'upcoming'}; p={'prediction_summary':'watch only','prediction_score':71,'expected_direction':'uncertain','watch_action':'watch','key_drivers':[],'risks':['limited data'],'confidence':50}; print(save_or_update_ipo(c.database_path, ipo, p)); print(save_or_update_ipo(c.database_path, {**ipo, 'source_url':'manual:test2', 'source_quality':8}, p)); print([row for row in get_recent_ipos(c.database_path) if row.get('ticker')=='EXRB'])"
```

Daily report inclusion:

```powershell
python -c "from config import load_config; from database import initialize_database; from report_generator import build_report_context; c=load_config(); initialize_database(c.database_path); ctx=build_report_context(c); print(ctx['ipos'][:5])"
```

For the full monitor path, make sure Ollama is running and `ENABLE_IPO_MONITOR=true`, then run `python main.py`.

## Known Limitations

- No paid news APIs yet.
- Source verification uses simple source-name scoring and headline keyword overlap only.
- This is not true real-time cross-source verification yet.
- RSS feeds can be delayed, duplicated, or missing key primary-source context.
- SEC filing text extraction is lightweight and does not parse XBRL tables deeply yet.
- Investor-relations feeds must be configured manually in `config/watchlist.json`.
- IPO calendar sources are best-effort; public pages/APIs can change shape or block automated requests.
- Stooq price checks are lightweight and may not cover every suffix, future, or newly listed symbol.
- Dashboard exports are static local files and do not auto-refresh in an open browser tab.

## Next Recommended Step

Add price/volume visualization and dashboard trend charts without broker integration.
