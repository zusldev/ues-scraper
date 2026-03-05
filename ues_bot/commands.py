"""Telegram command handlers for runtime control and on-demand scraping."""

from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Coroutine

try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .ical import build_ics_filename, build_iphone_calendar_ics
from .scrape_job import run_scrape_cycle
from .state import (
    cancel_sleep,
    is_sleeping,
    load_state,
    save_state,
    set_sleep,
    update_digest_evening_hour,
    update_notification_mode,
    update_quiet_hours,
)
from .summary import (
    build_course_stats,
    build_daily_digest,
    build_evening_preview,
    build_sectioned_summary,
    build_weekly_calendar,
    due_unix,
    grading_badge,
    remaining_parts_from_unix,
    status_badge,
    urgency_bucket,
)
from .telegram_client import tg_send, tg_send_document
from .utils import chunk_messages, esc, parse_hhmm, short

SCRAPE_JOB_NAME = "scrape_cycle"
SCRAPE_JOB_CALLBACK_KEY = "scrape_job_callback"
SCRAPE_LOCK_KEY = "scrape_lock"
SCRAPE_COMMAND_COOLDOWN = 60
LAST_SCRAPE_TS_KEY = "last_scrape_command_ts"


CommandFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]


class ScrapeAlreadyRunningError(RuntimeError):
    """Raised when a scrape is already running and lock acquisition times out."""


def _restricted(func: CommandFn) -> CommandFn:
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        settings = context.application.bot_data["settings"]
        chat = update.effective_chat
        if chat is None:
            return
        try:
            allowed_chat = int(settings.tg_chat_id)
        except Exception:
            logging.error("TG_CHAT_ID inválido o no configurado.")
            return
        if chat.id != allowed_chat:
            logging.warning("Intento de comando no autorizado desde chat %s", chat.id)
            return
        await func(update, context)

    return wrapper


async def _reply(update: Update, text: str, **kwargs) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(text, **kwargs)


def _fmt_ts(ts: int | None, tz_name: str) -> str:
    if not ts:
        return "-"
    if ZoneInfo is not None:
        dt = datetime.fromtimestamp(ts, ZoneInfo(tz_name))
    else:
        dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


async def run_scrape_now(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    wait_for_lock_sec: float | None = None,
):
    settings = context.application.bot_data["settings"]
    run_args = context.application.bot_data.get("run_scrape_args", {})
    if wait_for_lock_sec is None:
        wait_for_lock_sec = max(0.0, float(getattr(settings, "scrape_lock_wait_sec", 0)))

    lock = context.application.bot_data.get(SCRAPE_LOCK_KEY)
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        context.application.bot_data[SCRAPE_LOCK_KEY] = lock

    if wait_for_lock_sec <= 0:
        # timeout=0 with wait_for can raise immediately even when the lock is free.
        if lock.locked():
            raise ScrapeAlreadyRunningError("Ya hay un scraping en curso. Intenta de nuevo en unos segundos.")
        await lock.acquire()
    else:
        try:
            await asyncio.wait_for(lock.acquire(), timeout=wait_for_lock_sec)
        except TimeoutError as ex:
            raise ScrapeAlreadyRunningError("Ya hay un scraping en curso. Intenta de nuevo en unos segundos.") from ex

    try:
        return await asyncio.to_thread(run_scrape_cycle, settings, run_args)
    finally:
        lock.release()


def _reschedule_interval_job(app: Application, minutes: int) -> None:
    callback = app.bot_data.get(SCRAPE_JOB_CALLBACK_KEY)
    if callback is None:
        raise RuntimeError("No hay callback de scraping registrada.")
    job_queue = app.job_queue
    if job_queue is None:
        raise RuntimeError("JobQueue no disponible.")
    for job in job_queue.get_jobs_by_name(SCRAPE_JOB_NAME):
        job.schedule_removal()
    job_queue.run_repeating(callback, interval=minutes * 60, first=0, name=SCRAPE_JOB_NAME)


def _build_brief_event_lines(events: list, max_lines: int = 20) -> str:
    if not events:
        return "Sin resultados."
    sorted_events = sorted(events, key=lambda e: due_unix(e) or 10**18)
    lines = []
    for event in sorted_events[:max_lines]:
        due = due_unix(event)
        if due:
            _, rem = remaining_parts_from_unix(due)
        else:
            rem = event.due_text.strip() or "N/D"
        lines.append(
            f"{status_badge(event.submitted)} {esc(short(event.title, 65))} — "
            f"<i>{esc(short(event.course_name, 36))}</i> — <b>{esc(rem)}</b>"
        )
    if len(sorted_events) > max_lines:
        lines.append(f"… (+{len(sorted_events) - max_lines} más)")
    return "\n".join(lines)


def _check_cooldown(bot_data: dict) -> tuple[bool, int]:
    elapsed = _time.time() - bot_data.get(LAST_SCRAPE_TS_KEY, 0.0)
    if elapsed < SCRAPE_COMMAND_COOLDOWN:
        return False, int(SCRAPE_COMMAND_COOLDOWN - elapsed)
    return True, 0


def _mark_scrape_used(bot_data: dict) -> None:
    bot_data[LAST_SCRAPE_TS_KEY] = _time.time()


async def _scrape_or_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    cmd_name: str,
    status_msg: str = "Ejecutando scraping...",
) -> tuple[list, list] | None:
    """Shared cooldown + scrape logic for on-demand commands.

    Returns (events_all, events_changed) or None if it failed
    (error already replied to the user).
    """
    bot_data = context.application.bot_data
    can_run, wait_sec = _check_cooldown(bot_data)
    if not can_run:
        await _reply(update, f"⏳ Espera {wait_sec}s antes de ejecutar otro scrape.")
        return None
    _mark_scrape_used(bot_data)

    await _reply(update, status_msg)
    try:
        return await run_scrape_now(context)
    except Exception as ex:
        await _reply(update, f"No se pudo ejecutar /{cmd_name}: {ex}")
        return None


@_restricted
async def cmd_dormir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    hours = 8.0
    if context.args:
        try:
            hours = float(context.args[0])
        except ValueError:
            await _reply(update, "Uso: /dormir <horas> (ej. /dormir 4)")
            return
    state = load_state(settings.state_file)
    wake_ts = set_sleep(state, hours)
    save_state(settings.state_file, state)
    await _reply(
        update,
        f"💤 Dormido por {hours:g}h (hasta {_fmt_ts(wake_ts, settings.tz_name)}). Usa /despertar para cancelar."
    )


@_restricted
async def cmd_despertar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)
    cancel_sleep(state)
    save_state(settings.state_file, state)
    await _reply(update, "☀️ Modo dormido cancelado. Bot activo.")


@_restricted
async def cmd_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "resumen", "Ejecutando scraping y preparando resumen...")
    if result is None:
        return
    events_all, _ = result
    summary = build_sectioned_summary(
        events_all,
        tz_name=settings.tz_name,
        urgent_hours=settings.urgent_hours,
        max_lines_total=settings.max_summary_lines,
    )
    for part in chunk_messages(summary):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_urgente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "urgente", "Buscando urgentes/vencidos no entregados...")
    if result is None:
        return
    events_all, _ = result
    urgent_items = [
        event
        for event in events_all
        if event.submitted is False and urgency_bucket(event, urgent_hours=settings.urgent_hours) in {"urgente", "vencidos"}
    ]
    body = _build_brief_event_lines(urgent_items, max_lines=settings.max_summary_lines)
    text = f"🚨 <b>Urgentes/Vencidos no entregados</b>\n{body}"
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "pendientes", "Buscando pendientes (sin enviar o por verificar)...")
    if result is None:
        return
    events_all, _ = result
    # Treat unknown status (None) as pending so users don't miss tasks when Moodle status detection fails.
    pending_items = [event for event in events_all if event.submitted is not True]
    body = _build_brief_event_lines(pending_items, max_lines=settings.max_summary_lines)
    text = f"📝 <b>Pendientes (sin enviar / por verificar)</b>\n{body}"
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_calendario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "calendario", "Preparando calendario semanal...")
    if result is None:
        return
    events_all, _ = result
    calendar = build_weekly_calendar(events_all, tz_name=settings.tz_name)
    for part in chunk_messages(calendar):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_iphonecal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "iphonecal", "Generando archivo .ics para iPhone Calendar...")
    if result is None:
        return
    events_all, _ = result

    ics_data, count = build_iphone_calendar_ics(events_all, tz_name=settings.tz_name, days_ahead=30)
    if count == 0:
        await _reply(update, "No hay pendientes con fecha en los próximos 30 días para exportar.")
        return

    filename = build_ics_filename(settings.tz_name)
    caption = (
        f"📎 <b>Calendario iPhone listo</b>\n"
        f"Eventos exportados: <b>{count}</b>\n"
        "Abre el archivo y elige <i>Agregar a Calendario</i>."
    )
    await tg_send_document(
        ics_data,
        filename,
        settings.tg_bot_token,
        settings.tg_chat_id,
        caption=caption,
        dry_run=settings.dry_run,
        bot=context.bot,
    )


@_restricted
async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)
    sleeping = is_sleeping(state)
    sleep_txt = _fmt_ts(state.get("sleep_until"), settings.tz_name) if sleeping else "No"
    tracked = len(state.get("events", {}))
    last_run = _fmt_ts(state.get("last_run"), settings.tz_name)
    last_error = state.get("last_error") or "-"
    last_error_kind = state.get("last_error_kind") or "-"
    text = (
        "🤖 <b>Estado del bot</b>\n"
        f"• Dormido hasta: <b>{esc(sleep_txt)}</b>\n"
        f"• Quiet hours: <b>{esc(settings.quiet_start)} - {esc(settings.quiet_end)}</b>\n"
        f"• Intervalo: <b>{settings.scrape_interval_min} min</b>\n"
        f"• Eventos trackeados: <b>{tracked}</b>\n"
        f"• Última ejecución: <b>{esc(last_run)}</b>\n"
        f"• Último error: <b>{esc(short(str(last_error), 120))}</b>\n"
        f"• Tipo último error: <b>{esc(str(last_error_kind))}</b>"
    )
    await _reply(update, text, parse_mode="HTML", disable_web_page_preview=True)
    save_state(settings.state_file, state)


@_restricted
async def cmd_silencio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    args = context.args or []
    if len(args) != 2:
        await _reply(update, "Uso: /silencio <HH:MM> <HH:MM> (ej. /silencio 22:00 07:00)")
        return
    start = args[0]
    end = args[1]
    try:
        parse_hhmm(start)
        parse_hhmm(end)
    except ValueError as ex:
        await _reply(update, str(ex))
        return
    settings.quiet_start = start
    settings.quiet_end = end
    state = load_state(settings.state_file)
    update_quiet_hours(state, start, end)
    save_state(settings.state_file, state)
    await _reply(update, f"🔕 Quiet hours actualizadas: {start} - {end}")


@_restricted
async def cmd_intervalo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    args = context.args or []
    if len(args) != 1:
        await _reply(update, "Uso: /intervalo <minutos> (ej. /intervalo 60)")
        return
    try:
        minutes = int(args[0])
    except ValueError:
        await _reply(update, "El intervalo debe ser un número entero de minutos.")
        return
    if minutes < 1 or minutes > 24 * 60:
        await _reply(update, "Rango válido: 1 a 1440 minutos.")
        return

    settings.scrape_interval_min = minutes
    try:
        _reschedule_interval_job(context.application, minutes)
    except Exception as ex:
        await _reply(update, f"No se pudo actualizar el intervalo: {ex}")
        return
    await _reply(update, f"⏱️ Intervalo actualizado a {minutes} minutos.")


@_restricted
async def cmd_notificar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change notification mode: smart, silent, all."""
    settings = context.application.bot_data["settings"]
    args = context.args or []

    if not args:
        current = getattr(settings, "notification_mode", "smart")
        modes_desc = {
            "smart": "📱 <b>smart</b> — Solo cambios + recordatorios. Digests a sus horas.",
            "silent": "🔇 <b>silent</b> — Solo recordatorios urgentes (≤1h). Digests a sus horas.",
            "all": "📢 <b>all</b> — Resumen completo cada ciclo (puede ser ruidoso).",
        }
        lines = [
            "🔔 <b>Modo de notificación</b>",
            f"\nActual: <b>{esc(current)}</b>",
            "\nModos disponibles:",
        ]
        for mode, desc in modes_desc.items():
            marker = " ← actual" if mode == current else ""
            lines.append(f"  {desc}{marker}")
        lines.append("\nUso: /notificar smart|silent|all")
        await _reply(update, "\n".join(lines), parse_mode="HTML")
        return

    mode = args[0].lower()
    if mode not in ("smart", "silent", "all"):
        await _reply(update, "Modo inválido. Usa: /notificar smart|silent|all")
        return

    settings.notification_mode = mode
    state = load_state(settings.state_file)
    update_notification_mode(state, mode)
    save_state(settings.state_file, state)

    descriptions = {
        "smart": "📱 Modo <b>smart</b> activado.\n\nRecibirás:\n• Novedades cuando se detecten\n• Recordatorios a 24h, 6h, 1h\n• Digest matutino y vespertino",
        "silent": "🔇 Modo <b>silent</b> activado.\n\nRecibirás:\n• Solo recordatorios urgentes (≤1h)\n• Digest matutino y vespertino",
        "all": "📢 Modo <b>all</b> activado.\n\nRecibirás:\n• Resumen completo cada ciclo\n• Todos los recordatorios\n• Digest matutino y vespertino",
    }
    await _reply(update, descriptions[mode], parse_mode="HTML")


@_restricted
async def cmd_digestpm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure evening digest time, or disable it."""
    settings = context.application.bot_data["settings"]
    args = context.args or []

    if not args:
        current = getattr(settings, "digest_evening_hour", "") or "desactivado"
        await _reply(
            update,
            f"🌙 Preview vespertino: <b>{esc(current)}</b>\n\n"
            "Uso:\n"
            "  /digestpm 20:00  — Activar a las 20:00\n"
            "  /digestpm off    — Desactivar",
            parse_mode="HTML",
        )
        return

    value = args[0].strip().lower()
    if value in ("off", "desactivar", "0", "no"):
        settings.digest_evening_hour = ""
        state = load_state(settings.state_file)
        update_digest_evening_hour(state, "")
        save_state(settings.state_file, state)
        # Remove scheduled job
        jq = context.application.job_queue
        if jq:
            for job in jq.get_jobs_by_name("evening_preview"):
                job.schedule_removal()
        await _reply(update, "🌙 Preview vespertino <b>desactivado</b>.", parse_mode="HTML")
        return

    try:
        parse_hhmm(value)
    except ValueError as ex:
        await _reply(update, str(ex))
        return

    settings.digest_evening_hour = value
    state = load_state(settings.state_file)
    update_digest_evening_hour(state, value)
    save_state(settings.state_file, state)

    # Reschedule job
    jq = context.application.job_queue
    if jq:
        for job in jq.get_jobs_by_name("evening_preview"):
            job.schedule_removal()
        from main import evening_preview_job, _schedule_daily_job
        _schedule_daily_job(jq, evening_preview_job, value, settings.tz_name, "evening_preview")

    await _reply(update, f"🌙 Preview vespertino actualizado a <b>{esc(value)}</b>.", parse_mode="HTML")


_NOTIFICATION_MODE_LABELS = {"smart": "📱 smart", "silent": "🔇 silent", "all": "📢 all"}


@_restricted
async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    mode = getattr(settings, "notification_mode", "smart")
    mode_label = _NOTIFICATION_MODE_LABELS.get(mode, mode)
    evening = getattr(settings, "digest_evening_hour", "") or "off"
    text = (
        "⚙️ <b>Configuración actual</b>\n\n"
        f"<b>🔔 Notificaciones</b>\n"
        f"  Modo: <b>{esc(mode_label)}</b>\n"
        f"  Digest matutino: <b>{esc(settings.digest_hour)}</b>\n"
        f"  Preview vespertino: <b>{esc(evening)}</b>\n"
        f"  Quiet hours: <b>{esc(settings.quiet_start)} - {esc(settings.quiet_end)}</b>\n\n"
        f"<b>⚡ Scraping</b>\n"
        f"  Intervalo: <b>{settings.scrape_interval_min} min</b>\n"
        f"  Urgencia: <b>{settings.urgent_hours}h</b>\n\n"
        f"<b>📋 Display</b>\n"
        f"  Máx cambios: <b>{settings.max_change_items}</b>\n"
        f"  Máx resumen: <b>{settings.max_summary_lines}</b>\n\n"
        f"<b>🛠️ Sistema</b>\n"
        f"  Timezone: <b>{esc(settings.tz_name)}</b>\n"
        f"  Headful: <b>{'Sí' if settings.headful else 'No'}</b>\n"
        f"  Dry-run: <b>{'Sí' if settings.dry_run else 'No'}</b>"
    )
    await _reply(update, text, parse_mode="HTML", disable_web_page_preview=True)


@_restricted
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)
    metrics = state.get("metrics", {})
    text = (
        "📊 <b>Estadísticas del bot</b>\n"
        f"• Scrapes totales: <b>{metrics.get('total_scrapes', 0)}</b>\n"
        f"• Exitosos: <b>{metrics.get('successful_scrapes', 0)}</b>\n"
        f"• Fallidos: <b>{metrics.get('failed_scrapes', 0)}</b>\n"
        f"• Errores red transitorios: <b>{metrics.get('network_transient_errors', 0)}</b>\n"
        f"• Errores funcionales: <b>{metrics.get('functional_errors', 0)}</b>\n"
        f"• Último scrape: <b>{metrics.get('last_scrape_seconds', 0)}s</b>\n"
        f"• Promedio: <b>{metrics.get('avg_scrape_seconds', 0)}s</b>\n"
        f"• Eventos último ciclo: <b>{metrics.get('last_event_count', 0)}</b>"
    )
    await _reply(update, text, parse_mode="HTML", disable_web_page_preview=True)


@_restricted
async def cmd_proxima(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the next upcoming unsubmitted deadline with full details."""
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "proxima", "Buscando próxima entrega...")
    if result is None:
        return
    events_all, _ = result

    pending = [e for e in events_all if e.submitted is not True and due_unix(e) is not None]
    pending.sort(key=lambda e: due_unix(e) or 10**18)

    # Filter to only future events
    from datetime import datetime as _dt, timezone as _tz
    now_ts = int(_dt.now(_tz.utc).timestamp())
    pending = [e for e in pending if (due_unix(e) or 0) > now_ts]

    if not pending:
        await tg_send(
            "🎉 <b>¡Sin entregas pendientes!</b>\nNo tienes tareas próximas sin entregar.",
            settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot,
        )
        return

    e = pending[0]
    du = due_unix(e)
    _, rem = remaining_parts_from_unix(du) if du else (0, "N/D")
    g_badge = grading_badge(e.grading_status)
    link = e.assignment_url or e.url

    text = (
        f"⏰ <b>Próxima entrega</b>\n\n"
        f"{status_badge(e.submitted)} <b>{esc(e.title)}</b>\n"
        f"📚 {esc(e.course_name)}\n"
        f"⏳ Tiempo restante: <b>{esc(rem)}</b>\n"
        f"📅 {esc(e.due_text)}\n"
    )
    if e.grading_status:
        text += f"📝 Calificación: {esc(e.grading_status)} {g_badge}\n"
    if e.description:
        text += f"\n📋 {esc(short(e.description, 300))}\n"
    text += f"\n🔗 {esc(link)}"

    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_materia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Filter events by course name. No args = list all courses."""
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "materia", "Buscando eventos por materia...")
    if result is None:
        return
    events_all, _ = result

    query = " ".join(context.args).strip().lower() if context.args else ""

    if not query:
        # List all unique course names
        courses = sorted({e.course_name for e in events_all if e.course_name and e.course_name != "Sin materia"})
        if not courses:
            await _reply(update, "No se detectaron materias.")
            return
        lines = ["📚 <b>Materias detectadas</b>\nUsa: /materia <nombre parcial>\n"]
        for c in courses:
            count = sum(1 for e in events_all if e.course_name == c)
            submitted = sum(1 for e in events_all if e.course_name == c and e.submitted is True)
            lines.append(f"• <b>{esc(c)}</b> ({submitted}✅/{count}📋)")
        await _reply(update, "\n".join(lines), parse_mode="HTML")
        return

    matched = [e for e in events_all if query in (e.course_name or "").lower()]
    if not matched:
        await _reply(update, f"No encontré eventos para «{esc(query)}».")
        return

    body = _build_brief_event_lines(matched, max_lines=settings.max_summary_lines)
    course_display = matched[0].course_name if len({e.course_name for e in matched}) == 1 else query
    text = f"📚 <b>{esc(course_display)}</b> ({len(matched)} eventos)\n{body}"
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_detalle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show full details of a specific event by index or title search."""
    settings = context.application.bot_data["settings"]

    if not context.args:
        await _reply(update, "Uso: /detalle <número o texto>\nEjemplo: /detalle 1 ó /detalle Resumen OSI")
        return

    result = await _scrape_or_reply(update, context, "detalle", "Buscando detalles del evento...")
    if result is None:
        return
    events_all, _ = result

    sorted_events = sorted(events_all, key=lambda e: due_unix(e) or 10**18)
    # Store for index lookup
    context.application.bot_data["_last_event_list"] = sorted_events

    query = " ".join(context.args).strip()

    # Try numeric index first
    e = None
    try:
        idx = int(query)
        if 1 <= idx <= len(sorted_events):
            e = sorted_events[idx - 1]
    except ValueError:
        pass

    # Fallback: text search
    if e is None:
        q_lower = query.lower()
        for ev in sorted_events:
            if q_lower in ev.title.lower() or q_lower in ev.course_name.lower():
                e = ev
                break

    if e is None:
        await _reply(update, f"No encontré evento «{esc(query)}». Usa /resumen para ver la lista numerada.")
        return

    du = due_unix(e)
    _, rem = remaining_parts_from_unix(du) if du else (0, "N/D")
    g_badge = grading_badge(e.grading_status)
    link = e.assignment_url or e.url

    text = (
        f"🔍 <b>Detalle del evento</b>\n\n"
        f"<b>{esc(e.title)}</b>\n\n"
        f"📚 Materia: {esc(e.course_name)}\n"
        f"📌 Estado: {status_badge(e.submitted)} {esc(e.submission_status or 'Desconocido')}\n"
        f"⏳ Restante: <b>{esc(rem)}</b>\n"
        f"📅 Fecha: {esc(e.due_text)}\n"
    )
    if e.grading_status:
        text += f"📝 Calificación: {esc(e.grading_status)} {g_badge}\n"
    if e.description:
        text += f"\n📋 <b>Descripción:</b>\n{esc(short(e.description, 500))}\n"
    text += f"\n🔗 {esc(link)}"

    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_materiastats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show per-course statistics."""
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "materiastats", "Calculando estadísticas por materia...")
    if result is None:
        return
    events_all, _ = result
    text = build_course_stats(events_all)
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show daily digest: overdue, due today, due tomorrow."""
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "digest", "Preparando resumen del día...")
    if result is None:
        return
    events_all, _ = result
    text = build_daily_digest(events_all, tz_name=settings.tz_name, urgent_hours=settings.urgent_hours)
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show evening preview: what's due tomorrow."""
    settings = context.application.bot_data["settings"]
    result = await _scrape_or_reply(update, context, "preview", "Preparando preview nocturno...")
    if result is None:
        return
    events_all, _ = result
    text = build_evening_preview(events_all, tz_name=settings.tz_name)
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 <b>Comandos disponibles</b>\n\n"

        "<b>📋 Consultas</b>\n"
        "/resumen — Resumen completo por urgencia\n"
        "/digest — Resumen del día (vencidas, hoy, mañana)\n"
        "/preview — Preview nocturno (¿qué hay mañana?)\n"
        "/proxima — Próxima entrega pendiente\n"
        "/urgente — Urgentes y vencidos no entregados\n"
        "/pendientes — Todas las tareas sin enviar\n"
        "/materia [nombre] — Filtrar por materia\n"
        "/detalle &lt;n|texto&gt; — Detalles de un evento\n"
        "/calendario — Vista semanal\n"
        "/materiastats — Estadísticas por materia\n\n"

        "<b>📤 Exportar</b>\n"
        "/iphonecal — Exportar .ics para iPhone Calendar\n\n"

        "<b>🔔 Notificaciones</b>\n"
        "/notificar [smart|silent|all] — Modo de notificación\n"
        "/digestpm [HH:MM|off] — Hora del preview vespertino\n"
        "/dormir [horas] — Silencia por X horas (default 8)\n"
        "/despertar — Cancela modo dormido\n"
        "/silencio HH:MM HH:MM — Quiet hours\n\n"

        "<b>⚙️ Configuración</b>\n"
        "/intervalo &lt;min&gt; — Frecuencia de scraping\n"
        "/config — Ver configuración actual\n"
        "/estado — Estado operativo del bot\n"
        "/stats — Métricas de scraping\n"
        "/help — Esta ayuda"
    )
    await _reply(update, text, parse_mode="HTML")


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("dormir", cmd_dormir))
    application.add_handler(CommandHandler("despertar", cmd_despertar))
    application.add_handler(CommandHandler("resumen", cmd_resumen))
    application.add_handler(CommandHandler("urgente", cmd_urgente))
    application.add_handler(CommandHandler("pendientes", cmd_pendientes))
    application.add_handler(CommandHandler("proxima", cmd_proxima))
    application.add_handler(CommandHandler("materia", cmd_materia))
    application.add_handler(CommandHandler("detalle", cmd_detalle))
    application.add_handler(CommandHandler("digest", cmd_digest))
    application.add_handler(CommandHandler("preview", cmd_preview))
    application.add_handler(CommandHandler("calendario", cmd_calendario))
    application.add_handler(CommandHandler("iphonecal", cmd_iphonecal))
    application.add_handler(CommandHandler("materiastats", cmd_materiastats))
    application.add_handler(CommandHandler("notificar", cmd_notificar))
    application.add_handler(CommandHandler("digestpm", cmd_digestpm))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CommandHandler("silencio", cmd_silencio))
    application.add_handler(CommandHandler("intervalo", cmd_intervalo))
    application.add_handler(CommandHandler("config", cmd_config))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("help", cmd_help))
