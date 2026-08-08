"""Centralized structured logging with secret redaction.

Logs go to stdout (for Docker / uvicorn) and to a rotating file. API
keys, tokens, and authorization headers are scrubbed as a safety net in
addition to being kept out of log calls in the first place.
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler

from publisher.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{6,}"),
    re.compile(r"(api[_-]?key[\"'\s:=]+[^\s,;]+)", re.IGNORECASE),
    re.compile(r"(bearer\s+[A-Za-z0-9._~+/=-]+)", re.IGNORECASE),
)


class SecretRedactionFilter(logging.Filter):
    """Scrub likely secrets before a record reaches a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _SECRET_PATTERNS:
            message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


_LOGGING_CONFIGURED = False


def _build_handlers() -> list[logging.Handler]:
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(SecretRedactionFilter())
    handlers.append(stream_handler)

    if settings.log_file:
        try:
            log_dir = os.path.dirname(settings.log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                settings.log_file,
                maxBytes=5_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(SecretRedactionFilter())
            handlers.append(file_handler)
        except OSError:
            # Logging must never crash startup because a path is unwritable.
            pass

    return handlers


def setup_logging() -> None:
    """Configure the root logger exactly once."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for handler in _build_handlers():
        root.addHandler(handler)
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the calling module."""
    setup_logging()
    return logging.getLogger(name)
