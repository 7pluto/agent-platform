#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify/docker
sudo docker compose logs --tail=80 agent_backend
echo "--- validator source ---"
sudo docker run --rm --entrypoint sh langgenius/dify-agent-backend:1.16.1 -c \
  "grep -R -n 'must decode to exactly 32' /app /usr/local/lib/python3.12/site-packages 2>/dev/null | head -n 10"
