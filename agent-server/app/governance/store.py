from __future__ import annotations

import asyncio
from uuid import UUID

from app.governance.models import AuditEventRecord, GrantEffect, ResourceGrantCreate, ResourceGrantRecord, SubjectType
from app.iam.models import Principal


class GovernanceStore:
    """Tenant-local grants and append-only audit events for development mode."""

    def __init__(self) -> None:
        self._grants: dict[UUID, ResourceGrantRecord] = {}
        self._audit: list[AuditEventRecord] = []
        self._lock = asyncio.Lock()

    async def create_grant(self, request: ResourceGrantCreate, principal: Principal) -> ResourceGrantRecord:
        async with self._lock:
            record = ResourceGrantRecord(
                tenant_id=principal.tenant_id,
                created_by=principal.external_user_id,
                **request.model_dump(),
            )
            self._grants[record.grant_id] = record
            return record.model_copy(deep=True)

    async def list_grants(
        self, principal: Principal, resource_type: str | None = None, resource_id: str | None = None
    ) -> list[ResourceGrantRecord]:
        async with self._lock:
            return [
                grant.model_copy(deep=True)
                for grant in self._grants.values()
                if grant.tenant_id == principal.tenant_id
                and (resource_type is None or grant.resource_type == resource_type)
                and (resource_id is None or grant.resource_id == resource_id)
            ]

    async def delete_grant(self, grant_id: UUID, principal: Principal) -> ResourceGrantRecord | None:
        async with self._lock:
            record = self._grants.get(grant_id)
            if record is None or record.tenant_id != principal.tenant_id:
                return None
            del self._grants[grant_id]
            return record.model_copy(deep=True)

    async def is_allowed(self, principal: Principal, action: str, resource_type: str, resource_id: str) -> bool:
        async with self._lock:
            grants = [
                grant
                for grant in self._grants.values()
                if grant.tenant_id == principal.tenant_id
                and grant.resource_type == resource_type
                and grant.resource_id in (resource_id, "*")
                and (action in grant.actions or "*" in grant.actions)
                and self._subject_matches(grant, principal)
            ]
            if any(grant.effect == GrantEffect.DENY for grant in grants):
                return False
            return any(grant.effect == GrantEffect.ALLOW for grant in grants)

    async def record_audit(
        self,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: str,
        data: dict | None = None,
    ) -> AuditEventRecord:
        async with self._lock:
            event = AuditEventRecord(
                tenant_id=principal.tenant_id,
                actor_id=principal.external_user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                data=dict(data or {}),
            )
            self._audit.append(event)
            return event.model_copy(deep=True)

    async def list_audit(self, principal: Principal, limit: int = 100) -> list[AuditEventRecord]:
        async with self._lock:
            return [
                event.model_copy(deep=True)
                for event in reversed(self._audit)
                if event.tenant_id == principal.tenant_id
            ][:limit]

    @staticmethod
    def _subject_matches(grant: ResourceGrantRecord, principal: Principal) -> bool:
        if grant.subject_type == SubjectType.USER:
            return grant.subject_id == principal.external_user_id
        if grant.subject_type == SubjectType.ROLE:
            return grant.subject_id in principal.role_codes
        return grant.subject_id in principal.dept_ids
