"""Stub Splunk MCP server — Platform & Developer Experience tool surface.

Submission for the Splunk Agentic Ops Hackathon, Platform & Developer
Experience track. The tool surface mirrors the official Splunk MCP server's
admin/dev side: knowledge-object management (savedsearches, lookups, KV
store collections), app inventory, and a lint/audit step that flags
disabled or deprecated objects.

The canned scenario: a Splunk admin just inherited a Splunk Cloud tenant
and wants the agent to walk the tools, produce an inventory, and emit a
ranked cleanup punch-list.

Run with: python -m gemini_splunk_devx_agent.mcp_stub
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Canned data — Splunk Platform shape
# ---------------------------------------------------------------------------

_APPS = [
    {"name": "search",                          "label": "Search & Reporting",          "version": "9.3.2", "owning_user": "system",     "is_disabled": False},
    {"name": "SplunkEnterpriseSecuritySuite",   "label": "Enterprise Security",         "version": "8.0.1", "owning_user": "admin",      "is_disabled": False},
    {"name": "Splunk_TA_nix",                   "label": "Splunk Add-on for Unix/Linux","version": "8.10.0","owning_user": "nobody",     "is_disabled": False},
    {"name": "Splunk_TA_windows",               "label": "Splunk Add-on for Windows",   "version": "8.9.1", "owning_user": "nobody",     "is_disabled": False},
    {"name": "TA-deprecated-2024",              "label": "Legacy Web Logs TA",          "version": "1.2.0", "owning_user": "ex_admin_a", "is_disabled": True},
    {"name": "internal_dashboards",             "label": "Internal Dashboards (custom)","version": "0.4.7", "owning_user": "endpoint-management","is_disabled": False},
]


_SAVEDSEARCHES = [
    {
        "name":          "Endpoint - Binary executed from temp folder - Rule",
        "app":           "SplunkEnterpriseSecuritySuite",
        "is_disabled":   False,
        "is_scheduled":  True,
        "cron_schedule": "*/5 * * * *",
        "earliest":      "-5m",
        "latest":        "now",
        "spl":           'search index=endpoint sourcetype="WinEventLog:Sysmon" EventCode=1 process_path="*\\\\Windows\\\\Temp\\\\*.exe" | stats count by host, user, process_path, process_sha256',
        "owner":         "soc",
    },
    {
        "name":          "Daily index size audit",
        "app":           "search",
        "is_disabled":   False,
        "is_scheduled":  True,
        "cron_schedule": "0 6 * * *",
        "earliest":      "-1d",
        "latest":        "now",
        "spl":           '| rest /services/data/indexes | stats sum(currentDBSizeMB) as size_mb by title',
        "owner":         "admin",
    },
    {
        "name":          "Legacy: nightly user dump (DISABLED, kept for history)",
        "app":           "TA-deprecated-2024",
        "is_disabled":   True,
        "is_scheduled":  False,
        "cron_schedule": "",
        "earliest":      "-1d",
        "latest":        "now",
        "spl":           '| dbinspect index=_audit | stats count by sourcetype',
        "owner":         "ex_admin_a",
    },
    {
        "name":          "DEPRECATED: webhost stats via inputlookup",
        "app":           "TA-deprecated-2024",
        "is_disabled":   False,
        "is_scheduled":  True,
        "cron_schedule": "*/30 * * * *",
        "earliest":      "-30m",
        "latest":        "now",
        "spl":           '| inputlookup webhosts.csv | stats count by host | sendresults to=ops@example.com',
        "owner":         "ex_admin_a",
        "issues": [
            "uses deprecated 'sendresults' command (removed in 9.0+)",
            "owner ex_admin_a is an offboarded user — search will fail on next run",
        ],
    },
    {
        "name":          "Endpoint health rollup",
        "app":           "internal_dashboards",
        "is_disabled":   False,
        "is_scheduled":  True,
        "cron_schedule": "0 * * * *",
        "earliest":      "-1h",
        "latest":        "now",
        "spl":           'search index=endpoint | stats latest(status) as status by host | stats count by status',
        "owner":         "endpoint-management",
    },
]


_KVSTORES = [
    {"collection": "asset_inventory",          "app": "SplunkEnterpriseSecuritySuite", "record_count": 18_412, "size_mb": 14.2, "last_modified": (NOW - timedelta(hours=2)).isoformat()},
    {"collection": "identity_inventory",       "app": "SplunkEnterpriseSecuritySuite", "record_count": 4_120,  "size_mb": 2.1,  "last_modified": (NOW - timedelta(hours=2)).isoformat()},
    {"collection": "approved_change_windows",  "app": "internal_dashboards",          "record_count": 287,    "size_mb": 0.4,  "last_modified": (NOW - timedelta(minutes=46)).isoformat()},
    {"collection": "legacy_webhosts_kvstore",  "app": "TA-deprecated-2024",            "record_count": 12_900, "size_mb": 6.8,  "last_modified": (NOW - timedelta(days=412)).isoformat()},
    {"collection": "scratch_test",             "app": "search",                        "record_count": 3,      "size_mb": 0.0,  "last_modified": (NOW - timedelta(days=180)).isoformat()},
]


_LOOKUPS = [
    {"name": "approved_change_windows.csv", "app": "internal_dashboards",       "type": "csv",     "row_count": 287},
    {"name": "webhosts.csv",                "app": "TA-deprecated-2024",        "type": "csv",     "row_count": 12_900, "orphaned": True},
    {"name": "asset_inventory_kvstore",     "app": "SplunkEnterpriseSecuritySuite", "type": "kvstore", "row_count": 18_412},
    {"name": "old_users_2024.csv",          "app": "TA-deprecated-2024",        "type": "csv",     "row_count": 4_817,  "orphaned": True},
]


# ---------------------------------------------------------------------------
# Response builders (also reused by tests)
# ---------------------------------------------------------------------------


def list_apps_response(include_disabled: bool = True) -> dict[str, Any]:
    apps = _APPS if include_disabled else [a for a in _APPS if not a["is_disabled"]]
    return {"count": len(apps), "apps": apps}


def list_savedsearches_response(app: str | None = None) -> dict[str, Any]:
    items = _SAVEDSEARCHES if app is None else [s for s in _SAVEDSEARCHES if s["app"] == app]
    return {"count": len(items), "savedsearches": items}


def get_savedsearch_response(name: str) -> dict[str, Any]:
    rec = next((s for s in _SAVEDSEARCHES if s["name"] == name), None)
    if rec is None:
        return {"error": f"unknown savedsearch {name!r}"}
    return {"savedsearch": rec}


def list_kvstore_collections_response() -> dict[str, Any]:
    return {"count": len(_KVSTORES), "collections": _KVSTORES}


def audit_knowledge_objects_response() -> dict[str, Any]:
    """Lint pass over savedsearches + lookups + KV stores. Returns the
    same shape that the official Splunk MCP server's audit endpoint
    produces: a list of issues grouped by severity, plus a ranked
    cleanup punch-list."""
    issues: list[dict[str, Any]] = []

    # Disabled apps still referenced by enabled savedsearches
    for s in _SAVEDSEARCHES:
        owning_app = next((a for a in _APPS if a["name"] == s["app"]), None)
        if owning_app and owning_app["is_disabled"] and not s["is_disabled"]:
            issues.append({
                "severity":   "high",
                "kind":       "savedsearch_in_disabled_app",
                "object":     s["name"],
                "app":        s["app"],
                "detail":     f"Active savedsearch lives in disabled app {s['app']!r}; will silently stop running.",
            })

    # Savedsearches with explicit per-object issues
    for s in _SAVEDSEARCHES:
        for note in s.get("issues", []):
            issues.append({
                "severity":   "high" if "deprecated" in note.lower() else "medium",
                "kind":       "savedsearch_issue",
                "object":     s["name"],
                "app":        s["app"],
                "detail":     note,
            })

    # Orphaned lookups (large CSV in a disabled or deprecated app)
    for lk in _LOOKUPS:
        if lk.get("orphaned"):
            issues.append({
                "severity":   "medium",
                "kind":       "orphaned_lookup",
                "object":     lk["name"],
                "app":        lk["app"],
                "detail":     f"Lookup is in deprecated app {lk['app']!r}; "
                              f"{lk['row_count']:,} rows.",
            })

    # KV stores that haven't been touched in > 90 days
    for kv in _KVSTORES:
        try:
            last = datetime.fromisoformat(kv["last_modified"])
            age_days = (NOW - last).days
            if age_days > 90:
                issues.append({
                    "severity":   "low",
                    "kind":       "stale_kvstore",
                    "object":     kv["collection"],
                    "app":        kv["app"],
                    "detail":     f"KV collection not modified in {age_days} days ({kv['record_count']:,} records, {kv['size_mb']} MB).",
                })
        except Exception:
            pass

    # Rank punch-list (severity desc, then kind alphabetic)
    sev_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (sev_order.get(i["severity"], 9), i["kind"], i["object"]))

    return {
        "issue_count":    len(issues),
        "by_severity":    {
            "high":   sum(1 for i in issues if i["severity"] == "high"),
            "medium": sum(1 for i in issues if i["severity"] == "medium"),
            "low":    sum(1 for i in issues if i["severity"] == "low"),
        },
        "issues":          issues,
    }


# ---------------------------------------------------------------------------
# MCP server wiring
# ---------------------------------------------------------------------------


def _make_server() -> Server:
    server = Server("splunk-devx-stub")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name="list_apps",
                 description=("List installed Splunk apps with their version, "
                              "owning user, and disabled state."),
                 inputSchema={"type": "object",
                              "properties": {"include_disabled": {"type": "boolean", "default": True}},
                              "required": []}),
            Tool(name="list_savedsearches",
                 description=("List scheduled / ad-hoc savedsearches across the "
                              "instance. Optionally filter by app name."),
                 inputSchema={"type": "object",
                              "properties": {"app": {"type": "string"}},
                              "required": []}),
            Tool(name="get_savedsearch",
                 description=("Fetch one savedsearch by name with its cron "
                              "schedule, SPL, owner, and any lint issues."),
                 inputSchema={"type": "object",
                              "properties": {"name": {"type": "string"}},
                              "required": ["name"]}),
            Tool(name="list_kvstore_collections",
                 description=("List Splunk KV store collections with record "
                              "counts, sizes, and last-modified timestamps."),
                 inputSchema={"type": "object", "properties": {}, "required": []}),
            Tool(name="audit_knowledge_objects",
                 description=("Run a lint pass over savedsearches + lookups + "
                              "KV stores. Returns issues grouped by severity "
                              "(high / medium / low) plus a ranked cleanup "
                              "punch-list for a Splunk admin."),
                 inputSchema={"type": "object", "properties": {}, "required": []}),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        a = arguments
        if name == "list_apps":
            payload = list_apps_response(bool(a.get("include_disabled", True)))
        elif name == "list_savedsearches":
            payload = list_savedsearches_response(a.get("app"))
        elif name == "get_savedsearch":
            payload = get_savedsearch_response(a.get("name", ""))
        elif name == "list_kvstore_collections":
            payload = list_kvstore_collections_response()
        elif name == "audit_knowledge_objects":
            payload = audit_knowledge_objects_response()
        else:
            payload = {"error": f"unknown tool {name!r}"}
        return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]

    return server


async def _main() -> None:
    server = _make_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
