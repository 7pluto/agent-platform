#!/usr/bin/env bash
set -euo pipefail

value="$(sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' docker-agent_backend-1 | grep '^DIFY_AGENT_SERVER_SECRET_KEY=' | cut -d= -f2-)"
printf 'encoded_len=%s ' "${#value}"
if printf '%s' "$value" | base64 -d >/tmp/dify-agent-key.bin 2>/dev/null; then
  printf 'decoded_len=%s base64_valid=yes\n' "$(wc -c </tmp/dify-agent-key.bin)"
else
  echo 'decoded_len=0 base64_valid=no'
fi
