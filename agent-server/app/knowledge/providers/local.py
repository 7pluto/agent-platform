"""Adapter around the existing MinIO + embedding + pgvector Knowledge path."""

from __future__ import annotations

from uuid import UUID

from app.iam.models import Principal
from app.knowledge.service import get_knowledge_file_service
from app.knowledge.providers.base import KnowledgeHit, KnowledgeProvider, KnowledgeSearchResult


class LocalKnowledgeProvider(KnowledgeProvider):
    provider_name = "LOCAL"

    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def search(
        self,
        *,
        knowledge_version_id: str,
        config: dict,
        query: str,
        top_k: int,
    ) -> KnowledgeSearchResult:
        index, hits = await get_knowledge_file_service().retrieval_test(
            self.principal, UUID(knowledge_version_id), query, top_k
        )
        return KnowledgeSearchResult(
            provider=self.provider_name,
            metadata={"index_version_id": str(index.index_version_id)},
            hits=[
                KnowledgeHit(
                    id=f"{hit.get('document_id', '')}:{hit.get('chunk_number', '')}",
                    content=str(hit.get("content", "")),
                    score=float(hit["score"]) if hit.get("score") is not None else None,
                    title=str(hit.get("filename") or hit.get("document_id") or "") or None,
                    source="LOCAL",
                    metadata={"document_id": str(hit.get("document_id", "")), "chunk_number": hit.get("chunk_number")},
                )
                for hit in hits
            ],
        )
