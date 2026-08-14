#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
label="service"
app_id="$(cat /tmp/dify-app-service-id)"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

python3 - /tmp/dify-app-service-configured.json /tmp/dify-agent-stream-payload.json <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    detail = json.load(handle)
payload = {
    'inputs': {},
    'query': '战略客户核心业务完全不可用，应定为什么级别？多久通知谁？事件识别短语是什么？',
    'response_mode': 'streaming',
    'retriever_from': 'dev',
    'model_config': detail.get('model_config') or {},
}
with open(sys.argv[2], 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False)
PY

http_status="$(curl -sS -N -o /tmp/dify-agent-stream.sse -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/dify-agent-stream-payload.json \
  "$base_url/apps/$app_id/chat-messages")"

printf 'agent_stream_http=%s\n' "$http_status"
python3 - <<'PY'
import json

answer_parts = []
events = []
retriever_resources = []
usage = None
with open('/tmp/dify-agent-stream.sse', encoding='utf-8') as handle:
    for raw in handle:
        if not raw.startswith('data:'):
            continue
        text = raw[5:].strip()
        if not text or text == '[DONE]':
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        events.append(event.get('event'))
        if event.get('answer'):
            answer_parts.append(event['answer'])
        metadata = event.get('metadata') or {}
        if metadata.get('retriever_resources'):
            retriever_resources = metadata['retriever_resources']
        if metadata.get('usage'):
            usage = metadata['usage']

print(json.dumps({
    'events': events,
    'answer': ''.join(answer_parts),
    'retriever_resource_count': len(retriever_resources),
    'usage': usage,
}, ensure_ascii=False))
PY
