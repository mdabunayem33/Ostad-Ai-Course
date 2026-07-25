"""End-to-end support pipeline.

Chains every capability built in Steps 2-11 into one flow:

    Support Message
        -> Classification            (triage: prescreen + routed, Steps 2/3/7)
        -> Parallel Tool Calls       (customer + order + subscription, Steps 4/5/11)
        -> GitHub MCP                (create/track an issue, Step 9)
        -> Slack MCP                 (notify the owning team, Step 10)
        -> Final Response            (streamed customer reply, Step 6)

External integrations (GitHub, Slack) are best-effort: if a token is not
configured, that stage is skipped cleanly so the whole pipeline still runs.
Sub-services are injectable so the orchestration is unit-tested offline.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

from app.core.logging import get_logger
from app.data import store
from app.mcp_server.server import check_subscription_logic
from app.services.github_mcp import GitHubMCPError, GitHubMCPService
from app.services.slack_mcp import SlackMCPError, SlackMCPService
from app.services.streaming import StreamingResponder
from app.services.triage import TriageDecision, TriageService
from app.services.usage import UsageTracker

logger = get_logger(__name__)


@dataclass
class Stage:
    """Outcome of a single pipeline stage."""

    name: str
    status: str  # "ok" | "skipped" | "error"
    detail: str = ""


@dataclass
class Enrichment:
    """Results of the parallel enrichment stage."""

    customer: dict[str, Any] | None = None
    order: dict[str, Any] | None = None
    subscription: dict[str, Any] | None = None
    wall_ms: float = 0.0


@dataclass
class PipelineResult:
    """The full result of running a support message through the pipeline."""

    message: str
    decision: TriageDecision
    enrichment: Enrichment
    github: Stage
    slack: Stage
    final_reply: str
    stages: list[Stage] = field(default_factory=list)


class SupportPipeline:
    """Orchestrates the end-to-end triage pipeline."""

    def __init__(
        self,
        triage: Any = None,
        github: Any = None,
        slack: Any = None,
        responder: Any = None,
        tracker: UsageTracker | None = None,
    ) -> None:
        self._tracker = tracker or UsageTracker()
        self._triage = triage or TriageService(tracker=self._tracker)
        self._github = github or GitHubMCPService()
        self._slack = slack or SlackMCPService()
        self._responder = responder or StreamingResponder()

    @property
    def tracker(self) -> UsageTracker:
        return self._tracker

    async def run(
        self,
        message: str,
        *,
        customer_id: str | None = None,
        order_id: str | None = None,
        email: str | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> PipelineResult:
        """Run a support message through all six stages."""
        logger.info("=== Support pipeline start ===")

        # 1. Classification (sync service, off the event loop).
        decision = await asyncio.to_thread(self._triage.triage, message)

        # 2. Parallel tool calls (customer + order + subscription concurrently).
        enrichment = await self._enrich(customer_id, email, order_id)

        # 3. GitHub MCP (best-effort).
        github = await asyncio.to_thread(self._github_stage, message, decision)

        # 4. Slack MCP (best-effort).
        slack = await asyncio.to_thread(self._slack_stage, decision, github)

        # 5. Final response (streamed reply).
        final_reply = await asyncio.to_thread(self._final_reply, message, on_token)

        logger.info("=== Support pipeline complete ===")
        return PipelineResult(
            message=message,
            decision=decision,
            enrichment=enrichment,
            github=github,
            slack=slack,
            final_reply=final_reply,
            stages=[
                Stage("classification", "ok", decision.result.assigned_team),
                Stage("enrichment", "ok", f"{enrichment.wall_ms:.0f}ms"),
                github,
                slack,
                Stage("final_response", "ok"),
            ],
        )

    # -- Stage 2: parallel enrichment --------------------------------------

    async def _enrich(
        self, customer_id: str | None, email: str | None, order_id: str | None
    ) -> Enrichment:
        async def _customer() -> dict[str, Any] | None:
            if not (customer_id or email):
                return None
            return await store.afind_customer(customer_id=customer_id, email=email)

        async def _order() -> dict[str, Any] | None:
            if not order_id:
                return None
            return await store.afind_order(order_id)

        async def _subscription() -> dict[str, Any] | None:
            if not customer_id:
                return None
            # The subscription tool is served by our custom MCP server (Step 11);
            # its logic runs here concurrently with the other lookups.
            return await asyncio.to_thread(check_subscription_logic, customer_id)

        start = perf_counter()
        customer, order, subscription = await asyncio.gather(
            _customer(), _order(), _subscription()
        )
        wall_ms = (perf_counter() - start) * 1000
        logger.info("Parallel enrichment completed in %.0fms", wall_ms)
        return Enrichment(customer=customer, order=order, subscription=subscription, wall_ms=wall_ms)

    # -- Stage 3: GitHub ---------------------------------------------------

    def _github_stage(self, message: str, decision: TriageDecision) -> Stage:
        res = decision.result
        warranted = res.urgency in ("high", "critical") or res.topic == "technical"
        if not warranted:
            return Stage("github", "skipped", "Not warranted (low urgency, non-technical).")
        if not self._github.describe_connection()["token_configured"]:
            return Stage("github", "skipped", "GITHUB_TOKEN not configured.")

        subject = " ".join(message.split())[:70]
        instruction = (
            "Search open issues for an existing report of this problem. If none "
            f"exists, create an issue titled '[{res.urgency}] {subject}' with a "
            "body summarizing the problem and this triage "
            f"(urgency={res.urgency}, topic={res.topic}, team={res.assigned_team}). "
            "Then report the issue number or URL."
        )
        try:
            result = self._github.run(instruction)
            detail = result.summary or f"{len(result.tool_calls)} tool call(s)."
            return Stage("github", "ok", detail)
        except GitHubMCPError as exc:
            return Stage("github", "error", str(exc))

    # -- Stage 4: Slack ----------------------------------------------------

    def _slack_stage(self, decision: TriageDecision, github: Stage) -> Stage:
        res = decision.result
        if not self._slack.describe_connection()["token_configured"]:
            return Stage("slack", "skipped", "SLACK_TOKEN not configured.")

        note = (
            f"[{res.urgency.upper()}] New {res.topic} ticket routed to "
            f"{res.assigned_team}. Summary: {res.reason}"
        )
        if github.status == "ok":
            note += f" (GitHub: {github.detail[:120]})"
        try:
            result = self._slack.notify_team(res.assigned_team, note)
            return Stage("slack", "ok", f"Posted to {result.channel}.")
        except SlackMCPError as exc:
            return Stage("slack", "error", str(exc))

    # -- Stage 5: final response -------------------------------------------

    def _final_reply(
        self, message: str, on_token: Callable[[str], None] | None
    ) -> str:
        result = self._responder.stream_reply(message, on_token=on_token)
        return result.text
