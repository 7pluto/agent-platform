from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.errors import ApiError
from app.main import app


class FakeVault:
    async def create(self, *_args, **_kwargs):
        return SimpleNamespace(secret_ref="vault://22222222-2222-2222-2222-222222222222", fingerprint="safe-fingerprint")


def _session(client: TestClient) -> dict[str, str]:
    payload = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"}).json()
    return {"X-CSRF-Token": payload["csrf_token"]}


def _draft_resource(client: TestClient, slug: str, resource_type: str) -> dict:
    definitions = client.get(f"/api/v1/resources?resource_type={resource_type}").json()
    definition = next(item for item in definitions if item["slug"] == slug)
    versions = client.get(f"/api/v1/resources/{definition['resource_id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["status"] == "DRAFT"
    return versions[0]


def test_failed_mcp_probe_leaves_connection_draft(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise ApiError(502, "MCP_UPSTREAM_UNAVAILABLE", "MCP endpoint is unavailable")

    monkeypatch.setattr("app.api.routes.mcp.get_secret_vault", lambda: FakeVault())
    monkeypatch.setattr("app.api.routes.mcp.mcp_client.discover", fail)
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        response = client.post("/api/v1/mcp-connections", headers=headers, json={
            "slug": "mcp-failed-draft-test", "display_name": "失败 MCP Draft",
            "endpoint": "https://mcp-invalid.example/mcp", "api_key": "invalid-mcp-key",
        })
        assert response.status_code == 502
        assert "invalid-mcp-key" not in response.text
        version = _draft_resource(client, "mcp-failed-draft-test", "MCP_CONNECTION")
        assert version["config"]["secret_ref"].startswith("vault://")
        validation = client.get(f"/api/v1/resource-versions/{version['resource_version_id']}/validation-runs").json()
        assert validation[0]["status"] == "FAILED"
        assert validation[0]["result"]["code"] == "MCP_UPSTREAM_UNAVAILABLE"

        async def no_auth(*_args, **_kwargs):
            return {}
        async def success(*_args, **_kwargs):
            return [{"name": "query_customer", "inputSchema": {"type": "object"}}]
        monkeypatch.setattr("app.api.routes.resource_registry.mcp_auth_headers", no_auth)
        monkeypatch.setattr("app.api.routes.resource_registry.mcp_client.discover", success)
        tested = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/test", headers=headers, json={"input": {}})
        assert tested.status_code == 200
        assert tested.json()["tool_count"] == 1
        validated = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/validate", headers=headers)
        assert validated.status_code == 200
        assert validated.json()["status"] == "SUCCEEDED"
        published = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/publish", headers=headers)
        assert published.status_code == 200
        assert published.json()["status"] == "PUBLISHED"


def test_failed_ragflow_probe_leaves_connection_draft(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise ApiError(502, "RAGFLOW_UPSTREAM_ERROR", "RAGFlow request failed")

    monkeypatch.setattr("app.api.routes.ragflow.get_secret_vault", lambda: FakeVault())
    monkeypatch.setattr("app.api.routes.ragflow.RagflowKnowledgeProvider.discover_datasets", fail)
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        response = client.post("/api/v1/ragflow-connections", headers=headers, json={
            "slug": "ragflow-failed-draft-test", "display_name": "失败 RAGFlow Draft",
            "endpoint": "https://ragflow-invalid.example", "api_key": "invalid-ragflow-key",
        })
        assert response.status_code == 502
        assert "invalid-ragflow-key" not in response.text
        version = _draft_resource(client, "ragflow-failed-draft-test", "KNOWLEDGE_CONNECTION")
        validation = client.get(f"/api/v1/resource-versions/{version['resource_version_id']}/validation-runs").json()
        assert validation[0]["status"] == "FAILED"
        assert validation[0]["result"]["code"] == "RAGFLOW_UPSTREAM_ERROR"

        async def success(*_args, **_kwargs):
            return [{"id": "dataset-hr", "name": "人事制度库"}]
        monkeypatch.setattr("app.api.routes.resource_registry.RagflowKnowledgeProvider.discover_datasets", success)
        tested = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/test", headers=headers, json={"input": {}})
        assert tested.status_code == 200
        assert tested.json()["dataset_count"] == 1
        validated = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/validate", headers=headers)
        assert validated.status_code == 200
        assert validated.json()["status"] == "SUCCEEDED"
        published = client.post(f"/api/v1/resource-versions/{version['resource_version_id']}/publish", headers=headers)
        assert published.status_code == 200
        assert published.json()["status"] == "PUBLISHED"


def test_failed_model_probe_leaves_model_version_draft(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise ApiError(502, "MODEL_UPSTREAM_UNAVAILABLE", "model provider request failed")

    monkeypatch.setattr("app.api.routes.resources.get_secret_vault", lambda: FakeVault())
    monkeypatch.setattr("app.api.routes.resources.OpenAICompatibleModel.test_connection", fail)
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        response = client.post("/api/v1/models/with-secret", headers=headers, json={
            "slug": "model-failed-draft-test", "display_name": "失败 Model Draft",
            "base_url": "https://model-invalid.example/v1", "model": "invalid-model",
            "api_key": "invalid-model-key", "model_mode": "CHAT",
        })
        assert response.status_code == 502
        assert "invalid-model-key" not in response.text
        models = client.get("/api/v1/models").json()
        model = next(item for item in models if item["slug"] == "model-failed-draft-test")
        versions = client.get(f"/api/v1/models/{model['model_id']}/versions").json()
        assert len(versions) == 1
        assert versions[0]["status"] == "DRAFT"
        assert versions[0]["config"]["secret_ref"].startswith("vault://")
        assert "invalid-model-key" not in str(versions[0])
