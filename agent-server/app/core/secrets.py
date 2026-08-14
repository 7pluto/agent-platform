from __future__ import annotations

import os
import re
from typing import Any

from app.core.errors import ApiError


_SECRET_KEYWORDS = ("secret", "password", "token", "api_key", "apikey", "credential", "private_key")


def reject_secret_values(value: Any, path: str = "specification") -> None:
    """Reject secret-bearing configuration before it reaches platform storage.

    Resource configurations may carry opaque `secret_ref` values, but never a
    credential value. The check is recursive so nested provider/tool options do
    not evade the API boundary.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            child_path = f"{path}.{key}"
            if any(keyword in normalized for keyword in _SECRET_KEYWORDS):
                if normalized not in {"secret_ref", "secret_refs"}:
                    raise ApiError(422, "SECRET_VALUE_FORBIDDEN", f"secret-bearing field is not allowed: {child_path}")
            reject_secret_values(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_secret_values(item, f"{path}[{index}]")
_ENV_SECRET_REF = re.compile(r"^env://([A-Z][A-Z0-9_]*)$")
_VAULT_SECRET_REF = re.compile(r"^vault://[0-9a-fA-F-]{36}$")


def validate_secret_ref(secret_ref: str) -> None:
    if not (_ENV_SECRET_REF.fullmatch(secret_ref) or _VAULT_SECRET_REF.fullmatch(secret_ref)):
        raise ApiError(422, "INVALID_SECRET_REF", "secret reference must use vault://UUID or legacy env://VARIABLE")


def validate_persisted_secret_ref(secret_ref: str) -> None:
    """Require tenant Vault references for every newly persisted business secret.

    ``env://`` remains resolvable only so already-published legacy versions can
    be replayed. New definitions and versions must enter through the Vault.
    """
    if not _VAULT_SECRET_REF.fullmatch(secret_ref):
        raise ApiError(422, "VAULT_SECRET_REF_REQUIRED", "new resources must use a tenant vault://UUID secret reference")


def require_vault_secret_refs(value: Any, path: str = "configuration") -> None:
    """Enforce Vault-only references at API persistence boundaries."""
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "secret_ref":
                if not isinstance(item, str):
                    raise ApiError(422, "INVALID_SECRET_REF", f"{child_path} must be a secret reference")
                validate_persisted_secret_ref(item)
            elif key == "secret_refs":
                references = item.values() if isinstance(item, dict) else item if isinstance(item, list) else [item]
                for reference in references:
                    if not isinstance(reference, str):
                        raise ApiError(422, "INVALID_SECRET_REF", f"{child_path} must contain secret references")
                    validate_persisted_secret_ref(reference)
            else:
                require_vault_secret_refs(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            require_vault_secret_refs(item, f"{path}[{index}]")


def resolve_env_secret(secret_ref: str) -> str:
    """Resolve a deployment-owned environment secret without persisting its value."""
    match = _ENV_SECRET_REF.fullmatch(secret_ref)
    if not match:
        raise ApiError(422, "INVALID_SECRET_REF", "only env://UPPERCASE_VARIABLE secret references are supported")
    value = os.getenv(match.group(1))
    if not value:
        raise ApiError(409, "SECRET_NOT_CONFIGURED", "referenced deployment secret is not configured")
    return value


async def resolve_secret_reference(secret_ref: str, tenant_id: str, user_id: str) -> str:
    """Resolve tenant Vault references; env:// remains migration compatibility only."""
    validate_secret_ref(secret_ref)
    if secret_ref.startswith("env://"):
        return resolve_env_secret(secret_ref)
    from app.secrets.vault import get_secret_vault
    return await get_secret_vault().resolve(secret_ref, tenant_id, user_id)
