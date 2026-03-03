# Guia de funcionalidades

Esta guia explica como usar las funcionalidades nuevas y que esperar de cada una.

## 1) Recordatorios escalonados (24h, 6h, 1h)

- Aplica solo a actividades pendientes (`submitted != True`) con fecha detectable.
- El bot envia recordatorios automaticos cuando se cruza cada umbral.
- Cada umbral se envia una sola vez por evento para evitar spam.
- Se guardan en estado persistente (`sent_reminders`) para sobrevivir reinicios.

Comportamiento esperado:

- Si un evento esta a 23h: envia recordatorio `24h`.
- Si luego baja a 5h: envia recordatorio `6h`.
- Si luego baja a 40m: envia recordatorio `1h`.

## 2) Comando `/calendario`

- Fuerza un scraping inmediato.
- Muestra eventos de los proximos 7 dias agrupados por dia.
- Incluye badge de estado, titulo corto, materia y tiempo restante.

Ejemplo:

```text
/calendario
```

## 3) Comando `/iphonecal` (exportar a iPhone Calendar)

- Fuerza un scraping inmediato.
- Genera un archivo `.ics` con pendientes de los proximos 30 dias.
- Excluye actividades marcadas como enviadas.
- Envia el archivo por Telegram para importarlo en iPhone.

Uso:

```text
/iphonecal
```

Como importarlo en iPhone:

1. Abre el archivo `.ics` recibido en Telegram.
2. Toca compartir/abrir con Calendario (o "Agregar a Calendario").
3. Confirma el calendario destino.

Resultado:

- Cada entrega se agrega como evento de 30 minutos terminando en la hora limite.
- Incluye materia, estado y link en la descripcion.

## 4) Comando `/config`

- Muestra configuracion activa en runtime.
- Sirve para validar rapidamente timezone, quiet hours, intervalo, limites y flags.

Ejemplo:

```text
/config
```

## 5) Comando `/stats`

- Muestra metricas operativas de scraping:
  - scrapes totales
  - exitosos / fallidos
  - tiempo del ultimo scrape
  - tiempo promedio
  - eventos detectados en ultimo ciclo

Ejemplo:

```text
/stats
```

## 6) Cooldown en comandos de scraping

- Comandos afectados: `/resumen`, `/urgente`, `/pendientes`, `/calendario`, `/iphonecal`.
- Cooldown global: 60s.
- Si se dispara otro comando dentro del cooldown, el bot responde con segundos restantes.

Objetivo:

- Evitar saturacion de portal, duplicidad de requests y spam de mensajes.

## 7) Alertas por errores consecutivos

- Si fallan 3 scrapes periodicos seguidos, el bot envia alerta al chat.
- El contador se reinicia automaticamente en el siguiente scrape exitoso.
- Se conserva en estado (`consecutive_errors`).

## 8) Rotacion de logs

- El log principal rota automaticamente para evitar crecimiento ilimitado.
- Configuracion actual:
  - max size: 5 MB
  - backups: 3 archivos

## 9) Retry automatico (`tenacity`)

- Navegacion Playwright (`safe_goto`) con retries y backoff exponencial.
- Envio Telegram (`tg_send`) con retries y backoff exponencial.
- Reduce fallos transitorios por red inestable o latencia del portal.

## 10) Shutdown con persistencia

- Al apagar el proceso del bot, se persiste el estado.
- Evita perdida de informacion de operacion (sleep, errores, recordatorios, metricas).

## 11) Pruebas

La suite cubre:

- comandos
- utilidades
- estado
- resumen
- parseo scraping
- logging
- retries
- errores
- recordatorios
- calendario
- ical
- grading status
- daily digest
- course stats

Ejecucion:

```bash
pytest tests/ -q
```

## 12) Detección de calificaciones

- Al visitar la página de cada asignación, el bot extrae el "Estatus de calificación" (e.g. "No calificado", "Calificado").
- Se almacena en `event.grading_status` y se muestra con badge 📝 (calificado) o ⏳ (pendiente).
- Aparece en `/resumen`, `/detalle`, `/proxima` y en las notificaciones de cambios.

## 13) Comando `/proxima`

- Muestra la **próxima entrega pendiente** (no enviada, no vencida) con todos los detalles.
- Incluye: título, materia, tiempo restante, fecha, calificación, descripción y link.

Ejemplo:

```text
/proxima
```

## 14) Comando `/materia [nombre]`

- Sin argumentos: lista todas las materias detectadas con conteo de tareas.
- Con argumento: filtra eventos que coincidan (búsqueda parcial, case-insensitive).

Ejemplo:

```text
/materia            → lista materias
/materia Redes      → eventos de "IS N Redes de Computo 001"
/materia audit      → eventos de "IS N Auditoria en Informatica 001"
```

## 15) Comando `/detalle <n|texto>`

- Muestra todos los campos de un evento específico.
- Acepta número de índice (del listado de /resumen) o búsqueda por texto.
- Incluye: título, materia, estado, calificación, tiempo restante, fecha, descripción y link.

Ejemplo:

```text
/detalle 1              → primer evento de la lista
/detalle Resumen OSI    → busca por título
```

## 16) Comando `/digest` y digest diario automático

- `/digest`: genera un resumen del día bajo demanda (vencidas, hoy, mañana).
- El bot envía automáticamente un digest matutino a la hora configurada (`digest_hour`, default 07:00).
- Respeta quiet hours y modo dormido.

Configuración:

```text
--digest-hour 07:00    # hora local del digest automático
```

## 17) Comando `/materiastats`

- Muestra estadísticas por materia: tareas enviadas ✅, pendientes 📝, vencidas 🔴 y total 📋.
- Útil para saber el progreso general por curso.

Ejemplo:

```text
/materiastats
```

## 18) Alarmas VALARM en exportación iCal

- Los archivos `.ics` generados con `/iphonecal` ahora incluyen 3 alarmas por evento:
  - 24 horas antes
  - 6 horas antes
  - 1 hora antes
- iPhone Calendar mostrará notificaciones automáticas sin configuración adicional.

## 19) Badges mejorados

- ✅ Enviado
- 📝 Pendiente (sin enviar)
- ⚠️ Por verificar (si Moodle no devolvió estado concluyente)
- 📝 Calificado
- ⏳ Pendiente de calificar

## 20) Sistema de notificaciones inteligente

El bot ahora tiene 3 modos de notificación que cambian cómo se comporta el scrape periódico (cada hora):

### Modo `smart` (default)
- **Solo envía mensaje cuando hay cambios reales** (tareas nuevas, fechas modificadas).
- Recordatorios a 24h, 6h, 1h.
- Digest matutino a las 07:00.
- Preview vespertino a las 20:00.
- **Ya no spamea resumen completo cada hora.**

### Modo `silent`
- Solo envía recordatorios urgentes (≤1h antes de fecha límite).
- Digest matutino y vespertino siguen funcionando.
- Ideal para épocas de exámenes donde quieres mínima distracción.

### Modo `all` (legacy)
- Comportamiento anterior: resumen completo cada ciclo.
- Todos los recordatorios.
- Digests a sus horas.

### Cambiar modo:
```text
/notificar           → ver modo actual y opciones
/notificar smart     → activar smart
/notificar silent    → activar silent
/notificar all       → activar all
```

## 21) Preview vespertino automático

- Se ejecuta a las 20:00 por default (configurable).
- Muestra qué entregas tienes **para mañana** y si hay vencidas pendientes.
- Si no hay entregas mañana, muestra "✨ ¡Mañana libre!".
- Incluye tips motivacionales.

### Configurar hora o desactivar:
```text
/digestpm           → ver hora actual
/digestpm 21:00     → cambiar a las 21:00
/digestpm off       → desactivar
```

### Bajo demanda:
```text
/preview            → ver preview nocturno ahora
```

## 22) Digest matutino mejorado

El digest de las 07:00 ahora incluye:
- Saludo aleatorio ("Buenos días ☀️", "¡A darle! 💪", etc.)
- Fecha del día
- **Barra de progreso general**: `████░░░░░░ 4/10`
- Secciones: vencidas, para hoy, mañana
- Hora de entrega junto a cada tarea
- Tip aleatorio al final

## 23) Comando `/preview`

- Preview nocturno bajo demanda (mismo formato que el automático de las 20:00).
- Muestra entregas de mañana y vencidas pendientes.

```text
/preview
```

## 24) Persistencia de configuración

Los siguientes ajustes sobreviven reinicios del bot:
- Modo de notificación (`/notificar`)
- Hora del preview vespertino (`/digestpm`)
- Quiet hours (`/silencio`)
- Estado de sueño (`/dormir`)
- Recordatorios ya enviados
- Métricas de scraping
