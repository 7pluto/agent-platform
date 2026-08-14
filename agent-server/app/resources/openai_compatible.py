from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings
from app.core.errors import ApiError
from app.core.secrets import resolve_env_secret, resolve_secret_reference


@dataclass(frozen=True)
class OpenAICompatibleModel:
    base_url: str
    model: str
    api_key: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "OpenAICompatibleModel":
        return cls(
            base_url=str(config["base_url"]).rstrip("/"),
            model=str(config["model"]),
            api_key=resolve_env_secret(str(config["secret_ref"])),
        )

    @classmethod
    async def from_runtime_config(cls, config: dict[str, Any], tenant_id: str, user_id: str) -> "OpenAICompatibleModel":
        return cls(
            base_url=str(config["base_url"]).rstrip("/"),
            model=str(config["model"]),
            api_key=await resolve_secret_reference(str(config["secret_ref"]), tenant_id, user_id),
        )

    async def complete(self, *, system_prompt: str, message: str) -> str:
        body = await self.chat(
            ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [{"role": "user", "content": message}]
        )
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ApiError(502, "MODEL_UPSTREAM_INVALID_RESPONSE", "model provider returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip():
            raise ApiError(502, "MODEL_UPSTREAM_INVALID_RESPONSE", "model provider returned an empty response")
        return content

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        # A provider connection can be reset transiently.  Retry only once and
        # only before a response is received; tool calls themselves are never retried here.
        body: Any = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=get_settings().model_request_timeout_seconds) as client:
                    response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers={"Authorization": f"Bearer {self.api_key}"})
                    response.raise_for_status()
                    body = response.json()
                    break
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    await asyncio.sleep(0.4)
                    continue
                raise ApiError(504, "MODEL_UPSTREAM_TIMEOUT", "model provider did not respond before the configured timeout") from exc
            except httpx.HTTPError as exc:
                if attempt == 0 and isinstance(exc, httpx.NetworkError):
                    await asyncio.sleep(0.4)
                    continue
                raise ApiError(502, "MODEL_UPSTREAM_UNAVAILABLE", "model provider request failed") from exc
        if not isinstance(body, dict) or not isinstance(body.get("choices"), list):
            raise ApiError(502, "MODEL_UPSTREAM_INVALID_RESPONSE", "model provider returned an invalid response")
        return body

    async def test_connection(self) -> None:
        await self.complete(system_prompt="Respond with only: OK", message="ping")


@dataclass(frozen=True)
class OpenAICompatibleEmbedder:
    base_url: str
    model: str
    api_key: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "OpenAICompatibleEmbedder":
        return cls(
            base_url=str(config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")).rstrip("/"),
            model=str(config.get("embedding_model", "text-embedding-v3")),
            api_key=resolve_env_secret(str(config.get("secret_ref", "env://QWEN_API_KEY"))),
        )

    @classmethod
    async def from_runtime_config(cls, config: dict[str, Any], tenant_id: str, user_id: str) -> "OpenAICompatibleEmbedder":
        return cls(
            base_url=str(config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")).rstrip("/"),
            model=str(config.get("embedding_model", "text-embedding-v3")),
            api_key=await resolve_secret_reference(str(config.get("secret_ref", "env://QWEN_API_KEY")), tenant_id, user_id),
        )

    @classmethod
    async def from_model_config(cls, config: dict[str, Any], tenant_id: str, user_id: str) -> "OpenAICompatibleEmbedder":
        return cls(
            base_url=str(config["base_url"]).rstrip("/"),
            model=str(config["model"]),
            api_key=await resolve_secret_reference(str(config["secret_ref"]), tenant_id, user_id),
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(timeout=get_settings().model_request_timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/embeddings", json={"model": self.model, "input": texts}, headers={"Authorization": f"Bearer {self.api_key}"})
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise ApiError(502, "EMBEDDING_UPSTREAM_UNAVAILABLE", "embedding provider request failed") from exc
        try:
            values = [item["embedding"] for item in sorted(payload["data"], key=lambda item: item["index"])]
        except (KeyError, TypeError) as exc:
            raise ApiError(502, "EMBEDDING_UPSTREAM_INVALID_RESPONSE", "embedding provider returned an invalid response") from exc
        if len(values) != len(texts) or any(not isinstance(value, list) or len(value) != 1024 for value in values):
            raise ApiError(502, "EMBEDDING_UPSTREAM_INVALID_RESPONSE", "embedding vector dimension must be 1024")
        return values
