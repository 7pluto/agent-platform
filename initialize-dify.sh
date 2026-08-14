#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
rm -f "$cookie_jar"

curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
  -H 'Content-Type: application/json' \
  -d '{"password":"DifyAdmin123!"}' \
  "$base_url/init" >/tmp/dify-init-response.json

curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@chenwh.xin","name":"管理员","password":"DifyAdmin123!","language":"zh-Hans"}' \
  "$base_url/setup" >/tmp/dify-setup-response.json

printf 'init=' && cat /tmp/dify-init-response.json
printf '\nsetup=' && cat /tmp/dify-setup-response.json
printf '\nstatus=' && curl -fsS "$base_url/setup"
printf '\n'
