#!/usr/bin/env bash
set -euo pipefail

sudo docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' agent-platform-agent-server-1
sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' agent-platform-agent-server-1 \
  | awk -F= '/^QWEN_API_KEY=/{print "container_key_length=" length($2)}'
