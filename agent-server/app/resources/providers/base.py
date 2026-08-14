"""Stable provider contract used by all external capability sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ProviderErrorCode(StrEnum):
    CONNECTION_FAILED = "CONNECTION_FAILED"
    AUTH_FAILED = "AUTH_FAILED"
    TIMEOUT = "TIMEOUT"
    INVALID_CONFIG = "INVALID_CONFIG"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    CAPABILITY_NOT_FOUND = "CAPABILITY_NOT_FOUND"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    DEPENDENCY_INVALID = "DEPENDENCY_INVALID"


class ProviderResult(BaseModel):
    ok: bool
    error_code: ProviderErrorCode | None = None
    message: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class ProbeResult(ProviderResult):
    provider: str
    capabilities: list[str] = Field(default_factory=list)


class DiscoveryResult(ProviderResult):
    provider: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    schema_hash: str | None = None


class ValidationResult(ProviderResult):
    provider: str


class TestResult(ProviderResult):
    provider: str
    output_summary: str | None = None


class ResourceProvider(ABC):
    """Provider implementations expose lifecycle operations, not permissions."""

    provider_name: str

    @abstractmethod
    async def probe(self, config: dict[str, Any]) -> ProbeResult: ...

    async def discover(self, config: dict[str, Any]) -> DiscoveryResult:
        return DiscoveryResult(provider=self.provider_name, ok=True)

    @abstractmethod
    async def test(self, config: dict[str, Any], test_input: dict[str, Any] | None = None) -> TestResult: ...

    async def validate(self, config: dict[str, Any]) -> ValidationResult:
        probe = await self.probe(config)
        return ValidationResult(
            provider=self.provider_name,
            ok=probe.ok,
            error_code=probe.error_code,
            message=probe.message,
            latency_ms=probe.latency_ms,
            details=probe.details,
        )
