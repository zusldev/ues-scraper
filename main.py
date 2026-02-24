"""Entry point.
# ues_to_telegram_playwright.py
# Reqs:
#   pip install playwright requests beautifulsoup4
#   python -m playwright install
#
# Env vars:
#   TG_BOT_TOKEN, TG_CHAT_ID
#   UES_USER, UES_PASS
#
# Notes:
# - Uses Playwright to login (username/password) and persist session in storage_state.json
# - Scrapes Dashboard events, sends detailed messages for NEW/CHANGED events
# - Sends a "Resumen rápido" at the end: status + activity + course + remaining time
# - NOW -
Run:
  python main.py

Options:
  python main.py --headful
  python main.py --dry-run
  python main.py --quiet-start 22:00 --quiet-end 07:00
  python main.py --urgent-hours 12
"""

from __future__ import annotations

import argparse
import logging
import os

from playwright.sync_api import sync_playwright

# Optional .env support (recommended)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from ues_bot.config import from_env
from ues_bot.logging_utils import setup_logging
from ues_bot.state import load_state, save_state
from ues_bot.scrape import (
    login_if_needed,
    safe_goto,
    parse_events_from_dashboard,
    enrich_from_event_page,
    find_assignment_url,
    assignment_is_submitted,
)
from ues_bot.summary import build_changes_batch_message, build_sectioned_summary
from ues_bot.telegram_client import tg_send
from ues_bot.utils import now_local, is_in_quiet_hours, chunk_messages


def main() -> None:
    settings = from_env()

    parser = argparse.ArgumentParser(description="UES Learning -> Telegram (Playwright) modular")
    parser.add_argument("--headful", action="store_true", help="Abrir navegador visible (no headless).")
    parser.add_argument("--verbose", action="store_true", help="Logs DEBUG.")
    parser.add_argument("--dry-run", action="store_true", help="No envía a Telegram, solo simula.")
    parser.add_argument("--tz", default=settings.tz_name, help="Timezone IANA.")
    parser.add_argument("--quiet-start", default=settings.quiet_start, help="Inicio quiet hours HH:MM (vacío desactiva).")
    parser.add_argument("--quiet-end", default=settings.quiet_end, help="Fin quiet hours HH:MM (vacío desactiva).")
    parser.add_argument("--urgent-hours", type=int, default=settings.urgent_hours, help="Horas para considerar urgente.")
    parser.add_argument("--only-changes", action="store_true", help="Solo notificar cambios (default).")
    parser.add_argument("--notify-unchanged", action="store_true", help="Notificar aunque no haya cambios.")
    parser.add_argument("--max-change-items", type=int, default=settings.max_change_items, help="Máx items en cambios.")
    parser.add_argument("--max-summary-lines", type=int, default=settings.max_summary_lines, help="Máx líneas resumen.")
    args = parser.parse_args()

    headful = args.headful
    verbose = args.verbose
    dry_run = args.dry_run
    only_changes = True if args.only_changes else settings.only_changes
    notify_unchanged = args.notify_unchanged or settings.notify_unchanged

    setup_logging(settings.log_file, verbose=verbose)

    local_now = now_local(args.tz)
    quiet = is_in_quiet_hours(local_now, args.quiet_start, args.quiet_end)
    if quiet:
        logging.info("Quiet hours activas (%s-%s). No se enviarán mensajes.", args.quiet_start, args.quiet_end)

    state = load_state(settings.state_file)
    known = state.setdefault("events", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        if settings.storage_file and os.path.exists(settings.storage_file):
            context = browser.new_context(storage_state=settings.storage_file)
        else:
            context = browser.new_context()

        page = context.new_page()

        login_if_needed(
            page,
            context,
            dashboard_url=settings.dashboard_url,
            ues_user=settings.ues_user,
            ues_pass=settings.ues_pass,
            storage_file=settings.storage_file,
        )

        safe_goto(page, settings.dashboard_url)
        dashboard_html = page.content()
        events = parse_events_from_dashboard(dashboard_html)
        logging.info("Eventos en dashboard: %d", len(events))

        changed_basic = []
        for e in events:
            prev = known.get(e.event_id)
            if prev is None or prev.get("due_text") != e.due_text or prev.get("title") != e.title:
                changed_basic.append(e)
            known[e.event_id] = {**(prev or {}), "title": e.title, "due_text": e.due_text, "url": e.url}

        enriched_all = []
        changed_ids = {c.event_id for c in changed_basic}

        for e in events:
            try:
                safe_goto(page, e.url)
            except Exception as ex:
                logging.warning("No pude abrir evento %s: %s", e.url, ex)
                enriched_all.append(e)
                continue

            event_html = page.content()
            e.course_name, e.description = enrich_from_event_page(event_html)
            e.assignment_url = find_assignment_url(event_html, base=settings.base)

            if e.assignment_url:
                try:
                    safe_goto(page, e.assignment_url)
                    assign_html = page.content()
                    e.submitted, e.submission_status = assignment_is_submitted(assign_html)
                except Exception as ex:
                    logging.warning("No pude abrir assignment %s: %s", e.assignment_url, ex)

            enriched_all.append(e)

        enriched_changed = [e for e in enriched_all if e.event_id in changed_ids]

        should_send_changes = bool(enriched_changed) or notify_unchanged
        if only_changes and not enriched_changed:
            should_send_changes = False

        if not quiet and should_send_changes:
            msg = build_changes_batch_message(enriched_changed, max_items=args.max_change_items)
            for part in chunk_messages(msg):
                tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=dry_run)

        if not quiet:
            summary = build_sectioned_summary(
                enriched_all,
                tz_name=args.tz,
                urgent_hours=args.urgent_hours,
                max_lines_total=args.max_summary_lines,
            )
            for part in chunk_messages(summary):
                tg_send(part, settings.tg_bot_token, settings.tg_chat_id, dry_run=dry_run)

        save_state(settings.state_file, state)
        browser.close()

    logging.info("Listo.")


if __name__ == "__main__":
    main()
