from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import Cookie, Header, Request

from app.config import Settings, get_settings
from app.core.errors import ApiError
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.iam.providers import UpstreamToken
from app.session.factory import get_session_store
from app.session.store import SessionRecord


@lru_cache
def get_iam_service():
    from app.iam.service import IamService

    return IamService(get_settings())


async def _load_session(
    request: Request,
    ap_session: str | None,
    authorization: str | None,
) -> tuple[SessionRecord, UpstreamToken]:
    settings: Settings = get_settings()
    store = get_session_store()
    session_id = ap_session or request.cookies.get(settings.session_cookie_name)
    if not session_id and settings.allow_direct_bearer and authorization and authorization.lower().startswith("bearer "):
        token = UpstreamToken(authorization[7:].strip())
        principal = await get_iam_service().resolve(token)
        _, record = await store.create(token, principal)
        return record, token
    if not session_id:
        raise ApiError(401, "AUTH_REQUIRED", "Agent Platform session is required")
    record = await store.get(session_id)
    if not record:
        raise ApiError(401, "AUTH_EXPIRED", "Agent Platform session has expired")
    return record, await store.upstream_token(record)


async def current_session(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
) -> tuple[SessionRecord, UpstreamToken]:
    return await _load_session(request, ap_session, authorization)


async def current_upstream_token(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
) -> UpstreamToken:
    _, token = await _load_session(request, ap_session, authorization)
    return token


async def require_principal(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
) -> Principal:
    record, _ = await _load_session(request, ap_session, authorization)
    return record.principal


async def require_fresh_principal(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
) -> Principal:
    record, token = await _load_session(request, ap_session, authorization)
    principal = await get_iam_service().resolve(token)
    record.principal = principal
    await get_session_store().update_principal(record)
    return principal


async def require_fresh_mutation_principal(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Principal:
    """Require an anti-CSRF token for cookie-authenticated state changes."""
    record, token = await _load_session(request, ap_session, authorization)
    session_id = ap_session or request.cookies.get(get_settings().session_cookie_name)
    if session_id and csrf_token != record.csrf_token:
        raise ApiError(403, "CSRF_INVALID", "valid X-CSRF-Token is required")
    principal = await get_iam_service().resolve(token)
    record.principal = principal
    await get_session_store().update_principal(record)
    return principal


def is_platform_admin(principal: Principal) -> bool:
    settings = get_settings()
    return principal.external_user_id in settings.platform_admin_user_ids or bool(
        set(principal.role_codes) & set(settings.platform_admin_role_codes)
    )


def is_resource_developer(principal: Principal) -> bool:
    settings = get_settings()
    return (
        is_platform_admin(principal)
        or principal.external_user_id in settings.resource_developer_user_ids
        or bool(set(principal.role_codes) & set(settings.resource_developer_role_codes))
    )


async def require_platform_admin(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Principal:
    principal = await require_fresh_mutation_principal(request, ap_session, authorization, csrf_token)
    if not is_platform_admin(principal):
        raise ApiError(403, "PLATFORM_ADMIN_REQUIRED", "platform administrator role is required")
    return principal


async def require_platform_admin_read(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
) -> Principal:
    principal = await require_fresh_principal(request, ap_session, authorization)
    if not is_platform_admin(principal):
        raise ApiError(403, "PLATFORM_ADMIN_REQUIRED", "platform administrator role is required")
    return principal


async def require_resource_developer(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Principal:
    principal = await require_fresh_mutation_principal(request, ap_session, authorization, csrf_token)
    if not is_resource_developer(principal):
        raise ApiError(403, "RESOURCE_DEVELOPER_REQUIRED", "resource developer role is required")
    return principal


async def require_resource_developer_read(
    request: Request,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
    authorization: str | None = Header(default=None),
) -> Principal:
    principal = await require_fresh_principal(request, ap_session, authorization)
    if not is_resource_developer(principal):
        raise ApiError(403, "RESOURCE_DEVELOPER_REQUIRED", "resource developer role is required")
    return principal


async def _definition_resource_id(
    principal: Principal,
    resource_type: str,
    resource_id: str,
) -> tuple[str | None, str]:
    """Resolve an immutable version id to its stable definition id when possible."""
    try:
        target_id = UUID(resource_id)
    except (TypeError, ValueError):
        return None, resource_type

    if resource_type == "MODEL":
        from app.resources.store_factory import get_resource_store

        try:
            version = await get_resource_store().get_model_version(target_id, principal)
        except ApiError as exc:
            if exc.code == "NOT_FOUND":
                return None, resource_type
            raise
        return str(version.model_id), "MODEL"

    if resource_type in {"DEPLOYMENT", "AGENT", "RUN", "RESOURCE_GRANT"}:
        return None, resource_type

    from app.resources.registry_factory import get_resource_registry

    try:
        version = await get_resource_registry().get_version(target_id, principal)
    except ApiError as exc:
        if exc.code == "NOT_FOUND":
            return None, resource_type
        raise
    return str(version.resource_id), version.resource_type.value


async def ensure_resource_action(principal: Principal, action: str, resource_type: str, resource_id: str) -> None:
    """Authorize a business-resource action without an admin USE/RUN bypass."""
    governance = get_governance_store()
    if await governance.is_allowed(principal, action, resource_type, resource_id):
        return

    definition_id, actual_type = await _definition_resource_id(principal, resource_type, resource_id)
    if definition_id and definition_id != resource_id:
        if await governance.is_allowed(principal, action, actual_type, definition_id):
            return

    if action in {"VIEW", "USE", "EDIT"} and definition_id and get_settings().storage_mode == "postgres":
        from sqlalchemy import select

        from app.db.models import ResourceDescriptorRow
        from app.db.rls import set_local_tenant_context
        from app.db.session import get_session_factory

        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                owner = await session.scalar(select(ResourceDescriptorRow.owner_user_id).where(
                    ResourceDescriptorRow.tenant_id == principal.tenant_id,
                    ResourceDescriptorRow.resource_type == actual_type,
                    ResourceDescriptorRow.resource_id == UUID(definition_id),
                ))
                if owner == principal.external_user_id:
                    return

    if is_platform_admin(principal) and action in {"EDIT", "PUBLISH", "MANAGE"}:
        return

    raise ApiError(403, "RESOURCE_FORBIDDEN", "resource grant does not allow this action")
