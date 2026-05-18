from gemini_splunk_devx_agent.mcp_stub import (
    _APPS,
    _KVSTORES,
    _SAVEDSEARCHES,
    audit_knowledge_objects_response,
    get_savedsearch_response,
    list_apps_response,
    list_kvstore_collections_response,
    list_savedsearches_response,
)


def test_apps_seeded():
    assert len(_APPS) >= 5
    names = [a["name"] for a in _APPS]
    assert "SplunkEnterpriseSecuritySuite" in names
    assert "TA-deprecated-2024" in names


def test_list_apps_includes_disabled_by_default():
    payload = list_apps_response()
    assert payload["count"] == len(_APPS)
    assert any(a["is_disabled"] for a in payload["apps"])


def test_list_apps_filters_disabled():
    payload = list_apps_response(include_disabled=False)
    assert all(not a["is_disabled"] for a in payload["apps"])


def test_list_savedsearches_all():
    payload = list_savedsearches_response()
    assert payload["count"] == len(_SAVEDSEARCHES)


def test_list_savedsearches_filter_by_app():
    payload = list_savedsearches_response(app="TA-deprecated-2024")
    assert payload["count"] == 2
    assert all(s["app"] == "TA-deprecated-2024" for s in payload["savedsearches"])


def test_get_savedsearch_returns_full_record():
    payload = get_savedsearch_response("DEPRECATED: webhost stats via inputlookup")
    s = payload["savedsearch"]
    assert s["is_scheduled"] is True
    assert s["cron_schedule"] == "*/30 * * * *"
    assert "issues" in s
    assert any("sendresults" in issue for issue in s["issues"])


def test_get_savedsearch_unknown_returns_error():
    payload = get_savedsearch_response("no-such-savedsearch")
    assert "error" in payload


def test_list_kvstore_collections():
    payload = list_kvstore_collections_response()
    assert payload["count"] == len(_KVSTORES)
    names = [kv["collection"] for kv in payload["collections"]]
    assert "asset_inventory" in names
    assert "legacy_webhosts_kvstore" in names


def test_audit_returns_grouped_issues():
    payload = audit_knowledge_objects_response()
    assert payload["issue_count"] >= 4
    assert payload["by_severity"]["high"] >= 1
    assert payload["by_severity"]["medium"] >= 1
    assert payload["by_severity"]["low"] >= 1


def test_audit_flags_deprecated_sendresults_command():
    payload = audit_knowledge_objects_response()
    hits = [i for i in payload["issues"] if "sendresults" in i["detail"].lower()]
    assert hits, "audit must flag the deprecated sendresults command"
    assert hits[0]["severity"] == "high"


def test_audit_flags_orphaned_lookups():
    payload = audit_knowledge_objects_response()
    hits = [i for i in payload["issues"] if i["kind"] == "orphaned_lookup"]
    assert hits, "audit must flag orphaned lookups in deprecated apps"
    apps = {i["app"] for i in hits}
    assert "TA-deprecated-2024" in apps


def test_audit_flags_stale_kvstore_over_90d():
    payload = audit_knowledge_objects_response()
    hits = [i for i in payload["issues"] if i["kind"] == "stale_kvstore"]
    assert hits, "audit must flag KV collections idle > 90 days"


def test_audit_sorted_by_severity():
    payload = audit_knowledge_objects_response()
    sevs = [i["severity"] for i in payload["issues"]]
    order = {"high": 0, "medium": 1, "low": 2}
    assert sevs == sorted(sevs, key=lambda s: order[s]), (
        "audit issues should be sorted high -> medium -> low"
    )


def test_inherited_tenant_story_is_consistent():
    """The pitch: 'I inherited this tenant — what's here, what's broken?'.

    The five tools combined produce a coherent inventory + audit story:
    one disabled legacy app, two savedsearches inside it (one already
    disabled, one still firing with a deprecated command), two orphaned
    lookups, and an ancient KV collection. The agent has to surface
    those in priority order.
    """
    apps = list_apps_response()["apps"]
    saved = list_savedsearches_response()["savedsearches"]
    audit = audit_knowledge_objects_response()

    # Legacy disabled app exists
    legacy = [a for a in apps if a["name"] == "TA-deprecated-2024"]
    assert legacy and legacy[0]["is_disabled"] is True

    # An active savedsearch lives inside the disabled app
    active_in_disabled = [
        s for s in saved if s["app"] == "TA-deprecated-2024" and not s["is_disabled"]
    ]
    assert active_in_disabled, "there must be an active SS in the disabled app"

    # The audit must surface that
    assert any(i["kind"] == "savedsearch_in_disabled_app" for i in audit["issues"])
