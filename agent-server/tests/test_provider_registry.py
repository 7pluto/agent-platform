from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.providers.dify import DifyToolProvider
from app.resources.providers.mcp import McpToolProvider
from app.resources.providers.registry import provider_registry
from app.resources.registry_models import ResourceType


def _principal() -> Principal:
    return Principal(provider="mock", external_user_id="developer", external_org_id="org", tenant_id="tenant", display_name="Developer")


def test_provider_registry_uses_trusted_resource_type_and_kind() -> None:
    assert isinstance(provider_registry.resolve(ResourceType.TOOL, {"kind": "DIFY_FLOW"}, _principal()), DifyToolProvider)
    assert isinstance(provider_registry.resolve(ResourceType.MCP_CONNECTION, {"transport": "streamable_http"}, _principal()), McpToolProvider)
    try:
        provider_registry.resolve(ResourceType.KNOWLEDGE, {}, _principal())
    except ApiError as exc:
        assert exc.code == "PROVIDER_NOT_SUPPORTED"
    else:
        raise AssertionError("unsupported provider was resolved")
