# Changelog

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
