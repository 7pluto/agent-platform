import asyncio

import pytest
from pydantic import ValidationError

from app.governance.models import GrantEffect, ResourceGrantCreate, SubjectType
from app.governance.store import GovernanceStore
from app.iam.models import Principal


def _principal(user_id: str, role_codes: list[str] | None = None) -> Principal:
    return Principal(
        provider="mock",
        external_user_id=user_id,
        external_org_id="org-demo",
        tenant_id="tenant-demo",
        display_name=user_id,
        role_codes=role_codes or [],
        dept_ids=["dept-demo"],
    )


def test_resource_grant_default_deny_and_explicit_deny_wins() -> None:
    async def run() -> None:
        store = GovernanceStore()
        admin = _principal("admin", ["agent_admin"])
        member = _principal("member", ["viewer"])
        assert not await store.is_allowed(member, "RUN", "DEPLOYMENT", "deployment-a")

        await store.create_grant(
            ResourceGrantCreate(
                subject_type=SubjectType.ROLE,
                subject_id="viewer",
                resource_type="DEPLOYMENT",
                resource_id="deployment-a",
                actions={"RUN"},
            ),
            admin,
        )
        assert await store.is_allowed(member, "RUN", "DEPLOYMENT", "deployment-a")

        await store.create_grant(
            ResourceGrantCreate(
                subject_type=SubjectType.USER,
                subject_id="member",
                resource_type="DEPLOYMENT",
                resource_id="deployment-a",
                actions={"RUN"},
                effect=GrantEffect.DENY,
            ),
            admin,
        )
        assert not await store.is_allowed(member, "RUN", "DEPLOYMENT", "deployment-a")

    asyncio.run(run())


def test_audit_is_tenant_scoped() -> None:
    async def run() -> None:
        store = GovernanceStore()
        tenant_a = _principal("a")
        tenant_b = Principal(
            provider="mock",
            external_user_id="b",
            external_org_id="org-b",
            tenant_id="tenant-b",
            display_name="b",
        )
        await store.record_audit(tenant_a, "agent.create", "AGENT_DEFINITION", "agent-a")
        await store.record_audit(tenant_b, "agent.create", "AGENT_DEFINITION", "agent-b")
        events = await store.list_audit(tenant_a)
        assert [event.resource_id for event in events] == ["agent-a"]

    asyncio.run(run())


def test_resource_grant_actions_are_fixed() -> None:
    ResourceGrantCreate(
        subject_type=SubjectType.USER,
        subject_id="member",
        resource_type="TOOL",
        resource_id="tool-a",
        actions={"VIEW", "USE", "EDIT", "PUBLISH", "MANAGE", "RUN"},
    )
    with pytest.raises(ValidationError):
        ResourceGrantCreate(
            subject_type=SubjectType.USER,
            subject_id="member",
            resource_type="TOOL",
            resource_id="tool-a",
            actions={"DELETE_EVERYTHING"},
        )
