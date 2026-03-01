# Pendientes y plan de implementacion

Este documento concentra lo que aun no se implementa y el plan recomendado para hacerlo.

## Resumen rapido

- Estado actual: fase critica + funcionalidades principales completadas.
- Pendiente principal: evolucion de arquitectura (SQLite), calidad estandarizada (mypy/ruff/CI), y features avanzadas (calificaciones, multiusuario, iCal).

## Priorizacion

### Prioridad alta

1. Migrar estado de JSON a SQLite.
2. Endurecer calidad continua con `ruff` + `mypy` en CI.
3. Definir release process para cambios de scraping/selectores.

### Prioridad media

4. Integracion de deteccion de calificaciones.
5. Mejorar exportacion iCal (suscripcion por URL y filtros por materia).

### Prioridad baja / estrategica

6. Multiusuario con credenciales cifradas.
7. Docker para despliegue estandarizado.

---

## Plan detallado de implementacion pendiente

## P1) Migracion a SQLite

Objetivo:

- Reemplazar backend JSON (`seen_events.json`) por persistencia transaccional.

Archivos previstos:

- `ues_bot/db.py` (nuevo)
- `ues_bot/state.py` (refactor a backend persistente)
- `ues_bot/scrape_job.py` (lectura/escritura de eventos via DB)
- `main.py` (bootstrapping de DB)

Pasos sugeridos:

1. Agregar dependencia `aiosqlite`.
2. Crear schema inicial (`events`, `bot_state`, `reminders_sent`, `metrics`).
3. Implementar capa de acceso con funciones equivalentes a `load_state/save_state`.
4. Crear migrador de JSON -> SQLite para adopcion sin perdida.
5. Agregar pruebas de migracion, lectura y escritura concurrente.

Riesgos:

- Migracion incompleta de estado historico.

Mitigacion:

- Backup automatico del JSON previo y test de roundtrip.

---

## P2) Estandar de calidad con CI (ruff + mypy)

Objetivo:

- Garantizar consistencia de codigo y tipado en cada cambio.

Archivos previstos:

- `pyproject.toml` o `ruff.toml`
- `mypy.ini`
- `.github/workflows/ci.yml` (nuevo)

Pasos sugeridos:

1. Configurar `ruff` (lint + import order + quality rules).
2. Configurar `mypy` con baseline gradual (no bloquear todo de golpe).
3. Crear workflow CI para `pytest`, `ruff`, `mypy`.
4. Elevar severidad por etapas hasta modo estricto.

Riesgos:

- Ruptura inicial por deudas de tipado existentes.

Mitigacion:

- Activacion gradual por modulos.

---

## P3) Deteccion de calificaciones

Objetivo:

- Avisar cuando aparezca o cambie una calificacion.

Archivos previstos:

- `ues_bot/grades.py` (nuevo)
- `ues_bot/scrape_job.py` (integracion de ciclo)
- `ues_bot/commands.py` (comando `/calificaciones`)
- `ues_bot/state.py` (tracking de cambios de nota)

Pasos sugeridos:

1. Mapear pagina de grades en UES/Moodle.
2. Parsear tabla de calificaciones y normalizar datos.
3. Comparar contra snapshot previo y detectar cambios.
4. Notificar cambios relevantes al chat.
5. Agregar comando de consulta manual.

---

## P4) iCal avanzado (mejora sobre lo ya implementado)

Objetivo:

- Extender la exportacion `.ics` actual para soporte de suscripcion y filtros.

Archivos previstos:

- `ues_bot/ical.py` (nuevo)
- `ues_bot/commands.py` (comando `/exportar`)

Pasos sugeridos:

1. Publicar feed `.ics` por URL para suscripcion continua.
2. Agregar filtros por materia/estado.
3. Mantener opcion manual actual via Telegram.

---

## P5) Multiusuario con cifrado de credenciales

Objetivo:

- Soportar varios usuarios/chat IDs con aislamiento de estado.

Prerequisito:

- SQLite implementado.

Archivos previstos:

- `ues_bot/users.py` (nuevo)
- `ues_bot/commands.py` (`/register`, `/unlink`)
- `ues_bot/scrape_job.py` (ejecucion por usuario)

Pasos sugeridos:

1. Modelo `users` con `chat_id`, `ues_user`, credenciales cifradas.
2. Cifrado con `cryptography` (Fernet/KMS local).
3. Ciclo de scraping por usuario con lock aislado.
4. Politicas anti abuso por usuario.

---

## P6) Docker para despliegue reproducible

Objetivo:

- Estandarizar ejecucion en entornos nuevos.

Archivos previstos:

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

Pasos sugeridos:

1. Imagen Python slim + dependencias para Chromium.
2. Instalacion Playwright y navegador en build.
3. Variables via `.env` y volumenes para estado/logs.

---

## Orden de ejecucion recomendado (futuro)

1. P1 SQLite
2. P2 CI quality gates
3. P3 Calificaciones
4. P4 iCal
5. P5 Multiusuario
6. P6 Docker

## Criterio de listo para cada pendiente

- Tiene pruebas automatizadas dedicadas.
- No rompe `pytest tests/ -q`.
- Tiene documentacion de uso en `README.md` y/o `docs/FEATURE_GUIDE.md`.
- Tiene entrada en `CHANGELOG.md`.
