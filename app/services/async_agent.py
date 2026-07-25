"""Parallel tool-using support agent (asyncio).

Identical control flow to the synchronous `SupportAgent`, with one crucial
difference: when Claude returns several `tool_use` blocks in a single turn,
their handlers are executed **concurrently** with `asyncio.gather` instead of
one after another. Independent lookups (customer + order) therefore overlap,
turning ~sum(latency) into ~max(latency).

Order is preserved: results are gathered in block order and each `tool_result`
carries its matching `tool_use_id`, so concurrency never corrupts the reply.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tasks import TaskType
from app.prompts.agent import build_agent_system_prompt
from app.services.agent import AgentError, AgentResult, ToolCall
from app.services.claude_client import get_async_claude_client
from app.services.model_router import ModelRouter
from app.tools.registry import ToolRegistry, default_registry

logger = get_logger(__name__)


class AsyncSupportAgent:
    """Resolves support requests, executing parallel tool calls concurrently."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        max_iterations: int = 6,
    ) -> None:
        self._client = get_async_claude_client()
        self._settings = get_settings()
        self._registry = registry or default_registry()
        self._system_prompt = build_agent_system_prompt()
        self._model = ModelRouter().model_for(TaskType.AGENT)
        self._max_iterations = max_iterations

    async def handle(self, message: str) -> AgentResult:
        """Run the tool-use loop, executing each turn's tools in parallel."""
        if not message or not message.strip():
            raise AgentError("Cannot handle an empty message.")

        logger.info("Async agent handling request with model=%s", self._model)
        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
        all_calls: list[ToolCall] = []

        for iteration in range(1, self._max_iterations + 1):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._settings.max_tokens,
                system=self._system_prompt,
                tools=self._registry.schemas(),
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                reply = self._extract_text(response)
                logger.info(
                    "Async agent finished in %d iteration(s), %d tool call(s)",
                    iteration,
                    len(all_calls),
                )
                return AgentResult(reply=reply, tool_calls=all_calls)

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            calls = await self._execute_parallel(tool_use_blocks)
            all_calls.extend(calls)

            # Return all results in ONE user message, in original block order.
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": call.output,
                    "is_error": call.is_error,
                }
                for block, call in zip(tool_use_blocks, calls)
            ]
            messages.append({"role": "user", "content": tool_results})

        raise AgentError(
            f"Reached the {self._max_iterations}-iteration limit without a final reply."
        )

    async def _execute_parallel(self, tool_use_blocks: list[Any]) -> list[ToolCall]:
        """Run every tool_use block concurrently, preserving order."""
        if not tool_use_blocks:
            return []

        wall_start = time.perf_counter()
        calls = await asyncio.gather(
            *(self._execute_one(block) for block in tool_use_blocks)
        )
        wall_ms = (time.perf_counter() - wall_start) * 1000
        sequential_ms = sum(call.duration_ms for call in calls)
        logger.info(
            "Executed %d tool(s) in parallel: wall=%.0fms, "
            "sequential-would-be=%.0fms",
            len(calls),
            wall_ms,
            sequential_ms,
        )
        return list(calls)

    async def _execute_one(self, block: Any) -> ToolCall:
        """Dispatch a single tool call and record its duration."""
        start = time.perf_counter()
        content, is_error = await self._registry.adispatch(block.name, block.input)
        duration_ms = (time.perf_counter() - start) * 1000
        return ToolCall(
            name=block.name,
            input=dict(block.input),
            output=content,
            is_error=is_error,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _extract_text(response) -> str:
        parts = [block.text for block in response.content if block.type == "text"]
        return "".join(parts).strip()
