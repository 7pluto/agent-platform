from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any

from app.core.errors import ApiError
from app.runtime.dify_flow import DifyFlowClient
from app.resources.providers.base import (
    DiscoveryResult, ProbeResult, ProviderErrorCode, ResourceProvider, TestResult, ValidationResult,
)


def _error_code(error: ApiError) -> ProviderErrorCode:
    if error.code in {"DIFY_CREDENTIAL_REJECTED", "AUTH_FAILED"}:
        return ProviderErrorCode.AUTH_FAILED
    if "TIMEOUT" in error.code:
        return ProviderErrorCode.TIMEOUT
    if "INVALID" in error.code:
        return ProviderErrorCode.INVALID_SCHEMA
    if "CONNECTION" in error.code or "UNAVAILABLE" in error.code:
        return ProviderErrorCode.CONNECTION_FAILED
    return ProviderErrorCode.UPSTREAM_ERROR


class DifyToolProvider(ResourceProvider):
    provider_name = "DIFY"

    def __init__(self, tenant_id: str, user_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def probe(self, config: dict[str, Any]) -> ProbeResult:
        started = perf_counter()
        try:
            inspection = await (await DifyFlowClient.from_runtime_config(config, self.tenant_id, self.user_id)).inspect_application()
            return ProbeResult(
                provider=self.provider_name, ok=True, latency_ms=round((perf_counter() - started) * 1000),
                capabilities=[str(inspection.get("flow_type", "DIFY"))], details=inspection,
            )
        except ApiError as exc:
            return ProbeResult(provider=self.provider_name, ok=False, error_code=_error_code(exc), message=exc.message, latency_ms=round((perf_counter() - started) * 1000))

    async def discover(self, config: dict[str, Any]) -> DiscoveryResult:
        probe = await self.probe(config)
        if not probe.ok:
            return DiscoveryResult(provider=self.provider_name, ok=False, error_code=probe.error_code, message=probe.message, latency_ms=probe.latency_ms)
        inputs = probe.details.get("input_form", [])
        items = [{"kind": "INPUT", "definition": item} for item in inputs if isinstance(item, dict)]
        canonical = json.dumps({"flow_type": probe.details.get("flow_type"), "input_form": inputs}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return DiscoveryResult(provider=self.provider_name, ok=True, latency_ms=probe.latency_ms, items=items, schema_hash=hashlib.sha256(canonical.encode()).hexdigest())

    async def test(self, config: dict[str, Any], test_input: dict[str, Any] | None = None) -> TestResult:
        started = perf_counter()
        try:
            query = str((test_input or {}).get("query") or config.get("test_query") or "请回复 OK")
            result = await (await DifyFlowClient.from_runtime_config(config, self.tenant_id, self.user_id)).test_connection(query)
            return TestResult(provider=self.provider_name, ok=True, latency_ms=round((perf_counter() - started) * 1000), details=result, output_summary="Dify application connection succeeded")
        except ApiError as exc:
            return TestResult(provider=self.provider_name, ok=False, error_code=_error_code(exc), message=exc.message, latency_ms=round((perf_counter() - started) * 1000))

    async def validate(self, config: dict[str, Any]) -> ValidationResult:
        result = await self.test(config)
        return ValidationResult(provider=self.provider_name, ok=result.ok, error_code=result.error_code, message=result.message, latency_ms=result.latency_ms, details=result.details)
