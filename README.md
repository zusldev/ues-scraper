# UES Learning → Telegram (Playwright) — Modular

**Author:** zusldev

> **Disclaimer:** This project is for educational purposes only. Use at your own risk. The author is not responsible for any misuse, account bans, or legal issues arising from the usage of this script. Scraping may violate the terms of service of the target platform.

Este proyecto revisa el **Dashboard** de UES Learning, detecta **actividades nuevas/cambiadas**, y envía:

- Un **batch** con cambios (para evitar spam).
- Un **resumen** agrupado por urgencia: urgente, vencidos, próximos, enviados, etc.

## Requisitos

- Python 3.9+ (recomendado por `zoneinfo`)
- Playwright + navegador:
  ```bash
  pip install playwright requests beautifulsoup4 python-dotenv
  python -m playwright install
  ```

## Configuración (variables de entorno)

### Obligatorias
- `TG_BOT_TOKEN` — token de tu bot de Telegram
- `TG_CHAT_ID` — chat id destino (tu usuario o un grupo)
- `UES_USER` — usuario del portal
- `UES_PASS` — contraseña del portal

### Opcionales (nuevas funciones)
- `UES_TZ` — zona horaria (default: `America/Mazatlan`)
- `UES_QUIET_START` — inicio quiet hours (default `00:00`)
- `UES_QUIET_END` — fin quiet hours (default `07:00`)
- `UES_BASE` — base URL (default `https://ueslearning.ues.mx`)
- `UES_DASHBOARD_URL` — URL del dashboard (default `${UES_BASE}/my/`)
- `UES_STATE_FILE` — JSON de estado (default `seen_events.json`)
- `UES_STORAGE_FILE` — sesión Playwright (default `storage_state.json`)
- `UES_LOG_FILE` — archivo log (default `ues_to_telegram.log`)

## Usar `.env` (recomendado)

Crea un archivo `.env` en la misma carpeta que `main.py`, por ejemplo:

```env
TG_BOT_TOKEN=123456:ABCDEF...
TG_CHAT_ID=123456789
UES_USER=tu_usuario
UES_PASS=tu_password

# Opcional
UES_TZ=America/Mazatlan
UES_QUIET_START=00:00
UES_QUIET_END=07:00
```

## Ejecución

### Modo normal (headless)
```bash
python main.py
```

### Ver el navegador (headful)
```bash
python main.py --headful
```

### Probar sin mandar Telegram
```bash
python main.py --dry-run
```

### Cambiar quiet hours
```bash
python main.py --quiet-start 22:00 --quiet-end 07:00
```

### Cambiar umbral de urgencia
```bash
python main.py --urgent-hours 12
```

### Control de notificaciones
- Por defecto se comporta como **solo cambios** (batch de cambios + resumen).
- Para forzar notificar aunque no haya cambios:
```bash
python main.py --notify-unchanged
```

## Estructura del proyecto

```
.
├─ main.py
└─ ues_bot/
   ├─ config.py
   ├─ logging_utils.py
   ├─ models.py
   ├─ scrape.py
   ├─ state.py
   ├─ summary.py
   ├─ telegram_client.py
   └─ utils.py
```

## Notas

- El resumen NO incluye links (diseñado para lectura rápida).
- El batch de cambios sí incluye link (assignment o evento).
- Si cambia el HTML del portal, puede requerir ajustar selectores en `ues_bot/scrape.py`.
