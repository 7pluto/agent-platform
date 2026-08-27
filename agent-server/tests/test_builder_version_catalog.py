from fastapi.testclient import TestClient

from app.main import app


def _exchange(client: TestClient, ticket: str) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": ticket})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload, {"X-CSRF-Token": payload["csrf_token"]}


def _semantics(summary: str) -> dict:
    return {
        "one_line_summary": summary,
        "when_to_use": "当 Agent 需要该能力时使用",
        "when_not_to_use": "无关任务不要使用",
        "input_summary": "接收业务参数",
        "output_summary": "返回结构化结果",
        "risk_level": "LOW",
        "read_only": True,
        "tags": ["builder-version-test"],
        "publication_scope": "PERSONAL",
        "publication_subjects": [],
    }


def test_builder_catalog_keeps_authorized_v1_and_v2_for_explicit_selection() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        _, developer_headers = _exchange(client, "dev-developer-ticket")

        v1 = client.post(
            "/api/v1/developer/resources/native-tools",
            headers=developer_headers,
            json={
                "slug": "builder-version-tool",
                "display_name": "Builder 版本测试工具",
                "description": "用于验证 Agent Builder 显式版本选择",
                "native_name": "calculator",
                "tool_name": "builder_version_tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                **_semantics("提供基础计算能力"),
            },
        )
        assert v1.status_code == 201, v1.text
        v1_payload = v1.json()

        v2 = client.post(
            f"/api/v1/developer/resources/{v1_payload['resource_id']}/versions",
            headers=developer_headers,
            json={
                "config": {
                    "kind": "NATIVE",
                    "native_name": "calculator",
                    "tool_name": "builder_version_tool",
                    "description": "支持精度参数",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                            "precision": {"type": "integer"},
                        },
                        "required": ["expression"],
                    },
                },
                **_semantics("提供支持精度参数的计算能力"),
            },
        )
        assert v2.status_code == 201, v2.text
        v2_payload = v2.json()
        published = client.post(
            f"/api/v1/developer/resources/{v1_payload['resource_id']}/versions/{v2_payload['resource_version_id']}/publish",
            headers=developer_headers,
        )
        assert published.status_code == 200, published.text

        _, admin_headers = _exchange(client, "dev-ticket")
        grant = client.post(
            "/api/v1/resource-grants",
            headers=admin_headers,
            json={
                "subject_type": "ROLE",
                "subject_id": "agent_admin",
                "resource_type": "TOOL",
                "resource_id": v1_payload["resource_id"],
                "actions": ["VIEW", "USE"],
                "effect": "ALLOW",
            },
        )
        assert grant.status_code == 201, grant.text

        catalog = client.get("/api/v1/resource-version-catalog")
        assert catalog.status_code == 200, catalog.text
        versions = [
            item for item in catalog.json()
            if item["resource_id"] == v1_payload["resource_id"]
        ]
        assert [item["version_number"] for item in versions] == [1, 2]
        assert {item["version_id"] for item in versions} == {
            v1_payload["resource_version_id"],
            v2_payload["resource_version_id"],
        }
        assert all(item["status"] == "PUBLISHED" for item in versions)
