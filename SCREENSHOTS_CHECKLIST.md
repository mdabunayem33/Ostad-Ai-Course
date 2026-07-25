# Screenshots Checklist

Capture these screenshots to demonstrate every feature working. Each item lists
the command to run and what the screenshot must show. Items marked **(offline)**
need no API key; **(key)** needs `ANTHROPIC_API_KEY`; **(GitHub)** / **(Slack)**
need those tokens configured.

---

## Setup & foundation

- [ ] **1. Environment install** — `pip install -r requirements.txt` completing successfully; show `python --version`.
- [ ] **2. Project structure** — an editor/file-tree view of the `app/` layers (`core`, `domain`, `services`, `tools`, `mcp_server`, `prompts`, `utils`, `data`) and `tests/`.
- [ ] **3. Config fail-fast (offline)** — run `main.py` with the placeholder key still in `.env`; show the clear `ANTHROPIC_API_KEY ... placeholder` validation error (proves validated config).

## Core Claude features

- [ ] **4. Classification (key)** — full `main.py` run; screenshot the **1. CLASSIFICATION** block showing `urgency / topic / assigned_team / reason`.
- [ ] **5. Model routing (key)** — same run; show `prescreen: claude-haiku-4-5` and `triage model: claude-sonnet-4-5` (Haiku vs Sonnet routing).
- [ ] **6. Tool Use (key)** — the **GITHUB MCP** / enrichment output, or a dedicated agent run, showing Claude calling `lookup_customer` → `lookup_order` → `create_ticket`.
- [ ] **7. Parallel Tool Use (key or offline test)** — the **2. PARALLEL TOOL CALLS** block with the `wall time … ms` (well under the sequential sum). Alternatively screenshot the `EnrichmentTests` passing.
- [ ] **8. Streaming (key)** — set `on_token` to a live printer (or run an earlier streaming demo) and capture the reply appearing token-by-token.

## Token optimization

- [ ] **9. Usage & cost report (key)** — the **TOKEN USAGE & COST** table at the end of `main.py`, including the "if all calls used Sonnet — routing saved …%" line.

## Built-in server tool

- [ ] **10. Web Search (key + web access)** — a research run showing the **web searches Claude ran**, the **sources found**, and the **context note** (proves the built-in server tool).

## MCP integrations

- [ ] **11. GitHub MCP connection (offline)** — `main.py` (or the connection print) showing the GitHub MCP `server_url`, `beta`, and `allowed_tools = [search_issues, create_issue, update_issue]`.
- [ ] **12. GitHub MCP live (GitHub)** — a real run creating an issue; screenshot the tool calls + summary, **and** the created issue in the GitHub UI.
- [ ] **13. Slack MCP connection (offline)** — the Slack connection block showing `allowed_channels = [#support, #billing, #engineering]`.
- [ ] **14. Slack channel guardrail (offline)** — the `Rejected #random -> Channel #random is not permitted…` line (proves the in-code channel restriction).
- [ ] **15. Slack MCP live (Slack)** — a real notification; screenshot the summary **and** the message in the Slack channel.

## Custom MCP server

- [ ] **16. Custom MCP server running (offline)** — `python -m app.mcp_server.server` showing it serving at `http://127.0.0.1:8050/mcp`.
- [ ] **17. Custom MCP HTTP round-trip (offline)** — `main.py` from Step 11 (or the current pipeline's subscription output) showing `check_customer_subscription` results for `CUST-001`, `CUST-002`, and the not-found `CUST-999`.

## End-to-end & tests

- [ ] **18. Full pipeline (key)** — the complete `main.py` output showing all five numbered stages in order (Classification → Parallel Tool Calls → GitHub → Slack → Final Response).
- [ ] **19. Final customer response (key)** — the **5. FINAL RESPONSE** block.
- [ ] **20. Test suite (offline)** — `python -m unittest discover -s tests -v` ending in `Ran 27 tests … OK`.

---

### Tips
- Run `main.py` once with GitHub/Slack **unconfigured** to capture the graceful-skip screenshots (11, 13, 14), and once **configured** for the live ones (12, 15).
- For the streaming shot (8), a short screen recording converted to a GIF reads better than a still.
- Keep the terminal font large and the window wide so the stage banners are legible.
