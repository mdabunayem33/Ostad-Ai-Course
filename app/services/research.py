"""Web-search-grounded research service (built-in server tool).

Enables Anthropic's web-search server tool so Claude can look up current
external facts relevant to a support ticket. Search executes on Anthropic's
servers; the response carries `server_tool_use` blocks (the queries Claude
ran) and `web_search_tool_result` blocks (the hits), which we extract alongside
the synthesized context note.

The server-tool sampling loop can stop with `stop_reason == "pause_turn"`; we
resume by re-sending the accumulated conversation until it finishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tasks import TaskType
from app.prompts.research import (
    build_research_system_prompt,
    build_research_user_prompt,
)
from app.services.claude_client import get_claude_client
from app.services.model_router import ModelRouter
from app.services.usage import log_usage
from app.utils.caching import to_cached_system

logger = get_logger(__name__)


class ResearchError(Exception):
    """Raised when the research request cannot complete."""


@dataclass
class Source:
    """A web source Claude found."""

    title: str
    url: str


@dataclass
class ResearchResult:
    """The synthesized context note plus the searches that produced it."""

    context_note: str
    queries: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    model: str = ""


class WebResearchService:
    """Grounds triage in current external facts via web search."""

    def __init__(self, max_rounds: int = 5) -> None:
        self._client = get_claude_client()
        self._settings = get_settings()
        self._router = ModelRouter()
        self._system_prompt = build_research_system_prompt()
        self._model = self._router.model_for(TaskType.RESEARCH)
        self._max_tokens = self._router.max_tokens_for(TaskType.RESEARCH)
        self._max_rounds = max_rounds

    def _web_search_tool(self) -> dict[str, Any]:
        """Declare the web-search server tool (with a search cap)."""
        return {
            "type": self._settings.web_search_tool_type,
            "name": "web_search",
            "max_uses": self._settings.web_search_max_uses,
        }

    def research(self, message: str) -> ResearchResult:
        """Run web-search-grounded research for a support message."""
        if not message or not message.strip():
            raise ResearchError("Cannot research an empty message.")

        logger.info(
            "Web research with model=%s tool=%s",
            self._model,
            self._settings.web_search_tool_type,
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": build_research_user_prompt(message)}
        ]
        text_parts: list[str] = []
        queries: list[str] = []
        sources: list[Source] = []
        last_model = self._model

        for _ in range(self._max_rounds):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=to_cached_system(self._system_prompt),
                tools=[self._web_search_tool()],
                messages=messages,
            )
            last_model = response.model
            log_usage(TaskType.RESEARCH, response.model, response.usage)

            self._collect(response, text_parts, queries, sources)

            # Server-tool loop paused mid-turn; resume by re-sending.
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break

        return ResearchResult(
            context_note="".join(text_parts).strip(),
            queries=queries,
            sources=sources,
            model=last_model,
        )

    @staticmethod
    def _collect(
        response: Any,
        text_parts: list[str],
        queries: list[str],
        sources: list[Source],
    ) -> None:
        """Pull text, search queries, and sources from a response."""
        for block in response.content:
            btype = getattr(block, "type", None)

            if btype == "text":
                text_parts.append(block.text)

            elif btype == "server_tool_use" and getattr(block, "name", "") == "web_search":
                query = (getattr(block, "input", None) or {}).get("query")
                if query:
                    queries.append(query)

            elif btype == "web_search_tool_result":
                content = getattr(block, "content", None)
                if isinstance(content, list):
                    for item in content:
                        if getattr(item, "type", None) == "web_search_result":
                            sources.append(
                                Source(
                                    title=getattr(item, "title", "") or "",
                                    url=getattr(item, "url", "") or "",
                                )
                            )
