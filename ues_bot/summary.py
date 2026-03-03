"""Builds batch change messages + sectioned summaries."""

from __future__ import annotations

import random
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
    """Extract a unix timestamp from a ``?time=`` query parameter."""
    m = re.search(r"[?&]time=(\d+)", url or "")
    return int(m.group(1)) if m else None


# Spanish month names → month number (for parsing due dates from aria-label).
_ES_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Pattern: "8 de marzo de 2026, 23:59"
_ES_DATE_RE = re.compile(
    r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4}),?\s+(\d{1,2}):(\d{2})"
)


def parse_due_unix_from_text(text: str) -> Optional[int]:
    """Try to extract a unix timestamp from a Spanish due-date string."""
    m = _ES_DATE_RE.search(text or "")
    if not m:
        return None
    day, month_name, year, hour, minute = m.groups()
    month = _ES_MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        dt = datetime(int(year), month, int(day), int(hour), int(minute), tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, OverflowError):
        return None


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
    """Submission badge for user-facing messages.

    ✅ submitted
    📝 pending / not submitted
    ⚠️ unknown (verification issue)
    """
    if submitted is True:
        return "✅"
    if submitted is False:
        return "📝"
    return "⚠️"


def grading_badge(grading_status: str) -> str:
    """Return an emoji for the grading status."""
    g = (grading_status or "").lower()
    if not g:
        return ""
    if "calificado" in g and "no calificado" not in g:
        return "📝"
    if "graded" in g and "not graded" not in g:
        return "📝"
    return "⏳"


def due_unix(e: Event) -> Optional[int]:
    """Best-effort extraction of due-date as a unix timestamp."""
    ts = parse_due_unix_from_event_url(e.url)
    if ts:
        return ts
    # Timeline events may carry the date in due_text from aria-label
    return parse_due_unix_from_text(e.due_text)


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


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    """Render a text progress bar like ████░░░░░░ 4/10."""
    if total <= 0:
        return "░" * width + " 0/0"
    filled = round(done / total * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {done}/{total}"


_MORNING_GREETINGS = [
    "Buenos días ☀️",
    "¡Buen día! 🌅",
    "¡Arriba! ☀️",
    "¡A darle! 💪",
]

_EVENING_GREETINGS = [
    "Buenas noches 🌙",
    "Preview nocturno 🌆",
    "Antes de dormir 🌙",
]

_TIPS = [
    "💡 Tip: Usa /proxima para ver tu entrega más cercana.",
    "💡 Tip: /materia Redes filtra solo esa materia.",
    "💡 Tip: /iphonecal exporta tus entregas al calendario del iPhone.",
    "💡 Tip: /dormir 3 silencia el bot por 3 horas.",
    "💡 Tip: /detalle 1 muestra detalles del primer evento.",
    "💡 Tip: /notificar smart activa notificaciones inteligentes.",
    "💡 Tip: /calendario muestra tu semana de un vistazo.",
]


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
    """Build a friendly notification for detected changes."""
    if not changed:
        return ""

    items = changed[:max_items]

    # Categorize changes
    new_tasks = [e for e in items if e.submitted is None or e.submitted is False]
    graded = [e for e in items if e.grading_status and "calificado" in e.grading_status.lower()
              and "no calificado" not in e.grading_status.lower()]

    if len(items) == 1:
        e = items[0]
        badge = status_badge(e.submitted)
        link = e.assignment_url or e.url
        header = "📬 <b>Novedad detectada</b>"
        lines = [
            header,
            f"",
            f"{badge} <b>{esc(short(e.title, 60))}</b>",
            f"📚 {esc(short(e.course_name, 40))}",
            f"⏳ {esc(e.due_text.strip() or 'N/D')}",
        ]
        if e.grading_status:
            g_badge = grading_badge(e.grading_status)
            lines.append(f"📝 {esc(e.grading_status)} {g_badge}")
        lines.append(f"🔗 {esc(link)}")
        return "\n".join(lines)

    header = f"📬 <b>Novedades detectadas</b> ({len(changed)})"
    lines = [header]
    for e in items:
        badge = status_badge(e.submitted)
        g_badge = grading_badge(e.grading_status)
        g_txt = f" {g_badge}" if g_badge else ""
        due = e.due_text.strip() or "N/D"
        link = e.assignment_url or e.url
        lines.append(
            f"\n{badge}{g_txt} <b>{esc(short(e.course_name, 35))}</b>"
            f"\n   {esc(short(e.title, 60))}"
            f"\n   ⏳ {esc(due)} · 🔗 {esc(short(link, 50))}"
        )
    if len(changed) > max_items:
        lines.append(f"\n… y {len(changed) - max_items} más")
    return "\n".join(lines)


def build_daily_digest(
    events_all: list[Event],
    tz_name: str,
    urgent_hours: int = 24,
) -> str:
    """Build a friendly morning digest with greeting, progress bars, and tips."""
    if ZoneInfo is not None:
        now = datetime.now(ZoneInfo(tz_name))
    else:
        now = datetime.now()

    overdue: list[str] = []
    today_items: list[str] = []
    tomorrow_items: list[str] = []

    # Progress metrics
    total_events = 0
    submitted_count = 0
    today_total = 0
    today_submitted = 0

    for e in events_all:
        total_events += 1
        if e.submitted is True:
            submitted_count += 1

        du = due_unix(e)
        if du is None:
            continue
        if ZoneInfo is not None:
            due_dt = datetime.fromtimestamp(du, tz=timezone.utc).astimezone(ZoneInfo(tz_name))
        else:
            due_dt = datetime.fromtimestamp(du)
        day_diff = (due_dt.date() - now.date()).days
        _sec, rem = remaining_parts_from_unix(du)

        if day_diff == 0:
            today_total += 1
            if e.submitted is True:
                today_submitted += 1

        time_str = due_dt.strftime("%H:%M")
        line = (
            f"{status_badge(e.submitted)} {esc(short(e.title, 45))}"
            f"\n   <i>{esc(short(e.course_name, 30))}</i> · 🕐 {esc(time_str)} · <b>{esc(rem)}</b>"
        )

        if _sec <= 0 and e.submitted is not True:
            overdue.append(line)
        elif day_diff == 0:
            today_items.append(line)
        elif day_diff == 1:
            tomorrow_items.append(line)

    greeting = random.choice(_MORNING_GREETINGS)
    date_str = now.strftime("%A %d de %B").capitalize()
    progress_today = _progress_bar(today_submitted, today_total)
    progress_global = _progress_bar(submitted_count, total_events)

    lines = [
        f"{greeting}",
        f"📅 <b>{esc(date_str)}</b>",
        f"",
        f"📊 Progreso de hoy: {esc(progress_today)}",
    ]

    # Add global progress only when it differs from today's scope.
    if total_events != today_total:
        lines.append(f"📈 Progreso general: {esc(progress_global)}")

    if not overdue and not today_items and not tomorrow_items:
        lines.append("")
        lines.append("🎉 <b>¡Día libre!</b> No tienes entregas pendientes para hoy ni mañana.")
        lines.append("")
        lines.append(random.choice(_TIPS))
        return "\n".join(lines)

    if overdue:
        lines.append(f"\n🔴 <b>Vencidas sin entregar ({len(overdue)})</b>")
        for item in overdue[:6]:
            lines.append(item)
        if len(overdue) > 6:
            lines.append(f"   … y {len(overdue) - 6} más")

    if today_items:
        lines.append(f"\n🟡 <b>Para hoy ({len(today_items)})</b>")
        for item in today_items[:6]:
            lines.append(item)
        if len(today_items) > 6:
            lines.append(f"   … y {len(today_items) - 6} más")

    if tomorrow_items:
        lines.append(f"\n🔵 <b>Mañana ({len(tomorrow_items)})</b>")
        for item in tomorrow_items[:4]:
            lines.append(item)
        if len(tomorrow_items) > 4:
            lines.append(f"   … y {len(tomorrow_items) - 4} más")

    lines.append("")
    lines.append(random.choice(_TIPS))
    return "\n".join(lines)


def build_evening_preview(
    events_all: list[Event],
    tz_name: str,
) -> str:
    """Build an evening preview: what's due tomorrow + overdue reminders."""
    if ZoneInfo is not None:
        now = datetime.now(ZoneInfo(tz_name))
    else:
        now = datetime.now()

    overdue_pending: list[str] = []
    tomorrow_items: list[str] = []

    for e in events_all:
        du = due_unix(e)
        if du is None:
            continue
        if ZoneInfo is not None:
            due_dt = datetime.fromtimestamp(du, tz=timezone.utc).astimezone(ZoneInfo(tz_name))
        else:
            due_dt = datetime.fromtimestamp(du)
        day_diff = (due_dt.date() - now.date()).days
        _sec, rem = remaining_parts_from_unix(du)

        time_str = due_dt.strftime("%H:%M")

        if _sec <= 0 and e.submitted is not True:
            overdue_pending.append(
                f"❌ {esc(short(e.title, 45))}"
                f"\n   <i>{esc(short(e.course_name, 30))}</i>"
            )
        elif day_diff == 1 and e.submitted is not True:
            tomorrow_items.append(
                f"📌 {esc(short(e.title, 45))}"
                f"\n   <i>{esc(short(e.course_name, 30))}</i> · 🕐 {esc(time_str)}"
            )

    greeting = random.choice(_EVENING_GREETINGS)

    if not overdue_pending and not tomorrow_items:
        return (
            f"{greeting}\n\n"
            "✨ <b>¡Mañana libre!</b> No tienes entregas pendientes.\n"
            "Descansa bien 😴"
        )

    lines = [greeting, ""]

    if tomorrow_items:
        lines.append(f"📋 <b>Mañana tienes {len(tomorrow_items)} entrega{'s' if len(tomorrow_items) > 1 else ''}</b>")
        for item in tomorrow_items[:6]:
            lines.append(item)
        if len(tomorrow_items) > 6:
            lines.append(f"   … y {len(tomorrow_items) - 6} más")

    if overdue_pending:
        lines.append(f"\n⚠️ <b>Pendientes vencidas ({len(overdue_pending)})</b>")
        for item in overdue_pending[:4]:
            lines.append(item)
        if len(overdue_pending) > 4:
            lines.append(f"   … y {len(overdue_pending) - 4} más")

    if tomorrow_items:
        lines.append("")
        lines.append("💡 Prepara lo que puedas esta noche para ir con ventaja 🚀")

    return "\n".join(lines)


def build_smart_notification(
    changed: list[Event],
    events_all: list[Event],
    reminders: list[tuple[Event, str]],
) -> str:
    """Build a compact periodic notification for smart mode.

    Only called when there's something worth telling the user:
    new changes, or upcoming reminders.  Returns empty string if nothing.
    """
    parts: list[str] = []

    # Changes
    if changed:
        parts.append(build_changes_batch_message(changed, max_items=6))

    # No duplicating reminders here — they're sent separately.
    # But if there's nothing else, add a tiny summary nudge.
    if not parts and not reminders:
        return ""

    return "\n\n".join(parts)


def build_course_stats(events_all: list[Event]) -> str:
    """Build per-course statistics: submitted, pending, overdue counts."""
    from collections import Counter, defaultdict

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"submitted": 0, "pending": 0, "overdue": 0, "total": 0})

    for e in events_all:
        course = e.course_name or "Sin materia"
        stats[course]["total"] += 1
        if e.submitted is True:
            stats[course]["submitted"] += 1
        else:
            du = due_unix(e)
            if du:
                sec, _ = remaining_parts_from_unix(du)
                if sec <= 0:
                    stats[course]["overdue"] += 1
                else:
                    stats[course]["pending"] += 1
            else:
                stats[course]["pending"] += 1

    if not stats:
        return "📊 <b>Estadísticas por materia</b>\n\nSin eventos registrados."

    lines = ["📊 <b>Estadísticas por materia</b>"]
    for course in sorted(stats.keys()):
        s = stats[course]
        lines.append(
            f"\n<b>{esc(short(course, 40))}</b>"
            f"\n  ✅ {s['submitted']}  ❌ {s['pending']}  🔴 {s['overdue']}  📋 {s['total']}"
        )
    return "\n".join(lines)


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
