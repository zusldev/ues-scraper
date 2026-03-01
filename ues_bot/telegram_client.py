"""Telegram send helper with dry-run support."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.constants import ParseMode


async def tg_send(
    text: str,
    tg_bot_token: str,
    tg_chat_id: str,
    dry_run: bool = False,
    bot: Bot | None = None,
) -> None:
    if dry_run:
        logging.info("[DRY_RUN] Would send Telegram message (%d chars).", len(text))
        return

    if not tg_chat_id:
        raise RuntimeError("Falta TG_CHAT_ID.")

    sender = bot
    if sender is None:
        if not tg_bot_token:
            raise RuntimeError("Falta TG_BOT_TOKEN.")
        sender = Bot(token=tg_bot_token)

    await sender.send_message(
        chat_id=tg_chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
