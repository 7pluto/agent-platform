from fastapi.testclient import TestClient

from app.main import app


def _exchange(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-developer-ticket"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _semantics(summary: str) -> dict:
    return {
        "one_line_summary": summary,
        "when_to_use": "当业务任务需要该能力时使用",
        "when_not_to_use": "无关任务不要使用",
        "input_summary": "接收业务参数",
        "output_summary": "返回结构化结果",
        "risk_level": "LOW",
        "read_only": True,
        "tags": ["dependency-upgrade-test"],
        "publication_scope": "PERSONAL",
        "publication_subjects": [],
    }


def test_skill_dependency_upgrade_is_visible_diffable_and_explicit() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _exchange(client)

        tool_v1 = client.post(
            "/api/v1/developer/resources/native-tools",
            headers=headers,
            json={
                "slug": "upgrade-test-calculator",
                "display_name": "升级测试计算器",
                "description": "用于依赖升级测试",
                "native_name": "calculator",
                "tool_name": "upgrade_test_calculator",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                **_semantics("提供基础数学计算能力"),
            },
        )
        assert tool_v1.status_code == 201, tool_v1.text
        tool_v1_payload = tool_v1.json()

        skill_v1 = client.post(
            "/api/v1/developer/resources/skills",
            headers=headers,
            json={
                "slug": "upgrade-test-skill",
                "display_name": "依赖升级测试 Skill",
                "description": "验证 Skill 显式依赖升级",
                "skill_md": "# 依赖升级测试 Skill\n需要精确计算时调用升级测试计算器，并解释结果。",
                "tool_version_ids": [tool_v1_payload["resource_version_id"]],
                "knowledge_version_ids": [],
                **_semantics("验证 Skill 显式依赖升级流程"),
            },
        )
        assert skill_v1.status_code == 201, skill_v1.text
        skill_v1_payload = skill_v1.json()

        tool_v2_draft = client.post(
            f"/api/v1/developer/resources/{tool_v1_payload['resource_id']}/versions",
            headers=headers,
            json={
                "config": {
                    "kind": "NATIVE",
                    "native_name": "calculator",
                    "tool_name": "upgrade_test_calculator",
                    "description": "支持精度参数的计算器",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                            "precision": {"type": "integer"},
                        },
                        "required": ["expression"],
                    },
                },
                **_semantics("提供支持精度参数的数学计算能力"),
            },
        )
        assert tool_v2_draft.status_code == 201, tool_v2_draft.text
        tool_v2_payload = tool_v2_draft.json()
        assert tool_v2_payload["version_number"] == 2
        assert tool_v2_payload["status"] == "DRAFT"

        publish_tool_v2 = client.post(
            f"/api/v1/developer/resources/{tool_v1_payload['resource_id']}/versions/{tool_v2_payload['resource_version_id']}/publish",
            headers=headers,
        )
        assert publish_tool_v2.status_code == 200, publish_tool_v2.text
        assert publish_tool_v2.json()["status"] == "PUBLISHED"

        report = client.get(
            f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}/dependency-upgrades"
        )
        assert report.status_code == 200, report.text
        payload = report.json()
        assert payload["based_on_draft"] is False
        assert payload["skill_version_number"] == 1
        assert payload["upgrades_available"] == 1
        assert len(payload["dependencies"]) == 1

        dependency = payload["dependencies"][0]
        assert dependency["dependency_type"] == "TOOL"
        assert dependency["resource_id"] == tool_v1_payload["resource_id"]
        assert dependency["current"]["version_id"] == tool_v1_payload["resource_version_id"]
        assert dependency["current"]["version_number"] == 1
        assert dependency["latest"]["version_id"] == tool_v2_payload["resource_version_id"]
        assert dependency["latest"]["version_number"] == 2
        assert dependency["upgrade_available"] is True
        assert dependency["upgrade_allowed"] is True
        assert "input_schema" in dependency["changed_fields"]
        assert "precision" not in dependency["current"]["config_preview"]["input_schema"]["properties"]
        assert "precision" in dependency["latest"]["config_preview"]["input_schema"]["properties"]

        skill_v2_draft = client.post(
            f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}/versions",
            headers=headers,
            json={
                "config": {
                    "skill_md": "# 依赖升级测试 Skill\n需要精确计算时调用升级测试计算器，并解释结果。",
                    "tool_version_ids": [tool_v2_payload["resource_version_id"]],
                    "knowledge_version_ids": [],
                },
                **_semantics("验证 Skill 显式依赖升级流程"),
            },
        )
        assert skill_v2_draft.status_code == 201, skill_v2_draft.text
        skill_v2_payload = skill_v2_draft.json()
        assert skill_v2_payload["version_number"] == 2
        assert skill_v2_payload["status"] == "DRAFT"

        draft_report = client.get(
            f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}/dependency-upgrades"
        )
        assert draft_report.status_code == 200, draft_report.text
        draft_payload = draft_report.json()
        assert draft_payload["based_on_draft"] is True
        assert draft_payload["skill_version_number"] == 2
        assert draft_payload["upgrades_available"] == 0
        assert draft_payload["dependencies"][0]["current"]["version_id"] == tool_v2_payload["resource_version_id"]
        assert draft_payload["dependencies"][0]["upgrade_available"] is False

        publish_skill_v2 = client.post(
            f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}/versions/{skill_v2_payload['resource_version_id']}/publish",
            headers=headers,
        )
        assert publish_skill_v2.status_code == 200, publish_skill_v2.text

        detail = client.get(f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}")
        assert detail.status_code == 200, detail.text
        versions = {item["version_number"]: item for item in detail.json()["versions"]}
        assert versions[1]["config"]["tool_version_ids"] == [tool_v1_payload["resource_version_id"]]
        assert versions[2]["config"]["tool_version_ids"] == [tool_v2_payload["resource_version_id"]]
        assert versions[1]["status"] == "PUBLISHED"
        assert versions[2]["status"] == "PUBLISHED"
