import time

from ues_bot.summary import parse_due_unix_from_event_url, remaining_parts_from_unix, status_badge
from ues_bot.utils import esc, short


def test_esc_basic():
    assert esc("<>&") == "&lt;&gt;&amp;"
    assert esc("normal") == "normal"
    assert esc("") == ""


def test_status_badge():
    assert status_badge(True) == "✅"
    assert status_badge(False) == "⚠️"
    assert status_badge(None) == "❔"


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
