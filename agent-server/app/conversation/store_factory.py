from functools import lru_cache

from app.config import get_settings
from app.conversation.postgres_store import PostgresConversationStore
from app.conversation.store import ConversationStore


@lru_cache
def get_conversation_store() -> ConversationStore | PostgresConversationStore:
    return PostgresConversationStore() if get_settings().storage_mode == "postgres" else ConversationStore()