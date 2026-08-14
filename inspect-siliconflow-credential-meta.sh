#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/dify/docker
sudo docker compose exec -T db_postgres psql -U postgres -d dify -At <<'SQL'
select tenant_id || '|' || provider_name || '|' || id || '|' || coalesce(credential_name,'') || '|' ||
       coalesce((select string_agg(key, ',') from jsonb_object_keys(encrypted_config::jsonb) key), '')
from provider_credentials
where provider_name like '%siliconflow%';
SQL
