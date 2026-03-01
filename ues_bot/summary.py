"""Builds batch change messages + sectioned summaries."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .models import Event
from .utils import esc, short


def parse_due_unix_from_event_url(url: str) -> Optional[int]:
    m = re.search(r"[?&]time=(\d+)", url or "")
    return int(m.group(1)) if m else None


def remaining_parts_from_unix(due_unix: int) -> tuple[int, str]:
    now = datetime.now(timezone.utc)
    due = datetime.fromtimestamp(due_unix, tz=timezone.utc)
    sec = int((due - now).total_seconds())
    if sec <= 0:
        return sec, "0m"
    mins = sec // 60
    if mins < 60:
        return sec, f"{mins}m"
    hrs = mins // 60
    rem_m = mins % 60
    if hrs < 24:
        return sec, f"{hrs}h {rem_m}m" if rem_m else f"{hrs}h"
    days = hrs // 24
    rem_h = hrs % 24
    return sec, f"{days}d {rem_h}h"


def status_badge(submitted: Optional[bool]) -> str:
    if submitted is True:
        return "✅"
    if submitted is False:
        return "⚠️"
    return "❔"


def due_unix(e: Event) -> Optional[int]:
    return parse_due_unix_from_event_url(e.url)


def urgency_bucket(e: Event, urgent_hours: int = 24) -> str:
    du = due_unix(e)
    if not du:
        return "sin_fecha"
    sec, _ = remaining_parts_from_unix(du)

    if e.submitted is True:
        return "enviados"
    if sec <= 0 and e.submitted is not True:
        return "vencidos"
    if sec <= urgent_hours * 3600 and e.submitted is not True:
        return "urgente"
    if sec <= 7 * 24 * 3600:
        return "proximos"
    return "futuro"


def build_sectioned_summary(
    events_all: list[Event],
    tz_name: str,
    urgent_hours: int = 24,
    max_lines_total: int = 18,
) -> str:
    rows = []
    for e in events_all:
        du = due_unix(e)
        if du:
            _, rem_txt = remaining_parts_from_unix(du)
            sort_key = du
            local_due_txt = ""
            if ZoneInfo is not None:
                local_due = datetime.fromtimestamp(du, tz=timezone.utc).astimezone(ZoneInfo(tz_name))
                local_due_txt = local_due.strftime("%Y-%m-%d %H:%M")
        else:
            rem_txt = e.due_text.strip() or "N/D"
            sort_key = 10**18
            local_due_txt = ""

        rows.append(
            {
                "sort": sort_key,
                "badge": status_badge(e.submitted),
                "title": short(e.title, 44),
                "course": short(e.course_name, 28),
                "remaining": rem_txt,
                "bucket": urgency_bucket(e, urgent_hours=urgent_hours),
                "due_local": local_due_txt,
            }
        )

    rows.sort(key=lambda r: r["sort"])

    buckets = {
        "urgente": [],
        "vencidos": [],
        "proximos": [],
        "futuro": [],
        "enviados": [],
        "sin_fecha": [],
    }
    for r in rows:
        buckets[r["bucket"]].append(r)

    now_local_txt = (
        datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
        if ZoneInfo is not None
        else datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    lines: list[str] = [f"📌 <b>Resumen</b> — {esc(now_local_txt)} ({esc(tz_name)})"]

    def add_group(title: str, key: str, limit: int) -> int:
        if not buckets[key]:
            return 0
        lines.append(f"\n<b>{esc(title)}</b>")
        count = 0
        for r in buckets[key][:limit]:
            extra = f" — <i>{esc(r['due_local'])}</i>" if r["due_local"] else ""
            lines.append(
                f"{r['badge']} {esc(r['title'])} — <i>{esc(r['course'])}</i> — <b>{esc(r['remaining'])}</b>{extra}"
            )
            count += 1
        remain = len(buckets[key]) - limit
        if remain > 0:
            lines.append(f"… (+{remain} más)")
        return count

    remaining_budget = max_lines_total
    for title, key in [
        (f"🔥 Urgente (≤{urgent_hours}h)", "urgente"),
        ("🕒 Vencidos (no enviados)", "vencidos"),
        ("📅 Próximos (≤7d)", "proximos"),
        ("✅ Enviados", "enviados"),
        ("⌛ Sin fecha detectada", "sin_fecha"),
        ("🗓️ Futuro", "futuro"),
    ]:
        if remaining_budget <= 0:
            break
        cap = min(6, remaining_budget) if key in ("urgente", "vencidos") else min(4, remaining_budget)
        used = add_group(title, key, cap)
        remaining_budget -= used

    return "\n".join(lines)


def build_changes_batch_message(changed: list[Event], max_items: int = 12) -> str:
    items = changed[:max_items]
    lines = [f"🆕 <b>Cambios detectados</b> ({len(changed)})"]
    for e in items:
        badge = status_badge(e.submitted)
        due = e.due_text.strip() or "N/D"
        link = e.assignment_url or e.url
        lines.append(
            f"{badge} <b>{esc(short(e.course_name, 40))}</b>\n"
            f"• {esc(short(e.title, 70))}\n"
            f"• ⏳ {esc(due)}\n"
            f"• 🔗 {esc(link)}"
        )
    if len(changed) > max_items:
        lines.append(f"\n… (+{len(changed) - max_items} más)")
    return "\n\n".join(lines).strip()


def build_weekly_calendar(events_all: list[Event], tz_name: str) -> str:
    from collections import defaultdict

    if ZoneInfo is not None:
        now = datetime.now(ZoneInfo(tz_name))
    else:
        now = datetime.now()

    day_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    grouped: dict[str, list[str]] = defaultdict(list)

    for event in events_all:
        due = due_unix(event)
        if due is None:
            continue

        if ZoneInfo is not None:
            due_dt = datetime.fromtimestamp(due, tz=timezone.utc).astimezone(ZoneInfo(tz_name))
        else:
            due_dt = datetime.fromtimestamp(due)

        day_diff = (due_dt.date() - now.date()).days
        if day_diff < 0 or day_diff > 7:
            continue

        day_key = f"{day_names[due_dt.weekday()]} {due_dt.strftime('%Y-%m-%d')}"
        _sec, rem_txt = remaining_parts_from_unix(due)
        grouped[day_key].append(
            f"{status_badge(event.submitted)} {esc(short(event.title, 50))}"
            f" — <i>{esc(short(event.course_name, 30))}</i> — {esc(rem_txt)}"
        )

    if not grouped:
        return "📅 <b>Calendario semanal</b>\n\nSin eventos en los próximos 7 días."

    lines = ["📅 <b>Calendario semanal</b>"]
    for day_key in sorted(grouped.keys()):
        lines.append(f"\n<b>{esc(day_key)}</b>")
        lines.extend(grouped[day_key])

    return "\n".join(lines)
