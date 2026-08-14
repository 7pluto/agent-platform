#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/agent-platform
release=/tmp/agent-platform-dify-vault-20260812.tgz
stamp=20260812-dify-vault

test -f "$release"
mkdir -p /home/ubuntu/backups
tar -czf "/home/ubuntu/backups/agent-platform-${stamp}.tgz" \
  -C "$root" agent-server agent-console docker-compose.yml .env

if ! grep -q '^AGENT_SECRET_ENCRYPTION_KEY=' "$root/.env"; then
  vault_key="$(sudo docker exec agent-platform-agent-server-1 python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  printf '\nAGENT_SECRET_ENCRYPTION_KEY=%s\n' "$vault_key" >>"$root/.env"
  unset vault_key
fi
chmod 600 "$root/.env"
sudo tar -xzf "$release" -C "$root" --no-same-owner
sudo chown -R ubuntu:ubuntu "$root/agent-server" "$root/agent-console" "$root/docker-compose.yml" "$root/.env.example"

cd "$root"
sudo docker compose build agent-server agent-worker agent-migrate agent-console
sudo docker compose run --rm agent-migrate
sudo docker compose up -d --no-deps --force-recreate agent-server agent-worker agent-console
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/api/v1/health
printf '\nbackup=%s\n' "/home/ubuntu/backups/agent-platform-${stamp}.tgz"
