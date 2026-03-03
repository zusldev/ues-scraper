# Changelog

## Unreleased

### Added
- **Sistema de notificaciones inteligente** con 3 modos: `smart` (default), `silent`, `all`.
- **Digest matutino automático** a las 07:00 con saludo, barra de progreso y tips.
- **Preview vespertino automático** a las 20:00: muestra entregas de mañana.
- Comando `/notificar [smart|silent|all]` para cambiar modo de notificación en caliente.
- Comando `/digestpm [HH:MM|off]` para configurar hora del preview vespertino.
- Comando `/preview` para preview nocturno bajo demanda.
- Comando `/proxima` para ver la próxima entrega pendiente con detalles completos.
- Comando `/materia [nombre]` para filtrar eventos por materia (sin args lista todas).
- Comando `/detalle <n|texto>` para mostrar todos los campos de un evento.
- Comando `/digest` para resumen del día (vencidas, hoy, mañana).
- Comando `/materiastats` para estadísticas por materia (enviadas, pendientes, vencidas).
- Detección de calificaciones: extrae "Estatus de calificación" de cada assignment.
- Campo `grading_status` en modelo `Event` y `grading_badge()` en summary.
- Alarmas VALARM (24h, 6h, 1h) en exportación `.ics` para notificaciones iPhone.
- Parser `parse_grading_status()` en scrape.py.
- Funciones `build_daily_digest()`, `build_evening_preview()`, `build_course_stats()` en summary.
- Barra de progreso `_progress_bar()` en mensajes digest.
- Saludos aleatorios y tips en digest matutino/vespertino.
- Persistencia de `notification_mode` y `digest_evening_hour` en state.json.
- Variables de entorno: `UES_DIGEST_HOUR`, `UES_DIGEST_EVENING_HOUR`, `UES_NOTIFICATION_MODE`.
- CLI args: `--digest-evening`, `--notification-mode`.
- Tests: 87 pruebas (+9 nuevas para evening preview, progress bar, state persistence).

### Changed
- **Scrape periódico ya NO envía resumen completo cada hora** (modo `smart` por default).
- En modo `smart`: solo envía mensajes cuando hay cambios reales o recordatorios.
- En modo `silent`: solo envía recordatorios urgentes (≤1h).
- En modo `all`: comportamiento legacy (resumen completo cada ciclo).
- Al despertar del modo dormido, ahora envía un digest completo en lugar de solo "Bot activo".
- Mensaje de cambios mejorado: "📬 Novedad detectada" (singular) / "📬 Novedades detectadas" (plural).
- Recordatorios ahora incluyen link directo al assignment.
- `/config` reorganizado con secciones: Notificaciones, Scraping, Display, Sistema.
- `/help` reorganizado con categorías: Consultas, Exportar, Notificaciones, Configuración.
- `status_badge(False)` ahora retorna 📝 (pendiente) y `status_badge(None)` retorna ⚠️ (verificación).
- Parser de estado de entrega endurecido con normalización de texto y fallback global para evitar falsos `None`.

### Testing
- Suite reorganizada en `tests/` y expandida a 87 pruebas.

## v1.3.0 — Notificaciones inteligentes + UX digest + scraping robusto

### Added
- Modos de notificación `smart/silent/all`.
- Digest matutino automático y preview vespertino automático (20:00 default).
- Comandos `/notificar`, `/digestpm`, `/preview`.
- Heurísticas robustas de estado de entrega para Moodle real (acentos/encoding).

### Changed
- Scrape periódico en modo `smart` ya no spamea resumen completo cada hora.
- `/pendientes` ahora incluye tareas sin enviar **y** tareas por verificar (`submitted is not True`).

### Notes
- Release generado desde la rama `master` con cobertura completa de tests.
