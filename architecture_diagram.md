# Architecture

```
                         ┌──────────────────────────────────┐
                         │  Streamlit dashboard on Cloud Run│
                         │  (app/dashboard.py)              │
                         └────────────┬─────────────────────┘
                                      │ ask()
                                      ▼
                         ┌──────────────────────────────────┐
                         │  runner.py · async ADK Runner    │
                         └────────────┬─────────────────────┘
                                      │ run_async()
                                      ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │  google.adk.agents.LlmAgent  (gemini_splunk_devx_agent)         │
       │                                                                  │
       │  Gemini 2.5 Flash via Vertex AI                                  │
       │  System prompt: enforces INVENTORY / ENVIRONMENT /               │
       │  HIGH-SEVERITY / MEDIUM / LOW / CLEANUP PUNCH-LIST / NEXT STEP   │
       └─────────┬───────────────────────────────────────────────────────┘
                 │ tool calls
                 ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │  McpToolset  →  StdioConnectionParams                            │
       │                                                                    │
       │  stub=True  →  python -m gemini_splunk_devx_agent.mcp_stub         │
       │                (5 tools, canned inherited-tenant scenario)         │
       │                                                                    │
       │  stub=False →  npx -y @splunk/splunk-mcp                           │
       │                (real Splunk Cloud / Enterprise)                    │
       └─────────────────────────────────────────────────────────────────┘
                 │ MCP stdio
                 ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │  Splunk Platform MCP server tool surface (5 tools)               │
       │                                                                    │
       │  • list_apps(include_disabled)         → app inventory + versions  │
       │  • list_savedsearches(app)             → scheduled SS + schedules  │
       │  • get_savedsearch(name)               → SPL + cron + owner + lint │
       │  • list_kvstore_collections()          → KV inventory + sizes      │
       │  • audit_knowledge_objects()           → grouped lint issues       │
       └─────────────────────────────────────────────────────────────────┘
                 │ (when stub=False)
                 ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │  Splunk Enterprise / Cloud REST API (savedsearches, kvstore,     │
       │  apps, lookups) via Splunk's hosted MCP                          │
       └─────────────────────────────────────────────────────────────────┘
```

## Components

- **Streamlit dashboard** (`app/dashboard.py`): user-facing UI on Cloud Run. Takes the admin's question, renders the labeled audit report.
- **ADK Runner** (`src/gemini_splunk_devx_agent/runner.py`): async wrapper that drives the agent.
- **LlmAgent** (`src/gemini_splunk_devx_agent/agent.py`): Gemini 2.5 Flash + a hardened system prompt that enforces labeled audit sections + verbatim quoting of issue detail strings.
- **MCP toolset** (Splunk Platform MCP): stub bundled (default) or official `@splunk/splunk-mcp` server when `stub=False`.

## Data flow (the canned inherited-tenant scenario)

1. Admin asks "I inherited this Splunk Cloud tenant. What's here, what's broken?"
2. Agent calls `list_apps()` → 6 apps including a disabled legacy app `TA-deprecated-2024`.
3. Agent calls `list_savedsearches()` → 5 savedsearches; notices one is "DEPRECATED" but still scheduled.
4. Agent calls `get_savedsearch("DEPRECATED: webhost stats via inputlookup")` → SPL uses the removed `sendresults` command, owner is offboarded user `ex_admin_a`.
5. Agent calls `list_kvstore_collections()` → 5 collections; flags `legacy_webhosts_kvstore` (412 days idle).
6. Agent calls `audit_knowledge_objects()` → returns 8 issues grouped high/medium/low.
7. Agent emits the labeled audit with a ranked CLEANUP PUNCH-LIST.

## Why this fits the Splunk Agentic Ops Platform & Developer Experience track

The track asks for "solutions that enhance the developer experience, automate workflows, or simplify how applications interact with Splunk data and API."

This agent IS a Splunk-admin developer-experience tool. It turns the manual chore of inheriting a tenant — manually opening Settings → Searches and clicking through every app and savedsearch and KV collection — into a single conversational walk-through with a prioritized action list at the end.

- Real Splunk surface (apps, savedsearches, KV stores, lookups) — every tool call hits an MCP method.
- Output is auditable: each line in the punch-list ties back to a specific knowledge object name.
- Targets the "Best Use of Splunk MCP Server" bonus prize.

## Real-tenant deployment

Set `stub=False` in `agent.py` and provide:
- `SPLUNK_HOST` — Splunk Cloud or Enterprise endpoint
- `SPLUNK_TOKEN` — Splunk REST API token (must have read scope on apps + savedsearches + KV store)

The stub's tool shape matches the real MCP server one-to-one, so the swap is configuration-only.
