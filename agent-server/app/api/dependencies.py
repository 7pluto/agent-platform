from __future__ import annotations

from functools import lru_cache

from fastapi import Cookie, Header, Request

from app.config import Settings, get_settings
from app.core.errors import ApiError
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.iam.providers import UpstreamToken
from app.iam.service import IamService
from app.session.factory import get_session_store
from app.session.store import SessionRecord


@lru_cache
def get_iam_service() -> IamService:
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
    """Require an anti-CSRF token for cookie-authenticated state changes.

    Direct bearer is only a development compatibility path and deliberately does
    not create a browser cookie, so it is not subject to the cookie CSRF check.
    """
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
    """Require fresh admin identity for GET requests without mutation-only CSRF."""
    principal = await require_fresh_principal(request, ap_session, authorization)
    if not is_platform_admin(principal):
        raise ApiError(403, "PLATFORM_ADMIN_REQUIRED", "platform administrator role is required")
    return principal

async def ensure_resource_action(principal: Principal, action: str, resource_type: str, resource_id: str) -> None:
    if is_platform_admin(principal):
        return
    if await get_governance_store().is_allowed(principal, action, resource_type, resource_id):
        return
    # Descriptors are defined at the resource-definition level while grants are
    # intentionally version-specific. Resolve either version kind only when an
    # ownership-based action is requested.
    if action in {"VIEW", "USE", "EDIT"} and get_settings().storage_mode == "postgres":
        from sqlalchemy import select
        from app.db.models import ModelVersionRow, ResourceDescriptorRow, ResourceVersionRow
        from app.db.rls import set_local_tenant_context
        from app.db.session import get_session_factory
        from uuid import UUID
        try:
            target_id = UUID(resource_id)
        except ValueError:
            target_id = None
        if target_id:
            async with get_session_factory()() as session:
                async with session.begin():
                    await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                    definition_id = await session.scalar(select(ResourceVersionRow.resource_id).where(
                        ResourceVersionRow.tenant_id == principal.tenant_id,
                        ResourceVersionRow.resource_version_id == target_id,
                    ))
                    actual_type = resource_type
                    if definition_id is None:
                        definition_id = await session.scalar(select(ModelVersionRow.model_id).where(
                            ModelVersionRow.tenant_id == principal.tenant_id,
                            ModelVersionRow.model_version_id == target_id,
                        ))
                        actual_type = "MODEL"
                    if definition_id is not None:
                        owner = await session.scalar(select(ResourceDescriptorRow.owner_user_id).where(
                            ResourceDescriptorRow.tenant_id == principal.tenant_id,
                            ResourceDescriptorRow.resource_type == actual_type,
                            ResourceDescriptorRow.resource_id == definition_id,
                        ))
                        if owner == principal.external_user_id:
                            return
    raise ApiError(403, "RESOURCE_FORBIDDEN", "resource grant does not allow this action")
