from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.core.errors import ApiError
from app.resources.openai_compatible import OpenAICompatibleModel
from app.runtime.native_tools import native_tools
from app.memory.store import MemoryStore
from app.knowledge.providers import knowledge_provider_registry
from app.knowledge.providers.context import resolve_knowledge_provider_config
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType
from app.resources.registry_store import ResourceRegistryStore
from app.mcp.service import mcp_auth_headers, mcp_client
from app.runtime.models import ExecutionManifest, RunRecord
from app.runtime.observation import observation_policy
from app.runtime.dify_flow import DifyFlowClient
from app.runtime.http_tool import http_tool_client
from app.conversation.store_factory import get_conversation_store


class RuntimeCancelled(Exception):
    """Raised when a runtime reaches a safe cancellation boundary."""


class RuntimeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: RunRecord
    manifest: ExecutionManifest


class RuntimeResult(BaseModel):
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)


EmitEvent = Callable[[str, dict[str, Any]], Awaitable[None]]
IsCancelled = Callable[[], Awaitable[bool]]


class RuntimeAdapter(ABC):
    harness_type = "unknown"
    version = "0.0.0"

    @abstractmethod
    async def execute(self, context: RuntimeContext, emit: EmitEvent, is_cancelled: IsCancelled) -> RuntimeResult:
        raise NotImplementedError

    async def emit_started(self, context: RuntimeContext, emit: EmitEvent) -> None:
        await emit(
            "runtime.started",
            {
                "harness": self.harness_type,
                "harness_version": self.version,
                "manifest_hash": context.manifest.manifest_hash,
            },
        )
        if context.manifest.resources:
            await emit(
                "manifest.resources.resolved",
                {
                    "resources": [resource.model_dump() for resource in context.manifest.resources],
                    "deployment_revision_id": str(context.manifest.deployment_revision_id) if context.manifest.deployment_revision_id else None,
                },
            )


class MockRuntimeAdapter(RuntimeAdapter):
    """Deterministic development adapter used when no external harness is selected."""

    harness_type = "mock"
    version = "0.1.0"

    async def execute(self, context: RuntimeContext, emit: EmitEvent, is_cancelled: IsCancelled) -> RuntimeResult:
        await self.emit_started(context, emit)
        if await is_cancelled():
            raise RuntimeCancelled
        await asyncio.sleep(0)
        if await is_cancelled():
            raise RuntimeCancelled
        output = f"Mock response: {context.run.message}"
        await emit("runtime.output", {"content": output})
        return RuntimeResult(output=output, metadata={"mode": "deterministic"})


class OpenAICompatibleRuntimeAdapter(RuntimeAdapter):
    """Executes a manifest-bound model through an official LangGraph graph."""

    harness_type = "openai-compatible"
    version = "1.0.0"

    def __init__(self, model: OpenAICompatibleModel) -> None:
        self._model = model

    async def execute(self, context: RuntimeContext, emit: EmitEvent, is_cancelled: IsCancelled) -> RuntimeResult:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError("langgraph is required for the OpenAI-compatible runtime") from exc
        await self.emit_started(context, emit)
        if await is_cancelled():
            raise RuntimeCancelled
        prompt = str(context.manifest.resource_versions.get("system_prompt", ""))
        resource_types = {resource.type for resource in context.manifest.resources}
        skill_instructions: list[str] = []
        if context.manifest.schema_version == "3":
            principal = Principal(provider="runtime", external_user_id=context.run.user_id, external_org_id="runtime", tenant_id=context.run.tenant_id, display_name="Runtime")
            for resource in context.manifest.resources:
                if resource.type != ResourceType.SKILL.value:
                    continue
                version = await get_resource_registry().get_version(UUID(resource.version_id), principal, published=True)
                skill_md = str(version.config.get("skill_md") or "").strip()
                if skill_md:
                    skill_instructions.append(skill_md)
            if skill_instructions:
                prompt = f"{prompt}\n\nApproved Skills (follow when relevant):\n" + "\n\n".join(skill_instructions)
                await emit("skills.loaded", {"count": len(skill_instructions), "mode": "assembly"})
        if "MEMORY_POLICY" in resource_types:
            memories = await MemoryStore().list_for_runtime(
                context.run.tenant_id, context.run.deployment_id, context.run.user_id
            )
            if memories:
                prompt = f"{prompt}\n\nUser memory (use only when relevant):\n" + "\n".join(f"- {item.content}" for item in memories)
            await emit("memory.read", {"count": len(memories)})
        tool_specs, tool_configs = await self._manifest_tools(context)
        filtered_capability_count = sum(
            1
            for resource in context.manifest.resources
            if resource.type in {ResourceType.TOOL.value, ResourceType.KNOWLEDGE.value, ResourceType.MCP_CONNECTION.value}
            and not resource.use_allowed
        )
        await emit("runtime.capabilities.registered", {
            "tools": [spec["function"]["name"] for spec in tool_specs],
            "tool_count": len(tool_specs),
            "available_tools": list(tool_configs),
            # Do not expose the names of denied capabilities to the model or
            # ordinary user trace.  The count is retained for operations.
            "filtered_capability_count": filtered_capability_count,
            "memory_loaded": "MEMORY_POLICY" in resource_types,
        })

        class _ModelState(TypedDict, total=False):
            message: str
            output: str

        async def call_model(state: _ModelState) -> _ModelState:
            if await is_cancelled():
                raise RuntimeCancelled
            principal = Principal(provider="runtime", external_user_id=context.run.user_id, external_org_id="runtime", tenant_id=context.run.tenant_id, display_name="Runtime")
            try:
                history = await get_conversation_store().list_messages(context.run.thread_id, principal)
            except ApiError as exc:
                if exc.code != "NOT_FOUND":
                    raise
                history = []  # Compatibility for historical/debug Runs without a Conversation row.
            history = [item for item in history if item.source_run_id != context.run.run_id]
            history = history[-20:]
            total = sum(len(item.content) for item in history)
            trimmed = False
            while history and total > 40_000:
                removed = history.pop(0)
                total -= len(removed.content)
                trimmed = True
            await emit("conversation.history.loaded", {"count": len(history), "characters": total, "trimmed": trimmed})
            history_messages = [{"role": item.role.value.lower(), "content": item.content} for item in history]
            messages: list[dict[str, Any]] = ([{"role": "system", "content": prompt}] if prompt else []) + history_messages + [{"role": "user", "content": state["message"]}]
            tool_steps = 0
            while True:
                response = await self._model.chat(messages, tool_specs or None)
                message = response["choices"][0].get("message", {})
                calls = message.get("tool_calls", [])
                if not isinstance(calls, list) or not calls:
                    return {"output": str(message.get("content") or "")}
                if tool_steps + len(calls) > 6:
                    raise ApiError(422, "RUN_TOOL_BUDGET_EXCEEDED", "Run exceeded the six-call Tool budget")
                messages.append(message)
                for call in calls:
                    name = call.get("function", {}).get("name")
                    raw = call.get("function", {}).get("arguments", "{}")
                    try:
                        arguments = json.loads(raw) if isinstance(raw, str) else {}
                    except json.JSONDecodeError:
                        await emit("tool.arguments.invalid", {"tool": name, "code": "MODEL_INVALID_TOOL_ARGUMENTS"})
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "content": json.dumps({"error": "arguments must be a valid JSON object; retry this tool call with corrected JSON"}),
                        })
                        tool_steps += 1
                        continue
                    if not isinstance(arguments, dict):
                        await emit("tool.arguments.invalid", {"tool": name, "code": "MODEL_INVALID_TOOL_ARGUMENTS"})
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "content": json.dumps({"error": "arguments must be a JSON object; retry this tool call with corrected JSON"}),
                        })
                        tool_steps += 1
                        continue
                    await emit("tool.started", {"tool": name, "arguments": arguments})
                    result = await self._invoke_manifest_tool(name, arguments, tool_configs, context, emit)
                    await emit("tool.completed", {"tool": name, "output": result})
                    if configs := tool_configs.get(str(name)):
                        if configs.get("kind") == "DIFY_FLOW":
                            resources = result.get("retriever_resources", [])
                            await emit("dify.flow.completed", {"tool": name, "retriever_resource_count": len(resources), "conversation_id": result.get("conversation_id"), "workflow_run_id": result.get("workflow_run_id")})
                            if resources:
                                await emit("dify.rag.retrieved", {"tool": name, "resources": resources})
                    # The model receives a bounded observation. The Worker applies the
                    # same ObservationPolicy to persisted trace events, so neither path
                    # records unbounded upstream payloads or credentials.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps(observation_policy.bound_model_observation(self._model_tool_observation(configs.get(str(name), {}), result)), ensure_ascii=False),
                    })
                    tool_steps += 1

        graph = StateGraph(_ModelState)
        graph.add_node("model", call_model)
        graph.add_edge(START, "model")
        graph.add_edge("model", END)
        compiled = graph.compile()
        output = ""
        async for update in compiled.astream({"message": context.run.message}, stream_mode="updates"):
            if await is_cancelled():
                raise RuntimeCancelled
            for node, state in update.items():
                output = state.get("output", output)
                await emit("runtime.step", {"node": node})
        if not output:
            raise RuntimeError("LangGraph model node completed without output")
        await emit("runtime.output", {"content": output})
        return RuntimeResult(output=output, metadata={"mode": "langgraph-openai-compatible", "model": self._model.model})

    @staticmethod
    def _model_tool_observation(config: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        """Return the smallest useful tool observation for the next model turn."""
        if isinstance(result.get("error"), dict):
            return {"error": result["error"]}
        if config.get("kind") == "DIFY_FLOW":
            answer = result.get("answer")
            resources = result.get("retriever_resources")
            observation = {
                "answer": answer if isinstance(answer, str) else None,
                "workflow_run_id": result.get("workflow_run_id"),
                "retrieval_count": len(resources) if isinstance(resources, list) else 0,
            }
            if isinstance(result.get("outputs"), dict):
                observation["outputs"] = result["outputs"]
            if result.get("status") is not None:
                observation["status"] = result["status"]
            return observation
        if config.get("kind") == "KNOWLEDGE":
            hits = result.get("hits")
            if not isinstance(hits, list):
                return {"retrieval_count": 0}
            summaries = []
            for hit in hits[:5]:
                if not isinstance(hit, dict):
                    continue
                text = str(hit.get("content") or hit.get("text") or "")
                summaries.append({"document": hit.get("document_name") or hit.get("document_id"), "content": text[:1_500]})
            return {"retrieval_count": len(hits), "hits": summaries}
        return result

    async def _manifest_tools(self, context: RuntimeContext) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        principal = Principal(provider="runtime", external_user_id=context.run.user_id, external_org_id="runtime", tenant_id=context.run.tenant_id, display_name="Runtime")
        specs: list[dict[str, Any]] = []
        configs: dict[str, dict[str, Any]] = {}
        resource_access = {resource.version_id: resource.use_allowed for resource in context.manifest.resources}
        knowledge_definitions = {
            definition.resource_id: definition
            for definition in await get_resource_registry().list_definitions(principal, ResourceType.KNOWLEDGE)
        }
        for resource in context.manifest.resources:
            if resource.type == ResourceType.SKILL.value:
                if context.manifest.schema_version == "3":
                    # V3 composes Skill guidance into the system context instead
                    # of exposing a pseudo-tool the model has to remember to call.
                    continue
                version = await get_resource_registry().get_version(UUID(resource.version_id), principal, published=True)
                name = f"skill_use_{str(resource.version_id).replace('-', '')[:8]}"
                configs[name] = {"kind": "SKILL", "skill_md": str(version.config.get("skill_md") or "")}
                specs.append({"type": "function", "function": {"name": name, "description": "Apply this approved Skill when its workflow matches the user request.", "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []}}})
                continue
            if resource.type == ResourceType.KNOWLEDGE.value:
                if not resource.use_allowed:
                    # A denied KB is not a model-visible tool. This prevents a
                    # user from learning that another department's KB exists.
                    continue
                # Names live on the immutable Definition, while the Manifest
                # carries a Version.  Only allowed Knowledge entries reach
                # this branch, so this does not disclose restricted KB names.
                definition = knowledge_definitions.get(UUID(resource.resource_id))
                knowledge_name = definition.display_name if definition else "knowledge base"
                version = await get_resource_registry().get_version(UUID(resource.version_id), principal, published=True)
                knowledge_config = await resolve_knowledge_provider_config(version, principal)
                name = f"knowledge_search_{str(resource.version_id).replace('-', '')[:8]}"
                configs[name] = {
                    "kind": "KNOWLEDGE",
                    "knowledge_version_id": resource.version_id,
                    "knowledge_config": knowledge_config,
                    "resource_version_id": resource.version_id,
                    "use_allowed": resource.use_allowed,
                    "resource_type": ResourceType.KNOWLEDGE.value,
                    "resource_name": knowledge_name,
                }
                specs.append({"type": "function", "function": {"name": name, "description": f"Search the knowledge base ‘{knowledge_name}’ when the user asks about its internal documents or policies.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search question"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 5}}, "required": ["query"]}}})
                continue
            if resource.type != ResourceType.TOOL.value:
                continue
            if not resource.use_allowed:
                # The Tool itself is not USE-authorized. Keep its denial in
                # the immutable manifest for audit, but never reveal it to
                # the model function registry.
                continue
            version = await get_resource_registry().get_version(UUID(resource.version_id), principal, published=True)
            config = version.config
            tool_use_allowed = resource.use_allowed
            if config.get("kind") == "MCP":
                connection_id = config.get("connection_version_id")
                if not isinstance(connection_id, str):
                    raise ApiError(422, "INVALID_TOOL_CONFIG", "MCP tool is missing connection version")
                connection = await get_resource_registry().get_version(UUID(connection_id), principal, published=True)
                if connection.resource_type != ResourceType.MCP_CONNECTION:
                    raise ApiError(422, "INVALID_TOOL_CONFIG", "MCP tool connection must be MCP_CONNECTION")
                ResourceRegistryStore._validate(ResourceType.MCP_CONNECTION, connection.config)
                if not resource_access.get(connection_id, True):
                    # A Tool cannot reveal or use a connector that the user
                    # does not have permission to use.
                    continue
                config = {
                    **config,
                    **connection.config,
                    "connection_version_id": connection_id,
                    "connection_use_allowed": resource_access.get(connection_id, True),
                }
            name = str(config.get("native_name") or config.get("tool_name") or "")
            schema = config.get("input_schema", {"type": "object", "properties": {}})
            if not name or name in configs:
                continue
            configs[name] = {
                **config,
                "resource_version_id": resource.version_id,
                "resource_type": ResourceType.TOOL.value,
                "use_allowed": tool_use_allowed,
            }
            specs.append({"type": "function", "function": {"name": name, "description": str(config.get("description", name)), "parameters": schema}})
        return specs, configs

    async def _invoke_manifest_tool(
        self,
        name: str | None,
        arguments: dict[str, Any],
        configs: dict[str, dict[str, Any]],
        context: RuntimeContext,
        emit: EmitEvent,
    ) -> dict[str, Any]:
        if not name or name not in configs:
            raise ApiError(403, "TOOL_NOT_IN_MANIFEST", "tool is not available to this Run")
        config = configs[name]
        if not config.get("use_allowed", True):
            return await self._denied_tool_result(name, config, emit)
        if config.get("kind") == "MCP" and not config.get("connection_use_allowed", True):
            return await self._denied_tool_result(name, config, emit, resource_type=ResourceType.MCP_CONNECTION.value)
        if config["kind"] == "NATIVE":
            return await native_tools.invoke(name, arguments)
        if config["kind"] == "SKILL":
            await emit("skills.loaded", {"count": 1, "tool": name})
            return {"skill_instructions": config["skill_md"]}
        if config["kind"] == "MCP":
            headers = await mcp_auth_headers(config, context.run.tenant_id, context.run.user_id)
            return await mcp_client.invoke(config["endpoint"], name, arguments, float(config.get("timeout_seconds", 10)), headers, config["egress_allowlist"])
        if config["kind"] == "DIFY_FLOW":
            runtime_arguments = {
                **arguments,
                "_static_inputs": config.get("static_inputs", {}),
                "_query_input_name": config.get("query_input_name", "query"),
            }
            return await (await DifyFlowClient.from_runtime_config(config, context.run.tenant_id, context.run.user_id)).invoke(
                runtime_arguments,
                user_id=f"{context.run.tenant_id}:{context.run.user_id}",
            )
        if config["kind"] == "HTTP":
            return await http_tool_client.invoke(config, arguments, context.run.tenant_id, context.run.user_id)
        if config["kind"] == "KNOWLEDGE":
            principal = Principal(provider="runtime", external_user_id=context.run.user_id, external_org_id="runtime", tenant_id=context.run.tenant_id, display_name="Runtime")
            query = str(arguments.get("query") or context.run.message)
            top_k = max(1, min(int(arguments.get("top_k", 3)), 5))
            result = await knowledge_provider_registry.resolve(dict(config.get("knowledge_config") or {}), principal).search(
                knowledge_version_id=str(config["knowledge_version_id"]),
                config=dict(config.get("knowledge_config") or {}),
                query=query,
                top_k=top_k,
            )
            await emit("rag.retrieved", {
                "knowledge_version_id": config["knowledge_version_id"],
                "provider": result.provider,
                "index_version_id": result.metadata.get("index_version_id"),
                "chunk_count": len(result.hits),
                "query": query,
            })
            return result.model_dump(mode="json")
        raise ApiError(422, "INVALID_TOOL_CONFIG", "tool config is not executable")

    @staticmethod
    async def _denied_tool_result(
        name: str,
        config: dict[str, Any],
        emit: EmitEvent,
        *,
        resource_type: str | None = None,
    ) -> dict[str, Any]:
        denied_type = resource_type or str(config.get("resource_type") or "TOOL")
        message = "当前账号没有使用此能力的权限；请改用其他已授权能力，或直接说明无法访问该信息。"
        await emit("tool.denied", {
            "tool": name,
            "code": "RESOURCE_FORBIDDEN",
            "resource_type": denied_type,
            "resource_version_id": config.get("connection_version_id") if denied_type == ResourceType.MCP_CONNECTION.value else config.get("resource_version_id"),
            "message": message,
        })
        return {
            "error": {
                "code": "RESOURCE_FORBIDDEN",
                "message": message,
                "resource_type": denied_type,
                "tool": name,
            }
        }


class NativeToolRuntimeAdapter(RuntimeAdapter):
    """Manifest-driven deterministic native tool path used in runtime tests/debug."""

    harness_type = "native-tools"
    version = "1.0.0"

    async def execute(self, context: RuntimeContext, emit: EmitEvent, is_cancelled: IsCancelled) -> RuntimeResult:
        await self.emit_started(context, emit)
        if await is_cancelled():
            raise RuntimeCancelled
        output = await native_tools.invoke("echo", {"value": context.run.message})
        await emit("tool.completed", {"tool": "echo", "output": output})
        await emit("runtime.output", {"content": str(output["value"])})
        return RuntimeResult(output=str(output["value"]), metadata={"mode": "native-tools"})

class _BaselineState(TypedDict, total=False):
    message: str
    output: str


class LangGraphBaselineAdapter(RuntimeAdapter):
    """Official LangGraph baseline with no model provider dependency."""

    harness_type = "langgraph"

    def __init__(self) -> None:
        try:
            self.version = version("langgraph")
        except PackageNotFoundError:
            self.version = "unknown"

    async def execute(self, context: RuntimeContext, emit: EmitEvent, is_cancelled: IsCancelled) -> RuntimeResult:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError("langgraph is required for the langgraph_baseline harness") from exc

        await self.emit_started(context, emit)
        if await is_cancelled():
            raise RuntimeCancelled

        def respond(state: _BaselineState) -> _BaselineState:
            return {"output": f"LangGraph baseline response: {state['message']}"}

        graph = StateGraph(_BaselineState)
        graph.add_node("respond", respond)
        graph.add_edge(START, "respond")
        graph.add_edge("respond", END)
        compiled = graph.compile()
        output = ""
        async for update in compiled.astream({"message": context.run.message}, stream_mode="updates"):
            if await is_cancelled():
                raise RuntimeCancelled
            for node, state in update.items():
                output = state.get("output", output)
                await emit("runtime.step", {"node": node})
        if not output:
            raise RuntimeError("LangGraph baseline completed without output")
        await emit("runtime.output", {"content": output})
        return RuntimeResult(output=output, metadata={"mode": "langgraph_baseline"})


class RuntimeExecutor:
    """Small orchestration boundary kept independent from FastAPI and persistence."""

    def __init__(self, adapter: RuntimeAdapter | None = None) -> None:
        self.adapter = adapter

    async def execute(self, run: RunRecord, emit: EmitEvent, is_cancelled: IsCancelled) -> RuntimeResult:
        if run.execution_manifest is None:
            raise ValueError("run has no execution manifest")
        adapter = self.adapter
        if adapter is None:
            if run.execution_manifest.harness.type == "openai-compatible":
                config = run.execution_manifest.resource_versions.get("model_config")
                if not config:
                    raise ValueError("model configuration is missing from execution manifest")
                model_config = json.loads(config)
                model = await OpenAICompatibleModel.from_runtime_config(model_config, run.tenant_id, run.user_id)
                adapter = OpenAICompatibleRuntimeAdapter(model)
            else:
                adapter = LangGraphBaselineAdapter() if get_settings().runtime_harness == "langgraph_baseline" else MockRuntimeAdapter()
        return await adapter.execute(RuntimeContext(run=run, manifest=run.execution_manifest), emit, is_cancelled)
