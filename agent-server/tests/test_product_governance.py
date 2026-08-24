import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.api.routes.mcp import McpToolRegistration
from app.api.routes.ragflow import RagflowDatasetRegister
from app.core.errors import ApiError
from app.governance.models import GrantAction, SubjectType
from app.resources.product_governance import ProductGovernance, PublicationSubject, resolve_publication_subjects


def _product(**overrides) -> ProductGovernance:
    values = {
        "owner_user_id": "admin",
        "one_line_summary": "查询企业客户资料",
        "when_to_use": "需要读取客户基础信息时",
        "input_summary": "客户编号",
        "output_summary": "客户基础信息",
        "risk_level": "LOW",
        "read_only": True,
        "publication_scope": "PERSONAL",
    }
    values.update(overrides)
    return ProductGovernance(**values)


def test_personal_publication_keeps_owner_management_and_use_permissions() -> None:
    subjects = resolve_publication_subjects(_product())
    assert len(subjects) == 1
    subject_type, subject_id, actions = subjects[0]
    assert subject_type == SubjectType.USER
    assert subject_id == "admin"
    assert {GrantAction.VIEW, GrantAction.USE, GrantAction.EDIT, GrantAction.PUBLISH, GrantAction.MANAGE} == actions


def test_selected_ruoyi_subjects_receive_only_view_and_use() -> None:
    subjects = resolve_publication_subjects(_product(
        publication_scope="SELECTED_SUBJECTS",
        publication_subjects=[PublicationSubject(subject_type=SubjectType.DEPT, subject_id="dept-hr")],
    ))
    dept = next(item for item in subjects if item[0] == SubjectType.DEPT)
    assert dept[1] == "dept-hr"
    assert dept[2] == {GrantAction.VIEW, GrantAction.USE}


def test_department_scope_is_rejected_before_resource_publication_without_owner_department() -> None:
    with pytest.raises(ApiError) as captured:
        resolve_publication_subjects(_product(publication_scope="OWNER_DEPT"))
    assert captured.value.code == "PUBLICATION_SCOPE_INVALID"


def test_mcp_and_ragflow_product_commands_require_business_semantics() -> None:
    with pytest.raises(ValidationError):
        McpToolRegistration(tool_name="query_customer", slug="query-customer", display_name="查询客户")
    with pytest.raises(ValidationError):
        RagflowDatasetRegister(
            connection_version_id="00000000-0000-0000-0000-000000000001",
            dataset_id="hr-policy",
            slug="hr-policy",
            display_name="员工制度库",
        )


def _session(client: TestClient) -> dict[str, str]:
    exchange = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
    assert exchange.status_code == 200
    return {"X-CSRF-Token": exchange.json()["csrf_token"]}


def _product_payload() -> dict:
    return {
        "owner_user_id": "admin",
        "owner_dept_id": "dept-hr-product-test",
        "one_line_summary": "查询企业客户资料",
        "when_to_use": "需要读取客户基础信息时",
        "when_not_to_use": "不用于修改客户资料",
        "input_summary": "客户编号",
        "output_summary": "客户基础信息",
        "risk_level": "LOW",
        "read_only": True,
        "tags": ["客户", "只读"],
        "publication_scope": "OWNER_DEPT",
        "publication_subjects": [],
    }


def test_mcp_batch_product_command_creates_ruoyi_use_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    async def discover(*_args, **_kwargs):
        return [{"name": "query_product_customer", "description": "查询客户", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string"}}}}]

    monkeypatch.setattr("app.api.routes.mcp.mcp_client.discover", discover)
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        connection = client.post("/api/v1/mcp-connections", headers=headers, json={
            "slug": "product-test-mcp-connection",
            "display_name": "产品化测试 CRM MCP",
            "endpoint": "https://product-test-mcp.example/mcp",
        })
        assert connection.status_code == 201
        published = client.post("/api/v1/mcp-tools/register-batch", headers=headers, json={
            "connection_version_id": connection.json()["resource_version_id"],
            "tools": [{
                "tool_name": "query_product_customer",
                "slug": "query-product-customer",
                "display_name": "查询测试客户",
                "description": "按客户编号读取基础资料",
                **_product_payload(),
            }],
        })
        assert published.status_code == 201
        version_id = published.json()[0]["resource_version_id"]
        grants = client.get(f"/api/v1/resource-grants?resource_id={version_id}", headers=headers)
        assert grants.status_code == 200
        dept = next(item for item in grants.json() if item["subject_type"] == "DEPT")
        assert dept["subject_id"] == "dept-hr-product-test"
        assert set(dept["actions"]) == {"VIEW", "USE"}


def test_ragflow_product_command_creates_ruoyi_use_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSecret:
        secret_ref = "vault://00000000-0000-0000-0000-000000000099"
        fingerprint = "f" * 64

    class FakeVault:
        async def create(self, *_args, **_kwargs):
            return FakeSecret()

    async def datasets(*_args, **_kwargs):
        return [{"id": "dataset-product-hr", "name": "产品测试人事制度", "description": "员工制度"}]

    monkeypatch.setattr("app.api.routes.ragflow.get_secret_vault", lambda: FakeVault())
    monkeypatch.setattr("app.api.routes.ragflow.RagflowKnowledgeProvider.discover_datasets", datasets)
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        connection = client.post("/api/v1/ragflow-connections", headers=headers, json={
            "slug": "product-test-ragflow-connection",
            "display_name": "产品化测试 RAGFlow",
            "endpoint": "https://product-test-ragflow.example",
            "api_key": "not-persisted-test-key",
        })
        assert connection.status_code == 201
        published = client.post("/api/v1/ragflow-knowledge/register", headers=headers, json={
            "connection_version_id": connection.json()["resource_version_id"],
            "dataset_id": "dataset-product-hr",
            "slug": "product-test-hr-knowledge",
            "display_name": "产品测试人事制度库",
            "description": "检索员工制度",
            **_product_payload(),
        })
        assert published.status_code == 201
        version_id = published.json()["resource_version_id"]
        grants = client.get(f"/api/v1/resource-grants?resource_id={version_id}", headers=headers)
        assert grants.status_code == 200
        assert any(item["subject_type"] == "DEPT" and item["subject_id"] == "dept-hr-product-test" for item in grants.json())


def test_http_tool_product_command_tests_then_creates_ruoyi_use_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    async def invoke(*_args, **_kwargs):
        return {"status_code": 200, "body": {"ticket_id": "WO-1001"}}

    monkeypatch.setattr("app.api.routes.resource_registry.http_tool_client.invoke", invoke)
    with TestClient(app, base_url="https://testserver") as client:
        headers = _session(client)
        published = client.post("/api/v1/http-tools", headers=headers, json={
            "slug": "product-test-http-ticket",
            "display_name": "产品测试工单查询",
            "description": "通过受控 HTTP API 查询工单",
            "tool_name": "query_product_ticket",
            "endpoint": "https://product-test-ticket.example",
            "path": "/tickets/{{ticket_id}}",
            "method": "GET",
            "input_schema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
            "header_template": {"X-Business-Source": "agent-platform"},
            "response_mapping": {"fields": {"ticket_id": "ticket_id"}},
            "test_arguments": {"ticket_id": "WO-1001"},
            **_product_payload(),
        })
        assert published.status_code == 201
        version_id = published.json()["resource_version"]["resource_version_id"]
        grants = client.get(f"/api/v1/resource-grants?resource_id={version_id}", headers=headers)
        assert grants.status_code == 200
        assert any(item["subject_type"] == "DEPT" and set(item["actions"]) == {"VIEW", "USE"} for item in grants.json())
