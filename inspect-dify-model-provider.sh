#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  "$base_url/workspaces/current/model-providers" >/tmp/dify-model-providers.json

python3 - <<'PY'
import json

with open('/tmp/dify-model-providers.json', encoding='utf-8') as handle:
    payload = json.load(handle)

for item in payload.get('data', []):
    provider = str(item.get('provider', ''))
    if 'siliconflow' not in provider.lower():
        continue
    print(json.dumps({
        'provider': provider,
        'configurate_methods': item.get('configurate_methods'),
        'credential_schema': item.get('provider_credential_schema'),
        'status': item.get('status'),
    }, ensure_ascii=False))
PY
