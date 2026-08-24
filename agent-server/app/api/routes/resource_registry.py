from __future__ import annotations

from uuid import UUID, uuid4
from urllib.parse import urlsplit
from time import perf_counter

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import ensure_resource_action, require_fresh_principal, require_platform_admin, require_platform_admin_read
from app.governance.store_factory import get_governance_store
from app.core.errors import ApiError
from app.config import get_settings
from app.core.secrets import require_vault_secret_refs
from app.db.models import ResourceDescriptorRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.governance.models import GrantAction, GrantEffect, ResourceGrantCreate, ResourceGrantRecord, SubjectType
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_store import ResourceRegistryStore
from app.resources.registry_models import (
    ResourceDefinitionCreate, ResourceDefinitionRecord, ResourceType, ResourceValidationRunRecord,
    ResourceValidationStatus, ResourceValidationType, ResourceVersionCreate, ResourceVersionRecord,
)
from app.resources.validation import get_resource_validation_service
from app.resources.discovery import get_resource_discovery_service
from app.runtime.dify_flow import DifyFlowClient
from app.runtime.http_tool import http_tool_client
from app.mcp.service import mcp_auth_headers, mcp_client
from app.knowledge.providers.ragflow import RagflowKnowledgeProvider
from app.resources.providers.registry import provider_registry
from app.resources.product_governance import ProductGovernance, apply_product_governance, resolve_publication_subjects
from app.secrets.vault import get_secret_vault

router = APIRouter(tags=["resource-registry"])
store = get_resource_registry()
validation_runs = get_resource_validation_service()
discovery_snapshots = get_resource_discovery_service()


class DifyApplicationCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="调用已授权的 Dify Flow", max_length=4_000)
    flow_type: str = Field(default="CHATFLOW", pattern=r"^(CHATFLOW|WORKFLOW)$")
    base_url: str
    api_key: str = Field(min_length=1, max_length=32_768)
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
    timeout_seconds: float = Field(default=90, ge=0.1, le=300)
    test_query: str = Field(default="请回复 OK", min_length=1, max_length=4_000)
    owner_user_id: str = Field(min_length=1, max_length=128)
    owner_dept_id: str | None = Field(default=None, max_length=128)
    one_line_summary: str = Field(min_length=1, max_length=256)
    when_to_use: str = Field(min_length=1, max_length=4_000)
    when_not_to_use: str | None = Field(default=None, max_length=4_000)
    input_summary: str = Field(min_length=1, max_length=4_000)
    output_summary: str = Field(min_length=1, max_length=4_000)
    risk_level: str = Field(default="LOW", pattern=r"^(LOW|MEDIUM|HIGH)$")
    read_only: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)
    business_line: str | None = Field(default=None, max_length=128)
    data_involved: str | None = Field(default=None, max_length=4_000)
    audience: str | None = Field(default=None, max_length=4_000)
    usage_scenarios: str | None = Field(default=None, max_length=4_000)
    developer_user_ids: list[str] = Field(default_factory=list, max_length=50)
    opening_statement: str | None = Field(default=None, max_length=4_000)
    suggested_questions: list[str] = Field(default_factory=list, max_length=20)
    publication_scope: str = Field(default="PERSONAL", pattern=r"^(PERSONAL|OWNER_DEPT|SELECTED_SUBJECTS)$")
    publication_subjects: list[dict[str, str]] = Field(default_factory=list, max_length=100)


class DifyApplicationPublishResponse(BaseModel):
    resource_version: ResourceVersionRecord
    connection_test: dict
    grants_created: int


class HttpToolCreate(ProductGovernance):
    """Create a constrained API capability, not a user-programmable proxy."""

    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="调用受控业务 HTTP 接口", max_length=4_000)
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
    endpoint: str
    path: str = Field(default="/")
    method: str = Field(default="GET", pattern=r"^(GET|POST|PUT|PATCH)$")
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


class HttpToolPublishResponse(BaseModel):
    resource_version: ResourceVersionRecord
    test_result: dict


class SkillTestCase(BaseModel):
    input: str = Field(min_length=1, max_length=2_000)
    expected_behavior: str = Field(min_length=1, max_length=2_000)


class SkillProductCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="可复用业务技能", max_length=4_000)
    skill_md: str = Field(min_length=20, max_length=50_000)
    tool_version_ids: list[UUID] = Field(default_factory=list, max_length=50)
    knowledge_version_ids: list[UUID] = Field(default_factory=list, max_length=50)
    test_cases: list[SkillTestCase] = Field(min_length=1, max_length=20)


class SkillProductPublishResponse(BaseModel):
    resource_id: UUID
    resource_version_id: UUID
    version_number: int
    status: str
    test_result: dict


class ResourceTestRequest(BaseModel):
    input: dict = Field(default_factory=dict)


async def _validate_dify_version(
    record: ResourceVersionRecord,
    principal: Principal,
    validation_type: ResourceValidationType,
) -> ResourceValidationRunRecord:
    """Run and retain a safe, tenant-scoped Dify validation outcome."""
    started = perf_counter()
    result = await provider_registry.resolve(record.resource_type, record.config, principal).validate(record.config)
    if not result.ok:
        return await validation_runs.record(
            record.resource_version_id, validation_type, ResourceValidationStatus.FAILED,
            result.model_dump(mode="json"), principal,
            round((perf_counter() - started) * 1000),
        )
    return await validation_runs.record(
        record.resource_version_id, validation_type, ResourceValidationStatus.SUCCEEDED,
        {"provider": result.provider, "result": result.details}, principal, round((perf_counter() - started) * 1000),
    )


def _dify_tool_input_schema(flow_type: str, input_form: list) -> dict:
    type_map = {
        "text-input": "string", "paragraph": "string", "select": "string",
        "number": "number", "checkbox": "boolean",
    }
    properties: dict[str, dict] = {}
    required: list[str] = []
    for wrapper in input_form:
        if not isinstance(wrapper, dict) or not wrapper:
            continue
        kind, definition = next(iter(wrapper.items()))
        if not isinstance(definition, dict):
            continue
        variable = str(definition.get("variable", "")).strip()
        if not variable:
            continue
        property_schema: dict = {
            "type": type_map.get(str(kind), "string"),
            "description": str(definition.get("label") or variable),
        }
        options = definition.get("options")
        if isinstance(options, list) and all(isinstance(value, str) for value in options):
            property_schema["enum"] = options
        properties[variable] = property_schema
        if definition.get("required") is True:
            required.append(variable)
    inputs_schema: dict = {"type": "object", "properties": properties}
    if required:
        inputs_schema["required"] = required
    schema: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户当前的业务问题"},
            "inputs": {**inputs_schema, "description": "Dify 应用公开的结构化输入变量"},
        },
    }
    if flow_type == "CHATFLOW":
        schema["required"] = ["query"]
    elif required:
        schema["required"] = ["inputs"]
    return schema


async def _save_dify_descriptor(request: DifyApplicationCreate, resource_id: UUID, principal: Principal) -> None:
    if get_settings().storage_mode != "postgres":
        return
    async with get_session_factory()() as session:
        async with session.begin():
            await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
            row = await session.scalar(select(ResourceDescriptorRow).where(
                ResourceDescriptorRow.tenant_id == principal.tenant_id,
                ResourceDescriptorRow.resource_type == ResourceType.TOOL.value,
                ResourceDescriptorRow.resource_id == resource_id,
            ))
            values = {
                "owner_user_id": request.owner_user_id,
                "owner_dept_id": request.owner_dept_id,
                "source_type": "DIFY",
                "source_ref": urlsplit(request.base_url).hostname,
                "usage_guidance": request.when_to_use,
                "one_line_summary": request.one_line_summary,
                "when_to_use": request.when_to_use,
                "when_not_to_use": request.when_not_to_use,
                "input_summary": request.input_summary,
                "output_summary": request.output_summary,
                "risk_level": request.risk_level,
                "read_only": request.read_only,
                "tags": request.tags,
                "lifecycle_status": "ACTIVE",
            }
            if row is None:
                session.add(ResourceDescriptorRow(
                    descriptor_id=uuid4(), tenant_id=principal.tenant_id,
                    resource_type=ResourceType.TOOL.value, resource_id=resource_id, **values,
                ))
            else:
                for key, value in values.items():
                    setattr(row, key, value)


def _publication_subjects(request: DifyApplicationCreate) -> list[tuple[SubjectType, str, set[GrantAction]]]:
    subjects: list[tuple[SubjectType, str, set[GrantAction]]] = [
        (SubjectType.USER, request.owner_user_id, {
            GrantAction.VIEW, GrantAction.USE, GrantAction.EDIT, GrantAction.PUBLISH, GrantAction.MANAGE,
        })
    ]
    if request.publication_scope == "OWNER_DEPT":
        if not request.owner_dept_id:
            raise ApiError(422, "DIFY_PUBLICATION_SCOPE_INVALID", "owner department is required for department scope")
        subjects.append((SubjectType.DEPT, request.owner_dept_id, {GrantAction.VIEW, GrantAction.USE}))
    elif request.publication_scope == "SELECTED_SUBJECTS":
        if not request.publication_subjects:
            raise ApiError(422, "DIFY_PUBLICATION_SCOPE_INVALID", "at least one RuoYi subject is required")
        for item in request.publication_subjects:
            try:
                subject_type = SubjectType(str(item.get("subject_type", "")))
            except ValueError as exc:
                raise ApiError(422, "DIFY_PUBLICATION_SCOPE_INVALID", "subject type must be USER, ROLE, or DEPT") from exc
            subject_id = str(item.get("subject_id", "")).strip()
            if not subject_id:
                raise ApiError(422, "DIFY_PUBLICATION_SCOPE_INVALID", "subject id is required")
            subjects.append((subject_type, subject_id, {GrantAction.VIEW, GrantAction.USE}))
    unique: dict[tuple[SubjectType, str], set[GrantAction]] = {}
    for subject_type, subject_id, actions in subjects:
        unique.setdefault((subject_type, subject_id), set()).update(actions)
    return [(kind, subject_id, actions) for (kind, subject_id), actions in unique.items()]


@router.post("/dify-applications", response_model=DifyApplicationPublishResponse, status_code=201)
async def create_dify_application(request: DifyApplicationCreate, principal: Principal = Depends(require_platform_admin)) -> DifyApplicationPublishResponse:
    host = urlsplit(request.base_url).hostname
    if not host:
        raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "base_url must contain a hostname")
    publication_subjects = _publication_subjects(request)
    secret = await get_secret_vault().create(f"Dify Flow: {request.display_name}", request.api_key, principal)
    base_config = {
        "kind": "DIFY_FLOW",
        "tool_name": request.tool_name,
        "description": request.description,
        "flow_type": request.flow_type,
        "base_url": request.base_url.rstrip("/"),
        "secret_ref": secret.secret_ref,
        "timeout_seconds": request.timeout_seconds,
        "egress_allowlist": [host],
        "input_schema": _dify_tool_input_schema(request.flow_type, []),
        "test_query": request.test_query,
        "application_profile": {
            "business_line": request.business_line,
            "data_involved": request.data_involved,
            "audience": request.audience,
            "usage_scenarios": request.usage_scenarios,
            "developer_user_ids": request.developer_user_ids,
            "opening_statement": request.opening_statement,
            "suggested_questions": request.suggested_questions,
            "publication_scope": request.publication_scope,
        },
    }
    definition = await store.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.TOOL, slug=request.slug, display_name=request.display_name, description=request.description, draft_config=base_config), principal)
    try:
        connection_test = await DifyFlowClient(request.base_url.rstrip("/"), request.api_key, request.flow_type, request.timeout_seconds).test_connection(request.test_query)
    except ApiError as exc:
        failed_version = await store.create_version(definition.resource_id, ResourceVersionCreate(config=base_config), principal)
        await validation_runs.record(
            failed_version.resource_version_id, ResourceValidationType.VALIDATE, ResourceValidationStatus.FAILED,
            {"provider": "DIFY", "code": exc.code, "message": exc.message}, principal,
        )
        await get_governance_store().record_audit(
            principal, "dify_application.validation_failed", "TOOL", str(failed_version.resource_version_id),
            {"resource_id": str(definition.resource_id), "code": exc.code, "fingerprint": secret.fingerprint},
        )
        raise
    config = {
        **base_config,
        "input_schema": _dify_tool_input_schema(request.flow_type, connection_test.get("input_form", [])),
        "dify_input_form": connection_test.get("input_form", []),
        "application_profile": {
            **base_config["application_profile"],
            "opening_statement": request.opening_statement or connection_test.get("opening_statement"),
            "suggested_questions": request.suggested_questions or connection_test.get("suggested_questions", []),
        },
    }
    version = await store.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    await validation_runs.record(version.resource_version_id, ResourceValidationType.VALIDATE, ResourceValidationStatus.SUCCEEDED, connection_test, principal)
    published = await store.publish_version(version.resource_version_id, principal)
    await discovery_snapshots.capture_published(published, principal)
    await _save_dify_descriptor(request, published.resource_id, principal)
    governance = get_governance_store()
    grants: list[ResourceGrantRecord] = []
    for subject_type, subject_id, actions in publication_subjects:
        grants.append(await governance.create_grant(ResourceGrantCreate(
            subject_type=subject_type, subject_id=subject_id,
            resource_type=ResourceType.TOOL.value, resource_id=str(published.resource_version_id),
            actions=actions, effect=GrantEffect.ALLOW,
        ), principal))
    await governance.record_audit(principal, "dify_application.publish", "TOOL", str(published.resource_version_id), {
        "resource_id": str(published.resource_id),
        "fingerprint": secret.fingerprint, "flow_type": request.flow_type,
        "publication_scope": request.publication_scope,
        "grant_count": len(grants), "input_count": len(connection_test.get("input_form", [])),
    })
    return DifyApplicationPublishResponse(resource_version=published, connection_test=connection_test, grants_created=len(grants))


class DifyFlowToolCreate(BaseModel):
    """Compatibility contract for the Stage 4 technical API."""
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="调用已授权的 Dify Flow", max_length=4_000)
    flow_type: str = Field(default="CHATFLOW", pattern=r"^(CHATFLOW|WORKFLOW)$")
    base_url: str
    api_key: str = Field(min_length=1, max_length=32_768)
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
    timeout_seconds: float = Field(default=90, ge=0.1, le=300)
    test_query: str = Field(default="请回复 OK", min_length=1, max_length=4_000)


@router.post("/dify-flow-tools", response_model=ResourceVersionRecord, status_code=201)
async def create_dify_flow_tool(request: DifyFlowToolCreate, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    """Keep existing automation working while the console uses the product API."""
    host = urlsplit(request.base_url).hostname
    if not host:
        raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "base_url must contain a hostname")
    connection_test = await DifyFlowClient(
        request.base_url.rstrip("/"), request.api_key, request.flow_type, request.timeout_seconds,
    ).test_connection(request.test_query)
    secret = await get_secret_vault().create(f"Dify Flow: {request.display_name}", request.api_key, principal)
    config = {
        "kind": "DIFY_FLOW", "tool_name": request.tool_name, "description": request.description,
        "flow_type": request.flow_type, "base_url": request.base_url.rstrip("/"), "secret_ref": secret.secret_ref,
        "timeout_seconds": request.timeout_seconds, "egress_allowlist": [host],
        "input_schema": _dify_tool_input_schema(request.flow_type, connection_test.get("input_form", [])),
        "dify_input_form": connection_test.get("input_form", []), "test_query": request.test_query,
    }
    definition = await store.create_definition(ResourceDefinitionCreate(
        resource_type=ResourceType.TOOL, slug=request.slug, display_name=request.display_name,
        description=request.description, draft_config=config,
    ), principal)
    version = await store.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    await validation_runs.record(version.resource_version_id, ResourceValidationType.VALIDATE, ResourceValidationStatus.SUCCEEDED, connection_test, principal)
    published = await store.publish_version(version.resource_version_id, principal)
    await discovery_snapshots.capture_published(published, principal)
    await get_governance_store().record_audit(principal, "dify_flow_tool.publish", "TOOL", str(published.resource_version_id), {
        "resource_id": str(published.resource_id), "fingerprint": secret.fingerprint,
    })
    return published


@router.post("/skills", response_model=SkillProductPublishResponse, status_code=201)
async def create_skill_product(request: SkillProductCreate, principal: Principal = Depends(require_platform_admin)) -> SkillProductPublishResponse:
    """Publish a Skill only after its immutable dependencies and business tests compile."""
    if not request.skill_md.lstrip().startswith("#"):
        raise ApiError(422, "INVALID_SKILL_CONFIG", "SKILL.md must start with a Markdown heading")
    dependency_ids = [*request.tool_version_ids, *request.knowledge_version_ids]
    if len(dependency_ids) != len(set(dependency_ids)):
        raise ApiError(422, "SKILL_DEPENDENCY_DUPLICATED", "Skill dependencies must be unique")
    for version_id in request.tool_version_ids:
        dependency = await store.get_version(version_id, principal, published=True)
        if dependency.resource_type != ResourceType.TOOL:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "tool_version_ids may reference only published Tools")
    for version_id in request.knowledge_version_ids:
        dependency = await store.get_version(version_id, principal, published=True)
        if dependency.resource_type != ResourceType.KNOWLEDGE:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "knowledge_version_ids may reference only published Knowledge")
    config = {
        "skill_md": request.skill_md,
        "tool_version_ids": [str(value) for value in request.tool_version_ids],
        "knowledge_version_ids": [str(value) for value in request.knowledge_version_ids],
        "test_cases": [item.model_dump() for item in request.test_cases],
    }
    ResourceRegistryStore._validate(ResourceType.SKILL, config)
    definition = await store.create_definition(ResourceDefinitionCreate(
        resource_type=ResourceType.SKILL, slug=request.slug, display_name=request.display_name,
        description=request.description, draft_config=config,
    ), principal)
    version = await store.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    test_result = {
        "test_case_count": len(request.test_cases),
        "tool_dependency_count": len(request.tool_version_ids),
        "knowledge_dependency_count": len(request.knowledge_version_ids),
        "status": "COMPILED",
    }
    await validation_runs.record(
        version.resource_version_id, ResourceValidationType.TEST, ResourceValidationStatus.SUCCEEDED,
        test_result, principal,
    )
    published = await store.publish_version(version.resource_version_id, principal)
    await get_governance_store().record_audit(
        principal, "skill.publish", ResourceType.SKILL.value, str(published.resource_version_id),
        {"resource_id": str(published.resource_id), **test_result},
    )
    return SkillProductPublishResponse(
        resource_id=published.resource_id, resource_version_id=published.resource_version_id,
        version_number=published.version_number, status=published.status.value, test_result=test_result,
    )


@router.post("/http-tools", response_model=HttpToolPublishResponse, status_code=201)
async def create_http_tool(request: HttpToolCreate, principal: Principal = Depends(require_platform_admin)) -> HttpToolPublishResponse:
    """Register and validate one fixed HTTP capability before publication."""
    resolve_publication_subjects(request)
    host = urlsplit(request.endpoint).hostname
    if not host:
        raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "endpoint must contain a hostname")
    config: dict = {
        "kind": "HTTP",
        "tool_name": request.tool_name,
        "description": request.description,
        "endpoint": request.endpoint.rstrip("/"),
        "path": request.path,
        "method": request.method,
        "input_schema": request.input_schema,
        "timeout_seconds": request.timeout_seconds,
        "egress_allowlist": [host],
        "header_template": request.header_template,
        "response_mapping": request.response_mapping,
    }
    if request.query_template is not None:
        config["query_template"] = request.query_template
    if request.body_template is not None:
        config["body_template"] = request.body_template
    if request.api_key:
        secret = await get_secret_vault().create(f"HTTP Tool: {request.display_name}", request.api_key, principal)
        config.update({"secret_ref": secret.secret_ref, "auth_header": request.auth_header, "auth_scheme": request.auth_scheme})

    # Validate config before persisting any executable version.  The test below
    # invokes only this fixed endpoint/path and its declared templates.
    ResourceRegistryStore._validate(ResourceType.TOOL, config)
    definition = await store.create_definition(ResourceDefinitionCreate(
        resource_type=ResourceType.TOOL,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        draft_config=config,
    ), principal)
    version = await store.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    started = perf_counter()
    try:
        test_result = await http_tool_client.invoke(config, request.test_arguments, principal.tenant_id, principal.external_user_id)
    except ApiError as exc:
        await validation_runs.record(
            version.resource_version_id,
            ResourceValidationType.TEST,
            ResourceValidationStatus.FAILED,
            {"provider": "HTTP", "code": exc.code, "message": exc.message},
            principal,
            round((perf_counter() - started) * 1000),
        )
        raise
    await validation_runs.record(
        version.resource_version_id,
        ResourceValidationType.TEST,
        ResourceValidationStatus.SUCCEEDED,
        {"provider": "HTTP", "status_code": test_result["status_code"]},
        principal,
        round((perf_counter() - started) * 1000),
    )
    published = await store.publish_version(version.resource_version_id, principal)
    await discovery_snapshots.capture_published(published, principal)
    grants = await apply_product_governance(
        product=request,
        resource_type=ResourceType.TOOL.value,
        resource_id=published.resource_id,
        resource_version_id=published.resource_version_id,
        source_type="HTTP",
        source_ref=f"{request.method} {request.path}",
        principal=principal,
    )
    await get_governance_store().record_audit(
        principal,
        "http_tool.publish",
        "TOOL",
        str(published.resource_version_id),
        {"endpoint_host": host, "method": request.method, "path": request.path, "publication_scope": request.publication_scope, "grant_count": len(grants)},
    )
    return HttpToolPublishResponse(resource_version=published, test_result={"status_code": test_result["status_code"]})


@router.post("/resources", response_model=ResourceDefinitionRecord, status_code=201)
async def create_resource(request: ResourceDefinitionCreate, principal: Principal = Depends(require_platform_admin)) -> ResourceDefinitionRecord:
    require_vault_secret_refs(request.draft_config, "resource.draft_config")
    record = await store.create_definition(request, principal)
    await get_governance_store().record_audit(principal, "resource.create", record.resource_type.value, str(record.resource_id), {"slug": record.slug})
    return record


@router.get("/resources", response_model=list[ResourceDefinitionRecord])
async def list_resources(resource_type: ResourceType | None = Query(default=None), principal: Principal = Depends(require_platform_admin_read)) -> list[ResourceDefinitionRecord]:
    return await store.list_definitions(principal, resource_type)


@router.post("/resources/{resource_id}/versions", response_model=ResourceVersionRecord, status_code=201)
async def create_resource_version(resource_id: UUID, request: ResourceVersionCreate, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    effective_config = request.config
    if not effective_config:
        definition = next((item for item in await store.list_definitions(principal) if item.resource_id == resource_id), None)
        if definition is None:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        effective_config = definition.draft_config
    require_vault_secret_refs(effective_config, "resource.version.config")
    record = await store.create_version(resource_id, request, principal)
    await get_governance_store().record_audit(principal, "resource_version.create", record.resource_type.value, str(record.resource_version_id), {"resource_id": str(resource_id)})
    return record


@router.get("/resources/{resource_id}/versions", response_model=list[ResourceVersionRecord])
async def list_resource_versions(resource_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> list[ResourceVersionRecord]:
    return await store.list_versions(resource_id, principal)


@router.post("/resource-versions/{resource_version_id}/publish", response_model=ResourceVersionRecord)
async def publish_resource_version(resource_version_id: UUID, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    draft = await store.get_version(resource_version_id, principal)
    if draft.resource_type == ResourceType.TOOL and draft.config.get("kind") == "DIFY_FLOW":
        if not await validation_runs.has_successful_validation(resource_version_id, principal):
            raise ApiError(409, "RESOURCE_VALIDATION_REQUIRED", "Dify Tool must pass validation before publish")
    if draft.resource_type == ResourceType.TOOL and draft.config.get("kind") == "HTTP":
        if not await validation_runs.has_successful_validation(resource_version_id, principal, ResourceValidationType.TEST):
            raise ApiError(409, "RESOURCE_TEST_REQUIRED", "HTTP Tool must pass a test before publish")
    if draft.resource_type in {ResourceType.MCP_CONNECTION, ResourceType.KNOWLEDGE_CONNECTION}:
        if not await validation_runs.has_successful_validation(resource_version_id, principal):
            raise ApiError(409, "RESOURCE_VALIDATION_REQUIRED", "external connection must pass validation before publish")
    record = await store.publish_version(resource_version_id, principal)
    await discovery_snapshots.capture_published(record, principal)
    await get_governance_store().record_audit(principal, "resource_version.publish", record.resource_type.value, str(record.resource_version_id), {"content_hash": record.content_hash})
    return record


@router.post("/resource-versions/{resource_version_id}/test")
async def test_resource_version(
    resource_version_id: UUID,
    request: ResourceTestRequest | None = None,
    principal: Principal = Depends(require_platform_admin),
) -> dict:
    record = await store.get_version(resource_version_id, principal)
    if record.resource_type == ResourceType.TOOL and record.config.get("kind") == "DIFY_FLOW":
        outcome = await _validate_dify_version(record, principal, ResourceValidationType.TEST)
    elif record.resource_type == ResourceType.TOOL and record.config.get("kind") == "HTTP":
        started = perf_counter()
        result = await provider_registry.resolve(record.resource_type, record.config, principal).test(record.config, (request.input if request else {}))
        outcome = await validation_runs.record(
            record.resource_version_id,
            ResourceValidationType.TEST,
            ResourceValidationStatus.SUCCEEDED if result.ok else ResourceValidationStatus.FAILED,
            result.model_dump(mode="json"),
            principal,
            round((perf_counter() - started) * 1000),
        )
    elif record.resource_type in {ResourceType.MCP_CONNECTION, ResourceType.KNOWLEDGE_CONNECTION}:
        outcome = await _validate_external_connection(record, principal, ResourceValidationType.TEST)
    else:
        raise ApiError(422, "RESOURCE_TEST_UNSUPPORTED", "test is supported for Dify, HTTP, MCP and RAGFlow resource versions")
    await get_governance_store().record_audit(principal, "resource_version.test", record.resource_type.value, str(record.resource_version_id), {"validation_run_id": str(outcome.validation_run_id), "status": outcome.status.value})
    if outcome.status == ResourceValidationStatus.FAILED:
        raise ApiError(502, str(outcome.result.get("code") or outcome.result.get("error_code") or "UPSTREAM_ERROR"), str(outcome.result.get("message", "resource test failed")))
    return outcome.result.get("result", outcome.result)


@router.post("/resource-versions/{resource_version_id}/validate", response_model=ResourceValidationRunRecord)
async def validate_resource_version(resource_version_id: UUID, principal: Principal = Depends(require_platform_admin)) -> ResourceValidationRunRecord:
    record = await store.get_version(resource_version_id, principal)
    if record.resource_type == ResourceType.TOOL and record.config.get("kind") == "DIFY_FLOW":
        outcome = await _validate_dify_version(record, principal, ResourceValidationType.VALIDATE)
    elif record.resource_type in {ResourceType.MCP_CONNECTION, ResourceType.KNOWLEDGE_CONNECTION}:
        outcome = await _validate_external_connection(record, principal, ResourceValidationType.VALIDATE)
    else:
        raise ApiError(422, "RESOURCE_VALIDATION_UNSUPPORTED", "validation is supported for Dify, MCP and RAGFlow resource versions")
    await get_governance_store().record_audit(principal, "resource_version.validate", record.resource_type.value, str(record.resource_version_id), {"validation_run_id": str(outcome.validation_run_id), "status": outcome.status.value})
    return outcome


async def _validate_external_connection(
    record: ResourceVersionRecord,
    principal: Principal,
    validation_type: ResourceValidationType,
) -> ResourceValidationRunRecord:
    started = perf_counter()
    try:
        if record.resource_type == ResourceType.MCP_CONNECTION:
            headers = await mcp_auth_headers(record.config, principal.tenant_id, principal.external_user_id)
            tools = await mcp_client.discover(
                str(record.config["endpoint"]), float(record.config.get("timeout_seconds", 10)),
                headers, record.config.get("egress_allowlist", []),
            )
            result = {"provider": "MCP", "tool_count": len(tools)}
        else:
            datasets = await RagflowKnowledgeProvider(principal).discover_datasets(record.config)
            result = {"provider": "RAGFLOW", "dataset_count": len(datasets)}
        return await validation_runs.record(
            record.resource_version_id, validation_type, ResourceValidationStatus.SUCCEEDED,
            result, principal, round((perf_counter() - started) * 1000),
        )
    except Exception as exc:
        code = exc.code if isinstance(exc, ApiError) else "CONNECTION_VALIDATION_FAILED"
        message = exc.message if isinstance(exc, ApiError) else type(exc).__name__
        return await validation_runs.record(
            record.resource_version_id, validation_type, ResourceValidationStatus.FAILED,
            {"provider": "MCP" if record.resource_type == ResourceType.MCP_CONNECTION else "RAGFLOW", "code": code, "message": message},
            principal, round((perf_counter() - started) * 1000),
        )


@router.get("/resource-versions/{resource_version_id}/validation-runs", response_model=list[ResourceValidationRunRecord])
async def list_resource_validation_runs(resource_version_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> list[ResourceValidationRunRecord]:
    await store.get_version(resource_version_id, principal)
    return await validation_runs.list(resource_version_id, principal)


@router.get("/resource-versions/published", response_model=list[ResourceVersionRecord])
async def list_published_resource_versions(resource_type: ResourceType | None = Query(default=None), principal: Principal = Depends(require_fresh_principal)) -> list[ResourceVersionRecord]:
    # The next filter is action-aware in the assembly resolver; this endpoint is
    # intentionally tenant scoped and never trusts a client tenant identifier.
    return await store.list_published_versions(principal, resource_type)
