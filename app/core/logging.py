"""Application-wide logging setup.

Call `configure_logging()` once at process start (entrypoints do this), then
obtain module loggers everywhere else with `get_logger(__name__)`. Keeping the
configuration in one place means every subsystem — API calls, tool execution,
MCP servers — emits logs in the same format at the same level.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Initialize root logging exactly once, honoring the configured level."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Quiet noisy third-party libraries unless we are explicitly debugging.
    if settings.log_level != "DEBUG":
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, ensuring logging is configured first."""
    configure_logging()
    return logging.getLogger(name)
