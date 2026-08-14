#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
dataset_id="$(cat /tmp/dify-dataset-id)"
cookie_jar="/tmp/dify-admin.cookies"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

queries=(
  '员工制度的内部识别码是什么？'
  '标准交付口令是什么？'
  'P0事件的识别短语是什么？'
)

for index in "${!queries[@]}"; do
  payload="$(python3 -c 'import json,sys; print(json.dumps({"query":sys.argv[1]}))' "${queries[$index]}")"
  response_file="/tmp/dify-retrieval-${index}.json"
  http_status="$(curl -sS -o "$response_file" -w '%{http_code}' \
    -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "$base_url/datasets/$dataset_id/hit-testing")"
  printf 'query=%s http=%s\n' "${queries[$index]}" "$http_status"
  python3 - "$response_file" <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    payload = json.load(handle)
for record in payload.get('records', [])[:3]:
    segment = record.get('segment') or {}
    print(json.dumps({
        'document': segment.get('document', {}).get('name') if isinstance(segment.get('document'), dict) else segment.get('document_id'),
        'score': record.get('score'),
        'content': (segment.get('content') or '')[:180],
    }, ensure_ascii=False))
PY
done
