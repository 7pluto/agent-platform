from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.iam.models import ExternalIdentityContext, SubjectPage


class IamAuthError(Exception):
    """The upstream identity token is invalid or not authenticated."""


class IamUnavailableError(Exception):
    """The upstream IAM cannot be reached or violates the frozen contract."""


@dataclass(frozen=True)
class UpstreamToken:
    value: str


@dataclass(frozen=True)
class PasswordCredentials:
    username: str
    password: str
    code: str
    uuid: str


@dataclass(frozen=True)
class CaptchaChallenge:
    image: str
    uuid: str


class IamProvider(ABC):
    @abstractmethod
    async def exchange_ticket(self, ticket_code: str) -> UpstreamToken:
        raise NotImplementedError

    @abstractmethod
    async def login_password(self, credentials: PasswordCredentials) -> UpstreamToken:
        raise NotImplementedError

    @abstractmethod
    async def fetch_captcha(self) -> CaptchaChallenge:
        raise NotImplementedError

    @abstractmethod
    async def resolve_identity(self, token: UpstreamToken) -> ExternalIdentityContext:
        raise NotImplementedError

    @abstractmethod
    async def search_subjects(
        self, subject_type: str, query: str, cursor: str | None, limit: int, token: UpstreamToken
    ) -> SubjectPage:
        raise NotImplementedError

    async def close(self) -> None:
        return None


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload