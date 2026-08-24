from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError
from app.db.models import ResourceDescriptorRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.governance.models import GrantAction, GrantEffect, ResourceGrantCreate, ResourceGrantRecord, SubjectType
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal


class PublicationSubject(BaseModel):
    subject_type: SubjectType
    subject_id: str = Field(min_length=1, max_length=128)


class ProductGovernance(BaseModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    owner_dept_id: str | None = Field(default=None, max_length=128)
    one_line_summary: str = Field(min_length=1, max_length=256)
    when_to_use: str = Field(min_length=1, max_length=4_000)
    when_not_to_use: str | None = Field(default=None, max_length=4_000)
    input_summary: str = Field(min_length=1, max_length=4_000)
    output_summary: str = Field(min_length=1, max_length=4_000)
    risk_level: str = Field(default="LOW", pattern=r"^(LOW|MEDIUM|HIGH)$")
    read_only: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)
    business_line: str | None = Field(default=None, max_length=128)
    data_involved: str | None = Field(default=None, max_length=4_000)
    audience: str | None = Field(default=None, max_length=4_000)
    usage_scenarios: str | None = Field(default=None, max_length=4_000)
    publication_scope: str = Field(default="PERSONAL", pattern=r"^(PERSONAL|OWNER_DEPT|SELECTED_SUBJECTS)$")
    publication_subjects: list[PublicationSubject] = Field(default_factory=list, max_length=100)


def resolve_publication_subjects(product: ProductGovernance) -> list[tuple[SubjectType, str, set[GrantAction]]]:
    subjects: list[tuple[SubjectType, str, set[GrantAction]]] = [
        (
            SubjectType.USER,
            product.owner_user_id,
            {GrantAction.VIEW, GrantAction.USE, GrantAction.EDIT, GrantAction.PUBLISH, GrantAction.MANAGE},
        )
    ]
    if product.publication_scope == "OWNER_DEPT":
        if not product.owner_dept_id:
            raise ApiError(422, "PUBLICATION_SCOPE_INVALID", "owner department is required for department scope")
        subjects.append((SubjectType.DEPT, product.owner_dept_id, {GrantAction.VIEW, GrantAction.USE}))
    elif product.publication_scope == "SELECTED_SUBJECTS":
        if not product.publication_subjects:
            raise ApiError(422, "PUBLICATION_SCOPE_INVALID", "at least one RuoYi subject is required")
        subjects.extend(
            (subject.subject_type, subject.subject_id, {GrantAction.VIEW, GrantAction.USE})
            for subject in product.publication_subjects
        )

    unique: dict[tuple[SubjectType, str], set[GrantAction]] = {}
    for subject_type, subject_id, actions in subjects:
        unique.setdefault((subject_type, subject_id), set()).update(actions)
    return [(kind, subject_id, actions) for (kind, subject_id), actions in unique.items()]


async def apply_product_governance(
    *,
    product: ProductGovernance,
    resource_type: str,
    resource_id: UUID,
    resource_version_id: UUID,
    source_type: str,
    source_ref: str | None,
    principal: Principal,
) -> list[ResourceGrantRecord]:
    subjects = resolve_publication_subjects(product)
    if get_settings().storage_mode == "postgres":
        values = {
            "owner_user_id": product.owner_user_id,
            "owner_dept_id": product.owner_dept_id,
            "source_type": source_type,
            "source_ref": source_ref,
            "usage_guidance": product.when_to_use,
            "one_line_summary": product.one_line_summary,
            "when_to_use": product.when_to_use,
            "when_not_to_use": product.when_not_to_use,
            "input_summary": product.input_summary,
            "output_summary": product.output_summary,
            "risk_level": product.risk_level,
            "read_only": product.read_only,
            "business_line": product.business_line,
            "data_involved": product.data_involved,
            "audience": product.audience,
            "usage_scenarios": product.usage_scenarios,
            "developer_user_ids": [],
            "publication_scope": product.publication_scope,
            "tags": product.tags,
            "lifecycle_status": "ACTIVE",
        }
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.scalar(select(ResourceDescriptorRow).where(
                    ResourceDescriptorRow.tenant_id == principal.tenant_id,
                    ResourceDescriptorRow.resource_type == resource_type,
                    ResourceDescriptorRow.resource_id == resource_id,
                ))
                if row is None:
                    session.add(ResourceDescriptorRow(
                        descriptor_id=uuid4(), tenant_id=principal.tenant_id,
                        resource_type=resource_type, resource_id=resource_id, **values,
                    ))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)

    governance = get_governance_store()
    grants: list[ResourceGrantRecord] = []
    for subject_type, subject_id, actions in subjects:
        grants.append(await governance.create_grant(ResourceGrantCreate(
            subject_type=subject_type,
            subject_id=subject_id,
            resource_type=resource_type,
            resource_id=str(resource_version_id),
            actions=actions,
            effect=GrantEffect.ALLOW,
        ), principal))
    return grants
