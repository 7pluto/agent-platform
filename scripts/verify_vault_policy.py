#!/usr/bin/env python3
"""Verify deployed Vault policy without printing or transmitting secret values."""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request


BASE = "https://agent.chenwh.xin/api/v1"


def main() -> None:
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def request(path: str, method: str = "GET", payload: dict | None = None, csrf: str | None = None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with opener.open(req, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    status, health = request("/healthz")
    login_status, login = request("/auth/exchange", "POST", {"ticket_code": "dev-ticket"})
    csrf = login["csrf_token"]
    resources_status, resources = request("/resources")
    models_status, models = request("/models")

    refs: list[str] = []
    keyed_versions: list[dict] = []
    version_count = 0
    for resource in resources:
        version_status, versions = request(f"/resources/{resource['resource_id']}/versions")
        assert version_status == 200
        version_count += len(versions)
        for item in versions:
            if ref := item["config"].get("secret_ref"):
                refs.append(str(ref))
                keyed_versions.append({"resource": resource["slug"], "type": resource["resource_type"], "status": item["status"], "scheme": str(ref).split("://", 1)[0]})
    for model in models:
        version_status, versions = request(f"/models/{model['model_id']}/versions")
        assert version_status == 200
        version_count += len(versions)
        for item in versions:
            if ref := item["config"].get("secret_ref"):
                refs.append(str(ref))
                keyed_versions.append({"resource": model["slug"], "type": "MODEL", "status": item["status"], "scheme": str(ref).split("://", 1)[0]})

    reject_status, reject = request(
        "/resources",
        "POST",
        {
            "resource_type": "MCP_CONNECTION",
            "slug": "legacy-env-policy-probe",
            "display_name": "policy probe",
            "draft_config": {
                "transport": "streamable_http",
                "endpoint": "http://demo-crm-mcp:8090/mcp",
                "timeout_seconds": 10,
                "egress_allowlist": ["demo-crm-mcp"],
                "secret_ref": "env://SHOULD_BE_REJECTED",
            },
        },
        csrf,
    )

    dify = next((resource for resource in resources if resource["resource_type"] == "TOOL" and "dify" in resource["slug"]), None)
    dify_test = None
    if dify:
        _, versions = request(f"/resources/{dify['resource_id']}/versions")
        published = next(item for item in reversed(versions) if item["status"] == "PUBLISHED")
        test_status, test_result = request(f"/resource-versions/{published['resource_version_id']}/test", "POST", {}, csrf)
        dify_test = {"status": test_status, "flow_type": test_result.get("flow_type"), "has_retrieval": test_result.get("has_retrieval")}

    mcp = next((resource for resource in resources if resource["slug"] == "demo-crm-connection"), None)
    mcp_test = None
    if mcp:
        _, versions = request(f"/resources/{mcp['resource_id']}/versions")
        published = next(item for item in reversed(versions) if item["status"] == "PUBLISHED")
        discover_status, discovered = request(f"/mcp-connections/{published['resource_version_id']}/discover", "POST", {}, csrf)
        mcp_test = {"status": discover_status, "tools": sorted(item["name"] for item in discovered) if isinstance(discovered, list) else []}

    print(json.dumps({
        "health": {"status": status, "payload": health},
        "login_status": login_status,
        "resource_status": resources_status,
        "model_status": models_status,
        "version_count": version_count,
        "keyed_version_count": len(refs),
        "keyed_versions": keyed_versions,
        "all_published_keyed_versions_are_vault": all(item["scheme"] == "vault" for item in keyed_versions if item["status"] == "PUBLISHED"),
        "legacy_non_published_refs": [item for item in keyed_versions if item["scheme"] != "vault" and item["status"] != "PUBLISHED"],
        "legacy_env_write": {"status": reject_status, "code": reject.get("code")},
        "dify_connection_test": dify_test,
        "mcp_discovery_test": mcp_test,
    }, ensure_ascii=False, indent=2))

    assert status == login_status == resources_status == models_status == 200
    assert refs
    assert all(item["scheme"] == "vault" for item in keyed_versions if item["status"] == "PUBLISHED")
    assert reject_status == 422 and reject.get("code") == "VAULT_SECRET_REF_REQUIRED"
    assert dify_test and dify_test["status"] == 200
    assert mcp_test and mcp_test["status"] == 200


if __name__ == "__main__":
    main()
