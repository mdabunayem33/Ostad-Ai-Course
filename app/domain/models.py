"""Domain models for support-ticket triage.

These enums and models are the single contract for what a triage result may
contain. The classifier is constrained to these exact values, and every
response is validated against `TriageResult` before it leaves the service —
so downstream code (routing, dashboards, MCP tools) can trust the shape.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Complexity(str, Enum):
    """Whether a ticket is a routine sort or needs deeper reasoning."""

    SIMPLE = "simple"
    COMPLEX = "complex"


class Urgency(str, Enum):
    """How quickly the ticket needs a human response."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Topic(str, Enum):
    """The subject-matter category of the ticket."""

    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    PRODUCT_FEEDBACK = "product_feedback"
    GENERAL = "general"


class Team(str, Enum):
    """The internal team that should own the ticket."""

    BILLING_TEAM = "billing_team"
    ENGINEERING = "engineering"
    ACCOUNT_MANAGEMENT = "account_management"
    CUSTOMER_SUCCESS = "customer_success"
    GENERAL_SUPPORT = "general_support"


class PrescreenResult(BaseModel):
    """Validated output of the lightweight prescreen pass (Haiku)."""

    complexity: Complexity = Field(
        ..., description="Whether the ticket is simple or complex."
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Brief justification for the complexity judgment.",
    )

    model_config = {"use_enum_values": True}


class TriageResult(BaseModel):
    """Validated classification of a single support message."""

    urgency: Urgency = Field(..., description="Assessed urgency of the ticket.")
    topic: Topic = Field(..., description="Subject-matter category.")
    assigned_team: Team = Field(..., description="Team that should own the ticket.")
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="One-sentence justification for the classification.",
    )

    model_config = {"use_enum_values": True}
