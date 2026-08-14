#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
provider="langgenius/siliconflow/siliconflow"

/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"
api_key="$(< /tmp/siliconflow-api-key)"

if [[ -z "$api_key" ]]; then
  echo "QWEN_API_KEY is unavailable" >&2
  exit 1
fi

payload="$(python3 -c 'import json,sys; print(json.dumps({"credentials":{"api_key":sys.argv[1],"use_international_endpoint":"false"}}))' "$api_key")"

validate_http="$(curl -sS -o /tmp/dify-siliconflow-validate.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "$base_url/workspaces/current/model-providers/$provider/credentials/validate")"

printf 'validate_http=%s result=' "$validate_http"
cat /tmp/dify-siliconflow-validate.json
printf '\n'

create_payload="$(python3 -c 'import json,sys; print(json.dumps({"name":"SiliconFlow","credentials":{"api_key":sys.argv[1],"use_international_endpoint":"false"}}))' "$api_key")"
create_http="$(curl -sS -o /tmp/dify-siliconflow-create.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d "$create_payload" \
  "$base_url/workspaces/current/model-providers/$provider/credentials")"

printf 'create_http=%s result=' "$create_http"
cat /tmp/dify-siliconflow-create.json
printf '\n'

unset api_key payload create_payload
rm -f /tmp/siliconflow-api-key

curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  "$base_url/workspaces/current/model-providers?model_type=llm" >/tmp/dify-llm-providers.json

python3 - <<'PY'
import json
with open('/tmp/dify-llm-providers.json', encoding='utf-8') as handle:
    data = json.load(handle).get('data', [])
for item in data:
    if 'siliconflow' in str(item.get('provider', '')).lower():
        print(json.dumps({
            'provider': item.get('provider'),
            'status': item.get('status'),
            'credential_count': len(item.get('provider_credential_schema', {}).get('credential_form_schemas', [])),
        }, ensure_ascii=False))
PY
