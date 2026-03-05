"""Long-running Telegram bot for UES scraping + notifications."""

from __future__ import annotations

import argparse
import asyncio
import logging

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from telegram.error import NetworkError
from telegram.ext import Application, CallbackContext

from ues_bot.commands import (
    LAST_SCRAPE_TS_KEY,
    SCRAPE_JOB_CALLBACK_KEY,
    SCRAPE_JOB_NAME,
    SCRAPE_LOCK_KEY,
    ScrapeAlreadyRunningError,
    register_handlers,
    run_scrape_now,
)
from ues_bot.config import from_env
from ues_bot.logging_utils import setup_logging
from ues_bot.reminders import get_pending_reminders
from ues_bot.state import (
    increment_error_count,
    increment_error_metrics,
    is_sleeping,
    load_state,
    reset_error_count,
    save_state,
)
from ues_bot.summary import (
    build_changes_batch_message,
    build_daily_digest,
    build_evening_preview,
    build_sectioned_summary,
    due_unix,
    remaining_parts_from_unix,
)
from ues_bot.telegram_client import tg_send
from ues_bot.utils import chunk_messages, esc, is_in_quiet_hours, now_local


def _get_notification_mode(settings, state) -> str:
    """Resolve the effective notification mode (state overrides settings)."""
    mode = state.get("notification_mode")
    if mode in ("smart", "silent", "all"):
        return mode
    return getattr(settings, "notification_mode", "smart")


def _is_transient_telegram_network_error(error: Exception | None) -> bool:
    if error is None or not isinstance(error, NetworkError):
        return False
    text = str(error).lower()
    return "getaddrinfo failed" in text or "httpx.connecterror" in text


async def global_error_handler(update: object, context: CallbackContext) -> None:
    """Log unhandled exceptions and notify via Telegram (respects quiet hours / sleep)."""
    settings = context.application.bot_data.get("settings")
    if settings is None:
        return

    state = load_state(settings.state_file)
    error_text = str(context.error)[:200] if context.error else "Error desconocido"
    is_transient_network = _is_transient_telegram_network_error(context.error)

    state["last_error"] = error_text
    state["last_error_kind"] = "network_transient" if is_transient_network else "functional"
    increment_error_metrics(state, state["last_error_kind"])
    save_state(settings.state_file, state)

    if is_transient_network:
        logging.warning("Error de red transitorio en Telegram: %s", error_text)
        return

    logging.exception("Excepción no manejada en handler:", exc_info=context.error)

    sleeping = is_sleeping(state)
    local_now = now_local(settings.tz_name)
    quiet_now = is_in_quiet_hours(local_now, settings.quiet_start, settings.quiet_end)

    if sleeping or quiet_now:
        return

    msg = f"❌ <b>Error inesperado</b>\n<code>{esc(error_text)}</code>"
    try:
        await tg_send(
            msg,
            settings.tg_bot_token,
            settings.tg_chat_id,
            dry_run=settings.dry_run,
            bot=context.bot,
        )
    except Exception:
        logging.error("No se pudo enviar alerta de error inesperado: %s", error_text)


async def periodic_scrape_job(context: CallbackContext) -> None:
    """Periodic scrape job — respects notification_mode.

    Modes:
        smart  → only send on changes + reminders (DEFAULT).
        silent → only send urgent reminders (≤1h).
        all    → legacy: always send full summary.
    """
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)

    notification_mode = _get_notification_mode(settings, state)

    sleep_until_before = state.get("sleep_until")
    sleeping = is_sleeping(state)
    just_woke = bool(sleep_until_before) and not sleeping

    local_now = now_local(settings.tz_name)
    quiet_now = is_in_quiet_hours(local_now, settings.quiet_start, settings.quiet_end)
    save_state(settings.state_file, state)

    # --- Scrape ---
    try:
        enriched_all, enriched_changed = await run_scrape_now(context, wait_for_lock_sec=0)
        reset_error_count(state)
        save_state(settings.state_file, state)
    except ScrapeAlreadyRunningError:
        logging.info("Scraping periódico omitido: ya hay otro scraping en curso.")
        return
    except Exception as ex:
        logging.exception("Error en scraping periódico.")
        count = increment_error_count(state)
        state["last_error"] = str(ex)
        state["last_error_kind"] = "functional"
        increment_error_metrics(state, "functional")
        save_state(settings.state_file, state)
        if count >= 3 and not sleeping and not quiet_now:
            error_msg = (
                f"⚠️ <b>Error en scraping automático</b> ({count} fallos consecutivos)\n"
                f"<code>{esc(str(ex)[:200])}</code>"
            )
            try:
                await tg_send(
                    error_msg,
                    settings.tg_bot_token,
                    settings.tg_chat_id,
                    dry_run=settings.dry_run,
                    bot=context.bot,
                )
            except Exception:
                logging.exception("No se pudo enviar alerta de error.")
        return

    can_send_auto = not sleeping and not quiet_now
    if not can_send_auto:
        logging.info(
            "Scraping ejecutado, sin notificación (sleeping=%s, quiet_now=%s, mode=%s).",
            sleeping, quiet_now, notification_mode,
        )
        return

    # --- Reminders (always sent in smart and all; only urgent in silent) ---
    sent_reminders = state.setdefault("sent_reminders", {})
    pending_reminders = get_pending_reminders(enriched_all, sent_reminders)
    reminders_sent_now = False

    for event, label in pending_reminders:
        # In silent mode, skip non-urgent reminders (only send 1h)
        if notification_mode == "silent" and label != "1h":
            continue

        due = due_unix(event)
        if due is None:
            continue
        _sec, rem_txt = remaining_parts_from_unix(due)
        link = event.assignment_url or event.url
        reminder_msg = (
            f"⏰ <b>Recordatorio ({label})</b>\n"
            f"• {esc(event.title)}\n"
            f"• 📚 {esc(event.course_name)}\n"
            f"• Tiempo restante: <b>{esc(rem_txt)}</b>\n"
            f"• 🔗 {esc(link)}"
        )
        await tg_send(
            reminder_msg,
            settings.tg_bot_token,
            settings.tg_chat_id,
            dry_run=settings.dry_run,
            bot=context.bot,
        )
        sent_list = sent_reminders.setdefault(event.event_id, [])
        if label not in sent_list:
            sent_list.append(label)
            reminders_sent_now = True

    if reminders_sent_now:
        save_state(settings.state_file, state)

    # --- Just woke up → mini digest ---
    if just_woke:
        digest = build_daily_digest(enriched_all, tz_name=settings.tz_name, urgent_hours=settings.urgent_hours)
        wake_msg = "☀️ Bot activo de nuevo.\n\n" + digest
        for part in chunk_messages(wake_msg):
            await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)
        return

    # --- Mode-based messaging ---
    if notification_mode == "silent":
        # Silent: scrape done, reminders sent above, nothing else.
        logging.info("Scrape periódico OK (silent mode, %d eventos).", len(enriched_all))
        return

    if notification_mode == "smart":
        # Smart: only send changes notification, no full summary.
        if enriched_changed:
            msg = build_changes_batch_message(enriched_changed, max_items=settings.max_change_items)
            if msg:
                for part in chunk_messages(msg):
                    await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)
        else:
            logging.info("Scrape periódico OK, sin cambios (smart mode, %d eventos).", len(enriched_all))
        return

    # --- Mode "all" (legacy behavior) ---
    if enriched_changed:
        msg = build_changes_batch_message(enriched_changed, max_items=settings.max_change_items)
        if msg:
            for part in chunk_messages(msg):
                await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)

    summary = build_sectioned_summary(
        enriched_all,
        tz_name=settings.tz_name,
        urgent_hours=settings.urgent_hours,
        max_lines_total=settings.max_summary_lines,
    )
    for part in chunk_messages(summary):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


async def daily_digest_job(context: CallbackContext) -> None:
    """Daily morning digest — always sends (unless sleeping/quiet)."""
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)

    sleeping = is_sleeping(state)
    local_now = now_local(settings.tz_name)
    quiet_now = is_in_quiet_hours(local_now, settings.quiet_start, settings.quiet_end)

    if sleeping or quiet_now:
        logging.info("Digest matutino omitido (sleeping=%s, quiet=%s).", sleeping, quiet_now)
        return

    try:
        enriched_all, _ = await run_scrape_now(context, wait_for_lock_sec=0)
    except ScrapeAlreadyRunningError:
        logging.info("Digest matutino omitido: scrape en curso.")
        return
    except Exception as ex:
        logging.exception("Error en digest matutino: %s", ex)
        return

    digest = build_daily_digest(enriched_all, tz_name=settings.tz_name, urgent_hours=settings.urgent_hours)
    for part in chunk_messages(digest):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


async def evening_preview_job(context: CallbackContext) -> None:
    """Evening preview — shows what's due tomorrow."""
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)

    sleeping = is_sleeping(state)
    local_now = now_local(settings.tz_name)
    quiet_now = is_in_quiet_hours(local_now, settings.quiet_start, settings.quiet_end)

    if sleeping or quiet_now:
        logging.info("Preview vespertino omitido (sleeping=%s, quiet=%s).", sleeping, quiet_now)
        return

    try:
        enriched_all, _ = await run_scrape_now(context, wait_for_lock_sec=0)
    except ScrapeAlreadyRunningError:
        logging.info("Preview vespertino omitido: scrape en curso.")
        return
    except Exception as ex:
        logging.exception("Error en preview vespertino: %s", ex)
        return

    preview = build_evening_preview(enriched_all, tz_name=settings.tz_name)
    for part in chunk_messages(preview):
        await tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=settings.dry_run, bot=context.bot)


def persist_state_on_shutdown(state_file: str) -> None:
    state = load_state(state_file)
    save_state(state_file, state)
    logging.info("Estado guardado. Bot detenido correctamente.")


def _schedule_daily_job(job_queue, callback, hour_str: str, tz_name: str, job_name: str) -> bool:
    """Helper to schedule a daily job. Returns True if scheduled."""
    from ues_bot.utils import parse_hhmm
    from datetime import time as dt_time

    if not hour_str:
        return False
    try:
        hh, mm = parse_hhmm(hour_str)
        if ZoneInfo is not None:
            tz = ZoneInfo(tz_name)
        else:
            tz = None
        job_queue.run_daily(callback, time=dt_time(hour=hh, minute=mm, tzinfo=tz), name=job_name)
        logging.info("Job '%s' programado a las %s (%s).", job_name, hour_str, tz_name)
        return True
    except Exception as ex:
        logging.warning("No se pudo programar job '%s': %s", job_name, ex)
        return False


def main() -> None:
    settings = from_env()

    parser = argparse.ArgumentParser(description="UES Learning -> Telegram long-running bot")
    parser.add_argument("--headful", action="store_true", help="Abrir navegador visible (no headless).")
    parser.add_argument("--verbose", action="store_true", help="Logs DEBUG.")
    parser.add_argument("--dry-run", action="store_true", help="No envía a Telegram, solo simula.")
    parser.add_argument("--tz", default=None, help="Timezone IANA.")
    parser.add_argument("--quiet-start", default=None, help="Inicio quiet hours HH:MM (vacío desactiva).")
    parser.add_argument("--quiet-end", default=None, help="Fin quiet hours HH:MM (vacío desactiva).")
    parser.add_argument("--urgent-hours", type=int, default=None, help="Horas para considerar urgente.")
    parser.add_argument("--only-changes", action="store_true", help="Solo notificar cambios (default).")
    parser.add_argument("--notify-unchanged", action="store_true", help="Notificar aunque no haya cambios.")
    parser.add_argument("--max-change-items", type=int, default=None, help="Máx items en cambios.")
    parser.add_argument("--max-summary-lines", type=int, default=None, help="Máx líneas resumen.")
    parser.add_argument("--scrape-interval-min", type=int, default=None, help="Intervalo de scraping automático.")
    parser.add_argument(
        "--scrape-lock-wait-sec",
        type=int,
        default=None,
        help="Tiempo máximo para esperar lock de scraping en comandos bajo demanda.",
    )
    parser.add_argument("--digest-hour", default=None, help="Hora del digest matutino HH:MM (ej. 07:00).")
    parser.add_argument("--digest-evening", default=None, help="Hora del preview vespertino HH:MM (ej. 20:00, vacío desactiva).")
    parser.add_argument("--notification-mode", default=None, choices=["smart", "silent", "all"],
                        help="Modo de notificación: smart (default), silent, all.")
    args = parser.parse_args()

    settings.headful = args.headful
    settings.verbose = args.verbose
    settings.dry_run = args.dry_run

    if args.tz:
        settings.tz_name = args.tz
    if args.urgent_hours is not None:
        settings.urgent_hours = args.urgent_hours
    if args.max_change_items is not None:
        settings.max_change_items = args.max_change_items
    if args.max_summary_lines is not None:
        settings.max_summary_lines = args.max_summary_lines
    if args.scrape_interval_min is not None:
        settings.scrape_interval_min = args.scrape_interval_min
    if args.scrape_lock_wait_sec is not None:
        settings.scrape_lock_wait_sec = args.scrape_lock_wait_sec
    if args.only_changes:
        settings.only_changes = True
    if args.notify_unchanged:
        settings.notify_unchanged = True
    if args.digest_hour:
        settings.digest_hour = args.digest_hour
    if args.digest_evening is not None:
        settings.digest_evening_hour = args.digest_evening
    if args.notification_mode:
        settings.notification_mode = args.notification_mode

    # --- Restore state-persisted overrides ---
    startup_state = load_state(settings.state_file)
    if args.quiet_start is not None and args.quiet_end is not None:
        settings.quiet_start = args.quiet_start
        settings.quiet_end = args.quiet_end
        startup_state["quiet_start"] = args.quiet_start
        startup_state["quiet_end"] = args.quiet_end
    else:
        if startup_state.get("quiet_start"):
            settings.quiet_start = startup_state["quiet_start"]
        if startup_state.get("quiet_end"):
            settings.quiet_end = startup_state["quiet_end"]
    # Restore notification mode from state if set by /notificar
    saved_mode = startup_state.get("notification_mode")
    if saved_mode in ("smart", "silent", "all") and args.notification_mode is None:
        settings.notification_mode = saved_mode
    # Restore evening hour from state if set by /digestpm
    saved_evening = startup_state.get("digest_evening_hour")
    if saved_evening is not None and args.digest_evening is None:
        settings.digest_evening_hour = saved_evening

    save_state(settings.state_file, startup_state)

    setup_logging(settings.log_file, verbose=settings.verbose)

    if not settings.tg_bot_token or not settings.tg_chat_id:
        raise RuntimeError("Falta TG_BOT_TOKEN o TG_CHAT_ID en variables de entorno.")

    app = Application.builder().token(settings.tg_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["run_scrape_args"] = {"headful": settings.headful}
    app.bot_data[SCRAPE_JOB_CALLBACK_KEY] = periodic_scrape_job
    app.bot_data[SCRAPE_LOCK_KEY] = asyncio.Lock()
    app.bot_data[LAST_SCRAPE_TS_KEY] = 0.0

    register_handlers(app)
    app.add_error_handler(global_error_handler)

    if app.job_queue is None:
        raise RuntimeError("JobQueue no disponible. Instala python-telegram-bot[job-queue].")

    # Periodic scrape
    app.job_queue.run_repeating(
        periodic_scrape_job,
        interval=settings.scrape_interval_min * 60,
        first=0,
        name=SCRAPE_JOB_NAME,
    )

    # Morning digest
    _schedule_daily_job(app.job_queue, daily_digest_job, settings.digest_hour, settings.tz_name, "daily_digest")

    # Evening preview
    _schedule_daily_job(app.job_queue, evening_preview_job, settings.digest_evening_hour, settings.tz_name, "evening_preview")

    logging.info(
        "Bot iniciado. mode=%s, intervalo=%dmin, digest=%s, evening=%s, quiet=%s-%s, tz=%s",
        settings.notification_mode,
        settings.scrape_interval_min,
        settings.digest_hour,
        settings.digest_evening_hour or "off",
        settings.quiet_start,
        settings.quiet_end,
        settings.tz_name,
    )
    try:
        app.run_polling(drop_pending_updates=False)
    finally:
        persist_state_on_shutdown(settings.state_file)


if __name__ == "__main__":
    main()
