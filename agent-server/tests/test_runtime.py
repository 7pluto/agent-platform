import asyncio
from datetime import datetime, timezone
from uuid import uuid4


from app.runtime.adapter import (
    LangGraphBaselineAdapter,
    MockRuntimeAdapter,
    OpenAICompatibleRuntimeAdapter,
    RuntimeCancelled,
    RuntimeContext,
    RuntimeExecutor,
)
from app.api.routes.runs import _parse_last_event_id
from app.core.errors import ApiError
from app.runtime.manifest import build_execution_manifest
from app.runtime.models import RunRecord


def _run_record() -> RunRecord:
    return RunRecord(
        tenant_id="tenant-demo",
        user_id="user-demo",
        deployment_id=uuid4(),
        thread_id=uuid4(),
        message="hello runtime",
    )


def test_execution_manifest_is_bound_and_hash_is_stable() -> None:
    record = _run_record()
    generated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = build_execution_manifest(record, generated_at=generated_at, secret_refs={"model": "secret://model"})
    second = build_execution_manifest(record, generated_at=generated_at, secret_refs={"model": "secret://model"})

    assert first.manifest_hash == second.manifest_hash
    assert first.run_id == record.run_id
    assert first.tenant_id == record.tenant_id
    assert "secret://model" in first.secret_refs.values()
    assert "secret-value" not in first.model_dump_json()


def test_runtime_adapter_emits_deterministic_events_and_honors_cancel() -> None:
    async def run() -> None:
        record = _run_record()
        record.execution_manifest = build_execution_manifest(record)
        events: list[tuple[str, dict]] = []
        result = await RuntimeExecutor().execute(
            record,
            lambda event, data: _collect(events, event, data),
            _not_cancelled,
        )
        assert result.output == "Mock response: hello runtime"
        assert [event for event, _ in events] == ["runtime.started", "runtime.output"]

        cancelled_events: list[tuple[str, dict]] = []
        try:
            await MockRuntimeAdapter().execute(
                RuntimeContext(run=record, manifest=record.execution_manifest),
                lambda event, data: _collect(cancelled_events, event, data),
                _cancelled,
            )
        except RuntimeCancelled:
            pass
        else:
            raise AssertionError("cancelled runtime completed")
        assert cancelled_events[0][0] == "runtime.started"

    asyncio.run(run())


async def _not_cancelled() -> bool:
    return False

async def _cancelled() -> bool:
    return True

async def _collect(events: list[tuple[str, dict]], event: str, data: dict) -> None:
    events.append((event, data))
def test_langgraph_baseline_adapter_streams_platform_events() -> None:
    async def run() -> None:
        record = _run_record()
        record.execution_manifest = build_execution_manifest(record, harness_type="langgraph")
        events: list[tuple[str, dict]] = []
        result = await RuntimeExecutor(LangGraphBaselineAdapter()).execute(
            record,
            lambda event, data: _collect(events, event, data),
            _not_cancelled,
        )
        assert result.metadata["mode"] == "langgraph_baseline"
        assert result.output.startswith("LangGraph baseline response:")
        assert [event for event, _ in events] == ["runtime.started", "runtime.step", "runtime.output"]

    asyncio.run(run())

def test_last_event_id_parser_rejects_invalid_values() -> None:
    assert _parse_last_event_id(None) == 0
    assert _parse_last_event_id("7") == 7
    for value in ("-1", "not-a-number"):
        try:
            _parse_last_event_id(value)
        except ApiError as exc:
            assert exc.code == "INVALID_LAST_EVENT_ID"
        else:
            raise AssertionError("invalid Last-Event-ID was accepted")


def test_openai_runtime_recovers_from_malformed_tool_arguments(monkeypatch) -> None:
    class FakeModel:
        model = "fake-model"

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call-invalid",
                                "type": "function",
                                "function": {"name": "echo", "arguments": '{"text":'},
                            }],
                        }
                    }]
                }
            assert messages[-1]["role"] == "tool"
            assert "retry" in messages[-1]["content"]
            return {"choices": [{"message": {"role": "assistant", "content": "recovered"}}]}

    async def run() -> None:
        record = _run_record()
        record.execution_manifest = build_execution_manifest(record, harness_type="openai-compatible")
        model = FakeModel()
        adapter = OpenAICompatibleRuntimeAdapter(model)  # type: ignore[arg-type]

        async def manifest_tools(_context):
            return ([{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}], {"echo": {"kind": "NATIVE"}})

        monkeypatch.setattr(adapter, "_manifest_tools", manifest_tools)
        events: list[tuple[str, dict]] = []
        result = await adapter.execute(
            RuntimeContext(run=record, manifest=record.execution_manifest),
            lambda event, data: _collect(events, event, data),
            _not_cancelled,
        )
        assert result.output == "recovered"
        assert model.calls == 2
        assert any(event == "tool.arguments.invalid" for event, _ in events)

    asyncio.run(run())


def test_model_tool_observation_bounds_dify_retrieval_payload() -> None:
    result = {
        "answer": "考勤制度的回答",
        "conversation_id": "dify-conversation",
        "retriever_resources": [{"content": "x" * 20_000} for _ in range(3)],
        "usage": {"total_tokens": 123},
    }
    observation = OpenAICompatibleRuntimeAdapter._model_tool_observation({"kind": "DIFY_FLOW"}, result)
    assert observation == {"answer": "考勤制度的回答", "workflow_run_id": None, "retrieval_count": 3}
