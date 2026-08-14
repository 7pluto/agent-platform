#!/usr/bin/env bash
set -euo pipefail

dify_console="http://127.0.0.1:5200/console/api"
platform="http://127.0.0.1:8000/api/v1"
dify_cookies="$(mktemp)"
platform_cookies="$(mktemp)"
login_json="$(mktemp)"
key_json="$(mktemp)"
result_json="$(mktemp)"
trap 'rm -f "$dify_cookies" "$platform_cookies" "$login_json" "$key_json" "$result_json"' EXIT
chmod 600 "$dify_cookies" "$platform_cookies" "$login_json" "$key_json" "$result_json"

password_b64="$(printf %s 'DifyAdmin123!' | base64 -w0)"
curl -fsS -c "$dify_cookies" -b "$dify_cookies" -H 'Content-Type: application/json' \
  -d "{\"email\":\"admin@chenwh.xin\",\"password\":\"${password_b64}\",\"remember_me\":true}" \
  "$dify_console/login" >"$login_json"
dify_csrf="$(awk '$6 == "csrf_token" {print $7}' "$dify_cookies" | tail -n1)"

app_id="38aa1d12-5d85-4108-8280-2c4c908c7fd9"
curl -fsS -c "$dify_cookies" -b "$dify_cookies" -H "X-CSRF-Token: ${dify_csrf}" \
  -H 'Content-Type: application/json' -d '{}' "$dify_console/apps/$app_id/api-keys" >"$key_json"
dify_key="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$key_json")"

curl -fsS -c "$platform_cookies" -b "$platform_cookies" -H 'Content-Type: application/json' \
  -d '{"ticket_code":"dev-ticket"}' "$platform/auth/exchange" >"$login_json"
platform_csrf="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["csrf_token"])' "$login_json")"

python3 - "$dify_key" "$result_json.request" <<'PY'
import json, sys
json.dump({
    "slug": "dify-enterprise-knowledge-flow",
    "display_name": "Dify 企业知识 Flow",
    "description": "以 Tool 方式调用 Dify 企业知识 Flow，返回答案与检索证据",
    "flow_type": "CHATFLOW",
    "base_url": "http://dify-gateway/v1",
    "api_key": sys.argv[1],
    "tool_name": "dify_enterprise_knowledge_flow",
    "timeout_seconds": 90,
    "test_query": "标准交付口令是什么？只回答口令。",
}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
chmod 600 "$result_json.request"
http="$(curl -sS -o "$result_json" -w '%{http_code}' -c "$platform_cookies" -b "$platform_cookies" \
  -H "X-CSRF-Token: ${platform_csrf}" -H 'Content-Type: application/json' \
  --data-binary "@$result_json.request" "$platform/dify-flow-tools")"
rm -f "$result_json.request"
unset dify_key

python3 - "$http" "$result_json" <<'PY'
import json, sys
payload=json.load(open(sys.argv[2], encoding="utf-8"))
safe={k: payload.get(k) for k in ("resource_id", "resource_version_id", "resource_type", "version_number", "status", "content_hash")}
safe["http_status"]=sys.argv[1]
safe["secret_ref"]=((payload.get("config") or {}).get("secret_ref"))
safe["kind"]=((payload.get("config") or {}).get("kind"))
print(json.dumps(safe, ensure_ascii=False))
PY
test "$http" = 201
