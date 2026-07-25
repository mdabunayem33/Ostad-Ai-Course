"""Tool-using support agent: the manual Anthropic Tool Use loop.

The loop is: send the conversation with tool schemas -> if Claude stops with
`tool_use`, execute every requested tool and return ALL results in a single
user message -> repeat until Claude stops for another reason. An iteration cap
guards against runaway loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tasks import TaskType
from app.prompts.agent import build_agent_system_prompt
from app.services.claude_client import get_claude_client
from app.services.model_router import ModelRouter
from app.tools.registry import ToolRegistry, default_registry

logger = get_logger(__name__)


class AgentError(Exception):
    """Raised when the agent cannot complete the request."""


@dataclass
class ToolCall:
    """A record of one tool invocation, for observability."""

    name: str
    input: dict[str, Any]
    output: str
    is_error: bool
    duration_ms: float = 0.0


@dataclass
class AgentResult:
    """The agent's final reply plus every tool call it made."""

    reply: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class SupportAgent:
    """Resolves support requests by calling tools in a loop."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        max_iterations: int = 6,
    ) -> None:
        self._client = get_claude_client()
        self._settings = get_settings()
        self._registry = registry or default_registry()
        self._system_prompt = build_agent_system_prompt()
        self._model = ModelRouter().model_for(TaskType.AGENT)
        self._max_iterations = max_iterations

    def handle(self, message: str) -> AgentResult:
        """Run the tool-use loop until Claude finishes or the cap is hit."""
        if not message or not message.strip():
            raise AgentError("Cannot handle an empty message.")

        logger.info("Agent handling request with model=%s", self._model)
        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
        tool_calls: list[ToolCall] = []

        for iteration in range(1, self._max_iterations + 1):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._settings.max_tokens,
                system=self._system_prompt,
                tools=self._registry.schemas(),
                messages=messages,
            )

            # Preserve the assistant turn (including tool_use blocks) verbatim.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                reply = self._extract_text(response)
                logger.info(
                    "Agent finished in %d iteration(s), %d tool call(s)",
                    iteration,
                    len(tool_calls),
                )
                return AgentResult(reply=reply, tool_calls=tool_calls)

            # Execute every requested tool; return all results in ONE user turn.
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                content, is_error = self._registry.dispatch(block.name, block.input)
                tool_calls.append(
                    ToolCall(
                        name=block.name,
                        input=dict(block.input),
                        output=content,
                        is_error=is_error,
                    )
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        raise AgentError(
            f"Reached the {self._max_iterations}-iteration limit without a final reply."
        )

    @staticmethod
    def _extract_text(response) -> str:
        parts = [block.text for block in response.content if block.type == "text"]
        return "".join(parts).strip()
