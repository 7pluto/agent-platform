"""Resolve a Knowledge provider from trusted immutable resource configuration."""

from __future__ import annotations

from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.providers.base import KnowledgeProvider
from app.knowledge.providers.local import LocalKnowledgeProvider
from app.knowledge.providers.remote_http import RemoteHttpKnowledgeProvider
from app.knowledge.providers.ragflow import RagflowKnowledgeProvider


class KnowledgeProviderRegistry:
    @staticmethod
    def resolve(config: dict, principal: Principal) -> KnowledgeProvider:
        provider = str(config.get("provider", "LOCAL")).upper()
        if provider == "LOCAL":
            return LocalKnowledgeProvider(principal)
        if provider == "REMOTE_HTTP":
            return RemoteHttpKnowledgeProvider(principal)
        if provider == "RAGFLOW":
            return RagflowKnowledgeProvider(principal)
        raise ApiError(422, "KNOWLEDGE_PROVIDER_NOT_SUPPORTED", f"knowledge provider is not supported: {provider}")


knowledge_provider_registry = KnowledgeProviderRegistry()
