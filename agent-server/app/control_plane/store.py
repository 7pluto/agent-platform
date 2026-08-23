from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from app.control_plane.models import (
    AgentDefinitionCreate,
    AgentDefinitionRecord,
    AgentVersionCreate,
    AgentVersionRecord,
    DeploymentCreate,
    DeploymentRecord,
    DeploymentRevisionCreate,
    DeploymentRevisionRecord,
    ResolvedDeployment,
    VersionStatus,
)
from app.core.errors import ApiError
from app.core.secrets import reject_secret_values
from app.control_plane.specification import validate_agent_specification
from app.control_plane.assembly import is_resource_assembly_v2, validate_agent_assembly
from app.control_plane.validation import get_agent_validation_service
from app.iam.models import Principal


class ControlPlaneStore:
    """Tenant-safe in-memory control plane for direct local development."""

    def __init__(self) -> None:
        self._definitions: dict[UUID, AgentDefinitionRecord] = {}
        self._versions: dict[UUID, AgentVersionRecord] = {}
        self._deployments: dict[UUID, DeploymentRecord] = {}
        self._revisions: dict[UUID, DeploymentRevisionRecord] = {}
        self._publish_results: dict[tuple[str, UUID, str], tuple[UUID, UUID]] = {}
        self._lock = asyncio.Lock()

    async def create_definition(self, request: AgentDefinitionCreate, principal: Principal) -> AgentDefinitionRecord:
        reject_secret_values(request.draft_spec, "agent.draft_spec")
        async with self._lock:
            if any(
                item.tenant_id == principal.tenant_id and item.slug == request.slug
                for item in self._definitions.values()
            ):
                raise ApiError(409, "AGENT_SLUG_EXISTS", "agent slug already exists")
            record = AgentDefinitionRecord(tenant_id=principal.tenant_id, **request.model_dump())
            self._definitions[record.agent_id] = record
            return record.model_copy(deep=True)

    async def list_definitions(self, principal: Principal) -> list[AgentDefinitionRecord]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in sorted(self._definitions.values(), key=lambda value: value.created_at)
                if item.tenant_id == principal.tenant_id
            ]

    async def list_versions(self, agent_id: UUID, principal: Principal) -> list[AgentVersionRecord]:
        async with self._lock:
            self._definition(agent_id, principal)
            return [
                item.model_copy(deep=True)
                for item in sorted(
                    self._versions.values(), key=lambda value: (value.version_number, value.agent_version_id)
                )
                if item.tenant_id == principal.tenant_id and item.agent_id == agent_id
            ]
    async def create_version(
        self, agent_id: UUID, request: AgentVersionCreate, principal: Principal
    ) -> AgentVersionRecord:
        async with self._lock:
            definition = self._definition(agent_id, principal)
            version_number = 1 + max(
                (item.version_number for item in self._versions.values() if item.agent_id == agent_id), default=0
            )
            specification = request.specification or definition.draft_spec
            reject_secret_values(specification, "agent.version.specification")
            validate_agent_specification(specification)
            record = AgentVersionRecord(
                tenant_id=principal.tenant_id,
                agent_id=agent_id,
                version_number=version_number,
                specification=specification,
                content_hash=self._content_hash(specification),
                created_by=principal.external_user_id,
            )
            self._versions[record.agent_version_id] = record
            return record.model_copy(deep=True)

    async def publish_version(self, agent_version_id: UUID, principal: Principal) -> AgentVersionRecord:
        async with self._lock:
            version = self._version(agent_version_id, principal)
            if version.status != VersionStatus.DRAFT:
                raise ApiError(409, "VERSION_NOT_DRAFT", "only draft versions can be published")
            if is_resource_assembly_v2(version.specification):
                await validate_agent_assembly(version.specification, principal)
            version = version.model_copy(
                update={"status": VersionStatus.PUBLISHED, "published_at": datetime.now(timezone.utc)}
            )
            self._versions[agent_version_id] = version
            return version.model_copy(deep=True)

    async def create_deployment(self, request: DeploymentCreate, principal: Principal) -> DeploymentRecord:
        async with self._lock:
            self._definition(request.agent_id, principal)
            if any(
                item.tenant_id == principal.tenant_id and item.name == request.name
                for item in self._deployments.values()
            ):
                raise ApiError(409, "DEPLOYMENT_NAME_EXISTS", "deployment name already exists")
            record = DeploymentRecord(tenant_id=principal.tenant_id, **request.model_dump())
            self._deployments[record.deployment_id] = record
            return record.model_copy(deep=True)

    async def list_deployments(self, principal: Principal) -> list[DeploymentRecord]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in sorted(self._deployments.values(), key=lambda value: (value.name, value.deployment_id))
                if item.tenant_id == principal.tenant_id
            ]

    async def list_revisions(
        self, deployment_id: UUID, principal: Principal
    ) -> list[DeploymentRevisionRecord]:
        async with self._lock:
            self._deployment(deployment_id, principal)
            return [
                item.model_copy(deep=True)
                for item in sorted(
                    self._revisions.values(), key=lambda value: (value.revision_number, value.deployment_revision_id)
                )
                if item.tenant_id == principal.tenant_id and item.deployment_id == deployment_id
            ]
    async def create_revision(
        self, deployment_id: UUID, request: DeploymentRevisionCreate, principal: Principal
    ) -> DeploymentRevisionRecord:
        reject_secret_values(request.overrides, "deployment.revision.overrides")
        async with self._lock:
            deployment = self._deployment(deployment_id, principal)
            version = self._version(request.agent_version_id, principal)
            if version.status != VersionStatus.PUBLISHED:
                raise ApiError(409, "VERSION_NOT_PUBLISHED", "deployment revisions require a published agent version")
            if version.agent_id != deployment.agent_id:
                raise ApiError(409, "VERSION_AGENT_MISMATCH", "version does not belong to the deployment agent")
            revision_number = 1 + max(
                (
                    item.revision_number
                    for item in self._revisions.values()
                    if item.deployment_id == deployment_id
                ),
                default=0,
            )
            record = DeploymentRevisionRecord(
                tenant_id=principal.tenant_id,
                deployment_id=deployment_id,
                agent_version_id=version.agent_version_id,
                revision_number=revision_number,
                overrides=request.overrides,
                created_by=principal.external_user_id,
            )
            self._revisions[record.deployment_revision_id] = record
            return record.model_copy(deep=True)

    async def activate_revision(
        self, deployment_id: UUID, revision_id: UUID, principal: Principal
    ) -> DeploymentRecord:
        async with self._lock:
            deployment = self._deployment(deployment_id, principal)
            revision = self._revision(revision_id, principal)
            if revision.deployment_id != deployment_id:
                raise ApiError(409, "REVISION_DEPLOYMENT_MISMATCH", "revision does not belong to deployment")
            updated = deployment.model_copy(
                update={"active_revision_id": revision_id, "updated_at": datetime.now(timezone.utc)}
            )
            self._deployments[deployment_id] = updated
            return updated.model_copy(deep=True)

    async def resolve(self, deployment_id: UUID, principal: Principal) -> ResolvedDeployment:
        async with self._lock:
            deployment = self._deployment(deployment_id, principal)
            if deployment.active_revision_id is None:
                raise ApiError(409, "DEPLOYMENT_NOT_ACTIVE", "deployment has no active revision")
            revision = self._revision(deployment.active_revision_id, principal)
            version = self._version(revision.agent_version_id, principal)
            if version.status != VersionStatus.PUBLISHED:
                raise ApiError(409, "VERSION_NOT_PUBLISHED", "active revision references an unpublished version")
            return ResolvedDeployment(
                deployment=deployment.model_copy(deep=True),
                revision=revision.model_copy(deep=True),
                agent_version=version.model_copy(deep=True),
            )

    async def publish_configuration(
        self, deployment_id: UUID, specification: dict, idempotency_key: str, principal: Principal
    ) -> tuple[AgentVersionRecord, DeploymentRevisionRecord]:
        """In-memory equivalent of the atomic production publication command."""
        reject_secret_values(specification, "agent.version.specification")
        validate_agent_specification(specification)
        if is_resource_assembly_v2(specification):
            await get_agent_validation_service().require_valid(specification, principal)
        key = (principal.external_user_id, deployment_id, idempotency_key)
        async with self._lock:
            previous = self._publish_results.get(key)
            if previous:
                return (
                    self._version(previous[0], principal).model_copy(deep=True),
                    self._revision(previous[1], principal).model_copy(deep=True),
                )
            deployment = self._deployment(deployment_id, principal)
            version_number = 1 + max(
                (item.version_number for item in self._versions.values() if item.agent_id == deployment.agent_id),
                default=0,
            )
            version = AgentVersionRecord(
                tenant_id=principal.tenant_id, agent_id=deployment.agent_id,
                version_number=version_number, status=VersionStatus.PUBLISHED,
                specification=specification, content_hash=self._content_hash(specification),
                created_by=principal.external_user_id, published_at=datetime.now(timezone.utc),
            )
            revision_number = 1 + max(
                (item.revision_number for item in self._revisions.values() if item.deployment_id == deployment_id),
                default=0,
            )
            revision = DeploymentRevisionRecord(
                tenant_id=principal.tenant_id, deployment_id=deployment_id,
                agent_version_id=version.agent_version_id, revision_number=revision_number,
                overrides={}, created_by=principal.external_user_id,
            )
            self._versions[version.agent_version_id] = version
            self._revisions[revision.deployment_revision_id] = revision
            self._deployments[deployment_id] = deployment.model_copy(update={
                "active_revision_id": revision.deployment_revision_id,
                "updated_at": datetime.now(timezone.utc),
            })
            self._publish_results[key] = (version.agent_version_id, revision.deployment_revision_id)
            return version.model_copy(deep=True), revision.model_copy(deep=True)

    def _definition(self, agent_id: UUID, principal: Principal) -> AgentDefinitionRecord:
        record = self._definitions.get(agent_id)
        if record is None or record.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "agent definition was not found")
        return record

    def _version(self, agent_version_id: UUID, principal: Principal) -> AgentVersionRecord:
        record = self._versions.get(agent_version_id)
        if record is None or record.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "agent version was not found")
        return record

    def _deployment(self, deployment_id: UUID, principal: Principal) -> DeploymentRecord:
        record = self._deployments.get(deployment_id)
        if record is None or record.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "deployment was not found")
        return record

    def _revision(self, revision_id: UUID, principal: Principal) -> DeploymentRevisionRecord:
        record = self._revisions.get(revision_id)
        if record is None or record.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "deployment revision was not found")
        return record

    @staticmethod
    def _content_hash(specification: dict) -> str:
        payload = json.dumps(specification, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
