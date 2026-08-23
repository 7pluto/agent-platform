import asyncio
import json
from uuid import UUID, uuid4

from app.resources.registry_models import (
    ResourceDefinitionRecord,
    ResourceType,
    ResourceVersionRecord,
    ResourceVersionStatus,
)
from app.runtime.adapter import OpenAICompatibleRuntimeAdapter, RuntimeContext
from app.runtime.manifest import build_execution_manifest
from app.runtime.models import RunRecord


def _version(resource_id: UUID, resource_type: ResourceType, config: dict) -> ResourceVersionRecord:
    return ResourceVersionRecord(
        resource_id=resource_id,
        tenant_id="tenant-permission",
        resource_type=resource_type,
        version_number=1,
        status=ResourceVersionStatus.PUBLISHED,
        config=config,
        content_hash=uuid4().hex,
        created_by="admin",
    )


def test_runtime_registry_only_contains_use_authorized_business_capabilities(monkeypatch) -> None:
    async def run() -> None:
        definitions: list[ResourceDefinitionRecord] = []
        versions: dict[UUID, ResourceVersionRecord] = {}
        manifest_resources: list[dict] = []

        def add(resource_type: ResourceType, name: str, config: dict, allowed: bool = True) -> ResourceVersionRecord:
            resource_id = uuid4()
            version = _version(resource_id, resource_type, config)
            versions[version.resource_version_id] = version
            definitions.append(ResourceDefinitionRecord(
                resource_type=resource_type,
                slug=f"r-{resource_id.hex[:12]}",
                display_name=name,
                description=f"{name} business capability",
                resource_id=resource_id,
                tenant_id="tenant-permission",
                created_by="admin",
            ))
            manifest_resources.append({
                "type": resource_type.value,
                "resource_id": str(resource_id),
                "version_id": str(version.resource_version_id),
                "content_hash": version.content_hash,
                "binding_origin": "DIRECT",
                "use_allowed": allowed,
            })
            return version

        add(ResourceType.TOOL, "Dify A", {"kind": "DIFY_FLOW", "tool_name": "dify_allowed", "input_schema": {"type": "object", "properties": {}}})
        denied_dify = add(ResourceType.TOOL, "Dify B Finance", {"kind": "DIFY_FLOW", "tool_name": "dify_finance_denied", "external_id": "finance-app-secret-id"}, False)
        add(ResourceType.TOOL, "HTTP Ticket", {"kind": "HTTP", "tool_name": "ticket_allowed", "input_schema": {"type": "object", "properties": {}}})

        allowed_connection = add(ResourceType.MCP_CONNECTION, "CRM MCP", {"transport": "streamable_http", "endpoint": "https://crm.example.com/mcp", "egress_allowlist": ["crm.example.com"], "timeout_seconds": 10})
        denied_connection = add(ResourceType.MCP_CONNECTION, "Finance MCP", {"transport": "streamable_http", "endpoint": "https://finance.example.com/mcp", "egress_allowlist": ["finance.example.com"], "timeout_seconds": 10}, False)
        add(ResourceType.TOOL, "CRM Customer Query", {"kind": "MCP", "tool_name": "crm_customer_allowed", "connection_version_id": str(allowed_connection.resource_version_id), "input_schema": {"type": "object", "properties": {}}})
        denied_mcp_tool = add(ResourceType.TOOL, "Finance Account Query", {"kind": "MCP", "tool_name": "finance_account_denied", "connection_version_id": str(denied_connection.resource_version_id), "external_id": "finance-tool-id", "input_schema": {"type": "object", "properties": {}}})

        local_knowledge = add(ResourceType.KNOWLEDGE, "Employee Policy", {"provider": "LOCAL"})
        denied_ragflow = add(ResourceType.KNOWLEDGE, "RAGFlow Finance", {"provider": "RAGFLOW", "external_dataset_id": "finance-dataset-id"}, False)
        remote_knowledge = add(ResourceType.KNOWLEDGE, "Remote Support KB", {"provider": "REMOTE_HTTP"})

        class FakeRegistry:
            async def list_definitions(self, principal, resource_type=None):
                return [item for item in definitions if resource_type is None or item.resource_type == resource_type]

            async def get_version(self, version_id, principal, published=False):
                return versions[version_id]

        async def fake_knowledge_config(version, principal):
            return dict(version.config)

        monkeypatch.setattr("app.runtime.adapter.get_resource_registry", lambda: FakeRegistry())
        monkeypatch.setattr("app.runtime.adapter.resolve_knowledge_provider_config", fake_knowledge_config)

        record = RunRecord(tenant_id="tenant-permission", user_id="changsha-user", deployment_id=uuid4(), thread_id=uuid4(), message="测试权限矩阵")
        manifest = build_execution_manifest(record, resources=manifest_resources, harness_type="openai-compatible")
        specs, configs = await OpenAICompatibleRuntimeAdapter(None)._manifest_tools(RuntimeContext(run=record, manifest=manifest))  # type: ignore[arg-type]

        assert set(configs) == {
            "dify_allowed",
            "ticket_allowed",
            "crm_customer_allowed",
            f"knowledge_search_{local_knowledge.resource_version_id.hex[:8]}",
            f"knowledge_search_{remote_knowledge.resource_version_id.hex[:8]}",
        }
        model_registry = json.dumps(specs, ensure_ascii=False)
        assert "Dify B Finance" not in model_registry
        assert "dify_finance_denied" not in model_registry
        assert "finance-app-secret-id" not in model_registry
        assert "Finance Account Query" not in model_registry
        assert "finance_account_denied" not in model_registry
        assert "finance-tool-id" not in model_registry
        assert "RAGFlow Finance" not in model_registry
        assert "finance-dataset-id" not in model_registry
        assert str(denied_dify.resource_version_id) not in model_registry
        assert str(denied_mcp_tool.resource_version_id) not in model_registry
        assert str(denied_ragflow.resource_version_id) not in model_registry

    asyncio.run(run())
