from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    deployment_id: UUID | None = None


class ConversationRecord(ConversationCreate):
    conversation_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class ThreadRecord(ThreadCreate):
    thread_id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    tenant_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MessageCreate(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str = Field(min_length=1, max_length=100_000)
    source_run_id: UUID | None = None


class MessageRecord(MessageCreate):
    message_id: UUID = Field(default_factory=uuid4)
    thread_id: UUID
    tenant_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=256)


class ConversationSession(BaseModel):
    conversation: ConversationRecord
    thread: ThreadRecord
