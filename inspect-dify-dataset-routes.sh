#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/dify
grep -R -n -E '@console_ns.route\("/datasets|class Dataset.*Api|create.*by.*text|document.*create.*text' \
  api/controllers/console/datasets | head -n 240
