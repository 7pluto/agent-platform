from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, common_mcp, common_resources, control_plane, conversations, discovery, developer_dependency_upgrades, developer_external_capabilities, developer_knowledge_ops, developer_model_catalog, developer_playground, developer_resources, governance, resources, resource_registry, knowledge, memory, mcp, health, iam, runs, secrets, workbench, revision_history, ragflow
from app.config import get_settings
from app.core.errors import ApiError, api_error_handler
from app.api.dependencies import get_iam_service
from app.runtime.store_factory import close_run_store
from app.session.factory import close_session_store
from app.runtime.worker import get_runtime_worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await get_iam_service().close()
    await close_run_store()
    await close_session_store()
    await get_runtime_worker().shutdown()


settings = get_settings()
app = FastAPI(title="Enterprise Agent Platform", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)
if settings.trusted_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.trusted_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "Last-Event-ID", "X-CSRF-Token"],
    )
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(iam.router, prefix=settings.api_prefix)
app.include_router(runs.router, prefix=settings.api_prefix)
app.include_router(control_plane.router, prefix=settings.api_prefix)
app.include_router(governance.router, prefix=settings.api_prefix)
app.include_router(conversations.router, prefix=settings.api_prefix)
app.include_router(resources.router, prefix=settings.api_prefix)
app.include_router(resource_registry.router, prefix=settings.api_prefix)
app.include_router(developer_resources.router, prefix=settings.api_prefix)
app.include_router(developer_dependency_upgrades.router, prefix=settings.api_prefix)
app.include_router(developer_external_capabilities.router, prefix=settings.api_prefix)
app.include_router(developer_knowledge_ops.router, prefix=settings.api_prefix)
app.include_router(developer_model_catalog.router, prefix=settings.api_prefix)
app.include_router(developer_playground.router, prefix=settings.api_prefix)
app.include_router(common_resources.router, prefix=settings.api_prefix)
app.include_router(discovery.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(memory.router, prefix=settings.api_prefix)
app.include_router(mcp.router, prefix=settings.api_prefix)
app.include_router(common_mcp.router, prefix=settings.api_prefix)
app.include_router(ragflow.router, prefix=settings.api_prefix)
app.include_router(secrets.router, prefix=settings.api_prefix)
app.include_router(workbench.router, prefix=settings.api_prefix)
app.include_router(revision_history.router, prefix=settings.api_prefix)