import asyncio
from types import SimpleNamespace

import main
from telegram.error import NetworkError
from ues_bot.commands import ScrapeAlreadyRunningError
from ues_bot.config import Settings
from ues_bot.state import load_state, save_state


class _FakeApplication:
    def __init__(self, settings: Settings):
        self.bot_data = {"settings": settings}


class _FakeContext:
    def __init__(self, settings: Settings):
        self.application = _FakeApplication(settings)
        self.bot = object()


def test_periodic_scrape_job_does_not_count_lock_collision(tmp_path, monkeypatch):
    settings = Settings(
        tg_bot_token="token",
        tg_chat_id="123",
        state_file=str(tmp_path / "state.json"),
    )
    state = load_state(settings.state_file)
    state["consecutive_errors"] = 2
    save_state(settings.state_file, state)

    async def _fake_run_scrape_now(_context, wait_for_lock_sec=0):
        raise ScrapeAlreadyRunningError("Ya hay un scraping en curso")

    sent_messages = []

    async def _fake_tg_send(*args, **kwargs):
        sent_messages.append((args, kwargs))

    monkeypatch.setattr(main, "run_scrape_now", _fake_run_scrape_now)
    monkeypatch.setattr(main, "tg_send", _fake_tg_send)

    context = _FakeContext(settings)
    asyncio.run(main.periodic_scrape_job(context))

    updated_state = load_state(settings.state_file)
    assert updated_state["consecutive_errors"] == 2
    assert updated_state["last_error"] is None
    assert updated_state["metrics"]["network_transient_errors"] == 0
    assert updated_state["metrics"]["functional_errors"] == 0
    assert sent_messages == []


def test_global_error_handler_marks_transient_network_error_and_skips_alert(tmp_path, monkeypatch):
    settings = Settings(
        tg_bot_token="token",
        tg_chat_id="123",
        state_file=str(tmp_path / "state.json"),
        quiet_start="",
        quiet_end="",
    )

    sent_messages = []

    async def _fake_tg_send(*args, **kwargs):
        sent_messages.append((args, kwargs))

    monkeypatch.setattr(main, "tg_send", _fake_tg_send)

    context = SimpleNamespace(
        application=_FakeApplication(settings),
        bot=object(),
        error=NetworkError("httpx.ConnectError: [Errno 11001] getaddrinfo failed"),
    )

    asyncio.run(main.global_error_handler(object(), context))

    updated_state = load_state(settings.state_file)
    assert updated_state["last_error_kind"] == "network_transient"
    assert "getaddrinfo failed" in (updated_state["last_error"] or "")
    assert updated_state["metrics"]["network_transient_errors"] == 1
    assert updated_state["metrics"]["functional_errors"] == 0
    assert sent_messages == []


def test_periodic_scrape_job_marks_functional_error_metric(tmp_path, monkeypatch):
    settings = Settings(
        tg_bot_token="token",
        tg_chat_id="123",
        state_file=str(tmp_path / "state.json"),
        quiet_start="",
        quiet_end="",
    )

    async def _fake_run_scrape_now(_context, wait_for_lock_sec=0):
        raise RuntimeError("fallo scrape")

    async def _fake_tg_send(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "run_scrape_now", _fake_run_scrape_now)
    monkeypatch.setattr(main, "tg_send", _fake_tg_send)

    context = _FakeContext(settings)
    asyncio.run(main.periodic_scrape_job(context))

    updated_state = load_state(settings.state_file)
    assert updated_state["last_error_kind"] == "functional"
    assert updated_state["metrics"]["functional_errors"] == 1
    assert updated_state["metrics"]["network_transient_errors"] == 0
