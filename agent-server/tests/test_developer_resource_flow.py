import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import ensure_resource_action
from app.core.errors import ApiError
from app.iam.models import Principal
from app.main import app


def _exchange(client: TestClient, ticket: str) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": ticket})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload, {"X-CSRF-Token": payload["csrf_token"]}


def _semantics(summary: str) -> dict:
    return {
        "one_line_summary": summary,
        "when_to_use": "当 Agent 需要完成该业务动作时使用",
        "when_not_to_use": "与当前业务任务无关时不要使用",
        "input_summary": "接收当前业务任务需要的参数",
        "output_summary": "返回结构化业务结果",
        "risk_level": "LOW",
        "read_only": True,
        "publication_scope": "PERSONAL",
        "publication_subjects": [],
    }


def test_ruoyi_developer_can_publish_owned_skill_but_admin_needs_explicit_business_grant() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        developer_session, developer_headers = _exchange(client, "dev-developer-ticket")
        assert developer_session["principal"]["external_user_id"] == "user-developer"
        assert "agent_developer" in developer_session["principal"]["role_codes"]
        assert "agent_admin" not in developer_session["principal"]["role_codes"]

        tool = client.post(
            "/api/v1/developer/resources/native-tools",
            headers=developer_headers,
            json={
                "slug": "developer-calculator",
                "display_name": "开发者计算器",
                "description": "执行受控数学计算",
                "native_name": "calculator",
                "tool_name": "developer_calculator",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                **_semantics("为 Agent 提供只读数学计算能力"),
            },
        )
        assert tool.status_code == 201, tool.text
        tool_payload = tool.json()

        skill = client.post(
            "/api/v1/developer/resources/skills",
            headers=developer_headers,
            json={
                "slug": "developer-calculation-skill",
                "display_name": "业务计算 Skill",
                "description": "指导 Agent 在需要计算时调用受控计算器",
                "skill_md": "# 业务计算 Skill\n当问题需要精确计算时调用开发者计算器，并解释结果。",
                "tool_version_ids": [tool_payload["resource_version_id"]],
                "knowledge_version_ids": [],
                **_semantics("完成需要精确数值计算的业务任务"),
            },
        )
        assert skill.status_code == 201, skill.text

        admin_session, admin_headers = _exchange(client, "dev-ticket")
        assert "agent_admin" in admin_session["principal"]["role_codes"]
        admin_principal = Principal(
            provider="ruoyi-mock",
            external_user_id="user-demo",
            external_org_id="org-demo",
            tenant_id="tenant-demo",
            display_name="Demo Admin",
            dept_ids=("dept-demo",),
            role_codes=("agent_admin",),
        )

        # Platform-admin status alone must not confer business USE permission.
        with pytest.raises(ApiError) as denied:
            asyncio.run(ensure_resource_action(
                admin_principal,
                "USE",
                "TOOL",
                tool_payload["resource_version_id"],
            ))
        assert denied.value.code == "RESOURCE_FORBIDDEN"

        # The developer's ownership grant is stored on the stable Definition ID.
        grants = client.get(
            f"/api/v1/resource-grants?resource_id={tool_payload['resource_id']}",
            headers=admin_headers,
        )
        assert grants.status_code == 200, grants.text
        owner_grant = next(
            item for item in grants.json()
            if item["subject_type"] == "USER" and item["subject_id"] == "user-developer"
        )
        assert {"VIEW", "USE", "EDIT", "PUBLISH", "MANAGE"}.issubset(set(owner_grant["actions"]))

        # Explicit RuoYi Role grant makes the same immutable Tool Version usable.
        role_grant = client.post(
            "/api/v1/resource-grants",
            headers=admin_headers,
            json={
                "subject_type": "ROLE",
                "subject_id": "agent_admin",
                "resource_type": "TOOL",
                "resource_id": tool_payload["resource_id"],
                "actions": ["VIEW", "USE"],
                "effect": "ALLOW",
            },
        )
        assert role_grant.status_code == 201, role_grant.text

        asyncio.run(ensure_resource_action(
            admin_principal,
            "USE",
            "TOOL",
            tool_payload["resource_version_id"],
        ))
