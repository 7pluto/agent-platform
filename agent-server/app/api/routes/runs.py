from __future__ import annotations

import asyncio
import json
import json as json_module
from collections import Counter
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import ensure_resource_action, require_fresh_mutation_principal, require_fresh_principal, require_platform_admin_read
from app.config import get_settings
from app.control_plane.store_factory import get_control_plane_store
from app.control_plane.specification import model_version_reference
from app.conversation.models import MessageCreate, MessageRole
from app.conversation.store_factory import get_conversation_store
from app.core.errors import ApiError
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.runtime.manifest import build_execution_manifest
from app.resources.store_factory import get_resource_store
from app.control_plane.assembly import is_resource_assembly_v2, resolve_agent_assembly_for_run, validate_agent_assembly
from app.runtime.models import ExecutionManifest, RunCreateRequest, RunDetail, RunEvent, RunRecord
from app.runtime.store_factory import get_run_store
from app.runtime.worker import get_runtime_worker

router = APIRouter(prefix="", tags=["runs"])
run_store = get_run_store()
control_plane_store = get_control_plane_store()
conversation_store = get_conversation_store()
governance_store = get_governance_store()
runtime_worker = get_runtime_worker()
resource_store = get_resource_store()


class RunObservabilitySummary(BaseModel):
    sampled_runs: int
    status_counts: dict[str, int]
    terminal_runs: int
    completion_rate: float | None = None
    average_duration_ms: int | None = None
    tool_calls: int
    rag_retrievals: int
    denied_capability_calls: int
    failed_runs: int
    generated_at: datetime


def summarize_run_observability(records: list[tuple[RunRecord, list[RunEvent]]]) -> RunObservabilitySummary:
    """Aggregate trace metadata only; prompts, outputs and tool arguments stay private."""
    statuses = Counter(record.status.value for record, _ in records)
    durations: list[float] = []
    tool_calls = rag_retrievals = denied = 0
    terminal = {"COMPLETED", "FAILED", "CANCELLED"}
    for record, events in records:
        started = next((event.occurred_at for event in events if event.event == "run.started"), None)
        finished = next((event.occurred_at for event in reversed(events) if event.event in {"run.completed", "run.failed", "run.cancelled"}), None)
        if started and finished and finished >= started:
            durations.append((finished - started).total_seconds() * 1000)
        tool_calls += sum(1 for event in events if event.event == "tool.started")
        rag_retrievals += sum(1 for event in events if event.event == "rag.retrieved")
        denied += sum(1 for event in events if event.event == "tool.denied")
    terminal_runs = sum(statuses[value] for value in terminal)
    return RunObservabilitySummary(
        sampled_runs=len(records),
        status_counts=dict(statuses),
        terminal_runs=terminal_runs,
        completion_rate=round(statuses["COMPLETED"] / terminal_runs, 4) if terminal_runs else None,
        average_duration_ms=round(sum(durations) / len(durations)) if durations else None,
        tool_calls=tool_calls,
        rag_retrievals=rag_retrievals,
        denied_capability_calls=denied,
        failed_runs=statuses["FAILED"],
        generated_at=datetime.now().astimezone(),
    )


@router.post("/deployments/{deployment_id}/runs", response_model=RunRecord, status_code=202)
async def create_run(
    deployment_id: UUID,
    request: RunCreateRequest,
    principal: Principal = Depends(require_fresh_mutation_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunRecord:
    if request.deployment_id != deployment_id:
        raise ApiError(400, "DEPLOYMENT_MISMATCH", "deployment_id path and body must match")
    if request.conversation_id is not None and request.thread_id is None:
        raise ApiError(400, "THREAD_REQUIRED", "thread_id is required when conversation_id is provided")
    if request.conversation_id is None or request.thread_id is None:
        raise ApiError(400, "CONVERSATION_REQUIRED", "conversation_id and thread_id are required")
    conversation = await conversation_store.get_conversation(request.conversation_id, principal)
    thread = await conversation_store.get_thread(request.thread_id, principal)
    if thread.conversation_id != request.conversation_id:
        raise ApiError(409, "THREAD_CONVERSATION_MISMATCH", "thread does not belong to conversation")
    if conversation.deployment_id != deployment_id:
        raise ApiError(409, "CONVERSATION_DEPLOYMENT_MISMATCH", "conversation does not belong to deployment")
    if not idempotency_key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required")
    await ensure_resource_action(principal, "RUN", "DEPLOYMENT", str(deployment_id))
    resolved = await control_plane_store.resolve(deployment_id, principal)
    assembled_bindings = await resolve_agent_assembly_for_run(resolved.agent_version.specification, principal) if is_resource_assembly_v2(resolved.agent_version.specification) else []
    assembled_resources = [item.resource for item in assembled_bindings]
    configured_model_version_id = model_version_reference(resolved.agent_version.specification)
    configured_model = None
    if configured_model_version_id is not None:
        configured_model = await resource_store.get_model_version(configured_model_version_id, principal, require_available=True)
        if configured_model.config.get("model_mode", "CHAT") != "CHAT":
            raise ApiError(422, "CHAT_MODEL_REQUIRED", "Agent runtime requires a CHAT model version")
    harness_type = "openai-compatible" if configured_model is not None else ("langgraph" if get_settings().runtime_harness == "langgraph_baseline" else "mock")
    prompt_resource = next((item for item in assembled_resources if item.resource_type.value == "PROMPT"), None)
    assembled_secret_refs = {
        f"{item.resource_type.value.lower()}:{item.resource_version_id}": str(item.config["secret_ref"])
        for item in assembled_resources
        if isinstance(item.config.get("secret_ref"), str)
    }

    def manifest_builder(record: RunRecord) -> ExecutionManifest:
        return build_execution_manifest(
            record,
            deployment_revision_id=resolved.revision.deployment_revision_id,
            resource_versions={
                "agent_definition_id": str(resolved.deployment.agent_id),
                "agent_version_id": str(resolved.agent_version.agent_version_id),
                "agent_version_content_hash": resolved.agent_version.content_hash,
                "deployment_revision_id": str(resolved.revision.deployment_revision_id),
                **({"system_prompt": str(prompt_resource.config.get("template", ""))} if configured_model and prompt_resource else {}),
                **({"model_version_id": str(configured_model.model_version_id), "model_version_content_hash": configured_model.content_hash, "model_config": json_module.dumps(configured_model.config, sort_keys=True)} if configured_model else {}),
            },
            policy_versions={"builder": "react@1"},
            secret_refs={**({"model": configured_model.config["secret_ref"]} if configured_model else {}), **assembled_secret_refs},
            resources=(
                ([
                    {
                        "type": "MODEL",
                        "resource_id": str(configured_model.model_id),
                        "version_id": str(configured_model.model_version_id),
                        "content_hash": configured_model.content_hash,
                    }
                ] if configured_model else []) + [
                {
                    "type": binding.resource.resource_type.value,
                    "resource_id": str(binding.resource.resource_id),
                    "version_id": str(binding.resource.resource_version_id),
                    "content_hash": binding.resource.content_hash,
                    "binding_origin": binding.origin,
                    "dependency_path": binding.dependency_path,
                    "use_allowed": binding.use_allowed,
                }
                for binding in assembled_bindings]
            ),
            harness_type=harness_type,
        )

    record = await run_store.create(request, principal, idempotency_key, manifest_builder)
    await conversation_store.create_message(
        record.thread_id,
        MessageCreate(role=MessageRole.USER, content=record.message, source_run_id=record.run_id),
        principal,
    )
    await conversation_store.set_title_if_empty(record.conversation_id, record.message, principal)
    if get_settings().runtime_execution_mode == "in_process":
        runtime_worker.submit(record)
    await governance_store.record_audit(
        principal,
        "run.create",
        "RUN",
        str(record.run_id),
        {"deployment_id": str(deployment_id), "conversation_id": str(record.conversation_id) if record.conversation_id else None, "thread_id": str(record.thread_id), "manifest_hash": record.execution_manifest.manifest_hash},
    )
    return record


@router.get("/runs/{run_id}", response_model=RunRecord)
async def get_run(run_id: UUID, principal: Principal = Depends(require_fresh_principal)) -> RunRecord:
    return await run_store.get(run_id, principal)


@router.get("/runs", response_model=list[RunRecord])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_fresh_principal),
) -> list[RunRecord]:
    return await run_store.list_for_principal(principal, limit)


@router.get("/observability/runs/summary", response_model=RunObservabilitySummary)
async def run_observability_summary(
    limit: int = Query(default=500, ge=1, le=2_000),
    principal: Principal = Depends(require_platform_admin_read),
) -> RunObservabilitySummary:
    """Admin-only tenant metrics derived from Run events, never raw conversation content."""
    runs = await run_store.list_for_tenant(principal, limit)
    records = [(record, await run_store.events_for_tenant(record.run_id, principal)) for record in runs]
    return summarize_run_observability(records)


@router.get("/runs/{run_id}/detail", response_model=RunDetail)
async def get_run_detail(run_id: UUID, principal: Principal = Depends(require_fresh_principal)) -> RunDetail:
    record = await run_store.get(run_id, principal)
    if record.execution_manifest is None:
        raise ApiError(409, "MANIFEST_UNAVAILABLE", "run has no execution manifest")
    return RunDetail(
        run=record,
        manifest=record.execution_manifest,
        events=await run_store.events(run_id, principal),
    )


@router.get("/runs/{run_id}/manifest", response_model=ExecutionManifest)
async def get_manifest(run_id: UUID, principal: Principal = Depends(require_fresh_principal)) -> ExecutionManifest:
    record = await run_store.get(run_id, principal)
    if record.execution_manifest is None:
        raise ApiError(409, "MANIFEST_UNAVAILABLE", "run has no execution manifest")
    return record.execution_manifest


@router.post("/runs/{run_id}/cancel", response_model=RunRecord)
async def cancel_run(run_id: UUID, principal: Principal = Depends(require_fresh_mutation_principal)) -> RunRecord:
    record = await run_store.cancel(run_id, principal)
    await runtime_worker.submit_next(record.thread_id, record.tenant_id, record.user_id)
    return record


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: UUID,
    request: Request,
    principal: Principal = Depends(require_fresh_principal),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    follow: bool = Query(default=False),
) -> StreamingResponse:
    after = _parse_last_event_id(last_event_id)

    async def stream():
        sent = after
        while True:
            events = await run_store.events(run_id, principal, sent)
            for event in events:
                sent = event.sequence
                yield _sse(event)
            if not follow or await _is_terminal(run_id, principal):
                return
            if await request.is_disconnected():
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(10)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



def _parse_last_event_id(value: str | None) -> int:
    if value is None:
        return 0
    try:
        sequence = int(value)
    except ValueError as exc:
        raise ApiError(400, "INVALID_LAST_EVENT_ID", "Last-Event-ID must be a non-negative integer") from exc
    if sequence < 0:
        raise ApiError(400, "INVALID_LAST_EVENT_ID", "Last-Event-ID must be a non-negative integer")
    return sequence
async def _is_terminal(run_id: UUID, principal: Principal) -> bool:
    record = await run_store.get(run_id, principal)
    return record.status.value in {"COMPLETED", "FAILED", "CANCELLED"}


def _sse(event: RunEvent) -> str:
    payload = event.model_dump(mode="json")
    return f"id: {event.sequence}\nevent: {event.event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
