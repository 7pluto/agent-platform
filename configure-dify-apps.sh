#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:5200/console/api"
cookie_jar="/tmp/dify-admin.cookies"
dataset_id="$(cat /tmp/dify-dataset-id)"
/tmp/login-dify.sh >/tmp/dify-login-check.log
csrf_token="$(awk '$6 == "csrf_token" {print $7}' "$cookie_jar" | tail -n1)"

configure_app() {
  local label="$1"
  local app_id_file="/tmp/dify-app-${label}-id"
  local detail_file="/tmp/dify-app-${label}-detail.json"
  local payload_file="/tmp/dify-app-${label}-config-payload.json"
  local response_file="/tmp/dify-app-${label}-config-response.json"
  local app_id
  app_id="$(cat "$app_id_file")"

  python3 - "$label" "$detail_file" "$payload_file" "$dataset_id" <<'PY'
import json
import sys

label, detail_path, output_path, dataset_id = sys.argv[1:]
with open(detail_path, encoding='utf-8') as handle:
    detail = json.load(handle)
current = detail.get('model_config') or {}

prompts = {
    'knowledge': (
        '你是企业知识助手。优先依据已绑定知识库回答，并清楚引用检索到的制度、FAQ或客服规则。'
        '如果知识库没有依据，请明确说不知道，不得编造内部信息。回复使用简体中文。'
    ),
    'service': (
        '你是客户服务 Agent。你需要分析客户等级、故障级别、响应时限和升级路径。'
        '所有规则必须来自已绑定知识库；不得承诺未经授权的退款，不得泄露密钥或其他租户数据。'
        '给出结论、依据和下一步动作，使用简体中文。不得猜测或编造来源文档名称；仅在检索元数据明确提供文档名时引用。'
    ),
    'delivery': (
        '你是 Enterprise Agent Platform 交付方案助手。以下是不可违背的架构事实：'
        '一、Python 主动适配 RuoYi L1 既有接口，严禁要求 RuoYi Java 主动适配 Agent Platform；Java 侧优先零改造。'
        '二、浏览器只上传给后端 API，严禁浏览器直传 MinIO。'
        '三、4核4G单机固定 Worker 并发1、知识入库并发1。'
        '当用户询问这些事项时必须逐字保留上述方向，不得改成 Java 实现或泛化建议。输出简洁、可执行的中文方案。'
    ),
}

payload = {
    'pre_prompt': prompts[label],
    'prompt_type': current.get('prompt_type') or 'simple',
    'chat_prompt_config': current.get('chat_prompt_config') or {},
    'completion_prompt_config': current.get('completion_prompt_config') or {},
    'user_input_form': current.get('user_input_form') or [],
    'dataset_query_variable': current.get('dataset_query_variable') or '',
    'more_like_this': current.get('more_like_this') or {'enabled': False},
    'opening_statement': {
        'knowledge': '您好，我可以查询企业制度、产品交付和客服规则。',
        'service': '您好，我是客户服务 Agent，请描述客户等级与问题现象。',
        'delivery': '您好，我可以生成 Agent Platform 交付方案。',
    }[label],
    'suggested_questions': {
        'knowledge': ['员工制度识别码是什么？', '标准版交付周期是多少？'],
        'service': ['战略客户核心业务不可用如何升级？', '退款可以由客服直接承诺吗？'],
        'delivery': ['给出 RuoYi 零改造对接方案', '4核4G如何限制并发？'],
    }[label],
    'sensitive_word_avoidance': current.get('sensitive_word_avoidance') or {'enabled': False},
    'speech_to_text': current.get('speech_to_text') or {'enabled': False},
    'text_to_speech': current.get('text_to_speech') or {'enabled': False},
    'file_upload': current.get('file_upload') or {},
    'suggested_questions_after_answer': current.get('suggested_questions_after_answer') or {'enabled': False},
    'retriever_resource': {'enabled': label in {'knowledge', 'service'}},
    'external_data_tools': current.get('external_data_tools') or [],
    'model': {
        'provider': 'langgenius/siliconflow/siliconflow',
        'name': 'Qwen/Qwen3-8B',
        'mode': 'chat',
        'completion_params': {'temperature': 0.2, 'max_tokens': 1024, 'enable_thinking': False},
    },
    'agent_mode': {
        'enabled': label == 'service',
        'strategy': 'react' if label == 'service' else None,
        'tools': [],
        'max_iteration': 3,
        'prompt': None,
    },
    'dataset_configs': {
        'retrieval_model': 'multiple',
        'datasets': {
            'datasets': ([{'dataset': {'enabled': True, 'id': dataset_id}}]
                         if label in {'knowledge', 'service'} else []),
        },
        'reranking_enable': False,
        'top_k': 3,
        'score_threshold_enabled': False,
        'score_threshold': None,
    },
    'system_parameters': current.get('system_parameters') or {},
}

with open(output_path, 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False)
PY

  http_status="$(curl -sS -o "$response_file" -w '%{http_code}' \
    -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    -H 'Content-Type: application/json' \
    --data-binary "@$payload_file" \
    "$base_url/apps/$app_id/model-config")"
  printf 'configure=%s http=%s response=' "$label" "$http_status"
  cat "$response_file"
  printf '\n'

  curl -fsS -c "$cookie_jar" -b "$cookie_jar" \
    -H "X-CSRF-Token: ${csrf_token}" \
    "$base_url/apps/$app_id" >"/tmp/dify-app-${label}-configured.json"

  python3 - "$label" "/tmp/dify-app-${label}-configured.json" <<'PY'
import json
import sys
with open(sys.argv[2], encoding='utf-8') as handle:
    payload = json.load(handle)
config = payload.get('model_config') or {}
print(json.dumps({
    'label': sys.argv[1],
    'model': config.get('model'),
    'agent_mode': config.get('agent_mode'),
    'dataset_configs': config.get('dataset_configs'),
    'pre_prompt': config.get('pre_prompt'),
}, ensure_ascii=False))
PY
}

configure_app knowledge
configure_app service
configure_app delivery
