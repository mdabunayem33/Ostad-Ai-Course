"""Model routing: pick the right Claude model for each task.

The router is the one place that decides *which* model runs a given task. It
maps a `TaskType` to a `ModelTier` (the policy in `domain/tasks.py`) and then
resolves that tier to a concrete model ID from configuration. This keeps the
Haiku-vs-Sonnet decision explicit, centralized, and easy to audit.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tasks import (
    TASK_MAX_TOKENS,
    TASK_RATIONALE,
    TASK_TIERS,
    ModelTier,
    TaskType,
)

logger = get_logger(__name__)


class ModelRouter:
    """Resolves tasks and tiers to concrete Claude model IDs."""

    def __init__(self) -> None:
        settings = get_settings()
        self._tier_to_model: dict[ModelTier, str] = {
            ModelTier.FAST: settings.model_fast,
            ModelTier.SMART: settings.model_smart,
        }

    def tier_for(self, task: TaskType) -> ModelTier:
        """Return the model tier assigned to a task."""
        return TASK_TIERS[task]

    def model_for(self, task: TaskType) -> str:
        """Return the concrete model ID that should run a task."""
        tier = self.tier_for(task)
        model = self._tier_to_model[tier]
        logger.debug("Routing task=%s -> tier=%s -> model=%s", task, tier, model)
        return model

    def model_for_tier(self, tier: ModelTier) -> str:
        """Return the concrete model ID for a tier."""
        return self._tier_to_model[tier]

    def max_tokens_for(self, task: TaskType) -> int:
        """Return the per-task output-token budget (optimization #3)."""
        return TASK_MAX_TOKENS[task]

    def explain(self, task: TaskType) -> str:
        """Return a human-readable justification for a task's model choice."""
        tier = self.tier_for(task)
        model = self._tier_to_model[tier]
        return (
            f"{task.value}: {tier.value} tier ({model}) — {TASK_RATIONALE[task]}"
        )
