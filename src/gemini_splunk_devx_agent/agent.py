"""ADK Gemini agent wired to the Splunk MCP server.

Targets the Splunk Agentic Ops "Platform & Developer Experience" track plus
the "Best Use of Splunk MCP Server" bonus prize. The McpToolset connection
params point at our local stub server by default
(`gemini_splunk_devx_agent.mcp_stub`). To target a real Splunk Cloud /
Enterprise instance, swap the params to the official server (see below).
"""

from __future__ import annotations

import os
import sys
from typing import Any


try:
    from google.adk.agents import LlmAgent
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters
    _ADK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ADK_AVAILABLE = False


SYSTEM_PROMPT = """\
You are a Splunk admin copilot. The user has just inherited a Splunk Cloud
tenant and wants a clean inventory of what is here, what is broken, and a
ranked cleanup punch-list. You walk the Splunk MCP Platform tools and emit
an auditor-shaped report.

Workflow:
1. Call `list_apps` first to see what apps are installed (note any disabled
   apps).
2. Call `list_savedsearches` to see all scheduled / ad-hoc savedsearches.
   Note any savedsearch whose owning app is disabled, or whose owner looks
   offboarded.
3. For any savedsearch that looks suspicious (deprecated commands,
   offboarded owner, disabled-app residency), call `get_savedsearch` for
   the full record and quote the SPL + cron schedule + owner verbatim.
4. Call `list_kvstore_collections` to see KV store inventory, sizes, and
   last-modified timestamps.
5. Call `audit_knowledge_objects` last. The audit returns issues grouped by
   severity (high / medium / low). Quote those issues verbatim — do not
   paraphrase the detail strings.

Output a structured audit report with EXACTLY these labeled sections:

INVENTORY: <one sentence with app count, savedsearch count, KV collection count>
ENVIRONMENT: <2-4 bullets — notable apps / disabled apps / owning users with high object counts>
HIGH-SEVERITY ISSUES: <list, verbatim from audit_knowledge_objects with severity=high>
MEDIUM-SEVERITY ISSUES: <list, verbatim>
LOW-SEVERITY ISSUES: <list, verbatim>
CLEANUP PUNCH-LIST: <ranked top 5 actions, most-impactful first>
NEXT STEP: <one concrete first action — which savedsearch or KV store to handle today>

Strict rules:
- Quote savedsearch names, SPL fragments, app names, KV collection names,
  and issue detail strings verbatim from tool output.
- Counts (savedsearches, KV records, MB) must be copied verbatim.
- Do not invent issues that audit_knowledge_objects did not return.
- The CLEANUP PUNCH-LIST is the differentiator — rank the issues by real
  operational impact, not just severity.
"""


def _splunk_devx_toolset(stub: bool = True) -> Any:
    if not _ADK_AVAILABLE:
        raise ImportError(
            "google-adk and mcp must be installed: pip install google-adk mcp"
        )

    if stub:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "gemini_splunk_devx_agent.mcp_stub"],
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
            },
        )
    else:
        # Real Splunk MCP server (the official splunk/splunk-mcp package).
        params = StdioServerParameters(
            command="npx",
            args=["-y", "@splunk/splunk-mcp"],
            env={
                **os.environ,
                "SPLUNK_HOST":  os.environ.get("SPLUNK_HOST", ""),
                "SPLUNK_TOKEN": os.environ.get("SPLUNK_TOKEN", ""),
            },
        )
    return McpToolset(connection_params=StdioConnectionParams(server_params=params))


def build_agent(model: str = "gemini-2.5-flash", stub: bool = True) -> Any:
    if not _ADK_AVAILABLE:
        return None
    return LlmAgent(
        model=model,
        name="gemini_splunk_devx_agent",
        instruction=SYSTEM_PROMPT,
        tools=[_splunk_devx_toolset(stub=stub)],
    )
