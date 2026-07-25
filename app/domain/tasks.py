"""Task taxonomy and model-tier routing policy.

Every unit of work the triager performs is a `TaskType`. Each task is mapped
to a `ModelTier` — the *class* of model appropriate for it — and the router
(`app/services/model_router.py`) resolves a tier to a concrete model ID from
configuration. Keeping the policy here, as data, means model choices are
reviewed and changed in one obvious place.
"""

from __future__ import annotations

from enum import Enum


class ModelTier(str, Enum):
    """A class of model, chosen by capability-vs-cost trade-off."""

    FAST = "fast"    # Haiku — cheap, fast, great for lightweight sorting.
    SMART = "smart"  # Sonnet — stronger reasoning for hard, ambiguous cases.


class TaskType(str, Enum):
    """A discrete task the pipeline performs."""

    PRESCREEN = "prescreen"            # Is this ticket simple or complex?
    TRIAGE_SIMPLE = "triage_simple"    # Classify an obvious, low-ambiguity ticket.
    TRIAGE_COMPLEX = "triage_complex"  # Classify a hard, escalation-worthy ticket.
    AGENT = "agent"                    # Multi-step tool-using support agent.
    REPLY = "reply"                    # Draft a customer-facing reply (streamed).
    RESEARCH = "research"              # Web-search-grounded external context.
    GITHUB = "github"                  # Manage GitHub issues via the MCP server.
    SLACK = "slack"                    # Post a notification via the Slack MCP server.


# The routing policy: which tier handles which task, and a short rationale
# used both for logging and for the router's `explain()` output.
TASK_TIERS: dict[TaskType, ModelTier] = {
    TaskType.PRESCREEN: ModelTier.FAST,
    TaskType.TRIAGE_SIMPLE: ModelTier.FAST,
    TaskType.TRIAGE_COMPLEX: ModelTier.SMART,
    TaskType.AGENT: ModelTier.SMART,
    TaskType.REPLY: ModelTier.SMART,
    TaskType.RESEARCH: ModelTier.SMART,
    TaskType.GITHUB: ModelTier.SMART,
    TaskType.SLACK: ModelTier.FAST,
}

# Per-task output-token budgets (optimization #3). Each task caps max_tokens
# to what it realistically needs: prescreen returns a tiny JSON object, triage
# a short one, while the agent and reply require more room. Tight, task-sized
# budgets bound worst-case latency and cost and prevent runaway generation.
TASK_MAX_TOKENS: dict[TaskType, int] = {
    TaskType.PRESCREEN: 150,
    TaskType.TRIAGE_SIMPLE: 300,
    TaskType.TRIAGE_COMPLEX: 400,
    TaskType.AGENT: 1024,
    TaskType.REPLY: 512,
    TaskType.RESEARCH: 1024,
    TaskType.GITHUB: 1024,
    TaskType.SLACK: 512,
}


TASK_RATIONALE: dict[TaskType, str] = {
    TaskType.PRESCREEN: (
        "A binary simple/complex sort over short text — runs on every ticket, "
        "so the cheapest fast model is the right gatekeeper."
    ),
    TaskType.TRIAGE_SIMPLE: (
        "Unambiguous tickets have an obvious category and team; the fast model "
        "classifies them accurately with minimal cost and latency."
    ),
    TaskType.TRIAGE_COMPLEX: (
        "Ambiguous, multi-issue, or high-severity tickets need real judgment "
        "about severity and escalation — worth the stronger reasoning model."
    ),
    TaskType.AGENT: (
        "Multi-step tool use — deciding which tools to call, in what order, and "
        "when to stop — is reasoning-heavy and runs on the smart model."
    ),
    TaskType.REPLY: (
        "Customer-facing prose: tone and clarity matter, so the smart model "
        "drafts the reply, streamed to the customer token by token."
    ),
    TaskType.RESEARCH: (
        "Grounding triage in current external facts (outages, error codes, "
        "third-party status) via the web-search server tool needs the smart "
        "model to run queries and synthesize cited results."
    ),
    TaskType.GITHUB: (
        "Driving GitHub issue tools (search/create/update) over MCP — choosing "
        "the right tool and arguments — is agentic work for the smart model."
    ),
    TaskType.SLACK: (
        "Posting a notification to a fixed channel is a single mechanical tool "
        "call — the fast model handles it cheaply."
    ),
}
