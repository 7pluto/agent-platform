from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
try:  # Production image installs pgvector; keep unit-only imports lightweight.
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - exercised by minimal local test envs
    def Vector(_: int):
        return Text


class Base(DeclarativeBase):
    pass


class TenantRow(Base):
    __tablename__ = "platform_tenant"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    external_org_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunRow(Base):
    __tablename__ = "platform_run"
    __table_args__ = (
        Index(
            "uq_platform_run_active_thread",
            "tenant_id",
            "thread_id",
            unique=True,
            postgresql_where=text(
                "status IN ('RUNNING', 'CANCEL_REQUESTED')"
            ),
        ),
        Index("ix_platform_run_tenant_status", "tenant_id", "status"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    execution_manifest: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEventRow(Base):
    __tablename__ = "platform_run_event"
    __table_args__ = (UniqueConstraint("event_id", name="uq_platform_run_event_event_id"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_run.run_id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class RunIdempotencyRow(Base):
    __tablename__ = "platform_run_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "deployment_id", "idempotency_key", name="uq_platform_run_idempotency"
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ThreadLeaseRow(Base):
    __tablename__ = "platform_thread_lease"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    active_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RunSchedulerQueueRow(Base):
    __tablename__ = "platform_run_scheduler_queue"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_run.run_id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempt: Mapped[int] = mapped_column(nullable=False, server_default="0")
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
class AgentDefinitionRow(Base):
    __tablename__ = "platform_agent_definition"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_platform_agent_definition_slug"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    draft_spec: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentVersionRow(Base):
    __tablename__ = "platform_agent_version"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "version_number", name="uq_platform_agent_version_number"),
        Index("ix_platform_agent_version_tenant_agent", "tenant_id", "agent_id"),
    )

    agent_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_agent_definition.agent_id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    specification: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeploymentRow(Base):
    __tablename__ = "platform_deployment"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_platform_deployment_name"),)

    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_agent_definition.agent_id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeploymentPublicationProfileRow(Base):
    """The current audience contract for a deployed Agent.

    Revisions keep the assembled capabilities immutable.  The publication
    profile is deliberately separate because it controls who may *run* the
    active deployment, and needs to be changed without exposing any secret or
    resource configuration.
    """

    __tablename__ = "platform_deployment_publication_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "deployment_id", name="uq_platform_deployment_publication_profile"),
        Index("ix_platform_deployment_publication_profile_tenant", "tenant_id"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_deployment.deployment_id", ondelete="CASCADE"), nullable=False
    )
    publication_scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PERSONAL")
    subject_bindings: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)
    generated_grant_ids: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeploymentRevisionRow(Base):
    __tablename__ = "platform_deployment_revision"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "deployment_id", "revision_number", name="uq_platform_deployment_revision_number"
        ),
        Index("ix_platform_deployment_revision_tenant_deployment", "tenant_id", "deployment_id"),
    )

    deployment_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_deployment.deployment_id", ondelete="CASCADE"), nullable=False
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_agent_version.agent_version_id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(nullable=False)
    overrides: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class ResourceGrantRow(Base):
    __tablename__ = "platform_resource_grant"
    __table_args__ = (
        Index("ix_platform_resource_grant_lookup", "tenant_id", "resource_type", "resource_id"),
    )

    grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actions: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    effect: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEventRow(Base):
    __tablename__ = "platform_audit_event"
    __table_args__ = (Index("ix_platform_audit_event_tenant_time", "tenant_id", "occurred_at"),)

    audit_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class ConversationRow(Base):
    __tablename__ = "platform_conversation"

    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationThreadRow(Base):
    __tablename__ = "platform_conversation_thread"

    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_conversation.conversation_id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessageRow(Base):
    __tablename__ = "platform_conversation_message"
    __table_args__ = (
        UniqueConstraint("tenant_id", "thread_id", "source_run_id", "role", name="uq_platform_conversation_message_run_role"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_conversation_thread.thread_id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class ModelDefinitionRow(Base):
    __tablename__ = "platform_model_definition"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_platform_model_definition_slug"),)

    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelVersionRow(Base):
    __tablename__ = "platform_model_version"
    __table_args__ = (UniqueConstraint("tenant_id", "model_id", "version_number", name="uq_platform_model_version_number"),)

    model_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_model_definition.model_id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    availability: Mapped[str] = mapped_column(String(32), nullable=False, server_default="UNKNOWN")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_error: Mapped[str | None] = mapped_column(Text)


class ResourceDefinitionRow(Base):
    """Tenant-owned AI capability registry entry."""

    __tablename__ = "platform_resource_definition"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "slug", name="uq_platform_resource_definition_slug"),
        Index("ix_platform_resource_definition_tenant_type", "tenant_id", "resource_type"),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    draft_config: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResourceDescriptorRow(Base):
    """Mutable product metadata over immutable resource definitions/versions.

    It intentionally has no FK: Models still use their legacy definition table,
    while every other capability uses ``platform_resource_definition``.
    """

    __tablename__ = "platform_resource_descriptor"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_platform_resource_descriptor_target"),
        Index("ix_platform_resource_descriptor_tenant_type", "tenant_id", "resource_type"),
    )

    descriptor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_dept_id: Mapped[str | None] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PLATFORM_NATIVE")
    source_ref: Mapped[str | None] = mapped_column(String(256))
    usage_guidance: Mapped[str | None] = mapped_column(Text)
    one_line_summary: Mapped[str | None] = mapped_column(String(256))
    when_to_use: Mapped[str | None] = mapped_column(Text)
    when_not_to_use: Mapped[str | None] = mapped_column(Text)
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, server_default="LOW")
    read_only: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    business_line: Mapped[str | None] = mapped_column(String(128))
    data_involved: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str | None] = mapped_column(Text)
    usage_scenarios: Mapped[str | None] = mapped_column(Text)
    developer_user_ids: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)
    publication_scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PERSONAL")
    tags: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResourceVersionRow(Base):
    __tablename__ = "platform_resource_version"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_id", "version_number", name="uq_platform_resource_version_number"),
        Index("ix_platform_resource_version_tenant_resource", "tenant_id", "resource_id"),
    )

    resource_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_resource_definition.resource_id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResourceValidationRunRow(Base):
    """Auditable outcome of an external resource lifecycle operation."""

    __tablename__ = "platform_resource_validation_run"
    __table_args__ = (
        Index("ix_platform_resource_validation_run_tenant_version", "tenant_id", "resource_version_id", "created_at"),
    )

    validation_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_resource_version.resource_version_id", ondelete="CASCADE"), nullable=False
    )
    validation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SecretVaultRow(Base):
    """Encrypted tenant secret. APIs never serialize encrypted_value."""

    __tablename__ = "platform_secret_vault"
    __table_args__ = (Index("ix_platform_secret_vault_tenant", "tenant_id"),)

    secret_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ACTIVE")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResourceExternalBindingRow(Base):
    """Stable mapping from a discovered provider object to one platform resource."""

    __tablename__ = "platform_resource_external_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "connection_resource_id", "external_type", "external_id", name="uq_platform_resource_external_binding"),
        Index("ix_platform_resource_external_binding_tenant_connection", "tenant_id", "connection_resource_id"),
    )

    binding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_resource_definition.resource_id", ondelete="CASCADE"), nullable=False
    )
    external_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_resource_definition.resource_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="MANAGED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MemoryItemRow(Base):
    __tablename__ = "platform_memory_item"
    __table_args__ = (
        Index("ix_platform_memory_scope", "tenant_id", "deployment_id", "user_id"),
        UniqueConstraint("tenant_id", "deployment_id", "user_id", "source_run_id", name="uq_platform_memory_source_run"),
    )

    memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeploymentPublishIdempotencyRow(Base):
    __tablename__ = "platform_deployment_publish_idempotency"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "deployment_id", "idempotency_key", name="uq_platform_deployment_publish_idempotency"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    response: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeploymentConfigurationDraftRow(Base):
    """Mutable, tenant-scoped editing state; published revisions remain immutable."""

    __tablename__ = "platform_deployment_configuration_draft"
    __table_args__ = (
        UniqueConstraint("tenant_id", "deployment_id", name="uq_platform_deployment_configuration_draft"),
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    base_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    specification: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    lock_version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeDocumentRow(Base):
    __tablename__ = "platform_knowledge_document"
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    knowledge_resource_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeFileRow(Base):
    __tablename__ = "platform_knowledge_file"
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeIndexVersionRow(Base):
    __tablename__ = "platform_knowledge_index_version"
    __table_args__ = (UniqueConstraint("tenant_id", "knowledge_resource_version_id", "version_number", name="uq_platform_kb_index_version"),)
    index_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    knowledge_resource_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_strategy: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunkRow(Base):
    __tablename__ = "platform_knowledge_chunk"
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    index_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_knowledge_index_version.index_version_id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_knowledge_document.document_id", ondelete="CASCADE"), nullable=False)
    chunk_number: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB().with_variant(JSON, "sqlite"), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)


class IngestJobRow(Base):
    __tablename__ = "platform_ingest_job"
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    knowledge_resource_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
