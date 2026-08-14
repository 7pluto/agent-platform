import asyncio

from app.conversation.models import ConversationCreate, MessageCreate, ThreadCreate
from app.conversation.store import ConversationStore
from app.core.errors import ApiError
from app.iam.models import Principal


def _principal(tenant: str, user: str) -> Principal:
    return Principal(provider="mock", external_user_id=user, external_org_id=tenant, tenant_id=tenant, display_name=user)


def test_conversation_thread_message_are_user_and_tenant_scoped() -> None:
    async def run() -> None:
        store = ConversationStore()
        owner = _principal("tenant-a", "user-a")
        other = _principal("tenant-b", "user-b")
        conversation = await store.create_conversation(ConversationCreate(title="Demo"), owner)
        thread = await store.create_thread(conversation.conversation_id, ThreadCreate(title="Thread"), owner)
        message = await store.create_message(thread.thread_id, MessageCreate(content="hello"), owner)
        assert (await store.list_messages(thread.thread_id, owner))[0].message_id == message.message_id
        assert (await store.list_threads(conversation.conversation_id, owner))[0].thread_id == thread.thread_id
        try:
            await store.list_messages(thread.thread_id, other)
        except ApiError as exc:
            assert exc.code == "NOT_FOUND"
        else:
            raise AssertionError("cross-tenant message access was accepted")

    asyncio.run(run())