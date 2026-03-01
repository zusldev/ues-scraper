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

Ejecucion:

```bash
pytest tests/ -q
```
