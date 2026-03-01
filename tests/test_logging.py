import logging
from logging.handlers import RotatingFileHandler

from ues_bot.logging_utils import setup_logging


def test_setup_logging_creates_rotating_handler(tmp_path):
    log_file = str(tmp_path / "test.log")

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    setup_logging(log_file, verbose=False)

    file_handlers = [handler for handler in root.handlers if isinstance(handler, RotatingFileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == 5 * 1024 * 1024
    assert file_handlers[0].backupCount == 3

    for handler in root.handlers[:]:
        root.removeHandler(handler)
