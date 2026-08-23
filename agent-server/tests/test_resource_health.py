from app.api.routes.workbench import _health


def test_resource_health_uses_one_fixed_vocabulary() -> None:
    assert _health("MODEL", {"availability": "AVAILABLE"}) == "HEALTHY"
    assert _health("MODEL", {"availability": "UNAVAILABLE"}) == "UNHEALTHY"
    assert _health("KNOWLEDGE", {"provider": "LOCAL", "active_index_version": 2}) == "HEALTHY"
    assert _health("KNOWLEDGE", {"provider": "LOCAL"}) == "DEGRADED"
    assert _health("KNOWLEDGE", {"provider": "RAGFLOW"}) == "UNKNOWN"
    assert _health("TOOL", {"kind": "NATIVE"}) == "HEALTHY"
    assert _health("TOOL", {"kind": "DIFY_FLOW"}) == "UNKNOWN"
    assert _health("TOOL", {"kind": "DIFY_FLOW", "health_status": "CONFIGURED"}) == "UNKNOWN"
    assert _health("MCP_CONNECTION", {"health_status": "DEGRADED"}) == "DEGRADED"
