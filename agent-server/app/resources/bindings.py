"""Provider discovery bindings; never accept a model-supplied external identity."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError
from app.db.models import ResourceExternalBindingRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.resources.registry_models import ExternalBindingStatus, ResourceExternalBindingRecord


class ExternalBindingService:
    def __init__(self) -> None:
        self._memory: dict[tuple[str, str, UUID, str, str], ResourceExternalBindingRecord] = {}

    async def register_discovered(
        self,
        *,
        provider: str,
        connection_resource_id: UUID,
        external_type: str,
        external_id: str,
        resource_id: UUID,
        principal: Principal,
    ) -> ResourceExternalBindingRecord:
        provider, external_type, external_id = provider.upper().strip(), external_type.upper().strip(), external_id.strip()
        if not provider or not external_type or not external_id:
            raise ApiError(422, "EXTERNAL_BINDING_INVALID", "provider, external type and discovered external id are required")
        key = (principal.tenant_id, provider, connection_resource_id, external_type, external_id)
        if get_settings().storage_mode != "postgres":
            existing = self._memory.get(key)
            if existing and existing.resource_id != resource_id:
                raise ApiError(409, "EXTERNAL_BINDING_ALREADY_MANAGED", "external capability is already bound to another resource")
            record = ResourceExternalBindingRecord(
                binding_id=existing.binding_id if existing else uuid4(), tenant_id=principal.tenant_id,
                provider=provider, connection_resource_id=connection_resource_id, external_type=external_type,
                external_id=external_id, resource_id=resource_id,
                status=ExternalBindingStatus.MANAGED, created_at=existing.created_at if existing else datetime.now(timezone.utc),
            )
            self._memory[key] = record
            return record
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.scalar(select(ResourceExternalBindingRow).where(
                    ResourceExternalBindingRow.tenant_id == principal.tenant_id,
                    ResourceExternalBindingRow.provider == provider,
                    ResourceExternalBindingRow.connection_resource_id == connection_resource_id,
                    ResourceExternalBindingRow.external_type == external_type,
                    ResourceExternalBindingRow.external_id == external_id,
                ))
                if row is not None and row.resource_id != resource_id:
                    raise ApiError(409, "EXTERNAL_BINDING_ALREADY_MANAGED", "external capability is already bound to another resource")
                if row is None:
                    row = ResourceExternalBindingRow(
                        binding_id=uuid4(), tenant_id=principal.tenant_id, provider=provider,
                        connection_resource_id=connection_resource_id, external_type=external_type,
                        external_id=external_id, resource_id=resource_id, status=ExternalBindingStatus.MANAGED.value,
                    )
                    session.add(row)
                    await session.flush()
                else:
                    row.status = ExternalBindingStatus.MANAGED.value
                    await session.flush()
                return ResourceExternalBindingRecord.model_validate(row, from_attributes=True)

    async def list_for_connection(self, connection_resource_id: UUID, principal: Principal) -> list[ResourceExternalBindingRecord]:
        if get_settings().storage_mode != "postgres":
            return [item for item in self._memory.values() if item.tenant_id == principal.tenant_id and item.connection_resource_id == connection_resource_id]
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = (await session.scalars(select(ResourceExternalBindingRow).where(
                    ResourceExternalBindingRow.tenant_id == principal.tenant_id,
                    ResourceExternalBindingRow.connection_resource_id == connection_resource_id,
                ))).all()
        return [ResourceExternalBindingRecord.model_validate(row, from_attributes=True) for row in rows]


_service = ExternalBindingService()


def get_external_binding_service() -> ExternalBindingService:
    return _service
