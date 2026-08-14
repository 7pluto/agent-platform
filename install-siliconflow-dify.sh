#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
plugin_identifier="langgenius/siliconflow:0.0.59@8f02741bb210eac68b68263c1cbede0e0637f2d1ad082895906e03253461729c"

/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

http_status="$(curl -sS -o /tmp/dify-plugin-install.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d "{\"plugin_unique_identifiers\":[\"${plugin_identifier}\"]}" \
  "$base_url/workspaces/current/plugin/install/marketplace")"

printf 'install_http=%s\n' "$http_status"
cat /tmp/dify-plugin-install.json
printf '\n'

for attempt in $(seq 1 30); do
  sleep 3
  curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    "$base_url/workspaces/current/plugin/tasks?page=1&page_size=20" >/tmp/dify-plugin-tasks.json
  if grep -q '"status":"success"' /tmp/dify-plugin-tasks.json || grep -q '"status":"completed"' /tmp/dify-plugin-tasks.json; then
    break
  fi
done

printf 'tasks=' && cat /tmp/dify-plugin-tasks.json && printf '\n'
printf 'plugins=' && curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  "$base_url/workspaces/current/plugin/list?page=1&page_size=100"
printf '\n'
