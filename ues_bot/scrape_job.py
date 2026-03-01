"""Reusable scraping cycle for periodic jobs and on-demand commands."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Mapping

from playwright.sync_api import sync_playwright

from .config import Settings
from .models import Event
from .scrape import (
    assignment_is_submitted,
    enrich_from_event_page,
    find_assignment_url,
    login_if_needed,
    parse_events_from_dashboard,
    safe_goto,
)
from .state import load_state, save_state


def run_scrape_cycle(
    settings: Settings,
    args_override: Mapping[str, Any] | None = None,
) -> tuple[list[Event], list[Event]]:
    """Run one browser-backed scrape cycle and return (all, changed)."""
    overrides = dict(args_override or {})
    headful = bool(overrides.get("headful", settings.headful))

    state = load_state(settings.state_file)
    known = state.setdefault("events", {})

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headful)
            try:
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

                changed_basic: list[Event] = []
                for event in events:
                    prev = known.get(event.event_id)
                    if prev is None or prev.get("due_text") != event.due_text or prev.get("title") != event.title:
                        changed_basic.append(event)
                    known[event.event_id] = {
                        **(prev or {}),
                        "title": event.title,
                        "due_text": event.due_text,
                        "url": event.url,
                    }

                enriched_all: list[Event] = []
                changed_ids = {event.event_id for event in changed_basic}
                for event in events:
                    try:
                        safe_goto(page, event.url)
                    except Exception as ex:
                        logging.warning("No pude abrir evento %s: %s", event.url, ex)
                        enriched_all.append(event)
                        continue

                    event_html = page.content()
                    event.course_name, event.description = enrich_from_event_page(event_html)
                    event.assignment_url = find_assignment_url(event_html, base=settings.base)

                    if event.assignment_url:
                        try:
                            safe_goto(page, event.assignment_url)
                            assign_html = page.content()
                            event.submitted, event.submission_status = assignment_is_submitted(assign_html)
                        except Exception as ex:
                            logging.warning("No pude abrir assignment %s: %s", event.assignment_url, ex)

                    enriched_all.append(event)

                enriched_changed = [event for event in enriched_all if event.event_id in changed_ids]
            finally:
                browser.close()

        state["last_run"] = int(time.time())
        state["last_error"] = None
        save_state(settings.state_file, state)
        return enriched_all, enriched_changed
    except Exception as ex:
        state["last_error"] = str(ex)
        save_state(settings.state_file, state)
        raise
