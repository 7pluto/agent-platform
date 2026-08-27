from fastapi.testclient import TestClient

from app.main import app


def _exchange(client: TestClient, ticket: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": ticket})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _semantics(summary: str) -> dict:
    return {
        "one_line_summary": summary,
        "when_to_use": "当 Revision 对比测试需要该能力时使用",
        "when_not_to_use": "无关任务不要使用",
        "input_summary": "接收测试参数",
        "output_summary": "返回测试结果",
        "risk_level": "LOW",
        "read_only": True,
        "tags": ["revision-history-diff"],
        "publication_scope": "PERSONAL",
        "publication_subjects": [],
    }


def test_revision_history_preserves_skill_and_dependency_version_pins() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        developer_headers = _exchange(client, "dev-developer-ticket")

        tool_v1 = client.post(
            "/api/v1/developer/resources/native-tools",
            headers=developer_headers,
            json={
                "slug": "revision-history-calculator",
                "display_name": "Revision 历史计算器",
                "description": "验证历史依赖版本",
                "native_name": "calculator",
                "tool_name": "revision_history_calculator",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                **_semantics("基础计算能力"),
            },
        )
        assert tool_v1.status_code == 201, tool_v1.text
        tool_v1_payload = tool_v1.json()

        skill_v1 = client.post(
            "/api/v1/developer/resources/skills",
            headers=developer_headers,
            json={
                "slug": "revision-history-skill",
                "display_name": "Revision 历史 Skill",
                "description": "验证 Skill 历史依赖版本",
                "skill_md": "# Revision 历史 Skill\n需要计算时调用 Revision 历史计算器。",
                "tool_version_ids": [tool_v1_payload["resource_version_id"]],
                "knowledge_version_ids": [],
                **_semantics("封装计算步骤"),
            },
        )
        assert skill_v1.status_code == 201, skill_v1.text
        skill_v1_payload = skill_v1.json()

        tool_v2 = client.post(
            f"/api/v1/developer/resources/{tool_v1_payload['resource_id']}/versions",
            headers=developer_headers,
            json={
                "config": {
                    "kind": "NATIVE",
                    "native_name": "calculator",
                    "tool_name": "revision_history_calculator",
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
                **_semantics("支持精度参数的计算能力"),
            },
        )
        assert tool_v2.status_code == 201, tool_v2.text
        tool_v2_payload = tool_v2.json()
        publish_tool_v2 = client.post(
            f"/api/v1/developer/resources/{tool_v1_payload['resource_id']}/versions/{tool_v2_payload['resource_version_id']}/publish",
            headers=developer_headers,
        )
        assert publish_tool_v2.status_code == 200, publish_tool_v2.text

        skill_v2 = client.post(
            f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}/versions",
            headers=developer_headers,
            json={
                "config": {
                    "skill_md": "# Revision 历史 Skill\n需要计算时调用新版 Revision 历史计算器。",
                    "tool_version_ids": [tool_v2_payload["resource_version_id"]],
                    "knowledge_version_ids": [],
                },
                **_semantics("封装新版计算步骤"),
            },
        )
        assert skill_v2.status_code == 201, skill_v2.text
        skill_v2_payload = skill_v2.json()
        publish_skill_v2 = client.post(
            f"/api/v1/developer/resources/{skill_v1_payload['resource_id']}/versions/{skill_v2_payload['resource_version_id']}/publish",
            headers=developer_headers,
        )
        assert publish_skill_v2.status_code == 200, publish_skill_v2.text

        admin_headers = _exchange(client, "dev-ticket")
        for resource_type, resource_id in (
            ("TOOL", tool_v1_payload["resource_id"]),
            ("SKILL", skill_v1_payload["resource_id"]),
        ):
            grant = client.post(
                "/api/v1/resource-grants",
                headers=admin_headers,
                json={
                    "subject_type": "ROLE",
                    "subject_id": "agent_admin",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "actions": ["VIEW", "USE"],
                    "effect": "ALLOW",
                },
            )
            assert grant.status_code == 201, grant.text

        agent = client.post(
            "/api/v1/agents",
            headers=admin_headers,
            json={
                "slug": "revision-history-version-agent",
                "display_name": "Revision 历史版本 Agent",
                "description": "验证 Revision 资源版本对比",
                "draft_spec": {"skill_version_ids": [skill_v1_payload["resource_version_id"]]},
            },
        )
        assert agent.status_code == 201, agent.text
        agent_id = agent.json()["agent_id"]

        agent_v1 = client.post(f"/api/v1/agents/{agent_id}/versions", headers=admin_headers, json={})
        assert agent_v1.status_code == 201, agent_v1.text
        agent_v1_id = agent_v1.json()["agent_version_id"]
        published_agent_v1 = client.post(f"/api/v1/agent-versions/{agent_v1_id}/publish", headers=admin_headers)
        assert published_agent_v1.status_code == 200, published_agent_v1.text

        deployment = client.post(
            "/api/v1/deployments",
            headers=admin_headers,
            json={"agent_id": agent_id, "name": "revision-history-version-deployment", "description": "test"},
        )
        assert deployment.status_code == 201, deployment.text
        deployment_id = deployment.json()["deployment_id"]

        revision1 = client.post(
            f"/api/v1/deployments/{deployment_id}/revisions",
            headers=admin_headers,
            json={"agent_version_id": agent_v1_id, "overrides": {}},
        )
        assert revision1.status_code == 201, revision1.text
        revision1_id = revision1.json()["deployment_revision_id"]
        activated = client.post(
            f"/api/v1/deployments/{deployment_id}/revisions/{revision1_id}/activate",
            headers=admin_headers,
        )
        assert activated.status_code == 200, activated.text

        revision2 = client.post(
            f"/api/v1/deployments/{deployment_id}/publish-configuration",
            headers={**admin_headers, "Idempotency-Key": "revision-history-skill-v2"},
            json={
                "specification": {"skill_version_ids": [skill_v2_payload["resource_version_id"]]},
                "base_revision_id": revision1_id,
                "publication_scope": "PERSONAL",
                "publication_subjects": [],
            },
        )
        assert revision2.status_code == 200, revision2.text
        revision2_id = revision2.json()["deployment_revision_id"]

        response = client.get(f"/api/v1/workbench/deployments/{deployment_id}/revision-history")
        assert response.status_code == 200, response.text
        by_id = {item["revision_id"]: item for item in response.json()}

        revision1_skill = next(item for item in by_id[revision1_id]["capabilities"] if item["resource_type"] == "SKILL")
        revision2_skill = next(item for item in by_id[revision2_id]["capabilities"] if item["resource_type"] == "SKILL")

        assert revision1_skill["resource_id"] == skill_v1_payload["resource_id"]
        assert revision2_skill["resource_id"] == skill_v1_payload["resource_id"]
        assert revision1_skill["version_number"] == 1
        assert revision2_skill["version_number"] == 2

        assert len(revision1_skill["dependencies"]) == 1
        assert len(revision2_skill["dependencies"]) == 1
        dependency_v1 = revision1_skill["dependencies"][0]
        dependency_v2 = revision2_skill["dependencies"][0]
        assert dependency_v1["resource_id"] == tool_v1_payload["resource_id"]
        assert dependency_v2["resource_id"] == tool_v1_payload["resource_id"]
        assert dependency_v1["version_id"] == tool_v1_payload["resource_version_id"]
        assert dependency_v2["version_id"] == tool_v2_payload["resource_version_id"]
        assert dependency_v1["version_number"] == 1
        assert dependency_v2["version_number"] == 2
        assert dependency_v1["display_name"] == "Revision 历史计算器"
        assert dependency_v2["display_name"] == "Revision 历史计算器"
