"""Tool registry and dispatcher.

The registry is the bridge between Claude and the tool implementations. It
publishes every tool's schema for the Messages API and routes an incoming
tool_use block to the matching implementation, translating failures into
error results the model can recover from.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.tools.base import Tool, ToolError
from app.tools.support_tools import (
    CreateTicketTool,
    LookupCustomerTool,
    LookupOrderTool,
)

logger = get_logger(__name__)


class ToolRegistry:
    """Holds tools, publishes their schemas, and dispatches calls."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {tool.name: tool for tool in tools}

    def schemas(self) -> list[dict[str, Any]]:
        """Return all tool definitions for the Messages API `tools` array."""
        return [tool.to_schema() for tool in self._tools.values()]

    def dispatch(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Execute a tool call. Returns (content, is_error)."""
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Claude called unknown tool: %s", name)
            return (f"Unknown tool: {name}", True)

        logger.info("Executing tool %s with input=%s", name, tool_input)
        try:
            return (tool.run(tool_input), False)
        except ToolError as exc:
            logger.info("Tool %s returned an error result: %s", name, exc)
            return (str(exc), True)
        except Exception as exc:  # noqa: BLE001 - surface as recoverable tool error
            logger.exception("Tool %s raised an unexpected error", name)
            return (f"Tool '{name}' failed unexpectedly: {exc}", True)

    async def adispatch(
        self, name: str, tool_input: dict[str, Any]
    ) -> tuple[str, bool]:
        """Async twin of `dispatch`, awaited concurrently by the parallel agent."""
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Claude called unknown tool: %s", name)
            return (f"Unknown tool: {name}", True)

        logger.info("Executing tool %s (async) with input=%s", name, tool_input)
        try:
            return (await tool.arun(tool_input), False)
        except ToolError as exc:
            logger.info("Tool %s returned an error result: %s", name, exc)
            return (str(exc), True)
        except Exception as exc:  # noqa: BLE001 - surface as recoverable tool error
            logger.exception("Tool %s raised an unexpected error", name)
            return (f"Tool '{name}' failed unexpectedly: {exc}", True)


def default_registry() -> ToolRegistry:
    """Return a registry with the standard support tools registered."""
    return ToolRegistry(
        [LookupCustomerTool(), LookupOrderTool(), CreateTicketTool()]
    )
