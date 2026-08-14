#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
password_b64="$(printf '%s' 'DifyAdmin123!' | base64 -w0)"

login_status="$(curl -sS -o /tmp/dify-login-response.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"admin@chenwh.xin\",\"password\":\"${password_b64}\",\"remember_me\":true}" \
  "$base_url/login")"

printf 'login_http=%s\n' "$login_status"
cat /tmp/dify-login-response.json
printf '\n'

csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"
printf 'csrf_present=%s\n' "$([ -n "$csrf_token" ] && echo yes || echo no)"

curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  "$base_url/account/profile" >/tmp/dify-profile.json
printf 'profile=' && cat /tmp/dify-profile.json && printf '\n'
