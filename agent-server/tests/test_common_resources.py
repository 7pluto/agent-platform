from fastapi.testclient import TestClient

from app.main import app


def _developer_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-developer-ticket"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_common_resource_pack_installs_once_and_keeps_skill_dependencies() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        headers = _developer_headers(client)

        first = client.post("/api/v1/developer/resources/common/install", headers=headers)
        assert first.status_code == 200, first.text
        first_payload = first.json()
        assert first_payload["created"] == 13
        assert first_payload["existing"] == 0
        assert len(first_payload["items"]) == 13

        type_counts: dict[str, int] = {}
        by_slug = {}
        for item in first_payload["items"]:
            type_counts[item["resource_type"]] = type_counts.get(item["resource_type"], 0) + 1
            by_slug[item["slug"]] = item
        assert type_counts == {"TOOL": 3, "PROMPT": 4, "MEMORY_POLICY": 2, "SKILL": 4}

        second = client.post("/api/v1/developer/resources/common/install", headers=headers)
        assert second.status_code == 200, second.text
        second_payload = second.json()
        assert second_payload["created"] == 0
        assert second_payload["existing"] == 13
        assert {item["resource_id"] for item in second_payload["items"]} == {item["resource_id"] for item in first_payload["items"]}

        available = client.get("/api/v1/developer/resources/available")
        assert available.status_code == 200, available.text
        starter = [item for item in available.json() if "starter-pack" in item.get("tags", [])]
        assert len(starter) >= 13

        time_skill = client.get(f"/api/v1/developer/resources/{by_slug['common-time-awareness']['resource_id']}")
        assert time_skill.status_code == 200, time_skill.text
        time_skill_config = next(item for item in time_skill.json()["versions"] if item["status"] == "PUBLISHED")["config"]
        assert time_skill_config["tool_version_ids"] == [by_slug["common-current-time"]["resource_version_id"]]

        calculation_skill = client.get(f"/api/v1/developer/resources/{by_slug['common-calculation-check']['resource_id']}")
        assert calculation_skill.status_code == 200, calculation_skill.text
        calculation_config = next(item for item in calculation_skill.json()["versions"] if item["status"] == "PUBLISHED")["config"]
        assert calculation_config["tool_version_ids"] == [by_slug["common-calculator"]["resource_version_id"]]
