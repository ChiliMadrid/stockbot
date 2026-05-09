# Old Windows PC Deployment Guide

This guide sets up StockBot on a local Windows PC with no cloud dependency required.

## 1. Install Prerequisites

- Install Python 3.11 from python.org.
- Install Git for Windows.
- Install Ollama for Windows.
- Install VS Code if you want a simple editor.

Restart PowerShell after installing Python or Git if commands are not found.

## 2. Clone The Repo

```powershell
cd C:\
mkdir StockBot
cd StockBot
git clone https://github.com/ChiliMadrid/stockbot.git
cd stockbot
```

## 3. Create A Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then reopen PowerShell and activate the venv again.

## 4. Create `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in local values. Do not commit `.env`.

Minimum useful settings:

```env
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_TO=your_email@gmail.com
ENABLE_TRAY_APP=false
```

## 5. Install And Pull The Ollama Model

Start Ollama, then run:

```powershell
ollama pull qwen2.5:3b
ollama list
```

## 6. Run Health Checks

```powershell
python health_check.py
python main.py --health
```

Warnings can be acceptable for optional sources, but fix failures before leaving the bot running.

## 7. Run StockBot

```powershell
python main.py
```

Stop it with `Ctrl+C`.

## 8. Open The Dashboard

```powershell
python dashboard_exporter.py
start reports\dashboard\dashboard_latest.html
```

The dashboard is static and offline. If enabled, it uses a meta refresh to reload from disk.

## 9. Optional Tray Controls

Tray controls are disabled by default:

```env
ENABLE_TRAY_APP=false
```

Run manually:

```powershell
python tray_app.py
```

If optional tray packages are missing, StockBot opens a console fallback menu. To try a real tray icon:

```powershell
pip install pystray pillow
python tray_app.py
```

## 10. Backups And Restore

Manual backup:

```powershell
python backup_manager.py
```

Backups are saved under:

```text
backups/YYYY-MM-DD/HHMMSS/
```

To restore the database, stop StockBot, copy the backed-up `.sqlite3` file into `database/`, then restart:

```powershell
Copy-Item backups\YYYY-MM-DD\HHMMSS\database\stockbot.sqlite3 database\stockbot.sqlite3
python main.py
```

To restore the watchlist:

```powershell
Copy-Item backups\YYYY-MM-DD\HHMMSS\config\watchlist.json config\watchlist.json
```

## 11. Update From GitHub

Stop StockBot first, then run:

```powershell
git pull
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python health_check.py
```

## 12. Troubleshooting

Ollama not reachable:

```powershell
ollama list
```

If `health_check.py` cannot reach Ollama, start Ollama and confirm `OLLAMA_URL`.

Email not sending:

- Confirm Gmail App Password is correct.
- Confirm `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, and `EMAIL_TO`.
- Check spam folders for bot replies.

IMAP replies not working:

- Confirm IMAP is enabled in Gmail.
- Confirm `ENABLE_INBOX_MONITOR=true`.
- Reply to a StockBot email with `Re:` in the subject.

Dashboard not updating:

```powershell
python dashboard_exporter.py
start reports\dashboard\dashboard_latest.html
```

Backups not appearing:

- Confirm `ENABLE_BACKUPS=true`.
- Confirm `backups/` is writable.
- Run `python backup_manager.py` manually.

Old PC feels slow:

- Increase polling intervals in `.env`.
- Disable optional features you do not need.
- Keep `ENABLE_TRAY_APP=false` unless you installed tray dependencies.
