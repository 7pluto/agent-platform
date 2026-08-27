from uuid import uuid4

from app.runtime.manifest import build_execution_manifest
from app.runtime.models import PublicExecutionManifest, PublicRunRecord, RunRecord


def test_public_manifest_drops_secret_refs_provider_config_and_prompt_body() -> None:
    run = RunRecord(
        tenant_id="tenant-security",
        user_id="ruoyi-user-security",
        deployment_id=uuid4(),
        thread_id=uuid4(),
        message="hello",
    )
    manifest = build_execution_manifest(
        run,
        resource_versions={
            "agent_definition_id": str(uuid4()),
            "agent_version_id": str(uuid4()),
            "agent_version_content_hash": "a" * 64,
            "deployment_revision_id": str(uuid4()),
            "model_version_id": str(uuid4()),
            "model_version_content_hash": "b" * 64,
            "model_config": '{"base_url":"https://model.example/v1","secret_ref":"vault://secret-id"}',
            "system_prompt": "private system instructions must never be returned",
        },
        secret_refs={
            "model": "vault://secret-id",
            "tool:1": "vault://tool-secret-id",
        },
        resources=[{
            "type": "TOOL",
            "resource_id": str(uuid4()),
            "version_id": str(uuid4()),
            "content_hash": "c" * 64,
            "binding_origin": "DIRECT",
            "use_allowed": True,
        }],
        harness_type="openai-compatible",
    )
    run.execution_manifest = manifest

    public_manifest = PublicExecutionManifest.from_internal(manifest)
    payload = public_manifest.model_dump(mode="json")
    serialized = str(payload)

    assert "secret_refs" not in payload
    assert "model_config" not in payload["resource_versions"]
    assert "system_prompt" not in payload["resource_versions"]
    assert "vault://" not in serialized
    assert "private system instructions" not in serialized
    assert payload["resource_versions"]["model_version_id"] == manifest.resource_versions["model_version_id"]

    public_run = PublicRunRecord.from_internal(run).model_dump(mode="json")
    assert "vault://" not in str(public_run)
    assert "private system instructions" not in str(public_run)
