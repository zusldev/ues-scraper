import pytest
from ues_scr import esc, status_badge, short, remaining_text_from_unix, parse_due_unix_from_event_url


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
    import time
    # 5 minutos
    ts = int(time.time()) + 5 * 60
    out = remaining_text_from_unix(ts)
    assert "m" in out
    # vencido
    ts = int(time.time()) - 10
    assert remaining_text_from_unix(ts) == "0m"


def test_parse_due_unix_from_event_url():
    url = "http://x.com/foo?time=12345"
    assert parse_due_unix_from_event_url(url) == 12345
    url = "?other=99"
    assert parse_due_unix_from_event_url(url) is None
