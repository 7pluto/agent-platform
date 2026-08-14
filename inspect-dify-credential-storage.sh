#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/dify/docker
sudo docker compose exec -T db_postgres psql -U postgres -d dify -At <<'SQL'
select table_name || ':' || column_name
from information_schema.columns
where table_schema='public'
  and (column_name like '%credential%' or column_name like '%encrypted%')
order by table_name, ordinal_position;
SQL
