#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

run_app() {
  local label="$1"
  local query="$2"
  local app_id
  app_id="$(cat "/tmp/dify-app-${label}-id")"
  local config_file="/tmp/dify-app-${label}-configured.json"
  local payload_file="/tmp/dify-app-${label}-chat-payload.json"
  local response_file="/tmp/dify-app-${label}-chat-response.json"

  python3 - "$config_file" "$payload_file" "$query" <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    detail = json.load(handle)
payload = {
    'inputs': {},
    'query': sys.argv[3],
    'response_mode': 'blocking',
    'retriever_from': 'dev',
    'model_config': detail.get('model_config') or {},
}
with open(sys.argv[2], 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False)
PY

  http_status="$(curl -sS -o "$response_file" -w '%{http_code}' \
    -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    -H 'Content-Type: application/json' \
    --data-binary "@$payload_file" \
    "$base_url/apps/$app_id/chat-messages")"

  printf 'app=%s http=%s\n' "$label" "$http_status"
  python3 - "$response_file" <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    payload = json.load(handle)
metadata = payload.get('metadata') or {}
usage = metadata.get('usage') or {}
print(json.dumps({
    'answer': payload.get('answer'),
    'conversation_id': payload.get('conversation_id'),
    'message_id': payload.get('message_id'),
    'retriever_resources': metadata.get('retriever_resources'),
    'usage': {
        'prompt_tokens': usage.get('prompt_tokens'),
        'completion_tokens': usage.get('completion_tokens'),
        'total_tokens': usage.get('total_tokens'),
    },
    'error': payload.get('message') if payload.get('code') else None,
}, ensure_ascii=False))
PY
}

run_app knowledge '请只根据知识库回答：员工制度内部识别码是什么？发现疑似数据泄露后多久内联系哪个电话？'
run_app service '战略客户核心业务完全不可用，应定为什么级别？多久通知谁？事件识别短语是什么？'
run_app delivery '请用三点说明 RuoYi 对接、文件上传和4核4G并发约束。'
