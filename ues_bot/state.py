"""JSON state storage for seen events."""

from __future__ import annotations

import os
import json
import time
from typing import Any, Dict


def _with_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("events", {})
    state.setdefault("sleep_until", None)
    state.setdefault("quiet_start", None)
    state.setdefault("quiet_end", None)
    state.setdefault("last_run", None)
    state.setdefault("last_error", None)
    state.setdefault("consecutive_errors", 0)
    state.setdefault("sent_reminders", {})
    return state


def load_state(state_file: str) -> Dict:
    if not os.path.exists(state_file):
        return _with_defaults({"events": {}})
    with open(state_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return _with_defaults({"events": {}})
    return _with_defaults(raw)


def save_state(state_file: str, state: Dict) -> None:
    _with_defaults(state)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def set_sleep(state: Dict[str, Any], hours: float) -> int:
    until = int(time.time() + max(hours, 0) * 3600)
    state["sleep_until"] = until
    return until


def is_sleeping(state: Dict[str, Any]) -> bool:
    sleep_until = state.get("sleep_until")
    if not isinstance(sleep_until, (int, float)):
        return False
    now_ts = int(time.time())
    if now_ts >= int(sleep_until):
        state["sleep_until"] = None
        return False
    return True


def cancel_sleep(state: Dict[str, Any]) -> None:
    state["sleep_until"] = None


def update_quiet_hours(state: Dict[str, Any], start: str, end: str) -> None:
    state["quiet_start"] = start
    state["quiet_end"] = end


def increment_error_count(state: Dict[str, Any]) -> int:
    count = int(state.get("consecutive_errors", 0)) + 1
    state["consecutive_errors"] = count
    return count


def reset_error_count(state: Dict[str, Any]) -> None:
    state["consecutive_errors"] = 0
