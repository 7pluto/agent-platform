from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import (
    ensure_resource_action,
    require_resource_developer,
    require_resource_developer_read,
)
from app.api.routes.workbench import CatalogItem, _catalog
from app.config import get_settings
from app.core.errors import ApiError
from app.db.models import ResourceDescriptorRow, ResourceVersionRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.resources.product_governance import ProductGovernance, PublicationSubject, apply_product_governance
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import (
    ResourceDefinitionCreate,
    ResourceDefinitionRecord,
    ResourceType,
    ResourceVersionCreate,
    ResourceVersionRecord,
    ResourceVersionStatus,
)
from app.resources.registry_store import ResourceRegistryStore


router = APIRouter(prefix="/developer/resources", tags=["developer-resources"])
store = get_resource_registry()
_memory_semantics: dict[tuple[str, UUID], "ResourceSemantics"] = {}


class DeveloperContext(BaseModel):
    developer: bool = True
    external_user_id: str
    display_name: str
    role_codes: list[str] = Field(default_factory=list)
    dept_ids: list[str] = Field(default_factory=list)


class ResourceSemantics(BaseModel):
    one_line_summary: str = Field(min_length=1, max_length=256)
    when_to_use: str = Field(min_length=1, max_length=4_000)
    when_not_to_use: str | None = Field(default=None, max_length=4_000)
    input_summary: str = Field(min_length=1, max_length=4_000)
    output_summary: str = Field(min_length=1, max_length=4_000)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    read_only: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)
    business_line: str | None = Field(default=None, max_length=128)
    data_involved: str | None = Field(default=None, max_length=4_000)
    audience: str | None = Field(default=None, max_length=4_000)
    usage_scenarios: str | None = Field(default=None, max_length=4_000)
    publication_scope: Literal["PERSONAL", "OWNER_DEPT", "SELECTED_SUBJECTS"] = "PERSONAL"
    publication_subjects: list[PublicationSubject] = Field(default_factory=list, max_length=100)


class DeveloperPromptCreate(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="可复用 Prompt", max_length=4_000)
    template: str = Field(min_length=1, max_length=50_000)


class DeveloperNativeToolCreate(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="平台内置工具", max_length=4_000)
    native_name: Literal["current_time", "calculator", "echo"]
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
    input_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})


class DeveloperSkillCreate(ResourceSemantics):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="可复用业务技能", max_length=4_000)
    skill_md: str = Field(min_length=20, max_length=50_000)
    tool_version_ids: list[UUID] = Field(default_factory=list, max_length=50)
    knowledge_version_ids: list[UUID] = Field(default_factory=list, max_length=50)


class DeveloperVersionEdit(ResourceSemantics):
    config: dict


class DeveloperResourceDetail(BaseModel):
    resource_id: UUID
    resource_type: ResourceType
    slug: str
    display_name: str
    description: str | None = None
    editable: bool
    semantics: ResourceSemantics
    versions: list[ResourceVersionRecord]
    active_draft_version_id: UUID | None = None
    base_version_id: UUID | None = None
    editable_config: dict = Field(default_factory=dict)


def _governance(product: ResourceSemantics, principal: Principal) -> ProductGovernance:
    return ProductGovernance(
        owner_user_id=principal.external_user_id,
        owner_dept_id=principal.dept_ids[0] if principal.dept_ids else None,
        one_line_summary=product.one_line_summary,
        when_to_use=product.when_to_use,
        when_not_to_use=product.when_not_to_use,
        input_summary=product.input_summary,
        output_summary=product.output_summary,
        risk_level=product.risk_level,
        read_only=product.read_only,
        tags=product.tags,
        business_line=product.business_line,
        data_involved=product.data_involved,
        audience=product.audience,
        usage_scenarios=product.usage_scenarios,
        publication_scope=product.publication_scope,
        publication_subjects=product.publication_subjects,
    )


def _latest_per_resource(items: list[CatalogItem]) -> list[CatalogItem]:
    latest: dict[UUID, CatalogItem] = {}
    for item in items:
        current = latest.get(item.resource_id)
        if current is None or item.version_number > current.version_number:
            latest[item.resource_id] = item
    return sorted(latest.values(), key=lambda item: (item.resource_type, item.display_name.lower()))


def _semantics_from_catalog(item: CatalogItem) -> ResourceSemantics:
    return ResourceSemantics(
        one_line_summary=item.one_line_summary or item.description or item.summary or item.display_name,
        when_to_use=item.when_to_use or item.usage_guidance or "按资源业务说明使用",
        when_not_to_use=item.when_not_to_use,
        input_summary=item.input_summary or "按资源输入契约提供参数",
        output_summary=item.output_summary or "返回资源定义的业务结果",
        risk_level=item.risk_level if item.risk_level in {"LOW", "MEDIUM", "HIGH"} else "LOW",
        read_only=item.read_only,
        tags=item.tags,
    )


def _overlay_memory_semantics(items: list[CatalogItem], principal: Principal) -> list[CatalogItem]:
    if get_settings().storage_mode != "memory":
        return items
    result: list[CatalogItem] = []
    for item in items:
        semantics = _memory_semantics.get((principal.tenant_id, item.resource_id))
        if semantics is None:
            result.append(item)
            continue
        result.append(item.model_copy(update={
            "one_line_summary": semantics.one_line_summary,
            "when_to_use": semantics.when_to_use,
            "when_not_to_use": semantics.when_not_to_use,
            "input_summary": semantics.input_summary,
            "output_summary": semantics.output_summary,
            "risk_level": semantics.risk_level,
            "read_only": semantics.read_only,
            "tags": semantics.tags,
            "usage_guidance": semantics.when_to_use,
        }))
    return result


async def _definition(resource_id: UUID, principal: Principal) -> ResourceDefinitionRecord:
    definition = next((item for item in await store.list_definitions(principal) if item.resource_id == resource_id), None)
    if definition is None:
        raise ApiError(404, "NOT_FOUND", "resource was not found")
    return definition


async def _owned_definition(resource_id: UUID, principal: Principal) -> tuple[ResourceDefinitionRecord, CatalogItem]:
    definition = await _definition(resource_id, principal)
    catalog = _overlay_memory_semantics(await _catalog(principal), principal)
    latest = max((item for item in catalog if item.resource_id == resource_id), key=lambda item: item.version_number, default=None)
    owner = latest.owner_user_id if latest else definition.created_by
    if owner != principal.external_user_id:
        raise ApiError(403, "RESOURCE_OWNER_REQUIRED", "only the resource owner can create or edit its versions")
    if latest is None:
        raise ApiError(409, "RESOURCE_NOT_PUBLISHED", "developer resource has no published base version")
    return definition, latest


async def _validate_editable_config(resource_type: ResourceType, config: dict, principal: Principal) -> None:
    if resource_type not in {ResourceType.PROMPT, ResourceType.SKILL, ResourceType.TOOL}:
        raise ApiError(409, "RESOURCE_VERSION_EDIT_UNSUPPORTED", "this resource type is read-only in the developer workbench")
    if resource_type == ResourceType.TOOL and config.get("kind") != "NATIVE":
        raise ApiError(409, "RESOURCE_VERSION_EDIT_UNSUPPORTED", "only platform Native Tools are editable in the developer workbench")

    ResourceRegistryStore._validate(resource_type, config)
    if resource_type != ResourceType.SKILL:
        return

    raw_tools = config.get("tool_version_ids", [])
    raw_knowledge = config.get("knowledge_version_ids", [])
    dependency_ids = [*raw_tools, *raw_knowledge]
    if len(dependency_ids) != len(set(dependency_ids)):
        raise ApiError(422, "SKILL_DEPENDENCY_DUPLICATED", "Skill dependencies must be unique")

    for raw in raw_tools:
        try:
            version_id = UUID(str(raw))
        except ValueError as exc:
            raise ApiError(422, "INVALID_SKILL_CONFIG", "tool_version_ids must contain UUIDs") from exc
        dependency = await store.get_version(version_id, principal, published=True)
        if dependency.resource_type != ResourceType.TOOL:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "tool_version_ids may reference only published Tools")
        await ensure_resource_action(principal, "USE", ResourceType.TOOL.value, str(version_id))

    for raw in raw_knowledge:
        try:
            version_id = UUID(str(raw))
        except ValueError as exc:
            raise ApiError(422, "INVALID_SKILL_CONFIG", "knowledge_version_ids must contain UUIDs") from exc
        dependency = await store.get_version(version_id, principal, published=True)
        if dependency.resource_type != ResourceType.KNOWLEDGE:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "knowledge_version_ids may reference only published Knowledge")
        await ensure_resource_action(principal, "USE", ResourceType.KNOWLEDGE.value, str(version_id))


async def _save_semantics(
    *,
    resource_id: UUID,
    resource_type: ResourceType,
    semantics: ResourceSemantics,
    principal: Principal,
) -> None:
    if get_settings().storage_mode == "memory":
        _memory_semantics[(principal.tenant_id, resource_id)] = semantics.model_copy(deep=True)
        return

    values = {
        "owner_user_id": principal.external_user_id,
        "owner_dept_id": principal.dept_ids[0] if principal.dept_ids else None,
        "usage_guidance": semantics.when_to_use,
        "one_line_summary": semantics.one_line_summary,
        "when_to_use": semantics.when_to_use,
        "when_not_to_use": semantics.when_not_to_use,
        "input_summary": semantics.input_summary,
        "output_summary": semantics.output_summary,
        "risk_level": semantics.risk_level,
        "read_only": semantics.read_only,
        "business_line": semantics.business_line,
        "data_involved": semantics.data_involved,
        "audience": semantics.audience,
        "usage_scenarios": semantics.usage_scenarios,
        "publication_scope": semantics.publication_scope,
        "tags": semantics.tags,
        "lifecycle_status": "ACTIVE",
    }
    async with get_session_factory()() as session:
        async with session.begin():
            await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
            row = await session.scalar(select(ResourceDescriptorRow).where(
                ResourceDescriptorRow.tenant_id == principal.tenant_id,
                ResourceDescriptorRow.resource_type == resource_type.value,
                ResourceDescriptorRow.resource_id == resource_id,
            ))
            if row is None:
                session.add(ResourceDescriptorRow(
                    descriptor_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    source_type="PLATFORM_NATIVE",
                    source_ref="developer-editor",
                    developer_user_ids=[],
                    **values,
                ))
            else:
                for key, value in values.items():
                    setattr(row, key, value)


async def _replace_draft_config(
    *,
    resource_id: UUID,
    version_id: UUID,
    resource_type: ResourceType,
    config: dict,
    principal: Principal,
) -> ResourceVersionRecord:
    await _validate_editable_config(resource_type, config, principal)

    if get_settings().storage_mode == "memory":
        lock = getattr(store, "_lock", None)
        versions = getattr(store, "_versions", None)
        if lock is None or versions is None:
            raise ApiError(500, "DEVELOPER_STORAGE_ERROR", "development registry does not support draft editing")
        async with lock:
            record = versions.get(version_id)
            if record is None or record.tenant_id != principal.tenant_id or record.resource_id != resource_id:
                raise ApiError(404, "NOT_FOUND", "resource draft was not found")
            if record.status != ResourceVersionStatus.DRAFT:
                raise ApiError(409, "RESOURCE_VERSION_NOT_DRAFT", "only draft resource versions can be edited")
            updated = record.model_copy(update={
                "config": config,
                "content_hash": ResourceRegistryStore._hash(config),
            })
            versions[version_id] = updated
            return updated.model_copy(deep=True)

    async with get_session_factory()() as session:
        async with session.begin():
            await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
            row = await session.scalar(select(ResourceVersionRow).where(
                ResourceVersionRow.tenant_id == principal.tenant_id,
                ResourceVersionRow.resource_version_id == version_id,
                ResourceVersionRow.resource_id == resource_id,
            ).with_for_update())
            if row is None:
                raise ApiError(404, "NOT_FOUND", "resource draft was not found")
            if row.status != ResourceVersionStatus.DRAFT.value:
                raise ApiError(409, "RESOURCE_VERSION_NOT_DRAFT", "only draft resource versions can be edited")
            row.config = config
            row.content_hash = ResourceRegistryStore._hash(config)
    return await store.get_version(version_id, principal)


async def _publish(
    *,
    resource_type: ResourceType,
    slug: str,
    display_name: str,
    description: str,
    config: dict,
    semantics: ResourceSemantics,
    principal: Principal,
    source_type: str = "PLATFORM_NATIVE",
    source_ref: str | None = None,
) -> ResourceVersionRecord:
    definition = await store.create_definition(
        ResourceDefinitionCreate(
            resource_type=resource_type,
            slug=slug,
            display_name=display_name,
            description=description,
            draft_config=config,
        ),
        principal,
    )
    version = await store.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    published = await store.publish_version(version.resource_version_id, principal)
    grants = await apply_product_governance(
        product=_governance(semantics, principal),
        resource_type=resource_type.value,
        resource_id=definition.resource_id,
        resource_version_id=published.resource_version_id,
        source_type=source_type,
        source_ref=source_ref,
        principal=principal,
    )
    await _save_semantics(resource_id=definition.resource_id, resource_type=resource_type, semantics=semantics, principal=principal)
    await get_governance_store().record_audit(
        principal,
        "developer_resource.publish",
        resource_type.value,
        str(published.resource_version_id),
        {
            "resource_id": str(definition.resource_id),
            "owner_user_id": principal.external_user_id,
            "grant_count": len(grants),
        },
    )
    return published


@router.get("/context", response_model=DeveloperContext)
async def developer_context(
    principal: Principal = Depends(require_resource_developer_read),
) -> DeveloperContext:
    return DeveloperContext(
        external_user_id=principal.external_user_id,
        display_name=principal.display_name,
        role_codes=list(principal.role_codes),
        dept_ids=list(principal.dept_ids),
    )


@router.get("/mine", response_model=list[CatalogItem])
async def my_resources(
    principal: Principal = Depends(require_resource_developer_read),
) -> list[CatalogItem]:
    catalog = _overlay_memory_semantics(await _catalog(principal), principal)
    return _latest_per_resource([
        item for item in catalog if item.owner_user_id == principal.external_user_id
    ])


@router.get("/available", response_model=list[CatalogItem])
async def available_resources(
    principal: Principal = Depends(require_resource_developer_read),
) -> list[CatalogItem]:
    allowed: list[CatalogItem] = []
    for item in _overlay_memory_semantics(await _catalog(principal), principal):
        try:
            await ensure_resource_action(principal, "USE", item.resource_type, str(item.version_id))
        except ApiError as exc:
            if exc.code == "RESOURCE_FORBIDDEN":
                continue
            raise
        allowed.append(item)
    return _latest_per_resource(allowed)


@router.get("/{resource_id}", response_model=DeveloperResourceDetail)
async def developer_resource_detail(
    resource_id: UUID,
    principal: Principal = Depends(require_resource_developer_read),
) -> DeveloperResourceDetail:
    definition, latest_catalog = await _owned_definition(resource_id, principal)
    versions = sorted(await store.list_versions(resource_id, principal), key=lambda item: item.version_number, reverse=True)
    draft = next((item for item in versions if item.status == ResourceVersionStatus.DRAFT), None)
    published = next((item for item in versions if item.status == ResourceVersionStatus.PUBLISHED), None)
    semantics = _memory_semantics.get((principal.tenant_id, resource_id)) or _semantics_from_catalog(latest_catalog)
    editable = definition.resource_type in {ResourceType.PROMPT, ResourceType.SKILL} or (
        definition.resource_type == ResourceType.TOOL and (draft.config if draft else published.config if published else {}).get("kind") == "NATIVE"
    )
    base = published.resource_version_id if published else None
    editable_config = (draft.config if draft else published.config if published else definition.draft_config).copy()
    return DeveloperResourceDetail(
        resource_id=definition.resource_id,
        resource_type=definition.resource_type,
        slug=definition.slug,
        display_name=definition.display_name,
        description=definition.description,
        editable=editable,
        semantics=semantics,
        versions=versions,
        active_draft_version_id=draft.resource_version_id if draft else None,
        base_version_id=base,
        editable_config=editable_config,
    )


@router.post("/{resource_id}/versions", response_model=ResourceVersionRecord, status_code=201)
async def create_resource_draft(
    resource_id: UUID,
    request: DeveloperVersionEdit,
    principal: Principal = Depends(require_resource_developer),
) -> ResourceVersionRecord:
    definition, _ = await _owned_definition(resource_id, principal)
    versions = await store.list_versions(resource_id, principal)
    existing = next((item for item in versions if item.status == ResourceVersionStatus.DRAFT), None)
    if existing is not None:
        raise ApiError(409, "RESOURCE_DRAFT_EXISTS", f"V{existing.version_number} draft already exists; edit or publish it first")
    await _validate_editable_config(definition.resource_type, request.config, principal)
    version = await store.create_version(resource_id, ResourceVersionCreate(config=request.config), principal)
    await _save_semantics(resource_id=resource_id, resource_type=definition.resource_type, semantics=request, principal=principal)
    await get_governance_store().record_audit(principal, "developer_resource.draft.create", definition.resource_type.value, str(version.resource_version_id), {
        "resource_id": str(resource_id), "version_number": version.version_number,
    })
    return version


@router.put("/{resource_id}/versions/{version_id}", response_model=ResourceVersionRecord)
async def update_resource_draft(
    resource_id: UUID,
    version_id: UUID,
    request: DeveloperVersionEdit,
    principal: Principal = Depends(require_resource_developer),
) -> ResourceVersionRecord:
    definition, _ = await _owned_definition(resource_id, principal)
    version = await _replace_draft_config(
        resource_id=resource_id,
        version_id=version_id,
        resource_type=definition.resource_type,
        config=request.config,
        principal=principal,
    )
    await _save_semantics(resource_id=resource_id, resource_type=definition.resource_type, semantics=request, principal=principal)
    await get_governance_store().record_audit(principal, "developer_resource.draft.update", definition.resource_type.value, str(version_id), {
        "resource_id": str(resource_id), "version_number": version.version_number,
    })
    return version


@router.post("/{resource_id}/versions/{version_id}/publish", response_model=ResourceVersionRecord)
async def publish_resource_draft(
    resource_id: UUID,
    version_id: UUID,
    principal: Principal = Depends(require_resource_developer),
) -> ResourceVersionRecord:
    definition, _ = await _owned_definition(resource_id, principal)
    version = await store.get_version(version_id, principal)
    if version.resource_id != resource_id:
        raise ApiError(404, "NOT_FOUND", "resource draft was not found")
    if version.status != ResourceVersionStatus.DRAFT:
        raise ApiError(409, "RESOURCE_VERSION_NOT_DRAFT", "only draft resource versions can be published")
    await _validate_editable_config(definition.resource_type, version.config, principal)
    published = await store.publish_version(version_id, principal)
    await get_governance_store().record_audit(principal, "developer_resource.version.publish", definition.resource_type.value, str(version_id), {
        "resource_id": str(resource_id), "version_number": published.version_number,
    })
    return published


@router.post("/prompts", response_model=ResourceVersionRecord, status_code=201)
async def create_prompt(
    request: DeveloperPromptCreate,
    principal: Principal = Depends(require_resource_developer),
) -> ResourceVersionRecord:
    return await _publish(
        resource_type=ResourceType.PROMPT,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        config={"template": request.template},
        semantics=request,
        principal=principal,
        source_ref="prompt-editor",
    )


@router.post("/native-tools", response_model=ResourceVersionRecord, status_code=201)
async def create_native_tool(
    request: DeveloperNativeToolCreate,
    principal: Principal = Depends(require_resource_developer),
) -> ResourceVersionRecord:
    return await _publish(
        resource_type=ResourceType.TOOL,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        config={
            "kind": "NATIVE",
            "native_name": request.native_name,
            "tool_name": request.tool_name,
            "description": request.description,
            "input_schema": request.input_schema,
        },
        semantics=request,
        principal=principal,
        source_ref=request.native_name,
    )


@router.post("/skills", response_model=ResourceVersionRecord, status_code=201)
async def create_skill(
    request: DeveloperSkillCreate,
    principal: Principal = Depends(require_resource_developer),
) -> ResourceVersionRecord:
    config = {
        "skill_md": request.skill_md,
        "tool_version_ids": [str(value) for value in request.tool_version_ids],
        "knowledge_version_ids": [str(value) for value in request.knowledge_version_ids],
    }
    await _validate_editable_config(ResourceType.SKILL, config, principal)
    return await _publish(
        resource_type=ResourceType.SKILL,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        config=config,
        semantics=request,
        principal=principal,
        source_ref="skill-editor",
    )
