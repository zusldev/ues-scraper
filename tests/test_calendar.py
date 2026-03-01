import time

from ues_bot.models import Event
from ues_bot.summary import build_weekly_calendar


def _make_event(title: str, due_offset_sec: int, submitted=False):
    ts = int(time.time()) + due_offset_sec
    return Event(
        event_id=str(hash((title, due_offset_sec))),
        title=title,
        due_text="",
        url=f"http://x.com?time={ts}",
        course_name="Materia",
        submitted=submitted,
    )


def test_weekly_calendar_groups_by_day():
    events = [
        _make_event("Hoy", due_offset_sec=3600),
        _make_event("Manana", due_offset_sec=24 * 3600 + 3600),
    ]
    result = build_weekly_calendar(events, tz_name="UTC")
    assert "Hoy" in result
    assert "Manana" in result
    assert "Calendario" in result


def test_weekly_calendar_empty():
    result = build_weekly_calendar([], tz_name="UTC")
    assert "Sin eventos" in result
