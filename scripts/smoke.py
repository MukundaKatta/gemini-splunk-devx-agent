"""Real Vertex AI smoke test for gemini-splunk-devx-agent.

Walks the canned 'inherited-tenant' scenario end-to-end through Gemini 2.5
Flash on the Splunk Platform MCP stub. Verifies the agent emits the
labeled audit sections and quotes the key issues verbatim.

Usage:
    GOOGLE_CLOUD_PROJECT=careersavvy-mukunda \\
    GOOGLE_GENAI_USE_VERTEXAI=true \\
    GOOGLE_CLOUD_LOCATION=us-central1 \\
    .venv/bin/python scripts/smoke.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "careersavvy-mukunda")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from gemini_splunk_devx_agent.runner import ask  # noqa: E402


QUESTION = (
    "I just inherited this Splunk Cloud tenant. Walk the Splunk Platform "
    "MCP tools (list_apps, list_savedsearches, get_savedsearch on anything "
    "suspicious, list_kvstore_collections, audit_knowledge_objects) and "
    "give me the inventory + a ranked cleanup punch-list. Output the "
    "labeled sections from your system prompt."
)


def main() -> int:
    print("== gemini-splunk-devx-agent smoke ==")
    print(f"project={os.environ.get('GOOGLE_CLOUD_PROJECT')}")
    print(f"location={os.environ.get('GOOGLE_CLOUD_LOCATION')}")
    print(f"vertexai={os.environ.get('GOOGLE_GENAI_USE_VERTEXAI')}")
    print()
    print(f"> {QUESTION}")
    print()

    resp = ask(QUESTION, stub=True)
    print("--- FINAL TEXT ---")
    print(resp.final_text or "(no final text)")
    print("--- END FINAL TEXT ---")
    print(f"events: {len(resp.events)}")

    text = (resp.final_text or "").upper()
    checks = {
        "has INVENTORY":              "INVENTORY" in text,
        "has ENVIRONMENT":            "ENVIRONMENT" in text,
        "has HIGH-SEVERITY":          "HIGH-SEVERITY" in text or "HIGH SEVERITY" in text,
        "has CLEANUP PUNCH-LIST":     "CLEANUP" in text and "PUNCH" in text,
        "has NEXT STEP":              "NEXT STEP" in text,
        "names deprecated TA":        "TA-DEPRECATED-2024" in text,
        "flags sendresults command":  "SENDRESULTS" in text,
        "names a KV collection":      "ASSET_INVENTORY" in text or "LEGACY_WEBHOSTS_KVSTORE" in text,
    }
    print()
    print("--- CHECKS ---")
    for label, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
