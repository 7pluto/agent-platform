from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any

from app.core.errors import ApiError
from app.mcp.service import mcp_auth_headers, mcp_client
from app.resources.providers.base import (
    DiscoveryResult, ProbeResult, ProviderErrorCode, ResourceProvider, TestResult, ValidationResult,
)


def _error_code(error: ApiError) -> ProviderErrorCode:
    if "TIMEOUT" in error.code:
        return ProviderErrorCode.TIMEOUT
    if "INVALID" in error.code or "PROTOCOL" in error.code:
        return ProviderErrorCode.PROTOCOL_ERROR
    if "CONNECTION" in error.code or "UNAVAILABLE" in error.code:
        return ProviderErrorCode.CONNECTION_FAILED
    return ProviderErrorCode.UPSTREAM_ERROR


class McpToolProvider(ResourceProvider):
    provider_name = "MCP"

    def __init__(self, tenant_id: str, user_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def _discover(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        headers = await mcp_auth_headers(config, self.tenant_id, self.user_id)
        return await mcp_client.discover(
            str(config["endpoint"]), float(config.get("timeout_seconds", 10)), headers,
            config.get("egress_allowlist", []),
        )

    async def probe(self, config: dict[str, Any]) -> ProbeResult:
        started = perf_counter()
        try:
            tools = await self._discover(config)
            return ProbeResult(provider=self.provider_name, ok=True, latency_ms=round((perf_counter() - started) * 1000), capabilities=["STREAMABLE_HTTP", "TOOLS_LIST"], details={"tool_count": len(tools)})
        except ApiError as exc:
            return ProbeResult(provider=self.provider_name, ok=False, error_code=_error_code(exc), message=exc.message, latency_ms=round((perf_counter() - started) * 1000))

    async def discover(self, config: dict[str, Any]) -> DiscoveryResult:
        started = perf_counter()
        try:
            tools = await self._discover(config)
            canonical = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return DiscoveryResult(provider=self.provider_name, ok=True, latency_ms=round((perf_counter() - started) * 1000), items=tools, schema_hash=hashlib.sha256(canonical.encode()).hexdigest())
        except ApiError as exc:
            return DiscoveryResult(provider=self.provider_name, ok=False, error_code=_error_code(exc), message=exc.message, latency_ms=round((perf_counter() - started) * 1000))

    async def test(self, config: dict[str, Any], test_input: dict[str, Any] | None = None) -> TestResult:
        discovery = await self.discover(config)
        return TestResult(provider=self.provider_name, ok=discovery.ok, error_code=discovery.error_code, message=discovery.message, latency_ms=discovery.latency_ms, details={"tool_count": len(discovery.items)}, output_summary="MCP tools/list succeeded" if discovery.ok else None)

    async def validate(self, config: dict[str, Any]) -> ValidationResult:
        result = await self.test(config)
        return ValidationResult(provider=self.provider_name, ok=result.ok, error_code=result.error_code, message=result.message, latency_ms=result.latency_ms, details=result.details)
