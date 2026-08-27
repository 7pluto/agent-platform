from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import Settings
from app.iam.models import ExternalIdentityContext, Subject, SubjectPage
from app.iam.providers import (
    CaptchaChallenge,
    IamAuthError,
    IamProvider,
    IamUnavailableError,
    PasswordCredentials,
    UpstreamToken,
    unwrap_data,
)


class RuoYiIamProvider(IamProvider):
    """Adapter for standard RuoYi login plus the minimal read-only IAM extension."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            timeout=settings.ruoyi_timeout_seconds,
            verify=settings.ruoyi_verify_tls,
            follow_redirects=False,
        )

    def _url(self, path: str) -> str:
        return urljoin(f"{self.settings.ruoyi_base_url.rstrip('/')}/", path.lstrip("/"))

    @staticmethod
    def _json(response: httpx.Response, operation: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise IamUnavailableError(f"RuoYi {operation} response is not JSON") from exc
        if not isinstance(payload, dict):
            raise IamUnavailableError(f"RuoYi {operation} response has an invalid shape")
        return payload

    @staticmethod
    def _raise_for_response(response: httpx.Response, payload: dict[str, Any], operation: str) -> None:
        code = payload.get("code")
        if response.status_code in (401, 403) or code in (401, 403):
            raise IamAuthError(f"RuoYi {operation} was rejected")
        if response.status_code >= 500 or (isinstance(code, int) and code >= 500):
            raise IamUnavailableError(f"RuoYi {operation} failed")
        if response.status_code >= 400 or (isinstance(code, int) and code not in (200, 0)):
            raise IamAuthError(f"RuoYi {operation} was rejected")

    async def exchange_ticket(self, ticket_code: str) -> UpstreamToken:
        try:
            response = await self.client.post(self._url(self.settings.ruoyi_ticket_path), json={"ticketCode": ticket_code})
        except httpx.HTTPError as exc:
            raise IamUnavailableError("RuoYi ticket endpoint is unavailable") from exc
        payload = self._json(response, "ticket")
        self._raise_for_response(response, payload, "ticket")
        token = self._pick(unwrap_data(payload), "token", "accessToken", "access_token")
        if not token:
            raise IamUnavailableError("RuoYi ticket response has no token")
        return UpstreamToken(str(token))

    async def fetch_captcha(self) -> CaptchaChallenge:
        try:
            response = await self.client.get(self._url(self.settings.ruoyi_captcha_path))
        except httpx.HTTPError as exc:
            raise IamUnavailableError("RuoYi captcha endpoint is unavailable") from exc
        payload = self._json(response, "captcha")
        self._raise_for_response(response, payload, "captcha")
        raw = unwrap_data(payload)
        image = self._pick(raw, "img", "image")
        uuid = self._pick(raw, "uuid")
        if not image or not uuid:
            raise IamUnavailableError("RuoYi captcha response is incomplete")
        return CaptchaChallenge(image=str(image), uuid=str(uuid))

    async def login_password(self, credentials: PasswordCredentials) -> UpstreamToken:
        try:
            response = await self.client.post(
                self._url(self.settings.ruoyi_login_path),
                json={
                    "username": credentials.username,
                    "password": credentials.password,
                    "code": credentials.code,
                    "uuid": credentials.uuid,
                },
            )
        except httpx.HTTPError as exc:
            raise IamUnavailableError("RuoYi login endpoint is unavailable") from exc
        payload = self._json(response, "login")
        self._raise_for_response(response, payload, "login")
        token = self._pick(unwrap_data(payload), "token", "accessToken", "access_token")
        if not token:
            raise IamUnavailableError("RuoYi login response has no token")
        return UpstreamToken(str(token))

    async def resolve_identity(self, token: UpstreamToken) -> ExternalIdentityContext:
        try:
            response = await self.client.get(
                self._url(self.settings.ruoyi_current_user_path),
                headers={"Authorization": f"Bearer {token.value}"},
            )
        except httpx.HTTPError as exc:
            raise IamUnavailableError("RuoYi current-user endpoint is unavailable") from exc
        payload = self._json(response, "current-user")
        self._raise_for_response(response, payload, "current-user")
        return self._parse_identity(unwrap_data(payload))

    async def search_subjects(
        self, subject_type: str, query: str, cursor: str | None, limit: int, token: UpstreamToken
    ) -> SubjectPage:
        subject_type = subject_type.upper()
        if subject_type == "USER":
            path = self.settings.ruoyi_user_search_path
            params = {"name": query, "limit": str(limit)}
        elif subject_type == "DEPT":
            path = self.settings.ruoyi_dept_path
            params = {"name": query, "limit": str(limit)}
        elif subject_type == "ROLE":
            path = self.settings.ruoyi_role_search_path
            params = {"roleName": query, "pageNum": "1", "pageSize": str(limit)}
        else:
            return SubjectPage(items=[])
        try:
            response = await self.client.get(
                self._url(path), params=params, headers={"Authorization": f"Bearer {token.value}"}
            )
        except httpx.HTTPError as exc:
            raise IamUnavailableError("RuoYi directory endpoint is unavailable") from exc
        payload = self._json(response, "directory")
        self._raise_for_response(response, payload, "directory")
        raw = unwrap_data(payload)
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get("items") or raw.get("rows") or raw.get("records") or []
        else:
            items = []
        # Standard RuoYi list endpoints keep rows at the response top level
        # rather than inside data; support both shapes without a Java change.
        if not items and isinstance(payload.get("rows"), list):
            items = payload["rows"]
        return SubjectPage(
            items=[self._parse_subject(item, subject_type) for item in items[:limit]],
            next_cursor=None,
        )

    def _parse_identity(self, raw: Any) -> ExternalIdentityContext:
        if not isinstance(raw, dict):
            raise IamUnavailableError("RuoYi identity response has an invalid shape")
        user = raw.get("user") or raw
        dept = raw.get("dept") or user.get("dept") or {}
        external_user_id = self._pick(raw, "userId", "user_id") or self._pick(user, "userId", "user_id")
        external_org_id = self._pick(raw, "orgId", "org_id") or self.settings.ruoyi_default_org_id
        if not external_user_id or not external_org_id:
            raise IamUnavailableError("RuoYi identity is missing userId or organization")
        dept_ids = [str(dept["deptId"])] if isinstance(dept, dict) and dept.get("deptId") else []
        roles = raw.get("roles") or user.get("roles") or []
        role_codes = [
            str(item.get("roleKey")) if isinstance(item, dict) and item.get("roleKey") else str(item)
            for item in roles
            if item
        ]
        return ExternalIdentityContext(
            provider="ruoyi",
            external_user_id=str(external_user_id),
            external_org_id=str(external_org_id),
            display_name=str(self._pick(raw, "nickName", "nickname", "userName", "username") or external_user_id),
            user_type=self._pick(raw, "userType", "user_type"),
            dept_ids=dept_ids,
            role_codes=role_codes,
        )

    @staticmethod
    def _parse_subject(item: Any, subject_type: str) -> Subject:
        if not isinstance(item, dict):
            return Subject(type=subject_type, external_id=str(item), display_name=str(item))
        if subject_type == "USER":
            key_candidates = ("userId", "id")
            name_candidates = ("nickName", "userName", "name")
            parent = item.get("deptId") or item.get("parentId")
        elif subject_type == "ROLE":
            key_candidates = ("roleKey", "roleId", "id")
            name_candidates = ("roleName", "name", "roleKey")
            parent = None
        else:
            key_candidates = ("deptId", "id")
            name_candidates = ("deptName", "name")
            parent = item.get("parentId")
        external_id = next((item.get(key) for key in key_candidates if item.get(key) is not None), "")
        name = next((item.get(candidate) for candidate in name_candidates if item.get(candidate)), external_id)
        return Subject(
            type=subject_type,
            external_id=str(external_id),
            display_name=str(name),
            parent_id=str(parent) if parent is not None else None,
        )

    @staticmethod
    def _pick(payload: Any, *keys: str) -> Any:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            if payload.get(key) is not None:
                return payload[key]
        return None

    async def close(self) -> None:
        await self.client.aclose()
