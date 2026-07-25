"""Offline tests for the GitHub MCP service.

A fake Anthropic client stands in for the network, so we can verify the MCP
connection payload, the tool allowlist, response parsing, and pause_turn
resumption without contacting Anthropic or GitHub.

Run:
    venv/Scripts/python.exe -m unittest -v
"""

from __future__ import annotations

import os
import unittest
from typing import Any

# Provide dummy credentials before importing app modules (config validates them).
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-dummy-test")
os.environ.setdefault("GITHUB_TOKEN", "ghp_dummy_test")
os.environ.setdefault("GITHUB_REPO", "octo/hello")

from app.services.github_mcp import (  # noqa: E402
    ALLOWED_TOOLS,
    GitHubMCPError,
    GitHubMCPService,
)


class Block:
    """A minimal stand-in for an SDK content block."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class Response:
    """A minimal stand-in for a Messages API response."""

    def __init__(self, content: list[Block], stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.model = "claude-sonnet-4-5"
        self.usage = object()  # log_usage reads attrs defensively (defaults to 0)


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


class GitHubMCPRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GitHubMCPService(client=FakeClient([]))

    def test_request_declares_github_mcp_server_with_auth(self) -> None:
        req = self.service._build_request([{"role": "user", "content": "hi"}])
        server = req["mcp_servers"][0]
        self.assertEqual(server["type"], "url")
        self.assertEqual(server["name"], "github")
        self.assertEqual(server["url"], "https://api.githubcopilot.com/mcp/")
        self.assertEqual(server["authorization_token"], "ghp_dummy_test")

    def test_request_enables_mcp_connector_beta(self) -> None:
        req = self.service._build_request([{"role": "user", "content": "hi"}])
        self.assertIn("mcp-client-2025-11-20", req["betas"])

    def test_toolset_allowlists_only_the_three_actions(self) -> None:
        req = self.service._build_request([{"role": "user", "content": "hi"}])
        toolset = req["tools"][0]
        self.assertEqual(toolset["type"], "mcp_toolset")
        self.assertEqual(toolset["mcp_server_name"], "github")
        self.assertFalse(toolset["default_config"]["enabled"])
        enabled = {c["name"] for c in toolset["configs"] if c["enabled"]}
        self.assertEqual(enabled, set(ALLOWED_TOOLS))
        self.assertEqual(enabled, {"search_issues", "create_issue", "update_issue"})


class GitHubMCPParsingTests(unittest.TestCase):
    def test_collect_extracts_tool_calls_results_and_text(self) -> None:
        response = Response(
            content=[
                Block(type="mcp_tool_use", name="search_issues", input={"q": "login"}),
                Block(type="mcp_tool_result", content=[Block(type="text", text="0 issues")]),
                Block(type="mcp_tool_use", name="create_issue", input={"title": "Login bug"}),
                Block(type="mcp_tool_result", content="Created issue #42"),
                Block(type="text", text="Created issue #42 for the login bug."),
            ],
            stop_reason="end_turn",
        )
        text, calls, results = [], [], []
        GitHubMCPService._collect(response, text, calls, results)

        self.assertEqual([c.name for c in calls], ["search_issues", "create_issue"])
        self.assertEqual(calls[0].input, {"q": "login"})
        self.assertEqual(results, ["0 issues", "Created issue #42"])
        self.assertIn("#42", "".join(text))


class GitHubMCPRunTests(unittest.TestCase):
    def test_run_requires_a_token(self) -> None:
        service = GitHubMCPService(client=FakeClient([]))
        # Settings is a cached singleton; restore the token so other tests are
        # unaffected by this simulated-missing-token case.
        original = service._settings.github_token
        self.addCleanup(setattr, service._settings, "github_token", original)
        service._settings.github_token = None
        with self.assertRaises(GitHubMCPError):
            service.run("Search issues about login")

    def test_run_resumes_on_pause_turn_then_finishes(self) -> None:
        first = Response(
            content=[Block(type="mcp_tool_use", name="search_issues", input={"q": "x"})],
            stop_reason="pause_turn",
        )
        second = Response(
            content=[Block(type="text", text="Done — found issue #7.")],
            stop_reason="end_turn",
        )
        client = FakeClient([first, second])
        service = GitHubMCPService(client=client)

        result = service.run("Search issues about x")

        # Both rounds were called (pause_turn resumed), and results accumulated.
        self.assertEqual(len(client.beta.messages.calls), 2)
        self.assertEqual([c.name for c in result.tool_calls], ["search_issues"])
        self.assertIn("#7", result.summary)


if __name__ == "__main__":
    unittest.main()
