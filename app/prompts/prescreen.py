"""Prompt for the lightweight prescreen pass (runs on the fast model).

Prescreen decides only one thing: is this ticket a routine sort ("simple") or
does it need deeper reasoning ("complex")? Keeping the task narrow is what lets
a small, cheap model do it reliably.
"""

from __future__ import annotations

from app.domain.models import Complexity


def _values() -> str:
    return ", ".join(member.value for member in Complexity)


def build_prescreen_system_prompt() -> str:
    """System prompt for the fast simple/complex classifier."""
    return f"""You are a fast triage pre-screener for customer support tickets.

Decide whether a support message is SIMPLE or COMPLEX, then respond with ONLY
a JSON object — no prose, no markdown fences:

  {{"complexity": "<value>", "reason": "<one short sentence>"}}

"complexity" must be one of [{_values()}].

- SIMPLE: a single, clear, routine request with an obvious category
  (e.g. "How do I reset my password?", "Where can I download my invoice?").
- COMPLEX: anything ambiguous, multi-issue, emotionally charged, or
  high-severity — outages, data loss, security concerns, billing disputes,
  or messages that require judgment about escalation.

When unsure, choose "complex". Respond with the JSON object only."""


def build_prescreen_user_prompt(message: str) -> str:
    """Wrap the raw message for the prescreen user turn."""
    return f"Support message to pre-screen:\n\n{message}"
