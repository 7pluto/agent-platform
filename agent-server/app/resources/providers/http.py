"""Provider lifecycle implementation for governed HTTP Tool resources."""

from __future__ import annotations

from time import perf_counter

from app.core.errors import ApiError
from app.resources.providers.base import (
    ProbeResult,
    ProviderErrorCode,
    ResourceProvider,
    TestResult,
    ValidationResult,
)
from app.resources.registry_models import ResourceType
from app.resources.registry_store import ResourceRegistryStore
from app.runtime.http_tool import http_tool_client


def _error_code(error: ApiError) -> ProviderErrorCode:
    if error.code in {"OUTBOUND_TIMEOUT"}:
        return ProviderErrorCode.TIMEOUT
    if error.code in {"OUTBOUND_EGRESS_FORBIDDEN", "OUTBOUND_INVALID_CONFIG", "INVALID_HTTP_TOOL_CONFIG"}:
        return ProviderErrorCode.INVALID_CONFIG
    if error.code in {"HTTP_TOOL_ARGUMENT_MISSING"}:
        return ProviderErrorCode.DEPENDENCY_INVALID
    if error.code in {"OUTBOUND_CONNECTION_FAILED"}:
        return ProviderErrorCode.CONNECTION_FAILED
    return ProviderErrorCode.UPSTREAM_ERROR


class HttpToolProvider(ResourceProvider):
    provider_name = "HTTP"

    def __init__(self, tenant_id: str, user_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def probe(self, config: dict) -> ProbeResult:
        started = perf_counter()
        try:
            ResourceRegistryStore._validate(ResourceType.TOOL, config)
            return ProbeResult(
                provider=self.provider_name,
                ok=True,
                latency_ms=round((perf_counter() - started) * 1000),
                capabilities=[str(config.get("method", "GET")), "DECLARATIVE_TEMPLATE", "EGRESS_ALLOWLIST"],
                details={"endpoint_host": str(config.get("egress_allowlist", [""])[0])},
            )
        except ApiError as exc:
            return ProbeResult(
                provider=self.provider_name,
                ok=False,
                error_code=_error_code(exc),
                message=exc.message,
                latency_ms=round((perf_counter() - started) * 1000),
            )

    async def test(self, config: dict, test_input: dict | None = None) -> TestResult:
        started = perf_counter()
        try:
            result = await http_tool_client.invoke(config, test_input or {}, self.tenant_id, self.user_id)
            return TestResult(
                provider=self.provider_name,
                ok=True,
                latency_ms=round((perf_counter() - started) * 1000),
                details={"status_code": result["status_code"]},
                output_summary=f"HTTP {result['status_code']}",
            )
        except ApiError as exc:
            return TestResult(
                provider=self.provider_name,
                ok=False,
                error_code=_error_code(exc),
                message=exc.message,
                latency_ms=round((perf_counter() - started) * 1000),
            )

    async def validate(self, config: dict) -> ValidationResult:
        probe = await self.probe(config)
        return ValidationResult(
            provider=self.provider_name,
            ok=probe.ok,
            error_code=probe.error_code,
            message=probe.message,
            latency_ms=probe.latency_ms,
            details=probe.details,
        )
