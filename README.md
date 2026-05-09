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
```

You can also set values directly in Windows PowerShell:

```powershell
$env:OLLAMA_MODEL="qwen2.5:3b"
$env:OLLAMA_URL="http://localhost:11434/api/generate"
$env:EMAIL_ADDRESS="your_email@gmail.com"
$env:EMAIL_APP_PASSWORD="your_gmail_app_password"
$env:EMAIL_TO="your_email@gmail.com"
$env:ENABLE_INBOX_MONITOR="true"
```

## Run

```powershell
python main.py
```

The app runs continuously until you press `Ctrl+C`.

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

### Bot Replies Going To Spam

Check your spam folder and mark StockBot replies as not spam. If you use a custom domain, make sure SPF, DKIM, and DMARC are configured.

## Data

SQLite database:

```text
database/stockbot.sqlite3
```

Logs:

```text
logs/stockbot.log
```

Local secrets in `.env`, SQLite files, and log files are ignored by git.
