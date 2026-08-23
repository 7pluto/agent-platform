from app.runtime.observation import ObservationPolicy


def test_observation_policy_redacts_secrets_recursively() -> None:
    policy = ObservationPolicy()
    result = policy.sanitize_event(
        "tool.completed",
        {
            "headers": {"Authorization": "Bearer should-not-leak", "x-api-key": "also-secret"},
            "nested": [{"access_token": "hidden", "answer": "safe"}],
        },
    )

    assert result["headers"]["Authorization"] == "[REDACTED]"
    assert result["headers"]["x-api-key"] == "[REDACTED]"
    assert result["nested"][0]["access_token"] == "[REDACTED]"
    assert result["nested"][0]["answer"] == "safe"


def test_observation_policy_bounds_trace_and_model_payloads() -> None:
    policy = ObservationPolicy(max_trace_payload_chars=120, max_value_chars=40, max_model_observation_chars=100, max_rag_hits=2, max_rag_content_chars=20)

    event = policy.sanitize_event("tool.started", {"query": "a" * 200, "items": list(range(200))})
    assert event["_truncated"] is True
    assert len(event["summary"]) == 120

    observation = policy.bound_model_observation({"hits": [{"content": "b" * 80} for _ in range(5)]})
    assert observation.get("_truncated") is True or len(observation.get("hits", [])) <= 2
    assert "b" * 30 not in str(observation)
