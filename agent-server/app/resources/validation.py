"""Tenant-scoped audit trail and publish gate for resource validation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select

from app.config import get_settings
from app.db.models import ResourceValidationRunRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.resources.registry_models import (
    ResourceValidationRunRecord,
    ResourceValidationStatus,
    ResourceValidationType,
)


_SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "password", "secret", "secret_ref", "token"}


def redact_validation_result(value: Any) -> Any:
    """Persist useful diagnostics without retaining credentials or raw payloads."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower().replace("-", "_") in _SENSITIVE_KEYS else redact_validation_result(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_validation_result(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:4_000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:4_000]


class ResourceValidationService:
    def __init__(self) -> None:
        self._memory: list[ResourceValidationRunRecord] = []

    async def record(
        self,
        resource_version_id: UUID,
        validation_type: ResourceValidationType,
        status: ResourceValidationStatus,
        result: dict[str, Any],
        principal: Principal,
        latency_ms: int | None = None,
    ) -> ResourceValidationRunRecord:
        record = ResourceValidationRunRecord(
            validation_run_id=uuid4(), tenant_id=principal.tenant_id, resource_version_id=resource_version_id,
            validation_type=validation_type, status=status, result=redact_validation_result(result),
            latency_ms=latency_ms, created_by=principal.external_user_id, created_at=datetime.now(timezone.utc),
        )
        if get_settings().storage_mode != "postgres":
            self._memory.append(record)
            return record
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                session.add(ResourceValidationRunRow(**record.model_dump()))
        return record

    async def list(self, resource_version_id: UUID, principal: Principal) -> list[ResourceValidationRunRecord]:
        if get_settings().storage_mode != "postgres":
            return [item for item in reversed(self._memory) if item.tenant_id == principal.tenant_id and item.resource_version_id == resource_version_id]
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = (await session.scalars(select(ResourceValidationRunRow).where(
                    ResourceValidationRunRow.tenant_id == principal.tenant_id,
                    ResourceValidationRunRow.resource_version_id == resource_version_id,
                ).order_by(desc(ResourceValidationRunRow.created_at)))).all()
        return [ResourceValidationRunRecord.model_validate(row, from_attributes=True) for row in rows]

    async def has_successful_validation(
        self,
        resource_version_id: UUID,
        principal: Principal,
        validation_type: ResourceValidationType = ResourceValidationType.VALIDATE,
    ) -> bool:
        return any(
            item.status == ResourceValidationStatus.SUCCEEDED and item.validation_type == validation_type
            for item in await self.list(resource_version_id, principal)
        )


_service = ResourceValidationService()


def get_resource_validation_service() -> ResourceValidationService:
    return _service
