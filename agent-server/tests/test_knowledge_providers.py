from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.providers.local import LocalKnowledgeProvider
from app.knowledge.providers.remote_http import RemoteHttpKnowledgeProvider
from app.knowledge.providers.ragflow import RagflowKnowledgeProvider
from app.knowledge.providers.registry import knowledge_provider_registry


def _principal() -> Principal:
    return Principal(provider="mock", external_user_id="developer", external_org_id="org", tenant_id="tenant", display_name="Developer")


def test_knowledge_provider_registry_defaults_existing_knowledge_to_local() -> None:
    assert isinstance(knowledge_provider_registry.resolve({}, _principal()), LocalKnowledgeProvider)
    assert isinstance(knowledge_provider_registry.resolve({"provider": "LOCAL"}, _principal()), LocalKnowledgeProvider)
    assert isinstance(knowledge_provider_registry.resolve({"provider": "REMOTE_HTTP"}, _principal()), RemoteHttpKnowledgeProvider)
    assert isinstance(knowledge_provider_registry.resolve({"provider": "RAGFLOW"}, _principal()), RagflowKnowledgeProvider)


def test_knowledge_provider_registry_rejects_unimplemented_provider() -> None:
    try:
        knowledge_provider_registry.resolve({"provider": "UNTRUSTED"}, _principal())
    except ApiError as exc:
        assert exc.code == "KNOWLEDGE_PROVIDER_NOT_SUPPORTED"
    else:
        raise AssertionError("unsupported provider was resolved")
