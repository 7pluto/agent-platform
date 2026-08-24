from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.core.errors import ApiError
from app.main import app


def _payload(slug: str) -> dict:
    return {
        "slug": slug,
        "display_name": "验收失败的 Dify 应用",
        "description": "连接失败时保留 Draft",
        "flow_type": "CHATFLOW",
        "base_url": "https://dify-invalid.example/v1",
        "api_key": "invalid-app-key",
        "tool_name": "dify_failed_draft",
        "owner_user_id": "developer",
        "one_line_summary": "验证失败 Draft",
        "when_to_use": "验证发布失败行为时",
        "input_summary": "测试问题",
        "output_summary": "不会产生可用输出",
        "business_line": "平台研发",
        "audience": "平台管理员",
        "usage_scenarios": "连接验证",
        "publication_scope": "PERSONAL",
    }


def test_failed_dify_validation_leaves_a_non_published_draft(monkeypatch) -> None:
    async def fail_connection(*_args, **_kwargs):
        raise ApiError(502, "DIFY_CREDENTIAL_REJECTED", "Dify application could not be inspected")

    monkeypatch.setattr("app.api.routes.resource_registry.DifyFlowClient.test_connection", fail_connection)
    class FakeVault:
        async def create(self, *_args, **_kwargs):
            return SimpleNamespace(secret_ref="vault://11111111-1111-1111-1111-111111111111", fingerprint="safe-fingerprint")
    monkeypatch.setattr("app.api.routes.resource_registry.get_secret_vault", lambda: FakeVault())
    with TestClient(app, base_url="https://testserver") as client:
        session = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"}).json()
        headers = {"X-CSRF-Token": session["csrf_token"]}
        response = client.post("/api/v1/dify-applications", headers=headers, json=_payload("dify-failed-draft-test"))
        assert response.status_code == 502
        assert response.json()["code"] == "DIFY_CREDENTIAL_REJECTED"
        assert "invalid-app-key" not in response.text

        definitions = client.get("/api/v1/resources?resource_type=TOOL").json()
        definition = next(item for item in definitions if item["slug"] == "dify-failed-draft-test")
        versions = client.get(f"/api/v1/resources/{definition['resource_id']}/versions").json()
        assert len(versions) == 1
        assert versions[0]["status"] == "DRAFT"
        assert versions[0]["config"]["secret_ref"].startswith("vault://")
        assert "invalid-app-key" not in str(versions[0])

        validation = client.get(f"/api/v1/resource-versions/{versions[0]['resource_version_id']}/validation-runs").json()
        assert validation[0]["status"] == "FAILED"
        assert validation[0]["result"]["code"] == "DIFY_CREDENTIAL_REJECTED"
