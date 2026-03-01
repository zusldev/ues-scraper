# Changelog

## v1.2.0 — Bot interactivo de larga ejecución + hardening

### Added
- Bot de Telegram de larga ejecución con `python-telegram-bot` + `JobQueue` (`application.run_polling`).
- Comandos interactivos restringidos por `TG_CHAT_ID`: `/dormir`, `/despertar`, `/resumen`, `/urgente`, `/pendientes`, `/estado`, `/silencio`, `/intervalo`, `/help`.
- `run_scrape_cycle(settings, args_override)` en `ues_bot/scrape_job.py` para reutilizar scraping desde job periódico y comandos bajo demanda.
- Estado persistente ampliado: `sleep_until`, `quiet_start`, `quiet_end`, `last_run`, `last_error`.
- Soporte de intervalo en caliente con `scrape_interval_min` y comando `/intervalo`.
- Soporte de lock de scraping para evitar ejecuciones simultáneas (`scrape_lock_wait_sec`).
- Nuevas pruebas para handlers y control de concurrencia (`test_commands.py`).

### Changed
- `tg_send` ahora puede usar `Bot` de `python-telegram-bot` y mantiene compatibilidad con `dry_run`.
- `main.py` migrado de ejecución única tipo cron a proceso persistente con programación interna cada N minutos.
- `requirements.txt` actualizado para incluir `python-telegram-bot[job-queue]`.

### Notes
- Para producción, usar Task Scheduler solo para iniciar el proceso al arrancar sesión/sistema (no cada hora).

## 1.1.0 — Modular + Usabilidad (batch + quiet hours + resumen por secciones)

### Added
- **Quiet hours**: no envía mensajes entre `UES_QUIET_START` y `UES_QUIET_END` (por defecto 00:00–07:00).
- **Batch de cambios**: agrupa eventos nuevos/cambiados en un solo bloque (y se parte automáticamente si excede límite de Telegram).
- **Resumen por secciones**: agrupa por urgencia:
  - 🔥 Urgente (≤N horas)
  - 🕒 Vencidos (no enviados)
  - 📅 Próximos (≤7 días)
  - ✅ Enviados
  - ⌛ Sin fecha detectada
  - 🗓️ Futuro
- **Soporte .env** con `python-dotenv`.
- **Logs** a consola y archivo `ues_to_telegram.log`.
- **Retries de navegación** para páginas lentas/caídas (`safe_goto`).

### Changed
- Código separado en módulos (mejor mantenibilidad).

### Notes
- `--dry-run` simula envíos (ideal para depurar).
- Si tu Python es <3.9, `zoneinfo` puede no estar disponible (se usa hora local del sistema).
