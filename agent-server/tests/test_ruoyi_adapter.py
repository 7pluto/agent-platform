import asyncio
import json

import httpx

from app.config import Settings
from app.iam.providers import PasswordCredentials
from app.iam.ruoyi import RuoYiIamProvider


def test_standard_ruoyi_adapter_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/captchaImage":
            return httpx.Response(200, json={"code": 200, "img": "base64-image", "uuid": "captcha-uuid"})
        if request.url.path == "/login":
            assert json.loads(request.content) == {
                "username": "admin",
                "password": "password",
                "code": "1234",
                "uuid": "captcha-uuid",
            }
            return httpx.Response(200, json={"code": 200, "token": "ruoyi-token"})
        if request.url.path == "/agent-iam/me":
            assert request.headers["authorization"] == "Bearer ruoyi-token"
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "userId": 1,
                    "userName": "admin",
                    "nickName": "管理员",
                    "orgId": "ruoyi-default",
                    "dept": {"deptId": 100, "deptName": "研发"},
                    "roles": ["admin"],
                },
            )
        if request.url.path == "/agent-iam/users":
            return httpx.Response(200, json={"code": 200, "data": [{"userId": 2, "nickName": "用户"}]})
        if request.url.path == "/agent-iam/departments":
            return httpx.Response(200, json={"code": 200, "data": [{"deptId": 101, "deptName": "平台", "parentId": 100}]})
        raise AssertionError(f"unexpected request: {request.url}")

    async def run() -> None:
        provider = RuoYiIamProvider(
            Settings(
                iam_mode="ruoyi",
                ruoyi_base_url="http://ruoyi.test",
                ruoyi_default_org_id="ruoyi-default",
            )
        )
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        captcha = await provider.fetch_captcha()
        assert captcha.uuid == "captcha-uuid"
        token = await provider.login_password(PasswordCredentials("admin", "password", "1234", captcha.uuid))
        identity = await provider.resolve_identity(token)
        assert identity.external_user_id == "1"
        assert identity.external_org_id == "ruoyi-default"
        assert identity.dept_ids == ["100"]
        assert identity.role_codes == ["admin"]
        users = await provider.search_subjects("USER", "用户", None, 20, token)
        assert users.items[0].display_name == "用户"
        departments = await provider.search_subjects("DEPT", "平台", None, 20, token)
        assert departments.items[0].parent_id == "100"
        await provider.close()

    asyncio.run(run())