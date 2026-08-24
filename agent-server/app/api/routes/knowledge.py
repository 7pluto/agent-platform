from __future__ import annotations

from time import perf_counter
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.iam.models import Principal
from app.knowledge.models import IngestJobRecord, KnowledgeDocumentRecord, KnowledgeIndexRecord
from app.knowledge.providers import knowledge_provider_registry
from app.knowledge.providers.context import resolve_knowledge_provider_config
from app.resources.registry_models import ResourceType, ResourceValidationStatus, ResourceValidationType
from app.resources.registry_models import ResourceDefinitionCreate, ResourceVersionCreate
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_store import ResourceRegistryStore
from app.resources.validation import get_resource_validation_service
from app.resources.product_governance import ProductGovernance, apply_product_governance, resolve_publication_subjects
from app.knowledge.service import get_knowledge_file_service
from app.knowledge.jobs import ingest_jobs
from app.secrets.vault import get_secret_vault
from app.governance.store_factory import get_governance_store

router = APIRouter(tags=["knowledge"])


async def _published_knowledge(principal: Principal, resource_version_id: UUID):
    resource = await get_resource_registry().get_version(resource_version_id, principal, published=True)
    if resource.resource_type != ResourceType.KNOWLEDGE:
        from app.core.errors import ApiError
        raise ApiError(422, "INVALID_KNOWLEDGE_RESOURCE", "resource version must be published Knowledge")
    return resource


async def _local_knowledge(principal: Principal, resource_version_id: UUID):
    resource = await _published_knowledge(principal, resource_version_id)
    if str((resource.config or {}).get("provider", "LOCAL")).upper() != "LOCAL":
        from app.core.errors import ApiError
        raise ApiError(409, "KNOWLEDGE_OPERATION_EXTERNAL", "this operation is managed by the external Knowledge provider")
    return resource


class RegisterDocumentRequest(BaseModel):
    knowledge_resource_version_id: UUID
    file_id: UUID


class RetrievalTestRequest(BaseModel):
    knowledge_resource_version_id: UUID
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)


class BuildIndexRequest(BaseModel):
    knowledge_resource_version_id: UUID


class KnowledgeRetrievalHit(BaseModel):
    document_id: str
    chunk_number: int = 0
    content: str
    score: float = 0
    index_version_id: str | None = None
    title: str | None = None
    source: str | None = None


class RemoteHttpKnowledgeCreate(ProductGovernance):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="调用受控企业知识检索 API", max_length=4_000)
    endpoint: str
    search_path: str = Field(default="/search")
    method: str = Field(default="POST", pattern=r"^(GET|POST)$")
    timeout_seconds: float = Field(default=15, ge=0.1, le=60)
    api_key: str | None = Field(default=None, min_length=1, max_length=32_768)
    auth_header: str = Field(default="Authorization", min_length=1, max_length=128)
    auth_scheme: str = Field(default="Bearer", max_length=128)
    query_field: str = Field(default="query", min_length=1, max_length=128)
    top_k_field: str = Field(default="top_k", min_length=1, max_length=128)
    static_body: dict = Field(default_factory=dict)
    items_path: str = Field(default="items", max_length=256)
    id_field: str = Field(default="id", max_length=128)
    content_field: str = Field(default="content", min_length=1, max_length=128)
    title_field: str = Field(default="title", max_length=128)
    score_field: str | None = Field(default="score", max_length=128)
    metadata_field: str = Field(default="metadata", max_length=128)
    test_query: str = Field(min_length=1, max_length=2_000)
    test_top_k: int = Field(default=3, ge=1, le=10)


class RemoteHttpKnowledgePublishResponse(BaseModel):
    resource_id: UUID
    resource_version_id: UUID
    version_number: int
    status: str
    test_result: dict


@router.post("/knowledge/documents/upload", response_model=KnowledgeDocumentRecord, status_code=202)
async def upload_document(
    knowledge_resource_version_id: UUID = Form(),
    file: UploadFile = File(),
    principal: Principal = Depends(require_platform_admin),
) -> KnowledgeDocumentRecord:
    await _local_knowledge(principal, knowledge_resource_version_id)
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
    await _local_knowledge(principal, request.knowledge_resource_version_id)
    row = await get_knowledge_file_service().register_document(principal, request.knowledge_resource_version_id, request.file_id)
    return KnowledgeDocumentRecord(document_id=row.document_id, knowledge_resource_version_id=row.knowledge_resource_version_id, file_id=row.file_id, filename=row.filename, status=row.status, created_at=row.created_at)


@router.post("/knowledge/retrieval-test", response_model=list[KnowledgeRetrievalHit])
async def retrieval_test(request: RetrievalTestRequest, principal: Principal = Depends(require_platform_admin)) -> list[KnowledgeRetrievalHit]:
    resource = await _published_knowledge(principal, request.knowledge_resource_version_id)
    config = await resolve_knowledge_provider_config(resource, principal)
    provider = knowledge_provider_registry.resolve(config, principal)
    started = perf_counter()
    try:
        result = await provider.search(
            knowledge_version_id=str(resource.resource_version_id), config=config,
            query=request.query, top_k=request.top_k,
        )
    except Exception as exc:
        from app.core.errors import ApiError
        code = exc.code if isinstance(exc, ApiError) else "KNOWLEDGE_TEST_FAILED"
        message = exc.message if isinstance(exc, ApiError) else type(exc).__name__
        await get_resource_validation_service().record(
            resource.resource_version_id, ResourceValidationType.TEST, ResourceValidationStatus.FAILED,
            {"provider": str(config.get("provider", "LOCAL")), "code": code, "message": message},
            principal, round((perf_counter() - started) * 1000),
        )
        raise
    await get_resource_validation_service().record(
        resource.resource_version_id, ResourceValidationType.TEST, ResourceValidationStatus.SUCCEEDED,
        {"provider": result.provider, "hit_count": len(result.hits)},
        principal, round((perf_counter() - started) * 1000),
    )
    return [KnowledgeRetrievalHit(
        document_id=hit.id, chunk_number=index + 1, content=hit.content,
        score=float(hit.score or 0), index_version_id=str(result.metadata.get("index_version_id")) if result.metadata.get("index_version_id") else None,
        title=hit.title, source=hit.source or result.provider,
    ) for index, hit in enumerate(result.hits)]


@router.post("/remote-http-knowledge", response_model=RemoteHttpKnowledgePublishResponse, status_code=201)
async def create_remote_http_knowledge(
    request: RemoteHttpKnowledgeCreate,
    principal: Principal = Depends(require_platform_admin),
) -> RemoteHttpKnowledgePublishResponse:
    """Register one fixed enterprise Knowledge API and prove retrieval before publication."""
    resolve_publication_subjects(request)
    host = urlsplit(request.endpoint).hostname
    if not host:
        from app.core.errors import ApiError
        raise ApiError(422, "INVALID_REMOTE_KNOWLEDGE_CONFIG", "endpoint must contain a hostname")
    config: dict = {
        "provider": "REMOTE_HTTP",
        "endpoint": request.endpoint.rstrip("/"),
        "search_path": request.search_path,
        "method": request.method,
        "timeout_seconds": request.timeout_seconds,
        "egress_allowlist": [host],
        "request_mapping": {
            "query_field": request.query_field,
            "top_k_field": request.top_k_field,
            "static_body": request.static_body,
        },
        "response_mapping": {
            "items_path": request.items_path,
            "id_field": request.id_field,
            "content_field": request.content_field,
            "title_field": request.title_field,
            "score_field": request.score_field,
            "metadata_field": request.metadata_field,
        },
    }
    if request.api_key:
        secret = await get_secret_vault().create(f"Remote Knowledge: {request.display_name}", request.api_key, principal)
        config.update({"secret_ref": secret.secret_ref, "auth_header": request.auth_header, "auth_scheme": request.auth_scheme})
    ResourceRegistryStore._validate(ResourceType.KNOWLEDGE, config)
    registry = get_resource_registry()
    definition = await registry.create_definition(ResourceDefinitionCreate(
        resource_type=ResourceType.KNOWLEDGE, slug=request.slug, display_name=request.display_name,
        description=request.description, draft_config=config,
    ), principal)
    version = await registry.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    started = perf_counter()
    provider = knowledge_provider_registry.resolve(config, principal)
    try:
        result = await provider.search(
            knowledge_version_id=str(version.resource_version_id), config=config,
            query=request.test_query, top_k=request.test_top_k,
        )
    except Exception as exc:
        from app.core.errors import ApiError
        code = exc.code if isinstance(exc, ApiError) else "KNOWLEDGE_TEST_FAILED"
        message = exc.message if isinstance(exc, ApiError) else type(exc).__name__
        await get_resource_validation_service().record(
            version.resource_version_id, ResourceValidationType.TEST, ResourceValidationStatus.FAILED,
            {"provider": "REMOTE_HTTP", "code": code, "message": message}, principal,
            round((perf_counter() - started) * 1000),
        )
        raise
    test_result = {"provider": result.provider, "hit_count": len(result.hits)}
    await get_resource_validation_service().record(
        version.resource_version_id, ResourceValidationType.TEST, ResourceValidationStatus.SUCCEEDED,
        test_result, principal, round((perf_counter() - started) * 1000),
    )
    published = await registry.publish_version(version.resource_version_id, principal)
    grants = await apply_product_governance(
        product=request,
        resource_type=ResourceType.KNOWLEDGE.value,
        resource_id=published.resource_id,
        resource_version_id=published.resource_version_id,
        source_type="REMOTE_HTTP",
        source_ref=f"{request.method} {request.search_path}",
        principal=principal,
    )
    await get_governance_store().record_audit(
        principal, "remote_knowledge.publish", ResourceType.KNOWLEDGE.value,
        str(published.resource_version_id), {"resource_id": str(published.resource_id), "provider": "REMOTE_HTTP", "hit_count": len(result.hits), "publication_scope": request.publication_scope, "grant_count": len(grants)},
    )
    return RemoteHttpKnowledgePublishResponse(
        resource_id=published.resource_id, resource_version_id=published.resource_version_id,
        version_number=published.version_number, status=published.status.value, test_result=test_result,
    )


@router.post("/knowledge/indexes/build", status_code=202)
async def build_index(request: BuildIndexRequest, principal: Principal = Depends(require_platform_admin)) -> dict[str, str]:
    await _local_knowledge(principal, request.knowledge_resource_version_id)
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
