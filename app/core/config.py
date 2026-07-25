"""Centralized, validated application configuration.

All runtime configuration flows through the `Settings` object defined here.
Values are read from environment variables (and a local `.env` file during
development) and validated by Pydantic at import time, so a misconfigured
deployment fails fast with a descriptive error instead of at first use.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Anthropic / Claude API -------------------------------------------
    anthropic_api_key: str = Field(
        ...,
        alias="ANTHROPIC_API_KEY",
        description="Secret key for the Anthropic Messages API.",
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-5",
        alias="ANTHROPIC_MODEL",
        description="Legacy/default Claude model ID. Prefer the tiered models below.",
    )
    model_fast: str = Field(
        default="claude-haiku-4-5",
        alias="MODEL_FAST",
        description="Fast, low-cost model (Haiku) for lightweight tasks.",
    )
    model_smart: str = Field(
        default="claude-sonnet-4-5",
        alias="MODEL_SMART",
        description="Stronger-reasoning model (Sonnet) for complex tasks.",
    )
    max_tokens: int = Field(
        default=2048,
        alias="MAX_TOKENS",
        ge=1,
        description="Default output-token ceiling for a single response.",
    )

    # --- Web Search (built-in server tool) --------------------------------
    web_search_tool_type: str = Field(
        default="web_search_20250305",
        alias="WEB_SEARCH_TOOL_TYPE",
        description=(
            "Web search tool version. Use 'web_search_20250305' for Sonnet 4.5 / "
            "Haiku 4.5; newer models can use 'web_search_20260209'."
        ),
    )
    web_search_max_uses: int = Field(
        default=3,
        alias="WEB_SEARCH_MAX_USES",
        ge=1,
        description="Maximum web searches Claude may run per request (cost cap).",
    )

    # --- GitHub MCP server (Step 9) ---------------------------------------
    github_mcp_url: str = Field(
        default="https://api.githubcopilot.com/mcp/",
        alias="GITHUB_MCP_URL",
        description="Remote GitHub MCP server endpoint.",
    )
    github_token: str | None = Field(
        default=None,
        alias="GITHUB_TOKEN",
        description="GitHub Personal Access Token (repo/issues scope).",
    )
    github_repo: str | None = Field(
        default=None,
        alias="GITHUB_REPO",
        description="Optional owner/repo the agent operates on, e.g. octo/hello.",
    )
    github_mcp_beta: str = Field(
        default="mcp-client-2025-11-20",
        alias="GITHUB_MCP_BETA",
        description="Beta flag enabling the MCP connector.",
    )

    # --- Slack MCP server (Step 10) ---------------------------------------
    slack_mcp_url: str = Field(
        default="https://mcp.slack.com/mcp",
        alias="SLACK_MCP_URL",
        description="Remote Slack MCP server endpoint.",
    )
    slack_token: str | None = Field(
        default=None,
        alias="SLACK_TOKEN",
        description="Slack OAuth/bearer token for the MCP server.",
    )
    slack_mcp_beta: str = Field(
        default="mcp-client-2025-11-20",
        alias="SLACK_MCP_BETA",
        description="Beta flag enabling the MCP connector.",
    )

    # --- Application ------------------------------------------------------
    app_name: str = Field(default="customer-support-triager", alias="APP_NAME")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="ENVIRONMENT",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    @field_validator("anthropic_api_key")
    @classmethod
    def _key_must_look_valid(cls, value: str) -> str:
        """Guard against empty or placeholder keys slipping through."""
        if not value or value.strip() in {"", "your-api-key-here"}:
            raise ValueError(
                "ANTHROPIC_API_KEY is missing or is still the placeholder value. "
                "Set a real key in your .env file."
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, process-wide `Settings` instance.

    Using an LRU cache guarantees the environment is parsed and validated
    exactly once, and gives every module the same immutable configuration.
    """
    return Settings()  # type: ignore[call-arg]
