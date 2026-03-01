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

from telegram.ext import Application, CallbackContext

from ues_bot.commands import (
    SCRAPE_JOB_CALLBACK_KEY,
    SCRAPE_JOB_NAME,
    SCRAPE_LOCK_KEY,
    register_handlers,
    run_scrape_now,
)
from ues_bot.config import from_env
from ues_bot.logging_utils import setup_logging
from ues_bot.state import increment_error_count, is_sleeping, load_state, reset_error_count, save_state
from ues_bot.summary import build_changes_batch_message, build_sectioned_summary
from ues_bot.telegram_client import tg_send
from ues_bot.utils import chunk_messages, esc, is_in_quiet_hours, now_local


async def periodic_scrape_job(context: CallbackContext) -> None:
    """Periodic scrape job scheduled in the Telegram JobQueue."""
    settings = context.application.bot_data["settings"]
    state = load_state(settings.state_file)

    sleep_until_before = state.get("sleep_until")
    sleeping = is_sleeping(state)
    just_woke = bool(sleep_until_before) and not sleeping

    local_now = now_local(settings.tz_name)
    quiet_now = is_in_quiet_hours(local_now, settings.quiet_start, settings.quiet_end)
    save_state(settings.state_file, state)

    try:
        enriched_all, enriched_changed = await run_scrape_now(context, wait_for_lock_sec=0)
        reset_error_count(state)
        save_state(settings.state_file, state)
    except Exception as ex:
        logging.exception("Error en scraping periódico.")
        count = increment_error_count(state)
        state["last_error"] = str(ex)
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

    should_send_changes = bool(enriched_changed) or settings.notify_unchanged
    if settings.only_changes and not enriched_changed:
        should_send_changes = False

    can_send_auto = not sleeping and not quiet_now
    if not can_send_auto:
        logging.info(
            "Scraping ejecutado, sin notificación (sleeping=%s, quiet_now=%s).",
            sleeping,
            quiet_now,
        )
        return

    if just_woke:
        await tg_send(
            "☀️ Bot activo de nuevo. Enviando resumen automático.",
            settings.tg_bot_token,
            settings.tg_chat_id,
            dry_run=settings.dry_run,
            bot=context.bot,
        )

    if should_send_changes:
        msg = build_changes_batch_message(enriched_changed, max_items=settings.max_change_items)
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


def persist_state_on_shutdown(state_file: str) -> None:
    state = load_state(state_file)
    save_state(state_file, state)
    logging.info("Estado guardado. Bot detenido correctamente.")


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
    save_state(settings.state_file, startup_state)

    setup_logging(settings.log_file, verbose=settings.verbose)

    if not settings.tg_bot_token or not settings.tg_chat_id:
        raise RuntimeError("Falta TG_BOT_TOKEN o TG_CHAT_ID en variables de entorno.")

    app = Application.builder().token(settings.tg_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["run_scrape_args"] = {"headful": settings.headful}
    app.bot_data[SCRAPE_JOB_CALLBACK_KEY] = periodic_scrape_job
    app.bot_data[SCRAPE_LOCK_KEY] = asyncio.Lock()

    register_handlers(app)

    if app.job_queue is None:
        raise RuntimeError("JobQueue no disponible. Instala python-telegram-bot[job-queue].")
    app.job_queue.run_repeating(
        periodic_scrape_job,
        interval=settings.scrape_interval_min * 60,
        first=0,
        name=SCRAPE_JOB_NAME,
    )

    logging.info(
        "Bot iniciado. Intervalo=%d min, quiet=%s-%s, tz=%s",
        settings.scrape_interval_min,
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
