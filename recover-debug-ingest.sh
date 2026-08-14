#!/usr/bin/env bash
set -euo pipefail
sudo docker exec agent-platform-postgres-1 psql -U agent -d agent_platform -c "update platform_knowledge_document set status='UPLOADED' where knowledge_resource_version_id='5410a2f7-0d93-4170-8857-1d1ff771c6e5' and status='PARSING'"
/tmp/debug-ingest.sh
