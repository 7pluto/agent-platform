#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
label="delivery"
app_id="$(cat /tmp/dify-app-delivery-id)"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

python3 - /tmp/dify-app-delivery-configured.json /tmp/dify-delivery-retest-payload.json <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    detail = json.load(handle)
payload = {
    'inputs': {},
    'query': '请用三点准确说明 RuoYi 对接、文件上传和4核4G并发约束。',
    'response_mode': 'blocking',
    'retriever_from': 'dev',
    'model_config': detail.get('model_config') or {},
}
with open(sys.argv[2], 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False)
PY

http_status="$(curl -sS -o /tmp/dify-delivery-retest-response.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/dify-delivery-retest-payload.json \
  "$base_url/apps/$app_id/chat-messages")"

printf 'delivery_retest_http=%s\n' "$http_status"
python3 - <<'PY'
import json
with open('/tmp/dify-delivery-retest-response.json', encoding='utf-8') as handle:
    payload = json.load(handle)
usage = (payload.get('metadata') or {}).get('usage') or {}
print(json.dumps({
    'answer': payload.get('answer'),
    'total_tokens': usage.get('total_tokens'),
}, ensure_ascii=False))
PY
