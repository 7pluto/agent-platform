from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import ResourceDefinitionRow, ResourceVersionRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.resources.registry_models import (
    ResourceDefinitionCreate,
    ResourceDefinitionRecord,
    ResourceType,
    ResourceVersionCreate,
    ResourceVersionRecord,
    ResourceVersionStatus,
)
from app.resources.registry_store import ResourceRegistryStore
from app.governance.store_factory import get_governance_store
from app.api.dependencies import ensure_resource_action, is_platform_admin


class PostgresResourceRegistryStore:
    async def create_definition(self, request: ResourceDefinitionCreate, principal: Principal) -> ResourceDefinitionRecord:
        ResourceRegistryStore._validate(request.resource_type, request.draft_config)
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                exists = await session.scalar(select(ResourceDefinitionRow.resource_id).where(ResourceDefinitionRow.tenant_id == principal.tenant_id, ResourceDefinitionRow.resource_type == request.resource_type.value, ResourceDefinitionRow.slug == request.slug))
                if exists:
                    raise ApiError(409, "RESOURCE_SLUG_EXISTS", "resource type and slug already exist")
                row = ResourceDefinitionRow(resource_id=uuid4(), tenant_id=principal.tenant_id, resource_type=request.resource_type.value, slug=request.slug, display_name=request.display_name, description=request.description, draft_config=request.draft_config, created_by=principal.external_user_id)
                session.add(row)
                await session.flush()
                return self._definition(row)

    async def list_definitions(self, principal: Principal, resource_type: ResourceType | None = None) -> list[ResourceDefinitionRecord]:
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                statement = select(ResourceDefinitionRow).where(ResourceDefinitionRow.tenant_id == principal.tenant_id)
                if resource_type:
                    statement = statement.where(ResourceDefinitionRow.resource_type == resource_type.value)
                rows = await session.scalars(statement.order_by(ResourceDefinitionRow.resource_type, ResourceDefinitionRow.display_name))
                return [self._definition(row) for row in rows.all()]

    async def create_version(self, resource_id: UUID, request: ResourceVersionCreate, principal: Principal) -> ResourceVersionRecord:
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                definition = await self._definition_row(session, resource_id, principal)
                kind = ResourceType(definition.resource_type)
                config = request.config or definition.draft_config
                ResourceRegistryStore._validate(kind, config)
                number = await session.scalar(select(func.max(ResourceVersionRow.version_number)).where(ResourceVersionRow.tenant_id == principal.tenant_id, ResourceVersionRow.resource_id == resource_id))
                row = ResourceVersionRow(resource_version_id=uuid4(), resource_id=resource_id, tenant_id=principal.tenant_id, resource_type=definition.resource_type, version_number=(number or 0) + 1, status=ResourceVersionStatus.DRAFT.value, config=config, content_hash=ResourceRegistryStore._hash(config), created_by=principal.external_user_id)
                session.add(row)
                await session.flush()
                return self._version(row)

    async def list_versions(self, resource_id: UUID, principal: Principal) -> list[ResourceVersionRecord]:
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                await self._definition_row(session, resource_id, principal)
                rows = await session.scalars(select(ResourceVersionRow).where(ResourceVersionRow.tenant_id == principal.tenant_id, ResourceVersionRow.resource_id == resource_id).order_by(ResourceVersionRow.version_number))
                return [self._version(row) for row in rows.all()]

    async def list_published_versions(self, principal: Principal, resource_type: ResourceType | None = None) -> list[ResourceVersionRecord]:
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                statement = select(ResourceVersionRow).where(ResourceVersionRow.tenant_id == principal.tenant_id, ResourceVersionRow.status == ResourceVersionStatus.PUBLISHED.value)
                if resource_type:
                    statement = statement.where(ResourceVersionRow.resource_type == resource_type.value)
                rows = await session.scalars(statement.order_by(ResourceVersionRow.resource_type, ResourceVersionRow.resource_id, ResourceVersionRow.version_number))
                candidates = [self._version(row) for row in rows.all()]
        if is_platform_admin(principal):
            return candidates
        visible: list[ResourceVersionRecord] = []
        for item in candidates:
            try:
                await ensure_resource_action(principal, "USE", item.resource_type.value, str(item.resource_version_id))
                visible.append(item)
            except ApiError:
                pass
        return visible

    async def get_version(self, resource_version_id: UUID, principal: Principal, published: bool = False) -> ResourceVersionRecord:
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                row = await self._version_row(session, resource_version_id, principal)
                if published and row.status != ResourceVersionStatus.PUBLISHED.value:
                    raise ApiError(409, "RESOURCE_VERSION_NOT_PUBLISHED", "resource version must be published")
                return self._version(row)

    async def publish_version(self, resource_version_id: UUID, principal: Principal) -> ResourceVersionRecord:
        async with self._session() as session:
            async with session.begin():
                await self._context(session, principal)
                row = await self._version_row(session, resource_version_id, principal, lock=True)
                if row.status != ResourceVersionStatus.DRAFT.value:
                    raise ApiError(409, "RESOURCE_VERSION_NOT_DRAFT", "only draft resource versions can be published")
                row.status = ResourceVersionStatus.PUBLISHED.value
                row.published_at = datetime.now(timezone.utc)
                return self._version(row)

    @staticmethod
    async def _context(session: AsyncSession, principal: Principal) -> None:
        await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)

    @staticmethod
    def _session():
        return get_session_factory()()

    @staticmethod
    async def _definition_row(session: AsyncSession, resource_id: UUID, principal: Principal) -> ResourceDefinitionRow:
        row = await session.get(ResourceDefinitionRow, resource_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        return row

    @staticmethod
    async def _version_row(session: AsyncSession, resource_version_id: UUID, principal: Principal, lock: bool = False) -> ResourceVersionRow:
        row = await (session.scalar(select(ResourceVersionRow).where(ResourceVersionRow.resource_version_id == resource_version_id).with_for_update()) if lock else session.get(ResourceVersionRow, resource_version_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource version was not found")
        return row

    @staticmethod
    def _definition(row: ResourceDefinitionRow) -> ResourceDefinitionRecord:
        return ResourceDefinitionRecord(resource_id=row.resource_id, tenant_id=row.tenant_id, resource_type=ResourceType(row.resource_type), slug=row.slug, display_name=row.display_name, description=row.description, draft_config=row.draft_config, created_by=row.created_by, created_at=row.created_at, updated_at=row.updated_at)

    @staticmethod
    def _version(row: ResourceVersionRow) -> ResourceVersionRecord:
        return ResourceVersionRecord(resource_version_id=row.resource_version_id, resource_id=row.resource_id, tenant_id=row.tenant_id, resource_type=ResourceType(row.resource_type), version_number=row.version_number, status=ResourceVersionStatus(row.status), config=row.config, content_hash=row.content_hash, created_by=row.created_by, created_at=row.created_at, published_at=row.published_at)
