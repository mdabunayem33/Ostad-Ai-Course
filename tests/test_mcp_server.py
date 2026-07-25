"""Tests for the custom subscription MCP server.

Two layers:
- Unit tests call the tool logic directly.
- An integration test boots the server over HTTP (uvicorn on a free port) and
  drives it with a real MCP streamable-HTTP client: initialize, list_tools,
  call_tool. No Anthropic API key required.

Run:
    venv/Scripts/python.exe -m unittest -v
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import unittest
from typing import Any

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.mcp_server.server import build_server, check_subscription_logic


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _extract(result: Any) -> dict[str, Any]:
    """Pull the returned dict from a CallToolResult (structured or text JSON)."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        if "found" in structured:
            return structured
        inner = structured.get("result")
        if isinstance(inner, dict):
            return inner
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            data = json.loads(text)
            if isinstance(data, dict):
                return data.get("result", data) if "found" not in data else data
    raise AssertionError("Could not extract a result dict from the tool response.")


class SubscriptionLogicTests(unittest.TestCase):
    def test_found_customer(self) -> None:
        result = check_subscription_logic("CUST-001")
        self.assertTrue(result["found"])
        self.assertEqual(result["plan"], "Enterprise")
        self.assertEqual(result["status"], "active")

    def test_past_due_customer(self) -> None:
        result = check_subscription_logic("CUST-002")
        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "past_due")

    def test_missing_customer(self) -> None:
        result = check_subscription_logic("CUST-999")
        self.assertFalse(result["found"])

    def test_blank_customer_id(self) -> None:
        result = check_subscription_logic("   ")
        self.assertFalse(result["found"])


class HttpMcpServerTests(unittest.TestCase):
    """End-to-end: a real MCP client talks to the server over HTTP."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.host = "127.0.0.1"
        cls.port = _free_port()
        mcp = build_server(cls.host, cls.port)
        config = uvicorn.Config(
            mcp.streamable_http_app(),
            host=cls.host,
            port=cls.port,
            log_level="warning",
        )
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        for _ in range(200):  # wait up to ~10s for startup
            if cls.server.started:
                break
            time.sleep(0.05)
        if not cls.server.started:
            raise RuntimeError("MCP server failed to start")
        cls.url = f"http://{cls.host}:{cls.port}/mcp"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=10)

    async def _with_session(self, fn):
        async with streamablehttp_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    def test_list_tools_exposes_the_tool(self) -> None:
        result = asyncio.run(self._with_session(lambda s: s.list_tools()))
        names = [t.name for t in result.tools]
        self.assertIn("check_customer_subscription", names)

    def test_call_tool_found(self) -> None:
        result = asyncio.run(
            self._with_session(
                lambda s: s.call_tool(
                    "check_customer_subscription", {"customer_id": "CUST-001"}
                )
            )
        )
        self.assertFalse(result.isError)
        data = _extract(result)
        self.assertTrue(data["found"])
        self.assertEqual(data["plan"], "Enterprise")

    def test_call_tool_missing(self) -> None:
        result = asyncio.run(
            self._with_session(
                lambda s: s.call_tool(
                    "check_customer_subscription", {"customer_id": "CUST-999"}
                )
            )
        )
        data = _extract(result)
        self.assertFalse(data["found"])


if __name__ == "__main__":
    unittest.main()
