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

import os
import re
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://ueslearning.ues.mx"
DASHBOARD_URL = f"{BASE}/my/"
STATE_FILE = "seen_events.json"
STORAGE_FILE = "storage_state.json"

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

UES_USER = os.getenv("UES_USER", "")
UES_PASS = os.getenv("UES_PASS", "")

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


@dataclass
class Event:
    """Data class representing a course event/assignment from UES portal."""
    event_id: str
    title: str
    due_text: str
    url: str
    course_name: str = "Sin materia"
    description: str = ""
    assignment_url: str = ""
    submitted: Optional[bool] = None
    submission_status: str = ""


def tg_send(text: str) -> None:
    """Sends a message to Telegram using the Bot API."""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        raise RuntimeError("Falta TG_BOT_TOKEN o TG_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        data={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    r.raise_for_status()


def esc(s: str) -> str:
    """Escapes HTML special characters for Telegram messages."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def assignment_is_submitted(assign_html: str) -> Tuple[Optional[bool], str]:
    """Parses assignment HTML to determine if it was submitted or not."""
    soup = BeautifulSoup(assign_html, "html.parser")

    # Fast path: the exact class you showed in your HTML
    td_submitted = soup.select_one("td.submissionstatussubmitted")
    if td_submitted:
        val = td_submitted.get_text(" ", strip=True)
        return True, val or "Enviado para calificar"

    td_nosub = soup.select_one("td.submissionstatusnosubmission")
    if td_nosub:
        val = td_nosub.get_text(" ", strip=True)
        return False, val or "Sin envío"

    # Row lookup by label
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


def load_state() -> Dict:
    """Loads previously seen events from JSON file."""
    if not os.path.exists(STATE_FILE):
        return {"events": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: Dict) -> None:
    """Saves events state to JSON file for tracking changes."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def parse_events_from_dashboard(html: str) -> List[Event]:
    """Parses dashboard HTML to extract event information."""
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

        # fallback: try querystring
        if not event_id and url:
            m = re.search(r"[?&]event=(\d+)", url)
            if m:
                event_id = m.group(1)

        # last fallback: unique-ish key
        if not event_id:
            event_id = url or title

        events.append(Event(event_id=event_id, title=title, due_text=due_text, url=url))

    return events


def enrich_from_event_page(event_html: str) -> Tuple[str, str]:
    """Extracts course name and description from event detail page."""
    soup = BeautifulSoup(event_html, "html.parser")
    a_course = soup.select_one('a[href*="/course/view.php?id="]')
    course_name = a_course.get_text(" ", strip=True) if a_course else "Sin materia"

    desc_div = soup.select_one("div.description-content")
    description = ""
    if desc_div:
        description = desc_div.get_text("\n", strip=True)
        description = re.sub(r"\n{3,}", "\n\n", description).strip()

    return course_name, description


def find_assignment_url(event_html: str) -> str:
    """Finds the assignment link from event page HTML."""
    soup = BeautifulSoup(event_html, "html.parser")

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if isinstance(href, list):
            href = href[0] if href else ""
        if not isinstance(href, str):
            continue

        href = href.strip()
        if f"{BASE}/mod/" in href and "view.php?id=" in href:
            return href

    return ""


def login_if_needed(page, context) -> None:
    """Performs login to UES portal if session is not persisted."""
    page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
    if "login" not in page.url.lower():
        return

    if not UES_USER or not UES_PASS:
        raise RuntimeError("Faltan UES_USER / UES_PASS en variables de entorno.")

    try:
        page.wait_for_selector('input[type="password"]', timeout=8000)
    except PWTimeout:
        raise RuntimeError("No encontré el formulario de login (no apareció input password).")

    user_sel = 'input[name="username"], input#username, input[name="user"], input[type="email"]'
    pass_sel = 'input[name="password"], input#password, input[type="password"]'

    page.fill(user_sel, UES_USER)
    page.fill(pass_sel, UES_PASS)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("domcontentloaded")

    if "login" in page.url.lower():
        raise RuntimeError("Login falló (sigue en pantalla de login). Revisa usuario/contraseña o selectores.")

    context.storage_state(path=STORAGE_FILE)


# ------------ Minimal summary helpers ------------
def parse_due_unix_from_event_url(url: str) -> Optional[int]:
    """Extracts due date as Unix timestamp from event URL."""
    m = re.search(r"[?&]time=(\d+)", url or "")
    return int(m.group(1)) if m else None


def remaining_text_from_unix(due_unix: int) -> str:
    """Converts Unix timestamp to human-readable remaining time."""
    now = datetime.now(timezone.utc)
    due = datetime.fromtimestamp(due_unix, tz=timezone.utc)
    sec = int((due - now).total_seconds())
    if sec <= 0:
        return "0m"
    mins = sec // 60
    if mins < 60:
        return f"{mins}m"
    hrs = mins // 60
    rem_m = mins % 60
    if hrs < 24:
        return f"{hrs}h {rem_m}m" if rem_m else f"{hrs}h"
    days = hrs // 24
    rem_h = hrs % 24
    return f"{days}d {rem_h}h"


def short(s: str, n: int) -> str:
    """Truncates string to n characters with ellipsis."""
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def status_badge(submitted: Optional[bool]) -> str:
    """Returns emoji badge based on submission status."""
    if submitted is True:
        return "✅"
    if submitted is False:
        return "⚠️"
    return "❔"


def build_quick_summary(events_all: List[Event], max_lines: int = 12) -> str:
    """Builds a quick summary message of all events."""
    rows = []
    for e in events_all:
        due_unix = parse_due_unix_from_event_url(e.url)
        if due_unix:
            remaining = remaining_text_from_unix(due_unix)
            sort_key = due_unix
        else:
            remaining = e.due_text.strip() or "N/D"
            sort_key = 10**18

        rows.append(
            (
                sort_key,
                status_badge(e.submitted),
                short(e.title, 42),
                short(e.course_name, 26),
                remaining,
            )
        )

    rows.sort(key=lambda x: x[0])

    lines = ["📌 <b>Resumen rápido</b>"]
    for _, badge, title_s, course_s, remaining in rows[:max_lines]:
        lines.append(f"{badge} {esc(title_s)} — <i>{esc(course_s)}</i> — <b>quedan {esc(remaining)}</b>")

    if len(rows) > max_lines:
        lines.append(f"… (+{len(rows) - max_lines} más)")

    return "\n".join(lines)


def main():
    """Main function that orchestrates the scraping and notification process."""
    state = load_state()
    known = state.setdefault("events", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        if os.path.exists(STORAGE_FILE):
            context = browser.new_context(storage_state=STORAGE_FILE)
        else:
            context = browser.new_context()

        page = context.new_page()

        # 1) login automático si hace falta
        login_if_needed(page, context)

        # 2) dashboard html
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        dashboard_html = page.content()
        events = parse_events_from_dashboard(dashboard_html)

        # 3) detectar cambios básicos
        to_send: List[Event] = []
        for e in events:
            prev = known.get(e.event_id)
            if prev is None or prev.get("due_text") != e.due_text or prev.get("title") != e.title:
                to_send.append(e)

            known[e.event_id] = {**(prev or {}), "title": e.title, "due_text": e.due_text, "url": e.url}

        # 4) enriquecer todas para el resumen (materia + submitted)
        enriched_all: List[Event] = []
        for e in events:
            page.goto(e.url, wait_until="domcontentloaded")
            event_html = page.content()

            e.course_name, e.description = enrich_from_event_page(event_html)
            e.assignment_url = find_assignment_url(event_html)

            if e.assignment_url:
                page.goto(e.assignment_url, wait_until="domcontentloaded")
                assign_html = page.content()
                e.submitted, e.submission_status = assignment_is_submitted(assign_html)

            enriched_all.append(e)

        # 5) enviar SOLO lo nuevo/cambiado (detallado)
        to_send_ids = {x.event_id for x in to_send}
        for e in enriched_all:
            if e.event_id not in to_send_ids:
                continue

            badge = status_badge(e.submitted)
            msg = (
                f"🆕 <b>{esc(e.course_name)}</b>\n"
                f"{badge} <b>{esc(e.title)}</b>\n"
                f"⏳ {esc(e.due_text)}\n"
                f"🔗 {esc(e.assignment_url or e.url)}\n\n"
                f"{esc((e.description[:900] + '…') if len(e.description) > 900 else e.description)}"
            ).strip()

            tg_send(msg)

        # 6) resumen rápido (minimalista, sin links)
        tg_send(build_quick_summary(enriched_all))

        save_state(state)
        browser.close()


if __name__ == "__main__":
    main()