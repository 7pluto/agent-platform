#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify/docker
nohup sudo docker compose up -d >/tmp/dify-up.log 2>&1 &
echo $! >/tmp/dify-up.pid
echo "DIFY_UP_STARTED"
