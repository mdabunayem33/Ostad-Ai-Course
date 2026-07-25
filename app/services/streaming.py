"""Streaming responder: draft a reply and emit it token by token.

Uses the SDK's `messages.stream(...)` helper, which manages the SSE connection
and exposes `text_stream` (incremental text deltas) plus `get_final_message()`
(the fully accumulated message with usage). Every delta is handed to an
`on_token` callback so callers can render it live.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tasks import TaskType
from app.prompts.reply import build_reply_system_prompt, build_reply_user_prompt
from app.services.claude_client import get_async_claude_client, get_claude_client
from app.services.model_router import ModelRouter

logger = get_logger(__name__)

#: A callback invoked with each streamed text delta.
TokenHandler = Callable[[str], None]


def print_token(text: str) -> None:
    """Default token handler: write the delta immediately, unbuffered."""
    sys.stdout.write(text)
    sys.stdout.flush()


@dataclass(frozen=True)
class StreamResult:
    """The complete reply after streaming finishes."""

    text: str
    model: str
    output_tokens: int


class StreamingResponder:
    """Generates a customer reply, streaming tokens as they are produced."""

    def __init__(self) -> None:
        self._client = get_claude_client()
        self._aclient = get_async_claude_client()
        self._settings = get_settings()
        self._system_prompt = build_reply_system_prompt()
        self._model = ModelRouter().model_for(TaskType.REPLY)

    def stream_reply(
        self, message: str, on_token: TokenHandler | None = None
    ) -> StreamResult:
        """Stream a reply synchronously, calling `on_token` for each delta."""
        handler = on_token or print_token
        logger.info("Streaming reply (sync) with model=%s", self._model)

        chunks: list[str] = []
        with self._client.messages.stream(
            model=self._model,
            max_tokens=self._settings.max_tokens,
            system=self._system_prompt,
            messages=[{"role": "user", "content": build_reply_user_prompt(message)}],
        ) as stream:
            for delta in stream.text_stream:
                chunks.append(delta)
                handler(delta)
            final = stream.get_final_message()

        return StreamResult(
            text="".join(chunks),
            model=final.model,
            output_tokens=final.usage.output_tokens,
        )

    async def astream_reply(
        self, message: str, on_token: TokenHandler | None = None
    ) -> StreamResult:
        """Stream a reply asynchronously, calling `on_token` for each delta."""
        handler = on_token or print_token
        logger.info("Streaming reply (async) with model=%s", self._model)

        chunks: list[str] = []
        async with self._aclient.messages.stream(
            model=self._model,
            max_tokens=self._settings.max_tokens,
            system=self._system_prompt,
            messages=[{"role": "user", "content": build_reply_user_prompt(message)}],
        ) as stream:
            async for delta in stream.text_stream:
                chunks.append(delta)
                handler(delta)
            final = await stream.get_final_message()

        return StreamResult(
            text="".join(chunks),
            model=final.model,
            output_tokens=final.usage.output_tokens,
        )
