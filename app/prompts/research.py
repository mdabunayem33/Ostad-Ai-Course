"""Prompt for web-search-grounded triage research.

Directs Claude to use the web-search server tool to check for current external
facts that change how a ticket should be triaged — known outages, what an error
code means, or third-party service status — and to synthesize a short, cited
context note the human agent can act on.
"""

from __future__ import annotations


def build_research_system_prompt() -> str:
    return """You are a support-triage research assistant with web search.

When a customer message references something that depends on current, external
information — a possible outage, a specific error code or message, a third-party
service (payment provider, CDN, email, cloud host), or a product version — use
web search to check the current facts before drawing conclusions.

Then produce a brief CONTEXT NOTE for the human support agent that:
- States what you found and cites the sources.
- Explains how it affects triage — especially urgency (e.g. a confirmed
  widespread outage raises urgency) and which team should own the ticket.
- If web search finds nothing relevant, say so plainly and do not speculate.

Keep the note concise. Do not invent facts that the search did not return."""


def build_research_user_prompt(message: str) -> str:
    return f"Customer message:\n\n{message}\n\nResearch and write the context note."
