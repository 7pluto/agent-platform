from app.config import Settings
from app.core.errors import ApiError
from app.iam.models import ExternalIdentityContext, Principal, SubjectPage
from app.iam.mock import MockIamProvider
from app.iam.providers import (
    CaptchaChallenge,
    IamAuthError,
    IamProvider,
    IamUnavailableError,
    PasswordCredentials,
    UpstreamToken,
)
from app.iam.ruoyi import RuoYiIamProvider


class IamService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider: IamProvider = MockIamProvider() if settings.iam_mode == "mock" else RuoYiIamProvider(settings)

    async def exchange(self, ticket_code: str) -> tuple[UpstreamToken, Principal]:
        return await self._establish(self.provider.exchange_ticket(ticket_code))

    async def login_password(self, credentials: PasswordCredentials) -> tuple[UpstreamToken, Principal]:
        return await self._establish(self.provider.login_password(credentials))

    async def captcha(self) -> CaptchaChallenge:
        try:
            return await self.provider.fetch_captcha()
        except IamUnavailableError as exc:
            raise ApiError(503, "IAM_UNAVAILABLE", str(exc)) from exc

    async def _establish(self, token_operation) -> tuple[UpstreamToken, Principal]:
        try:
            token = await token_operation
            identity = await self.provider.resolve_identity(token)
            return token, self._principal(identity)
        except IamAuthError as exc:
            raise ApiError(401, "AUTH_INVALID", str(exc)) from exc
        except IamUnavailableError as exc:
            raise ApiError(503, "IAM_UNAVAILABLE", str(exc)) from exc

    async def resolve(self, token: UpstreamToken) -> Principal:
        try:
            identity = await self.provider.resolve_identity(token)
            return self._principal(identity)
        except IamAuthError as exc:
            raise ApiError(401, "AUTH_EXPIRED", str(exc)) from exc
        except IamUnavailableError as exc:
            raise ApiError(503, "IAM_UNAVAILABLE", str(exc)) from exc

    async def search(self, subject_type: str, query: str, cursor: str | None, limit: int, token: UpstreamToken) -> SubjectPage:
        try:
            return await self.provider.search_subjects(subject_type, query, cursor, limit, token)
        except IamAuthError as exc:
            raise ApiError(401, "AUTH_EXPIRED", str(exc)) from exc
        except IamUnavailableError as exc:
            raise ApiError(503, "IAM_UNAVAILABLE", str(exc)) from exc

    def _principal(self, identity: ExternalIdentityContext) -> Principal:
        tenant_id = self.settings.tenant_map.get(identity.external_org_id)
        if not tenant_id:
            raise ApiError(403, "TENANT_UNMAPPED", "RuoYi organization is not mapped to a platform tenant")
        return Principal(
            provider=identity.provider,
            external_user_id=identity.external_user_id,
            external_org_id=identity.external_org_id,
            tenant_id=tenant_id,
            display_name=identity.display_name,
            user_type=identity.user_type,
            dept_ids=tuple(identity.dept_ids),
            role_codes=tuple(identity.role_codes),
        )

    async def close(self) -> None:
        await self.provider.close()