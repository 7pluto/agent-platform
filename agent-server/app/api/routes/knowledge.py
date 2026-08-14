from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.iam.models import Principal
from app.knowledge.models import IngestJobRecord, KnowledgeDocumentRecord, KnowledgeIndexRecord, RetrievalHit
from app.resources.registry_models import ResourceType
from app.resources.registry_factory import get_resource_registry
from app.knowledge.service import get_knowledge_file_service
from app.knowledge.jobs import ingest_jobs

router = APIRouter(tags=["knowledge"])


async def _published_knowledge(principal: Principal, resource_version_id: UUID) -> None:
    resource = await get_resource_registry().get_version(resource_version_id, principal, published=True)
    if resource.resource_type != ResourceType.KNOWLEDGE:
        from app.core.errors import ApiError
        raise ApiError(422, "INVALID_KNOWLEDGE_RESOURCE", "resource version must be published Knowledge")


class RegisterDocumentRequest(BaseModel):
    knowledge_resource_version_id: UUID
    file_id: UUID


class RetrievalTestRequest(BaseModel):
    knowledge_resource_version_id: UUID
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)


class BuildIndexRequest(BaseModel):
    knowledge_resource_version_id: UUID


@router.post("/knowledge/documents/upload", response_model=KnowledgeDocumentRecord, status_code=202)
async def upload_document(
    knowledge_resource_version_id: UUID = Form(),
    file: UploadFile = File(),
    principal: Principal = Depends(require_platform_admin),
) -> KnowledgeDocumentRecord:
    await _published_knowledge(principal, knowledge_resource_version_id)
    row = await get_knowledge_file_service().upload_and_register(principal, knowledge_resource_version_id, file)
    return KnowledgeDocumentRecord(
        document_id=row.document_id,
        knowledge_resource_version_id=row.knowledge_resource_version_id,
        file_id=row.file_id,
        filename=row.filename,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/knowledge/documents", response_model=KnowledgeDocumentRecord, status_code=202)
async def register_document(request: RegisterDocumentRequest, principal: Principal = Depends(require_platform_admin)) -> KnowledgeDocumentRecord:
    await _published_knowledge(principal, request.knowledge_resource_version_id)
    row = await get_knowledge_file_service().register_document(principal, request.knowledge_resource_version_id, request.file_id)
    return KnowledgeDocumentRecord(document_id=row.document_id, knowledge_resource_version_id=row.knowledge_resource_version_id, file_id=row.file_id, filename=row.filename, status=row.status, created_at=row.created_at)


@router.post("/knowledge/retrieval-test", response_model=list[RetrievalHit])
async def retrieval_test(request: RetrievalTestRequest, principal: Principal = Depends(require_platform_admin)) -> list[RetrievalHit]:
    await _published_knowledge(principal, request.knowledge_resource_version_id)
    index, rows = await get_knowledge_file_service().retrieval_test(principal, request.knowledge_resource_version_id, request.query, request.top_k)
    return [RetrievalHit(document_id=row["document_id"], chunk_number=row["chunk_number"], content=row["content"], score=float(row["score"]), index_version_id=index.index_version_id) for row in rows]


@router.post("/knowledge/indexes/build", status_code=202)
async def build_index(request: BuildIndexRequest, principal: Principal = Depends(require_platform_admin)) -> dict[str, str]:
    await _published_knowledge(principal, request.knowledge_resource_version_id)
    job = await ingest_jobs.enqueue(principal.tenant_id, principal.external_user_id, request.knowledge_resource_version_id)
    return {"job_id": str(job.job_id), "status": "PENDING"}


@router.get("/knowledge/documents", response_model=list[KnowledgeDocumentRecord])
async def list_documents(
    knowledge_resource_version_id: UUID = Query(),
    principal: Principal = Depends(require_platform_admin_read),
) -> list[KnowledgeDocumentRecord]:
    await _published_knowledge(principal, knowledge_resource_version_id)
    return await get_knowledge_file_service().list_documents(principal, knowledge_resource_version_id)


@router.get("/knowledge/indexes", response_model=list[KnowledgeIndexRecord])
async def list_indexes(
    knowledge_resource_version_id: UUID = Query(),
    principal: Principal = Depends(require_platform_admin_read),
) -> list[KnowledgeIndexRecord]:
    await _published_knowledge(principal, knowledge_resource_version_id)
    return await get_knowledge_file_service().list_indexes(principal, knowledge_resource_version_id)


@router.get("/knowledge/ingest-jobs", response_model=list[IngestJobRecord])
async def list_ingest_jobs(
    knowledge_resource_version_id: UUID = Query(),
    principal: Principal = Depends(require_platform_admin_read),
) -> list[IngestJobRecord]:
    await _published_knowledge(principal, knowledge_resource_version_id)
    return await ingest_jobs.list_for_knowledge(principal, knowledge_resource_version_id)
