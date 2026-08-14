from app.core.errors import ApiError
from app.core.secrets import reject_secret_values, require_vault_secret_refs, validate_persisted_secret_ref, validate_secret_ref
from app.secrets.vault import SecretCreate, SecretRecord


def test_secret_api_record_has_reference_and_fingerprint_only() -> None:
    fields = set(SecretRecord.model_fields)
    assert {"secret_ref", "name", "fingerprint", "status", "last_used_at", "rotated_at", "disabled_at", "created_by", "created_at"} <= fields
    assert not fields.intersection({"value", "encrypted_value", "api_key", "token", "secret"})
    assert "value" not in fields and "encrypted_value" not in fields
    assert "value" in SecretCreate.model_fields


def test_vault_reference_is_valid_but_plaintext_secret_fields_are_rejected() -> None:
    validate_secret_ref("vault://12345678-1234-1234-1234-123456789abc")
    try:
        reject_secret_values({"api_key": "plain"}, "resource.config")
    except ApiError as exc:
        assert exc.code == "SECRET_VALUE_FORBIDDEN"
    else:
        raise AssertionError("plaintext api_key was accepted in resource config")


def test_new_resource_secret_refs_must_use_tenant_vault() -> None:
    validate_persisted_secret_ref("vault://12345678-1234-1234-1234-123456789abc")
    try:
        validate_persisted_secret_ref("env://LEGACY_PROVIDER_KEY")
    except ApiError as exc:
        assert exc.code == "VAULT_SECRET_REF_REQUIRED"
    else:
        raise AssertionError("new resource accepted a legacy environment secret")
    require_vault_secret_refs({"provider": {"secret_ref": "vault://12345678-1234-1234-1234-123456789abc"}})
    try:
        require_vault_secret_refs({"secret_refs": {"provider": "env://LEGACY_PROVIDER_KEY"}})
    except ApiError as exc:
        assert exc.code == "VAULT_SECRET_REF_REQUIRED"
    else:
        raise AssertionError("new secret_refs map accepted a legacy environment secret")
