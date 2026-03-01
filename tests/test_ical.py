import time

from ues_bot.ical import build_iphone_calendar_ics
from ues_bot.models import Event


def _make_event(event_id: str, title: str, due_offset_sec: int, submitted=False):
    due = int(time.time()) + due_offset_sec
    return Event(
        event_id=event_id,
        title=title,
        due_text="",
        url=f"https://x.test/event?time={due}",
        course_name="Materia Test",
        assignment_url="https://x.test/mod/assign/view.php?id=1",
        submitted=submitted,
        submission_status="Pendiente",
    )


def test_build_iphone_calendar_ics_includes_pending_events():
    events = [
        _make_event("1", "Tarea Algebra", due_offset_sec=3600, submitted=False),
        _make_event("2", "Tarea Enviada", due_offset_sec=7200, submitted=True),
    ]

    data, count = build_iphone_calendar_ics(events, tz_name="UTC", days_ahead=30)
    text = data.decode("utf-8")

    assert count == 1
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert "SUMMARY:[UES] Tarea Algebra" in text
    assert "Tarea Enviada" not in text


def test_build_iphone_calendar_ics_empty_when_no_valid_events():
    events = [_make_event("3", "Vencida", due_offset_sec=-100, submitted=False)]
    data, count = build_iphone_calendar_ics(events, tz_name="UTC", days_ahead=30)
    text = data.decode("utf-8")

    assert count == 0
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" not in text
