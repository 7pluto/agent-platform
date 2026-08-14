from __future__ import annotations

import io
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.errors import ApiError
from app.config import get_settings
from app.db.models import KnowledgeChunkRow, KnowledgeDocumentRow, KnowledgeIndexVersionRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.knowledge.service import get_knowledge_file_service
from app.resources.openai_compatible import OpenAICompatibleEmbedder
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.store_factory import get_resource_store


def _chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    return [normalized[start:start + size] for start in range(0, len(normalized), max(1, size - overlap))]


class KnowledgeIngestor:
    """Worker-only PDF/DOCX parser and atomic index-version builder."""

    async def build(self, tenant_id: str, user_id: str, knowledge_resource_version_id: UUID) -> UUID:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                number = await session.scalar(select(func.max(KnowledgeIndexVersionRow.version_number)).where(KnowledgeIndexVersionRow.tenant_id == tenant_id, KnowledgeIndexVersionRow.knowledge_resource_version_id == knowledge_resource_version_id))
                index = KnowledgeIndexVersionRow(index_version_id=uuid4(), tenant_id=tenant_id, knowledge_resource_version_id=knowledge_resource_version_id, version_number=(number or 0) + 1, status="BUILDING", embedding_model="text-embedding-v3", chunk_strategy={"size": 900, "overlap": 120})
                session.add(index)
                documents = (await session.scalars(select(KnowledgeDocumentRow).where(KnowledgeDocumentRow.tenant_id == tenant_id, KnowledgeDocumentRow.knowledge_resource_version_id == knowledge_resource_version_id, KnowledgeDocumentRow.status.in_(("UPLOADED", "READY"))))).all()
                document_ids = [document.document_id for document in documents]
                if not document_ids:
                    raise ApiError(409, "KNOWLEDGE_DOCUMENTS_REQUIRED", "register at least one document before building an index")
                for document in documents:
                    document.status = "PARSING"
                await session.flush()

        try:
            await self._ingest_documents(tenant_id, user_id, index.index_version_id, knowledge_resource_version_id, document_ids)
        except Exception:
            await self._fail(tenant_id, user_id, index.index_version_id, document_ids)
            raise
        await self._activate(tenant_id, user_id, index.index_version_id, knowledge_resource_version_id)
        return index.index_version_id

    async def _ingest_documents(self, tenant_id: str, user_id: str, index_id: UUID, knowledge_resource_version_id: UUID, document_ids: list[UUID]) -> None:
        service = get_knowledge_file_service()
        client = service._client()
        principal = Principal(provider="worker", external_user_id=user_id, external_org_id="worker", tenant_id=tenant_id, display_name="Worker")
        knowledge = await get_resource_registry().get_version(knowledge_resource_version_id, principal, published=True)
        model_version_id = knowledge.config.get("embedding_model_version_id")
        if not isinstance(model_version_id, str):
            raise ApiError(422, "EMBEDDING_MODEL_REQUIRED", "Knowledge must bind a published embedding model version")
        model = await get_resource_store().get_model_version(UUID(model_version_id), principal, require_available=True)
        embedder = await OpenAICompatibleEmbedder.from_model_config(model.config, tenant_id, user_id)
        for document_id in document_ids:
            async with get_session_factory()() as session:
                async with session.begin():
                    await set_local_tenant_context(session, tenant_id, user_id)
                    document = await session.get(KnowledgeDocumentRow, document_id)
                    if document is None:
                        continue
                    filename, object_key = document.filename, document.object_key
            obj = client.get_object(get_settings().minio_bucket, object_key)
            try:
                data = obj.read()
            finally:
                obj.close(); obj.release_conn()
            text = self._parse(filename, data)
            chunks = _chunks(text)
            embeddings = await embedder.embed(chunks)
            async with get_session_factory()() as session:
                async with session.begin():
                    await set_local_tenant_context(session, tenant_id, user_id)
                    for number, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                        session.add(KnowledgeChunkRow(chunk_id=uuid4(), tenant_id=tenant_id, index_version_id=index_id, document_id=document_id, chunk_number=number, content=content, metadata_json={"filename": filename}, embedding=embedding))
                    current = await session.get(KnowledgeDocumentRow, document_id)
                    if current:
                        current.status = "READY"

    @staticmethod
    def _parse(filename: str, data: bytes) -> str:
        try:
            if filename.lower().endswith(".pdf"):
                from pypdf import PdfReader
                return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
            if filename.lower().endswith(".docx"):
                from docx import Document
                return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        except Exception as exc:
            raise ApiError(422, "DOCUMENT_PARSE_FAILED", "unable to parse knowledge document") from exc
        raise ApiError(422, "UNSUPPORTED_FILE_TYPE", "V1 knowledge files must be PDF or DOCX")

    async def _activate(self, tenant_id: str, user_id: str, index_id: UUID, resource_version_id: UUID) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                rows = await session.scalars(select(KnowledgeIndexVersionRow).where(KnowledgeIndexVersionRow.tenant_id == tenant_id, KnowledgeIndexVersionRow.knowledge_resource_version_id == resource_version_id))
                for row in rows.all():
                    row.status = "ACTIVE" if row.index_version_id == index_id else "RETIRED"

    async def _fail(self, tenant_id: str, user_id: str, index_id: UUID, document_ids: list[UUID]) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                row = await session.get(KnowledgeIndexVersionRow, index_id)
                if row:
                    row.status = "FAILED"
                documents = await session.scalars(select(KnowledgeDocumentRow).where(KnowledgeDocumentRow.tenant_id == tenant_id, KnowledgeDocumentRow.document_id.in_(document_ids), KnowledgeDocumentRow.status == "PARSING"))
                for document in documents.all():
                    document.status = "UPLOADED"


knowledge_ingestor = KnowledgeIngestor()
