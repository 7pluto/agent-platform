from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.api.dependencies import ensure_resource_action, is_platform_admin, require_fresh_principal, require_platform_admin, require_platform_admin_read
from app.control_plane.assembly import agent_resource_ids, validate_agent_assembly
from app.control_plane.validation import get_agent_validation_service
from app.control_plane.store_factory import get_control_plane_store
from app.config import get_settings
from app.core.errors import ApiError
from app.db.models import (
    AgentDefinitionRow, AgentVersionRow, DeploymentConfigurationDraftRow, DeploymentPublicationProfileRow,
    DeploymentRevisionRow, DeploymentRow, ConversationRow, KnowledgeChunkRow,
    KnowledgeDocumentRow, KnowledgeIndexVersionRow, ModelDefinitionRow, ModelVersionRow,
    ResourceDefinitionRow, ResourceDescriptorRow, ResourceGrantRow, ResourceVersionRow, RunRow,
)
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType
from app.resources.store_factory import get_resource_store

router = APIRouter(tags=["workbench"])
_memory_drafts: dict[tuple[str, UUID], ConfigurationDraft] = {}
_memory_deployment_publications: dict[tuple[str, UUID], dict[str, Any]] = {}


class CatalogItem(BaseModel):
    version_id: UUID
    resource_id: UUID
    resource_type: str
    display_name: str
    description: str | None = None
    version_number: int
    status: str
    content_hash: str
    summary: str
    dependencies: list[UUID] = Field(default_factory=list)
    owner_user_id: str | None = None
    owner_dept_id: str | None = None
    source_type: str = "PLATFORM_NATIVE"
    usage_guidance: str | None = None
    one_line_summary: str | None = None
    when_to_use: str | None = None
    when_not_to_use: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    risk_level: str = "LOW"
    read_only: bool = True
    tags: list[str] = Field(default_factory=list)
    lifecycle_status: str = "ACTIVE"
    health: str = "UNKNOWN"


class DeploymentCapabilities(BaseModel):
    deployment_id: UUID
    agent_id: UUID
    agent_version_id: UUID
    agent_version_number: int
    active_revision_id: UUID
    editable: bool
    specification: dict[str, Any] | None = None
    capabilities: list[CatalogItem]
    publication_scope: str = "PERSONAL"
    publication_subjects: list[dict[str, str]] = Field(default_factory=list)


class PublicationSubject(BaseModel):
    subject_type: str = Field(pattern=r"^(USER|ROLE|DEPT)$")
    subject_id: str = Field(min_length=1, max_length=128)


class PublishConfigurationRequest(BaseModel):
    specification: dict[str, Any]
    base_revision_id: UUID | None = None
    publication_scope: str | None = Field(default=None, pattern=r"^(PERSONAL|OWNER_DEPT|SELECTED_SUBJECTS)$")
    publication_subjects: list[PublicationSubject] | None = Field(default=None, max_length=100)


class PublishConfigurationResponse(BaseModel):
    agent_version_id: UUID
    agent_version_number: int
    deployment_revision_id: UUID
    revision_number: int


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int


class ResourceListItem(BaseModel):
    resource_id: UUID
    resource_type: str
    slug: str
    display_name: str
    description: str | None = None
    latest_version_number: int | None = None
    latest_status: str | None = None
    published_version_count: int = 0
    referenced_by_count: int = 0
    updated_at: datetime | None = None
    owner_user_id: str | None = None
    owner_dept_id: str | None = None
    source_type: str = "PLATFORM_NATIVE"
    business_line: str | None = None
    audience: str | None = None
    publication_scope: str = "PERSONAL"
    lifecycle_status: str = "ACTIVE"
    health: str = "UNKNOWN"
    tags: list[str] = Field(default_factory=list)


class ResourceListPage(BaseModel):
    items: list[ResourceListItem]
    meta: PageMeta


class ResourceDetail(BaseModel):
    resource: ResourceListItem
    versions: list[CatalogItem]
    grants_count: int = 0
    references: list[dict[str, Any]] = Field(default_factory=list)
    safe_config: dict[str, Any] = Field(default_factory=dict)
    source: str = "Platform"
    created_by: str | None = None
    created_at: datetime | None = None
    usage_guidance: str | None = None
    one_line_summary: str | None = None
    when_to_use: str | None = None
    when_not_to_use: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    risk_level: str = "LOW"
    read_only: bool = True
    business_line: str | None = None
    data_involved: str | None = None
    audience: str | None = None
    usage_scenarios: str | None = None
    developer_user_ids: list[str] = Field(default_factory=list)
    publication_scope: str = "PERSONAL"
    dependency_graph: list[dict[str, Any]] = Field(default_factory=list)
    effective_permissions: list[dict[str, Any]] = Field(default_factory=list)


class ResourceImpact(BaseModel):
    resource_id: UUID
    can_delete: bool
    blockers: list[str] = Field(default_factory=list)
    agent_versions: list[dict[str, Any]] = Field(default_factory=list)
    dependent_resources: list[dict[str, Any]] = Field(default_factory=list)
    active_deployments: list[dict[str, Any]] = Field(default_factory=list)
    grant_count: int = 0
    recent_run_count: int = 0
    knowledge_document_count: int = 0


class ResourceDescriptorUpdate(BaseModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    owner_dept_id: str | None = Field(default=None, max_length=128)
    source_type: str = Field(default="PLATFORM_NATIVE", pattern=r"^(PLATFORM_NATIVE|OPENAI_COMPATIBLE|MCP|DIFY|RAGFLOW|REMOTE_HTTP|HTTP|IMPORT)$")
    source_ref: str | None = Field(default=None, max_length=256)
    usage_guidance: str | None = Field(default=None, max_length=4_000)
    one_line_summary: str = Field(min_length=1, max_length=256)
    when_to_use: str = Field(min_length=1, max_length=4_000)
    when_not_to_use: str | None = Field(default=None, max_length=4_000)
    input_summary: str = Field(min_length=1, max_length=4_000)
    output_summary: str = Field(min_length=1, max_length=4_000)
    risk_level: str = Field(default="LOW", pattern=r"^(LOW|MEDIUM|HIGH)$")
    read_only: bool = True
    business_line: str | None = Field(default=None, max_length=128)
    data_involved: str | None = Field(default=None, max_length=4_000)
    audience: str | None = Field(default=None, max_length=4_000)
    usage_scenarios: str | None = Field(default=None, max_length=4_000)
    developer_user_ids: list[str] = Field(default_factory=list, max_length=50)
    publication_scope: str = Field(default="PERSONAL", pattern=r"^(PERSONAL|OWNER_DEPT|SELECTED_SUBJECTS)$")
    tags: list[str] = Field(default_factory=list, max_length=20)
    lifecycle_status: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|ARCHIVED)$")


class KnowledgeDocumentPreview(BaseModel):
    document_id: UUID
    filename: str
    status: str
    created_at: datetime | None = None
    chunk_count: int = 0
    preview: str | None = None


class KnowledgeOverview(BaseModel):
    resource_id: UUID
    resource_version_id: UUID
    display_name: str
    description: str | None = None
    provider: str = "LOCAL"
    provider_display_name: str = "平台文件知识库"
    source_summary: str | None = None
    connection_display_name: str | None = None
    supported_operations: list[str] = Field(default_factory=list)
    active_index_version: int | None = None
    active_index_status: str | None = None
    embedding_model: str | None = None
    document_count: int = 0
    chunk_count: int = 0
    documents: list[KnowledgeDocumentPreview] = Field(default_factory=list)
    indexes: list[dict[str, Any]] = Field(default_factory=list)


class AgentListItem(BaseModel):
    deployment_id: UUID
    agent_id: UUID
    display_name: str
    description: str | None = None
    deployment_name: str
    active: bool
    revision_number: int | None = None
    capability_counts: dict[str, int] = Field(default_factory=dict)
    last_run_at: datetime | None = None


class AgentListPage(BaseModel):
    items: list[AgentListItem]
    meta: PageMeta


class ConfigurationDraft(BaseModel):
    draft_id: UUID
    deployment_id: UUID
    base_revision_id: UUID | None = None
    specification: dict[str, Any]
    lock_version: int
    updated_by: str
    updated_at: datetime | None = None


class SaveConfigurationDraftRequest(BaseModel):
    specification: dict[str, Any]
    base_revision_id: UUID | None = None
    lock_version: int | None = Field(default=None, ge=1)


class ConfigurationValidation(BaseModel):
    valid: bool
    blocking_errors: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)
    capabilities: list[CatalogItem] = Field(default_factory=list)
    resolved_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    changes: dict[str, list[str]] = Field(default_factory=dict)


class RevisionDetail(BaseModel):
    revision_id: UUID
    revision_number: int
    agent_version_id: UUID
    agent_version_number: int
    created_at: datetime | None = None
    capabilities: list[CatalogItem]


def _safe_config(config: dict[str, Any]) -> dict[str, Any]:
    """Never serialize vault refs or sensitive authentication fields to a browser."""
    hidden = {"secret_ref", "api_key", "authorization", "auth_header", "auth_scheme"}
    return {key: value for key, value in config.items() if key not in hidden}


def _summary(resource_type: str, config: dict[str, Any]) -> str:
    if resource_type == "MODEL":
        return str(config.get("model") or "OpenAI Compatible model")
    if resource_type == "PROMPT":
        return "System prompt"
    if resource_type == "SKILL":
        return "Approved Skill workflow"
    if resource_type == "TOOL":
        return str(config.get("description") or config.get("native_name") or config.get("tool_name") or "Tool")
    if resource_type == "MCP_CONNECTION":
        return "MCP connection"
    if resource_type == "KNOWLEDGE_CONNECTION":
        return "External Knowledge connection"
    if resource_type == "KNOWLEDGE":
        provider = str(config.get("provider") or "LOCAL").upper()
        return {"RAGFLOW": "RAGFlow external dataset", "REMOTE_HTTP": "Remote knowledge retrieval"}.get(provider, "Enterprise knowledge base")
    if resource_type == "MEMORY_POLICY":
        return "Long-term memory policy"
    return resource_type.replace("_", " ").title()


def _health(resource_type: str, config: dict[str, Any]) -> str:
    normalized = str(config.get("health_status") or "UNKNOWN").upper()
    external_health = normalized if normalized in {"HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"} else "UNKNOWN"
    if resource_type == "MODEL":
        return {"AVAILABLE": "HEALTHY", "UNAVAILABLE": "UNHEALTHY"}.get(str(config.get("availability") or "UNKNOWN"), "UNKNOWN")
    if resource_type == "KNOWLEDGE":
        if str(config.get("provider") or "LOCAL").upper() == "LOCAL":
            return "HEALTHY" if config.get("active_index_version") else "DEGRADED"
        return external_health
    if resource_type in {"TOOL", "MCP_CONNECTION", "KNOWLEDGE_CONNECTION"}:
        return "HEALTHY" if config.get("kind") == "NATIVE" else external_health
    return "HEALTHY"


async def _descriptors(principal: Principal) -> dict[tuple[str, UUID], dict[str, Any]]:
    """Return the metadata overlay. Old local-dev data simply has no overlay."""
    if get_settings().storage_mode != "postgres":
        return {}
    session = await _tx(principal)
    try:
        rows = await session.scalars(select(ResourceDescriptorRow).where(
            ResourceDescriptorRow.tenant_id == principal.tenant_id,
        ))
        return {
            (row.resource_type, row.resource_id): {
                "owner_user_id": row.owner_user_id,
                "owner_dept_id": row.owner_dept_id,
                "source_type": row.source_type,
                "usage_guidance": row.usage_guidance,
                "one_line_summary": row.one_line_summary,
                "when_to_use": row.when_to_use,
                "when_not_to_use": row.when_not_to_use,
                "input_summary": row.input_summary,
                "output_summary": row.output_summary,
                "risk_level": row.risk_level,
                "read_only": row.read_only,
                "business_line": row.business_line,
                "data_involved": row.data_involved,
                "audience": row.audience,
                "usage_scenarios": row.usage_scenarios,
                "developer_user_ids": list(row.developer_user_ids or []),
                "publication_scope": row.publication_scope,
                "tags": list(row.tags or []),
                "lifecycle_status": row.lifecycle_status,
            }
            for row in rows.all()
        }
    finally:
        await _close_tx(session)


def _descriptor_values(
    descriptors: dict[tuple[str, UUID], dict[str, Any]],
    resource_type: str,
    resource_id: UUID,
    *,
    fallback_owner: str | None = None,
    fallback_source: str = "PLATFORM_NATIVE",
) -> dict[str, Any]:
    descriptor = descriptors.get((resource_type, resource_id))
    if descriptor is None:
        return {
            "owner_user_id": fallback_owner,
            "owner_dept_id": None,
            "source_type": fallback_source,
            "usage_guidance": None,
            "one_line_summary": None,
            "when_to_use": None,
            "when_not_to_use": None,
            "input_summary": None,
            "output_summary": None,
            "risk_level": "LOW",
            "read_only": True,
            "business_line": None,
            "data_involved": None,
            "audience": None,
            "usage_scenarios": None,
            "developer_user_ids": [],
            "publication_scope": "PERSONAL",
            "tags": [],
            "lifecycle_status": "ACTIVE",
        }
    return {
        "owner_user_id": descriptor["owner_user_id"],
        "owner_dept_id": descriptor["owner_dept_id"],
        "source_type": descriptor["source_type"],
        "usage_guidance": descriptor["usage_guidance"],
        "one_line_summary": descriptor["one_line_summary"],
        "when_to_use": descriptor["when_to_use"],
        "when_not_to_use": descriptor["when_not_to_use"],
        "input_summary": descriptor["input_summary"],
        "output_summary": descriptor["output_summary"],
        "risk_level": descriptor["risk_level"],
        "read_only": descriptor["read_only"],
        "business_line": descriptor["business_line"],
        "data_involved": descriptor["data_involved"],
        "audience": descriptor["audience"],
        "usage_scenarios": descriptor["usage_scenarios"],
        "developer_user_ids": descriptor["developer_user_ids"],
        "publication_scope": descriptor["publication_scope"],
        "tags": descriptor["tags"],
        "lifecycle_status": descriptor["lifecycle_status"],
    }


async def _catalog(principal: Principal) -> list[CatalogItem]:
    items: list[CatalogItem] = []
    descriptors = await _descriptors(principal)
    active_local_indexes: set[UUID] = set()
    if get_settings().storage_mode == "postgres":
        session = await _tx(principal)
        try:
            active_local_indexes = set((await session.scalars(select(KnowledgeIndexVersionRow.knowledge_resource_version_id).where(
                KnowledgeIndexVersionRow.tenant_id == principal.tenant_id,
                KnowledgeIndexVersionRow.status == "ACTIVE",
            ))).all())
        finally:
            await _close_tx(session)
    model_store = get_resource_store()
    for definition in await model_store.list_models(principal):
        for version in await model_store.list_model_versions(definition.model_id, principal):
            if version.status.value != "PUBLISHED":
                continue
            descriptor = _descriptor_values(descriptors, "MODEL", definition.model_id,
                                            fallback_owner="legacy-import", fallback_source="OPENAI_COMPATIBLE")
            items.append(CatalogItem(
                version_id=version.model_version_id, resource_id=definition.model_id, resource_type="MODEL",
                display_name=definition.display_name, description=None, version_number=version.version_number,
                status=version.status.value, content_hash=version.content_hash, summary=_summary("MODEL", version.config),
                health=_health("MODEL", {**version.config, "availability": version.availability.value}), **descriptor,
            ))
    registry = get_resource_registry()
    definitions = {item.resource_id: item for item in await registry.list_definitions(principal)}
    for version in await registry.list_published_versions(principal):
        definition = definitions.get(version.resource_id)
        if definition is None:
            continue
        dependencies: list[UUID] = []
        for field in ("tool_version_ids", "knowledge_version_ids"):
            dependencies.extend(UUID(str(value)) for value in version.config.get(field, []) if value)
        if version.resource_type == ResourceType.TOOL and version.config.get("connection_version_id"):
            dependencies.append(UUID(str(version.config["connection_version_id"])))
        if version.config.get("embedding_model_version_id"):
            dependencies.append(UUID(str(version.config["embedding_model_version_id"])))
        fallback_source = (
            "DIFY" if version.config.get("kind") == "DIFY_FLOW" else
            "MCP" if version.config.get("kind") == "MCP" else
            "RAGFLOW" if str(version.config.get("provider") or "").upper() == "RAGFLOW" else
            "REMOTE_HTTP" if str(version.config.get("provider") or "").upper() == "REMOTE_HTTP" else
            "PLATFORM_NATIVE"
        )
        descriptor = _descriptor_values(descriptors, version.resource_type.value, version.resource_id,
                                        fallback_owner=definition.created_by, fallback_source=fallback_source)
        health_config = dict(version.config)
        if version.resource_type == ResourceType.KNOWLEDGE and version.resource_version_id in active_local_indexes:
            health_config["active_index_version"] = True
        items.append(CatalogItem(
            version_id=version.resource_version_id, resource_id=version.resource_id,
            resource_type=version.resource_type.value, display_name=definition.display_name,
            description=definition.description, version_number=version.version_number,
            status=version.status.value, content_hash=version.content_hash,
            summary=_summary(version.resource_type.value, version.config), dependencies=dependencies,
            health=_health(version.resource_type.value, health_config), **descriptor,
        ))
    return sorted(items, key=lambda item: (item.resource_type, item.display_name.lower(), item.version_number))


async def _tx(principal: Principal):
    session = get_session_factory()()
    await session.__aenter__()
    await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
    return session


async def _close_tx(session, commit: bool = False) -> None:
    if commit:
        await session.commit()
    else:
        await session.rollback()
    await session.__aexit__(None, None, None)


def _capability_ids(specification: dict[str, Any]) -> list[UUID]:
    return [resource_id for _, resource_id in agent_resource_ids(specification)]


async def _resource_impact(session, principal: Principal, resource_id: UUID, *, is_model: bool) -> ResourceImpact:
    version_uuid_ids = (await session.scalars(
        select(ModelVersionRow.model_version_id).where(
            ModelVersionRow.tenant_id == principal.tenant_id, ModelVersionRow.model_id == resource_id
        ) if is_model else select(ResourceVersionRow.resource_version_id).where(
            ResourceVersionRow.tenant_id == principal.tenant_id, ResourceVersionRow.resource_id == resource_id
        )
    )).all()
    version_ids = {str(item) for item in version_uuid_ids}

    definition_rows = (await session.scalars(select(ResourceDefinitionRow).where(
        ResourceDefinitionRow.tenant_id == principal.tenant_id))).all()
    definitions = {row.resource_id: row for row in definition_rows}
    dependent_resources: list[dict[str, Any]] = []
    candidates = (await session.scalars(select(ResourceVersionRow).where(
        ResourceVersionRow.tenant_id == principal.tenant_id))).all()
    seen_dependencies: set[UUID] = set()
    for candidate in candidates:
        dependencies = [str(value) for field in ("tool_version_ids", "knowledge_version_ids") for value in candidate.config.get(field, [])]
        for field in ("connection_version_id", "embedding_model_version_id"):
            if candidate.config.get(field):
                dependencies.append(str(candidate.config[field]))
        if any(value in version_ids for value in dependencies) and candidate.resource_id not in seen_dependencies:
            seen_dependencies.add(candidate.resource_id)
            definition = definitions.get(candidate.resource_id)
            dependent_resources.append({
                "resource_id": str(candidate.resource_id),
                "display_name": definition.display_name if definition else str(candidate.resource_id),
                "resource_type": candidate.resource_type,
            })

    agent_versions: list[dict[str, Any]] = []
    referenced_agent_version_ids: list[UUID] = []
    rows = await session.execute(select(AgentVersionRow, AgentDefinitionRow).join(
        AgentDefinitionRow, AgentDefinitionRow.agent_id == AgentVersionRow.agent_id).where(
        AgentVersionRow.tenant_id == principal.tenant_id))
    for version, agent in rows.all():
        if any(str(value) in version_ids for value in _capability_ids(version.specification or {})):
            referenced_agent_version_ids.append(version.agent_version_id)
            agent_versions.append({
                "agent_id": str(agent.agent_id), "agent_version_id": str(version.agent_version_id),
                "display_name": agent.display_name, "version_number": version.version_number,
            })

    active_deployments: list[dict[str, Any]] = []
    if referenced_agent_version_ids:
        deployment_rows = await session.execute(select(DeploymentRow, DeploymentRevisionRow).join(
            DeploymentRevisionRow, DeploymentRevisionRow.deployment_revision_id == DeploymentRow.active_revision_id).where(
            DeploymentRow.tenant_id == principal.tenant_id,
            DeploymentRevisionRow.agent_version_id.in_(referenced_agent_version_ids),
        ))
        active_deployments = [{
            "deployment_id": str(deployment.deployment_id), "name": deployment.name,
            "revision_number": revision.revision_number,
        } for deployment, revision in deployment_rows.all()]

    grant_target_ids = [str(resource_id), *version_ids]
    grant_count = await session.scalar(select(func.count()).select_from(ResourceGrantRow).where(
        ResourceGrantRow.tenant_id == principal.tenant_id,
        ResourceGrantRow.resource_id.in_(grant_target_ids),
    )) or 0
    knowledge_document_count = await session.scalar(select(func.count()).select_from(KnowledgeDocumentRow).where(
        KnowledgeDocumentRow.tenant_id == principal.tenant_id,
        KnowledgeDocumentRow.knowledge_resource_version_id.in_(version_uuid_ids or [UUID(int=0)]),
    )) or 0
    deployment_ids = [UUID(item["deployment_id"]) for item in active_deployments]
    recent_run_count = 0
    if deployment_ids:
        recent_run_count = await session.scalar(select(func.count()).select_from(RunRow).where(
            RunRow.tenant_id == principal.tenant_id,
            RunRow.deployment_id.in_(deployment_ids),
            RunRow.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
        )) or 0

    blockers = []
    if agent_versions:
        blockers.append("AGENT_VERSION_REFERENCES")
    if dependent_resources:
        blockers.append("DEPENDENT_RESOURCES")
    if knowledge_document_count:
        blockers.append("KNOWLEDGE_DOCUMENTS")
    return ResourceImpact(
        resource_id=resource_id, can_delete=not blockers, blockers=blockers,
        agent_versions=agent_versions, dependent_resources=dependent_resources,
        active_deployments=active_deployments, grant_count=grant_count,
        recent_run_count=recent_run_count, knowledge_document_count=knowledge_document_count,
    )


def _change_summary(previous: dict[str, Any], current: dict[str, Any], catalog: dict[UUID, CatalogItem]) -> dict[str, list[str]]:
    before = set(_capability_ids(previous)) if previous else set()
    after = set(_capability_ids(current)) if current else set()
    label = lambda value: catalog.get(value).display_name if catalog.get(value) else str(value)[:8]
    return {
        "added": [label(value) for value in sorted(after - before, key=str)],
        "removed": [label(value) for value in sorted(before - after, key=str)],
        "unchanged": [label(value) for value in sorted(before & after, key=str)],
    }


@router.get("/resource-version-catalog", response_model=list[CatalogItem])
async def resource_version_catalog(principal: Principal = Depends(require_platform_admin_read)) -> list[CatalogItem]:
    return await _catalog(principal)


@router.get("/resources/{resource_id}/descriptor", response_model=ResourceDetail)
async def get_resource_descriptor(resource_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> ResourceDetail:
    return await workbench_resource_detail(resource_id, principal)


@router.patch("/resources/{resource_id}/descriptor", response_model=ResourceDetail)
async def update_resource_descriptor(
    resource_id: UUID, request: ResourceDescriptorUpdate,
    principal: Principal = Depends(require_platform_admin),
) -> ResourceDetail:
    if get_settings().storage_mode != "postgres":
        raise ApiError(409, "RESOURCE_DESCRIPTOR_UNSUPPORTED", "resource descriptors require the persistent runtime")
    session = await _tx(principal)
    try:
        definition = await session.get(ResourceDefinitionRow, resource_id)
        resource_type = definition.resource_type if definition is not None else "MODEL"
        if definition is None:
            model = await session.get(ModelDefinitionRow, resource_id)
            if model is None or model.tenant_id != principal.tenant_id:
                raise ApiError(404, "NOT_FOUND", "resource was not found")
        elif definition.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        row = await session.scalar(select(ResourceDescriptorRow).where(
            ResourceDescriptorRow.tenant_id == principal.tenant_id,
            ResourceDescriptorRow.resource_type == resource_type,
            ResourceDescriptorRow.resource_id == resource_id,
        ).with_for_update())
        values = request.model_dump()
        if row is None:
            row = ResourceDescriptorRow(descriptor_id=uuid4(), tenant_id=principal.tenant_id,
                                        resource_type=resource_type, resource_id=resource_id, **values)
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
    finally:
        await _close_tx(session, commit=True)
    await get_governance_store().record_audit(principal, "resource_descriptor.update", resource_type, str(resource_id), {
        "owner_user_id": request.owner_user_id, "owner_dept_id": request.owner_dept_id,
        "source_type": request.source_type, "lifecycle_status": request.lifecycle_status,
        "one_line_summary": request.one_line_summary, "risk_level": request.risk_level,
    })
    return await workbench_resource_detail(resource_id, principal)


@router.get("/workbench/resources", response_model=ResourceListPage)
async def workbench_resources(
    query: str | None = Query(default=None, max_length=128),
    resource_type: ResourceType | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_platform_admin_read),
) -> ResourceListPage:
    catalog = await _catalog(principal)
    descriptors = await _descriptors(principal)
    versions_by_resource: dict[UUID, list[CatalogItem]] = {}
    for item in catalog:
        versions_by_resource.setdefault(item.resource_id, []).append(item)
    if get_settings().storage_mode != "postgres":
        definitions = await get_resource_registry().list_definitions(principal)
        candidates: list[ResourceListItem] = []
        for definition in definitions:
            versions = versions_by_resource.get(definition.resource_id, [])
            latest = max(versions, key=lambda item: item.version_number, default=None)
            haystack = f"{definition.display_name} {definition.slug} {definition.description or ''}".lower()
            if (resource_type and definition.resource_type != resource_type) or (status and (latest is None or latest.status != status)) or (query and query.lower() not in haystack):
                continue
            metadata = _descriptor_values(descriptors, definition.resource_type.value, definition.resource_id,
                                          fallback_owner=getattr(definition, "created_by", None))
            candidates.append(ResourceListItem(resource_id=definition.resource_id, resource_type=definition.resource_type.value,
                slug=definition.slug, display_name=definition.display_name, description=definition.description,
                latest_version_number=latest.version_number if latest else None, latest_status=latest.status if latest else None,
                published_version_count=len(versions), updated_at=definition.updated_at, health=latest.health if latest else "UNKNOWN", **{key: metadata[key] for key in (
                    "owner_user_id", "owner_dept_id", "source_type", "lifecycle_status", "tags")}))
        for definition in await get_resource_store().list_models(principal):
            versions = versions_by_resource.get(definition.model_id, [])
            latest = max(versions, key=lambda item: item.version_number, default=None)
            haystack = f"{definition.display_name} {definition.slug} {definition.provider}".lower()
            if (resource_type and resource_type != ResourceType.MODEL) or (status and (latest is None or latest.status != status)) or (query and query.lower() not in haystack):
                continue
            metadata = _descriptor_values(descriptors, "MODEL", definition.model_id,
                                          fallback_owner="legacy-import", fallback_source="OPENAI_COMPATIBLE")
            candidates.append(ResourceListItem(resource_id=definition.model_id, resource_type="MODEL",
                slug=definition.slug, display_name=definition.display_name,
                description=f"{definition.provider} 模型", latest_version_number=latest.version_number if latest else None,
                latest_status=latest.status if latest else None, published_version_count=len(versions),
                updated_at=definition.created_at, health=latest.health if latest else "UNKNOWN",
                **{key: metadata[key] for key in ("owner_user_id", "owner_dept_id", "source_type", "lifecycle_status", "tags")}))
        candidates.sort(key=lambda item: (item.resource_type, item.display_name.lower()))
        start = (page - 1) * page_size
        return ResourceListPage(items=candidates[start:start + page_size], meta=PageMeta(total=len(candidates), page=page, page_size=page_size))
    session = await _tx(principal)
    try:
        rows = await session.scalars(select(ResourceDefinitionRow).where(ResourceDefinitionRow.tenant_id == principal.tenant_id))
        definitions = rows.all()
        model_rows = await session.scalars(select(ModelDefinitionRow).where(ModelDefinitionRow.tenant_id == principal.tenant_id))
        models = model_rows.all()
        agent_rows = await session.scalars(select(AgentVersionRow).where(AgentVersionRow.tenant_id == principal.tenant_id))
        referenced_ids = {
            str(version_id)
            for agent_version in agent_rows.all()
            for version_id in _capability_ids(agent_version.specification or {})
        }
        candidates: list[ResourceListItem] = []
        for definition in definitions:
            versions = versions_by_resource.get(definition.resource_id, [])
            latest = max(versions, key=lambda item: item.version_number, default=None)
            if resource_type and definition.resource_type != resource_type.value:
                continue
            if status and (latest is None or latest.status != status):
                continue
            haystack = f"{definition.display_name} {definition.slug} {definition.description or ''}".lower()
            if query and query.lower() not in haystack:
                continue
            metadata = _descriptor_values(descriptors, definition.resource_type, definition.resource_id,
                                          fallback_owner=definition.created_by)
            candidates.append(ResourceListItem(
                resource_id=definition.resource_id, resource_type=definition.resource_type,
                slug=definition.slug, display_name=definition.display_name,
                description=definition.description, latest_version_number=latest.version_number if latest else None,
                latest_status=latest.status if latest else None,
                published_version_count=len(versions),
                referenced_by_count=sum(str(version.version_id) in referenced_ids for version in versions),
                updated_at=definition.updated_at, health=latest.health if latest else "UNKNOWN",
                **{key: metadata[key] for key in ("owner_user_id", "owner_dept_id", "source_type", "business_line", "audience", "publication_scope", "lifecycle_status", "tags")},
            ))
        for definition in models:
            versions = versions_by_resource.get(definition.model_id, [])
            latest = max(versions, key=lambda item: item.version_number, default=None)
            if resource_type and resource_type != ResourceType.MODEL:
                continue
            if status and (latest is None or latest.status != status):
                continue
            haystack = f"{definition.display_name} {definition.slug} {definition.provider}".lower()
            if query and query.lower() not in haystack:
                continue
            metadata = _descriptor_values(descriptors, "MODEL", definition.model_id,
                                          fallback_owner="legacy-import", fallback_source="OPENAI_COMPATIBLE")
            candidates.append(ResourceListItem(
                resource_id=definition.model_id, resource_type="MODEL", slug=definition.slug,
                display_name=definition.display_name, description=f"{definition.provider} 模型",
                latest_version_number=latest.version_number if latest else None,
                latest_status=latest.status if latest else None, published_version_count=len(versions),
                referenced_by_count=sum(str(version.version_id) in referenced_ids for version in versions),
                updated_at=definition.created_at, health=latest.health if latest else "UNKNOWN",
                **{key: metadata[key] for key in ("owner_user_id", "owner_dept_id", "source_type", "business_line", "audience", "publication_scope", "lifecycle_status", "tags")},
            ))
        candidates.sort(key=lambda item: (item.resource_type, item.display_name.lower()))
        total = len(candidates)
        start = (page - 1) * page_size
        return ResourceListPage(items=candidates[start:start + page_size], meta=PageMeta(total=total, page=page, page_size=page_size))
    finally:
        await _close_tx(session)


@router.get("/workbench/resources/{resource_id}", response_model=ResourceDetail)
async def workbench_resource_detail(resource_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> ResourceDetail:
    catalog = await _catalog(principal)
    descriptors = await _descriptors(principal)
    versions = [item for item in catalog if item.resource_id == resource_id]
    if get_settings().storage_mode != "postgres":
        definition = next((item for item in await get_resource_registry().list_definitions(principal) if item.resource_id == resource_id), None)
        if definition is None:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        latest = max(versions, key=lambda item: item.version_number, default=None)
        metadata = _descriptor_values(descriptors, definition.resource_type.value, definition.resource_id,
                                      fallback_owner=getattr(definition, "created_by", None))
        return ResourceDetail(resource=ResourceListItem(resource_id=definition.resource_id, resource_type=definition.resource_type.value,
            slug=definition.slug, display_name=definition.display_name, description=definition.description,
            latest_version_number=latest.version_number if latest else None, latest_status=latest.status if latest else None,
            published_version_count=len(versions), updated_at=definition.updated_at, health=latest.health if latest else "UNKNOWN",
            **{key: metadata[key] for key in ("owner_user_id", "owner_dept_id", "source_type", "business_line", "audience", "publication_scope", "lifecycle_status", "tags")}), versions=versions,
            safe_config=_safe_config(definition.draft_config), source="Platform resource center",
            created_by=getattr(definition, "created_by", None), created_at=getattr(definition, "created_at", None),
            usage_guidance=metadata["usage_guidance"], **{key: metadata[key] for key in (
                "one_line_summary", "when_to_use", "when_not_to_use", "input_summary", "output_summary", "risk_level", "read_only",
                "business_line", "data_involved", "audience", "usage_scenarios", "developer_user_ids", "publication_scope")})
    session = await _tx(principal)
    try:
        definition = await session.get(ResourceDefinitionRow, resource_id)
        model = None if definition is not None else await session.get(ModelDefinitionRow, resource_id)
        if definition is None and (model is None or model.tenant_id != principal.tenant_id):
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        if definition is not None and definition.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        is_model = model is not None
        deleted_type = "MODEL" if is_model else definition.resource_type
        resource_type = "MODEL" if is_model else definition.resource_type
        slug = model.slug if is_model else definition.slug
        display_name = model.display_name if is_model else definition.display_name
        description = f"{model.provider} 模型" if is_model else definition.description
        draft_config = model.config if is_model else definition.draft_config
        created_by = "legacy-import" if is_model else definition.created_by
        created_at = model.created_at if is_model else definition.created_at
        updated_at = model.created_at if is_model else definition.updated_at
        latest = max(versions, key=lambda item: item.version_number, default=None)
        grant_target_ids = [str(resource_id), *(str(item.version_id) for item in versions)]
        grants_count = await session.scalar(select(func.count()).select_from(ResourceGrantRow).where(
            ResourceGrantRow.tenant_id == principal.tenant_id,
            ResourceGrantRow.resource_id.in_(grant_target_ids),
        )) or 0
        references: list[dict[str, Any]] = []
        rows = await session.execute(select(AgentVersionRow, AgentDefinitionRow).join(AgentDefinitionRow, AgentDefinitionRow.agent_id == AgentVersionRow.agent_id).where(AgentVersionRow.tenant_id == principal.tenant_id))
        ids = {str(item.version_id) for item in versions}
        for version, agent in rows.all():
            specification = version.specification or {}
            if any(str(value) in ids for value in _capability_ids(specification)):
                references.append({"kind": "AGENT_VERSION", "display_name": agent.display_name, "version_number": version.version_number, "agent_id": str(agent.agent_id)})
        metadata = _descriptor_values(descriptors, resource_type, resource_id,
                                      fallback_owner=created_by,
                                      fallback_source="OPENAI_COMPATIBLE" if is_model else "PLATFORM_NATIVE")
        resource = ResourceListItem(
            resource_id=resource_id, resource_type=resource_type,
            slug=slug, display_name=display_name, description=description,
            latest_version_number=latest.version_number if latest else None,
            latest_status=latest.status if latest else None,
            published_version_count=len(versions), referenced_by_count=len(references), updated_at=updated_at, health=latest.health if latest else "UNKNOWN",
            **{key: metadata[key] for key in ("owner_user_id", "owner_dept_id", "source_type", "business_line", "audience", "publication_scope", "lifecycle_status", "tags")},
        )
        source = metadata["source_type"].replace("_", " ").title()
        catalog_by_version = {item.version_id: item for item in catalog}
        graph = [{
            "version_id": str(item.version_id), "display_name": item.display_name,
            "resource_type": item.resource_type,
            "dependencies": [{
                "version_id": str(value),
                "display_name": catalog_by_version[value].display_name if value in catalog_by_version else str(value),
                "resource_type": catalog_by_version[value].resource_type if value in catalog_by_version else "UNKNOWN",
                "version_number": catalog_by_version[value].version_number if value in catalog_by_version else None,
            } for value in item.dependencies],
        } for item in versions]
        grants = []
        for target_id in grant_target_ids:
            grants.extend(await get_governance_store().list_grants(principal, resource_type, target_id))
        effective_permissions: list[dict[str, Any]] = []
        if metadata["owner_user_id"] == principal.external_user_id:
            effective_permissions.append({"origin": "OWNER", "effect": "ALLOW", "actions": ["VIEW", "USE", "EDIT"]})
        if is_platform_admin(principal):
            effective_permissions.append({"origin": "ADMIN_BYPASS", "effect": "ALLOW", "actions": ["VIEW", "USE", "EDIT", "PUBLISH", "MANAGE", "RUN"]})
        for grant in grants:
            effective_permissions.append({"origin": grant.subject_type.value, "effect": grant.effect.value,
                                          "subject_id": grant.subject_id, "actions": sorted(action.value for action in grant.actions)})
        return ResourceDetail(resource=resource, versions=versions, grants_count=grants_count, references=references,
                              safe_config=_safe_config(draft_config), source=source,
                              created_by=created_by, created_at=created_at,
                              usage_guidance=metadata["usage_guidance"], dependency_graph=graph,
                              **{key: metadata[key] for key in (
                                  "one_line_summary", "when_to_use", "when_not_to_use", "input_summary", "output_summary", "risk_level", "read_only",
                                  "business_line", "data_involved", "audience", "usage_scenarios", "developer_user_ids", "publication_scope")},
                              effective_permissions=effective_permissions)
    finally:
        await _close_tx(session)


@router.get("/workbench/knowledge/{resource_id}", response_model=KnowledgeOverview)
async def workbench_knowledge_overview(resource_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> KnowledgeOverview:
    session = await _tx(principal)
    try:
        definition = await session.get(ResourceDefinitionRow, resource_id)
        if definition is None or definition.tenant_id != principal.tenant_id or definition.resource_type != ResourceType.KNOWLEDGE.value:
            raise ApiError(404, "NOT_FOUND", "knowledge base was not found")
        version = await session.scalar(select(ResourceVersionRow).where(
            ResourceVersionRow.tenant_id == principal.tenant_id, ResourceVersionRow.resource_id == resource_id,
            ResourceVersionRow.status == "PUBLISHED",
        ).order_by(ResourceVersionRow.version_number.desc()))
        if version is None:
            raise ApiError(409, "KNOWLEDGE_VERSION_UNPUBLISHED", "knowledge base has no published version")
        config = version.config or {}
        provider = str(config.get("provider") or "LOCAL").upper()
        provider_display_names = {
            "LOCAL": "平台文件知识库",
            "RAGFLOW": "RAGFlow 外部知识库",
            "REMOTE_HTTP": "远程知识检索服务",
        }
        if provider != "LOCAL":
            connection_display_name = None
            connection_id = config.get("connection_version_id")
            if connection_id:
                try:
                    connection_version = await session.get(ResourceVersionRow, UUID(str(connection_id)))
                    if connection_version is not None and connection_version.tenant_id == principal.tenant_id:
                        connection_definition = await session.get(ResourceDefinitionRow, connection_version.resource_id)
                        if connection_definition is not None:
                            connection_display_name = connection_definition.display_name
                except ValueError:
                    pass
            source_summary = "由已绑定的外部连接实时检索；文档和索引仍在外部服务管理。"
            if provider == "RAGFLOW":
                source_summary = "由 RAGFlow 数据集实时检索；文档、解析和索引在 RAGFlow 中管理。"
            return KnowledgeOverview(
                resource_id=resource_id,
                resource_version_id=version.resource_version_id,
                display_name=definition.display_name,
                description=definition.description,
                provider=provider,
                provider_display_name=provider_display_names.get(provider, provider),
                source_summary=source_summary,
                connection_display_name=connection_display_name,
                supported_operations=["RETRIEVAL_TEST", "PERMISSIONS", "USAGE", "CONNECTION_STATUS"],
            )
        documents = (await session.scalars(select(KnowledgeDocumentRow).where(
            KnowledgeDocumentRow.tenant_id == principal.tenant_id,
            KnowledgeDocumentRow.knowledge_resource_version_id == version.resource_version_id,
        ).order_by(KnowledgeDocumentRow.created_at.desc()))).all()
        indexes = (await session.scalars(select(KnowledgeIndexVersionRow).where(
            KnowledgeIndexVersionRow.tenant_id == principal.tenant_id,
            KnowledgeIndexVersionRow.knowledge_resource_version_id == version.resource_version_id,
        ).order_by(KnowledgeIndexVersionRow.version_number.desc()))).all()
        active = next((item for item in indexes if item.status == "ACTIVE"), None)
        previews: list[KnowledgeDocumentPreview] = []
        total_chunks = 0
        for document in documents:
            chunk_count = 0
            preview = None
            if active:
                chunks = (await session.scalars(select(KnowledgeChunkRow).where(
                    KnowledgeChunkRow.tenant_id == principal.tenant_id,
                    KnowledgeChunkRow.index_version_id == active.index_version_id,
                    KnowledgeChunkRow.document_id == document.document_id,
                ).order_by(KnowledgeChunkRow.chunk_number))).all()
                chunk_count = len(chunks)
                total_chunks += chunk_count
                if chunks:
                    preview = chunks[0].content[:600]
            previews.append(KnowledgeDocumentPreview(document_id=document.document_id, filename=document.filename,
                status=document.status, created_at=document.created_at, chunk_count=chunk_count, preview=preview))
        return KnowledgeOverview(resource_id=resource_id, resource_version_id=version.resource_version_id,
            display_name=definition.display_name, description=definition.description,
            provider=provider, provider_display_name=provider_display_names["LOCAL"],
            source_summary="文件由平台后端接收并保存到对象存储，索引在平台内构建和激活。",
            supported_operations=["UPLOAD", "INDEX", "RETRIEVAL_TEST", "PERMISSIONS", "USAGE"],
            active_index_version=active.version_number if active else None,
            active_index_status=active.status if active else None,
            embedding_model=active.embedding_model if active else None,
            document_count=len(documents), chunk_count=total_chunks, documents=previews,
            indexes=[{"version_number": item.version_number, "status": item.status, "embedding_model": item.embedding_model,
                      "created_at": item.created_at, "chunk_strategy": item.chunk_strategy} for item in indexes])
    finally:
        await _close_tx(session)


@router.get("/workbench/resources/{resource_id}/impact", response_model=ResourceImpact)
async def workbench_resource_impact(resource_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> ResourceImpact:
    if get_settings().storage_mode != "postgres":
        raise ApiError(409, "RESOURCE_IMPACT_UNSUPPORTED", "resource impact requires the persistent runtime")
    session = await _tx(principal)
    try:
        definition = await session.get(ResourceDefinitionRow, resource_id)
        model = None if definition is not None else await session.get(ModelDefinitionRow, resource_id)
        if definition is None and (model is None or model.tenant_id != principal.tenant_id):
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        if definition is not None and definition.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        return await _resource_impact(session, principal, resource_id, is_model=model is not None)
    finally:
        await _close_tx(session)


@router.delete("/workbench/resources/{resource_id}", status_code=204, response_class=Response)
async def delete_workbench_resource(resource_id: UUID, principal: Principal = Depends(require_platform_admin)) -> Response:
    """Delete only a capability that has never been assembled into an Agent Version."""
    if get_settings().storage_mode != "postgres":
        raise ApiError(409, "RESOURCE_DELETE_UNSUPPORTED", "resource deletion requires the persistent runtime")
    session = await _tx(principal)
    try:
        definition = await session.get(ResourceDefinitionRow, resource_id)
        model = None if definition is not None else await session.get(ModelDefinitionRow, resource_id)
        if definition is None and (model is None or model.tenant_id != principal.tenant_id):
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        if definition is not None and definition.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        is_model = model is not None
        deleted_type = "MODEL" if is_model else definition.resource_type
        impact = await _resource_impact(session, principal, resource_id, is_model=is_model)
        version_uuid_ids = (await session.scalars(
            select(ModelVersionRow.model_version_id).where(
                ModelVersionRow.tenant_id == principal.tenant_id, ModelVersionRow.model_id == resource_id
            ) if is_model else select(ResourceVersionRow.resource_version_id).where(
                ResourceVersionRow.tenant_id == principal.tenant_id, ResourceVersionRow.resource_id == resource_id
            )
        )).all()
        version_ids = {str(item) for item in version_uuid_ids}
        if not impact.can_delete:
            raise ApiError(409, "RESOURCE_DELETE_BLOCKED", "resource is still in use and cannot be deleted", {
                **impact.model_dump(mode="json"),
            })
        grant_target_ids = [str(resource_id), *version_ids]
        await session.execute(delete(ResourceGrantRow).where(
            ResourceGrantRow.tenant_id == principal.tenant_id,
            ResourceGrantRow.resource_id.in_(grant_target_ids),
        ))
        await session.execute(delete(ResourceDescriptorRow).where(
            ResourceDescriptorRow.tenant_id == principal.tenant_id,
            ResourceDescriptorRow.resource_id == resource_id,
        ))
        await session.delete(model if is_model else definition)
    finally:
        await _close_tx(session, commit=True)
    await get_governance_store().record_audit(
        principal, "resource.delete", deleted_type, str(resource_id), {}
    )
    return Response(status_code=204)


@router.get("/workbench/agents", response_model=AgentListPage)
async def workbench_agents(
    query: str | None = Query(default=None, max_length=128),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_fresh_principal),
) -> AgentListPage:
    # Agent Plaza visibility is governed solely by the Deployment grant.  Do
    # not build a USE-filtered resource catalogue here: an inaccessible RAG,
    # MCP connection or Tool must never make an otherwise visible Agent vanish
    # from the list before a Run has even started.
    if get_settings().storage_mode != "postgres":
        store = get_control_plane_store()
        definitions = {item.agent_id: item for item in await store.list_definitions(principal)}
        candidates: list[AgentListItem] = []
        for deployment in await store.list_deployments(principal):
            if not is_platform_admin(principal):
                try:
                    await _ensure_deployment_visible(principal, deployment.deployment_id)
                except ApiError:
                    continue
            agent = definitions.get(deployment.agent_id)
            if not agent:
                continue
            resolved = await store.resolve(deployment.deployment_id, principal) if deployment.active_revision_id else None
            is_active = resolved is not None
            haystack = f"{agent.display_name} {deployment.name} {agent.description or ''}".lower()
            if (query and query.lower() not in haystack) or (active is not None and active != is_active):
                continue
            counts: dict[str, int] = {}
            if resolved:
                for resource_type_, _ in agent_resource_ids(resolved.agent_version.specification or {}):
                    counts[resource_type_.value] = counts.get(resource_type_.value, 0) + 1
            candidates.append(AgentListItem(deployment_id=deployment.deployment_id, agent_id=agent.agent_id,
                display_name=agent.display_name, description=agent.description, deployment_name=deployment.description or deployment.name,
                active=is_active, revision_number=resolved.revision.revision_number if resolved else None,
                capability_counts=counts))
        candidates.sort(key=lambda item: item.display_name.lower())
        start = (page - 1) * page_size
        return AgentListPage(items=candidates[start:start + page_size], meta=PageMeta(total=len(candidates), page=page, page_size=page_size))
    session = await _tx(principal)
    try:
        result = await session.execute(
            select(DeploymentRow, AgentDefinitionRow, DeploymentRevisionRow, AgentVersionRow)
            .join(AgentDefinitionRow, AgentDefinitionRow.agent_id == DeploymentRow.agent_id)
            .outerjoin(DeploymentRevisionRow, DeploymentRevisionRow.deployment_revision_id == DeploymentRow.active_revision_id)
            .outerjoin(AgentVersionRow, AgentVersionRow.agent_version_id == DeploymentRevisionRow.agent_version_id)
            .where(DeploymentRow.tenant_id == principal.tenant_id)
        )
        items: list[AgentListItem] = []
        for deployment, agent, revision, version in result.all():
            if not is_platform_admin(principal):
                try:
                    await _ensure_deployment_visible(principal, deployment.deployment_id)
                except ApiError:
                    continue
            is_active = revision is not None
            haystack = f"{agent.display_name} {deployment.name} {agent.description or ''}".lower()
            if query and query.lower() not in haystack:
                continue
            if active is not None and active != is_active:
                continue
            counts: dict[str, int] = {}
            if version:
                for type_, version_id in agent_resource_ids(version.specification or {}):
                    label = type_.value
                    counts[label] = counts.get(label, 0) + 1
            last_run_at = await session.scalar(select(func.max(RunRow.created_at)).where(
                RunRow.tenant_id == principal.tenant_id, RunRow.deployment_id == deployment.deployment_id
            ))
            items.append(AgentListItem(
                deployment_id=deployment.deployment_id, agent_id=agent.agent_id,
                display_name=agent.display_name, description=agent.description,
                deployment_name=deployment.description or deployment.name, active=is_active,
                revision_number=revision.revision_number if revision else None,
                capability_counts=counts, last_run_at=last_run_at,
            ))
        items.sort(key=lambda item: item.display_name.lower())
        total = len(items)
        start = (page - 1) * page_size
        return AgentListPage(items=items[start:start + page_size], meta=PageMeta(total=total, page=page, page_size=page_size))
    finally:
        await _close_tx(session)


@router.get("/workbench/deployments/{deployment_id}", response_model=DeploymentCapabilities)
async def workbench_deployment_detail(
    deployment_id: UUID, principal: Principal = Depends(require_platform_admin_read)
) -> DeploymentCapabilities:
    return await deployment_capabilities(deployment_id, principal)


@router.delete("/workbench/deployments/{deployment_id}", status_code=204, response_class=Response)
async def delete_workbench_deployment(deployment_id: UUID, principal: Principal = Depends(require_platform_admin)) -> Response:
    """Remove an unused Agent deployment without breaking run reproducibility."""
    if get_settings().storage_mode != "postgres":
        raise ApiError(409, "DEPLOYMENT_DELETE_UNSUPPORTED", "agent deletion requires the persistent runtime")
    session = await _tx(principal)
    deleted_agent_id: UUID | None = None
    try:
        deployment = await session.get(DeploymentRow, deployment_id)
        if deployment is None or deployment.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "deployment was not found")
        run_count = await session.scalar(select(func.count()).select_from(RunRow).where(
            RunRow.tenant_id == principal.tenant_id, RunRow.deployment_id == deployment_id)) or 0
        conversation_count = await session.scalar(select(func.count()).select_from(ConversationRow).where(
            ConversationRow.tenant_id == principal.tenant_id, ConversationRow.deployment_id == deployment_id)) or 0
        if run_count or conversation_count:
            raise ApiError(409, "DEPLOYMENT_DELETE_BLOCKED", "agent has Run or conversation history and cannot be deleted", {
                "run_count": run_count, "conversation_count": conversation_count,
                "recommendation": "keep the historical Agent, or create a new replacement deployment",
            })
        agent_id = deployment.agent_id
        await session.delete(deployment)
        await session.flush()
        remaining = await session.scalar(select(func.count()).select_from(DeploymentRow).where(
            DeploymentRow.tenant_id == principal.tenant_id, DeploymentRow.agent_id == agent_id)) or 0
        if remaining == 0:
            agent = await session.get(AgentDefinitionRow, agent_id)
            if agent is not None:
                await session.delete(agent)
                deleted_agent_id = agent_id
    finally:
        await _close_tx(session, commit=True)
    await get_governance_store().record_audit(principal, "deployment.delete", "DEPLOYMENT", str(deployment_id),
                                               {"agent_deleted": str(deleted_agent_id) if deleted_agent_id else None})
    return Response(status_code=204)


@router.get("/deployments/{deployment_id}/configuration-draft", response_model=ConfigurationDraft)
async def get_configuration_draft(
    deployment_id: UUID, principal: Principal = Depends(require_platform_admin_read)
) -> ConfigurationDraft:
    resolved = await get_control_plane_store().resolve(deployment_id, principal)
    if get_settings().storage_mode != "postgres":
        return _memory_drafts.get((principal.tenant_id, deployment_id), ConfigurationDraft(
            draft_id=uuid4(), deployment_id=deployment_id, base_revision_id=resolved.revision.deployment_revision_id,
            specification=resolved.agent_version.specification, lock_version=0, updated_by=principal.external_user_id,
        ))
    session = await _tx(principal)
    try:
        row = await session.scalar(select(DeploymentConfigurationDraftRow).where(
            DeploymentConfigurationDraftRow.tenant_id == principal.tenant_id,
            DeploymentConfigurationDraftRow.deployment_id == deployment_id,
        ))
        if row is None:
            return ConfigurationDraft(
                draft_id=uuid4(), deployment_id=deployment_id,
                base_revision_id=resolved.revision.deployment_revision_id,
                specification=resolved.agent_version.specification, lock_version=0,
                updated_by=principal.external_user_id,
            )
        return ConfigurationDraft(
            draft_id=row.draft_id, deployment_id=row.deployment_id,
            base_revision_id=row.base_revision_id, specification=row.specification,
            lock_version=row.lock_version, updated_by=row.updated_by, updated_at=row.updated_at,
        )
    finally:
        await _close_tx(session)


@router.put("/deployments/{deployment_id}/configuration-draft", response_model=ConfigurationDraft)
async def save_configuration_draft(
    deployment_id: UUID, request: SaveConfigurationDraftRequest,
    principal: Principal = Depends(require_platform_admin),
) -> ConfigurationDraft:
    resolved = await get_control_plane_store().resolve(deployment_id, principal)
    if get_settings().storage_mode != "postgres":
        key = (principal.tenant_id, deployment_id)
        existing = _memory_drafts.get(key)
        if existing and request.lock_version is not None and request.lock_version != existing.lock_version:
            raise ApiError(409, "CONFIGURATION_DRAFT_CONFLICT", "configuration draft was changed by another administrator")
        saved = ConfigurationDraft(draft_id=existing.draft_id if existing else uuid4(), deployment_id=deployment_id,
            base_revision_id=request.base_revision_id or (existing.base_revision_id if existing else resolved.revision.deployment_revision_id),
            specification=request.specification, lock_version=(existing.lock_version + 1) if existing else 1,
            updated_by=principal.external_user_id)
        _memory_drafts[key] = saved
        return saved
    session = await _tx(principal)
    try:
        row = await session.scalar(select(DeploymentConfigurationDraftRow).where(
            DeploymentConfigurationDraftRow.tenant_id == principal.tenant_id,
            DeploymentConfigurationDraftRow.deployment_id == deployment_id,
        ).with_for_update())
        if row and request.lock_version is not None and request.lock_version != row.lock_version:
            raise ApiError(409, "CONFIGURATION_DRAFT_CONFLICT", "configuration draft was changed by another administrator")
        if row is None:
            row = DeploymentConfigurationDraftRow(
                draft_id=uuid4(), tenant_id=principal.tenant_id, deployment_id=deployment_id,
                base_revision_id=request.base_revision_id or resolved.revision.deployment_revision_id,
                specification=request.specification, lock_version=1, updated_by=principal.external_user_id,
            )
            session.add(row)
        else:
            row.specification = request.specification
            row.base_revision_id = request.base_revision_id or row.base_revision_id
            row.lock_version += 1
            row.updated_by = principal.external_user_id
        await session.flush()
        return ConfigurationDraft(
            draft_id=row.draft_id, deployment_id=row.deployment_id, base_revision_id=row.base_revision_id,
            specification=row.specification, lock_version=row.lock_version,
            updated_by=row.updated_by, updated_at=row.updated_at,
        )
    finally:
        await _close_tx(session, commit=True)


@router.post("/deployments/{deployment_id}/configuration-draft/validate", response_model=ConfigurationValidation)
async def validate_configuration_draft(
    deployment_id: UUID, request: SaveConfigurationDraftRequest,
    principal: Principal = Depends(require_platform_admin),
) -> ConfigurationValidation:
    resolved = await get_control_plane_store().resolve(deployment_id, principal)
    catalog = {item.version_id: item for item in await _catalog(principal)}
    outcome = await get_agent_validation_service().validate(request.specification, principal)
    errors = outcome.blocking_errors
    warnings = outcome.warnings
    capabilities: list[CatalogItem] = []
    try:
        bindings = outcome.bindings
        capability_ids = _capability_ids(request.specification)
        capabilities = [catalog[item] for item in capability_ids if item in catalog]
        resolved_capabilities = [
            {
                "version_id": str(binding.resource.resource_version_id),
                "display_name": catalog.get(binding.resource.resource_version_id).display_name if catalog.get(binding.resource.resource_version_id) else str(binding.resource.resource_version_id),
                "resource_type": binding.resource.resource_type.value,
                "origin": binding.origin,
                "dependency_path": binding.dependency_path,
            }
            for binding in bindings
        ]
    except ApiError as exc:
        issue = {"code": exc.code, "message": exc.message}
        if issue not in errors:
            errors.append(issue)
    changes = _change_summary(resolved.agent_version.specification, request.specification, catalog)
    if not changes["added"] and not changes["removed"]:
        warnings.append({"code": "NO_CAPABILITY_CHANGE", "message": "Capability selection is unchanged; only runtime policy or metadata may differ."})
    return ConfigurationValidation(valid=not errors, blocking_errors=errors, warnings=warnings, capabilities=capabilities,
                                   resolved_capabilities=locals().get("resolved_capabilities", []), changes=changes)


@router.get("/deployments/{deployment_id}/revisions/{revision_id}", response_model=RevisionDetail)
async def deployment_revision_detail(
    deployment_id: UUID, revision_id: UUID, principal: Principal = Depends(require_platform_admin_read)
) -> RevisionDetail:
    session = await _tx(principal)
    try:
        revision = await session.get(DeploymentRevisionRow, revision_id)
        if revision is None or revision.tenant_id != principal.tenant_id or revision.deployment_id != deployment_id:
            raise ApiError(404, "NOT_FOUND", "deployment revision was not found")
        version = await session.get(AgentVersionRow, revision.agent_version_id)
        catalog = {item.version_id: item for item in await _catalog(principal)}
        capabilities = [catalog[item] for item in _capability_ids(version.specification) if item in catalog]
        return RevisionDetail(revision_id=revision_id, revision_number=revision.revision_number,
                              agent_version_id=version.agent_version_id, agent_version_number=version.version_number,
                              created_at=revision.created_at, capabilities=capabilities)
    finally:
        await _close_tx(session)


@router.get("/deployments/{deployment_id}/capabilities", response_model=DeploymentCapabilities)
async def deployment_capabilities(
    deployment_id: UUID, principal: Principal = Depends(require_fresh_principal)
) -> DeploymentCapabilities:
    if not is_platform_admin(principal):
        await _ensure_deployment_visible(principal, deployment_id)
    resolved = await get_control_plane_store().resolve(deployment_id, principal)
    admin = is_platform_admin(principal)
    # Build the safe catalogue internally for every caller so ordinary users see
    # meaningful business names. Only administrators receive the specification,
    # versions/dependencies remain sanitized by CatalogItem.
    catalog: dict[UUID, CatalogItem] = {item.version_id: item for item in await _catalog(principal)}
    ids: list[UUID] = []
    specification = resolved.agent_version.specification
    for field in ("model_version_id", "prompt_version_id", "memory_policy_version_id"):
        if specification.get(field):
            ids.append(UUID(str(specification[field])))
    for field in ("skill_version_ids", "tool_version_ids", "mcp_connection_version_ids", "knowledge_version_ids"):
        ids.extend(UUID(str(value)) for value in specification.get(field, []))
    publication_scope = "PERSONAL"
    publication_subjects: list[dict[str, str]] = []
    if get_settings().storage_mode == "postgres":
        session = await _tx(principal)
        try:
            profile = await session.scalar(select(DeploymentPublicationProfileRow).where(
                DeploymentPublicationProfileRow.tenant_id == principal.tenant_id,
                DeploymentPublicationProfileRow.deployment_id == deployment_id,
            ))
            if profile:
                publication_scope = profile.publication_scope
                publication_subjects = [dict(item) for item in (profile.subject_bindings or [])]
        finally:
            await _close_tx(session)
    else:
        profile = _memory_deployment_publications.get((principal.tenant_id, deployment_id))
        if profile:
            publication_scope = str(profile["publication_scope"])
            publication_subjects = [dict(item) for item in profile["subject_bindings"]]
    return DeploymentCapabilities(
        deployment_id=deployment_id, agent_id=resolved.deployment.agent_id,
        agent_version_id=resolved.agent_version.agent_version_id,
        agent_version_number=resolved.agent_version.version_number,
        active_revision_id=resolved.revision.deployment_revision_id, editable=admin,
        specification=specification if admin else None,
        capabilities=[catalog[item] for item in ids if item in catalog],
        publication_scope=publication_scope, publication_subjects=publication_subjects,
    )


async def _ensure_deployment_visible(principal: Principal, deployment_id: UUID) -> None:
    """Allow a plaza card to be seen with either VIEW or RUN on its Deployment.

    This intentionally has no dependency-resolution step.  Capability grants
    are evaluated later, only when the runtime invokes an optional capability.
    """
    try:
        await ensure_resource_action(principal, "VIEW", "DEPLOYMENT", str(deployment_id))
        return
    except ApiError as view_error:
        try:
            await ensure_resource_action(principal, "RUN", "DEPLOYMENT", str(deployment_id))
            return
        except ApiError:
            raise view_error


def _resolve_publication_bindings(
    request: PublishConfigurationRequest, principal: Principal, current: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Normalize the audience selected in the Agent publishing form.

    The signed-in publisher is always retained so a non-admin owner cannot
    lock themselves out. Department/role/user identities remain RuoYi subject
    IDs; Agent Platform only owns the authorization decision.
    """
    scope = request.publication_scope or (str(current["publication_scope"]) if current else "PERSONAL")
    supplied = request.publication_subjects
    selected = ([item.model_dump() for item in supplied] if supplied is not None
                else [dict(item) for item in (current or {}).get("subject_bindings", [])])
    if scope == "PERSONAL":
        selected = []
    elif scope == "OWNER_DEPT":
        departments = [item for item in selected if item.get("subject_type") == "DEPT"]
        if len(departments) != 1:
            raise ApiError(422, "DEPLOYMENT_PUBLICATION_DEPT_REQUIRED", "department scope requires exactly one RuoYi department")
        selected = departments
    elif scope == "SELECTED_SUBJECTS":
        if not selected:
            raise ApiError(422, "DEPLOYMENT_PUBLICATION_SUBJECT_REQUIRED", "selected scope requires at least one RuoYi user, role, or department")
    else:  # Pydantic normally rejects this; retained for non-HTTP callers.
        raise ApiError(422, "DEPLOYMENT_PUBLICATION_SCOPE_INVALID", "invalid deployment publication scope")

    bindings: list[dict[str, str]] = [{"subject_type": "USER", "subject_id": principal.external_user_id}]
    for item in selected:
        normalized = {"subject_type": str(item["subject_type"]), "subject_id": str(item["subject_id"]).strip()}
        if normalized["subject_id"] and normalized not in bindings:
            bindings.append(normalized)
    return scope, bindings


async def _current_publication_profile(principal: Principal, deployment_id: UUID) -> dict[str, Any] | None:
    if get_settings().storage_mode != "postgres":
        return _memory_deployment_publications.get((principal.tenant_id, deployment_id))
    session = await _tx(principal)
    try:
        profile = await session.scalar(select(DeploymentPublicationProfileRow).where(
            DeploymentPublicationProfileRow.tenant_id == principal.tenant_id,
            DeploymentPublicationProfileRow.deployment_id == deployment_id,
        ))
        if not profile:
            return None
        return {"publication_scope": profile.publication_scope, "subject_bindings": list(profile.subject_bindings or [])}
    finally:
        await _close_tx(session)


async def _persist_publication_profile(
    principal: Principal, deployment_id: UUID, scope: str, bindings: list[dict[str, str]],
) -> None:
    if get_settings().storage_mode != "postgres":
        _memory_deployment_publications[(principal.tenant_id, deployment_id)] = {
            "publication_scope": scope, "subject_bindings": bindings,
        }
        return
    session = await _tx(principal)
    try:
        profile = await session.scalar(select(DeploymentPublicationProfileRow).where(
            DeploymentPublicationProfileRow.tenant_id == principal.tenant_id,
            DeploymentPublicationProfileRow.deployment_id == deployment_id,
        ).with_for_update())
        if profile:
            prior_ids = [UUID(value) for value in (profile.generated_grant_ids or [])]
            if prior_ids:
                await session.execute(delete(ResourceGrantRow).where(
                    ResourceGrantRow.tenant_id == principal.tenant_id,
                    ResourceGrantRow.grant_id.in_(prior_ids),
                ))
        generated_ids: list[str] = []
        for subject in bindings:
            grant_id = uuid4()
            generated_ids.append(str(grant_id))
            session.add(ResourceGrantRow(
                grant_id=grant_id, tenant_id=principal.tenant_id,
                subject_type=subject["subject_type"], subject_id=subject["subject_id"],
                resource_type="DEPLOYMENT", resource_id=str(deployment_id),
                actions=["RUN", "VIEW"], effect="ALLOW", created_by=principal.external_user_id,
            ))
        if profile:
            profile.publication_scope = scope
            profile.subject_bindings = bindings
            profile.generated_grant_ids = generated_ids
            profile.updated_by = principal.external_user_id
        else:
            session.add(DeploymentPublicationProfileRow(
                profile_id=uuid4(), tenant_id=principal.tenant_id, deployment_id=deployment_id,
                publication_scope=scope, subject_bindings=bindings, generated_grant_ids=generated_ids,
                updated_by=principal.external_user_id,
            ))
    finally:
        await _close_tx(session, commit=True)


@router.post("/deployments/{deployment_id}/publish-configuration", response_model=PublishConfigurationResponse)
async def publish_configuration(
    deployment_id: UUID,
    request: PublishConfigurationRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_platform_admin),
) -> PublishConfigurationResponse:
    if not idempotency_key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required")
    control = get_control_plane_store()
    resolved = await control.resolve(deployment_id, principal)
    if request.base_revision_id and request.base_revision_id != resolved.revision.deployment_revision_id:
        raise ApiError(409, "CONFIGURATION_BASE_REVISION_CONFLICT", "the active Revision changed; refresh the configuration draft")
    current_profile = await _current_publication_profile(principal, deployment_id)
    scope, bindings = _resolve_publication_bindings(request, principal, current_profile)
    version, revision = await control.publish_configuration(
        deployment_id, request.specification, idempotency_key, principal
    )
    await _persist_publication_profile(principal, deployment_id, scope, bindings)
    if get_settings().storage_mode == "postgres":
        session = await _tx(principal)
        try:
            draft = await session.scalar(select(DeploymentConfigurationDraftRow).where(
                DeploymentConfigurationDraftRow.tenant_id == principal.tenant_id,
                DeploymentConfigurationDraftRow.deployment_id == deployment_id,
            ).with_for_update())
            if draft:
                await session.delete(draft)
        finally:
            await _close_tx(session, commit=True)
    else:
        _memory_drafts.pop((principal.tenant_id, deployment_id), None)
    response = PublishConfigurationResponse(
        agent_version_id=version.agent_version_id, agent_version_number=version.version_number,
        deployment_revision_id=revision.deployment_revision_id, revision_number=revision.revision_number,
    )
    await get_governance_store().record_audit(principal, "deployment.configuration.publish", "DEPLOYMENT", str(deployment_id), {
        **response.model_dump(mode="json"), "publication_scope": scope, "publication_subjects": bindings,
    })
    return response
