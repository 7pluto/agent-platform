#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json

for label in ('knowledge', 'service', 'delivery'):
    with open(f'/tmp/dify-app-{label}-detail.json', encoding='utf-8') as handle:
        payload = json.load(handle)
    config = payload.get('model_config') or {}
    print(label)
    for key, value in config.items():
        if key in {'pre_prompt', 'model', 'dataset_configs', 'agent_mode', 'retrieval_model', 'opening_statement', 'suggested_questions', 'retriever_resource'}:
            print(f'  {key}={json.dumps(value, ensure_ascii=False)}')
        else:
            print(f'  {key}: {type(value).__name__}')
PY
