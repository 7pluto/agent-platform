#!/usr/bin/env bash
set -euo pipefail

compose_dir=/home/ubuntu/ruoyi-vue-standalone
repair_sql="$compose_dir/repair-mysql-utf8.sql"
mysql_container=ruoyi-vue-standalone-ruoyi-mysql-1
backup_dir="$compose_dir/backups"
backup_file="$backup_dir/ry-vue-before-utf8-fix-$(date +%Y%m%d-%H%M%S).sql"

mkdir -p "$backup_dir"
sudo docker exec "$mysql_container" sh -lc 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --default-character-set=utf8mb4 ry-vue' > "$backup_file"
sudo docker exec -i "$mysql_container" sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4' < "$repair_sql"

cd "$compose_dir"
sudo docker compose restart ruoyi-server
sudo docker exec "$mysql_container" sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 -N -e "SELECT menu_id,menu_name,HEX(menu_name) FROM \`ry-vue\`.sys_menu WHERE parent_id=0 ORDER BY order_num;"'
printf 'backup=%s\n' "$backup_file"