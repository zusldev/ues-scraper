"""Playwright + BeautifulSoup scraping routines for UES dashboard/events."""

from __future__ import annotations

import re
import logging
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout
from tenacity import Retrying, before_sleep_log, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import Event

SUBMITTED_PHRASES = ["enviado para calificar", "entregado para calificar", "submitted for grading"]
NOT_SUBMITTED_PHRASES = [
    "aun no se ha hecho ninguna tarea",
    "aún no se ha hecho ninguna tarea",
    "no se han realizado envíos",
    "no se han realizado entregas",
    "sin enviar",
    "borrador",
    "draft (not submitted)",
    "no submission",
]


def assignment_is_submitted(assign_html: str) -> Tuple[Optional[bool], str]:
    soup = BeautifulSoup(assign_html, "html.parser")

    td_submitted = soup.select_one("td.submissionstatussubmitted")
    if td_submitted:
        val = td_submitted.get_text(" ", strip=True)
        return True, val or "Enviado para calificar"

    td_nosub = soup.select_one("td.submissionstatusnosubmission")
    if td_nosub:
        val = td_nosub.get_text(" ", strip=True)
        return False, val or "Sin envío"

    for row in soup.select("table.generaltable tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = th.get_text(" ", strip=True).lower()
        if (
            "estatus de la entrega" in label
            or "estado de la entrega" in label
            or "submission status" in label
        ):
            value = td.get_text(" ", strip=True)
            v = value.lower()
            if any(p in v for p in SUBMITTED_PHRASES):
                return True, value
            if any(p in v for p in NOT_SUBMITTED_PHRASES):
                return False, value
            return None, value

    return None, "No detectado"


def parse_events_from_dashboard(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for ev in soup.select('div.event[data-region="event-item"]'):
        a_title = ev.select_one('h6 a[data-action="view-event"]')
        a_due = ev.select_one("div.date.small a")
        if not a_title:
            continue

        title = a_title.get_text(" ", strip=True)

        url = a_title.get("href") or ""
        if isinstance(url, list):
            url = url[0] if url else ""
        url = (url or "").strip()

        due_text = a_due.get_text(" ", strip=True) if a_due else ""

        event_id = a_title.get("data-event-id") or ""
        if isinstance(event_id, list):
            event_id = event_id[0] if event_id else ""
        event_id = (event_id or "").strip()

        if not event_id and url:
            m = re.search(r"[?&]event=(\d+)", url)
            if m:
                event_id = m.group(1)

        if not event_id:
            event_id = url or title

        events.append(Event(event_id=event_id, title=title, due_text=due_text, url=url))

    return events


def enrich_from_event_page(event_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(event_html, "html.parser")
    a_course = soup.select_one('a[href*="/course/view.php?id="]')
    course_name = a_course.get_text(" ", strip=True) if a_course else "Sin materia"

    desc_div = soup.select_one("div.description-content")
    description = ""
    if desc_div:
        description = desc_div.get_text("\n", strip=True)
        description = re.sub(r"\n{3,}", "\n\n", description).strip()

    return course_name, description


def find_assignment_url(event_html: str, base: str) -> str:
    soup = BeautifulSoup(event_html, "html.parser")
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if isinstance(href, list):
            href = href[0] if href else ""
        if not isinstance(href, str):
            continue
        href = href.strip()
        if f"{base}/mod/" in href and "view.php?id=" in href:
            return href
    return ""


def login_if_needed(page, context, dashboard_url: str, ues_user: str, ues_pass: str, storage_file: str) -> None:
    page.goto(dashboard_url, wait_until="domcontentloaded")
    if "login" not in page.url.lower():
        return

    if not ues_user or not ues_pass:
        raise RuntimeError("Faltan UES_USER / UES_PASS en variables de entorno.")

    try:
        page.wait_for_selector('input[type="password"]', timeout=10000)
    except PWTimeout:
        raise RuntimeError("No encontré el formulario de login (no apareció input password).")

    user_sel = 'input[name="username"], input#username, input[name="user"], input[type="email"]'
    pass_sel = 'input[name="password"], input#password, input[type="password"]'

    page.fill(user_sel, ues_user)
    page.fill(pass_sel, ues_pass)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("domcontentloaded")

    if "login" in page.url.lower():
        raise RuntimeError("Login falló (sigue en pantalla de login). Revisa usuario/contraseña o selectores.")

    context.storage_state(path=storage_file)


def safe_goto(page, url: str, tries: int = 3, wait_until: str = "domcontentloaded") -> None:
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(tries),
            wait=wait_exponential(multiplier=1.2, min=1, max=10),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
            reraise=True,
        ):
            with attempt:
                page.goto(url, wait_until=wait_until, timeout=45000)
    except Exception as exc:
        raise RuntimeError(f"No se pudo navegar a {url}") from exc
