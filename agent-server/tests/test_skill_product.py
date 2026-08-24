from fastapi.testclient import TestClient

from app.main import app


def _headers(client: TestClient) -> dict[str, str]:
    session = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"}).json()
    return {"X-CSRF-Token": session["csrf_token"]}


def _published_native_tool(client: TestClient, headers: dict[str, str]) -> str:
    definition = client.post("/api/v1/resources", headers=headers, json={
        "resource_type": "TOOL", "slug": "skill-product-echo-tool", "display_name": "Skill 测试 Echo",
        "draft_config": {"kind": "NATIVE", "native_name": "echo"},
    }).json()
    version = client.post(f"/api/v1/resources/{definition['resource_id']}/versions", headers=headers, json={
        "config": {"kind": "NATIVE", "native_name": "echo"},
    }).json()
    published = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/publish", headers=headers)
    assert published.status_code == 200, published.text
    return version["resource_version_id"]


def test_skill_product_compiles_tests_and_published_dependencies() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _headers(client)
        tool_version_id = _published_native_tool(client, headers)
        response = client.post("/api/v1/skills", headers=headers, json={
            "slug": "customer-query-business-skill",
            "display_name": "客户查询业务技能",
            "description": "按业务规则调用客户查询工具",
            "skill_md": "# 客户查询技能\n\n当用户查询客户时，先使用已授权工具，再基于真实结果回答。",
            "tool_version_ids": [tool_version_id],
            "knowledge_version_ids": [],
            "test_cases": [{"input": "查询客户 C001", "expected_behavior": "调用客户查询工具并总结结果"}],
        })
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["status"] == "PUBLISHED"
        assert payload["test_result"] == {
            "test_case_count": 1, "tool_dependency_count": 1,
            "knowledge_dependency_count": 0, "status": "COMPILED",
        }
        assert "skill_md" not in response.text


def test_skill_product_rejects_non_heading_skill_md() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _headers(client)
        response = client.post("/api/v1/skills", headers=headers, json={
            "slug": "invalid-business-skill", "display_name": "无效技能",
            "skill_md": "这不是一个以标题开头的 SKILL.md 内容。",
            "test_cases": [{"input": "测试", "expected_behavior": "拒绝发布"}],
        })
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_SKILL_CONFIG"
