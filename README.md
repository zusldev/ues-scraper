# UES to Telegram Scraper

**Author:** zusldev

## Description

Script that scrapes the UES Learning portal (ueslearning.ues.mx) and sends notifications to Telegram about new or changed assignments, events, and deadlines.

## Requirements

- Python 3.8+
- Playwright
- requests
- beautifulsoup4

Install dependencies:

```bash
pip install playwright requests beautifulsoup4
python -m playwright install
```

## Environment Variables

Set the following environment variables:

| Variable | Description |
|----------|-------------|
| `TG_BOT_TOKEN` | Telegram Bot API Token |
| `TG_CHAT_ID` | Telegram Chat ID to send messages |
| `UES_USER` | UES portal username |
| `UES_PASS` | UES portal password |

## Usage

```bash
python ues_scr.py
```

## Features

- Automatic login with session persistence
- Detects new and changed events
- Sends detailed messages for new/changed assignments
- Sends a quick summary with status, course, and remaining time
- Tracks submitted/not submitted status

## Files

- `ues_scr.py` - Main script
- `seen_events.json` - Tracks previously seen events (auto-generated)
- `storage_state.json` - Browser session state (auto-generated)
