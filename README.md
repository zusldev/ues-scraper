# UES Learning → Telegram (Playwright) — Modular

**Author:** zusldev

> **Disclaimer:** This project is for educational purposes only. Use at your own risk. The author is not responsible for any misuse, account bans, or legal issues arising from the usage of this script. Scraping may violate the terms of service of the target platform.

This project monitors the **Dashboard** of UES Learning, detects **new/changed activities**, and sends:

- A **batch** with changes (to avoid spam).
- A **summary** grouped by urgency: urgent, overdue, upcoming, submitted, etc.

## Requirements

- Python 3.9+ (recommended for `zoneinfo` support)
- Playwright + browser:
  ```bash
  pip install playwright requests beautifulsoup4 python-dotenv
  python -m playwright install
  ```

## Configuration (Environment Variables)

### Required
- `TG_BOT_TOKEN` — your Telegram bot token
- `TG_CHAT_ID` — destination chat id (your user or a group)
- `UES_USER` — portal username
- `UES_PASS` — portal password

### Optional (new features)
- `UES_TZ` — timezone (default: `America/Mazatlan`)
- `UES_QUIET_START` — quiet hours start (default `00:00`)
- `UES_QUIET_END` — quiet hours end (default `07:00`)
- `UES_BASE` — base URL (default `https://ueslearning.ues.mx`)
- `UES_DASHBOARD_URL` — dashboard URL (default `${UES_BASE}/my/`)
- `UES_STATE_FILE` — state JSON file (default `seen_events.json`)
- `UES_STORAGE_FILE` — Playwright session file (default `storage_state.json`)
- `UES_LOG_FILE` — log file (default `ues_to_telegram.log`)

## Use `.env` (recommended)

Create a `.env` file in the same folder as `main.py`, for example:

```env
TG_BOT_TOKEN=123456:ABCDEF...
TG_CHAT_ID=123456789
UES_USER=your_username
UES_PASS=your_password

# Optional
UES_TZ=America/Mazatlan
UES_QUIET_START=00:00
UES_QUIET_END=07:00
```

## Running

### Normal mode (headless)
```bash
python main.py
```

### Show browser (headful)
```bash
python main.py --headful
```

### Test without Telegram messages (dry run)
```bash
python main.py --dry-run
```

### Change quiet hours
```bash
python main.py --quiet-start 22:00 --quiet-end 07:00
```

### Change urgency threshold
```bash
python main.py --urgent-hours 12
```

### Notification controls
- By default, behaves as **only changes** (batch of changes + summary).
- To force notifications even if there are no changes:
```bash
python main.py --notify-unchanged
```

## Project Structure

```
.
├── main.py
└── ues_bot/
   ├── config.py
   ├── logging_utils.py
   ├── models.py
   ├── scrape.py
   ├── state.py
   ├── summary.py
   ├── telegram_client.py
   └── utils.py
```

## Notes
- The summary does NOT include links (designed for fast reading).
- The batch of changes DOES include a link (assignment or event).
- If the portal HTML changes, you may need to adjust selectors in `ues_bot/scrape.py`.
