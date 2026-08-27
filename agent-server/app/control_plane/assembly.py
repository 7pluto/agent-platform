from __future__ import annotations

from uuid import UUID

from app.api.dependencies import ensure_resource_action
from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType, ResourceVersionRecord
from app.resources.store_factory import get_resource_store


_SINGLE = {
    "model_version_id": ResourceType.MODEL,
    "prompt_version_id": ResourceType.PROMPT,
    "memory_policy_version_id": ResourceType.MEMORY_POLICY,
}
_MULTIPLE = {
    "skill_version_ids": ResourceType.SKILL,
    "tool_version_ids": ResourceType.TOOL,
    "knowledge_version_ids": ResourceType.KNOWLEDGE,
    "mcp_connection_version_ids": ResourceType.MCP_CONNECTION,
}


class ResolvedAssemblyResource:
    """A resource plus why it became part of the assembled Agent."""

    def __init__(
        self,
        resource: ResourceVersionRecord,
        origin: str,
        dependency_path: list[str],
        *,
        use_allowed: bool = True,
    ) -> None:
        self.resource = resource
        self.origin = origin
        self.dependency_path = dependency_path
        self.use_allowed = use_allowed


def _uuid(value: object, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ApiError(422, "INVALID_RESOURCE_REFERENCE", f"{field} must contain UUID version references") from exc


def agent_resource_ids(specification: dict) -> list[tuple[ResourceType, UUID]]:
    values: list[tuple[ResourceType, UUID]] = []
    for field, resource_type in _SINGLE.items():
        value = specification.get(field)
        if value is not None:
            values.append((resource_type, _uuid(value, field)))
    for field, resource_type in _MULTIPLE.items():
        value = specification.get(field, [])
        if not isinstance(value, list):
            raise ApiError(422, "INVALID_RESOURCE_REFERENCE", f"{field} must be a list")
        values.extend((resource_type, _uuid(item, field)) for item in value)
    return values


async def validate_agent_assembly(specification: dict, principal: Principal, action: str = "USE") -> list[ResourceVersionRecord]:
    return [item.resource for item in await resolve_agent_assembly(specification, principal, action)]


async def resolve_agent_assembly(
    specification: dict, principal: Principal, action: str = "USE"
) -> list[ResolvedAssemblyResource]:
    """Strictly resolve all bindings for publish/configuration validation."""
    return await _resolve_agent_assembly(specification, principal, action=action)


async def resolve_agent_assembly_for_run(
    specification: dict, principal: Principal
) -> list[ResolvedAssemblyResource]:
    """Resolve a Run manifest while preserving strict Skill dependencies.

    Direct model-invoked Tool/Knowledge/MCP capabilities may be retained as
    denied bindings and filtered from the model registry. A dependency brought
    in by a Skill is not optional: if any transitive Tool/Knowledge/MCP
    dependency is unauthorized, Run creation fails before the first LLM call.
    """
    return await _resolve_agent_assembly(
        specification,
        principal,
        action="USE",
        deferred_types={ResourceType.TOOL, ResourceType.KNOWLEDGE, ResourceType.MCP_CONNECTION},
    )


async def _resolve_agent_assembly(
    specification: dict,
    principal: Principal,
    *,
    action: str,
    deferred_types: set[ResourceType] | None = None,
) -> list[ResolvedAssemblyResource]:
    deferred_types = deferred_types or set()
    registry = get_resource_registry()
    resolved: list[ResolvedAssemblyResource] = []
    pending = [
        (kind, version_id, "DIRECT", [f"agent.{kind.value.lower()}"])
        for kind, version_id in agent_resource_ids(specification)
    ]
    seen: set[UUID] = set()

    while pending:
        expected_type, version_id, origin, path = pending.pop(0)
        if expected_type == ResourceType.MODEL:
            model = await get_resource_store().get_model_version(version_id, principal, require_available=True)
            await ensure_resource_action(principal, action, "MODEL", str(model.model_version_id))
            continue
        if version_id in seen:
            continue

        resource = await registry.get_version(version_id, principal, published=True)
        if resource.resource_type != expected_type:
            raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version does not match Agent field")

        use_allowed = True
        try:
            await ensure_resource_action(principal, action, resource.resource_type.value, str(resource.resource_version_id))
        except ApiError as exc:
            can_defer = (
                exc.code == "RESOURCE_FORBIDDEN"
                and origin == "DIRECT"
                and resource.resource_type in deferred_types
            )
            if not can_defer:
                if exc.code == "RESOURCE_FORBIDDEN" and origin == "TRANSITIVE":
                    raise ApiError(
                        403,
                        "RESOURCE_DEPENDENCY_FORBIDDEN",
                        f"required dependency is not authorized: {' -> '.join(path)}",
                    ) from exc
                raise
            use_allowed = False

        seen.add(version_id)
        resolved.append(ResolvedAssemblyResource(resource, origin, path, use_allowed=use_allowed))

        if resource.resource_type == ResourceType.SKILL:
            config = resource.config
            for field, kind in (
                ("tool_version_ids", ResourceType.TOOL),
                ("knowledge_version_ids", ResourceType.KNOWLEDGE),
            ):
                dependencies = config.get(field, [])
                if not isinstance(dependencies, list):
                    raise ApiError(422, "INVALID_SKILL_CONFIG", f"{field} must be a list")
                pending.extend(
                    (
                        kind,
                        _uuid(item, f"skill.{field}"),
                        "TRANSITIVE",
                        path + [f"skill.{field}"],
                    )
                    for item in dependencies
                )

        if resource.resource_type == ResourceType.TOOL and resource.config.get("kind") == "MCP":
            connection_id = resource.config.get("connection_version_id")
            pending.append(
                (
                    ResourceType.MCP_CONNECTION,
                    _uuid(connection_id, "tool.connection_version_id"),
                    "TRANSITIVE" if origin == "TRANSITIVE" else "DIRECT",
                    path + ["tool.connection_version_id"],
                )
            )

    return resolved


def reject_legacy_text_resources(specification: dict) -> None:
    forbidden = {"prompt", "skills", "mcp_servers", "rag", "memory", "model_ref", "prompt_ref"}
    found = sorted(key for key in forbidden if key in specification)
    if found:
        raise ApiError(422, "LEGACY_RESOURCE_REFERENCE_FORBIDDEN", f"resource text references are not supported: {', '.join(found)}")


def is_resource_assembly_v2(specification: dict) -> bool:
    return specification.get("assembly_schema") == "v2"
