from __future__ import annotations

import asyncio
import os
import zipfile
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select, text

from app.config import get_settings
from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.models import FileStatus, KnowledgeDocumentRecord, KnowledgeFileRecord, KnowledgeIndexRecord
from app.db.models import KnowledgeDocumentRow, KnowledgeFileRow, KnowledgeIndexVersionRow, KnowledgeChunkRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.resources.openai_compatible import OpenAICompatibleEmbedder
from app.resources.registry_factory import get_resource_registry
from app.resources.store_factory import get_resource_store


class KnowledgeFileService:
    """Tenant-safe MinIO entry point; parsing/indexing stays in the Worker."""

    def _client(self):
        # Keep test/API import independent from the optional object-storage
        # client; the production image installs minio from pyproject.toml.
        try:
            from minio import Minio
        except ImportError as exc:
            raise ApiError(503, "OBJECT_STORAGE_UNAVAILABLE", "MinIO client is not installed") from exc
        settings = get_settings()
        endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix("https://")
        return Minio(endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=settings.minio_endpoint.startswith("https://"))

    async def upload_and_register(
        self,
        principal: Principal,
        knowledge_resource_version_id: UUID,
        upload: UploadFile,
    ) -> KnowledgeDocumentRow:
        """Receive browser bytes at the API boundary and write them to MinIO.

        The browser never receives an object-store endpoint or credential. The
        worker remains the only component that parses and embeds document data.
        """
        filename = os.path.basename(upload.filename or "")
        if (
            not filename
            or filename != upload.filename
            or "/" in filename
            or "\\" in filename
            or not filename.lower().endswith((".pdf", ".docx"))
        ):
            raise ApiError(422, "UNSUPPORTED_FILE_TYPE", "V1 knowledge files must be PDF or DOCX")
        await self._validate_uploaded_file(upload, filename)
        content_type = "application/pdf" if filename.lower().endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        record = KnowledgeFileRecord(
            tenant_id=principal.tenant_id,
            filename=filename,
            content_type=content_type,
            object_key=f"tenant/{principal.tenant_id}/files/{uuid4()}",
            status=FileStatus.SAFE,
            created_by=principal.external_user_id,
        )
        client = self._client()
        try:
            await asyncio.to_thread(
                self._put_object,
                client,
                record.object_key,
                upload.file,
                await self._file_size(upload),
                content_type,
            )
            await self.persist_upload(record, principal)
            return await self.register_document(principal, knowledge_resource_version_id, record.file_id)
        except ApiError:
            raise
        except Exception as exc:
            try:
                await asyncio.to_thread(client.remove_object, get_settings().minio_bucket, record.object_key)
            except Exception:
                pass
            raise ApiError(503, "OBJECT_STORAGE_UNAVAILABLE", "unable to store uploaded knowledge file") from exc

    @staticmethod
    def _put_object(client, object_key: str, source, length: int, content_type: str) -> None:
        settings = get_settings()
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        client.put_object(settings.minio_bucket, object_key, source, length, content_type=content_type)

    @staticmethod
    async def _file_size(upload: UploadFile) -> int:
        await upload.seek(0)
        upload.file.seek(0, 2)
        size = upload.file.tell()
        await upload.seek(0)
        return size

    async def _validate_uploaded_file(self, upload: UploadFile, filename: str) -> None:
        size = await self._file_size(upload)
        if size == 0 or size > get_settings().knowledge_upload_max_bytes:
            raise ApiError(413, "KNOWLEDGE_FILE_TOO_LARGE", "knowledge file exceeds the configured upload limit")
        header = await upload.read(8)
        await upload.seek(0)
        if filename.lower().endswith(".pdf"):
            if not header.startswith(b"%PDF-"):
                raise ApiError(422, "INVALID_DOCUMENT_CONTENT", "file is not a valid PDF")
            return
        if not header.startswith(b"PK") or not await asyncio.to_thread(self._is_docx, upload.file):
            raise ApiError(422, "INVALID_DOCUMENT_CONTENT", "file is not a valid DOCX")
        await upload.seek(0)

    @staticmethod
    def _is_docx(source) -> bool:
        try:
            source.seek(0)
            with zipfile.ZipFile(source) as archive:
                return "[Content_Types].xml" in archive.namelist() and "word/document.xml" in archive.namelist()
        except zipfile.BadZipFile:
            return False
        finally:
            source.seek(0)

    async def persist_upload(self, record: KnowledgeFileRecord, principal: Principal) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                session.add(KnowledgeFileRow(file_id=record.file_id, tenant_id=record.tenant_id, filename=record.filename, content_type=record.content_type, object_key=record.object_key, status=record.status.value, created_by=record.created_by))

    async def register_document(self, principal: Principal, knowledge_resource_version_id: UUID, file_id: UUID):
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                file = await session.get(KnowledgeFileRow, file_id)
                if file is None:
                    raise ApiError(404, "NOT_FOUND", "uploaded file was not found")
                row = KnowledgeDocumentRow(document_id=uuid4(), tenant_id=principal.tenant_id, knowledge_resource_version_id=knowledge_resource_version_id, file_id=file_id, filename=file.filename, object_key=file.object_key, status=FileStatus.UPLOADED.value, created_by=principal.external_user_id)
                session.add(row)
                await session.flush()
                return row

    async def list_documents(self, principal: Principal, knowledge_resource_version_id: UUID) -> list[KnowledgeDocumentRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(KnowledgeDocumentRow)
                    .where(
                        KnowledgeDocumentRow.tenant_id == principal.tenant_id,
                        KnowledgeDocumentRow.knowledge_resource_version_id == knowledge_resource_version_id,
                    )
                    .order_by(KnowledgeDocumentRow.created_at.desc())
                )
                return [
                    KnowledgeDocumentRecord(
                        document_id=row.document_id,
                        knowledge_resource_version_id=row.knowledge_resource_version_id,
                        file_id=row.file_id,
                        filename=row.filename,
                        status=FileStatus(row.status),
                        created_at=row.created_at,
                    )
                    for row in rows.all()
                ]

    async def list_indexes(self, principal: Principal, knowledge_resource_version_id: UUID) -> list[KnowledgeIndexRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(KnowledgeIndexVersionRow)
                    .where(
                        KnowledgeIndexVersionRow.tenant_id == principal.tenant_id,
                        KnowledgeIndexVersionRow.knowledge_resource_version_id == knowledge_resource_version_id,
                    )
                    .order_by(KnowledgeIndexVersionRow.version_number.desc())
                )
                return [
                    KnowledgeIndexRecord(
                        index_version_id=row.index_version_id,
                        knowledge_resource_version_id=row.knowledge_resource_version_id,
                        version_number=row.version_number,
                        status=row.status,
                        embedding_model=row.embedding_model,
                        chunk_strategy=row.chunk_strategy,
                        created_at=row.created_at,
                    )
                    for row in rows.all()
                ]

    async def retrieval_test(self, principal: Principal, knowledge_resource_version_id: UUID, query: str, top_k: int):
        # Retrieval always filters tenant and knowledge resource in the SQL query;
        # no global vector recall followed by Python filtering is permitted.
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                active = await session.scalar(select(KnowledgeIndexVersionRow).where(KnowledgeIndexVersionRow.tenant_id == principal.tenant_id, KnowledgeIndexVersionRow.knowledge_resource_version_id == knowledge_resource_version_id, KnowledgeIndexVersionRow.status == "ACTIVE").order_by(KnowledgeIndexVersionRow.version_number.desc()))
                if active is None:
                    raise ApiError(409, "KNOWLEDGE_INDEX_NOT_READY", "knowledge base has no active index")
                knowledge = await get_resource_registry().get_version(knowledge_resource_version_id, principal, published=True)
                model_version_id = knowledge.config.get("embedding_model_version_id")
                if not isinstance(model_version_id, str):
                    raise ApiError(422, "EMBEDDING_MODEL_REQUIRED", "Knowledge must bind a published embedding model version")
                model = await get_resource_store().get_model_version(UUID(model_version_id), principal, require_available=True)
                embedding = (await (await OpenAICompatibleEmbedder.from_model_config(model.config, principal.tenant_id, principal.external_user_id)).embed([query]))[0]
                # pgvector distance and every access boundary live in this one
                # query. This must never become global recall plus filtering.
                result = await session.execute(text("""
                    SELECT chunk.chunk_id, chunk.document_id, chunk.chunk_number,
                           chunk.content, 1 - (chunk.embedding <=> CAST(:embedding AS vector)) AS score
                    FROM platform_knowledge_chunk AS chunk
                    JOIN platform_knowledge_document AS document
                      ON document.document_id = chunk.document_id
                    WHERE chunk.tenant_id = :tenant_id
                      AND chunk.index_version_id = :index_version_id
                      AND document.tenant_id = :tenant_id
                      AND document.knowledge_resource_version_id = :knowledge_resource_version_id
                    ORDER BY chunk.embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                """), {"embedding": "[" + ",".join(str(value) for value in embedding) + "]", "tenant_id": principal.tenant_id, "index_version_id": active.index_version_id, "knowledge_resource_version_id": knowledge_resource_version_id, "top_k": top_k})
                # Runtime events and tool observations are persisted as JSONB.
                # SQLAlchemy RowMapping (and UUID values inside it) cannot be
                # serialized by the database driver, so normalize at this
                # storage boundary instead of leaking ORM values to runtime.
                hits = [
                    {
                        "chunk_id": str(row["chunk_id"]),
                        "document_id": str(row["document_id"]),
                        "chunk_number": int(row["chunk_number"]),
                        "content": str(row["content"]),
                        "score": float(row["score"]) if row["score"] is not None else 0.0,
                    }
                    for row in result.mappings().all()
                ]
                return active, hits


_service = KnowledgeFileService()


def get_knowledge_file_service() -> KnowledgeFileService:
    return _service
