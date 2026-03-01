"""Generate iCalendar (.ics) exports compatible with iPhone Calendar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .models import Event
from .summary import due_unix


def _ics_escape(value: str) -> str:
    text = (value or "").replace("\\", "\\\\")
    text = text.replace(";", "\\;").replace(",", "\\,")
    return text.replace("\n", "\\n")


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_iphone_calendar_ics(
    events: list[Event],
    tz_name: str,
    days_ahead: int = 30,
) -> tuple[bytes, int]:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc + timedelta(days=days_ahead)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UES Telegram Bot//Calendar Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:UES Entregas",
    ]

    count = 0
    for event in events:
        if event.submitted is True:
            continue

        due = due_unix(event)
        if due is None:
            continue

        due_dt = datetime.fromtimestamp(due, tz=timezone.utc)
        if due_dt <= now_utc or due_dt > cutoff:
            continue

        start_dt = due_dt - timedelta(minutes=30)
        url = event.assignment_url or event.url
        course = event.course_name or "Sin materia"
        desc_parts = [
            f"Materia: {course}",
            f"Estado: {event.submission_status or 'Pendiente'}",
            f"Link: {url}",
        ]
        if event.description:
            desc_parts.append("")
            desc_parts.append(event.description)

        summary = f"[UES] {event.title}"
        description = "\n".join(desc_parts)

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ics_escape(event.event_id)}@ues-bot",
                f"DTSTAMP:{_fmt_utc(now_utc)}",
                f"DTSTART:{_fmt_utc(start_dt)}",
                f"DTEND:{_fmt_utc(due_dt)}",
                f"SUMMARY:{_ics_escape(summary)}",
                f"DESCRIPTION:{_ics_escape(description)}",
                f"URL:{_ics_escape(url)}",
                "END:VEVENT",
            ]
        )
        count += 1

    lines.append("END:VCALENDAR")
    content = "\r\n".join(lines) + "\r\n"

    return content.encode("utf-8"), count


def build_ics_filename(tz_name: str) -> str:
    if ZoneInfo is not None:
        local_now = datetime.now(ZoneInfo(tz_name))
    else:
        local_now = datetime.now()
    return f"ues_entregas_{local_now.strftime('%Y%m%d_%H%M')}.ics"
