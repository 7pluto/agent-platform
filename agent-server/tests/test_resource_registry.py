import asyncio

from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.registry_models import ResourceDefinitionCreate, ResourceType, ResourceVersionCreate, ResourceVersionStatus
from app.resources.registry_store import ResourceRegistryStore
from app.api.routes.resource_registry import _dify_tool_input_schema


def _principal(tenant: str = "tenant-demo") -> Principal:
    return Principal(provider="mock", external_user_id="user-demo", external_org_id="org-demo", tenant_id=tenant, display_name="Demo")


def test_skill_dependencies_and_native_tool_are_versioned() -> None:
    async def run() -> None:
        store = ResourceRegistryStore()
        principal = _principal()
        tool = await store.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.TOOL, slug="current-time", display_name="Current time", draft_config={"kind": "NATIVE", "native_name": "current_time"}), principal)
        tool_version = await store.create_version(tool.resource_id, ResourceVersionCreate(), principal)
        await store.publish_version(tool_version.resource_version_id, principal)
        skill = await store.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.SKILL, slug="time-skill", display_name="Time skill", draft_config={"skill_md": "Use the time tool.", "tool_version_ids": [str(tool_version.resource_version_id)], "knowledge_version_ids": []}), principal)
        version = await store.create_version(skill.resource_id, ResourceVersionCreate(), principal)
        assert version.status == ResourceVersionStatus.DRAFT
        assert (await store.publish_version(version.resource_version_id, principal)).status == ResourceVersionStatus.PUBLISHED
        try:
            await store.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.TOOL, slug="unsafe-shell", display_name="Unsafe", draft_config={"kind": "SHELL", "command": "whoami"}), principal)
        except ApiError as exc:
            assert exc.code == "INVALID_TOOL_CONFIG"
        else:
            raise AssertionError("arbitrary shell tool was accepted")

    asyncio.run(run())


def test_registry_is_tenant_scoped_and_rejects_plaintext_secrets() -> None:
    async def run() -> None:
        store = ResourceRegistryStore()
        owner, other = _principal("tenant-a"), _principal("tenant-b")
        try:
            await store.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.MCP_CONNECTION, slug="bad-mcp", display_name="Bad", draft_config={"transport": "streamable_http", "endpoint": "http://mcp", "api_key": "plain"}), owner)
        except ApiError as exc:
            assert exc.code == "SECRET_VALUE_FORBIDDEN"
        else:
            raise AssertionError("plaintext MCP credential was accepted")
        prompt = await store.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.PROMPT, slug="tenant-prompt", display_name="Prompt", draft_config={"template": "hello"}), owner)
        version = await store.create_version(prompt.resource_id, ResourceVersionCreate(), owner)
        await store.publish_version(version.resource_version_id, owner)
        try:
            await store.get_version(version.resource_version_id, other)
        except ApiError as exc:
            assert exc.code == "NOT_FOUND"
        else:
            raise AssertionError("cross tenant resource read was accepted")

    asyncio.run(run())


def test_mcp_egress_and_memory_policy_are_enforced() -> None:
    valid_mcp = {
        "transport": "streamable_http",
        "endpoint": "http://demo-crm-mcp:8090/mcp",
        "timeout_seconds": 5,
        "egress_allowlist": ["demo-crm-mcp"],
    }
    ResourceRegistryStore._validate(ResourceType.MCP_CONNECTION, valid_mcp)
    for patch, code in (
        ({"egress_allowlist": ["other-service"]}, "MCP_EGRESS_FORBIDDEN"),
        ({"egress_allowlist": []}, "INVALID_MCP_EGRESS_POLICY"),
        ({"timeout_seconds": 0}, "INVALID_MCP_CONNECTION"),
    ):
        try:
            ResourceRegistryStore._validate(ResourceType.MCP_CONNECTION, {**valid_mcp, **patch})
        except ApiError as exc:
            assert exc.code == code
        else:
            raise AssertionError("invalid MCP connection was accepted")

    ResourceRegistryStore._validate(
        ResourceType.MEMORY_POLICY,
        {
            "read_enabled": True,
            "write_enabled": True,
            "write_mode": "EXPLICIT",
            "ttl_days": 30,
            "max_items": 50,
            "allowed_categories": ["preference"],
        },
    )
    for config in ({"ttl_days": 0}, {"max_items": 0}, {"allowed_categories": [""]}):
        try:
            ResourceRegistryStore._validate(ResourceType.MEMORY_POLICY, config)
        except ApiError as exc:
            assert exc.code == "INVALID_MEMORY_POLICY"
        else:
            raise AssertionError("invalid Memory Policy was accepted")


def test_dify_flow_is_a_versioned_tool_with_secret_ref_only() -> None:
    config = {
        "kind": "DIFY_FLOW",
        "tool_name": "enterprise_knowledge_flow",
        "description": "Ask the approved Dify flow",
        "flow_type": "CHATFLOW",
        "base_url": "http://dify-gateway/v1",
        "secret_ref": "vault://12345678-1234-1234-1234-123456789abc",
        "timeout_seconds": 90,
        "egress_allowlist": ["dify-gateway"],
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    ResourceRegistryStore._validate(ResourceType.TOOL, config)
    for patch, code in (
        ({"base_url": "http://other/v1"}, "DIFY_FLOW_EGRESS_FORBIDDEN"),
        ({"secret_ref": "bad-secret"}, "INVALID_SECRET_REF"),
        ({"flow_type": "AGENT"}, "INVALID_DIFY_FLOW_CONFIG"),
    ):
        try:
            ResourceRegistryStore._validate(ResourceType.TOOL, {**config, **patch})
        except ApiError as exc:
            assert exc.code == code
        else:
            raise AssertionError("invalid Dify Flow Tool was accepted")

    try:
        ResourceRegistryStore._validate(ResourceType.TOOL, {**config, "api_key": "plaintext"})
    except ApiError as exc:
        assert exc.code == "SECRET_VALUE_FORBIDDEN"
    else:
        raise AssertionError("plaintext Dify key was accepted")


def test_dify_input_form_becomes_a_real_tool_schema() -> None:
    schema = _dify_tool_input_schema("WORKFLOW", [
        {"text-input": {"label": "Project code", "variable": "project_code", "required": True}},
        {"select": {"label": "Language", "variable": "language", "required": False, "options": ["zh", "en"]}},
    ])
    assert schema["required"] == ["inputs"]
    inputs = schema["properties"]["inputs"]
    assert inputs["required"] == ["project_code"]
    assert inputs["properties"]["language"]["enum"] == ["zh", "en"]
