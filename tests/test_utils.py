import time

from ues_bot.summary import (
    grading_badge,
    parse_due_unix_from_event_url,
    parse_due_unix_from_text,
    remaining_parts_from_unix,
    status_badge,
)
from ues_bot.utils import esc, short


def test_esc_basic():
    assert esc("<>&") == "&lt;&gt;&amp;"
    assert esc("normal") == "normal"
    assert esc("") == ""


def test_status_badge():
    assert status_badge(True) == "✅"
    assert status_badge(False) == "📝"
    assert status_badge(None) == "⚠️"


def test_grading_badge():
    assert grading_badge("Calificado") == "📝"
    assert grading_badge("No calificado") == "⏳"
    assert grading_badge("Graded") == "📝"
    assert grading_badge("Not graded") == "⏳"
    assert grading_badge("") == ""
    assert grading_badge("Algún estado") == "⏳"


def test_short():
    assert short("Hello World", 5) == "Hell…"
    assert short("abc", 5) == "abc"
    assert short("", 7) == ""


def test_remaining_text_from_unix():
    ts = int(time.time()) + 5 * 60
    _, out = remaining_parts_from_unix(ts)
    assert "m" in out

    ts = int(time.time()) - 10
    _, out = remaining_parts_from_unix(ts)
    assert out == "0m"


def test_parse_due_unix_from_event_url():
    url = "http://x.com/foo?time=12345"
    assert parse_due_unix_from_event_url(url) == 12345

    url = "?other=99"
    assert parse_due_unix_from_event_url(url) is None


def test_parse_due_unix_from_text():
    # Standard Spanish date format from aria-label
    text = "8 de marzo de 2026, 23:59"
    ts = parse_due_unix_from_text(text)
    assert ts is not None
    assert ts > 0

    # Embedded in longer text
    text2 = "Act 13: Resumen... está pendiente para 8 de marzo de 2026, 23:59"
    ts2 = parse_due_unix_from_text(text2)
    assert ts2 == ts

    # Invalid
    assert parse_due_unix_from_text("Hoy, 23:21") is None
    assert parse_due_unix_from_text("") is None
    assert parse_due_unix_from_text(None) is None

