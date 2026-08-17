import asyncio

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


def test_ragflow_provider_discovers_and_searches_a_fixed_dataset() -> None:
    provider = RagflowKnowledgeProvider(_principal())

    async def fake_request(method: str, config: dict, path: str, body: dict | None = None) -> dict:
        if path.endswith("datasets"):
            return {"code": 0, "data": [{"id": "dataset-hr", "name": "HR Policy", "description": "Policies"}]}
        assert body == {"question": "attendance", "dataset_ids": ["dataset-hr"], "page": 1, "page_size": 2, "top_k": 2}
        return {"code": 0, "data": [{"id": "chunk-1", "content": "Attendance policy", "similarity": 0.91, "document_name": "HR handbook"}]}

    provider._request = fake_request  # type: ignore[method-assign]

    async def scenario() -> None:
        assert await provider.discover_datasets({"endpoint": "https://ragflow.example"}) == [{"id": "dataset-hr", "name": "HR Policy", "description": "Policies"}]
        result = await provider.search(knowledge_version_id="knowledge-v1", config={"endpoint": "https://ragflow.example", "external_dataset_id": "dataset-hr"}, query="attendance", top_k=2)
        assert result.provider == "RAGFLOW"
        assert result.hits[0].content == "Attendance policy"
        assert result.hits[0].metadata["dataset_id"] == "dataset-hr"

    asyncio.run(scenario())
