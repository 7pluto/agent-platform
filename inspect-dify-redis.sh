#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify/docker
sed -n '480,530p' docker-compose.yaml
echo "--- redis env config ---"
sed -n '1,80p' envs/databases/redis.env.example
api_pw="$(sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' docker-api-1 | grep '^REDIS_PASSWORD=' | cut -d= -f2- || true)"
worker_pw="$(sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' docker-worker-1 | grep '^REDIS_PASSWORD=' | cut -d= -f2- || true)"
redis_pw="$(sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' docker-redis-1 | grep '^REDISCLI_AUTH=' | cut -d= -f2- || true)"
broker_url="$(sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' docker-worker-1 | grep '^CELERY_BROKER_URL=' | cut -d= -f2- || true)"
printf 'api_len=%s worker_len=%s redis_len=%s api_redis_equal=%s worker_redis_equal=%s broker_url_set=%s\n' \
  "${#api_pw}" "${#worker_pw}" "${#redis_pw}" \
  "$([ "$api_pw" = "$redis_pw" ] && echo yes || echo no)" \
  "$([ "$worker_pw" = "$redis_pw" ] && echo yes || echo no)" \
  "$([ -n "$broker_url" ] && echo yes || echo no)"

if sudo docker exec docker-redis-1 redis-cli -a "$redis_pw" ping 2>/dev/null | grep -q PONG; then
  echo "redis_auth=success"
else
  echo "redis_auth=failed"
fi
