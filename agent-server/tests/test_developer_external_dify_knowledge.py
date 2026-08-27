import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.governance.models import GrantAction, GrantEffect, ResourceGrantCreate, SubjectType
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.knowledge.jobs import ingest_jobs
from app.knowledge.models import FileStatus
from app.knowledge.service import get_knowledge_file_service
from app.main import app
from app.resources.models import ModelDefinitionCreate, ModelVersionCreate
from app.resources.store_factory import get_resource_store
from app.runtime.dify_flow import DifyFlowClient
from app.secrets.vault import get_secret_vault


def _exchange(client: TestClient, ticket: str = "dev-developer-ticket") -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": ticket})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload, {"X-CSRF-Token": payload["csrf_token"]}


def _semantics(summary: str) -> dict:
    return {
        "one_line_summary": summary,
        "when_to_use": "测试需要该能力时使用",
        "when_not_to_use": "与测试目标无关时不要使用",
        "input_summary": "按输入契约提供测试参数",
        "output_summary": "返回结构化测试结果",
        "risk_level": "LOW",
        "read_only": True,
        "publication_scope": "PERSONAL",
        "publication_subjects": [],
    }


def test_developer_dify_onboarding_and_playground(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_test_connection(self, test_query="请回复 OK"):
        return {
            "available": True,
            "flow_type": self.flow_type,
            "input_form": [],
            "opening_statement": "hello",
            "suggested_questions": [],
            "has_retrieval": False,
            "invocation_tested": True,
        }

    async def fake_invoke(self, arguments, *, user_id):
        return {"answer": f"Dify:{arguments.get('query', '')}", "conversation_id": "demo", "retriever_resources": [], "usage": {}}

    monkeypatch.setattr(DifyFlowClient, "test_connection", fake_test_connection)
    monkeypatch.setattr(DifyFlowClient, "invoke", fake_invoke)

    with TestClient(app, base_url="https://testserver") as client:
        _, headers = _exchange(client)
        created = client.post(
            "/api/v1/developer/external/dify",
            headers=headers,
            json={
                "slug": "developer-dify-playground",
                "display_name": "开发者 Dify 测试",
                "description": "验证 Dify 外部能力接入",
                "flow_type": "CHATFLOW",
                "base_url": "https://dify.example.test/v1",
                "api_key": "test-key",
                "tool_name": "developer_dify_flow",
                "test_query": "ping",
                **_semantics("调用已有 Dify 应用完成测试任务"),
            },
        )
        assert created.status_code == 201, created.text
        version = created.json()["resource_version"]
        assert version["status"] == "PUBLISHED"

        played = client.post(
            f"/api/v1/developer/playground/{version['resource_version_id']}/run",
            headers=headers,
            json={"arguments": {"query": "查询测试"}},
        )
        assert played.status_code == 200, played.text
        payload = played.json()
        assert payload["kind"] == "DIFY_FLOW"
        assert payload["output"]["answer"] == "Dify:查询测试"


def test_developer_local_knowledge_create_upload_and_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = Principal(
        provider="ruoyi-mock",
        external_user_id="user-demo",
        external_org_id="org-demo",
        tenant_id="tenant-demo",
        display_name="Demo Admin",
        dept_ids=("dept-demo",),
        role_codes=("agent_admin",),
    )

    async def prepare_model() -> str:
        secret = await get_secret_vault().create("test embedding", "test-embedding-key", admin)
        store = get_resource_store()
        definition = await store.create_model(ModelDefinitionCreate(
            slug=f"developer-embedding-{uuid4().hex[:8]}",
            display_name="Developer Embedding",
            config={"base_url": "https://model.example.test/v1", "model": "embedding-test", "model_mode": "EMBEDDING", "secret_ref": secret.secret_ref},
        ), admin)
        version = await store.create_model_version(definition.model_id, ModelVersionCreate(config=definition.config), admin)
        await store.record_connection_test(version.model_version_id, admin, True, "test")
        published = await store.publish_model_version(version.model_version_id, admin)
        await get_governance_store().create_grant(ResourceGrantCreate(
            subject_type=SubjectType.ROLE,
            subject_id="agent_developer",
            resource_type="MODEL",
            resource_id=str(definition.model_id),
            actions={GrantAction.VIEW, GrantAction.USE},
            effect=GrantEffect.ALLOW,
        ), admin)
        return str(published.model_version_id)

    model_version_id = asyncio.run(prepare_model())

    async def fake_upload(principal, knowledge_resource_version_id, upload):
        return SimpleNamespace(
            document_id=uuid4(),
            knowledge_resource_version_id=knowledge_resource_version_id,
            file_id=uuid4(),
            filename=upload.filename or "test.pdf",
            status=FileStatus.UPLOADED,
            created_at=datetime.now(timezone.utc),
        )

    async def fake_enqueue(tenant_id, user_id, knowledge_resource_version_id):
        return SimpleNamespace(job_id=uuid4())

    monkeypatch.setattr(get_knowledge_file_service(), "upload_and_register", fake_upload)
    monkeypatch.setattr(ingest_jobs, "enqueue", fake_enqueue)

    with TestClient(app, base_url="https://testserver") as client:
        _, headers = _exchange(client)
        models = client.get("/api/v1/developer/external/models")
        assert models.status_code == 200, models.text
        assert model_version_id in {item["model_version_id"] for item in models.json()}

        created = client.post(
            "/api/v1/developer/external/knowledge/local",
            headers=headers,
            json={
                "slug": f"developer-knowledge-{uuid4().hex[:8]}",
                "display_name": "开发者本地知识库",
                "description": "验证知识文件接入",
                "embedding_model_version_id": model_version_id,
                **_semantics("检索开发者上传的企业文档"),
            },
        )
        assert created.status_code == 201, created.text
        version = created.json()["resource_version"]
        assert version["status"] == "PUBLISHED"

        upload = client.post(
            f"/api/v1/developer/external/knowledge/{version['resource_version_id']}/documents",
            headers=headers,
            files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
        )
        assert upload.status_code == 202, upload.text
        assert upload.json()["filename"] == "test.pdf"

        build = client.post(
            f"/api/v1/developer/external/knowledge/{version['resource_version_id']}/build",
            headers=headers,
        )
        assert build.status_code == 202, build.text
        assert build.json()["status"] == "PENDING"
