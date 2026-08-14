from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SubjectType(StrEnum):
    USER = "USER"
    ROLE = "ROLE"
    DEPT = "DEPT"


class GrantEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class GrantAction(StrEnum):
    VIEW = "VIEW"
    USE = "USE"
    EDIT = "EDIT"
    PUBLISH = "PUBLISH"
    MANAGE = "MANAGE"
    RUN = "RUN"


class ResourceGrantCreate(BaseModel):
    subject_type: SubjectType
    subject_id: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=128)
    actions: set[GrantAction] = Field(min_length=1)
    effect: GrantEffect = GrantEffect.ALLOW


class ResourceGrantRecord(ResourceGrantCreate):
    grant_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEventRecord(BaseModel):
    audit_event_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
