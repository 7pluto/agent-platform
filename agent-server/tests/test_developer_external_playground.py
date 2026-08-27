import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp.service import mcp_client
from app.runtime.http_tool import http_tool_client


def _exchange(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-developer-ticket"})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload, {"X-CSRF-Token": payload["csrf_token"]}


def _semantics(summary: str) -> dict:
    return {
        "one_line_summary": summary,
        "when_to_use": "测试需要该能力时使用",
        "when_not_to_use": "与测试目标无关时不要使用",
        "input_summary": "按输入契约提供测试参数",
        "output_summary": "返回结构化测试结果",
        "risk_level": "LOW",
        "read_only": True,
        "publication_scope": "PERSONAL",
        "publication_subjects": [],
    }


def test_common_resources_can_run_independently_in_playground() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        _, headers = _exchange(client)
        installed = client.post("/api/v1/developer/resources/common/install", headers=headers)
        assert installed.status_code == 200, installed.text

        available = client.get("/api/v1/developer/resources/available")
        assert available.status_code == 200, available.text
        items = available.json()

        calculator = next(item for item in items if item["resource_type"] == "TOOL" and item["display_name"] == "基础计算器")
        calculated = client.post(
            f"/api/v1/developer/playground/{calculator['version_id']}/run",
            headers=headers,
            json={"arguments": {"expression": "2+3*4"}},
        )
        assert calculated.status_code == 200, calculated.text
        assert calculated.json()["mode"] == "EXECUTE"
        assert calculated.json()["output"]["value"] == 14

        prompt = next(item for item in items if item["resource_type"] == "PROMPT" and item["display_name"] == "企业通用助手")
        preview = client.post(
            f"/api/v1/developer/playground/{prompt['version_id']}/run",
            headers=headers,
            json={"message": "请测试这个 Prompt"},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["mode"] == "PREVIEW"
        assert "企业内部智能助手" in preview.json()["output"]["system_prompt"]

        skill = next(item for item in items if item["resource_type"] == "SKILL" and item["display_name"] == "数值计算与校验")
        skill_preview = client.post(
            f"/api/v1/developer/playground/{skill['version_id']}/run",
            headers=headers,
            json={"message": "帮我计算 12*8"},
        )
        assert skill_preview.status_code == 200, skill_preview.text
        assert skill_preview.json()["mode"] == "PREVIEW"
        assert skill_preview.json()["output"]["tool_version_ids"]


def test_developer_http_onboarding_publishes_tool_and_reuses_http_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict, dict]] = []

    async def fake_http_invoke(config, arguments, tenant_id, user_id):
        calls.append((config, arguments))
        return {"status_code": 200, "body": {"customer_id": arguments.get("customer_id"), "name": "Playground Customer"}}

    monkeypatch.setattr(http_tool_client, "invoke", fake_http_invoke)

    with TestClient(app, base_url="https://testserver") as client:
        _, headers = _exchange(client)
        created = client.post(
            "/api/v1/developer/external/http-tools",
            headers=headers,
            json={
                "slug": "developer-http-playground",
                "display_name": "开发者 HTTP 客户查询",
                "description": "测试开发者 HTTP 接入和 Playground",
                "tool_name": "developer_http_customer",
                "endpoint": "https://business.example.test",
                "path": "/customers/{{customer_id}}",
                "method": "GET",
                "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
                "test_arguments": {"customer_id": "C1001"},
                **_semantics("按客户编号查询业务客户信息"),
            },
        )
        assert created.status_code == 201, created.text
        version = created.json()["resource_version"]
        assert version["status"] == "PUBLISHED"
        assert calls and calls[0][1]["customer_id"] == "C1001"

        played = client.post(
            f"/api/v1/developer/playground/{version['resource_version_id']}/run",
            headers=headers,
            json={"arguments": {"customer_id": "C2002"}},
        )
        assert played.status_code == 200, played.text
        assert played.json()["kind"] == "HTTP"
        assert played.json()["output"]["body"]["customer_id"] == "C2002"
        assert len(calls) == 2


def test_developer_mcp_onboarding_discovers_registers_and_runs_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_discover(endpoint, timeout_seconds=10.0, headers=None, egress_allowlist=None):
        return [{
            "name": "lookup_asset",
            "description": "按资产编号查询资产",
            "inputSchema": {"type": "object", "properties": {"asset_id": {"type": "string"}}, "required": ["asset_id"]},
        }]

    async def fake_invoke(endpoint, name, arguments, timeout_seconds=10.0, headers=None, egress_allowlist=None):
        return {"content": [{"type": "text", "text": f"asset:{arguments['asset_id']}"}]}

    monkeypatch.setattr(mcp_client, "discover", fake_discover)
    monkeypatch.setattr(mcp_client, "invoke", fake_invoke)

    with TestClient(app, base_url="https://testserver") as client:
        _, headers = _exchange(client)
        connection = client.post(
            "/api/v1/developer/external/mcp/connections",
            headers=headers,
            json={
                "slug": "developer-asset-mcp",
                "display_name": "开发者资产 MCP",
                "description": "测试 MCP 接入",
                "endpoint": "https://mcp.example.test/mcp",
                **_semantics("从资产系统读取资产信息"),
            },
        )
        assert connection.status_code == 201, connection.text
        connection_version_id = connection.json()["resource_version_id"]

        discovered = client.post(f"/api/v1/developer/external/mcp/connections/{connection_version_id}/discover", headers=headers)
        assert discovered.status_code == 200, discovered.text
        assert discovered.json()[0]["name"] == "lookup_asset"

        registered = client.post(
            "/api/v1/developer/external/mcp/tools",
            headers=headers,
            json={
                "connection_version_id": connection_version_id,
                "tools": [{
                    "tool_name": "lookup_asset",
                    "slug": "developer-lookup-asset",
                    "display_name": "查询资产",
                    "description": "按资产编号查询资产",
                    "one_line_summary": "读取资产基础信息",
                    "when_to_use": "已有资产编号并需要核对资产信息时",
                    "when_not_to_use": "没有资产编号时",
                    "input_summary": "asset_id 资产编号",
                    "output_summary": "资产查询结果",
                    "risk_level": "LOW",
                    "read_only": True,
                    "tags": ["asset"],
                }],
            },
        )
        assert registered.status_code == 201, registered.text
        tool = registered.json()[0]

        played = client.post(
            f"/api/v1/developer/playground/{tool['resource_version_id']}/run",
            headers=headers,
            json={"arguments": {"asset_id": "A-100"}},
        )
        assert played.status_code == 200, played.text
        assert played.json()["kind"] == "MCP"
        assert "asset:A-100" in played.text
