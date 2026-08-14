#!/usr/bin/env bash
set -euo pipefail

dataset_id="$(cat /tmp/dify-dataset-id)"
batch="$(cat /tmp/dify-dataset-batch)"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' /tmp/dify-admin.cookies | tail -n1)"

for attempt in $(seq 1 12); do
  response="$(curl -fsS -b /tmp/dify-admin.cookies \
    -H "X-CSRF-Token: ${csrf_token}" \
    "http://127.0.0.1:5200/console/api/datasets/${dataset_id}/batch/${batch}/indexing-status")"
  printf 'attempt=%s status=%s\n' "$attempt" "$response"
  if [[ "$response" == *'"completed"'* ]] && [[ "$response" != *'"indexing"'* ]] && [[ "$response" != *'"waiting"'* ]]; then
    break
  fi
  sleep 5
done

cd /home/ubuntu/dify/docker
sudo docker compose logs --since=6m --tail=220 worker plugin_daemon \
  | grep -E 'ERROR|error|document|embedding|index' \
  | tail -n 120 || true
