import json
import time

import pytest

from ues_bot.state import cancel_sleep, is_sleeping, load_state, save_state, set_sleep, update_quiet_hours


def test_load_state_creates_defaults(tmp_path):
    sf = str(tmp_path / "state.json")
    state = load_state(sf)
    assert "events" in state
    assert state["sleep_until"] is None
    assert state["last_run"] is None


def test_save_and_load_roundtrip(tmp_path):
    sf = str(tmp_path / "state.json")
    state = load_state(sf)
    state["events"]["ev1"] = {"title": "Test", "due_text": "Tomorrow"}
    save_state(sf, state)

    loaded = load_state(sf)
    assert loaded["events"]["ev1"]["title"] == "Test"


def test_set_sleep_and_is_sleeping(tmp_path):
    sf = str(tmp_path / "state.json")
    state = load_state(sf)
    set_sleep(state, 2.0)
    assert is_sleeping(state) is True


def test_sleep_expires():
    state = {"sleep_until": int(time.time()) - 10}
    assert is_sleeping(state) is False
    assert state["sleep_until"] is None


def test_cancel_sleep():
    state = {"sleep_until": int(time.time()) + 9999}
    cancel_sleep(state)
    assert state["sleep_until"] is None
    assert is_sleeping(state) is False


def test_update_quiet_hours():
    state = {}
    update_quiet_hours(state, "22:00", "06:00")
    assert state["quiet_start"] == "22:00"
    assert state["quiet_end"] == "06:00"


def test_load_state_handles_corrupt_file(tmp_path):
    sf = str(tmp_path / "state.json")
    with open(sf, "w", encoding="utf-8") as f:
        f.write("not json")
    with pytest.raises(json.JSONDecodeError):
        load_state(sf)
