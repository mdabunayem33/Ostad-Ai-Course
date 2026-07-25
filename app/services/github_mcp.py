"""GitHub issue agent over the MCP connector.

Uses Anthropic's server-side MCP connector: we declare the GitHub MCP server
and an allowlisted `mcp_toolset`, and Anthropic connects to GitHub and executes
the issue tools for us. From our side it behaves like a server tool — results
arrive inline as `mcp_tool_use` / `mcp_tool_result` blocks, and a long turn may
stop with `pause_turn`, which we resume by re-sending.

The tool allowlist enforces the three permitted actions: search, create, and
update issues. The Anthropic client is injectable so the behavior is unit
tested without any network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tasks import TaskType
from app.prompts.github import build_github_system_prompt
from app.services.claude_client import get_claude_client
from app.services.model_router import ModelRouter
from app.services.usage import log_usage

logger = get_logger(__name__)

#: The GitHub MCP tools Claude is permitted to call.
ALLOWED_TOOLS = ["search_issues", "create_issue", "update_issue"]

MCP_SERVER_NAME = "github"


class GitHubMCPError(Exception):
    """Raised when the GitHub MCP request cannot be made or completed."""


@dataclass
class GitHubToolCall:
    """One GitHub MCP tool invocation Claude made."""

    name: str
    input: dict[str, Any]


@dataclass
class GitHubResult:
    """The agent's summary plus the tool calls and raw results it produced."""

    summary: str
    tool_calls: list[GitHubToolCall] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    model: str = ""


class GitHubMCPService:
    """Lets Claude search, create, and update GitHub issues via MCP."""

    def __init__(self, client: Any = None, max_rounds: int = 6) -> None:
        self._client = client or get_claude_client()
        self._settings = get_settings()
        router = ModelRouter()
        self._model = router.model_for(TaskType.GITHUB)
        self._max_tokens = router.max_tokens_for(TaskType.GITHUB)
        self._max_rounds = max_rounds

    # -- Connection description (for demos / diagnostics) ------------------

    def describe_connection(self) -> dict[str, Any]:
        """Return a non-secret view of the MCP connection configuration."""
        return {
            "server_url": self._settings.github_mcp_url,
            "server_name": MCP_SERVER_NAME,
            "beta": self._settings.github_mcp_beta,
            "allowed_tools": ALLOWED_TOOLS,
            "repo": self._settings.github_repo,
            "token_configured": bool(self._settings.github_token),
        }

    # -- Request assembly --------------------------------------------------

    def _mcp_server(self) -> dict[str, Any]:
        server: dict[str, Any] = {
            "type": "url",
            "name": MCP_SERVER_NAME,
            "url": self._settings.github_mcp_url,
        }
        if self._settings.github_token:
            server["authorization_token"] = self._settings.github_token
        return server

    def _mcp_toolset(self) -> dict[str, Any]:
        """Allowlist: disable all tools, then enable only the three we permit."""
        return {
            "type": "mcp_toolset",
            "mcp_server_name": MCP_SERVER_NAME,
            "default_config": {"enabled": False},
            "configs": [{"name": name, "enabled": True} for name in ALLOWED_TOOLS],
        }

    def _build_request(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "betas": [self._settings.github_mcp_beta],
            "system": build_github_system_prompt(self._settings.github_repo),
            "mcp_servers": [self._mcp_server()],
            "tools": [self._mcp_toolset()],
            "messages": messages,
        }

    # -- Execution ---------------------------------------------------------

    def run(self, instruction: str) -> GitHubResult:
        """Have Claude act on GitHub issues per a natural-language instruction."""
        if not instruction or not instruction.strip():
            raise GitHubMCPError("Instruction must not be empty.")
        if not self._settings.github_token:
            raise GitHubMCPError(
                "GITHUB_TOKEN is not set — cannot authenticate to the GitHub MCP server."
            )

        logger.info("GitHub MCP run (model=%s)", self._model)
        messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
        text_parts: list[str] = []
        tool_calls: list[GitHubToolCall] = []
        results: list[str] = []
        model = self._model

        for _ in range(self._max_rounds):
            response = self._client.beta.messages.create(**self._build_request(messages))
            model = response.model
            log_usage(TaskType.GITHUB, response.model, response.usage)

            self._collect(response, text_parts, tool_calls, results)

            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break

        return GitHubResult(
            summary="".join(text_parts).strip(),
            tool_calls=tool_calls,
            results=results,
            model=model,
        )

    # -- Response parsing --------------------------------------------------

    @staticmethod
    def _collect(
        response: Any,
        text_parts: list[str],
        tool_calls: list[GitHubToolCall],
        results: list[str],
    ) -> None:
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "mcp_tool_use":
                tool_calls.append(
                    GitHubToolCall(
                        name=getattr(block, "name", "") or "",
                        input=dict(getattr(block, "input", None) or {}),
                    )
                )
            elif btype == "mcp_tool_result":
                results.append(GitHubMCPService._stringify(getattr(block, "content", None)))

    @staticmethod
    def _stringify(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                text = getattr(item, "text", None)
                parts.append(text if text is not None else str(item))
            return "".join(parts)
        return "" if content is None else str(content)
