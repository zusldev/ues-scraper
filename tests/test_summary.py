import time

from ues_bot.models import Event
from ues_bot.summary import (
    _progress_bar,
    build_changes_batch_message,
    build_course_stats,
    build_daily_digest,
    build_evening_preview,
    build_sectioned_summary,
    urgency_bucket,
)


def _make_event(
    event_id="1", title="Test Event", due_offset_sec=3600, submitted=None,
    course_name="Materia Test", grading_status="",
):
    ts = int(time.time()) + due_offset_sec
    return Event(
        event_id=event_id,
        title=title,
        due_text="Tomorrow",
        url=f"http://example.com?time={ts}",
        course_name=course_name,
        submitted=submitted,
        grading_status=grading_status,
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
    assert result == ""


def test_build_changes_batch_message_truncates():
    events = [_make_event(event_id=str(i)) for i in range(20)]
    result = build_changes_batch_message(events, max_items=5)
    assert "y 15 más" in result


def test_build_changes_single_event():
    events = [_make_event(submitted=False, grading_status="No calificado")]
    result = build_changes_batch_message(events, max_items=5)
    assert "Novedad detectada" in result
    assert "No calificado" in result


def test_build_changes_includes_grading():
    events = [_make_event(submitted=True, grading_status="No calificado")]
    result = build_changes_batch_message(events, max_items=5)
    assert "No calificado" in result


def test_build_daily_digest_empty():
    result = build_daily_digest([], tz_name="UTC")
    assert "libre" in result.lower() or "sin entregas" in result.lower()


def test_build_daily_digest_with_overdue():
    events = [_make_event(due_offset_sec=-3600, submitted=False, title="Tarea Vencida")]
    result = build_daily_digest(events, tz_name="UTC")
    assert "Vencidas sin entregar" in result
    assert "Tarea Vencida" in result


def test_build_daily_digest_with_today():
    events = [_make_event(due_offset_sec=3600, submitted=False, title="Tarea Hoy")]
    result = build_daily_digest(events, tz_name="UTC")
    assert "Hoy" in result
    assert "Tarea Hoy" in result


def test_build_course_stats_empty():
    result = build_course_stats([])
    assert "Sin eventos" in result


def test_build_course_stats_counts():
    events = [
        _make_event(event_id="1", course_name="Redes", submitted=True),
        _make_event(event_id="2", course_name="Redes", submitted=False),
        _make_event(event_id="3", course_name="Redes", submitted=False, due_offset_sec=-3600),
        _make_event(event_id="4", course_name="Algebra", submitted=True),
    ]
    result = build_course_stats(events)
    assert "Redes" in result
    assert "Algebra" in result
    # Redes: 1 submitted, 1 pending, 1 overdue, 3 total
    assert "✅ 1" in result


def test_build_evening_preview_empty():
    result = build_evening_preview([], tz_name="UTC")
    assert "libre" in result.lower() or "pendientes" in result.lower()


def test_build_evening_preview_with_tomorrow():
    # Create event due tomorrow (26h from now)
    events = [_make_event(due_offset_sec=26 * 3600, submitted=False, title="Tarea Mañana", course_name="Redes")]
    result = build_evening_preview(events, tz_name="UTC")
    assert "Tarea Mañana" in result


def test_build_evening_preview_with_overdue():
    events = [_make_event(due_offset_sec=-3600, submitted=False, title="Tarea Vencida")]
    result = build_evening_preview(events, tz_name="UTC")
    assert "Pendientes vencidas" in result


def test_progress_bar_full():
    bar = _progress_bar(10, 10)
    assert "10/10" in bar
    assert "█" in bar
    assert "░" not in bar


def test_progress_bar_empty():
    bar = _progress_bar(0, 10)
    assert "0/10" in bar
    assert "░" in bar


def test_progress_bar_zero_total():
    bar = _progress_bar(0, 0)
    assert "0/0" in bar

