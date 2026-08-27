from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import ensure_resource_action, require_resource_developer
from app.core.errors import ApiError
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.resources.product_governance import ProductGovernance, PublicationSubject, apply_product_governance
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import (
    ResourceDefinitionCreate,
    ResourceType,
    ResourceVersionCreate,
    ResourceVersionRecord,
)


router = APIRouter(prefix="/developer/resources", tags=["developer-resources"])
store = get_resource_registry()


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
    if not request.skill_md.lstrip().startswith("#"):
        raise ApiError(422, "INVALID_SKILL_CONFIG", "SKILL.md must start with a Markdown heading")

    dependency_ids = [*request.tool_version_ids, *request.knowledge_version_ids]
    if len(dependency_ids) != len(set(dependency_ids)):
        raise ApiError(422, "SKILL_DEPENDENCY_DUPLICATED", "Skill dependencies must be unique")

    for version_id in request.tool_version_ids:
        dependency = await store.get_version(version_id, principal, published=True)
        if dependency.resource_type != ResourceType.TOOL:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "tool_version_ids may reference only published Tools")
        await ensure_resource_action(principal, "USE", ResourceType.TOOL.value, str(version_id))

    for version_id in request.knowledge_version_ids:
        dependency = await store.get_version(version_id, principal, published=True)
        if dependency.resource_type != ResourceType.KNOWLEDGE:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "knowledge_version_ids may reference only published Knowledge")
        await ensure_resource_action(principal, "USE", ResourceType.KNOWLEDGE.value, str(version_id))

    return await _publish(
        resource_type=ResourceType.SKILL,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        config={
            "skill_md": request.skill_md,
            "tool_version_ids": [str(value) for value in request.tool_version_ids],
            "knowledge_version_ids": [str(value) for value in request.knowledge_version_ids],
        },
        semantics=request,
        principal=principal,
        source_ref="skill-editor",
    )
