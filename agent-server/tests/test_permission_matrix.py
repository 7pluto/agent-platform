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


def test_same_agent_exposes_only_each_ruoyi_users_authorized_capabilities(monkeypatch) -> None:
    async def run() -> None:
        definitions: list[ResourceDefinitionRecord] = []
        versions: dict[UUID, ResourceVersionRecord] = {}
        resources: list[tuple[ResourceVersionRecord, str]] = []

        def add(resource_type: ResourceType, name: str, config: dict) -> ResourceVersionRecord:
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
            resources.append((version, name))
            return version

        dify_general = add(ResourceType.TOOL, "Dify General", {
            "kind": "DIFY_FLOW", "tool_name": "dify_general",
            "input_schema": {"type": "object", "properties": {}},
        })
        dify_finance = add(ResourceType.TOOL, "Dify Finance", {
            "kind": "DIFY_FLOW", "tool_name": "dify_finance",
            "external_id": "finance-app-private-id",
            "input_schema": {"type": "object", "properties": {}},
        })
        http_ticket = add(ResourceType.TOOL, "HTTP Ticket", {
            "kind": "HTTP", "tool_name": "ticket_query",
            "input_schema": {"type": "object", "properties": {}},
        })

        crm_connection = add(ResourceType.MCP_CONNECTION, "CRM MCP", {
            "transport": "streamable_http", "endpoint": "https://crm.example.com/mcp",
            "egress_allowlist": ["crm.example.com"], "timeout_seconds": 10,
        })
        finance_connection = add(ResourceType.MCP_CONNECTION, "Finance MCP", {
            "transport": "streamable_http", "endpoint": "https://finance.example.com/mcp",
            "egress_allowlist": ["finance.example.com"], "timeout_seconds": 10,
        })
        crm_customer = add(ResourceType.TOOL, "CRM Customer Query", {
            "kind": "MCP", "tool_name": "crm_customer_query",
            "connection_version_id": str(crm_connection.resource_version_id),
            "input_schema": {"type": "object", "properties": {}},
        })
        crm_notes = add(ResourceType.TOOL, "CRM Sensitive Notes", {
            "kind": "MCP", "tool_name": "crm_sensitive_notes",
            "connection_version_id": str(crm_connection.resource_version_id),
            "external_id": "crm-sensitive-tool-private-id",
            "input_schema": {"type": "object", "properties": {}},
        })
        finance_account = add(ResourceType.TOOL, "Finance Account Query", {
            "kind": "MCP", "tool_name": "finance_account_query",
            "connection_version_id": str(finance_connection.resource_version_id),
            "external_id": "finance-tool-private-id",
            "input_schema": {"type": "object", "properties": {}},
        })

        local_knowledge = add(ResourceType.KNOWLEDGE, "Employee Policy", {"provider": "LOCAL"})
        finance_knowledge = add(ResourceType.KNOWLEDGE, "RAGFlow Finance", {
            "provider": "RAGFLOW", "external_dataset_id": "finance-dataset-private-id",
        })
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

        async def registry_for(user_id: str, allowed: set[UUID]) -> tuple[set[str], str]:
            record = RunRecord(
                tenant_id="tenant-permission", user_id=user_id,
                deployment_id=uuid4(), thread_id=uuid4(), message="测试权限矩阵",
            )
            manifest_resources = [{
                "type": version.resource_type.value,
                "resource_id": str(version.resource_id),
                "version_id": str(version.resource_version_id),
                "content_hash": version.content_hash,
                "binding_origin": "DIRECT",
                "use_allowed": version.resource_version_id in allowed,
            } for version, _ in resources]
            manifest = build_execution_manifest(record, resources=manifest_resources, harness_type="openai-compatible")
            specs, configs = await OpenAICompatibleRuntimeAdapter(None)._manifest_tools(  # type: ignore[arg-type]
                RuntimeContext(run=record, manifest=manifest)
            )
            return set(configs), json.dumps(specs, ensure_ascii=False)

        changsha_names, changsha_registry = await registry_for("ruoyi-user-changsha", {
            dify_general.resource_version_id,
            http_ticket.resource_version_id,
            crm_connection.resource_version_id,
            crm_customer.resource_version_id,
            # crm_notes is intentionally denied although it shares an allowed
            # MCP connection, proving single discovered tools are governable.
            # finance_account is allowed, but its connection is intentionally
            # denied, proving connection permission is an additional boundary.
            finance_account.resource_version_id,
            local_knowledge.resource_version_id,
            remote_knowledge.resource_version_id,
        })
        assert changsha_names == {
            "dify_general", "ticket_query", "crm_customer_query",
            f"knowledge_search_{local_knowledge.resource_version_id.hex[:8]}",
            f"knowledge_search_{remote_knowledge.resource_version_id.hex[:8]}",
        }
        for private_value in (
            "Dify Finance", "dify_finance", "finance-app-private-id",
            "CRM Sensitive Notes", "crm_sensitive_notes", "crm-sensitive-tool-private-id",
            "Finance Account Query", "finance_account_query", "finance-tool-private-id",
            "RAGFlow Finance", "finance-dataset-private-id",
            str(dify_finance.resource_version_id), str(crm_notes.resource_version_id),
            str(finance_account.resource_version_id), str(finance_knowledge.resource_version_id),
        ):
            assert private_value not in changsha_registry

        finance_names, finance_registry = await registry_for("ruoyi-user-finance", {
            dify_finance.resource_version_id,
            http_ticket.resource_version_id,
            finance_connection.resource_version_id,
            finance_account.resource_version_id,
            local_knowledge.resource_version_id,
            finance_knowledge.resource_version_id,
        })
        assert finance_names == {
            "dify_finance", "ticket_query", "finance_account_query",
            f"knowledge_search_{local_knowledge.resource_version_id.hex[:8]}",
            f"knowledge_search_{finance_knowledge.resource_version_id.hex[:8]}",
        }
        for private_value in (
            "Dify General", "dify_general", "CRM Customer Query", "crm_customer_query",
            "CRM Sensitive Notes", "crm_sensitive_notes", "Remote Support KB",
            str(dify_general.resource_version_id), str(crm_customer.resource_version_id),
            str(crm_notes.resource_version_id), str(remote_knowledge.resource_version_id),
        ):
            assert private_value not in finance_registry

    asyncio.run(run())
