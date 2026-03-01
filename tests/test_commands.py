import asyncio
import time

from ues_bot.commands import SCRAPE_LOCK_KEY, cmd_dormir, cmd_help, cmd_intervalo, run_scrape_now
from ues_bot.config import Settings
from ues_bot.state import load_state


class _FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class _FakeChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class _FakeUpdate:
    def __init__(self, chat_id: int):
        self.effective_chat = _FakeChat(chat_id)
        self.effective_message = _FakeMessage()


class _FakeJobQueue:
    def get_jobs_by_name(self, _name):
        return []

    def run_repeating(self, _cb, interval, first, name):
        self.last = (interval, first, name)


class _FakeApp:
    def __init__(self, settings: Settings):
        self.bot_data = {
            "settings": settings,
            "run_scrape_args": {},
            "scrape_job_callback": lambda _ctx: None,
            SCRAPE_LOCK_KEY: asyncio.Lock(),
        }
        self.job_queue = _FakeJobQueue()


class _FakeContext:
    def __init__(self, app, args=None):
        self.application = app
        self.args = args or []


def test_help_restricted_to_chat_id():
    settings = Settings(tg_chat_id="123")
    app = _FakeApp(settings)

    update_allowed = _FakeUpdate(123)
    context = _FakeContext(app, [])
    asyncio.run(cmd_help(update_allowed, context))
    assert len(update_allowed.effective_message.replies) == 1

    update_blocked = _FakeUpdate(999)
    asyncio.run(cmd_help(update_blocked, context))
    assert len(update_blocked.effective_message.replies) == 0


def test_dormir_default_8_hours(tmp_path):
    settings = Settings(tg_chat_id="123", state_file=str(tmp_path / "state.json"), tz_name="UTC")
    app = _FakeApp(settings)
    update = _FakeUpdate(123)
    context = _FakeContext(app, [])

    before = int(time.time())
    asyncio.run(cmd_dormir(update, context))
    after = int(time.time())

    state = load_state(settings.state_file)
    sleep_until = state["sleep_until"]
    assert before + 8 * 3600 <= sleep_until <= after + 8 * 3600 + 2
    assert "8h" in update.effective_message.replies[0][0]


def test_intervalo_updates_settings(monkeypatch):
    settings = Settings(tg_chat_id="123")
    app = _FakeApp(settings)
    update = _FakeUpdate(123)
    context = _FakeContext(app, ["30"])

    called = {}

    def _fake_reschedule(_app, minutes):
        called["minutes"] = minutes

    monkeypatch.setattr("ues_bot.commands._reschedule_interval_job", _fake_reschedule)

    asyncio.run(cmd_intervalo(update, context))

    assert settings.scrape_interval_min == 30
    assert called["minutes"] == 30
    assert "30" in update.effective_message.replies[0][0]


def test_run_scrape_now_fails_fast_when_scrape_in_progress():
    settings = Settings(tg_chat_id="123", scrape_lock_wait_sec=0)
    app = _FakeApp(settings)
    context = _FakeContext(app, [])

    lock = app.bot_data[SCRAPE_LOCK_KEY]

    async def _run_test():
        await lock.acquire()
        try:
            try:
                await run_scrape_now(context)
            except RuntimeError as ex:
                assert "curso" in str(ex)
                assert "scraping" in str(ex).lower()
            else:
                raise AssertionError("Expected run_scrape_now to fail while lock is busy")
        finally:
            lock.release()

    asyncio.run(_run_test())


def test_scrape_cooldown():
    import ues_bot.commands as commands

    commands._last_scrape_command_ts = 0.0
    can_run, _wait = commands._check_cooldown()
    assert can_run is True

    commands._mark_scrape_used()
    can_run, wait = commands._check_cooldown()
    assert can_run is False
    assert wait > 0

    commands._last_scrape_command_ts = 0.0
