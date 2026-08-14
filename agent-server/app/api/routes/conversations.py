from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import require_fresh_mutation_principal, require_fresh_principal
from app.conversation.models import (
    ConversationCreate,
    ConversationRecord,
    ConversationSession,
    ConversationUpdate,
    MessageCreate,
    MessageRecord,
    ThreadCreate,
    ThreadRecord,
)
from app.conversation.store_factory import get_conversation_store
from app.iam.models import Principal
from app.api.dependencies import ensure_resource_action
from app.control_plane.store_factory import get_control_plane_store

router = APIRouter(tags=["conversations"])
store = get_conversation_store()


@router.post("/conversations", response_model=ConversationRecord, status_code=201)
async def create_conversation(
    request: ConversationCreate, principal: Principal = Depends(require_fresh_mutation_principal)
) -> ConversationRecord:
    return await store.create_conversation(request, principal)


@router.get("/conversations", response_model=list[ConversationRecord])
async def list_conversations(principal: Principal = Depends(require_fresh_principal)) -> list[ConversationRecord]:
    return await store.list_conversations(principal)


@router.post("/deployments/{deployment_id}/conversations", response_model=ConversationSession, status_code=201)
async def create_deployment_conversation(
    deployment_id: UUID,
    request: ConversationCreate,
    principal: Principal = Depends(require_fresh_mutation_principal),
) -> ConversationSession:
    await ensure_resource_action(principal, "RUN", "DEPLOYMENT", str(deployment_id))
    await get_control_plane_store().resolve(deployment_id, principal)
    conversation = await store.create_conversation(
        request.model_copy(update={"deployment_id": deployment_id}), principal
    )
    thread = await store.create_thread(conversation.conversation_id, ThreadCreate(title=request.title), principal)
    return ConversationSession(conversation=conversation, thread=thread)


@router.get("/deployments/{deployment_id}/conversations", response_model=list[ConversationRecord])
async def list_deployment_conversations(
    deployment_id: UUID, principal: Principal = Depends(require_fresh_principal)
) -> list[ConversationRecord]:
    await ensure_resource_action(principal, "RUN", "DEPLOYMENT", str(deployment_id))
    return await store.list_for_deployment(deployment_id, principal)


@router.patch("/conversations/{conversation_id}", response_model=ConversationRecord)
async def update_conversation(
    conversation_id: UUID,
    request: ConversationUpdate,
    principal: Principal = Depends(require_fresh_mutation_principal),
) -> ConversationRecord:
    return await store.update_conversation(conversation_id, request, principal)


@router.post("/conversations/{conversation_id}/threads", response_model=ThreadRecord, status_code=201)
async def create_thread(
    conversation_id: UUID,
    request: ThreadCreate,
    principal: Principal = Depends(require_fresh_mutation_principal),
) -> ThreadRecord:
    return await store.create_thread(conversation_id, request, principal)


@router.get("/conversations/{conversation_id}/threads", response_model=list[ThreadRecord])
async def list_threads(
    conversation_id: UUID, principal: Principal = Depends(require_fresh_principal)
) -> list[ThreadRecord]:
    return await store.list_threads(conversation_id, principal)


@router.post("/threads/{thread_id}/messages", response_model=MessageRecord, status_code=201)
async def create_message(
    thread_id: UUID,
    request: MessageCreate,
    principal: Principal = Depends(require_fresh_mutation_principal),
) -> MessageRecord:
    return await store.create_message(thread_id, request, principal)


@router.get("/threads/{thread_id}/messages", response_model=list[MessageRecord])
async def list_messages(thread_id: UUID, principal: Principal = Depends(require_fresh_principal)) -> list[MessageRecord]:
    return await store.list_messages(thread_id, principal)
