#!/usr/bin/env python3
"""Verify the deployed RuoYi password login without printing credentials/tokens."""

from __future__ import annotations

import base64
import http.cookiejar
import json
import urllib.error
import urllib.request


BASE = "https://agent.chenwh.xin/api/v1"


def main() -> None:
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def request(path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with opener.open(req, timeout=20) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    mode_status, mode = request("/auth/mode")
    captcha_status, captcha = request("/auth/ruoyi/captcha")
    image = captcha.get("image", "")
    captcha_valid = image.startswith("data:image/") and len(image) > 100
    # The deployed RuoYi acceptance environment currently has captcha disabled,
    # so the adapter returns an empty code/uuid pair while still exercising the
    # real upstream login endpoint.
    login_status, login = request("/auth/ruoyi/login", {"username": "admin", "password": "admin123", "code": "", "uuid": ""})
    principal = login.get("principal", {})
    print(json.dumps({
        "mode_status": mode_status,
        "mode": mode.get("mode"),
        "captcha_status": captcha_status,
        "captcha_image_present": captcha_valid,
        "login_status": login_status,
        "display_name": principal.get("display_name"),
        "tenant_id": principal.get("tenant_id"),
        "roles": principal.get("role_codes", []),
        "session_cookie_secure": any(cookie.secure for cookie in cookies),
    }, ensure_ascii=False, indent=2))
    assert mode_status == captcha_status == login_status == 200
    assert mode.get("mode") == "password"
    assert principal.get("external_user_id")
    assert any(cookie.secure for cookie in cookies)


if __name__ == "__main__":
    main()
