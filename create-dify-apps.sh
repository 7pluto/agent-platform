#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

create_app() {
  local name="$1"
  local mode="$2"
  local description="$3"
  local output_file="$4"
  local payload
  payload="$(python3 -c 'import json,sys; print(json.dumps({"name":sys.argv[1],"mode":sys.argv[2],"description":sys.argv[3],"icon_type":"emoji","icon":"🤖","icon_background":"#E4FBCC"}, ensure_ascii=False))' "$name" "$mode" "$description")"
  local status
  status="$(curl -sS -o "$output_file" -w '%{http_code}' \
    -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "$base_url/apps")"
  local app_id
  app_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$output_file")"
  printf 'created name=%s mode=%s http=%s id=%s\n' "$name" "$mode" "$status" "$app_id"
  printf '%s' "$app_id"
}

knowledge_id="$(create_app '企业知识助手' 'chat' '基于企业制度、产品交付与客服规则的知识问答助手' /tmp/dify-app-knowledge.json | tail -n1)"
service_id="$(create_app '客户服务 Agent' 'agent-chat' '可自主分析客户问题并依据服务规则给出升级建议' /tmp/dify-app-service.json | tail -n1)"
delivery_id="$(create_app '交付方案助手' 'chat' '生成遵循 RuoYi 零改造原则的交付建议' /tmp/dify-app-delivery.json | tail -n1)"

printf '%s' "$knowledge_id" >/tmp/dify-app-knowledge-id
printf '%s' "$service_id" >/tmp/dify-app-service-id
printf '%s' "$delivery_id" >/tmp/dify-app-delivery-id

for pair in knowledge:$knowledge_id service:$service_id delivery:$delivery_id; do
  label="${pair%%:*}"
  app_id="${pair#*:}"
  curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    "$base_url/apps/$app_id" >"/tmp/dify-app-${label}-detail.json"
  python3 - "$label" "/tmp/dify-app-${label}-detail.json" <<'PY'
import json
import sys
with open(sys.argv[2], encoding='utf-8') as handle:
    payload = json.load(handle)
config = payload.get('model_config') or {}
print(json.dumps({
    'label': sys.argv[1],
    'id': payload.get('id'),
    'mode': payload.get('mode'),
    'model': config.get('model'),
    'prompt_type': config.get('prompt_type'),
    'dataset_configs': config.get('dataset_configs'),
    'agent_mode': config.get('agent_mode'),
}, ensure_ascii=False))
PY
done
