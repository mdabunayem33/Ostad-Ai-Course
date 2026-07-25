"""Application entrypoint — Step 9 GitHub MCP demo.

Prints the MCP connection configuration, then (if GITHUB_TOKEN and GITHUB_REPO
are set) asks Claude to search for a login-related issue and create one if none
exists — exercising the search/create/update issue tools over MCP.

Usage:
    venv/Scripts/python.exe main.py
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.github_mcp import GitHubMCPError, GitHubMCPService

logger = get_logger(__name__)

INSTRUCTION = (
    "Search the repository's open issues for anything about login failures. "
    "If you find no matching open issue, create one titled 'Login failures "
    "reported by customers' with a short body noting that multiple customers "
    "report failed logins. Then summarize what you did."
)


def main() -> None:
    service = GitHubMCPService()

    print("=== GitHub MCP connection ===")
    for key, value in service.describe_connection().items():
        print(f"  {key:16s}: {value}")
    print()

    if not service.describe_connection()["token_configured"]:
        print("GITHUB_TOKEN is not set. Add a PAT (and GITHUB_REPO) to .env to run live.")
        print("The connection above shows how Claude is wired to the GitHub MCP server.")
        return

    print("=== Instruction ===")
    print(INSTRUCTION)
    print()

    try:
        result = service.run(INSTRUCTION)
    except GitHubMCPError as exc:
        print(f"ERROR: {exc}")
        return

    print("=== GitHub tools Claude called ===")
    for i, call in enumerate(result.tool_calls, start=1):
        print(f"{i}. {call.name}  input={call.input}")
    if not result.tool_calls:
        print("(none)")
    print()

    print("=== Summary ===")
    print(result.summary)
    print(f"\n[model: {result.model}]")


if __name__ == "__main__":
    main()
