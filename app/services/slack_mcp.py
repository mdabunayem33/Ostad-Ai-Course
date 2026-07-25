"""Slack notification agent over the MCP connector.

Uses Anthropic's server-side MCP connector to post messages to Slack. Two
restrictions apply:

1. Tool allowlist: the `mcp_toolset` enables only message-posting tools.
2. Channel guardrail: `send()` validates the channel against a fixed allowlist
   (#support, #billing, #engineering) *before* any API call, so an off-limits
   channel is rejected in our code and never reaches Slack.

`notify_team()` maps a triage Team to the appropriate channel, connecting
routing (Step 2) to notification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.models import Team
from app.domain.tasks import TaskType
from app.prompts.slack import build_slack_system_prompt
from app.services.claude_client import get_claude_client
from app.services.model_router import ModelRouter
from app.services.usage import log_usage

logger = get_logger(__name__)

MCP_SERVER_NAME = "slack"

#: The only channels this service will post to.
ALLOWED_CHANNELS = ["#support", "#billing", "#engineering"]

#: Candidate message-posting tool names across Slack MCP server variants. Only
#: the ones the connected server actually exposes take effect; set to your
#: server's exact tool name if it differs.
SLACK_SEND_TOOLS = ["send_message", "post_message", "chat_postMessage"]

#: Which channel each team's notifications go to.
TEAM_CHANNELS: dict[str, str] = {
    Team.BILLING_TEAM.value: "#billing",
    Team.ENGINEERING.value: "#engineering",
    # account_management, customer_success, general_support -> #support
}


class SlackMCPError(Exception):
    """Raised when a Slack notification cannot be made or completed."""


@dataclass
class SlackToolCall:
    name: str
    input: dict[str, Any]


@dataclass
class SlackResult:
    channel: str
    summary: str
    tool_calls: list[SlackToolCall] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    model: str = ""


class SlackMCPService:
    """Posts support notifications to a fixed set of Slack channels via MCP."""

    def __init__(self, client: Any = None, max_rounds: int = 6) -> None:
        self._client = client or get_claude_client()
        self._settings = get_settings()
        router = ModelRouter()
        self._model = router.model_for(TaskType.SLACK)
        self._max_tokens = router.max_tokens_for(TaskType.SLACK)
        self._max_rounds = max_rounds
        self._system_prompt = build_slack_system_prompt(ALLOWED_CHANNELS)

    # -- Public API --------------------------------------------------------

    @staticmethod
    def channel_for_team(team: Any) -> str:
        """Map a Team (enum or value) to its notification channel."""
        value = getattr(team, "value", team)
        return TEAM_CHANNELS.get(value, "#support")

    def notify_team(self, team: Any, message: str) -> SlackResult:
        """Post a message to the channel owned by `team`."""
        return self.send(self.channel_for_team(team), message)

    def send(self, channel: str, message: str) -> SlackResult:
        """Post `message` to `channel` after validating the channel allowlist."""
        if not message or not message.strip():
            raise SlackMCPError("Message must not be empty.")

        channel = self._normalize_channel(channel)
        if channel not in ALLOWED_CHANNELS:
            raise SlackMCPError(
                f"Channel {channel} is not permitted. "
                f"Allowed channels: {', '.join(ALLOWED_CHANNELS)}."
            )

        instruction = (
            f"Post the following message to the {channel} Slack channel, "
            f"exactly as written:\n\n{message}"
        )
        return self._run(instruction, channel)

    def describe_connection(self) -> dict[str, Any]:
        """Return a non-secret view of the MCP connection configuration."""
        return {
            "server_url": self._settings.slack_mcp_url,
            "server_name": MCP_SERVER_NAME,
            "beta": self._settings.slack_mcp_beta,
            "allowed_channels": ALLOWED_CHANNELS,
            "send_tools": SLACK_SEND_TOOLS,
            "token_configured": bool(self._settings.slack_token),
        }

    # -- Request assembly --------------------------------------------------

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        channel = (channel or "").strip()
        if channel and not channel.startswith("#"):
            channel = f"#{channel}"
        return channel

    def _mcp_server(self) -> dict[str, Any]:
        server: dict[str, Any] = {
            "type": "url",
            "name": MCP_SERVER_NAME,
            "url": self._settings.slack_mcp_url,
        }
        if self._settings.slack_token:
            server["authorization_token"] = self._settings.slack_token
        return server

    def _mcp_toolset(self) -> dict[str, Any]:
        return {
            "type": "mcp_toolset",
            "mcp_server_name": MCP_SERVER_NAME,
            "default_config": {"enabled": False},
            "configs": [{"name": name, "enabled": True} for name in SLACK_SEND_TOOLS],
        }

    def _build_request(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "betas": [self._settings.slack_mcp_beta],
            "system": self._system_prompt,
            "mcp_servers": [self._mcp_server()],
            "tools": [self._mcp_toolset()],
            "messages": messages,
        }

    # -- Execution ---------------------------------------------------------

    def _run(self, instruction: str, channel: str) -> SlackResult:
        if not self._settings.slack_token:
            raise SlackMCPError(
                "SLACK_TOKEN is not set — cannot authenticate to the Slack MCP server."
            )

        logger.info("Slack MCP post to %s (model=%s)", channel, self._model)
        messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
        text_parts: list[str] = []
        tool_calls: list[SlackToolCall] = []
        results: list[str] = []
        model = self._model

        for _ in range(self._max_rounds):
            response = self._client.beta.messages.create(**self._build_request(messages))
            model = response.model
            log_usage(TaskType.SLACK, response.model, response.usage)

            self._collect(response, text_parts, tool_calls, results)

            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break

        return SlackResult(
            channel=channel,
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
        tool_calls: list[SlackToolCall],
        results: list[str],
    ) -> None:
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "mcp_tool_use":
                tool_calls.append(
                    SlackToolCall(
                        name=getattr(block, "name", "") or "",
                        input=dict(getattr(block, "input", None) or {}),
                    )
                )
            elif btype == "mcp_tool_result":
                results.append(SlackMCPService._stringify(getattr(block, "content", None)))

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
