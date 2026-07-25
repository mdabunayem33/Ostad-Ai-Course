"""Base abstraction for client-side tools.

A `Tool` bundles the metadata Claude needs (name, description, input schema)
with the Python implementation that runs when Claude calls it. `to_schema()`
produces the exact dict shape the Messages API expects in its `tools` array.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any


class ToolError(Exception):
    """Raised by a tool for an expected, recoverable failure.

    The agent converts this into a tool_result with is_error=True so Claude
    can read the message and adjust (e.g. ask for a valid ID).
    """


class Tool(ABC):
    """Interface every client-side tool implements."""

    #: Stable tool name Claude references when calling.
    name: str
    #: Description Claude uses to decide when and how to call the tool.
    description: str

    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for this tool's inputs."""

    @abstractmethod
    def run(self, tool_input: dict[str, Any]) -> str:
        """Execute the tool and return a string result for Claude.

        Raise `ToolError` for expected failures (not found, invalid input).
        """

    async def arun(self, tool_input: dict[str, Any]) -> str:
        """Async execution used by the parallel agent.

        The default offloads the blocking `run()` to a worker thread so any
        sync tool participates in concurrent execution unchanged. Tools with
        native async I/O should override this to await it directly.
        """
        return await asyncio.to_thread(self.run, tool_input)

    def to_schema(self) -> dict[str, Any]:
        """Return the tool definition for the Messages API `tools` array."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema(),
        }
