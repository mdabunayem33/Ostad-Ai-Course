"""Offline tests for the end-to-end support pipeline.

Fakes stand in for the triage, GitHub, Slack, and streaming services so the
orchestration logic (stage sequencing, graceful skips, parallel enrichment) is
verified without any network access.

Run:
    venv/Scripts/python.exe -m unittest -v
"""

from __future__ import annotations

import asyncio
import os
import unittest
from typing import Any

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-dummy-test")

from app.domain.models import Team, Topic, TriageResult, Urgency  # noqa: E402
from app.domain.tasks import TaskType  # noqa: E402
from app.services.orchestrator import SupportPipeline  # noqa: E402
from app.services.triage import TriageDecision  # noqa: E402


def _decision(urgency: Urgency, topic: Topic, team: Team) -> TriageDecision:
    return TriageDecision(
        result=TriageResult(
            urgency=urgency, topic=topic, assigned_team=team, reason="test reason"
        ),
        complexity="complex",
        prescreen_model="claude-haiku-4-5",
        triage_task=TaskType.TRIAGE_COMPLEX,
        triage_model="claude-sonnet-4-5",
    )


class FakeTriage:
    def __init__(self, decision: TriageDecision) -> None:
        self._decision = decision

    def triage(self, message: str) -> TriageDecision:
        return self._decision


class FakeGitHub:
    def __init__(self, token: bool, summary: str = "Created issue #42") -> None:
        self._token = token
        self._summary = summary
        self.ran = False

    def describe_connection(self) -> dict[str, Any]:
        return {"token_configured": self._token}

    def run(self, instruction: str) -> Any:
        self.ran = True
        return type("R", (), {"summary": self._summary, "tool_calls": [1]})()


class FakeSlack:
    def __init__(self, token: bool) -> None:
        self._token = token
        self.posted_to: str | None = None

    def describe_connection(self) -> dict[str, Any]:
        return {"token_configured": self._token}

    def notify_team(self, team: Any, message: str) -> Any:
        from app.services.slack_mcp import SlackMCPService

        channel = SlackMCPService.channel_for_team(team)
        self.posted_to = channel
        return type("R", (), {"channel": channel})()


class FakeResponder:
    def stream_reply(self, message: str, on_token: Any = None) -> Any:
        return type("R", (), {"text": "Thanks for reaching out — we're on it."})()


def _pipeline(github_token: bool, slack_token: bool) -> tuple[SupportPipeline, FakeGitHub, FakeSlack]:
    github = FakeGitHub(token=github_token)
    slack = FakeSlack(token=slack_token)
    pipeline = SupportPipeline(
        triage=FakeTriage(_decision(Urgency.HIGH, Topic.TECHNICAL, Team.ENGINEERING)),
        github=github,
        slack=slack,
        responder=FakeResponder(),
    )
    return pipeline, github, slack


class PipelineFlowTests(unittest.TestCase):
    def test_full_flow_when_everything_configured(self) -> None:
        pipeline, github, slack = _pipeline(github_token=True, slack_token=True)
        result = asyncio.run(
            pipeline.run(
                "Production 500 errors after your update — checkout is down.",
                customer_id="CUST-001",
                order_id="ORD-1001",
            )
        )
        # Classification
        self.assertEqual(result.decision.result.assigned_team, "engineering")
        # Parallel enrichment pulled all three sources
        self.assertEqual(result.enrichment.customer["customer_id"], "CUST-001")
        self.assertEqual(result.enrichment.order["order_id"], "ORD-1001")
        self.assertTrue(result.enrichment.subscription["found"])
        # GitHub + Slack both ran
        self.assertEqual(result.github.status, "ok")
        self.assertTrue(github.ran)
        self.assertEqual(result.slack.status, "ok")
        self.assertEqual(slack.posted_to, "#engineering")
        # Final response produced
        self.assertIn("we're on it", result.final_reply)

    def test_integrations_skip_gracefully_when_unconfigured(self) -> None:
        pipeline, github, slack = _pipeline(github_token=False, slack_token=False)
        result = asyncio.run(
            pipeline.run(
                "Production 500 errors after your update.",
                customer_id="CUST-001",
            )
        )
        # Core stages still succeed
        self.assertEqual(result.decision.result.assigned_team, "engineering")
        self.assertTrue(result.final_reply)
        # External stages skipped cleanly (no exceptions)
        self.assertEqual(result.github.status, "skipped")
        self.assertFalse(github.ran)
        self.assertEqual(result.slack.status, "skipped")

    def test_github_skipped_when_not_warranted(self) -> None:
        github = FakeGitHub(token=True)
        pipeline = SupportPipeline(
            triage=FakeTriage(_decision(Urgency.LOW, Topic.GENERAL, Team.GENERAL_SUPPORT)),
            github=github,
            slack=FakeSlack(token=True),
            responder=FakeResponder(),
        )
        result = asyncio.run(pipeline.run("How do I change my email?"))
        self.assertEqual(result.github.status, "skipped")
        self.assertFalse(github.ran)  # low-urgency general ticket: no issue filed


class EnrichmentTests(unittest.TestCase):
    def test_enrichment_gathers_sources_and_runs_in_parallel(self) -> None:
        pipeline, _, _ = _pipeline(github_token=False, slack_token=False)
        enrichment = asyncio.run(
            pipeline._enrich(customer_id="CUST-002", email=None, order_id="ORD-1002")
        )
        self.assertEqual(enrichment.customer["customer_id"], "CUST-002")
        self.assertEqual(enrichment.order["order_id"], "ORD-1002")
        self.assertEqual(enrichment.subscription["status"], "past_due")
        # Three ~0.5s lookups in parallel finish well under the ~1.5s sequential sum.
        self.assertLess(enrichment.wall_ms, 1200)


if __name__ == "__main__":
    unittest.main()
