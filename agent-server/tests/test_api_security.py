from fastapi.testclient import TestClient

from app.main import app


def test_cookie_authenticated_mutations_require_csrf_token() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        exchange = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
        assert exchange.status_code == 200

        rejected = client.post(
            "/api/v1/agents",
            json={"slug": "csrf-rejected", "display_name": "CSRF rejected"},
        )
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "CSRF_INVALID"

        accepted = client.post(
            "/api/v1/agents",
            json={"slug": "csrf-accepted", "display_name": "CSRF accepted"},
            headers={"X-CSRF-Token": exchange.json()["csrf_token"]},
        )
        assert accepted.status_code == 201

def test_run_rejects_missing_thread_for_a_conversation() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        exchange = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
        headers = {"X-CSRF-Token": exchange.json()["csrf_token"]}
        agent = client.post("/api/v1/agents", json={"slug": "conversation-run", "display_name": "Conversation run"}, headers=headers)
        version = client.post(f"/api/v1/agents/{agent.json()['agent_id']}/versions", json={}, headers=headers)
        client.post(f"/api/v1/agent-versions/{version.json()['agent_version_id']}/publish", headers=headers)
        deployment = client.post("/api/v1/deployments", json={"agent_id": agent.json()["agent_id"], "name": "conversation-deployment"}, headers=headers)
        revision = client.post(f"/api/v1/deployments/{deployment.json()['deployment_id']}/revisions", json={"agent_version_id": version.json()["agent_version_id"]}, headers=headers)
        client.post(f"/api/v1/deployments/{deployment.json()['deployment_id']}/revisions/{revision.json()['deployment_revision_id']}/activate", headers=headers)
        conversation = client.post("/api/v1/conversations", json={"title": "Conversation"}, headers=headers)
        rejected = client.post(
            f"/api/v1/deployments/{deployment.json()['deployment_id']}/runs",
            json={"deployment_id": deployment.json()["deployment_id"], "conversation_id": conversation.json()["conversation_id"], "message": "hello"},
            headers={**headers, "Idempotency-Key": "conversation-no-thread"},
        )
        assert rejected.status_code == 400
        assert rejected.json()["code"] == "THREAD_REQUIRED"
        audit = client.get("/api/v1/audit-events", headers=headers)
        assert audit.status_code == 200