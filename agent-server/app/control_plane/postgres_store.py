from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.control_plane.store import ControlPlaneStore
from app.core.errors import ApiError
from app.core.secrets import reject_secret_values
from app.control_plane.specification import validate_agent_specification
from app.control_plane.assembly import is_resource_assembly_v2, validate_agent_assembly
from app.control_plane.validation import get_agent_validation_service
from app.db.models import AgentDefinitionRow, AgentVersionRow, DeploymentPublishIdempotencyRow, DeploymentRevisionRow, DeploymentRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal


class PostgresControlPlaneStore:
    """PostgreSQL control plane with tenant context set for every transaction."""

    async def create_definition(self, request: AgentDefinitionCreate, principal: Principal) -> AgentDefinitionRecord:
        reject_secret_values(request.draft_spec, "agent.draft_spec")
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                exists = await session.scalar(
                    select(AgentDefinitionRow.agent_id).where(
                        AgentDefinitionRow.tenant_id == principal.tenant_id,
                        AgentDefinitionRow.slug == request.slug,
                    )
                )
                if exists:
                    raise ApiError(409, "AGENT_SLUG_EXISTS", "agent slug already exists")
                row = AgentDefinitionRow(
                    agent_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    slug=request.slug,
                    display_name=request.display_name,
                    description=request.description,
                    draft_spec=request.draft_spec,
                )
                session.add(row)
                await session.flush()
                return self._definition(row)

    async def list_definitions(self, principal: Principal) -> list[AgentDefinitionRecord]:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(AgentDefinitionRow)
                    .where(AgentDefinitionRow.tenant_id == principal.tenant_id)
                    .order_by(AgentDefinitionRow.created_at, AgentDefinitionRow.agent_id)
                )
                return [self._definition(row) for row in rows.all()]

    async def list_versions(self, agent_id: UUID, principal: Principal) -> list[AgentVersionRecord]:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._get_definition(session, agent_id, principal)
                rows = await session.scalars(
                    select(AgentVersionRow)
                    .where(AgentVersionRow.tenant_id == principal.tenant_id, AgentVersionRow.agent_id == agent_id)
                    .order_by(AgentVersionRow.version_number, AgentVersionRow.agent_version_id)
                )
                return [self._version(row) for row in rows.all()]
    async def create_version(
        self, agent_id: UUID, request: AgentVersionCreate, principal: Principal
    ) -> AgentVersionRecord:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                definition = await self._get_definition(session, agent_id, principal)
                current = await session.scalar(
                    select(func.max(AgentVersionRow.version_number)).where(
                        AgentVersionRow.tenant_id == principal.tenant_id,
                        AgentVersionRow.agent_id == agent_id,
                    )
                )
                specification = request.specification or definition.draft_spec
                reject_secret_values(specification, "agent.version.specification")
                validate_agent_specification(specification)
                row = AgentVersionRow(
                    agent_version_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    agent_id=agent_id,
                    version_number=(current or 0) + 1,
                    status=VersionStatus.DRAFT.value,
                    specification=specification,
                    content_hash=ControlPlaneStore._content_hash(specification),
                    created_by=principal.external_user_id,
                )
                session.add(row)
                await session.flush()
                return self._version(row)

    async def publish_version(self, agent_version_id: UUID, principal: Principal) -> AgentVersionRecord:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await self._get_version(session, agent_version_id, principal, lock=True)
                if row.status != VersionStatus.DRAFT.value:
                    raise ApiError(409, "VERSION_NOT_DRAFT", "only draft versions can be published")
                if is_resource_assembly_v2(row.specification):
                    await validate_agent_assembly(row.specification, principal)
                row.status = VersionStatus.PUBLISHED.value
                row.published_at = datetime.now(timezone.utc)
                return self._version(row)

    async def create_deployment(self, request: DeploymentCreate, principal: Principal) -> DeploymentRecord:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._get_definition(session, request.agent_id, principal)
                exists = await session.scalar(
                    select(DeploymentRow.deployment_id).where(
                        DeploymentRow.tenant_id == principal.tenant_id,
                        DeploymentRow.name == request.name,
                    )
                )
                if exists:
                    raise ApiError(409, "DEPLOYMENT_NAME_EXISTS", "deployment name already exists")
                row = DeploymentRow(
                    deployment_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    agent_id=request.agent_id,
                    name=request.name,
                    description=request.description,
                )
                session.add(row)
                await session.flush()
                return self._deployment(row)

    async def list_deployments(self, principal: Principal) -> list[DeploymentRecord]:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(DeploymentRow)
                    .where(DeploymentRow.tenant_id == principal.tenant_id)
                    .order_by(DeploymentRow.name, DeploymentRow.deployment_id)
                )
                return [self._deployment(row) for row in rows.all()]

    async def list_revisions(
        self, deployment_id: UUID, principal: Principal
    ) -> list[DeploymentRevisionRecord]:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._get_deployment(session, deployment_id, principal)
                rows = await session.scalars(
                    select(DeploymentRevisionRow)
                    .where(
                        DeploymentRevisionRow.tenant_id == principal.tenant_id,
                        DeploymentRevisionRow.deployment_id == deployment_id,
                    )
                    .order_by(DeploymentRevisionRow.revision_number, DeploymentRevisionRow.deployment_revision_id)
                )
                return [self._revision(row) for row in rows.all()]
    async def create_revision(
        self, deployment_id: UUID, request: DeploymentRevisionCreate, principal: Principal
    ) -> DeploymentRevisionRecord:
        reject_secret_values(request.overrides, "deployment.revision.overrides")
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                deployment = await self._get_deployment(session, deployment_id, principal)
                version = await self._get_version(session, request.agent_version_id, principal)
                if version.status != VersionStatus.PUBLISHED.value:
                    raise ApiError(409, "VERSION_NOT_PUBLISHED", "deployment revisions require a published agent version")
                if version.agent_id != deployment.agent_id:
                    raise ApiError(409, "VERSION_AGENT_MISMATCH", "version does not belong to the deployment agent")
                current = await session.scalar(
                    select(func.max(DeploymentRevisionRow.revision_number)).where(
                        DeploymentRevisionRow.tenant_id == principal.tenant_id,
                        DeploymentRevisionRow.deployment_id == deployment_id,
                    )
                )
                row = DeploymentRevisionRow(
                    deployment_revision_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    deployment_id=deployment_id,
                    agent_version_id=version.agent_version_id,
                    revision_number=(current or 0) + 1,
                    overrides=request.overrides,
                    created_by=principal.external_user_id,
                )
                session.add(row)
                await session.flush()
                return self._revision(row)

    async def activate_revision(
        self, deployment_id: UUID, revision_id: UUID, principal: Principal
    ) -> DeploymentRecord:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                deployment = await self._get_deployment(session, deployment_id, principal, lock=True)
                revision = await self._get_revision(session, revision_id, principal)
                if revision.deployment_id != deployment_id:
                    raise ApiError(409, "REVISION_DEPLOYMENT_MISMATCH", "revision does not belong to deployment")
                deployment.active_revision_id = revision_id
                return self._deployment(deployment)

    async def resolve(self, deployment_id: UUID, principal: Principal) -> ResolvedDeployment:
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                deployment = await self._get_deployment(session, deployment_id, principal)
                if deployment.active_revision_id is None:
                    raise ApiError(409, "DEPLOYMENT_NOT_ACTIVE", "deployment has no active revision")
                revision = await self._get_revision(session, deployment.active_revision_id, principal)
                version = await self._get_version(session, revision.agent_version_id, principal)
                if version.status != VersionStatus.PUBLISHED.value:
                    raise ApiError(409, "VERSION_NOT_PUBLISHED", "active revision references an unpublished version")
                return ResolvedDeployment(
                    deployment=self._deployment(deployment),
                    revision=self._revision(revision),
                    agent_version=self._version(version),
                )

    async def publish_configuration(
        self, deployment_id: UUID, specification: dict, idempotency_key: str, principal: Principal
    ) -> tuple[AgentVersionRecord, DeploymentRevisionRecord]:
        """Atomically version, publish, revise and activate one Deployment."""
        reject_secret_values(specification, "agent.version.specification")
        validate_agent_specification(specification)
        await get_agent_validation_service().require_valid(specification, principal)
        async with self._session(principal) as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                # Serialize configuration publication per deployment before checking
                # idempotency. Concurrent retries must observe the first committed
                # result instead of racing into a second immutable version.
                deployment = await self._get_deployment(session, deployment_id, principal, lock=True)
                existing = await session.scalar(select(DeploymentPublishIdempotencyRow).where(
                    DeploymentPublishIdempotencyRow.tenant_id == principal.tenant_id,
                    DeploymentPublishIdempotencyRow.user_id == principal.external_user_id,
                    DeploymentPublishIdempotencyRow.deployment_id == deployment_id,
                    DeploymentPublishIdempotencyRow.idempotency_key == idempotency_key,
                ))
                if existing:
                    version = await self._get_version(session, UUID(existing.response["agent_version_id"]), principal)
                    revision = await self._get_revision(session, UUID(existing.response["deployment_revision_id"]), principal)
                    return self._version(version), self._revision(revision)
                version_number = await session.scalar(select(func.max(AgentVersionRow.version_number)).where(AgentVersionRow.tenant_id == principal.tenant_id, AgentVersionRow.agent_id == deployment.agent_id))
                version = AgentVersionRow(agent_version_id=uuid4(), tenant_id=principal.tenant_id, agent_id=deployment.agent_id, version_number=(version_number or 0) + 1, status=VersionStatus.PUBLISHED.value, specification=specification, content_hash=ControlPlaneStore._content_hash(specification), created_by=principal.external_user_id, published_at=datetime.now(timezone.utc))
                session.add(version)
                await session.flush()
                revision_number = await session.scalar(select(func.max(DeploymentRevisionRow.revision_number)).where(DeploymentRevisionRow.tenant_id == principal.tenant_id, DeploymentRevisionRow.deployment_id == deployment_id))
                revision = DeploymentRevisionRow(deployment_revision_id=uuid4(), tenant_id=principal.tenant_id, deployment_id=deployment_id, agent_version_id=version.agent_version_id, revision_number=(revision_number or 0) + 1, overrides={}, created_by=principal.external_user_id)
                session.add(revision)
                await session.flush()
                deployment.active_revision_id = revision.deployment_revision_id
                session.add(DeploymentPublishIdempotencyRow(
                    record_id=uuid4(), tenant_id=principal.tenant_id,
                    user_id=principal.external_user_id, deployment_id=deployment_id,
                    idempotency_key=idempotency_key,
                    response={
                        "agent_version_id": str(version.agent_version_id),
                        "agent_version_number": version.version_number,
                        "deployment_revision_id": str(revision.deployment_revision_id),
                        "revision_number": revision.revision_number,
                    },
                ))
                return self._version(version), self._revision(revision)

    @staticmethod
    def _session(principal: Principal):
        class TenantSession:
            async def __aenter__(self):
                self._session = get_session_factory()()
                session = await self._session.__aenter__()
                return session

            async def __aexit__(self, exc_type, exc, traceback):
                await self._session.__aexit__(exc_type, exc, traceback)

        return TenantSession()

    async def _get_definition(
        self, session: AsyncSession, agent_id: UUID, principal: Principal
    ) -> AgentDefinitionRow:
        row = await session.get(AgentDefinitionRow, agent_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "agent definition was not found")
        return row

    async def _get_version(
        self, session: AsyncSession, agent_version_id: UUID, principal: Principal, lock: bool = False
    ) -> AgentVersionRow:
        if lock:
            row = await session.scalar(
                select(AgentVersionRow).where(AgentVersionRow.agent_version_id == agent_version_id).with_for_update()
            )
        else:
            row = await session.get(AgentVersionRow, agent_version_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "agent version was not found")
        return row

    async def _get_deployment(
        self, session: AsyncSession, deployment_id: UUID, principal: Principal, lock: bool = False
    ) -> DeploymentRow:
        if lock:
            row = await session.scalar(
                select(DeploymentRow).where(DeploymentRow.deployment_id == deployment_id).with_for_update()
            )
        else:
            row = await session.get(DeploymentRow, deployment_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "deployment was not found")
        return row

    async def _get_revision(
        self, session: AsyncSession, revision_id: UUID, principal: Principal
    ) -> DeploymentRevisionRow:
        row = await session.get(DeploymentRevisionRow, revision_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "deployment revision was not found")
        return row

    @staticmethod
    def _definition(row: AgentDefinitionRow) -> AgentDefinitionRecord:
        return AgentDefinitionRecord(
            agent_id=row.agent_id,
            tenant_id=row.tenant_id,
            slug=row.slug,
            display_name=row.display_name,
            description=row.description,
            draft_spec=row.draft_spec,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _version(row: AgentVersionRow) -> AgentVersionRecord:
        return AgentVersionRecord(
            agent_version_id=row.agent_version_id,
            tenant_id=row.tenant_id,
            agent_id=row.agent_id,
            version_number=row.version_number,
            status=VersionStatus(row.status),
            specification=row.specification,
            content_hash=row.content_hash,
            created_by=row.created_by,
            created_at=row.created_at,
            published_at=row.published_at,
        )

    @staticmethod
    def _deployment(row: DeploymentRow) -> DeploymentRecord:
        return DeploymentRecord(
            deployment_id=row.deployment_id,
            tenant_id=row.tenant_id,
            agent_id=row.agent_id,
            name=row.name,
            description=row.description,
            active_revision_id=row.active_revision_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _revision(row: DeploymentRevisionRow) -> DeploymentRevisionRecord:
        return DeploymentRevisionRecord(
            deployment_revision_id=row.deployment_revision_id,
            tenant_id=row.tenant_id,
            deployment_id=row.deployment_id,
            agent_version_id=row.agent_version_id,
            revision_number=row.revision_number,
            overrides=row.overrides,
            created_by=row.created_by,
            created_at=row.created_at,
        )
