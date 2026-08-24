"""Execution adapter for a governed, declarative HTTP Tool.

The Tool definition owns the host, method, path and request templates.  A
model can only fill placeholders declared by the input schema; it can never
choose an arbitrary URL, authorization header or shell command.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode, urljoin

import httpx

from app.core.errors import ApiError
from app.mcp.service import mcp_auth_headers
from app.outbound.safe_http import OutboundPolicy, safe_http_client

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render_template(value: Any, arguments: dict[str, Any]) -> Any:
    """Render only named argument placeholders in a declarative template."""
    if isinstance(value, dict):
        return {key: render_template(item, arguments) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, arguments) for item in value]
    if not isinstance(value, str):
        return value

    exact = _PLACEHOLDER.fullmatch(value)
    if exact:
        return _required_argument(exact.group(1), arguments)

    def replace(match: re.Match[str]) -> str:
        return str(_required_argument(match.group(1), arguments))

    return _PLACEHOLDER.sub(replace, value)


def _required_argument(name: str, arguments: dict[str, Any]) -> Any:
    if name not in arguments:
        raise ApiError(422, "HTTP_TOOL_ARGUMENT_MISSING", f"required HTTP Tool argument is missing: {name}")
    return arguments[name]


def render_path_template(value: str, arguments: dict[str, Any]) -> str:
    """Render path placeholders as one encoded path segment each."""
    def replace(match: re.Match[str]) -> str:
        rendered = str(_required_argument(match.group(1), arguments))
        if rendered in {".", ".."}:
            raise ApiError(422, "HTTP_TOOL_PATH_INVALID", "path arguments cannot be traversal segments")
        return quote(rendered, safe="")

    path = _PLACEHOLDER.sub(replace, value)
    if not path.startswith("/") or any(segment in {".", ".."} for segment in path.split("/")):
        raise ApiError(422, "HTTP_TOOL_PATH_INVALID", "rendered HTTP Tool path is invalid")
    return path


def _path_value(value: Any, path: str) -> Any:
    current = value
    for segment in (item for item in path.split(".") if item):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            raise ApiError(502, "HTTP_TOOL_RESPONSE_MAPPING_FAILED", f"response path was not found: {path}")
    return current


def apply_response_mapping(payload: Any, mapping: dict[str, Any] | None) -> Any:
    if not mapping:
        return payload
    source = _path_value(payload, str(mapping["body_path"])) if mapping.get("body_path") else payload
    fields = mapping.get("fields")
    if not fields:
        return source
    return {name: _path_value(source, path) for name, path in fields.items()}


class HttpToolClient:
    async def invoke(self, config: dict[str, Any], arguments: dict[str, Any], tenant_id: str, user_id: str) -> dict[str, Any]:
        endpoint = str(config["endpoint"]).rstrip("/") + "/"
        path = render_path_template(str(config.get("path", "/")), arguments).lstrip("/")
        target = urljoin(endpoint, path)
        query = render_template(config.get("query_template", {}), arguments)
        if query:
            if not isinstance(query, dict):
                raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "query_template must render to an object")
            target = f"{target}?{urlencode(query, doseq=True)}"
        body = render_template(config.get("body_template"), arguments) if "body_template" in config else None
        headers = await mcp_auth_headers(config, tenant_id, user_id)
        static_headers = render_template(config.get("header_template", {}), arguments)
        if static_headers:
            if not isinstance(static_headers, dict):
                raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "header_template must render to an object")
            headers.update({str(key): str(value) for key, value in static_headers.items()})
        if body is not None:
            headers.setdefault("Content-Type", "application/json")
        try:
            response = await safe_http_client.request(
                str(config.get("method", "GET")),
                target,
                policy=OutboundPolicy.from_config(config, default_timeout=15),
                headers=headers or None,
                json_body=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ApiError(502, "HTTP_TOOL_UPSTREAM_ERROR", f"HTTP Tool returned {exc.response.status_code}") from exc
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text
        return {"status_code": response.status_code, "body": apply_response_mapping(payload, config.get("response_mapping"))}


http_tool_client = HttpToolClient()
