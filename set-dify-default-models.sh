#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
provider="langgenius/siliconflow/siliconflow"

/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

payload="$(python3 - <<'PY'
import json
print(json.dumps({
    'model_settings': [
        {'model_type': 'llm', 'provider': 'langgenius/siliconflow/siliconflow', 'model': 'Qwen/Qwen3-8B'},
        {'model_type': 'text-embedding', 'provider': 'langgenius/siliconflow/siliconflow', 'model': 'BAAI/bge-large-zh-v1.5'},
    ]
}))
PY
)"

http_status="$(curl -sS -o /tmp/dify-default-models-set.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "$base_url/workspaces/current/default-model")"

printf 'set_http=%s result=' "$http_status"
cat /tmp/dify-default-models-set.json
printf '\n'

for model_type in llm text-embedding; do
  printf '%s=' "$model_type"
  curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    "$base_url/workspaces/current/default-model?model_type=${model_type}"
  printf '\n'
done
