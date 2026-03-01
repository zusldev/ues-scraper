"""Logging setup (console + rotating file)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler


def setup_logging(
    log_file: str,
    verbose: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s | %(levelname)s | %(message)s"

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)
