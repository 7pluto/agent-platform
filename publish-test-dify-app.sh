#!/usr/bin/env bash
set -euo pipefail

console_base="http://127.0.0.1:5200/console/api"
service_base="http://127.0.0.1:5200/v1"
cookie_jar="/tmp/dify-admin.cookies"
app_id="$(cat /tmp/dify-app-knowledge-id)"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

enable_http="$(curl -sS -o /tmp/dify-api-enable.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d '{"enable_api":true}' \
  "$console_base/apps/$app_id/api-enable")"
printf 'api_enable_http=%s\n' "$enable_http"

key_http="$(curl -sS -o /tmp/dify-app-api-key.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d '{}' \
  "$console_base/apps/$app_id/api-keys")"

api_key="$(python3 -c 'import json; print(json.load(open("/tmp/dify-app-api-key.json"))["token"])')"
printf 'api_key_create_http=%s token_length=%s\n' "$key_http" "${#api_key}"

chmod 600 /tmp/dify-app-api-key.json
payload='{"inputs":{},"query":"标准交付口令是什么？只回答口令。","response_mode":"blocking","user":"codex-acceptance"}'
invoke_http="$(curl -sS -o /tmp/dify-published-chat-response.json -w '%{http_code}' \
  -H "Authorization: Bearer ${api_key}" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "$service_base/chat-messages")"

printf 'published_invoke_http=%s\n' "$invoke_http"
python3 - <<'PY'
import json
with open('/tmp/dify-published-chat-response.json', encoding='utf-8') as handle:
    payload = json.load(handle)
metadata = payload.get('metadata') or {}
usage = metadata.get('usage') or {}
print(json.dumps({
    'answer': payload.get('answer'),
    'conversation_id': payload.get('conversation_id'),
    'retriever_resource_count': len(metadata.get('retriever_resources') or []),
    'total_tokens': usage.get('total_tokens'),
}, ensure_ascii=False))
PY

unset api_key
rm -f /tmp/dify-app-api-key.json
