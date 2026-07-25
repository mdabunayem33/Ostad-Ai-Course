"""Prompt construction for the triage classifier.

The system prompt is generated from the domain enums so the instructions and
the validation contract stay in lockstep — adding a new Team or Topic in
`domain/models.py` automatically updates what the model is told.
"""

from __future__ import annotations

from app.domain.models import Team, Topic, Urgency


def _values(enum_cls: type) -> str:
    """Render an enum's values as a comma-separated list for the prompt."""
    return ", ".join(member.value for member in enum_cls)


def build_system_prompt() -> str:
    """Return the system prompt instructing Claude to classify and emit JSON."""
    return f"""You are a customer-support triage classifier for a SaaS product.

Given a single customer support message, classify it along three dimensions
and respond with ONLY a JSON object — no prose, no markdown code fences.

Fields and their allowed values (use these exact lowercase strings):

- "urgency": one of [{_values(Urgency)}]
- "topic": one of [{_values(Topic)}]
- "assigned_team": one of [{_values(Team)}]
- "reason": a single concise sentence justifying the classification.

Guidelines:
- Judge urgency by customer impact and time-sensitivity. Outages, data loss,
  payment failures, or security concerns are "high" or "critical".
- Match "assigned_team" to the topic and severity:
  billing -> billing_team, technical -> engineering,
  account -> account_management, product_feedback -> customer_success,
  general -> general_support. Escalate to a more senior team when severity
  warrants it, and explain that choice in "reason".

Respond with the JSON object only."""


def build_user_prompt(message: str) -> str:
    """Wrap the raw customer message for the user turn."""
    return f"Support message to classify:\n\n{message}"
