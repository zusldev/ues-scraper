"""Telegram Bot API client (sendMessage)."""

from __future__ import annotations

import logging
import requests


def tg_send(text: str, tg_bot_token: str, tg_chat_id: str, dry_run: bool = False) -> None:
    if dry_run:
        logging.info("[DRY_RUN] Would send Telegram message (%d chars).", len(text))
        return

    if not tg_bot_token or not tg_chat_id:
        raise RuntimeError("Falta TG_BOT_TOKEN o TG_CHAT_ID.")

    url = f"https://api.telegram.org/bot{tg_bot_token}/sendMessage"
    r = requests.post(
        url,
        data={
            "chat_id": tg_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    r.raise_for_status()
