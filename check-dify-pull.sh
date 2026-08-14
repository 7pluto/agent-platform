#!/usr/bin/env bash
set -u

pid="$(cat /tmp/dify-pull.pid)"
if kill -0 "$pid" 2>/dev/null; then
  echo "PULL_RUNNING"
else
  echo "PULL_FINISHED"
fi

tail -n 35 /tmp/dify-pull.log
df -h /
free -h
