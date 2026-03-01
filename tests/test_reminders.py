import time

from ues_bot.models import Event
from ues_bot.reminders import get_pending_reminders


def _make_event(due_offset_sec: int, submitted=False):
    ts = int(time.time()) + due_offset_sec
    return Event(
        event_id="ev1",
        title="Tarea",
        due_text="",
        url=f"http://x.com?time={ts}",
        submitted=submitted,
    )


def test_no_reminder_for_submitted():
    event = _make_event(due_offset_sec=3600, submitted=True)
    reminders = get_pending_reminders([event], sent_reminders={})
    assert reminders == []


def test_reminder_at_24h():
    event = _make_event(due_offset_sec=23 * 3600)
    reminders = get_pending_reminders([event], sent_reminders={})
    assert len(reminders) == 1
    assert reminders[0][1] == "24h"


def test_no_duplicate_reminder():
    event = _make_event(due_offset_sec=23 * 3600)
    sent = {"ev1": ["24h"]}
    reminders = get_pending_reminders([event], sent_reminders=sent)
    assert reminders == []


def test_reminder_at_1h():
    event = _make_event(due_offset_sec=50 * 60)
    reminders = get_pending_reminders([event], sent_reminders={})
    assert any(reminder[1] == "1h" for reminder in reminders)
