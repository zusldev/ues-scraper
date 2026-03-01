import asyncio
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from ues_bot.scrape import safe_goto
from ues_bot.telegram_client import tg_send


def test_safe_goto_retries_on_failure():
    page = MagicMock()
    page.goto.side_effect = PWTimeout("Timeout")

    with pytest.raises(RuntimeError, match="No se pudo navegar"):
        safe_goto(page, "http://example.com", tries=3)

    assert page.goto.call_count == 3


def test_safe_goto_succeeds_on_second_try():
    page = MagicMock()
    page.goto.side_effect = [PWTimeout("Timeout"), None]

    safe_goto(page, "http://example.com", tries=3)
    assert page.goto.call_count == 2


def test_tg_send_dry_run_does_not_send():
    asyncio.run(tg_send("test", "token", "123", dry_run=True))
