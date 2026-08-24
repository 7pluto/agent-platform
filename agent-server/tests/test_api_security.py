from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.secrets.vault import SecretRecord


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


def test_admin_can_revoke_grant_and_revoke_is_audited() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        exchange = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
        headers = {"X-CSRF-Token": exchange.json()["csrf_token"]}
        created = client.post(
            "/api/v1/resource-grants",
            headers=headers,
            json={
                "subject_type": "DEPT",
                "subject_id": "permission-test-dept",
                "resource_type": "TOOL",
                "resource_id": "permission-test-tool",
                "actions": ["VIEW", "USE"],
                "effect": "ALLOW",
            },
        )
        assert created.status_code == 201
        deleted = client.delete(f"/api/v1/resource-grants/{created.json()['grant_id']}", headers=headers)
        assert deleted.status_code == 204
        grants = client.get("/api/v1/resource-grants?resource_id=permission-test-tool", headers=headers)
        assert grants.status_code == 200
        assert grants.json() == []
        audit = client.get("/api/v1/audit-events?limit=20", headers=headers)
        assert audit.status_code == 200
        assert any(item["action"] == "resource_grant.delete" and item["resource_id"] == created.json()["grant_id"] for item in audit.json())


def test_secret_rotation_and_disable_never_return_or_audit_secret_value(monkeypatch) -> None:
    audits: list[tuple[str, str, dict]] = []

    def record(status: str = "ACTIVE") -> SecretRecord:
        return SecretRecord(
            secret_ref="vault://00000000-0000-0000-0000-000000000077",
            name="MCP: 企业 CRM",
            fingerprint="a" * 64,
            status=status,
            created_by="admin",
            created_at=datetime.now(timezone.utc),
        )

    class FakeVault:
        async def list(self, _principal):
            return [record()]

        async def rotate(self, _secret_id, _value, _principal):
            return record()

        async def disable(self, _secret_id, _principal):
            return record("DISABLED")

    class FakeGovernance:
        async def record_audit(self, _principal, action, _resource_type, resource_id, data):
            audits.append((action, resource_id, data))

    monkeypatch.setattr("app.api.routes.secrets.get_secret_vault", lambda: FakeVault())
    monkeypatch.setattr("app.api.routes.secrets.get_governance_store", lambda: FakeGovernance())
    with TestClient(app, base_url="https://testserver") as client:
        exchange = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
        headers = {"X-CSRF-Token": exchange.json()["csrf_token"]}
        listed = client.get("/api/v1/secrets")
        assert listed.status_code == 200
        rotated = client.post(
            "/api/v1/secrets/00000000-0000-0000-0000-000000000077/rotate",
            headers=headers,
            json={"value": "new-sensitive-value"},
        )
        assert rotated.status_code == 200
        disabled = client.post("/api/v1/secrets/00000000-0000-0000-0000-000000000077/disable", headers=headers)
        assert disabled.status_code == 200
        for payload in [listed.json()[0], rotated.json(), disabled.json()]:
            assert payload["secret_id"] == "00000000-0000-0000-0000-000000000077"
            assert not {"value", "encrypted_value", "api_key", "token", "secret_ref"}.intersection(payload)
        assert [item[0] for item in audits] == ["secret.rotate", "secret.disable"]
        assert "new-sensitive-value" not in str(audits)
        assert "vault://" not in str(audits)
