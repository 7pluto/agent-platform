from fastapi.testclient import TestClient

from app.main import app


def _session(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _deployment(client: TestClient, headers: dict[str, str], suffix: str = "one") -> str:
    agent = client.post("/api/v1/agents", json={"slug": f"workbench-agent-{suffix}", "display_name": "Workbench Agent"}, headers=headers).json()
    version = client.post(f"/api/v1/agents/{agent['agent_id']}/versions", json={}, headers=headers).json()
    client.post(f"/api/v1/agent-versions/{version['agent_version_id']}/publish", headers=headers)
    deployment = client.post("/api/v1/deployments", json={"agent_id": agent["agent_id"], "name": f"workbench-deployment-{suffix}"}, headers=headers).json()
    revision = client.post(f"/api/v1/deployments/{deployment['deployment_id']}/revisions", json={"agent_version_id": version["agent_version_id"]}, headers=headers).json()
    client.post(f"/api/v1/deployments/{deployment['deployment_id']}/revisions/{revision['deployment_revision_id']}/activate", headers=headers)
    return deployment["deployment_id"]


def test_deployment_conversation_and_run_message_are_idempotent() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        deployment_id = _deployment(client, headers)
        session = client.post(f"/api/v1/deployments/{deployment_id}/conversations", json={"title": "新会话"}, headers=headers)
        assert session.status_code == 201
        conversation = session.json()["conversation"]
        thread = session.json()["thread"]
        payload = {"deployment_id": deployment_id, "conversation_id": conversation["conversation_id"], "thread_id": thread["thread_id"], "message": "项目代号是星河"}
        run_headers = {**headers, "Idempotency-Key": "workbench-run-1"}
        first = client.post(f"/api/v1/deployments/{deployment_id}/runs", json=payload, headers=run_headers)
        second = client.post(f"/api/v1/deployments/{deployment_id}/runs", json=payload, headers=run_headers)
        assert first.status_code == 202
        assert second.json()["run_id"] == first.json()["run_id"]
        messages = client.get(f"/api/v1/threads/{thread['thread_id']}/messages").json()
        assert [(item["role"], item["content"]) for item in messages] == [("USER", "项目代号是星河"), ("ASSISTANT", "Mock response: 项目代号是星河")]
        listed = client.get(f"/api/v1/deployments/{deployment_id}/conversations").json()
        assert listed[0]["title"] == "项目代号是星河"


def test_conversation_cannot_run_against_another_deployment() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        first_deployment = _deployment(client, headers, "two")
        # Slugs in the in-memory store are global for this process, so make a second deployment for the same Agent.
        agent_id = client.get("/api/v1/agents").json()[-1]["agent_id"]
        versions = client.get(f"/api/v1/agents/{agent_id}/versions").json()
        second = client.post("/api/v1/deployments", json={"agent_id": agent_id, "name": "workbench-second"}, headers=headers).json()
        revision = client.post(f"/api/v1/deployments/{second['deployment_id']}/revisions", json={"agent_version_id": versions[-1]["agent_version_id"]}, headers=headers).json()
        client.post(f"/api/v1/deployments/{second['deployment_id']}/revisions/{revision['deployment_revision_id']}/activate", headers=headers)
        session = client.post(f"/api/v1/deployments/{first_deployment}/conversations", json={"title": "A"}, headers=headers).json()
        response = client.post(f"/api/v1/deployments/{second['deployment_id']}/runs", json={"deployment_id": second["deployment_id"], "conversation_id": session["conversation"]["conversation_id"], "thread_id": session["thread"]["thread_id"], "message": "hello"}, headers={**headers, "Idempotency-Key": "wrong-deployment"})
        assert response.status_code == 409
        assert response.json()["code"] == "CONVERSATION_DEPLOYMENT_MISMATCH"


def test_publish_configuration_is_idempotent_and_can_roll_back() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        deployment_id = _deployment(client, headers, "publish")
        publish_headers = {**headers, "Idempotency-Key": "configuration-1"}
        payload = {
            "specification": {"runtime_policy": {"max_steps": 8}},
            "publication_scope": "SELECTED_SUBJECTS",
            "publication_subjects": [{"subject_type": "DEPT", "subject_id": "200"}],
        }
        first = client.post(
            f"/api/v1/deployments/{deployment_id}/publish-configuration",
            json=payload,
            headers=publish_headers,
        )
        second = client.post(
            f"/api/v1/deployments/{deployment_id}/publish-configuration",
            json=payload,
            headers=publish_headers,
        )
        assert first.status_code == 200
        assert second.json() == first.json()
        capabilities = client.get(f"/api/v1/deployments/{deployment_id}/capabilities").json()
        assert capabilities["publication_scope"] == "SELECTED_SUBJECTS"
        assert {"subject_type": "DEPT", "subject_id": "200"} in capabilities["publication_subjects"]
        revisions = client.get(f"/api/v1/deployments/{deployment_id}/revisions").json()
        assert len(revisions) == 2
        old_revision_id = revisions[0]["deployment_revision_id"]
        rollback = client.post(
            f"/api/v1/deployments/{deployment_id}/revisions/{old_revision_id}/activate",
            headers=headers,
        )
        assert rollback.status_code == 200
        assert rollback.json()["active_revision_id"] == old_revision_id


def test_workbench_resource_detail_and_configuration_draft() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        resource = client.post(
            "/api/v1/resources",
            json={
                "resource_type": "PROMPT",
                "slug": "workbench-detail-prompt",
                "display_name": "工作台详情提示词",
                "description": "用于验证资源详情聚合。",
                "draft_config": {"template": "你是企业助手。"},
            },
            headers=headers,
        ).json()
        version = client.post(
            f"/api/v1/resources/{resource['resource_id']}/versions",
            json={"config": {"template": "你是企业助手。"}},
            headers=headers,
        ).json()
        client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/publish", headers=headers)
        listing = client.get("/api/v1/workbench/resources?query=%E8%AF%A6%E6%83%85").json()
        assert listing["meta"]["total"] == 1
        detail = client.get(f"/api/v1/workbench/resources/{resource['resource_id']}").json()
        assert detail["resource"]["display_name"] == "工作台详情提示词"
        assert detail["versions"][0]["display_name"] == "工作台详情提示词"
        assert detail["resource"]["owner_user_id"]
        assert detail["resource"]["source_type"]

        deployment_id = _deployment(client, headers, "draft")
        initial = client.get(f"/api/v1/deployments/{deployment_id}/configuration-draft").json()
        assert initial["lock_version"] == 0
        save = client.put(
            f"/api/v1/deployments/{deployment_id}/configuration-draft",
            json={"specification": {"runtime_policy": {"max_steps": 5}}, "base_revision_id": initial["base_revision_id"]},
            headers=headers,
        )
        assert save.status_code == 200
        saved = save.json()
        conflict = client.put(
            f"/api/v1/deployments/{deployment_id}/configuration-draft",
            json={"specification": {}, "lock_version": saved["lock_version"] + 1},
            headers=headers,
        )
        assert conflict.status_code == 409
        validation = client.post(
            f"/api/v1/deployments/{deployment_id}/configuration-draft/validate",
            json={"specification": saved["specification"], "base_revision_id": saved["base_revision_id"]},
            headers=headers,
        )
        assert validation.status_code == 200
        assert validation.json()["valid"]
