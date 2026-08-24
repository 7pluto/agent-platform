from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.resources.registry_models import ResourceType
from app.runtime.adapter import OpenAICompatibleRuntimeAdapter, RuntimeContext
from app.runtime.manifest import build_execution_manifest
from app.runtime.models import RunRecord


def _load_demo():
    path = Path(__file__).parents[2] / "demo-enterprise-services" / "app.py"
    spec = importlib.util.spec_from_file_location("demo_business_runtime", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


demo = _load_demo()


class ProtocolModel:
    model = "demo-qwen-compatible"

    async def chat(self, messages, tools=None):
        return demo._model_response({"messages": messages, "tools": tools or []})


def _manifest_resource(resource_type: ResourceType, *, allowed: bool = True) -> dict:
    return {
        "type": resource_type.value,
        "resource_id": str(uuid4()),
        "version_id": str(uuid4()),
        "content_hash": uuid4().hex,
        "binding_origin": "DIRECT",
        "use_allowed": allowed,
    }


@pytest.mark.parametrize(("question", "expected_tool"), [
    ("查询客户信息", "query_customer"),
    ("员工考勤管理办法", "knowledge_search_hr"),
    ("查询工单处理状态", "ticket_query"),
    ("使用 Dify 流程查询制度", "dify_enterprise_flow"),
])
def test_business_agent_autonomously_selects_authorized_capability_and_returns_answer(monkeypatch, question: str, expected_tool: str) -> None:
    async def scenario() -> None:
        record = RunRecord(
            tenant_id="tenant-demo", user_id="business-user", deployment_id=uuid4(),
            thread_id=uuid4(), message=question,
        )
        resources = [
            _manifest_resource(ResourceType.SKILL),
            _manifest_resource(ResourceType.MEMORY_POLICY),
            _manifest_resource(ResourceType.TOOL),
            _manifest_resource(ResourceType.KNOWLEDGE),
            _manifest_resource(ResourceType.TOOL, allowed=False),
        ]
        manifest = build_execution_manifest(record, resources=resources, harness_type="openai-compatible")
        record.execution_manifest = manifest
        adapter = OpenAICompatibleRuntimeAdapter(ProtocolModel())  # type: ignore[arg-type]

        tool_specs = [
            {"type": "function", "function": {"name": "query_customer", "description": "查询 CRM 客户", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "knowledge_search_hr", "description": "检索人事制度", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "ticket_query", "description": "查询工单", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "dify_enterprise_flow", "description": "Dify 企业制度流程", "parameters": {"type": "object"}}},
        ]
        tool_configs = {
            "query_customer": {"kind": "MCP"},
            "knowledge_search_hr": {"kind": "KNOWLEDGE"},
            "ticket_query": {"kind": "HTTP"},
            "dify_enterprise_flow": {"kind": "DIFY_FLOW"},
        }

        async def manifest_tools(_context):
            return tool_specs, tool_configs

        async def invoke(name, arguments, configs, context, emit):
            if name == "query_customer":
                return {"customer_id": arguments["customer_id"], "name": "示例客户", "tier": "重点客户"}
            if name == "knowledge_search_hr":
                await emit("rag.retrieved", {"provider": "RAGFLOW", "chunk_count": 1, "query": arguments["query"]})
                return {"hits": [{"content": "异常考勤应在两个工作日内补交说明", "score": 0.94}]}
            if name == "ticket_query":
                return {"ticket": {"id": arguments["ticket_id"], "status": "处理中"}}
            if name == "dify_enterprise_flow":
                return {"answer": "Dify 企业制度流程已完成", "retriever_resources": [{"document_name": "员工考勤管理办法.pdf"}]}
            raise AssertionError(f"unexpected tool {name}")

        class FakeRegistry:
            async def get_version(self, *_args, **_kwargs):
                return SimpleNamespace(config={"skill_md": "# 企业制度查询技能\n优先选择与问题匹配的已授权工具。"})

        class FakeMemoryStore:
            async def list_for_runtime(self, *_args, **_kwargs):
                return [SimpleNamespace(content="所有回答使用简体中文")]

        monkeypatch.setattr(adapter, "_manifest_tools", manifest_tools)
        monkeypatch.setattr(adapter, "_invoke_manifest_tool", invoke)
        monkeypatch.setattr("app.runtime.adapter.get_resource_registry", lambda: FakeRegistry())
        monkeypatch.setattr("app.runtime.adapter.MemoryStore", FakeMemoryStore)

        events: list[tuple[str, dict]] = []

        async def emit(event: str, data: dict) -> None:
            events.append((event, data))

        async def not_cancelled() -> bool:
            return False

        result = await adapter.execute(RuntimeContext(run=record, manifest=manifest), emit, not_cancelled)
        completed = [data["tool"] for event, data in events if event == "tool.completed"]
        registered = next(data for event, data in events if event == "runtime.capabilities.registered")

        assert completed == [expected_tool]
        assert result.output.startswith("已完成业务查询")
        assert registered["filtered_capability_count"] == 1
        assert "finance_denied" not in json.dumps(registered, ensure_ascii=False)
        assert any(event == "skills.loaded" for event, _ in events)
        assert any(event == "memory.read" and data["count"] == 1 for event, data in events)
        if expected_tool == "knowledge_search_hr":
            assert any(event == "rag.retrieved" for event, _ in events)
        if expected_tool == "dify_enterprise_flow":
            assert any(event == "dify.flow.completed" for event, _ in events)

    asyncio.run(scenario())
