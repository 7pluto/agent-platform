#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

file_ids=()
for file_path in /tmp/dify-hr-policy.txt /tmp/dify-product-faq.txt /tmp/dify-customer-service.txt; do
  response_file="/tmp/upload-$(basename "$file_path").json"
  http_status="$(curl -sS -o "$response_file" -w '%{http_code}' \
    -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    -F "file=@${file_path};type=text/plain" \
    "$base_url/files/upload")"
  file_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$response_file")"
  file_ids+=("$file_id")
  printf 'upload=%s http=%s file_id=%s\n' "$(basename "$file_path")" "$http_status" "$file_id"
done

payload="$(python3 - "${file_ids[@]}" <<'PY'
import json
import sys

print(json.dumps({
    'data_source': {
        'info_list': {
            'data_source_type': 'upload_file',
            'file_info_list': {'file_ids': sys.argv[1:]},
        },
    },
    'indexing_technique': 'high_quality',
    'process_rule': {'mode': 'automatic'},
    'doc_form': 'text_model',
    'doc_language': 'Chinese',
    'retrieval_model': {
        'search_method': 'semantic_search',
        'reranking_enable': False,
        'top_k': 3,
        'score_threshold_enabled': False,
        'score_threshold': None,
    },
    'embedding_model': 'BAAI/bge-large-zh-v1.5',
    'embedding_model_provider': 'langgenius/siliconflow/siliconflow',
}))
PY
)"

init_http="$(curl -sS -o /tmp/dify-dataset-init.json -w '%{http_code}' \
  -c "$cookie_jar" -b "$cookie_jar" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "$base_url/datasets/init")"

printf 'dataset_init_http=%s\n' "$init_http"
cat /tmp/dify-dataset-init.json
printf '\n'

python3 - <<'PY'
import json
with open('/tmp/dify-dataset-init.json', encoding='utf-8') as handle:
    payload = json.load(handle)
with open('/tmp/dify-dataset-id', 'w', encoding='utf-8') as handle:
    handle.write(payload['dataset']['id'])
with open('/tmp/dify-dataset-batch', 'w', encoding='utf-8') as handle:
    handle.write(payload['batch'])
PY

rm -f /tmp/dify-hr-policy.txt /tmp/dify-product-faq.txt /tmp/dify-customer-service.txt
