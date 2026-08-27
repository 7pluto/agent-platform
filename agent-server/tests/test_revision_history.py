from fastapi.testclient import TestClient

from app.main import app


def _admin(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_revision_history_keeps_publication_snapshot_without_backfilling_old_revision() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _admin(client)

        agent = client.post(
            "/api/v1/agents",
            headers=headers,
            json={
                "slug": "revision-history-agent",
                "display_name": "Revision History Agent",
                "description": "revision history test",
                "draft_spec": {},
            },
        )
        assert agent.status_code == 201, agent.text
        agent_id = agent.json()["agent_id"]

        version = client.post(f"/api/v1/agents/{agent_id}/versions", headers=headers, json={})
        assert version.status_code == 201, version.text
        version_id = version.json()["agent_version_id"]
        published = client.post(f"/api/v1/agent-versions/{version_id}/publish", headers=headers)
        assert published.status_code == 200, published.text

        deployment = client.post(
            "/api/v1/deployments",
            headers=headers,
            json={"agent_id": agent_id, "name": "revision-history-deployment", "description": "test"},
        )
        assert deployment.status_code == 201, deployment.text
        deployment_id = deployment.json()["deployment_id"]

        revision1 = client.post(
            f"/api/v1/deployments/{deployment_id}/revisions",
            headers=headers,
            json={"agent_version_id": version_id, "overrides": {}},
        )
        assert revision1.status_code == 201, revision1.text
        revision1_id = revision1.json()["deployment_revision_id"]
        activated = client.post(
            f"/api/v1/deployments/{deployment_id}/revisions/{revision1_id}/activate",
            headers=headers,
        )
        assert activated.status_code == 200, activated.text

        revision2 = client.post(
            f"/api/v1/deployments/{deployment_id}/publish-configuration",
            headers={**headers, "Idempotency-Key": "revision-history-personal"},
            json={
                "specification": {},
                "base_revision_id": revision1_id,
                "publication_scope": "PERSONAL",
                "publication_subjects": [],
            },
        )
        assert revision2.status_code == 200, revision2.text
        revision2_id = revision2.json()["deployment_revision_id"]

        revision3 = client.post(
            f"/api/v1/deployments/{deployment_id}/publish-configuration",
            headers={**headers, "Idempotency-Key": "revision-history-role"},
            json={
                "specification": {},
                "base_revision_id": revision2_id,
                "publication_scope": "SELECTED_SUBJECTS",
                "publication_subjects": [{"subject_type": "ROLE", "subject_id": "agent_admin"}],
            },
        )
        assert revision3.status_code == 200, revision3.text
        revision3_id = revision3.json()["deployment_revision_id"]

        response = client.get(f"/api/v1/workbench/deployments/{deployment_id}/revision-history")
        assert response.status_code == 200, response.text
        history = response.json()
        assert [item["revision_number"] for item in history] == [3, 2, 1]

        by_id = {item["revision_id"]: item for item in history}
        assert by_id[revision1_id]["publication"]["available"] is False
        assert by_id[revision2_id]["publication"]["available"] is True
        assert by_id[revision2_id]["publication"]["scope"] == "PERSONAL"
        assert by_id[revision3_id]["publication"]["available"] is True
        assert by_id[revision3_id]["publication"]["scope"] == "SELECTED_SUBJECTS"
        assert {f"{item['subject_type']}:{item['subject_id']}" for item in by_id[revision3_id]["publication"]["subjects"]} >= {
            "USER:user-demo",
            "ROLE:agent_admin",
        }
        assert by_id[revision3_id]["active"] is True
        assert by_id[revision2_id]["active"] is False
