from __future__ import annotations

from app.iam.models import ExternalIdentityContext, Subject, SubjectPage
from app.iam.providers import (
    CaptchaChallenge,
    IamAuthError,
    IamProvider,
    IamUnavailableError,
    PasswordCredentials,
    UpstreamToken,
)


class MockIamProvider(IamProvider):
    """Deterministic provider for local development and contract tests only."""

    def __init__(self) -> None:
        self._tokens = {
            "dev-ticket": "mock-ruoyi-token",
            "dev-developer-ticket": "mock-ruoyi-developer-token",
        }

    async def exchange_ticket(self, ticket_code: str) -> UpstreamToken:
        token = self._tokens.get(ticket_code)
        if not token:
            raise IamAuthError("mock ticket is invalid")
        return UpstreamToken(token)

    async def login_password(self, credentials: PasswordCredentials) -> UpstreamToken:
        raise IamUnavailableError("password login is only available with RuoYi IAM mode")

    async def fetch_captcha(self) -> CaptchaChallenge:
        raise IamUnavailableError("captcha is only available with RuoYi IAM mode")

    async def resolve_identity(self, token: UpstreamToken) -> ExternalIdentityContext:
        if token.value == "mock-ruoyi-token":
            return ExternalIdentityContext(
                provider="ruoyi-mock",
                external_user_id="user-demo",
                external_org_id="org-demo",
                display_name="Demo Admin",
                user_type="01",
                dept_ids=["dept-demo"],
                role_codes=["agent_admin"],
            )
        if token.value == "mock-ruoyi-developer-token":
            return ExternalIdentityContext(
                provider="ruoyi-mock",
                external_user_id="user-developer",
                external_org_id="org-demo",
                display_name="Demo Resource Developer",
                user_type="01",
                dept_ids=["dept-demo"],
                role_codes=["agent_developer"],
            )
        raise IamAuthError("mock token is invalid")

    async def search_subjects(
        self, subject_type: str, query: str, cursor: str | None, limit: int, token: UpstreamToken
    ) -> SubjectPage:
        await self.resolve_identity(token)
        items = [
            Subject(type="USER", external_id="user-demo", display_name="Demo Admin"),
            Subject(type="USER", external_id="user-developer", display_name="Demo Resource Developer"),
            Subject(type="DEPT", external_id="dept-demo", display_name="Demo Department"),
            Subject(type="ROLE", external_id="agent_admin", display_name="Agent Platform Administrator"),
            Subject(type="ROLE", external_id="agent_developer", display_name="Agent Resource Developer"),
        ]
        normalized = subject_type.upper()
        needle = query.lower()
        filtered = [
            item for item in items
            if item.type == normalized and (not needle or needle in item.display_name.lower() or needle in item.external_id.lower())
        ]
        return SubjectPage(items=filtered[:limit])
