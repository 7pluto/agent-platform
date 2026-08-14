import asyncio

import httpx

from app.core.errors import ApiError
from app.outbound.safe_http import OutboundPolicy, SafeHttpClient


def test_safe_http_rejects_loopback_even_when_allowlisted() -> None:
    async def run() -> None:
        client = SafeHttpClient()
        try:
            await client.request("GET", "http://127.0.0.1/metadata", policy=OutboundPolicy(("127.0.0.1",)))
        except ApiError as exc:
            assert exc.code == "OUTBOUND_EGRESS_FORBIDDEN"
        else:
            raise AssertionError("loopback target was accepted")

    asyncio.run(run())


def test_safe_http_requires_an_explicit_allowlist_match() -> None:
    async def run() -> None:
        client = SafeHttpClient()
        try:
            await client.request("GET", "https://untrusted.example/data", policy=OutboundPolicy(("approved.example",)))
        except ApiError as exc:
            assert exc.code == "OUTBOUND_EGRESS_FORBIDDEN"
        else:
            raise AssertionError("unapproved target was accepted")

    asyncio.run(run())


def test_safe_http_revalidates_redirect_target(monkeypatch) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://untrusted.example/next"})

        original = httpx.AsyncClient

        def client(*args, **kwargs):
            return original(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", client)
        try:
            await SafeHttpClient().request("GET", "https://approved.example/start", policy=OutboundPolicy(("approved.example",)))
        except ApiError as exc:
            assert exc.code == "OUTBOUND_EGRESS_FORBIDDEN"
        else:
            raise AssertionError("redirect to unapproved target was accepted")

    asyncio.run(run())
