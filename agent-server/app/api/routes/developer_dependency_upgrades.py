from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import ensure_resource_action, require_resource_developer_read
from app.api.routes.developer_resources import _owned_definition, store
from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.registry_models import ResourceType, ResourceVersionRecord, ResourceVersionStatus


router = APIRouter(prefix="/developer/resources", tags=["developer-resource-dependencies"])


class DependencyVersionSnapshot(BaseModel):
    version_id: UUID
    version_number: int
    content_hash: str
    config_preview: dict[str, Any] = Field(default_factory=dict)


class DependencyUpgradeItem(BaseModel):
    dependency_type: Literal["TOOL", "KNOWLEDGE"]
    resource_id: UUID
    display_name: str
    current: DependencyVersionSnapshot
    latest: DependencyVersionSnapshot
    upgrade_available: bool
    upgrade_allowed: bool
    changed_fields: list[str] = Field(default_factory=list)
    message: str


class SkillDependencyUpgradeReport(BaseModel):
    skill_resource_id: UUID
    skill_version_id: UUID
    skill_version_number: int
    based_on_draft: bool
    dependencies: list[DependencyUpgradeItem] = Field(default_factory=list)
    upgrades_available: int = 0


_TOOL_PREVIEW_KEYS = ("kind", "native_name", "tool_name", "description", "input_schema", "output_schema")
_KNOWLEDGE_PREVIEW_KEYS = (
    "provider",
    "external_dataset_id",
    "embedding_model_version_id",
    "search_path",
    "method",
    "response_mapping",
    "top_k",
)


def _preview(resource_type: ResourceType, config: dict) -> dict[str, Any]:
    keys = _TOOL_PREVIEW_KEYS if resource_type == ResourceType.TOOL else _KNOWLEDGE_PREVIEW_KEYS
    return {key: config[key] for key in keys if key in config}


def _changed_fields(current: dict, latest: dict) -> list[str]:
    keys = set(current) | set(latest)
    return sorted(key for key in keys if current.get(key) != latest.get(key))


def _snapshot(version: ResourceVersionRecord) -> DependencyVersionSnapshot:
    return DependencyVersionSnapshot(
        version_id=version.resource_version_id,
        version_number=version.version_number,
        content_hash=version.content_hash,
        config_preview=_preview(version.resource_type, version.config),
    )


async def _dependency_item(
    *,
    version_id: UUID,
    expected_type: ResourceType,
    definitions: dict[UUID, str],
    principal: Principal,
) -> DependencyUpgradeItem:
    current = await store.get_version(version_id, principal, published=True)
    if current.resource_type != expected_type:
        raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", f"Skill dependency {version_id} is not {expected_type.value}")

    published = [
        version
        for version in await store.list_versions(current.resource_id, principal)
        if version.status == ResourceVersionStatus.PUBLISHED
    ]
    if not published:
        raise ApiError(409, "DEPENDENCY_HAS_NO_PUBLISHED_VERSION", "Skill dependency has no published version")
    latest = max(published, key=lambda item: item.version_number)

    allowed = True
    try:
        await ensure_resource_action(principal, "USE", expected_type.value, str(latest.resource_version_id))
    except ApiError as exc:
        if exc.code != "RESOURCE_FORBIDDEN":
            raise
        allowed = False

    current_preview = _preview(expected_type, current.config)
    latest_preview = _preview(expected_type, latest.config)
    changed = _changed_fields(current_preview, latest_preview)
    available = latest.version_number > current.version_number
    if not available:
        message = "已锁定最新已发布版本"
    elif not allowed:
        message = f"已有 V{latest.version_number}，但当前 RuoYi 身份没有 USE 权限"
    else:
        message = f"可从 V{current.version_number} 升级到 V{latest.version_number}"

    return DependencyUpgradeItem(
        dependency_type=expected_type.value,
        resource_id=current.resource_id,
        display_name=definitions.get(current.resource_id, expected_type.value),
        current=_snapshot(current),
        latest=_snapshot(latest),
        upgrade_available=available,
        upgrade_allowed=allowed,
        changed_fields=changed,
        message=message,
    )


@router.get("/{resource_id}/dependency-upgrades", response_model=SkillDependencyUpgradeReport)
async def skill_dependency_upgrades(
    resource_id: UUID,
    principal: Principal = Depends(require_resource_developer_read),
) -> SkillDependencyUpgradeReport:
    definition, _ = await _owned_definition(resource_id, principal)
    if definition.resource_type != ResourceType.SKILL:
        raise ApiError(409, "DEPENDENCY_UPGRADE_UNSUPPORTED", "dependency upgrades are available only for Skill resources")

    versions = sorted(await store.list_versions(resource_id, principal), key=lambda item: item.version_number, reverse=True)
    draft = next((item for item in versions if item.status == ResourceVersionStatus.DRAFT), None)
    published = next((item for item in versions if item.status == ResourceVersionStatus.PUBLISHED), None)
    base = draft or published
    if base is None:
        raise ApiError(409, "RESOURCE_NOT_PUBLISHED", "Skill has no version to analyze")

    definitions = {item.resource_id: item.display_name for item in await store.list_definitions(principal)}
    dependencies: list[DependencyUpgradeItem] = []

    for raw in base.config.get("tool_version_ids", []):
        try:
            version_id = UUID(str(raw))
        except ValueError as exc:
            raise ApiError(422, "INVALID_SKILL_CONFIG", "tool_version_ids must contain UUIDs") from exc
        dependencies.append(await _dependency_item(
            version_id=version_id,
            expected_type=ResourceType.TOOL,
            definitions=definitions,
            principal=principal,
        ))

    for raw in base.config.get("knowledge_version_ids", []):
        try:
            version_id = UUID(str(raw))
        except ValueError as exc:
            raise ApiError(422, "INVALID_SKILL_CONFIG", "knowledge_version_ids must contain UUIDs") from exc
        dependencies.append(await _dependency_item(
            version_id=version_id,
            expected_type=ResourceType.KNOWLEDGE,
            definitions=definitions,
            principal=principal,
        ))

    return SkillDependencyUpgradeReport(
        skill_resource_id=resource_id,
        skill_version_id=base.resource_version_id,
        skill_version_number=base.version_number,
        based_on_draft=base.status == ResourceVersionStatus.DRAFT,
        dependencies=dependencies,
        upgrades_available=sum(1 for item in dependencies if item.upgrade_available and item.upgrade_allowed),
    )
