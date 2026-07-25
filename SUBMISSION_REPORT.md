# Submission Report — Customer Support Triager

**Project:** Production-ready Customer Support Triager on the Anthropic Claude API
**Language:** Python
**Architecture:** Clean, layered (core → domain → services), fully test-backed

---

## 1. Overview

This project implements an end-to-end customer-support triage system that takes a
raw support message and drives it through classification, data enrichment, issue
tracking, team notification, and a customer reply — orchestrated as a single
pipeline. It was built incrementally over 12 steps, each adding one capability on
a stable, clean-architecture foundation.

**Pipeline:**

```
Support Message → Classification → Parallel Tool Calls → GitHub MCP → Slack MCP → Final Response
```

---

## 2. Requirements coverage

| # | Requirement | Status | Implementation |
|---|---|---|---|
| 1 | Python only | ✅ | Entire codebase |
| 2 | Anthropic Messages API | ✅ | `services/triage.py`, `services/streaming.py` |
| 3 | Tool Use | ✅ | `tools/` (`lookup_customer`, `lookup_order`, `create_ticket`) + `services/agent.py` |
| 4 | Parallel Tool Use | ✅ | `services/async_agent.py`, `orchestrator._enrich` (`asyncio.gather`) |
| 5 | Streaming | ✅ | `services/streaming.py` (`messages.stream` + `text_stream`) |
| 6 | Token Optimization | ✅ | Routing + prompt caching + output budgets + cost accounting |
| 7 | Built-in Server Tools | ✅ | `services/research.py` (Web Search) |
| 8 | GitHub MCP | ✅ | `services/github_mcp.py` (search / create / update issues) |
| 9 | Slack MCP | ✅ | `services/slack_mcp.py` (#support / #billing / #engineering) |
| 10 | Custom MCP Server | ✅ | `app/mcp_server/server.py` (HTTP, `check_customer_subscription`) |
| 11 | Final end-to-end integration | ✅ | `services/orchestrator.py` + `main.py` |

---

## 3. Step-by-step summary

1. **Foundation** — validated config (`pydantic-settings`), structured logging, env isolation, reproducible `requirements.txt`.
2. **Triage logic** — classify a message into `Urgency` / `Topic` / `Team` as validated JSON via the Messages API.
3. **Model routing** — a `ModelRouter` maps each task to a model tier: **Haiku** for lightweight tasks (prescreen, simple triage), **Sonnet** for complex reasoning.
4. **Tool Use** — three client-side tools with a registry and a manual agentic loop; failed tools return recoverable `is_error` results.
5. **Parallel Tool Use** — an async agent runs independent tool calls concurrently with `asyncio.gather` (measured ~2× speedup on two lookups).
6. **Streaming** — token-by-token replies with a pluggable `on_token` callback (sync + async).
7. **Token optimization** — three techniques (below) plus a `UsageTracker` that reports real cost and a routing-savings counterfactual.
8. **Web Search** — the built-in server tool grounds triage in current external facts (outages, error codes), returning cited context notes.
9. **GitHub MCP** — issues managed via Anthropic's server-side MCP connector; a tool allowlist restricts Claude to exactly search/create/update.
10. **Slack MCP** — notifications restricted to three channels by a tool allowlist **and** an in-code channel guardrail; `notify_team` maps a triage team to its channel.
11. **Custom MCP server** — a standalone FastMCP HTTP service exposing `check_customer_subscription`, tested over real HTTP.
12. **Integration** — the `SupportPipeline` chains all six stages, with best-effort external stages and a full token-usage report.

---

## 4. Token optimization (three techniques + impact)

| Technique | Where | Impact on cost | Latency | Quality |
|---|---|---|---|---|
| **Model right-sizing** (tiered routing) | `model_router.py`, `tasks.py` | Large — lightweight tasks run on Haiku (~3–5× cheaper than Sonnet) | Lower for routed-down tasks | Neutral: simple tasks handled well by Haiku; hard tasks stay on Sonnet |
| **Prompt caching** | `utils/caching.py` | Up to ~90% off the cached prefix on repeat calls (reads ≈ 0.1× input) | Lower TTFT on cache hits | Identical (same prompt) |
| **Per-task output budgets** | `tasks.py` (`TASK_MAX_TOKENS`) | Bounds worst-case output cost; prevents runaway generation | Caps worst-case latency | Neutral when budget ≥ needed output |

Measurement is provided by `services/usage.py` (`UsageTracker`), which prints
per-call tokens/cost and a "if everything used Sonnet" comparison to quantify the
routing savings.

> Caching note: the API caches a prefix only once it exceeds the model's minimum
> cacheable size. The mechanism is wired via `cache_control`; the benefit scales
> with the size of the shared prefix and is verifiable through
> `usage.cache_read_input_tokens`.

---

## 5. Testing

- **Framework:** stdlib `unittest` (no extra dependency).
- **Isolation:** external services (Claude, GitHub, Slack) are faked; tests run fully offline.
- **Real HTTP:** the custom MCP server is booted with `uvicorn` on a free port and driven by a genuine MCP `streamable-http` client (`initialize` → `list_tools` → `call_tool`).
- **Result:** **27 tests, all passing.**

```
venv/Scripts/python.exe -m unittest discover -s tests
# Ran 27 tests ... OK
```

Coverage highlights: triage parsing/validation, model routing, tool dispatch and
error handling, parallel-execution speedup, MCP payload/allowlist construction,
Slack channel guardrail, GitHub/Slack `pause_turn` resumption, the custom MCP
server over HTTP, and full pipeline sequencing with graceful skips.

---

## 6. Design decisions

- **Clean architecture / strict dependency direction** — `services` depend on `domain`/`core`, never the reverse; the custom MCP server has **zero** Anthropic dependency.
- **Everything routed through one place** — model + budget choices live only in `ModelRouter` + `tasks.py`.
- **Graceful degradation** — GitHub/Slack stages skip cleanly when unconfigured, so the system runs anywhere.
- **Safety by construction** — MCP tool allowlists + the in-code Slack channel guardrail + enum-constrained tool schemas prevent out-of-policy actions.
- **Observability** — structured logging and per-call token/cost accounting throughout.

---

## 7. How to run

```bash
# install
python -m venv venv && pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (+ optional GitHub/Slack)

# full pipeline
venv/Scripts/python.exe main.py

# custom MCP server
venv/Scripts/python.exe -m app.mcp_server.server

# tests
venv/Scripts/python.exe -m unittest discover -s tests -v
```
