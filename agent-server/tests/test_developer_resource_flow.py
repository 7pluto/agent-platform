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

        context = client.get("/api/v1/developer/resources/context")
        assert context.status_code == 200, context.text
        assert context.json()["developer"] is True
        assert context.json()["external_user_id"] == "user-developer"

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
        skill_payload = skill.json()

        owned = client.get("/api/v1/developer/resources/mine")
        assert owned.status_code == 200, owned.text
        owned_ids = {item["resource_id"] for item in owned.json()}
        assert tool_payload["resource_id"] in owned_ids
        assert skill_payload["resource_id"] in owned_ids

        available = client.get("/api/v1/developer/resources/available")
        assert available.status_code == 200, available.text
        available_ids = {item["resource_id"] for item in available.json()}
        assert tool_payload["resource_id"] in available_ids
        assert skill_payload["resource_id"] in available_ids

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

        with pytest.raises(ApiError) as denied:
            asyncio.run(ensure_resource_action(
                admin_principal,
                "USE",
                "TOOL",
                tool_payload["resource_version_id"],
            ))
        assert denied.value.code == "RESOURCE_FORBIDDEN"

        admin_available_before = client.get("/api/v1/developer/resources/available")
        assert admin_available_before.status_code == 200, admin_available_before.text
        assert tool_payload["resource_id"] not in {item["resource_id"] for item in admin_available_before.json()}

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

        admin_available_after = client.get("/api/v1/developer/resources/available")
        assert admin_available_after.status_code == 200, admin_available_after.text
        assert tool_payload["resource_id"] in {item["resource_id"] for item in admin_available_after.json()}


def test_developer_resource_edit_creates_draft_and_publishes_new_immutable_version() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        _, headers = _exchange(client, "dev-developer-ticket")
        created = client.post(
            "/api/v1/developer/resources/prompts",
            headers=headers,
            json={
                "slug": "version-lifecycle-prompt",
                "display_name": "版本演进 Prompt",
                "description": "用于验证开发者版本工作流",
                "template": "你是 V1 助手。",
                **_semantics("V1：提供基础业务回答规则"),
            },
        )
        assert created.status_code == 201, created.text
        v1 = created.json()
        resource_id = v1["resource_id"]

        detail = client.get(f"/api/v1/developer/resources/{resource_id}")
        assert detail.status_code == 200, detail.text
        initial = detail.json()
        assert initial["editable"] is True
        assert initial["active_draft_version_id"] is None
        assert initial["editable_config"]["template"] == "你是 V1 助手。"
        assert [(item["version_number"], item["status"]) for item in initial["versions"]] == [(1, "PUBLISHED")]

        draft = client.post(
            f"/api/v1/developer/resources/{resource_id}/versions",
            headers=headers,
            json={
                "config": {"template": "你是 V2 草稿助手。"},
                **_semantics("V2：增加更清晰的业务回答规则"),
            },
        )
        assert draft.status_code == 201, draft.text
        v2_draft = draft.json()
        assert v2_draft["version_number"] == 2
        assert v2_draft["status"] == "DRAFT"

        duplicate_draft = client.post(
            f"/api/v1/developer/resources/{resource_id}/versions",
            headers=headers,
            json={
                "config": {"template": "不应创建 V3。"},
                **_semantics("重复 Draft"),
            },
        )
        assert duplicate_draft.status_code == 409
        assert duplicate_draft.json()["code"] == "RESOURCE_DRAFT_EXISTS"

        updated = client.put(
            f"/api/v1/developer/resources/{resource_id}/versions/{v2_draft['resource_version_id']}",
            headers=headers,
            json={
                "config": {"template": "你是最终 V2 助手。"},
                **_semantics("V2：最终业务回答规则"),
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "DRAFT"
        assert updated.json()["config"]["template"] == "你是最终 V2 助手。"

        before_publish = client.get(f"/api/v1/developer/resources/{resource_id}").json()
        versions_before = {item["version_number"]: item for item in before_publish["versions"]}
        assert versions_before[1]["status"] == "PUBLISHED"
        assert versions_before[1]["config"]["template"] == "你是 V1 助手。"
        assert versions_before[2]["status"] == "DRAFT"
        assert versions_before[2]["config"]["template"] == "你是最终 V2 助手。"

        published = client.post(
            f"/api/v1/developer/resources/{resource_id}/versions/{v2_draft['resource_version_id']}/publish",
            headers=headers,
        )
        assert published.status_code == 200, published.text
        assert published.json()["version_number"] == 2
        assert published.json()["status"] == "PUBLISHED"

        final_detail = client.get(f"/api/v1/developer/resources/{resource_id}")
        assert final_detail.status_code == 200, final_detail.text
        final_payload = final_detail.json()
        assert final_payload["active_draft_version_id"] is None
        final_versions = {item["version_number"]: item for item in final_payload["versions"]}
        assert final_versions[1]["status"] == "PUBLISHED"
        assert final_versions[1]["config"]["template"] == "你是 V1 助手。"
        assert final_versions[2]["status"] == "PUBLISHED"
        assert final_versions[2]["config"]["template"] == "你是最终 V2 助手。"
        assert final_versions[1]["content_hash"] != final_versions[2]["content_hash"]

        mine = client.get("/api/v1/developer/resources/mine")
        assert mine.status_code == 200, mine.text
        current = next(item for item in mine.json() if item["resource_id"] == resource_id)
        assert current["version_number"] == 2
        assert current["one_line_summary"] == "V2：最终业务回答规则"
