# Local AI Stock Intelligence System

A simple Windows-friendly local stock intelligence starter project.

This project polls RSS feeds, filters stories by tickers and categories, sends matching headlines to a local Ollama model, stores structured sentiment results in SQLite, and can send Telegram alerts for important signals.

## What is included

- RSS polling with `feedparser`
- Local Ollama API calls through `requests`
- SQLite initialization and storage
- Telegram alert function using `python-telegram-bot`
- Sample watchlist configuration
- Logging to console and `logs/stockbot.log`
- Simple modular Python files

## Requirements

- Python 3.11
- Ollama running locally
- A local Ollama model such as `llama3.1`
- Optional Telegram bot token and chat ID

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Make sure Ollama is running:

```powershell
ollama serve
```

Pull a model if needed:

```powershell
ollama pull llama3.1
```

Run the project:

```powershell
python main.py
```

By default, the app runs one polling cycle and exits. To run continuously:

```powershell
$env:STOCKBOT_POLL_ONCE="false"
python main.py
```

## Configuration

Edit:

```text
config/watchlist.json
```

Optional environment variables:

```powershell
$env:OLLAMA_MODEL="llama3.1"
$env:OLLAMA_URL="http://localhost:11434/api/generate"
$env:TELEGRAM_ENABLED="true"
$env:TELEGRAM_BOT_TOKEN="your_bot_token"
$env:TELEGRAM_CHAT_ID="your_chat_id"
$env:STOCKBOT_ALERT_SCORE_THRESHOLD="7"
$env:STOCKBOT_POLL_INTERVAL_SECONDS="900"
```

## Project Structure

```text
stockbot/
  main.py
  config.py
  requirements.txt
  rss_monitor.py
  ollama_client.py
  telegram_alerts.py
  database.py
  utils.py
  README.md
  config/
    watchlist.json
  database/
    .gitkeep
  logs/
    .gitkeep
  reports/
    .gitkeep
```

## Notes

This is a starter system, not financial advice and not a trading bot. It does not place trades and does not depend on cloud services.
