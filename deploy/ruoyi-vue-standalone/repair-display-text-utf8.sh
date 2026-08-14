#!/usr/bin/env bash
set -euo pipefail

compose_dir=/home/ubuntu/ruoyi-vue-standalone
repair_sql="$compose_dir/repair-display-text-utf8.sql"
mysql_container=ruoyi-vue-standalone-ruoyi-mysql-1
backup_dir="$compose_dir/backups"
backup_file="$backup_dir/display-tables-before-utf8-fix-$(date +%Y%m%d-%H%M%S).sql"

mkdir -p "$backup_dir"
sudo docker exec "$mysql_container" sh -lc 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --default-character-set=utf8mb4 ry-vue sys_dept sys_user sys_post sys_role sys_menu sys_dict_type sys_dict_data sys_config sys_notice sys_job' > "$backup_file"
sudo docker exec -i "$mysql_container" sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4' < "$repair_sql"
sudo docker exec "$mysql_container" sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 -N -e "SELECT nick_name,HEX(nick_name) FROM \`ry-vue\`.sys_user ORDER BY user_id LIMIT 2; SELECT role_name,HEX(role_name) FROM \`ry-vue\`.sys_role ORDER BY role_id LIMIT 2; SELECT dict_label,HEX(dict_label) FROM \`ry-vue\`.sys_dict_data ORDER BY dict_code LIMIT 3;"'
printf 'backup=%s\n' "$backup_file"
