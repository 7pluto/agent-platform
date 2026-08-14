"""The single controlled HTTP boundary for external resource providers."""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.errors import ApiError


@dataclass(frozen=True)
class OutboundPolicy:
    """Immutable egress limits supplied by a published resource configuration."""

    allowed_hosts: tuple[str, ...]
    timeout_seconds: float = 10.0
    max_request_bytes: int = 1_000_000
    max_response_bytes: int = 4_000_000
    max_redirects: int = 2

    @classmethod
    def from_config(cls, config: dict[str, Any], *, default_timeout: float) -> "OutboundPolicy":
        hosts = config.get("egress_allowlist", [])
        if not isinstance(hosts, list) or not hosts:
            raise ApiError(422, "OUTBOUND_POLICY_REQUIRED", "external resource requires egress_allowlist")
        return cls(
            allowed_hosts=tuple(str(host).strip().lower().rstrip(".") for host in hosts),
            timeout_seconds=float(config.get("timeout_seconds", default_timeout)),
        )


class SafeHttpClient:
    """Validates every target before opening an outbound HTTP connection.

    Host allowlists intentionally permit Docker service names such as
    ``demo-crm-mcp``. Literal loopback, link-local and metadata addresses are
    never permitted, including if they were accidentally put on an allowlist.
    Redirects are followed only after their target passes the same checks.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        policy: OutboundPolicy,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        content: bytes | str | None = None,
    ) -> httpx.Response:
        self._validate_target(url, policy)
        self._validate_request_size(json_body=json_body, content=content, policy=policy)
        current_method, current_url = method.upper(), url
        current_json, current_content = json_body, content

        for redirect_number in range(policy.max_redirects + 1):
            try:
                async with httpx.AsyncClient(timeout=policy.timeout_seconds, follow_redirects=False) as client:
                    response = await client.request(
                        current_method,
                        current_url,
                        headers=headers,
                        json=current_json,
                        content=current_content,
                    )
            except httpx.TimeoutException as exc:
                raise ApiError(504, "OUTBOUND_TIMEOUT", "external provider request timed out") from exc
            except httpx.HTTPError as exc:
                raise ApiError(502, "OUTBOUND_CONNECTION_FAILED", "external provider connection failed") from exc

            self._validate_response_size(response, policy)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            if redirect_number == policy.max_redirects:
                raise ApiError(502, "OUTBOUND_REDIRECT_LIMIT", "external provider exceeded redirect limit")

            current_url = urljoin(current_url, location)
            self._validate_target(current_url, policy)
            if response.status_code == 303:
                current_method, current_json, current_content = "GET", None, None

        raise ApiError(502, "OUTBOUND_REDIRECT_LIMIT", "external provider exceeded redirect limit")

    @staticmethod
    def _validate_target(url: str, policy: OutboundPolicy) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ApiError(422, "OUTBOUND_INVALID_CONFIG", "outbound target must be an HTTP(S) URL without embedded credentials")
        host = parsed.hostname.lower().rstrip(".")
        if host not in policy.allowed_hosts:
            raise ApiError(422, "OUTBOUND_EGRESS_FORBIDDEN", "outbound target is not allowed by egress policy")
        if host == "localhost" or host.endswith(".localhost"):
            raise ApiError(422, "OUTBOUND_EGRESS_FORBIDDEN", "localhost is never a valid outbound target")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
            raise ApiError(422, "OUTBOUND_EGRESS_FORBIDDEN", "sensitive IP address is not a valid outbound target")

    @staticmethod
    def _validate_request_size(*, json_body: Any | None, content: bytes | str | None, policy: OutboundPolicy) -> None:
        if json_body is not None:
            size = len(json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        elif content is not None:
            size = len(content.encode("utf-8") if isinstance(content, str) else content)
        else:
            size = 0
        if size > policy.max_request_bytes:
            raise ApiError(422, "OUTBOUND_REQUEST_TOO_LARGE", "external provider request exceeds the policy limit")

    @staticmethod
    def _validate_response_size(response: httpx.Response, policy: OutboundPolicy) -> None:
        declared_size = response.headers.get("content-length")
        if declared_size and declared_size.isdigit() and int(declared_size) > policy.max_response_bytes:
            raise ApiError(502, "OUTBOUND_RESPONSE_TOO_LARGE", "external provider response exceeds the policy limit")
        if len(response.content) > policy.max_response_bytes:
            raise ApiError(502, "OUTBOUND_RESPONSE_TOO_LARGE", "external provider response exceeds the policy limit")


safe_http_client = SafeHttpClient()
