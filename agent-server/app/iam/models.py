from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExternalIdentityContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    external_user_id: str
    external_org_id: str
    display_name: str
    user_type: str | None = None
    dept_ids: list[str] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    authenticated_at: datetime = Field(default_factory=utc_now)
    upstream_expires_at: datetime | None = None


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    external_user_id: str
    external_org_id: str
    tenant_id: str
    display_name: str
    user_type: str | None = None
    dept_ids: tuple[str, ...] = ()
    role_codes: tuple[str, ...] = ()


class Subject(BaseModel):
    type: str
    external_id: str
    display_name: str
    parent_id: str | None = None


class SubjectPage(BaseModel):
    items: list[Subject]
    next_cursor: str | None = None
