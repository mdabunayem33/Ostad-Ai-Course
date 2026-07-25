"""Triage service: two-stage, model-routed, token-optimized classification.

Stage 1 (prescreen, fast model): simple vs complex.
Stage 2 (triage, routed): fast model for simple tickets, smart model for complex.

Every call applies the Step 7 optimizations: the right-sized model per task
(routing), the stable system prompt sent as a cached block (prompt caching),
and a per-task output budget (max_tokens). Usage is logged and, optionally,
accumulated in a UsageTracker for cost reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.models import Complexity, PrescreenResult, TriageResult
from app.domain.tasks import TaskType
from app.prompts.prescreen import (
    build_prescreen_system_prompt,
    build_prescreen_user_prompt,
)
from app.prompts.triage import build_system_prompt, build_user_prompt
from app.services.claude_client import get_claude_client
from app.services.model_router import ModelRouter
from app.services.usage import UsageTracker, log_usage
from app.utils.caching import to_cached_system
from app.utils.parsing import ParseError, parse_json_object

logger = get_logger(__name__)


class TriageError(Exception):
    """Raised when a message cannot be classified into a valid result."""


@dataclass(frozen=True)
class TriageDecision:
    """A triage result plus the routing metadata that produced it."""

    result: TriageResult
    complexity: Complexity
    prescreen_model: str
    triage_task: TaskType
    triage_model: str


class TriageService:
    """Classifies support messages with cost-aware routing and caching."""

    def __init__(self, tracker: UsageTracker | None = None) -> None:
        self._client = get_claude_client()
        self._settings = get_settings()
        self._router = ModelRouter()
        self._tracker = tracker
        self._triage_system_prompt = build_system_prompt()
        self._prescreen_system_prompt = build_prescreen_system_prompt()

    # -- Public API --------------------------------------------------------

    def classify(self, message: str) -> TriageResult:
        """Classify a message and return just the validated result."""
        return self.triage(message).result

    def triage(self, message: str) -> TriageDecision:
        """Run the full prescreen + routed-triage pipeline."""
        if not message or not message.strip():
            raise TriageError("Cannot classify an empty message.")

        logger.info("Triage pipeline started (%d chars)", len(message))

        prescreen = self._prescreen(message)
        triage_task = (
            TaskType.TRIAGE_COMPLEX
            if prescreen.complexity == Complexity.COMPLEX
            else TaskType.TRIAGE_SIMPLE
        )
        result = self._run_triage(message, triage_task)

        logger.info(
            "Triage: urgency=%s topic=%s team=%s (%s)",
            result.urgency,
            result.topic,
            result.assigned_team,
            self._router.model_for(triage_task),
        )

        return TriageDecision(
            result=result,
            complexity=Complexity(prescreen.complexity),
            prescreen_model=self._router.model_for(TaskType.PRESCREEN),
            triage_task=triage_task,
            triage_model=self._router.model_for(triage_task),
        )

    # -- Stages ------------------------------------------------------------

    def _prescreen(self, message: str) -> PrescreenResult:
        text = self._complete(
            TaskType.PRESCREEN,
            self._prescreen_system_prompt,
            build_prescreen_user_prompt(message),
        )
        return self._validate(text, PrescreenResult)

    def _run_triage(self, message: str, task: TaskType) -> TriageResult:
        text = self._complete(
            task,
            self._triage_system_prompt,
            build_user_prompt(message),
        )
        return self._validate(text, TriageResult)

    # -- Helpers -----------------------------------------------------------

    def _complete(self, task: TaskType, system_prompt: str, user_content: str) -> str:
        """One Messages API call, applying routing, caching, and budgeting."""
        model = self._router.model_for(task)             # optimization #1: routing
        max_tokens = self._router.max_tokens_for(task)   # optimization #3: budget

        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=to_cached_system(system_prompt),      # optimization #2: caching
            messages=[{"role": "user", "content": user_content}],
        )

        log_usage(task, response.model, response.usage)
        if self._tracker is not None:
            self._tracker.record(task, response.model, response.usage)

        parts = [block.text for block in response.content if block.type == "text"]
        text = "".join(parts).strip()
        if not text:
            raise TriageError(f"Model {model} returned no text content.")
        return text

    @staticmethod
    def _validate(text: str, model_cls: type[BaseModel]):
        try:
            payload = parse_json_object(text)
        except ParseError as exc:
            raise TriageError(str(exc)) from exc
        try:
            return model_cls.model_validate(payload)
        except ValidationError as exc:
            raise TriageError(f"{model_cls.__name__} validation failed: {exc}") from exc
