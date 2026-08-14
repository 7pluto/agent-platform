from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.conversation.models import (
    ConversationCreate,
    ConversationRecord,
    ConversationUpdate,
    MessageCreate,
    MessageRecord,
    ThreadCreate,
    ThreadRecord,
)
from app.core.errors import ApiError
from app.iam.models import Principal


class ConversationStore:
    """Tenant- and user-owned Conversation, Thread, and Message store."""

    def __init__(self) -> None:
        self._conversations: dict[UUID, ConversationRecord] = {}
        self._threads: dict[UUID, ThreadRecord] = {}
        self._messages: dict[UUID, list[MessageRecord]] = {}
        self._lock = asyncio.Lock()

    async def create_conversation(self, request: ConversationCreate, principal: Principal) -> ConversationRecord:
        async with self._lock:
            record = ConversationRecord(tenant_id=principal.tenant_id, user_id=principal.external_user_id, **request.model_dump())
            self._conversations[record.conversation_id] = record
            return record.model_copy(deep=True)

    async def list_conversations(self, principal: Principal) -> list[ConversationRecord]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in sorted(self._conversations.values(), key=lambda value: value.updated_at, reverse=True)
                if self._owns(item.tenant_id, item.user_id, principal)
            ]

    async def list_for_deployment(self, deployment_id: UUID, principal: Principal) -> list[ConversationRecord]:
        return [item for item in await self.list_conversations(principal) if item.deployment_id == deployment_id]

    async def update_conversation(self, conversation_id: UUID, request: ConversationUpdate, principal: Principal) -> ConversationRecord:
        async with self._lock:
            item = self._conversation(conversation_id, principal).model_copy(update={"title": request.title, "updated_at": datetime.now(timezone.utc)})
            self._conversations[conversation_id] = item
            return item.model_copy(deep=True)

    async def create_thread(self, conversation_id: UUID, request: ThreadCreate, principal: Principal) -> ThreadRecord:
        async with self._lock:
            conversation = self._conversation(conversation_id, principal)
            record = ThreadRecord(
                conversation_id=conversation.conversation_id,
                tenant_id=principal.tenant_id,
                user_id=principal.external_user_id,
                **request.model_dump(),
            )
            self._threads[record.thread_id] = record
            return record.model_copy(deep=True)

    async def list_threads(self, conversation_id: UUID, principal: Principal) -> list[ThreadRecord]:
        async with self._lock:
            self._conversation(conversation_id, principal)
            return [
                item.model_copy(deep=True)
                for item in sorted(self._threads.values(), key=lambda value: value.created_at)
                if item.conversation_id == conversation_id and self._owns(item.tenant_id, item.user_id, principal)
            ]

    async def get_thread(self, thread_id: UUID, principal: Principal) -> ThreadRecord:
        async with self._lock:
            return self._thread(thread_id, principal).model_copy(deep=True)

    async def get_conversation(self, conversation_id: UUID, principal: Principal) -> ConversationRecord:
        async with self._lock:
            return self._conversation(conversation_id, principal).model_copy(deep=True)

    async def set_title_if_empty(self, conversation_id: UUID, title: str, principal: Principal) -> ConversationRecord:
        async with self._lock:
            item = self._conversation(conversation_id, principal)
            if not item.title or item.title == "新会话":
                item = item.model_copy(update={"title": title[:30]})
            item = item.model_copy(update={"updated_at": datetime.now(timezone.utc)})
            self._conversations[conversation_id] = item
            return item.model_copy(deep=True)
    async def create_message(self, thread_id: UUID, request: MessageCreate, principal: Principal) -> MessageRecord:
        async with self._lock:
            self._thread(thread_id, principal)
            if request.source_run_id is not None:
                existing = next((item for item in self._messages.get(thread_id, []) if item.source_run_id == request.source_run_id and item.role == request.role), None)
                if existing is not None:
                    return existing.model_copy(deep=True)
            record = MessageRecord(thread_id=thread_id, tenant_id=principal.tenant_id, user_id=principal.external_user_id, **request.model_dump())
            self._messages.setdefault(thread_id, []).append(record)
            conversation = self._conversations[self._threads[thread_id].conversation_id]
            self._conversations[conversation.conversation_id] = conversation.model_copy(update={"updated_at": datetime.now(timezone.utc)})
            return record.model_copy(deep=True)

    async def list_messages(self, thread_id: UUID, principal: Principal) -> list[MessageRecord]:
        async with self._lock:
            self._thread(thread_id, principal)
            return [item.model_copy(deep=True) for item in self._messages.get(thread_id, [])]

    def _conversation(self, conversation_id: UUID, principal: Principal) -> ConversationRecord:
        item = self._conversations.get(conversation_id)
        if item is None or not self._owns(item.tenant_id, item.user_id, principal):
            raise ApiError(404, "NOT_FOUND", "conversation was not found")
        return item

    def _thread(self, thread_id: UUID, principal: Principal) -> ThreadRecord:
        item = self._threads.get(thread_id)
        if item is None or not self._owns(item.tenant_id, item.user_id, principal):
            raise ApiError(404, "NOT_FOUND", "thread was not found")
        return item

    @staticmethod
    def _owns(tenant_id: str, user_id: str, principal: Principal) -> bool:
        return tenant_id == principal.tenant_id and user_id == principal.external_user_id
