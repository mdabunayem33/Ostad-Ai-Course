"""Application entrypoint — Step 12 end-to-end pipeline demo.

Runs one support message through the full pipeline:
    Classification -> Parallel Tool Calls -> GitHub MCP -> Slack MCP -> Final Response
and prints a stage-by-stage report plus a token-usage/cost summary.

GitHub and Slack stages are skipped cleanly if their tokens are not configured.

Usage:
    venv/Scripts/python.exe main.py
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.services.orchestrator import SupportPipeline

logger = get_logger(__name__)

TICKET = {
    "message": (
        "Our production checkout has been throwing 500 errors ever since your "
        "latest update this morning. It's blocking all customer purchases and "
        "we're losing sales by the minute. Please help urgently."
    ),
    "customer_id": "CUST-001",
    "order_id": "ORD-1001",
}


async def run() -> None:
    pipeline = SupportPipeline()

    print("=" * 70)
    print("SUPPORT MESSAGE")
    print("=" * 70)
    print(TICKET["message"])
    print(f"\n(customer_id={TICKET['customer_id']}, order_id={TICKET['order_id']})\n")

    result = await pipeline.run(
        TICKET["message"],
        customer_id=TICKET["customer_id"],
        order_id=TICKET["order_id"],
        on_token=None,  # final reply captured; set to a printer to stream live
    )

    d = result.decision
    print("=" * 70)
    print("1. CLASSIFICATION")
    print("=" * 70)
    print(f"  urgency       : {d.result.urgency}")
    print(f"  topic         : {d.result.topic}")
    print(f"  assigned_team : {d.result.assigned_team}")
    print(f"  reason        : {d.result.reason}")
    print(f"  complexity    : {d.complexity}  (prescreen: {d.prescreen_model})")
    print(f"  triage model  : {d.triage_model}")

    e = result.enrichment
    print("\n" + "=" * 70)
    print(f"2. PARALLEL TOOL CALLS  (wall time {e.wall_ms:.0f}ms)")
    print("=" * 70)
    print(f"  customer     : {e.customer}")
    print(f"  order        : {e.order}")
    print(f"  subscription : {e.subscription}")

    print("\n" + "=" * 70)
    print("3. GITHUB MCP")
    print("=" * 70)
    print(f"  [{result.github.status}] {result.github.detail}")

    print("\n" + "=" * 70)
    print("4. SLACK MCP")
    print("=" * 70)
    print(f"  [{result.slack.status}] {result.slack.detail}")

    print("\n" + "=" * 70)
    print("5. FINAL RESPONSE (to customer)")
    print("=" * 70)
    print(result.final_reply)

    print("\n" + "=" * 70)
    print("TOKEN USAGE & COST")
    print("=" * 70)
    print(pipeline.tracker.report(compare_model="claude-sonnet-4-5"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
