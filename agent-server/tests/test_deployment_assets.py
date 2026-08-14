from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_compose_uses_durable_storage_for_demo_stack() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "AGENT_STORAGE_MODE: postgres" in compose
    assert "AGENT_SESSION_STORAGE_MODE: redis" in compose
    assert "agent-migrate" in compose


def test_helm_api_probes_match_real_health_route_and_production_guard() -> None:
    api = (ROOT / "deploy" / "helm" / "agent-platform" / "templates" / "api.yaml").read_text(encoding="utf-8")
    assert "/api/v1/healthz" in api
    assert "AGENT_RUNTIME_EXECUTION_MODE, value: disabled" in api
    assert "readOnlyRootFilesystem: true" in api
    assert "runAsNonRoot: true" in api


def test_helm_runtime_secret_is_referenced_not_embedded() -> None:
    chart = ROOT / "deploy" / "helm" / "agent-platform"
    values = (chart / "values.yaml").read_text(encoding="utf-8")
    api = (chart / "templates" / "api.yaml").read_text(encoding="utf-8")
    assert "existingSecret" in values
    assert "secretRef" in api
    assert "AGENT_SESSION_ENCRYPTION_KEY" not in values
    assert "AGENT_DATABASE_URL" not in values