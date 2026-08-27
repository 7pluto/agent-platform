from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import require_platform_admin_read
from app.control_plane.store_factory import get_control_plane_store
from app.core.errors import ApiError
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.store_factory import get_resource_store


router = APIRouter(prefix="/workbench/deployments", tags=["workbench-revision-history"])


class RevisionDependencySnapshot(BaseModel):
    version_id: UUID
    resource_id: UUID
    resource_type: str
    display_name: str
    version_number: int
    content_hash: str


class RevisionCapabilitySnapshot(BaseModel):
    version_id: UUID
    resource_id: UUID
    resource_type: str
    display_name: str
    version_number: int
    content_hash: str
    dependencies: list[RevisionDependencySnapshot] = Field(default_factory=list)


class RevisionPublicationSnapshot(BaseModel):
    available: bool = False
    scope: str | None = None
    subjects: list[dict[str, str]] = Field(default_factory=list)


class RevisionHistoryItem(BaseModel):
    revision_id: UUID
    revision_number: int
    agent_version_id: UUID
    agent_version_number: int
    created_by: str
    created_at: datetime
    active: bool
    capabilities: list[RevisionCapabilitySnapshot] = Field(default_factory=list)
    publication: RevisionPublicationSnapshot = Field(default_factory=RevisionPublicationSnapshot)


_FIELDS = (
    "model_version_id",
    "prompt_version_id",
    "memory_policy_version_id",
    "skill_version_ids",
    "tool_version_ids",
    "mcp_connection_version_ids",
    "knowledge_version_ids",
)


def _version_ids(specification: dict[str, Any]) -> list[UUID]:
    result: list[UUID] = []
    for field in _FIELDS:
        raw = specification.get(field)
        if raw is None:
            continue
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            try:
                identifier = UUID(str(value))
            except (TypeError, ValueError):
                continue
            if identifier not in result:
                result.append(identifier)
    return result


def _dependency_ids(config: dict[str, Any]) -> list[UUID]:
    result: list[UUID] = []
    for field in ("tool_version_ids", "knowledge_version_ids"):
        values = config.get(field, [])
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                identifier = UUID(str(value))
            except (TypeError, ValueError):
                continue
            if identifier not in result:
                result.append(identifier)
    return result


async def _resource_snapshot(
    version_id: UUID,
    principal: Principal,
    *,
    model_definitions: dict,
    resource_definitions: dict,
    include_dependencies: bool,
) -> RevisionCapabilitySnapshot:
    model_store = get_resource_store()
    registry = get_resource_registry()

    try:
        model = await model_store.get_model_version(version_id, principal)
    except ApiError as exc:
        if exc.code != "NOT_FOUND":
            raise
    else:
        definition = model_definitions.get(model.model_id)
        return RevisionCapabilitySnapshot(
            version_id=model.model_version_id,
            resource_id=model.model_id,
            resource_type="MODEL",
            display_name=definition.display_name if definition else f"Model {str(model.model_id)[:8]}",
            version_number=model.version_number,
            content_hash=model.content_hash,
        )

    try:
        version = await registry.get_version(version_id, principal)
    except ApiError as exc:
        if exc.code != "NOT_FOUND":
            raise
        # Keep deleted historical references visible instead of silently dropping
        # them from a Revision comparison.
        return RevisionCapabilitySnapshot(
            version_id=version_id,
            resource_id=version_id,
            resource_type="UNKNOWN",
            display_name=f"历史资源 {str(version_id)[:8]}",
            version_number=0,
            content_hash="",
        )

    definition = resource_definitions.get(version.resource_id)
    dependencies: list[RevisionDependencySnapshot] = []
    if include_dependencies:
        for dependency_id in _dependency_ids(version.config):
            dependency = await _resource_snapshot(
                dependency_id,
                principal,
                model_definitions=model_definitions,
                resource_definitions=resource_definitions,
                include_dependencies=False,
            )
            dependencies.append(RevisionDependencySnapshot(
                version_id=dependency.version_id,
                resource_id=dependency.resource_id,
                resource_type=dependency.resource_type,
                display_name=dependency.display_name,
                version_number=dependency.version_number,
                content_hash=dependency.content_hash,
            ))

    return RevisionCapabilitySnapshot(
        version_id=version.resource_version_id,
        resource_id=version.resource_id,
        resource_type=version.resource_type.value,
        display_name=definition.display_name if definition else f"{version.resource_type.value} {str(version.resource_id)[:8]}",
        version_number=version.version_number,
        content_hash=version.content_hash,
        dependencies=dependencies,
    )


async def _capability_snapshots(specification: dict[str, Any], principal: Principal) -> list[RevisionCapabilitySnapshot]:
    model_store = get_resource_store()
    registry = get_resource_registry()
    model_definitions = {item.model_id: item for item in await model_store.list_models(principal)}
    resource_definitions = {item.resource_id: item for item in await registry.list_definitions(principal)}
    return [
        await _resource_snapshot(
            version_id,
            principal,
            model_definitions=model_definitions,
            resource_definitions=resource_definitions,
            include_dependencies=True,
        )
        for version_id in _version_ids(specification)
    ]


async def _publication_snapshots(
    deployment_id: UUID,
    principal: Principal,
) -> dict[UUID, RevisionPublicationSnapshot]:
    # publish_configuration already records one immutable audit event containing
    # the Revision id and normalized RuoYi publication bindings. Reuse that
    # append-only history instead of adding another development-stage table.
    events = await get_governance_store().list_audit(principal, limit=2_000)
    snapshots: dict[UUID, RevisionPublicationSnapshot] = {}
    for event in events:
        if event.action != "deployment.configuration.publish":
            continue
        if event.resource_type != "DEPLOYMENT" or event.resource_id != str(deployment_id):
            continue
        raw_revision_id = event.data.get("deployment_revision_id")
        try:
            revision_id = UUID(str(raw_revision_id))
        except (TypeError, ValueError):
            continue
        raw_subjects = event.data.get("publication_subjects", [])
        subjects = [
            {"subject_type": str(item.get("subject_type", "")), "subject_id": str(item.get("subject_id", ""))}
            for item in raw_subjects
            if isinstance(item, dict) and item.get("subject_type") and item.get("subject_id")
        ] if isinstance(raw_subjects, list) else []
        snapshots[revision_id] = RevisionPublicationSnapshot(
            available=True,
            scope=str(event.data.get("publication_scope") or "PERSONAL"),
            subjects=subjects,
        )
    return snapshots


@router.get("/{deployment_id}/revision-history", response_model=list[RevisionHistoryItem])
async def deployment_revision_history(
    deployment_id: UUID,
    principal: Principal = Depends(require_platform_admin_read),
) -> list[RevisionHistoryItem]:
    control = get_control_plane_store()
    resolved = await control.resolve(deployment_id, principal)
    revisions = await control.list_revisions(deployment_id, principal)
    versions = {item.agent_version_id: item for item in await control.list_versions(resolved.deployment.agent_id, principal)}
    publication = await _publication_snapshots(deployment_id, principal)

    history: list[RevisionHistoryItem] = []
    for revision in sorted(revisions, key=lambda item: item.revision_number, reverse=True):
        version = versions.get(revision.agent_version_id)
        if version is None:
            continue
        history.append(RevisionHistoryItem(
            revision_id=revision.deployment_revision_id,
            revision_number=revision.revision_number,
            agent_version_id=version.agent_version_id,
            agent_version_number=version.version_number,
            created_by=revision.created_by,
            created_at=revision.created_at,
            active=revision.deployment_revision_id == resolved.deployment.active_revision_id,
            capabilities=await _capability_snapshots(version.specification, principal),
            publication=publication.get(revision.deployment_revision_id, RevisionPublicationSnapshot()),
        ))
    return history
