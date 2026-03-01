from ues_bot.state import increment_error_count, load_state, reset_error_count


def test_increment_error_count(tmp_path):
    sf = str(tmp_path / "state.json")
    state = load_state(sf)
    assert state.get("consecutive_errors", 0) == 0

    increment_error_count(state)
    assert state["consecutive_errors"] == 1

    increment_error_count(state)
    assert state["consecutive_errors"] == 2


def test_reset_error_count(tmp_path):
    sf = str(tmp_path / "state.json")
    state = load_state(sf)
    state["consecutive_errors"] = 5
    reset_error_count(state)
    assert state["consecutive_errors"] == 0
