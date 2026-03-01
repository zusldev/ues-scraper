"""Escalated deadline reminders for pending assignments."""

from __future__ import annotations

from .models import Event
from .summary import due_unix, remaining_parts_from_unix

REMINDER_THRESHOLDS: list[tuple[int, str]] = [
    (1 * 3600, "1h"),
    (6 * 3600, "6h"),
    (24 * 3600, "24h"),
]


def get_pending_reminders(
    events: list[Event],
    sent_reminders: dict[str, list[str]],
) -> list[tuple[Event, str]]:
    pending: list[tuple[Event, str]] = []

    for event in events:
        if event.submitted is True:
            continue

        due = due_unix(event)
        if due is None:
            continue

        sec, _ = remaining_parts_from_unix(due)
        if sec <= 0:
            continue

        already_sent = set(sent_reminders.get(event.event_id, []))
        for threshold_sec, label in REMINDER_THRESHOLDS:
            if sec <= threshold_sec and label not in already_sent:
                pending.append((event, label))
                break

    return pending
