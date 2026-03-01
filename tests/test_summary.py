import time

from ues_bot.models import Event
from ues_bot.summary import build_changes_batch_message, build_sectioned_summary, urgency_bucket


def _make_event(
    event_id="1", title="Test Event", due_offset_sec=3600, submitted=None, course_name="Materia Test"
):
    ts = int(time.time()) + due_offset_sec
    return Event(
        event_id=event_id,
        title=title,
        due_text="Tomorrow",
        url=f"http://example.com?time={ts}",
        course_name=course_name,
        submitted=submitted,
    )


def test_urgency_bucket_urgent():
    e = _make_event(due_offset_sec=3600, submitted=False)
    assert urgency_bucket(e, urgent_hours=24) == "urgente"


def test_urgency_bucket_overdue():
    e = _make_event(due_offset_sec=-3600, submitted=False)
    assert urgency_bucket(e, urgent_hours=24) == "vencidos"


def test_urgency_bucket_submitted():
    e = _make_event(due_offset_sec=3600, submitted=True)
    assert urgency_bucket(e, urgent_hours=24) == "enviados"


def test_urgency_bucket_no_date():
    e = Event(event_id="1", title="T", due_text="", url="http://x.com")
    assert urgency_bucket(e) == "sin_fecha"


def test_urgency_bucket_future():
    e = _make_event(due_offset_sec=30 * 24 * 3600, submitted=False)
    assert urgency_bucket(e, urgent_hours=24) == "futuro"


def test_build_sectioned_summary_not_empty():
    events = [_make_event(submitted=False)]
    result = build_sectioned_summary(events, tz_name="UTC", urgent_hours=24)
    assert "Resumen" in result
    assert "Test Event" in result


def test_build_changes_batch_message_empty():
    result = build_changes_batch_message([], max_items=5)
    assert "Cambios detectados" in result
    assert "(0)" in result


def test_build_changes_batch_message_truncates():
    events = [_make_event(event_id=str(i)) for i in range(20)]
    result = build_changes_batch_message(events, max_items=5)
    assert "+15" in result
