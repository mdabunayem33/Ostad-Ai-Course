"""Prompt-caching helpers.

Prompt caching is a prefix match: a stable system prompt marked with
`cache_control` is stored once and reused across requests, so subsequent calls
pay roughly 0.1x for the cached tokens instead of full input price.

Note: the API only caches a prefix once it exceeds the model's minimum
cacheable size (model-dependent — e.g. ~1024 tokens on Sonnet, ~4096 on
Haiku). Marking a shorter prompt is harmless (it simply is not cached), and
the benefit grows as the shared prefix (guidelines, few-shot examples) grows.
Verify hits via `usage.cache_read_input_tokens`.
"""

from __future__ import annotations

from typing import Any


def to_cached_system(prompt: str) -> list[dict[str, Any]]:
    """Return a system prompt as a single cache-controlled text block."""
    return [
        {
            "type": "text",
            "text": prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
