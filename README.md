# UES Learning → Telegram (Playwright) — Modular

**Author:** zusldev

> **Disclaimer:** This project is for educational purposes only. Use at your own risk. The author is not responsible for any misuse, account bans, or legal issues arising from the usage of this script. Scraping may violate the terms of service of the target platform.

This project monitors the **Dashboard** of UES Learning, detects **new/changed activities**, and sends:

- A **batch** with changes (to avoid spam).
- A **summary** grouped by urgency: urgent, overdue, upcoming, submitted, etc.
- Runs as a **long-lived Telegram bot** with interactive commands (`/resumen`, `/dormir`, `/estado`, etc.).

## Changelog

- Full release history: `CHANGELOG.md`
- Latest release highlights: `v1.2.0` adds long-running interactive bot mode, command controls, and scraping concurrency hardening.

## Requirements

- Python 3.9+ (recommended for `zoneinfo` support)
- Playwright + browser:
  ```bash
  pip install playwright beautifulsoup4 python-dotenv python-telegram-bot[job-queue]
  python -m playwright install
  ```

## Configuration (Environment Variables)

### Required
- `TG_BOT_TOKEN` — your Telegram bot token
- `TG_CHAT_ID` — destination chat id (your user or a group)
- `UES_USER` — portal username
- `UES_PASS` — portal password

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

### Start bot (polling, headless browser)
```bash
python main.py
```

### Show browser (headful)
```bash
python main.py --headful
```

### Test without Telegram messages
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

### Notification controls (automatic job)
- Default behavior: send changes + summary.
- Force notifications even with no detected changes:
```bash
python main.py --notify-unchanged
```

### Telegram commands
- `/dormir <horas>` silencia notificaciones automáticas por X horas (default 8)
- `/despertar` cancela modo dormido
- `/resumen` fuerza scraping + resumen completo
- `/urgente` fuerza scraping + urgentes/vencidos no entregados
- `/pendientes` fuerza scraping + submitted=False
- `/estado` muestra estado operativo
- `/silencio <HH:MM> <HH:MM>` cambia quiet hours en caliente
- `/intervalo <minutos>` cambia frecuencia del job automático
- `/help` muestra ayuda

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
- If the portal HTML changes, you may need to adjust selectors in `ues_bot/scrape.py`.
