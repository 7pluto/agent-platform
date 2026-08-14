#!/usr/bin/env bash
set -euo pipefail

for container_name in agent-platform-agent-server-1 agent-platform-agent-worker-1; do
  if sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container_name" | grep -q '^QWEN_API_KEY='; then
    echo "${container_name}:QWEN_API_KEY_PRESENT"
  else
    echo "${container_name}:QWEN_API_KEY_ABSENT"
  fi
done
