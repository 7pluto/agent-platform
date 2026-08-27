from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from app.api.dependencies import ensure_resource_action, require_resource_developer, require_resource_developer_read
from app.api.routes.developer_resources import ResourceSemantics, _governance
from app.api.routes.mcp import (
    McpConnectionCreate,
    McpDiscoveredTool,
    McpToolRegistration,
    RegisterDiscoveredToolsRequest,
    create_mcp_connection,
    discover_mcp_tools,
    register_discovered_tools_batch,
)
from app.api.routes.resource_registry import (
    DifyApplicationCreate,
    HttpToolCreate,
    create_dify_application,
    create_http_tool,
)
from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.jobs import ingest_jobs
from app.knowledge.models import KnowledgeDocumentRecord
from app.knowledge.service import get_knowledge_file_service
from app.resources.models import ModelAvailability, ResourceVersionStatus as ModelVersionStatus
from app.resources.product_governance import apply_product_governance
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceDefinitionCreate, ResourceType, ResourceVersionCreate, ResourceVersionRecord
from app.resources.registry_store import ResourceRegistryStore
from app.resources.store_factory import get_resource_store

router = APIRouter(prefix="/developer/external", tags=["developer-external-capabilities"])
registry = get_resource_registry()


class DeveloperModelOption(BaseModel):
    model_id: UUID
    model_version_id: UUID
    display_name: str
    version_number: int
    provider: str
    model_name: str


class DeveloperMcpConnect(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="开发者接入的 MCP Server", max_length=4_000)
    endpoint: str
    timeout_seconds: float = Field(default=10, ge=0.1, le=60)
    api_key: str | None = Field(default=None, min_length=1, max_length=32_768)
    auth_header: str = Field(default="Authorization", min_length=1, max_length=128)
    auth_scheme: str = Field(default="Bearer", max_length=128)


class DeveloperMcpRegisterTool(BaseModel):
    tool_name: str = Field(min_length=1, max_length=128)
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4_000)
    one_line_summary: str = Field(min_length=1, max_length=256)
    when_to_use: str = Field(min_length=1, max_length=4_000)
    when_not_to_use: str | None = Field(default=None, max_length=4_000)
    input_summary: str = Field(min_length=1, max_length=4_000)
    output_summary: str = Field(min_length=1, max_length=4_000)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    read_only: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)


class DeveloperMcpRegisterRequest(BaseModel):
    connection_version_id: UUID
    tools: list[DeveloperMcpRegisterTool] = Field(min_length=1, max_length=50)


class DeveloperHttpToolCreate(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="开发者接入的受控 HTTP API", max_length=4_000)
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
    endpoint: str
    path: str = Field(default="/")
    method: Literal["GET", "POST", "PUT", "PATCH"] = "GET"
    input_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})
    query_template: dict | list | None = None
    body_template: dict | list | None = None
    header_template: dict[str, str] = Field(default_factory=dict)
    response_mapping: dict = Field(default_factory=dict)
    timeout_seconds: float = Field(default=15, ge=0.1, le=60)
    api_key: str | None = Field(default=None, min_length=1, max_length=32_768)
    auth_header: str = Field(default="Authorization", min_length=1, max_length=128)
    auth_scheme: str = Field(default="Bearer", max_length=128)
    test_arguments: dict = Field(default_factory=dict)


class DeveloperDifyCreate(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="开发者接入的 Dify Flow", max_length=4_000)
    flow_type: Literal["CHATFLOW", "WORKFLOW"] = "CHATFLOW"
    base_url: str
    api_key: str = Field(min_length=1, max_length=32_768)
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
    timeout_seconds: float = Field(default=90, ge=0.1, le=300)
    test_query: str = Field(default="请回复 OK", min_length=1, max_length=4_000)


class DeveloperLocalKnowledgeCreate(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="开发者上传的本地知识库", max_length=4_000)
    embedding_model_version_id: UUID


class DeveloperKnowledgeCreateResponse(BaseModel):
    resource_version: ResourceVersionRecord
    ready_for_upload: bool = True


class DeveloperKnowledgeBuildResponse(BaseModel):
    job_id: UUID
    status: str


@router.get("/models", response_model=list[DeveloperModelOption])
async def list_developer_models(principal: Principal = Depends(require_resource_developer_read)) -> list[DeveloperModelOption]:
    store = get_resource_store()
    result: list[DeveloperModelOption] = []
    for model in await store.list_models(principal):
        for version in await store.list_model_versions(model.model_id, principal):
            if version.status != ModelVersionStatus.PUBLISHED or version.availability != ModelAvailability.AVAILABLE:
                continue
            try:
                await ensure_resource_action(principal, "USE", "MODEL", str(version.model_version_id))
            except ApiError as exc:
                if exc.code == "RESOURCE_FORBIDDEN":
                    continue
                raise
            result.append(DeveloperModelOption(
                model_id=model.model_id,
                model_version_id=version.model_version_id,
                display_name=model.display_name,
                version_number=version.version_number,
                provider=version.provider,
                model_name=str(version.config.get("model") or model.display_name),
            ))
    return sorted(result, key=lambda item: (item.display_name.lower(), -item.version_number))


@router.post("/mcp/connections", response_model=ResourceVersionRecord, status_code=201)
async def connect_mcp(request: DeveloperMcpConnect, principal: Principal = Depends(require_resource_developer)) -> ResourceVersionRecord:
    published = await create_mcp_connection(McpConnectionCreate(
        slug=request.slug,
        display_name=request.display_name,
        endpoint=request.endpoint,
        timeout_seconds=request.timeout_seconds,
        api_key=request.api_key,
        auth_header=request.auth_header,
        auth_scheme=request.auth_scheme,
    ), principal)
    await apply_product_governance(
        product=_governance(request, principal),
        resource_type=ResourceType.MCP_CONNECTION.value,
        resource_id=published.resource_id,
        resource_version_id=published.resource_version_id,
        source_type="MCP",
        source_ref=urlsplit(request.endpoint).hostname or request.endpoint,
        principal=principal,
    )
    return published


@router.post("/mcp/connections/{connection_version_id}/discover", response_model=list[McpDiscoveredTool])
async def discover_developer_mcp(connection_version_id: UUID, principal: Principal = Depends(require_resource_developer)) -> list[McpDiscoveredTool]:
    connection = await registry.get_version(connection_version_id, principal, published=True)
    if connection.resource_type != ResourceType.MCP_CONNECTION:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version is not an MCP connection")
    await ensure_resource_action(principal, "USE", ResourceType.MCP_CONNECTION.value, str(connection_version_id))
    return await discover_mcp_tools(connection_version_id, principal)


@router.post("/mcp/tools", response_model=list[ResourceVersionRecord], status_code=201)
async def register_developer_mcp_tools(request: DeveloperMcpRegisterRequest, principal: Principal = Depends(require_resource_developer)) -> list[ResourceVersionRecord]:
    connection = await registry.get_version(request.connection_version_id, principal, published=True)
    if connection.resource_type != ResourceType.MCP_CONNECTION:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "connection version is not MCP")
    await ensure_resource_action(principal, "USE", ResourceType.MCP_CONNECTION.value, str(request.connection_version_id))
    tools = []
    for item in request.tools:
        tools.append(McpToolRegistration(
            tool_name=item.tool_name,
            slug=item.slug,
            display_name=item.display_name,
            description=item.description,
            owner_user_id=principal.external_user_id,
            owner_dept_id=principal.dept_ids[0] if principal.dept_ids else None,
            one_line_summary=item.one_line_summary,
            when_to_use=item.when_to_use,
            when_not_to_use=item.when_not_to_use,
            input_summary=item.input_summary,
            output_summary=item.output_summary,
            risk_level=item.risk_level,
            read_only=item.read_only,
            tags=["developer", "MCP", *item.tags],
            business_line="开发者接入",
            audience="Agent 开发者",
            usage_scenarios=item.when_to_use,
            publication_scope="PERSONAL",
            publication_subjects=[],
        ))
    return await register_discovered_tools_batch(RegisterDiscoveredToolsRequest(
        connection_version_id=request.connection_version_id,
        tools=tools,
    ), principal)


@router.post("/http-tools", status_code=201)
async def connect_http_tool(request: DeveloperHttpToolCreate, principal: Principal = Depends(require_resource_developer)) -> dict:
    governance = _governance(request, principal)
    result = await create_http_tool(HttpToolCreate(
        **governance.model_dump(),
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        tool_name=request.tool_name,
        endpoint=request.endpoint,
        path=request.path,
        method=request.method,
        input_schema=request.input_schema,
        query_template=request.query_template,
        body_template=request.body_template,
        header_template=request.header_template,
        response_mapping=request.response_mapping,
        timeout_seconds=request.timeout_seconds,
        api_key=request.api_key,
        auth_header=request.auth_header,
        auth_scheme=request.auth_scheme,
        test_arguments=request.test_arguments,
    ), principal)
    return result.model_dump(mode="json")


@router.post("/dify", status_code=201)
async def connect_dify(request: DeveloperDifyCreate, principal: Principal = Depends(require_resource_developer)) -> dict:
    result = await create_dify_application(DifyApplicationCreate(
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        flow_type=request.flow_type,
        base_url=request.base_url,
        api_key=request.api_key,
        tool_name=request.tool_name,
        timeout_seconds=request.timeout_seconds,
        test_query=request.test_query,
        owner_user_id=principal.external_user_id,
        owner_dept_id=principal.dept_ids[0] if principal.dept_ids else None,
        one_line_summary=request.one_line_summary,
        when_to_use=request.when_to_use,
        when_not_to_use=request.when_not_to_use,
        input_summary=request.input_summary,
        output_summary=request.output_summary,
        risk_level=request.risk_level,
        read_only=request.read_only,
        tags=["developer", "DIFY", *request.tags],
        business_line=request.business_line,
        data_involved=request.data_involved,
        audience=request.audience,
        usage_scenarios=request.usage_scenarios,
        developer_user_ids=[principal.external_user_id],
        publication_scope=request.publication_scope,
        publication_subjects=[item.model_dump() for item in request.publication_subjects],
    ), principal)
    # The legacy Dify product command still writes a version-scoped grant. Add
    # the stable Definition grant used by the developer workbench as well.
    published = result.resource_version
    await apply_product_governance(
        product=_governance(request, principal),
        resource_type=ResourceType.TOOL.value,
        resource_id=published.resource_id,
        resource_version_id=published.resource_version_id,
        source_type="DIFY",
        source_ref=urlsplit(request.base_url).hostname or request.base_url,
        principal=principal,
    )
    return result.model_dump(mode="json")


@router.post("/knowledge/local", response_model=DeveloperKnowledgeCreateResponse, status_code=201)
async def create_local_knowledge(request: DeveloperLocalKnowledgeCreate, principal: Principal = Depends(require_resource_developer)) -> DeveloperKnowledgeCreateResponse:
    await ensure_resource_action(principal, "USE", "MODEL", str(request.embedding_model_version_id))
    model = await get_resource_store().get_model_version(request.embedding_model_version_id, principal, require_available=True)
    if model.status != ModelVersionStatus.PUBLISHED:
        raise ApiError(409, "EMBEDDING_MODEL_NOT_PUBLISHED", "embedding model version must be published")
    config = {
        "provider": "LOCAL",
        "embedding_model_version_id": str(request.embedding_model_version_id),
    }
    ResourceRegistryStore._validate(ResourceType.KNOWLEDGE, config)
    definition = await registry.create_definition(ResourceDefinitionCreate(
        resource_type=ResourceType.KNOWLEDGE,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        draft_config=config,
    ), principal)
    version = await registry.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    published = await registry.publish_version(version.resource_version_id, principal)
    await apply_product_governance(
        product=_governance(request, principal),
        resource_type=ResourceType.KNOWLEDGE.value,
        resource_id=published.resource_id,
        resource_version_id=published.resource_version_id,
        source_type="LOCAL_FILE",
        source_ref="developer-upload",
        principal=principal,
    )
    return DeveloperKnowledgeCreateResponse(resource_version=published)


async def _owned_local_knowledge(resource_version_id: UUID, principal: Principal) -> ResourceVersionRecord:
    record = await registry.get_version(resource_version_id, principal, published=True)
    if record.resource_type != ResourceType.KNOWLEDGE:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version is not Knowledge")
    if str(record.config.get("provider", "LOCAL")).upper() != "LOCAL":
        raise ApiError(409, "KNOWLEDGE_OPERATION_EXTERNAL", "only local Knowledge accepts file upload")
    await ensure_resource_action(principal, "EDIT", ResourceType.KNOWLEDGE.value, str(resource_version_id))
    return record


@router.post("/knowledge/{resource_version_id}/documents", response_model=KnowledgeDocumentRecord, status_code=202)
async def upload_knowledge_document(
    resource_version_id: UUID,
    file: UploadFile = File(),
    principal: Principal = Depends(require_resource_developer),
) -> KnowledgeDocumentRecord:
    await _owned_local_knowledge(resource_version_id, principal)
    row = await get_knowledge_file_service().upload_and_register(principal, resource_version_id, file)
    return KnowledgeDocumentRecord(
        document_id=row.document_id,
        knowledge_resource_version_id=row.knowledge_resource_version_id,
        file_id=row.file_id,
        filename=row.filename,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/knowledge/{resource_version_id}/build", response_model=DeveloperKnowledgeBuildResponse, status_code=202)
async def build_knowledge_index(resource_version_id: UUID, principal: Principal = Depends(require_resource_developer)) -> DeveloperKnowledgeBuildResponse:
    await _owned_local_knowledge(resource_version_id, principal)
    job = await ingest_jobs.enqueue(principal.tenant_id, principal.external_user_id, resource_version_id)
    return DeveloperKnowledgeBuildResponse(job_id=job.job_id, status="PENDING")
