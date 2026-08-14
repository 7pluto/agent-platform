from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from app.conversation.models import ConversationCreate, ConversationRecord, ConversationUpdate, MessageCreate, MessageRecord, MessageRole, ThreadCreate, ThreadRecord
from app.core.errors import ApiError
from app.db.models import ConversationMessageRow, ConversationRow, ConversationThreadRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal


class PostgresConversationStore:
    async def create_conversation(self, request: ConversationCreate, principal: Principal) -> ConversationRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = ConversationRow(conversation_id=uuid4(), tenant_id=principal.tenant_id, user_id=principal.external_user_id, deployment_id=request.deployment_id, title=request.title)
                session.add(row)
                await session.flush()
                return self._conversation(row)

    async def list_conversations(self, principal: Principal) -> list[ConversationRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(select(ConversationRow).where(ConversationRow.tenant_id == principal.tenant_id, ConversationRow.user_id == principal.external_user_id).order_by(ConversationRow.updated_at.desc(), ConversationRow.conversation_id))
                return [self._conversation(row) for row in rows.all()]

    async def list_for_deployment(self, deployment_id: UUID, principal: Principal) -> list[ConversationRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(select(ConversationRow).where(ConversationRow.tenant_id == principal.tenant_id, ConversationRow.user_id == principal.external_user_id, ConversationRow.deployment_id == deployment_id).order_by(ConversationRow.updated_at.desc(), ConversationRow.conversation_id))
                return [self._conversation(row) for row in rows.all()]

    async def update_conversation(self, conversation_id: UUID, request: ConversationUpdate, principal: Principal) -> ConversationRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await self._conversation_owned(session, conversation_id, principal)
                row.title = request.title
                row.updated_at = datetime.now(timezone.utc)
                return self._conversation(row)

    async def create_thread(self, conversation_id: UUID, request: ThreadCreate, principal: Principal) -> ThreadRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._conversation_owned(session, conversation_id, principal)
                row = ConversationThreadRow(thread_id=uuid4(), conversation_id=conversation_id, tenant_id=principal.tenant_id, user_id=principal.external_user_id, title=request.title)
                session.add(row)
                await session.flush()
                return self._thread(row)

    async def list_threads(self, conversation_id: UUID, principal: Principal) -> list[ThreadRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._conversation_owned(session, conversation_id, principal)
                rows = await session.scalars(select(ConversationThreadRow).where(ConversationThreadRow.conversation_id == conversation_id, ConversationThreadRow.tenant_id == principal.tenant_id, ConversationThreadRow.user_id == principal.external_user_id).order_by(ConversationThreadRow.created_at, ConversationThreadRow.thread_id))
                return [self._thread(row) for row in rows.all()]

    async def get_thread(self, thread_id: UUID, principal: Principal) -> ThreadRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                return self._thread(await self._thread_owned(session, thread_id, principal))

    async def get_conversation(self, conversation_id: UUID, principal: Principal) -> ConversationRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                return self._conversation(await self._conversation_owned(session, conversation_id, principal))

    async def set_title_if_empty(self, conversation_id: UUID, title: str, principal: Principal) -> ConversationRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await self._conversation_owned(session, conversation_id, principal)
                if not row.title or row.title == "新会话":
                    row.title = title[:30]
                row.updated_at = datetime.now(timezone.utc)
                return self._conversation(row)
    async def create_message(self, thread_id: UUID, request: MessageCreate, principal: Principal) -> MessageRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._thread_owned(session, thread_id, principal)
                if request.source_run_id is not None:
                    existing = await session.scalar(select(ConversationMessageRow).where(ConversationMessageRow.tenant_id == principal.tenant_id, ConversationMessageRow.thread_id == thread_id, ConversationMessageRow.source_run_id == request.source_run_id, ConversationMessageRow.role == request.role.value))
                    if existing is not None:
                        return self._message(existing)
                row = ConversationMessageRow(message_id=uuid4(), thread_id=thread_id, tenant_id=principal.tenant_id, user_id=principal.external_user_id, role=request.role.value, content=request.content, source_run_id=request.source_run_id)
                session.add(row)
                thread = await self._thread_owned(session, thread_id, principal)
                conversation = await self._conversation_owned(session, thread.conversation_id, principal)
                conversation.updated_at = datetime.now(timezone.utc)
                await session.flush()
                return self._message(row)

    async def list_messages(self, thread_id: UUID, principal: Principal) -> list[MessageRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                await self._thread_owned(session, thread_id, principal)
                rows = await session.scalars(select(ConversationMessageRow).where(ConversationMessageRow.thread_id == thread_id, ConversationMessageRow.tenant_id == principal.tenant_id, ConversationMessageRow.user_id == principal.external_user_id).order_by(ConversationMessageRow.created_at, ConversationMessageRow.message_id))
                return [self._message(row) for row in rows.all()]

    @staticmethod
    async def _conversation_owned(session, identifier: UUID, principal: Principal) -> ConversationRow:
        row = await session.get(ConversationRow, identifier)
        if row is None or row.tenant_id != principal.tenant_id or row.user_id != principal.external_user_id:
            raise ApiError(404, "NOT_FOUND", "conversation was not found")
        return row

    @staticmethod
    async def _thread_owned(session, identifier: UUID, principal: Principal) -> ConversationThreadRow:
        row = await session.get(ConversationThreadRow, identifier)
        if row is None or row.tenant_id != principal.tenant_id or row.user_id != principal.external_user_id:
            raise ApiError(404, "NOT_FOUND", "thread was not found")
        return row

    @staticmethod
    def _conversation(row: ConversationRow) -> ConversationRecord: return ConversationRecord(conversation_id=row.conversation_id, tenant_id=row.tenant_id, user_id=row.user_id, deployment_id=row.deployment_id, title=row.title, created_at=row.created_at or datetime.now(timezone.utc), updated_at=row.updated_at or datetime.now(timezone.utc))
    @staticmethod
    def _thread(row: ConversationThreadRow) -> ThreadRecord: return ThreadRecord(thread_id=row.thread_id, conversation_id=row.conversation_id, tenant_id=row.tenant_id, user_id=row.user_id, title=row.title, created_at=row.created_at or datetime.now(timezone.utc))
    @staticmethod
    def _message(row: ConversationMessageRow) -> MessageRecord: return MessageRecord(message_id=row.message_id, thread_id=row.thread_id, tenant_id=row.tenant_id, user_id=row.user_id, role=MessageRole(row.role), content=row.content, source_run_id=row.source_run_id, created_at=row.created_at or datetime.now(timezone.utc))
