#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify/docker

redis_password="$(grep '^REDIS_PASSWORD=' .env | cut -d= -f2-)"
if [[ -z "$redis_password" ]]; then
  echo "REDIS_PASSWORD is empty" >&2
  exit 1
fi

agent_server_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"

sed -i \
  -e "s#^CELERY_BROKER_URL=.*#CELERY_BROKER_URL=redis://:${redis_password}@redis:6379/1#" \
  -e "s#^EXPOSE_PLUGIN_DEBUGGING_PORT=.*#EXPOSE_PLUGIN_DEBUGGING_PORT=5003#" \
  -e "s#^DIFY_AGENT_SERVER_SECRET_KEY=.*#DIFY_AGENT_SERVER_SECRET_KEY=${agent_server_key}#" \
  .env
chmod 600 .env

sed -i \
  's#- "${EXPOSE_PLUGIN_DEBUGGING_PORT:-5003}:${PLUGIN_DEBUGGING_PORT:-5003}"#- "127.0.0.1:${EXPOSE_PLUGIN_DEBUGGING_PORT:-5003}:${PLUGIN_DEBUGGING_PORT:-5003}"#' \
  docker-compose.yaml

sudo docker compose config -q
sudo docker compose up -d --force-recreate redis worker worker_beat api api_websocket plugin_daemon agent_backend nginx

echo "RUNTIME_REPAIRED"
