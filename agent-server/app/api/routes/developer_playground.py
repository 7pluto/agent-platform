from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import ensure_resource_action, require_resource_developer
from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.providers import knowledge_provider_registry
from app.knowledge.providers.context import resolve_knowledge_provider_config
from app.mcp.service import mcp_auth_headers, mcp_client
from app.resources.openai_compatible import OpenAICompatibleModel
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType, ResourceVersionRecord
from app.resources.registry_store import ResourceRegistryStore
from app.resources.store_factory import get_resource_store
from app.runtime.dify_flow import DifyFlowClient
from app.runtime.http_tool import http_tool_client
from app.runtime.native_tools import native_tools

router = APIRouter(prefix="/developer/playground", tags=["developer-resource-playground"])
registry = get_resource_registry()


class PlaygroundRunRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str = Field(default="", max_length=20_000)
    model_version_id: UUID | None = None
    top_k: int = Field(default=3, ge=1, le=10)


class PlaygroundToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    output: Any


class PlaygroundRunResponse(BaseModel):
    resource_version_id: UUID
    resource_type: str
    kind: str
    mode: str
    elapsed_ms: int
    output: Any
    tool_calls: list[PlaygroundToolCall] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


async def _authorized_model(model_version_id: UUID, principal: Principal) -> OpenAICompatibleModel:
    await ensure_resource_action(principal, "USE", "MODEL", str(model_version_id))
    version = await get_resource_store().get_model_version(model_version_id, principal, require_available=True)
    return await OpenAICompatibleModel.from_runtime_config(version.config, principal.tenant_id, principal.external_user_id)


async def _knowledge_search(record: ResourceVersionRecord, query: str, top_k: int, principal: Principal) -> dict[str, Any]:
    if record.resource_type != ResourceType.KNOWLEDGE:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource is not Knowledge")
    await ensure_resource_action(principal, "USE", ResourceType.KNOWLEDGE.value, str(record.resource_version_id))
    config = await resolve_knowledge_provider_config(record, principal)
    result = await knowledge_provider_registry.resolve(config, principal).search(
        knowledge_version_id=str(record.resource_version_id),
        config=config,
        query=query,
        top_k=top_k,
    )
    return result.model_dump(mode="json")


async def _execute_tool(record: ResourceVersionRecord, arguments: dict[str, Any], principal: Principal) -> dict[str, Any]:
    if record.resource_type != ResourceType.TOOL:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource is not Tool")
    await ensure_resource_action(principal, "USE", ResourceType.TOOL.value, str(record.resource_version_id))
    config = record.config
    kind = str(config.get("kind") or "")
    if kind == "NATIVE":
        native_name = str(config.get("native_name") or "")
        if not native_name:
            raise ApiError(422, "INVALID_TOOL_CONFIG", "Native Tool is missing native_name")
        return await native_tools.invoke(native_name, arguments)
    if kind == "MCP":
        raw_connection = config.get("connection_version_id")
        if not isinstance(raw_connection, str):
            raise ApiError(422, "INVALID_TOOL_CONFIG", "MCP Tool is missing connection version")
        connection_id = UUID(raw_connection)
        connection = await registry.get_version(connection_id, principal, published=True)
        if connection.resource_type != ResourceType.MCP_CONNECTION:
            raise ApiError(422, "INVALID_TOOL_CONFIG", "MCP Tool connection must be MCP_CONNECTION")
        await ensure_resource_action(principal, "USE", ResourceType.MCP_CONNECTION.value, str(connection_id))
        ResourceRegistryStore._validate(ResourceType.MCP_CONNECTION, connection.config)
        headers = await mcp_auth_headers(connection.config, principal.tenant_id, principal.external_user_id)
        return await mcp_client.invoke(
            str(connection.config["endpoint"]),
            str(config.get("tool_name") or ""),
            arguments,
            float(connection.config.get("timeout_seconds", 10)),
            headers,
            connection.config.get("egress_allowlist", []),
        )
    if kind == "DIFY_FLOW":
        runtime_arguments = {
            **arguments,
            "_static_inputs": config.get("static_inputs", {}),
            "_query_input_name": config.get("query_input_name", "query"),
        }
        client = await DifyFlowClient.from_runtime_config(config, principal.tenant_id, principal.external_user_id)
        return await client.invoke(runtime_arguments, user_id=f"playground:{principal.tenant_id}:{principal.external_user_id}")
    if kind == "HTTP":
        return await http_tool_client.invoke(config, arguments, principal.tenant_id, principal.external_user_id)
    raise ApiError(422, "PLAYGROUND_TOOL_UNSUPPORTED", f"unsupported Tool kind: {kind or 'UNKNOWN'}")


def _tool_name(record: ResourceVersionRecord) -> str:
    config = record.config
    return str(config.get("tool_name") or config.get("native_name") or f"tool_{str(record.resource_version_id).replace('-', '')[:8]}")


def _tool_spec(record: ResourceVersionRecord, name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": str(record.config.get("description") or name),
            "parameters": record.config.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


def _knowledge_spec(record: ResourceVersionRecord, name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Search this approved Knowledge resource when the test question needs its internal content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    }


async def _run_skill_with_model(
    skill: ResourceVersionRecord,
    request: PlaygroundRunRequest,
    principal: Principal,
) -> tuple[str, list[PlaygroundToolCall], dict[str, Any]]:
    if request.model_version_id is None:
        raise ApiError(422, "PLAYGROUND_MODEL_REQUIRED", "Skill execution requires a test Model")
    model = await _authorized_model(request.model_version_id, principal)
    message = request.message.strip()
    if not message:
        raise ApiError(422, "PLAYGROUND_MESSAGE_REQUIRED", "Skill execution requires a test message")

    specs: list[dict[str, Any]] = []
    executors: dict[str, tuple[str, ResourceVersionRecord]] = {}
    dependency_summary: list[dict[str, str]] = []

    for raw in skill.config.get("tool_version_ids", []):
        record = await registry.get_version(UUID(str(raw)), principal, published=True)
        if record.resource_type != ResourceType.TOOL:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "Skill Tool dependency is invalid")
        await ensure_resource_action(principal, "USE", ResourceType.TOOL.value, str(record.resource_version_id))
        base_name = _tool_name(record)
        name = base_name
        suffix = 2
        while name in executors:
            name = f"{base_name}_{suffix}"
            suffix += 1
        specs.append(_tool_spec(record, name))
        executors[name] = ("TOOL", record)
        dependency_summary.append({"type": "TOOL", "name": name, "version_id": str(record.resource_version_id)})

    for raw in skill.config.get("knowledge_version_ids", []):
        record = await registry.get_version(UUID(str(raw)), principal, published=True)
        if record.resource_type != ResourceType.KNOWLEDGE:
            raise ApiError(422, "SKILL_DEPENDENCY_TYPE_MISMATCH", "Skill Knowledge dependency is invalid")
        await ensure_resource_action(principal, "USE", ResourceType.KNOWLEDGE.value, str(record.resource_version_id))
        name = f"knowledge_search_{str(record.resource_version_id).replace('-', '')[:8]}"
        specs.append(_knowledge_spec(record, name))
        executors[name] = ("KNOWLEDGE", record)
        dependency_summary.append({"type": "KNOWLEDGE", "name": name, "version_id": str(record.resource_version_id)})

    system_prompt = str(skill.config.get("skill_md") or "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    trace: list[PlaygroundToolCall] = []

    for _ in range(5):
        response = await model.chat(messages, specs or None)
        reply = response["choices"][0].get("message", {})
        calls = reply.get("tool_calls", [])
        if not isinstance(calls, list) or not calls:
            return str(reply.get("content") or ""), trace, {"dependencies": dependency_summary}
        messages.append(reply)
        for call in calls:
            name = str(call.get("function", {}).get("name") or "")
            if name not in executors:
                raise ApiError(422, "PLAYGROUND_TOOL_NOT_IN_SKILL", f"model requested undeclared Skill dependency: {name}")
            raw_arguments = call.get("function", {}).get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError as exc:
                raise ApiError(422, "PLAYGROUND_TOOL_ARGUMENTS_INVALID", f"model produced invalid arguments for {name}") from exc
            if not isinstance(arguments, dict):
                raise ApiError(422, "PLAYGROUND_TOOL_ARGUMENTS_INVALID", f"tool arguments for {name} must be an object")
            dependency_type, record = executors[name]
            if dependency_type == "TOOL":
                output = await _execute_tool(record, arguments, principal)
            else:
                query = str(arguments.get("query") or message)
                top_k = max(1, min(int(arguments.get("top_k", request.top_k)), 10))
                output = await _knowledge_search(record, query, top_k, principal)
            trace.append(PlaygroundToolCall(name=name, arguments=arguments, output=output))
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id"),
                "content": json.dumps(output, ensure_ascii=False)[:20_000],
            })
    raise ApiError(422, "PLAYGROUND_TOOL_BUDGET_EXCEEDED", "Skill playground exceeded the five-step Tool budget")


@router.post("/{resource_version_id}/run", response_model=PlaygroundRunResponse)
async def run_resource_playground(
    resource_version_id: UUID,
    request: PlaygroundRunRequest,
    principal: Principal = Depends(require_resource_developer),
) -> PlaygroundRunResponse:
    record = await registry.get_version(resource_version_id, principal, published=True)
    await ensure_resource_action(principal, "USE", record.resource_type.value, str(resource_version_id))
    started = perf_counter()
    tool_calls: list[PlaygroundToolCall] = []
    metadata: dict[str, Any] = {}

    if record.resource_type == ResourceType.TOOL:
        output = await _execute_tool(record, request.arguments, principal)
        kind = str(record.config.get("kind") or "TOOL")
        mode = "EXECUTE"
    elif record.resource_type == ResourceType.KNOWLEDGE:
        query = request.message.strip() or str(request.arguments.get("query") or "").strip()
        if not query:
            raise ApiError(422, "PLAYGROUND_QUERY_REQUIRED", "Knowledge test requires a query")
        output = await _knowledge_search(record, query, request.top_k, principal)
        kind = str(record.config.get("provider") or "KNOWLEDGE")
        mode = "RETRIEVAL"
    elif record.resource_type == ResourceType.PROMPT:
        system_prompt = str(record.config.get("template") or "")
        if request.model_version_id is None:
            output = {"system_prompt": system_prompt, "message": request.message}
            mode = "PREVIEW"
        else:
            model = await _authorized_model(request.model_version_id, principal)
            output = await model.complete(system_prompt=system_prompt, message=request.message or "请根据该 Prompt 做一次测试回答。")
            mode = "MODEL_EXECUTE"
        kind = "PROMPT"
    elif record.resource_type == ResourceType.SKILL:
        if request.model_version_id is None:
            output = {
                "skill_md": str(record.config.get("skill_md") or ""),
                "tool_version_ids": list(record.config.get("tool_version_ids", [])),
                "knowledge_version_ids": list(record.config.get("knowledge_version_ids", [])),
                "message": request.message,
            }
            mode = "PREVIEW"
            metadata = {"message": "选择测试 Model 后可真实执行 Skill 及其依赖。"}
        else:
            output, tool_calls, metadata = await _run_skill_with_model(record, request, principal)
            mode = "MODEL_EXECUTE"
        kind = "SKILL"
    else:
        raise ApiError(422, "PLAYGROUND_RESOURCE_UNSUPPORTED", "Playground supports Prompt, Skill, Tool and Knowledge")

    return PlaygroundRunResponse(
        resource_version_id=resource_version_id,
        resource_type=record.resource_type.value,
        kind=kind,
        mode=mode,
        elapsed_ms=round((perf_counter() - started) * 1000),
        output=output,
        tool_calls=tool_calls,
        metadata=metadata,
    )
