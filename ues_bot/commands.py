"""Telegram command handlers for runtime control and on-demand scraping."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Coroutine

try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .scrape_job import run_scrape_cycle
from .state import (
    cancel_sleep,
    is_sleeping,
    load_state,
    save_state,
    set_sleep,
    update_quiet_hours,
)
from .summary import build_sectioned_summary, due_unix, remaining_parts_from_unix, status_badge, urgency_bucket
from .telegram_client import tg_send
from .utils import chunk_messages, esc, parse_hhmm, short

SCRAPE_JOB_NAME = "scrape_cycle"
SCRAPE_JOB_CALLBACK_KEY = "scrape_job_callback"
SCRAPE_LOCK_KEY = "scrape_lock"


CommandFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]


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

    if wait_for_lock_sec == 0 and lock.locked():
        raise RuntimeError("Ya hay un scraping en curso. Intenta de nuevo en unos segundos.")

    try:
        await asyncio.wait_for(lock.acquire(), timeout=wait_for_lock_sec)
    except TimeoutError as ex:
        raise RuntimeError("Ya hay un scraping en curso. Intenta de nuevo en unos segundos.") from ex

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
    await _reply(update, "Ejecutando scraping y preparando resumen...")
    try:
        events_all, _ = await run_scrape_now(context)
    except Exception as ex:
        await _reply(update, f"No se pudo ejecutar /resumen: {ex}")
        return
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
    await _reply(update, "Buscando urgentes/vencidos no entregados...")
    try:
        events_all, _ = await run_scrape_now(context)
    except Exception as ex:
        await _reply(update, f"No se pudo ejecutar /urgente: {ex}")
        return
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
    await _reply(update, "Buscando pendientes (submitted=False)...")
    try:
        events_all, _ = await run_scrape_now(context)
    except Exception as ex:
        await _reply(update, f"No se pudo ejecutar /pendientes: {ex}")
        return
    pending_items = [event for event in events_all if event.submitted is False]
    body = _build_brief_event_lines(pending_items, max_lines=settings.max_summary_lines)
    text = f"📝 <b>Pendientes (sin enviar)</b>\n{body}"
    for part in chunk_messages(text):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


@_restricted
async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)
    sleeping = is_sleeping(state)
    sleep_txt = _fmt_ts(state.get("sleep_until"), settings.tz_name) if sleeping else "No"
    tracked = len(state.get("events", {}))
    last_run = _fmt_ts(state.get("last_run"), settings.tz_name)
    last_error = state.get("last_error") or "-"
    text = (
        "🤖 <b>Estado del bot</b>\n"
        f"• Dormido hasta: <b>{esc(sleep_txt)}</b>\n"
        f"• Quiet hours: <b>{esc(settings.quiet_start)} - {esc(settings.quiet_end)}</b>\n"
        f"• Intervalo: <b>{settings.scrape_interval_min} min</b>\n"
        f"• Eventos trackeados: <b>{tracked}</b>\n"
        f"• Última ejecución: <b>{esc(last_run)}</b>\n"
        f"• Último error: <b>{esc(short(str(last_error), 120))}</b>"
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
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Comandos disponibles:\n"
        "/dormir <horas> - Silencia notificaciones automáticas por X horas (default 8).\n"
        "/despertar - Cancela el modo dormido.\n"
        "/resumen - Fuerza scraping y envía resumen completo.\n"
        "/urgente - Fuerza scraping y muestra urgentes/vencidos no entregados.\n"
        "/pendientes - Fuerza scraping y muestra tareas con submitted=False.\n"
        "/estado - Muestra estado operativo del bot.\n"
        "/silencio <HH:MM> <HH:MM> - Cambia quiet hours en caliente.\n"
        "/intervalo <minutos> - Cambia frecuencia del scraping automático.\n"
        "/help - Muestra esta ayuda."
    )
    await _reply(update, text)


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("dormir", cmd_dormir))
    application.add_handler(CommandHandler("despertar", cmd_despertar))
    application.add_handler(CommandHandler("resumen", cmd_resumen))
    application.add_handler(CommandHandler("urgente", cmd_urgente))
    application.add_handler(CommandHandler("pendientes", cmd_pendientes))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CommandHandler("silencio", cmd_silencio))
    application.add_handler(CommandHandler("intervalo", cmd_intervalo))
    application.add_handler(CommandHandler("help", cmd_help))
