#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify/docker

secret_key="$(openssl rand -hex 32)"
db_password="$(openssl rand -hex 24)"
redis_password="$(openssl rand -hex 24)"
sandbox_key="$(openssl rand -hex 24)"
plugin_daemon_key="$(openssl rand -hex 32)"
plugin_inner_key="$(openssl rand -hex 32)"
agent_server_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
agent_api_token="$(openssl rand -hex 32)"
agent_shell_token="$(openssl rand -hex 32)"
pgvector_password="$(openssl rand -hex 24)"

sed -i \
  -e "s/__SECRET_KEY__/${secret_key}/" \
  -e "s/__DB_PASSWORD__/${db_password}/" \
  -e "s/__REDIS_PASSWORD__/${redis_password}/g" \
  -e "s/__SANDBOX_API_KEY__/${sandbox_key}/g" \
  -e "s/__PLUGIN_DAEMON_KEY__/${plugin_daemon_key}/" \
  -e "s/__PLUGIN_INNER_KEY__/${plugin_inner_key}/" \
  -e "s/__AGENT_SERVER_KEY__/${agent_server_key}/" \
  -e "s/__AGENT_API_TOKEN__/${agent_api_token}/" \
  -e "s/__AGENT_SHELL_TOKEN__/${agent_shell_token}/" \
  -e "s/__PGVECTOR_PASSWORD__/${pgvector_password}/g" \
  .env

chmod 600 .env

if grep -qE '__[A-Z_]+__' .env; then
  echo "Dify environment still contains unresolved placeholders." >&2
  exit 1
fi

docker compose config -q
echo "CONFIG_OK"
docker compose config --services
