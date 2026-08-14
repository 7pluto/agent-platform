#!/usr/bin/env bash
set -euo pipefail
sudo docker exec docker-api-1 sh -lc "grep -R -n -E 'decrypt.*credential|encrypted_config' /app/api/services /app/api/core 2>/dev/null | head -100"
