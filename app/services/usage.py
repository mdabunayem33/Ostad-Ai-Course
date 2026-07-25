"""Token-usage accounting and cost estimation.

Turns each response's `usage` object into a cost figure and accumulates them,
so the token optimizations can be measured rather than assumed. Cache reads
are billed at ~0.1x input price and cache writes at ~1.25x, matching the
prompt-caching economics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.domain.tasks import TaskType

logger = get_logger(__name__)

# USD per single token (input, output). Aligned with published per-MTok rates.
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 1.0 / 1_000_000, "output": 5.0 / 1_000_000},
    "claude-sonnet-4-5": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-sonnet-4-6": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-opus-4-5": {"input": 5.0 / 1_000_000, "output": 25.0 / 1_000_000},
}

CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25


def _task_name(task: Any) -> str:
    return getattr(task, "value", str(task))


def _tokens(usage: Any, name: str) -> int:
    return int(getattr(usage, name, 0) or 0)


def estimate_cost_from_counts(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Estimate USD cost for a call from raw token counts."""
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_read_tokens * rates["input"] * CACHE_READ_MULTIPLIER
        + cache_write_tokens * rates["input"] * CACHE_WRITE_MULTIPLIER
    )


def estimate_cost(model: str, usage: Any) -> float:
    """Estimate USD cost for a call from a response `usage` object."""
    return estimate_cost_from_counts(
        model,
        _tokens(usage, "input_tokens"),
        _tokens(usage, "output_tokens"),
        _tokens(usage, "cache_read_input_tokens"),
        _tokens(usage, "cache_creation_input_tokens"),
    )


@dataclass
class CallRecord:
    """Token usage and cost for a single API call."""

    task: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float


@dataclass
class UsageTracker:
    """Accumulates per-call usage for reporting and cost comparison."""

    records: list[CallRecord] = field(default_factory=list)

    def record(self, task: TaskType, model: str, usage: Any) -> CallRecord:
        rec = CallRecord(
            task=_task_name(task),
            model=model,
            input_tokens=_tokens(usage, "input_tokens"),
            output_tokens=_tokens(usage, "output_tokens"),
            cache_read_tokens=_tokens(usage, "cache_read_input_tokens"),
            cache_write_tokens=_tokens(usage, "cache_creation_input_tokens"),
            cost_usd=estimate_cost(model, usage),
        )
        self.records.append(rec)
        return rec

    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.records)

    def counterfactual_cost(self, model: str) -> float:
        """Total cost if every call had run on `model` (same token counts)."""
        return sum(
            estimate_cost_from_counts(
                model,
                r.input_tokens,
                r.output_tokens,
                r.cache_read_tokens,
                r.cache_write_tokens,
            )
            for r in self.records
        )

    def report(self, compare_model: str | None = None) -> str:
        lines = ["Task              Model              In   Out  CacheR   Cost($)"]
        for r in self.records:
            lines.append(
                f"{r.task:17s} {r.model:18s} {r.input_tokens:4d} "
                f"{r.output_tokens:4d} {r.cache_read_tokens:6d}  {r.cost_usd:.6f}"
            )
        total = self.total_cost()
        lines.append(f"{'TOTAL':17s} {'':18s} {'':4s} {'':4s} {'':6s}  {total:.6f}")
        if compare_model:
            alt = self.counterfactual_cost(compare_model)
            saved = alt - total
            lines.append(
                f"If all calls used {compare_model}: ${alt:.6f} "
                f"(routing saved ${saved:.6f}, {saved / alt * 100:.0f}%)"
                if alt > 0
                else ""
            )
        return "\n".join(line for line in lines if line)


def log_usage(task: TaskType, model: str, usage: Any) -> None:
    """Emit a single structured usage log line for a call."""
    logger.info(
        "usage task=%s model=%s in=%d out=%d cache_read=%d cache_write=%d cost=$%.6f",
        _task_name(task),
        model,
        _tokens(usage, "input_tokens"),
        _tokens(usage, "output_tokens"),
        _tokens(usage, "cache_read_input_tokens"),
        _tokens(usage, "cache_creation_input_tokens"),
        estimate_cost(model, usage),
    )
