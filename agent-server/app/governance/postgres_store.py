from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select

from app.db.models import AuditEventRow, ResourceGrantRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.governance.models import AuditEventRecord, GrantEffect, ResourceGrantCreate, ResourceGrantRecord, SubjectType
from app.governance.store import GovernanceStore
from app.iam.models import Principal


class PostgresGovernanceStore:
    async def create_grant(self, request: ResourceGrantCreate, principal: Principal) -> ResourceGrantRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = ResourceGrantRow(
                    grant_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    subject_type=request.subject_type.value,
                    subject_id=request.subject_id,
                    resource_type=request.resource_type,
                    resource_id=request.resource_id,
                    actions=sorted(request.actions),
                    effect=request.effect.value,
                    created_by=principal.external_user_id,
                )
                session.add(row)
                await session.flush()
                return self._grant(row)

    async def list_grants(
        self, principal: Principal, resource_type: str | None = None, resource_id: str | None = None
    ) -> list[ResourceGrantRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                statement = select(ResourceGrantRow).where(ResourceGrantRow.tenant_id == principal.tenant_id)
                if resource_type:
                    statement = statement.where(ResourceGrantRow.resource_type == resource_type)
                if resource_id:
                    statement = statement.where(ResourceGrantRow.resource_id == resource_id)
                rows = await session.scalars(statement.order_by(ResourceGrantRow.created_at, ResourceGrantRow.grant_id))
                return [self._grant(row) for row in rows.all()]

    async def delete_grant(self, grant_id, principal: Principal) -> ResourceGrantRecord | None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.scalar(
                    select(ResourceGrantRow).where(
                        ResourceGrantRow.tenant_id == principal.tenant_id,
                        ResourceGrantRow.grant_id == grant_id,
                    )
                )
                if row is None:
                    return None
                record = self._grant(row)
                await session.execute(
                    delete(ResourceGrantRow).where(
                        ResourceGrantRow.tenant_id == principal.tenant_id,
                        ResourceGrantRow.grant_id == grant_id,
                    )
                )
                return record

    async def is_allowed(self, principal: Principal, action: str, resource_type: str, resource_id: str) -> bool:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(ResourceGrantRow).where(
                        ResourceGrantRow.tenant_id == principal.tenant_id,
                        ResourceGrantRow.resource_type == resource_type,
                        ResourceGrantRow.resource_id.in_((resource_id, "*")),
                    )
                )
                grants = [self._grant(row) for row in rows.all()]
                matching = [
                    grant
                    for grant in grants
                    if (action in grant.actions or "*" in grant.actions)
                    and GovernanceStore._subject_matches(grant, principal)
                ]
                if any(grant.effect == GrantEffect.DENY for grant in matching):
                    return False
                return any(grant.effect == GrantEffect.ALLOW for grant in matching)

    async def record_audit(
        self,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: str,
        data: dict | None = None,
    ) -> AuditEventRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = AuditEventRow(
                    audit_event_id=uuid4(),
                    tenant_id=principal.tenant_id,
                    actor_id=principal.external_user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    data=dict(data or {}),
                )
                session.add(row)
                await session.flush()
                return self._audit(row)

    async def list_audit(self, principal: Principal, limit: int = 100) -> list[AuditEventRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(AuditEventRow)
                    .where(AuditEventRow.tenant_id == principal.tenant_id)
                    .order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.audit_event_id.desc())
                    .limit(limit)
                )
                return [self._audit(row) for row in rows.all()]

    @staticmethod
    def _grant(row: ResourceGrantRow) -> ResourceGrantRecord:
        return ResourceGrantRecord(
            grant_id=row.grant_id,
            tenant_id=row.tenant_id,
            subject_type=SubjectType(row.subject_type),
            subject_id=row.subject_id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            actions=set(row.actions),
            effect=GrantEffect(row.effect),
            created_by=row.created_by,
            created_at=row.created_at,
        )

    @staticmethod
    def _audit(row: AuditEventRow) -> AuditEventRecord:
        return AuditEventRecord(
            audit_event_id=row.audit_event_id,
            tenant_id=row.tenant_id,
            actor_id=row.actor_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            data=row.data,
            occurred_at=row.occurred_at,
        )
