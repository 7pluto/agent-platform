from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "secret",
    "password",
    "passwd",
    "token",
    "cookie",
    "secret_ref",
}
_SENSITIVE_SUFFIXES = ("_api_key", "_access_key", "_access_token", "_refresh_token", "_auth_token", "_password", "_secret")


@dataclass(frozen=True, slots=True)
class ObservationPolicy:
    """One bounded and secret-safe policy for model observations and Run events."""

    version: str = "standard@1"
    max_trace_payload_chars: int = 16_000
    max_value_chars: int = 4_000
    max_tool_output_chars: int = 12_000
    max_model_observation_chars: int = 10_000
    max_rag_hits: int = 5
    max_rag_content_chars: int = 1_500

    def sanitize_event(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        value_limit = self.max_tool_output_chars if event in {"tool.completed", "runtime.output"} else self.max_value_chars
        sanitized = self._sanitize(data, value_limit=value_limit)
        if not isinstance(sanitized, dict):
            sanitized = {"value": sanitized}
        encoded = json.dumps(sanitized, ensure_ascii=False, default=str)
        if len(encoded) <= self.max_trace_payload_chars:
            return sanitized
        return {
            "summary": encoded[: self.max_trace_payload_chars],
            "_truncated": True,
            "_original_characters": len(encoded),
        }

    def bound_model_observation(self, value: dict[str, Any]) -> dict[str, Any]:
        sanitized = self._sanitize(value, value_limit=self.max_rag_content_chars)
        if isinstance(sanitized, dict) and isinstance(sanitized.get("hits"), list):
            sanitized["hits"] = sanitized["hits"][: self.max_rag_hits]
        encoded = json.dumps(sanitized, ensure_ascii=False, default=str)
        if len(encoded) <= self.max_model_observation_chars:
            return sanitized if isinstance(sanitized, dict) else {"value": sanitized}
        return {
            "summary": encoded[: self.max_model_observation_chars],
            "_truncated": True,
            "_original_characters": len(encoded),
        }

    def _sanitize(self, value: Any, *, value_limit: int) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                sensitive = normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)
                output[str(key)] = "[REDACTED]" if sensitive else self._sanitize(item, value_limit=value_limit)
            return output
        if isinstance(value, list):
            return [self._sanitize(item, value_limit=value_limit) for item in value[:100]]
        if isinstance(value, tuple):
            return [self._sanitize(item, value_limit=value_limit) for item in value[:100]]
        if isinstance(value, str) and len(value) > value_limit:
            return f"{value[:value_limit]}…[截断 {len(value) - value_limit} 字符]"
        return value


observation_policy = ObservationPolicy()
