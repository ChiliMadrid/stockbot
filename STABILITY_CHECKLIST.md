# StockBot Stability Checklist

Use this before leaving StockBot running unattended on a local Windows PC.

## Configuration

- `.env` exists locally and is not committed.
- `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, and `EMAIL_TO` are set if email alerts are needed.
- `OLLAMA_URL` points to the local Ollama generate endpoint.
- `OLLAMA_MODEL` is installed locally with `ollama pull qwen2.5:3b`.
- `SEC_USER_AGENT` includes a real contact address.
- `ENABLE_TRAY_APP=false` unless optional tray dependencies are installed.

## Local Files

- `.env`, logs, SQLite databases, generated reports, dashboard exports, and backups are ignored by git.
- `database/`, `logs/`, `reports/`, `reports/dashboard/`, and `backups/` are writable.
- `config/watchlist.json` exists or the default watchlist in `config.py` is acceptable.
- Backups are enabled with a retention window that fits disk space.

## Runtime Checks

- Run the filtered syntax check:

```powershell
$files = Get-ChildItem -Path . -Recurse -Filter *.py -File | Where-Object { $_.FullName -notmatch '\\.git\\|\\.venv\\|\\logs\\|\\database\\|\\reports\\|\\backups\\' } | ForEach-Object { $_.FullName }
python -m py_compile @files
```

- Run diagnostics:

```powershell
python health_check.py
python main.py --health
```

- Export and open the local dashboard:

```powershell
python dashboard_exporter.py
start reports\dashboard\dashboard_latest.html
```

- Run a manual backup:

```powershell
python backup_manager.py
```

## Main Loop

- News, SEC/IR, IPO, performance, dashboard, backup, and daily report schedules are separate.
- The tray pause flag only pauses monitoring/report work; dashboard exports and backups can still run.
- `logs/stockbot_status.json` should show `running`, `paused`, `error`, or `stopped`.
- `Ctrl+C` should stop `python main.py` cleanly.

## Known MVP Limits

- Source verification is approximate.
- RSS and public IPO sources can be delayed or change shape.
- SEC filing text extraction is lightweight and does not deeply parse XBRL tables.
- Optional tray icon mode requires `pystray` and `Pillow`; otherwise use the console fallback.
- This system is decision support only and does not place trades.
