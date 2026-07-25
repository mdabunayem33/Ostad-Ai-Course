"""Robust JSON extraction from model output.

Models sometimes wrap JSON in markdown code fences. These helpers strip the
fences and parse a JSON object, raising `ParseError` on anything malformed so
callers can translate it into a domain-specific error.
"""

from __future__ import annotations

import json
from typing import Any


class ParseError(Exception):
    """Raised when model output cannot be parsed into a JSON object."""


def strip_code_fences(text: str) -> str:
    """Remove a surrounding ```json ... ``` (or ``` ... ```) fence if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    """Strip fences, parse JSON, and confirm the result is an object."""
    cleaned = strip_code_fences(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"Output is not valid JSON: {exc}\nRaw output:\n{text}"
        ) from exc

    if not isinstance(payload, dict):
        raise ParseError(f"Expected a JSON object, got {type(payload).__name__}.")
    return payload
