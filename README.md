# Customer Support Triager

A production-grade, AI-powered customer-support triage system built on the
**Anthropic Claude API**. It classifies incoming support messages, enriches them
with customer data via parallel tool calls, files and tracks issues on GitHub,
notifies the right team on Slack, and drafts a customer reply — all through one
orchestrated pipeline.

```
Support Message
    → Classification            (urgency · topic · assigned team)
    → Parallel Tool Calls       (customer · order · subscription, concurrently)
    → GitHub MCP                (search / create / update issues)
    → Slack MCP                 (notify #support / #billing / #engineering)
    → Final Response            (streamed customer reply)
```

---

## Features

| Capability | Where |
|---|---|
| **Messages API** classification into structured JSON | `app/services/triage.py`, `app/domain/models.py` |
| **Task-based model routing** — Haiku for light tasks, Sonnet for reasoning | `app/services/model_router.py`, `app/domain/tasks.py` |
| **Tool Use** — `lookup_customer`, `lookup_order`, `create_ticket` | `app/tools/`, `app/services/agent.py` |
| **Parallel Tool Use** with `asyncio` | `app/services/async_agent.py`, `app/services/orchestrator.py` |
| **Streaming** responses (token-by-token) | `app/services/streaming.py` |
| **Token optimization** — routing, prompt caching, output budgets, cost accounting | `app/utils/caching.py`, `app/services/usage.py`, `app/domain/tasks.py` |
| **Built-in server tool** — Web Search | `app/services/research.py` |
| **GitHub MCP** — search / create / update issues | `app/services/github_mcp.py` |
| **Slack MCP** — post to a fixed set of channels | `app/services/slack_mcp.py` |
| **Custom MCP server** (HTTP) — `check_customer_subscription` | `app/mcp_server/server.py` |
| **End-to-end orchestration** | `app/services/orchestrator.py` |

---

## Architecture

Clean, layered architecture with a strict dependency direction
(`services → prompts / tools / domain → core`; nothing in `core`/`domain`
depends upward):

```
app/
├── core/            # config (validated settings) + logging  [cross-cutting]
├── domain/          # enums, models, task taxonomy           [contracts]
├── prompts/         # prompt builders per capability
├── tools/           # client-side tools + registry
├── data/            # mock backends (customers, orders, subscriptions, tickets)
├── mcp_server/      # custom HTTP MCP server
├── utils/           # parsing + caching helpers
└── services/        # orchestration + external integrations
    ├── claude_client.py   # sync + async Anthropic clients
    ├── model_router.py    # task → model + token budget
    ├── triage.py          # classification pipeline
    ├── agent.py           # tool-use loop (sequential)
    ├── async_agent.py     # tool-use loop (parallel)
    ├── streaming.py       # streamed replies
    ├── research.py        # web-search-grounded research
    ├── github_mcp.py      # GitHub issues over MCP
    ├── slack_mcp.py       # Slack notifications over MCP
    ├── usage.py           # token/cost accounting
    └── orchestrator.py    # the full pipeline
tests/               # unittest suite (offline; fakes + real HTTP MCP test)
main.py              # end-to-end pipeline demo
```

---

## Setup

### 1. Prerequisites
- Python 3.12+ (developed on 3.14)
- An Anthropic API key

### 2. Install

```bash
python -m venv venv
# Windows PowerShell:  .\venv\Scripts\Activate.ps1
# Git Bash:            source venv/Scripts/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and set your credentials:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API access |
| `MODEL_FAST` / `MODEL_SMART` | — | Tiered models (defaults: Haiku 4.5 / Sonnet 4.5) |
| `WEB_SEARCH_TOOL_TYPE` | — | Web search variant |
| `GITHUB_TOKEN` / `GITHUB_REPO` | for GitHub | PAT + `owner/repo` |
| `SLACK_TOKEN` | for Slack | Slack token with `chat:write` |

GitHub and Slack are optional — the pipeline skips those stages cleanly if the
tokens are absent.

---

## Running

### Full pipeline demo
```bash
venv/Scripts/python.exe main.py
```
Runs one support ticket through all six stages and prints a stage report plus a
token-usage / cost summary.

### Custom MCP server (standalone)
```bash
venv/Scripts/python.exe -m app.mcp_server.server
# serves at http://127.0.0.1:8050/mcp
```

### Tests
```bash
venv/Scripts/python.exe -m unittest discover -s tests -v
```
All tests run offline (no API key needed) — external services are faked, and the
custom MCP server is tested over real HTTP.

---

## Model & cost strategy

Every task is routed to the cheapest model that does it well (see
`app/domain/tasks.py`):

- **Haiku** — prescreen, simple triage, Slack notifications (mechanical work).
- **Sonnet** — complex triage, tool-use agent, replies, research, GitHub (reasoning).

Combined with **prompt caching** and **per-task output budgets**, this keeps cost
and latency low. Actual usage and cost are reported by `UsageTracker` after each
run.

---

## Tech stack
`anthropic` · `mcp` · `fastapi`/`starlette` · `uvicorn` · `pydantic` /
`pydantic-settings` · `httpx` · `python-dotenv` · `rich`

## License
Academic assignment — for educational use.
