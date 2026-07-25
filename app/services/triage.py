"""Triage service: a two-stage, model-routed classification pipeline.

Stage 1 (prescreen, fast model): decide simple vs complex.
Stage 2 (triage, routed): classify with the fast model for simple tickets and
the smart model for complex ones.

The `ModelRouter` owns every model choice; this service just asks it which
model to use for each task. `classify()` remains the Step 2 contract (returns
a `TriageResult`); `triage()` additionally reports the routing decision.
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
    """Classifies support messages with cost-aware model routing."""

    def __init__(self) -> None:
        self._client = get_claude_client()
        self._settings = get_settings()
        self._router = ModelRouter()
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

        # Stage 1: lightweight prescreen on the fast model.
        prescreen = self._prescreen(message)
        prescreen_model = self._router.model_for(TaskType.PRESCREEN)

        # Stage 2: route the triage task by complexity.
        triage_task = (
            TaskType.TRIAGE_COMPLEX
            if prescreen.complexity == Complexity.COMPLEX
            else TaskType.TRIAGE_SIMPLE
        )
        triage_model = self._router.model_for(triage_task)
        logger.info(
            "Prescreen=%s -> task=%s -> model=%s",
            prescreen.complexity,
            triage_task.value,
            triage_model,
        )

        result = self._run_triage(message, triage_model)
        logger.info(
            "Triage: urgency=%s topic=%s team=%s",
            result.urgency,
            result.topic,
            result.assigned_team,
        )

        return TriageDecision(
            result=result,
            complexity=Complexity(prescreen.complexity),
            prescreen_model=prescreen_model,
            triage_task=triage_task,
            triage_model=triage_model,
        )

    # -- Stages ------------------------------------------------------------

    def _prescreen(self, message: str) -> PrescreenResult:
        """Stage 1: fast simple/complex judgment."""
        model = self._router.model_for(TaskType.PRESCREEN)
        text = self._complete(
            model=model,
            system_prompt=self._prescreen_system_prompt,
            user_content=build_prescreen_user_prompt(message),
        )
        return self._validate(text, PrescreenResult)

    def _run_triage(self, message: str, model: str) -> TriageResult:
        """Stage 2: full classification on the routed model."""
        text = self._complete(
            model=model,
            system_prompt=self._triage_system_prompt,
            user_content=build_user_prompt(message),
        )
        return self._validate(text, TriageResult)

    # -- Helpers -----------------------------------------------------------

    def _complete(self, model: str, system_prompt: str, user_content: str) -> str:
        """Single Messages API call; return concatenated text content."""
        response = self._client.messages.create(
            model=model,
            max_tokens=self._settings.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        parts = [block.text for block in response.content if block.type == "text"]
        text = "".join(parts).strip()
        if not text:
            raise TriageError(f"Model {model} returned no text content.")
        return text

    @staticmethod
    def _validate(text: str, model_cls: type[BaseModel]):
        """Parse JSON from model output and validate against a Pydantic model."""
        try:
            payload = parse_json_object(text)
        except ParseError as exc:
            raise TriageError(str(exc)) from exc
        try:
            return model_cls.model_validate(payload)
        except ValidationError as exc:
            raise TriageError(
                f"{model_cls.__name__} validation failed: {exc}"
            ) from exc
