"""Provider-neutral Knowledge retrieval contract used by the Agent runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeHit(BaseModel):
    id: str
    content: str
    score: float | None = None
    title: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResult(BaseModel):
    provider: str
    hits: list[KnowledgeHit] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeProvider(ABC):
    provider_name: str

    @abstractmethod
    async def search(
        self,
        *,
        knowledge_version_id: str,
        config: dict[str, Any],
        query: str,
        top_k: int,
    ) -> KnowledgeSearchResult: ...
