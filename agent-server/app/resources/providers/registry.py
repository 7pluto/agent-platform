from __future__ import annotations

from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.providers.base import ResourceProvider
from app.resources.providers.dify import DifyToolProvider
from app.resources.providers.http import HttpToolProvider
from app.resources.providers.mcp import McpToolProvider
from app.resources.registry_models import ResourceType


class ProviderRegistry:
    """Provider routing is based on trusted resource configuration, never LLM input."""

    @staticmethod
    def resolve(resource_type: ResourceType, config: dict, principal: Principal) -> ResourceProvider:
        if resource_type == ResourceType.TOOL and config.get("kind") == "DIFY_FLOW":
            return DifyToolProvider(principal.tenant_id, principal.external_user_id)
        if resource_type == ResourceType.TOOL and config.get("kind") == "HTTP":
            return HttpToolProvider(principal.tenant_id, principal.external_user_id)
        if resource_type == ResourceType.MCP_CONNECTION:
            return McpToolProvider(principal.tenant_id, principal.external_user_id)
        raise ApiError(422, "PROVIDER_NOT_SUPPORTED", "resource does not have a provider lifecycle implementation")


provider_registry = ProviderRegistry()
