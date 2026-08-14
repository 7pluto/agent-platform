#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify
grep -R -n -E '@console_ns.route\("/apps|class App.*Api|class AppCreate|model-config|publish' \
  api/controllers/console/app | head -n 320
