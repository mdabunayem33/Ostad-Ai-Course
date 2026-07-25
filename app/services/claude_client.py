"""Thin wrapper around the official Anthropic SDK client.

Every subsystem obtains the Claude client through `get_claude_client()` so
authentication and transport are configured in exactly one place. The client
is cached for the process lifetime.
"""

from __future__ import annotations

from functools import lru_cache

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_claude_client() -> anthropic.Anthropic:
    """Return a cached, configured synchronous Anthropic client instance."""
    settings = get_settings()
    logger.debug("Initializing Anthropic client (model=%s)", settings.anthropic_model)
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


@lru_cache(maxsize=1)
def get_async_claude_client() -> anthropic.AsyncAnthropic:
    """Return a cached, configured asynchronous Anthropic client instance."""
    settings = get_settings()
    logger.debug("Initializing AsyncAnthropic client")
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
