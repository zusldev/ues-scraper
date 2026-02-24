"""Configuration loading (env, defaults) for UES -> Telegram bot."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE = "https://ueslearning.ues.mx"
DEFAULT_DASHBOARD_PATH = "/my/"
DEFAULT_STATE_FILE = "seen_events.json"
DEFAULT_STORAGE_FILE = "storage_state.json"
DEFAULT_LOG_FILE = "ues_to_telegram.log"
DEFAULT_TZ = "America/Mazatlan"


@dataclass(frozen=True)
class Settings:
    # Core URLs/files
    base: str = DEFAULT_BASE
    dashboard_url: str = f"{DEFAULT_BASE}{DEFAULT_DASHBOARD_PATH}"
    state_file: str = DEFAULT_STATE_FILE
    storage_file: str = DEFAULT_STORAGE_FILE
    log_file: str = DEFAULT_LOG_FILE

    # Telegram
    tg_bot_token: str = ""
    tg_chat_id: str = ""

    # UES
    ues_user: str = ""
    ues_pass: str = ""

    # Behavior
    tz_name: str = DEFAULT_TZ
    quiet_start: str = "00:00"
    quiet_end: str = "07:00"
    urgent_hours: int = 24
    max_change_items: int = 12
    max_summary_lines: int = 18

    # Runtime toggles
    headful: bool = False
    verbose: bool = False
    dry_run: bool = False
    only_changes: bool = True
    notify_unchanged: bool = False


def from_env() -> Settings:
    """Build Settings from environment variables (.env supported via main.py)."""
    base = os.getenv("UES_BASE", DEFAULT_BASE).rstrip("/")
    dashboard_url = os.getenv("UES_DASHBOARD_URL", f"{base}{DEFAULT_DASHBOARD_PATH}")
    return Settings(
        base=base,
        dashboard_url=dashboard_url,
        state_file=os.getenv("UES_STATE_FILE", DEFAULT_STATE_FILE),
        storage_file=os.getenv("UES_STORAGE_FILE", DEFAULT_STORAGE_FILE),
        log_file=os.getenv("UES_LOG_FILE", DEFAULT_LOG_FILE),
        tg_bot_token=os.getenv("TG_BOT_TOKEN", ""),
        tg_chat_id=os.getenv("TG_CHAT_ID", ""),
        ues_user=os.getenv("UES_USER", ""),
        ues_pass=os.getenv("UES_PASS", ""),
        tz_name=os.getenv("UES_TZ", DEFAULT_TZ),
        quiet_start=os.getenv("UES_QUIET_START", "00:00"),
        quiet_end=os.getenv("UES_QUIET_END", "07:00"),
    )
