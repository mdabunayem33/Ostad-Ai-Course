"""Offline tests for the Slack MCP service.

A fake Anthropic client stands in for the network, so we verify the MCP
connection payload, the send-tool allowlist, the channel guardrail, the
team->channel mapping, and pause_turn resumption without any real calls.

Run:
    venv/Scripts/python.exe -m unittest -v
"""

from __future__ import annotations

import os
import unittest
from typing import Any

os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-dummy-test")
os.environ["SLACK_TOKEN"] = "xoxb-dummy-test"

# Settings is an lru_cached singleton that may have been built by another test
# module before SLACK_TOKEN was set. Clear it so the env value above is picked
# up (real env vars take precedence over the .env file in pydantic-settings).
from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.domain.models import Team  # noqa: E402
from app.services.slack_mcp import (  # noqa: E402
    ALLOWED_CHANNELS,
    SLACK_SEND_TOOLS,
    SlackMCPError,
    SlackMCPService,
)


class Block:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class Response:
    def __init__(self, content: list[Block], stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.model = "claude-haiku-4-5"
        self.usage = object()


class FakeMessages:
    def __init__(self, responses: list[Response]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeBeta:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages


class FakeClient:
    def __init__(self, responses: list[Response]) -> None:
        self.beta = FakeBeta(FakeMessages(responses))


def _posted_response(text: str = "Posted.") -> Response:
    return Response(
        content=[
            Block(type="mcp_tool_use", name="send_message", input={"text": "hi"}),
            Block(type="mcp_tool_result", content="ok"),
            Block(type="text", text=text),
        ],
        stop_reason="end_turn",
    )


class SlackConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SlackMCPService(client=FakeClient([]))

    def test_request_declares_slack_mcp_server_with_auth(self) -> None:
        req = self.service._build_request([{"role": "user", "content": "hi"}])
        server = req["mcp_servers"][0]
        self.assertEqual(server["name"], "slack")
        self.assertEqual(server["url"], "https://mcp.slack.com/mcp")
        self.assertEqual(server["authorization_token"], "xoxb-dummy-test")
        self.assertIn("mcp-client-2025-11-20", req["betas"])

    def test_toolset_allowlists_only_send_tools(self) -> None:
        req = self.service._build_request([{"role": "user", "content": "hi"}])
        toolset = req["tools"][0]
        self.assertEqual(toolset["mcp_server_name"], "slack")
        self.assertFalse(toolset["default_config"]["enabled"])
        enabled = {c["name"] for c in toolset["configs"] if c["enabled"]}
        self.assertEqual(enabled, set(SLACK_SEND_TOOLS))


class SlackChannelGuardrailTests(unittest.TestCase):
    def test_disallowed_channel_is_rejected_before_any_call(self) -> None:
        client = FakeClient([])  # no responses: must not be called
        service = SlackMCPService(client=client)
        with self.assertRaises(SlackMCPError):
            service.send("#random", "hello")
        self.assertEqual(len(client.beta.messages.calls), 0)

    def test_allowed_channel_posts_and_instruction_names_channel(self) -> None:
        client = FakeClient([_posted_response()])
        service = SlackMCPService(client=client)
        result = service.send("#support", "Ticket TKT-1 opened")
        self.assertEqual(result.channel, "#support")
        sent = client.beta.messages.calls[0]["messages"][-1]["content"]
        self.assertIn("#support", sent)
        self.assertIn("Ticket TKT-1 opened", sent)
        self.assertEqual([c.name for c in result.tool_calls], ["send_message"])

    def test_channel_is_normalized_with_hash(self) -> None:
        client = FakeClient([_posted_response()])
        service = SlackMCPService(client=client)
        result = service.send("engineering", "deploy done")
        self.assertEqual(result.channel, "#engineering")

    def test_all_three_channels_are_allowed(self) -> None:
        self.assertEqual(set(ALLOWED_CHANNELS), {"#support", "#billing", "#engineering"})


class SlackTeamMappingTests(unittest.TestCase):
    def test_channel_for_team(self) -> None:
        self.assertEqual(SlackMCPService.channel_for_team(Team.BILLING_TEAM), "#billing")
        self.assertEqual(SlackMCPService.channel_for_team(Team.ENGINEERING), "#engineering")
        self.assertEqual(SlackMCPService.channel_for_team(Team.CUSTOMER_SUCCESS), "#support")
        self.assertEqual(SlackMCPService.channel_for_team(Team.ACCOUNT_MANAGEMENT), "#support")
        # accepts the raw enum value too
        self.assertEqual(SlackMCPService.channel_for_team("engineering"), "#engineering")

    def test_notify_team_posts_to_mapped_channel(self) -> None:
        client = FakeClient([_posted_response()])
        service = SlackMCPService(client=client)
        result = service.notify_team(Team.BILLING_TEAM, "Refund issued")
        self.assertEqual(result.channel, "#billing")
        sent = client.beta.messages.calls[0]["messages"][-1]["content"]
        self.assertIn("#billing", sent)


class SlackRunTests(unittest.TestCase):
    def test_send_requires_a_token(self) -> None:
        service = SlackMCPService(client=FakeClient([_posted_response()]))
        original = service._settings.slack_token
        self.addCleanup(setattr, service._settings, "slack_token", original)
        service._settings.slack_token = None
        with self.assertRaises(SlackMCPError):
            service.send("#support", "hello")

    def test_run_resumes_on_pause_turn_then_finishes(self) -> None:
        first = Response(
            content=[Block(type="mcp_tool_use", name="send_message", input={"text": "hi"})],
            stop_reason="pause_turn",
        )
        second = Response(
            content=[Block(type="text", text="Sent to #engineering.")],
            stop_reason="end_turn",
        )
        client = FakeClient([first, second])
        service = SlackMCPService(client=client)
        result = service.send("#engineering", "deploy complete")
        self.assertEqual(len(client.beta.messages.calls), 2)
        self.assertIn("#engineering", result.summary)


if __name__ == "__main__":
    unittest.main()
