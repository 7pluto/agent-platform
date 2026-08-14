#!/usr/bin/env python3
"""Offline Worker smoke test for malformed model Tool argument recovery."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import MethodType
from uuid import uuid4

from app.runtime.adapter import OpenAICompatibleRuntimeAdapter, RuntimeContext
from app.runtime.manifest import build_execution_manifest
from app.runtime.models import RunRecord


class FakeModel:
    model = "offline-fake-model"

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "bad-call", "type": "function", "function": {"name": "echo", "arguments": '{"text":'}}]}}]}
        assert messages[-1]["role"] == "tool"
        assert "retry" in messages[-1]["content"]
        return {"choices": [{"message": {"role": "assistant", "content": "recovered"}}]}


async def main() -> None:
    run = RunRecord(tenant_id="offline-test", user_id="offline-user", deployment_id=uuid4(), thread_id=uuid4(), message="offline recovery test", created_at=datetime.now(timezone.utc))
    run.execution_manifest = build_execution_manifest(run, harness_type="openai-compatible")
    model = FakeModel()
    adapter = OpenAICompatibleRuntimeAdapter(model)  # type: ignore[arg-type]

    async def manifest_tools(self, context):
        return ([{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}], {"echo": {"kind": "NATIVE"}})

    adapter._manifest_tools = MethodType(manifest_tools, adapter)  # type: ignore[method-assign]
    events: list[str] = []

    async def emit(event, data):
        events.append(event)

    async def not_cancelled():
        return False

    result = await adapter.execute(RuntimeContext(run=run, manifest=run.execution_manifest), emit, not_cancelled)
    assert result.output == "recovered"
    assert model.calls == 2
    assert "tool.arguments.invalid" in events
    print({"output": result.output, "model_calls": model.calls, "invalid_argument_events": events.count("tool.arguments.invalid")})


asyncio.run(main())
