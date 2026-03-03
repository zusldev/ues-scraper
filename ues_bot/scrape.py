"""Playwright + BeautifulSoup scraping routines for UES dashboard/events."""

from __future__ import annotations

import re
import logging
import unicodedata
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout
from tenacity import Retrying, before_sleep_log, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import Event

log = logging.getLogger(__name__)

SUBMITTED_PHRASES = ["enviado para calificar", "entregado para calificar", "submitted for grading"]
NOT_SUBMITTED_PHRASES = [
    "aun no se ha hecho ninguna tarea",
    "aún no se ha hecho ninguna tarea",
    "no se han realizado envíos",
    "no se han realizado entregas",
    "sin enviar",
    "sin envio",
    "sin entrega",
    "no enviado",
    "no entregado",
    "no ha enviado",
    "no ha entregado",
    "not submitted",
    "not yet submitted",
    "borrador",
    "draft (not submitted)",
    "no submission",
]

# Labels for the submission status row in the assignment table (ES + EN variants).
_SUBMISSION_STATUS_LABELS = [
    "estatus de la entrega",
    "estado de la entrega",
    "submission status",
    "estado del envío",
]

# Labels for the grading status row.
_GRADING_STATUS_LABELS = [
    "estatus de calificación",
    "estado de calificación",
    "grading status",
]


def _norm_text(text: str) -> str:
    """Normalize text for robust matching across accents/encoding quirks."""
    text = (text or "").lower().strip()
    # Replace common mojibake pieces seen in Windows logs/terminal output.
    text = text.replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i").replace("Ã³", "o").replace("Ãº", "u")
    text = text.replace("Ã±", "n")
    # Remove accents/diacritics.
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def assignment_is_submitted(assign_html: str) -> Tuple[Optional[bool], str]:
    soup = BeautifulSoup(assign_html, "html.parser")

    # 1) Fast path: CSS class on the <td> added by Moodle.
    td_submitted = soup.select_one("td.submissionstatussubmitted")
    if td_submitted:
        val = td_submitted.get_text(" ", strip=True)
        return True, val or "Enviado para calificar"

    td_nosub = soup.select_one("td.submissionstatusnosubmission")
    if td_nosub:
        val = td_nosub.get_text(" ", strip=True)
        return False, val or "Sin envío"

    # Normalized phrase lists for robust matching.
    submitted_phrases_n = [_norm_text(p) for p in SUBMITTED_PHRASES]
    not_submitted_phrases_n = [_norm_text(p) for p in NOT_SUBMITTED_PHRASES]
    status_labels_n = [_norm_text(lbl) for lbl in _SUBMISSION_STATUS_LABELS]

    # 2) Text-based fallback: walk the "generaltable" rows.
    for row in soup.select("table.generaltable tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label_raw = th.get_text(" ", strip=True)
        value_raw = td.get_text(" ", strip=True)
        label = _norm_text(label_raw)
        value = _norm_text(value_raw)

        if any(lbl in label for lbl in status_labels_n):
            if any(p in value for p in submitted_phrases_n):
                return True, value_raw
            if any(p in value for p in not_submitted_phrases_n):
                return False, value_raw
            return None, value_raw

    # 3) Last-resort fallback: detect phrases in the whole page text.
    whole = _norm_text(soup.get_text(" ", strip=True))
    if any(p in whole for p in submitted_phrases_n):
        return True, "Detectado por texto global"
    if any(p in whole for p in not_submitted_phrases_n):
        return False, "Detectado por texto global"

    return None, "No detectado"


def parse_grading_status(assign_html: str) -> str:
    """Extract the grading status (e.g. "No calificado", "Calificado") from the assignment page."""
    soup = BeautifulSoup(assign_html, "html.parser")
    for row in soup.select("table.generaltable tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = th.get_text(" ", strip=True).lower()
        if any(lbl in label for lbl in _GRADING_STATUS_LABELS):
            return td.get_text(" ", strip=True)
    return ""


# ---------------------------------------------------------------------------
# Timeline block parser  (data-region="event-list-item")
# ---------------------------------------------------------------------------

def _parse_timeline_items(soup: BeautifulSoup) -> List[Event]:
    """Parse the *Línea de tiempo* block rendered by block_timeline.

    Each ``<div data-region="event-list-item">`` contains:
    * ``h6.event-name a`` → title + direct assignment URL + ``aria-label``
      with course name & full due date.
    * ``.event-name-container small`` → subtitle text like
      "Tarea está en fecha de entrega · IS N Redes de Computo 001".
    * ``.timeline-action-button a`` → action URL ("Añadir envío", etc.).
    """
    events: List[Event] = []
    for item in soup.select('[data-region="event-list-item"]'):
        a_title = item.select_one("h6.event-name a")
        if not a_title:
            continue

        title = a_title.get_text(" ", strip=True)
        url = _attr_str(a_title, "href")
        aria = _attr_str(a_title, "aria-label")

        # Extract course name from aria-label:
        # "Act 13: ... actividad en IS N Redes de Computo 001 está pendiente para ..."
        course_name = ""
        m = re.search(r"actividad en (.+?) está pendiente para", aria)
        if m:
            course_name = m.group(1).strip()

        # Extract due date from aria-label:
        # "... está pendiente para 8 de marzo de 2026, 23:59"
        due_text = ""
        m_due = re.search(r"está pendiente para (.+)", aria)
        if m_due:
            due_text = m_due.group(1).strip()

        # subtitle may have course too: "Tarea está en fecha de entrega · COURSE"
        if not course_name:
            subtitle_el = item.select_one(".event-name-container small")
            if subtitle_el:
                subtitle = subtitle_el.get_text(" ", strip=True)
                parts = subtitle.rsplit("·", 1)
                if len(parts) == 2:
                    course_name = parts[1].strip()

        # Fallback due text from the time element
        if not due_text:
            time_el = item.select_one(".timeline-name > small")
            if time_el:
                due_text = time_el.get_text(" ", strip=True)

        # Assignment URL from the action button (e.g. "Añadir envío")
        assignment_url = ""
        action_a = item.select_one(".timeline-action-button a")
        if action_a:
            action_href = _attr_str(action_a, "href")
            # Strip query params like &action=editsubmission
            clean = re.sub(r"[&?]action=\w+", "", action_href)
            if "/mod/" in clean and "view.php" in clean:
                assignment_url = clean

        # Direct URL to the assignment (the title link itself often points there)
        if not assignment_url and "/mod/" in url and "view.php" in url:
            assignment_url = url

        # Generate event_id from URL
        event_id = ""
        if url:
            m_id = re.search(r"[?&]id=(\d+)", url)
            if m_id:
                event_id = f"tl_{m_id.group(1)}"
        if not event_id:
            event_id = url or title

        events.append(Event(
            event_id=event_id,
            title=title,
            due_text=due_text,
            url=url,
            course_name=course_name or "Sin materia",
            assignment_url=assignment_url,
        ))
    return events


# ---------------------------------------------------------------------------
# "Eventos próximos" block parser  (data-region="event-item")
# ---------------------------------------------------------------------------

def _parse_upcoming_events(soup: BeautifulSoup) -> List[Event]:
    """Parse the *Eventos próximos* sidebar block.

    Each ``<div class="event" data-region="event-item">`` contains:
    * ``h6 a[data-action="view-event"]`` → title, calendar URL, event-id
    * ``div.date.small`` → human-readable due text + link with ``time=`` unix ts
    """
    events: List[Event] = []
    for ev in soup.select('div.event[data-region="event-item"]'):
        a_title = ev.select_one('h6 a[data-action="view-event"]')
        a_due = ev.select_one("div.date.small a")
        if not a_title:
            continue

        title = a_title.get_text(" ", strip=True)
        url = _attr_str(a_title, "href")
        due_text = ""

        # Build due_text from the whole date div (e.g. "Hoy, 23:21")
        date_div = ev.select_one("div.date.small")
        if date_div:
            due_text = date_div.get_text(" ", strip=True)
        elif a_due:
            due_text = a_due.get_text(" ", strip=True)

        event_id = _attr_str(a_title, "data-event-id")

        if not event_id and url:
            m = re.search(r"#event_(\d+)", url)
            if m:
                event_id = m.group(1)

        if not event_id and url:
            m = re.search(r"[?&]event=(\d+)", url)
            if m:
                event_id = m.group(1)

        if not event_id:
            event_id = url or title

        events.append(Event(event_id=event_id, title=title, due_text=due_text, url=url))
    return events


def parse_events_from_dashboard(html: str) -> List[Event]:
    """Parse events from the Moodle dashboard page.

    Merges results from two blocks present on the dashboard:
    1. "Eventos próximos" — server-rendered, always available.
    2. "Línea de tiempo"  — JS-rendered, has richer info (course, assignment URL).

    Timeline items that match an upcoming event (by title) enrich it;
    any remaining timeline-only items are appended.
    """
    soup = BeautifulSoup(html, "html.parser")

    upcoming = _parse_upcoming_events(soup)
    timeline = _parse_timeline_items(soup)

    if not upcoming and not timeline:
        return []

    # Index upcoming events by a normalised title key for merging
    def _norm(t: str) -> str:
        # Timeline titles may omit the trailing " está en fecha de entrega" etc.
        t = re.sub(r"\s+", " ", t).strip().lower()
        for suffix in [
            " está en fecha de entrega",
            " is due",
            " debe entregarse",
        ]:
            if t.endswith(suffix):
                t = t[: -len(suffix)].strip()
        return t

    upcoming_by_norm: Dict[str, Event] = {}
    for ev in upcoming:
        upcoming_by_norm[_norm(ev.title)] = ev

    merged_ids: set[str] = set()
    for tl in timeline:
        norm_key = _norm(tl.title)
        match = upcoming_by_norm.get(norm_key)
        if match:
            # Enrich the upcoming event with timeline data
            if tl.course_name and tl.course_name != "Sin materia":
                match.course_name = tl.course_name
            if tl.assignment_url:
                match.assignment_url = tl.assignment_url
            if tl.due_text and not match.due_text:
                match.due_text = tl.due_text
            merged_ids.add(norm_key)

    # Start with all upcoming events (enriched where possible)
    result = list(upcoming)

    # Append timeline-only events (not already in upcoming)
    for tl in timeline:
        if _norm(tl.title) not in merged_ids:
            result.append(tl)

    log.info(
        "Dashboard parse: %d upcoming + %d timeline → %d merged events",
        len(upcoming), len(timeline), len(result),
    )
    return result


def enrich_from_event_page(event_html: str) -> tuple[str, str]:
    """Extract course name and description from a calendar day-view event page."""
    soup = BeautifulSoup(event_html, "html.parser")

    # The course name appears as a link to /course/view.php inside the event
    # detail card.  On the calendar day view the *last* such link (inside
    # the event detail area) holds the friendly short name (e.g.
    # "IS N Auditoria en Informatica 001") while earlier ones are generic
    # section names ("General", "Elemento de Competencia 2").
    course_name = "Sin materia"
    course_links = soup.select('a[href*="/course/view.php?id="]')
    if course_links:
        # Prefer a link whose text is NOT a generic section label
        generic_labels = {"general", "sección"}
        for a in reversed(course_links):
            text = a.get_text(" ", strip=True)
            if text and text.lower() not in generic_labels:
                course_name = text
                break
        if course_name == "Sin materia" and course_links:
            course_name = course_links[0].get_text(" ", strip=True) or "Sin materia"

    desc_div = soup.select_one("div.description-content")
    description = ""
    if desc_div:
        description = desc_div.get_text("\n", strip=True)
        description = re.sub(r"\n{3,}", "\n\n", description).strip()

    return course_name, description


def find_assignment_url(event_html: str, base: str) -> str:
    """Find the direct assignment/activity URL inside an event page."""
    soup = BeautifulSoup(event_html, "html.parser")

    # Prefer the "Ir a la actividad" / "Go to activity" footer link
    for a in soup.select("a.card-link[href]"):
        href = _attr_str(a, "href")
        if f"{base}/mod/" in href and "view.php" in href:
            return href

    # Fallback: any link to /mod/*/view.php?id=...
    for a in soup.select("a[href]"):
        href = _attr_str(a, "href")
        if f"{base}/mod/" in href and "view.php?id=" in href:
            return href
    return ""


def _attr_str(tag, attr: str) -> str:
    """Safely extract a single string attribute from a BS4 tag."""
    val = tag.get(attr, "")
    if isinstance(val, list):
        val = val[0] if val else ""
    return (val or "").strip()


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
