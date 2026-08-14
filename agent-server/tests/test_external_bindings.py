import asyncio
from uuid import uuid4

from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.bindings import ExternalBindingService


def _principal(tenant_id: str = "tenant-a") -> Principal:
    return Principal(provider="mock", external_user_id="developer", external_org_id="org", tenant_id=tenant_id, display_name="Developer")


def test_discovered_binding_is_unique_per_connection_and_tenant() -> None:
    async def run() -> None:
        service = ExternalBindingService()
        principal = _principal()
        connection_id, resource_id = uuid4(), uuid4()
        record = await service.register_discovered(
            provider="mcp", connection_resource_id=connection_id, external_type="tool",
            external_id="customer_search", resource_id=resource_id, principal=principal,
        )
        assert record.provider == "MCP"
        assert (await service.list_for_connection(connection_id, principal))[0].resource_id == resource_id
        try:
            await service.register_discovered(
                provider="MCP", connection_resource_id=connection_id, external_type="TOOL",
                external_id="customer_search", resource_id=uuid4(), principal=principal,
            )
        except ApiError as exc:
            assert exc.code == "EXTERNAL_BINDING_ALREADY_MANAGED"
        else:
            raise AssertionError("one discovered tool was bound to two resources")
        assert not await service.list_for_connection(connection_id, _principal("tenant-b"))

    asyncio.run(run())
