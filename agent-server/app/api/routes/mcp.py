from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from urllib.parse import urlsplit

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.iam.models import Principal
from app.mcp.service import mcp_auth_headers, mcp_client
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceDefinitionCreate, ResourceExternalBindingRecord, ResourceType, ResourceVersionCreate, ResourceVersionRecord
from app.resources.registry_store import ResourceRegistryStore
from app.resources.bindings import get_external_binding_service
from app.secrets.vault import get_secret_vault

router = APIRouter(tags=["mcp"])
bindings = get_external_binding_service()


class McpDiscoveredTool(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict = {}


class RegisterDiscoveredToolRequest(BaseModel):
    connection_version_id: UUID
    tool_name: str
    description: str | None = None
    input_schema: dict = {}
    slug: str
    display_name: str


class McpConnectionCreate(BaseModel):
    slug: str
    display_name: str
    endpoint: str
    timeout_seconds: float = 10
    api_key: str | None = None
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"


@router.post("/mcp-connections", response_model=ResourceVersionRecord, status_code=201)
async def create_mcp_connection(request: McpConnectionCreate, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    host = urlsplit(request.endpoint).hostname
    if not host:
        from app.core.errors import ApiError
        raise ApiError(422, "INVALID_MCP_CONNECTION", "endpoint must contain a hostname")
    headers = {request.auth_header: f"{request.auth_scheme} {request.api_key}".strip()} if request.api_key else {}
    await mcp_client.discover(request.endpoint, request.timeout_seconds, headers, [host])
    config = {"transport": "streamable_http", "endpoint": request.endpoint, "timeout_seconds": request.timeout_seconds, "egress_allowlist": [host]}
    fingerprint = None
    if request.api_key:
        secret = await get_secret_vault().create(f"MCP: {request.display_name}", request.api_key, principal)
        config.update({"secret_ref": secret.secret_ref, "auth_header": request.auth_header, "auth_scheme": request.auth_scheme})
        fingerprint = secret.fingerprint
    registry = get_resource_registry()
    definition = await registry.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.MCP_CONNECTION, slug=request.slug, display_name=request.display_name, draft_config=config), principal)
    version = await registry.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    published = await registry.publish_version(version.resource_version_id, principal)
    from app.governance.store_factory import get_governance_store
    await get_governance_store().record_audit(principal, "mcp_connection.publish", "MCP_CONNECTION", str(published.resource_version_id), {"fingerprint": fingerprint})
    return published


@router.post("/mcp-connections/{resource_version_id}/discover", response_model=list[McpDiscoveredTool])
async def discover_mcp_tools(resource_version_id: UUID, principal: Principal = Depends(require_platform_admin)) -> list[McpDiscoveredTool]:
    connection = await get_resource_registry().get_version(resource_version_id, principal, published=True)
    if connection.resource_type != ResourceType.MCP_CONNECTION:
        from app.core.errors import ApiError
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version is not an MCP connection")
    ResourceRegistryStore._validate(ResourceType.MCP_CONNECTION, connection.config)
    headers = await mcp_auth_headers(connection.config, principal.tenant_id, principal.external_user_id)
    tools = await mcp_client.discover(connection.config["endpoint"], float(connection.config.get("timeout_seconds", 10)), headers, connection.config["egress_allowlist"])
    return [McpDiscoveredTool(name=item["name"], description=item.get("description"), input_schema=item.get("inputSchema", {})) for item in tools]


@router.post("/mcp-tools/register", response_model=ResourceVersionRecord, status_code=201)
async def register_discovered_tool(request: RegisterDiscoveredToolRequest, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    registry = get_resource_registry()
    connection = await registry.get_version(request.connection_version_id, principal, published=True)
    if connection.resource_type != ResourceType.MCP_CONNECTION:
        from app.core.errors import ApiError
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "connection version is not MCP")
    ResourceRegistryStore._validate(ResourceType.MCP_CONNECTION, connection.config)
    headers = await mcp_auth_headers(connection.config, principal.tenant_id, principal.external_user_id)
    discovered = await mcp_client.discover(connection.config["endpoint"], float(connection.config.get("timeout_seconds", 10)), headers, connection.config["egress_allowlist"])
    match = next((item for item in discovered if item["name"] == request.tool_name), None)
    if match is None:
        from app.core.errors import ApiError
        raise ApiError(409, "MCP_TOOL_NOT_DISCOVERED", "tool must be discovered before registration")
    definition = await registry.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.TOOL, slug=request.slug, display_name=request.display_name, description=request.description or match.get("description"), draft_config={"kind": "MCP", "connection_version_id": str(request.connection_version_id), "tool_name": request.tool_name, "input_schema": match.get("inputSchema", request.input_schema)}), principal)
    await bindings.register_discovered(
        provider="MCP", connection_resource_id=connection.resource_id, external_type="TOOL",
        external_id=request.tool_name, resource_id=definition.resource_id, principal=principal,
    )
    version = await registry.create_version(definition.resource_id, ResourceVersionCreate(), principal)
    return await registry.publish_version(version.resource_version_id, principal)


@router.get("/mcp-connections/{resource_version_id}/bindings", response_model=list[ResourceExternalBindingRecord])
async def list_mcp_bindings(resource_version_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> list[ResourceExternalBindingRecord]:
    connection = await get_resource_registry().get_version(resource_version_id, principal, published=True)
    if connection.resource_type != ResourceType.MCP_CONNECTION:
        from app.core.errors import ApiError
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version is not an MCP connection")
    return await bindings.list_for_connection(connection.resource_id, principal)
