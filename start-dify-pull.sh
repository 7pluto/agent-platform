#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify/docker
nohup sudo docker compose pull >/tmp/dify-pull.log 2>&1 &
echo $! >/tmp/dify-pull.pid
echo "DIFY_PULL_STARTED"
