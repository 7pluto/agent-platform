import asyncio
from uuid import uuid4

from app.iam.models import Principal
from app.resources.registry_models import ResourceValidationStatus, ResourceValidationType
from app.resources.validation import ResourceValidationService, redact_validation_result


def _principal() -> Principal:
    return Principal(provider="mock", external_user_id="developer-1", external_org_id="org-1", tenant_id="tenant-1", display_name="Developer")


def test_validation_result_redacts_secrets_and_bounds_text() -> None:
    result = redact_validation_result({"api_key": "do-not-store", "nested": {"Authorization": "Bearer x"}, "message": "a" * 5_000})
    assert result["api_key"] == "[REDACTED]"
    assert result["nested"]["Authorization"] == "[REDACTED]"
    assert len(result["message"]) == 4_000


def test_validation_runs_are_tenant_scoped_and_support_publish_gate() -> None:
    async def run() -> None:
        service = ResourceValidationService()
        version_id = uuid4()
        principal = _principal()
        await service.record(version_id, ResourceValidationType.TEST, ResourceValidationStatus.SUCCEEDED, {"available": True}, principal, 12)
        assert not await service.has_successful_validation(version_id, principal)
        await service.record(version_id, ResourceValidationType.VALIDATE, ResourceValidationStatus.SUCCEEDED, {"api_key": "never"}, principal, 15)
        records = await service.list(version_id, principal)
        assert len(records) == 2
        assert records[0].result["api_key"] == "[REDACTED]"
        assert await service.has_successful_validation(version_id, principal)

    asyncio.run(run())
