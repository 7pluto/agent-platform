from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class AgentDefinitionCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4_000)
    draft_spec: dict[str, Any] = Field(default_factory=dict)


class AgentDefinitionRecord(AgentDefinitionCreate):
    agent_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentVersionCreate(BaseModel):
    specification: dict[str, Any] = Field(default_factory=dict)


class AgentVersionRecord(BaseModel):
    agent_version_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    agent_id: UUID
    version_number: int
    status: VersionStatus = VersionStatus.DRAFT
    specification: dict[str, Any]
    content_hash: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None


class DeploymentCreate(BaseModel):
    agent_id: UUID
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    description: str | None = Field(default=None, max_length=4_000)


class DeploymentRecord(DeploymentCreate):
    deployment_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    active_revision_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeploymentRevisionCreate(BaseModel):
    agent_version_id: UUID
    overrides: dict[str, Any] = Field(default_factory=dict)


class DeploymentRevisionRecord(BaseModel):
    deployment_revision_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    deployment_id: UUID
    agent_version_id: UUID
    revision_number: int
    overrides: dict[str, Any]
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResolvedDeployment(BaseModel):
    deployment: DeploymentRecord
    revision: DeploymentRevisionRecord
    agent_version: AgentVersionRecord


class ListPage(BaseModel):
    items: list[AgentDefinitionRecord]