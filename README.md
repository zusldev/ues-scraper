# UES Learning -> Telegram (Playwright) - Modular

**Author:** zusldev

> **Disclaimer:** This project is for educational purposes only. Use at your own risk. The author is not responsible for any misuse, account bans, or legal issues arising from the usage of this script. Scraping may violate the terms of service of the target platform.

Este proyecto monitorea el **Dashboard** de UES Learning, detecta actividades nuevas/cambiadas y envia notificaciones a Telegram en formato util para seguimiento academico.

## Indice

- [Estado actual del proyecto](#estado-actual-del-proyecto)
- [Novedades implementadas](#novedades-implementadas)
- [Changelog](#changelog)
- [Requisitos](#requisitos)
- [Dependencias y por que se usan](#dependencias-y-por-que-se-usan)
- [Configuracion por variables de entorno](#configuracion-por-variables-de-entorno)
- [Uso de `.env` (recomendado)](#uso-de-env-recomendado)
- [Ejecucion](#ejecucion)
- [Comandos Telegram](#comandos-telegram)
- [Automatismos implementados](#automatismos-implementados)
- [Estructura de proyecto](#estructura-de-proyecto)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Documentacion complementaria](#documentacion-complementaria)

## Estado actual del proyecto

- Implementado: mejoras criticas y de funcionalidad de la fase activa (resiliencia, observabilidad, comandos nuevos, recordatorios).
- Pendiente: roadmap futuro documentado en `docs/PENDING_ROADMAP.md`.
- Guia de uso completa: `docs/FEATURE_GUIDE.md`.

## Novedades implementadas

- Reintentos robustos con `tenacity` para navegacion de scraping y envio de mensajes Telegram.
- Rotacion de logs en archivo con limite de tamano y backups.
- Alerta automatica al chat cuando hay 3+ fallos consecutivos de scraping.
- Guardado de estado en shutdown para minimizar perdida de estado operativo.
- Recordatorios escalonados para pendientes (`24h`, `6h`, `1h`).
- Comando nuevo `/calendario` para vista semanal.
- Comando nuevo `/config` para inspeccionar configuracion activa.
- Comando nuevo `/stats` para metricas operativas.
- Rate limiting para comandos que disparan scraping manual (cooldown de 60s).
- Suite de pruebas reorganizada y ampliada (`47` tests).

## Changelog

- Historial completo: `CHANGELOG.md`
- Ultima base estable: `v1.2.0`
- Cambios recientes locales: revisa la seccion `Unreleased` en `CHANGELOG.md`

## Requisitos

- Python 3.9+ (recomendado para `zoneinfo`)
- Dependencias del proyecto:
  ```bash
  pip install -r requirements.txt
  python -m playwright install
  ```

## Dependencias y por que se usan

- `playwright`: automatiza navegador Chromium para login/navegacion real del portal.
- `beautifulsoup4`: parseo de HTML para extraer eventos, estados y enlaces.
- `python-dotenv`: carga variables de entorno desde `.env`.
- `python-telegram-bot[job-queue]`: bot de larga ejecucion + scheduler interno periodico.
- `tenacity`: politicas de retry con backoff para reducir fallas transitorias de red/portal.

## Configuracion por variables de entorno

### Requeridas

- `TG_BOT_TOKEN`: token del bot de Telegram.
- `TG_CHAT_ID`: chat autorizado para comandos y destino de notificaciones.
- `UES_USER`: usuario UES.
- `UES_PASS`: password UES.

### Opcionales

- `UES_TZ`: timezone (default `America/Mazatlan`).
- `UES_QUIET_START`: inicio de quiet hours (default `00:00`).
- `UES_QUIET_END`: fin de quiet hours (default `07:00`).
- `UES_SCRAPE_INTERVAL_MIN`: intervalo periodico en minutos (default `60`).
- `UES_SCRAPE_LOCK_WAIT_SEC`: espera de lock para comandos on-demand (default `12`).
- `UES_URGENT_HOURS`: umbral de urgencia en horas (default `24`).
- `UES_MAX_CHANGE_ITEMS`: maximo de items por mensaje de cambios (default `12`).
- `UES_MAX_SUMMARY_LINES`: maximo de lineas de resumen (default `18`).
- `UES_BASE`: base URL del portal (default `https://ueslearning.ues.mx`).
- `UES_DASHBOARD_URL`: dashboard URL (default `${UES_BASE}/my/`).
- `UES_STATE_FILE`: archivo JSON de estado (default `seen_events.json`).
- `UES_STORAGE_FILE`: archivo de sesion Playwright (default `storage_state.json`).
- `UES_LOG_FILE`: archivo log (default `ues_to_telegram.log`).
- `UES_ONLY_CHANGES`: notificar solo cambios (`true`/`false`, default `true`).
- `UES_NOTIFY_UNCHANGED`: permitir notificar sin cambios (`true`/`false`, default `false`).

## Uso de `.env` (recomendado)

Crea un archivo `.env` junto a `main.py`:

```env
TG_BOT_TOKEN=123456:ABCDEF...
TG_CHAT_ID=123456789
UES_USER=your_username
UES_PASS=your_password

# Opcionales
UES_TZ=America/Mazatlan
UES_QUIET_START=00:00
UES_QUIET_END=07:00
UES_SCRAPE_INTERVAL_MIN=60
UES_URGENT_HOURS=24
```

## Ejecucion

### Inicio normal

```bash
python main.py
```

### Headful (debug visual)

```bash
python main.py --headful
```

### Dry run (sin enviar Telegram)

```bash
python main.py --dry-run
```

### Ajustes por CLI

```bash
python main.py --quiet-start 22:00 --quiet-end 07:00
python main.py --urgent-hours 12
python main.py --notify-unchanged
python main.py --scrape-interval-min 30
```

## Comandos Telegram

- `/dormir <horas>`: silencia notificaciones automaticas por X horas (default 8).
- `/despertar`: cancela modo dormido.
- `/resumen`: fuerza scraping + resumen completo.
- `/urgente`: fuerza scraping + urgentes/vencidos no entregados.
- `/pendientes`: fuerza scraping + tareas `submitted=False`.
- `/calendario`: fuerza scraping + vista semanal agrupada por dia.
- `/iphonecal`: exporta pendientes a archivo `.ics` para importarlo en iPhone Calendar.
- `/estado`: muestra estado operativo (incluye ultimo error).
- `/silencio <HH:MM> <HH:MM>`: cambia quiet hours en caliente.
- `/intervalo <minutos>`: cambia frecuencia del job automatico.
- `/config`: muestra configuracion activa cargada en runtime.
- `/stats`: muestra metricas de scraping (totales, exitos/fallos, tiempos).
- `/help`: ayuda de comandos.

> Nota: `/resumen`, `/urgente`, `/pendientes` y `/calendario` comparten cooldown de `60s` para evitar spam/carga excesiva.

## Automatismos implementados

- **Quiet hours:** pausa notificaciones automaticas por ventana horaria.
- **Sleep mode:** pausa manual temporal con `/dormir`.
- **Alertas de fallo:** notifica cuando se acumulan `3+` errores consecutivos de scraping.
- **Recordatorios escalonados:** pendientes reciben avisos cercanos al vencimiento (`24h`, `6h`, `1h`).
- **Resumen por secciones:** urgente, vencidos, proximos, enviados, sin fecha, futuro.

## Estructura de proyecto

```text
.
|- main.py
|- requirements.txt
|- pytest.ini
|- tests/
|  |- test_commands.py
|  |- test_utils.py
|  |- test_state.py
|  |- test_summary.py
|  |- test_scrape_parse.py
|  |- test_logging.py
|  |- test_retries.py
|  |- test_error_handling.py
|  |- test_reminders.py
|  \- test_calendar.py
|- docs/
|  |- FEATURE_GUIDE.md
|  \- PENDING_ROADMAP.md
\- ues_bot/
   |- commands.py
   |- config.py
   |- logging_utils.py
   |- models.py
   |- reminders.py
   |- scrape.py
   |- scrape_job.py
   |- state.py
   |- summary.py
   |- telegram_client.py
   \- utils.py
```

## Limitaciones conocidas

- Si cambia el HTML del portal, se deben ajustar selectores en `ues_bot/scrape.py`.
- El estado actual usa JSON (no DB); roadmap para SQLite en `docs/PENDING_ROADMAP.md`.

## Documentacion complementaria

- Guia funcional de nuevas features: `docs/FEATURE_GUIDE.md`
- Pendientes + plan de implementacion futuro: `docs/PENDING_ROADMAP.md`
