"""Small helpers: HTML escape, truncation, timezone/quiet hours, chunking."""

from __future__ import annotations

import re
from datetime import datetime

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def parse_hhmm(s: str) -> tuple[int, int]:
    m = re.match(r"^(\d{1,2}):(\d{2})$", (s or "").strip())
    if not m:
        raise ValueError(f"Hora inválida: {s!r}. Usa HH:MM, ej. 07:00")
    hh = int(m.group(1))
    mm = int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"Hora inválida: {s!r}")
    return hh, mm


def now_local(tz_name: str) -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(tz_name))


def is_in_quiet_hours(now: datetime, quiet_start: str, quiet_end: str) -> bool:
    if not quiet_start or not quiet_end:
        return False

    sh, sm = parse_hhmm(quiet_start)
    eh, em = parse_hhmm(quiet_end)

    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)

    if start < end:
        return start <= now < end
    return now >= start or now < end


def chunk_messages(msg: str, max_len: int = 3800) -> list[str]:
    if len(msg) <= max_len:
        return [msg]

    parts: list[str] = []
    cur: list[str] = []
    cur_len = 0

    for block in msg.split("\n\n"):
        blen = len(block) + 2
        if cur and cur_len + blen > max_len:
            parts.append("\n\n".join(cur))
            cur = [block]
            cur_len = len(block)
        else:
            cur.append(block)
            cur_len += blen

    if cur:
        parts.append("\n\n".join(cur))

    return parts
