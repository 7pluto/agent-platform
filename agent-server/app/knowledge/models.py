from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FileStatus(StrEnum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    SAFE = "SAFE"
    PARSING = "PARSING"
    READY = "READY"
    REJECTED = "REJECTED"


class KnowledgeFileRecord(BaseModel):
    file_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    filename: str
    content_type: str
    object_key: str
    status: FileStatus = FileStatus.UPLOADED
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeDocumentRecord(BaseModel):
    document_id: UUID
    knowledge_resource_version_id: UUID
    file_id: UUID
    filename: str
    status: FileStatus
    created_at: datetime


class KnowledgeIndexRecord(BaseModel):
    index_version_id: UUID
    knowledge_resource_version_id: UUID
    version_number: int
    status: str
    embedding_model: str
    chunk_strategy: dict
    created_at: datetime


class IngestJobRecord(BaseModel):
    job_id: UUID
    knowledge_resource_version_id: UUID
    status: str
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RetrievalHit(BaseModel):
    document_id: UUID
    chunk_number: int
    content: str
    score: float
    index_version_id: UUID
