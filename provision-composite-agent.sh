#!/usr/bin/env bash
set -euo pipefail

base="http://127.0.0.1:8000/api/v1"
cookies="$(mktemp)"
work="$(mktemp -d)"
trap 'rm -rf "$work" "$cookies"' EXIT
chmod 700 "$work"
chmod 600 "$cookies"

json_value() {
  python3 - "$1" "$2" <<'PY'
import json,sys
value=json.load(open(sys.argv[1],encoding="utf-8"))
for part in sys.argv[2].split('.'):
    value=value[part]
print(value)
PY
}

login="$work/login.json"
curl -fsS -c "$cookies" -b "$cookies" -H 'Content-Type: application/json' \
  -d '{"ticket_code":"dev-ticket"}' "$base/auth/exchange" >"$login"
csrf="$(json_value "$login" csrf_token)"

post_json() {
  local path="$1" payload="$2" output="$3"
  curl -fsS -c "$cookies" -b "$cookies" -H "X-CSRF-Token: ${csrf}" \
    -H 'Content-Type: application/json' --data-binary "@$payload" "$base$path" >"$output"
}

create_resource() {
  local type="$1" slug="$2" name="$3" config_file="$4" prefix="$5"
  python3 - "$type" "$slug" "$name" "$config_file" "$work/${prefix}-definition-request.json" <<'PY'
import json,sys
config=json.load(open(sys.argv[4],encoding="utf-8"))
json.dump({"resource_type":sys.argv[1],"slug":sys.argv[2],"display_name":sys.argv[3],"draft_config":config},open(sys.argv[5],"w",encoding="utf-8"),ensure_ascii=False)
PY
  post_json /resources "$work/${prefix}-definition-request.json" "$work/${prefix}-definition.json"
  local resource_id
  resource_id="$(json_value "$work/${prefix}-definition.json" resource_id)"
  python3 - "$config_file" "$work/${prefix}-version-request.json" <<'PY'
import json,sys
json.dump({"config":json.load(open(sys.argv[1],encoding="utf-8"))},open(sys.argv[2],"w",encoding="utf-8"),ensure_ascii=False)
PY
  post_json "/resources/${resource_id}/versions" "$work/${prefix}-version-request.json" "$work/${prefix}-version.json"
  local version_id
  version_id="$(json_value "$work/${prefix}-version.json" resource_version_id)"
  printf '{}' >"$work/empty.json"
  post_json "/resource-versions/${version_id}/publish" "$work/empty.json" "$work/${prefix}-published.json"
  printf '%s' "$version_id"
}

chat_model_version="c0f13386-9fa7-4445-bb15-bed64476eb0d"
embedding_model_version="246a7680-396a-4eaf-a721-f85d7fed46bf"
dify_tool_version="b72f2cc6-ccfb-4c50-955c-760e3ec175db"

# Internal read-only CRM MCP connection and discovered Tool.
cat >"$work/mcp-connection.json" <<'JSON'
{"slug":"demo-crm-connection","display_name":"演示 CRM MCP 连接","endpoint":"http://demo-crm-mcp:8090/mcp","timeout_seconds":10,"auth_header":"Authorization","auth_scheme":"Bearer"}
JSON
post_json /mcp-connections "$work/mcp-connection.json" "$work/mcp-connection-result.json"
mcp_connection_version="$(json_value "$work/mcp-connection-result.json" resource_version_id)"
cat >"$work/mcp-tool.json" <<JSON
{"connection_version_id":"${mcp_connection_version}","tool_name":"query_customer","description":"按客户 ID 查询只读 CRM 客户信息","input_schema":{"type":"object","properties":{"customer_id":{"type":"string"}},"required":["customer_id"]},"slug":"query-customer","display_name":"查询 CRM 客户"}
JSON
post_json /mcp-tools/register "$work/mcp-tool.json" "$work/mcp-tool-result.json"
mcp_tool_version="$(json_value "$work/mcp-tool-result.json" resource_version_id)"

# Approved native calculator.
cat >"$work/calculator-config.json" <<'JSON'
{"kind":"NATIVE","native_name":"calculator","description":"执行仅包含数字和算术运算符的计算","input_schema":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}}
JSON
calculator_tool_version="$(create_resource TOOL calculator-tool "安全计算器" "$work/calculator-config.json" calculator)"

# Platform-owned Knowledge bound to the published Embedding Model version.
cat >"$work/knowledge-config.json" <<JSON
{"retrieval_top_k":5,"embedding_model_version_id":"${embedding_model_version}"}
JSON
knowledge_version="$(create_resource KNOWLEDGE platform-delivery-knowledge "平台交付知识库" "$work/knowledge-config.json" knowledge)"

# Generate a valid DOCX inside the existing API image, then upload through Agent API.
sudo docker run --rm -v "$work:/out" agent-platform-agent-server python -c 'from docx import Document; d=Document(); d.add_heading("Enterprise Agent Platform 交付规则",0); d.add_paragraph("平台知识标识：PLATFORM-RAG-2026。浏览器或客户端必须把 PDF/DOCX 上传到 Agent Platform 后端 API，由后端校验并写入私有 MinIO；禁止浏览器直传 MinIO。Python 主动适配 RuoYi L1，RuoYi Java 保持零改造。Dify Flow 只能作为版本化 Tool 接入 Agent，不替代平台的 Skill、MCP、RAG 与 Memory。"); d.save("/out/platform-delivery.docx")'
curl -fsS -c "$cookies" -b "$cookies" -H "X-CSRF-Token: ${csrf}" \
  -F "knowledge_resource_version_id=${knowledge_version}" -F "file=@$work/platform-delivery.docx" \
  "$base/knowledge/documents/upload" >"$work/upload-result.json"
cat >"$work/build-index.json" <<JSON
{"knowledge_resource_version_id":"${knowledge_version}"}
JSON
post_json /knowledge/indexes/build "$work/build-index.json" "$work/index-job.json"
job_id="$(json_value "$work/index-job.json" job_id)"
for _ in $(seq 1 90); do
  curl -fsS -c "$cookies" -b "$cookies" "$base/knowledge/ingest-jobs?knowledge_resource_version_id=${knowledge_version}" >"$work/jobs.json"
  job_status="$(python3 - "$work/jobs.json" "$job_id" <<'PY'
import json,sys
items=json.load(open(sys.argv[1],encoding="utf-8"))
print(next((x["status"] for x in items if x["job_id"]==sys.argv[2]),"UNKNOWN"))
PY
)"
  case "$job_status" in COMPLETED) break;; FAILED) cat "$work/jobs.json"; exit 1;; esac
  sleep 2
done
test "$job_status" = COMPLETED

# Retrieval acceptance before Agent publication.
cat >"$work/retrieval.json" <<JSON
{"knowledge_resource_version_id":"${knowledge_version}","query":"浏览器应该如何上传文件？","top_k":3}
JSON
post_json /knowledge/retrieval-test "$work/retrieval.json" "$work/retrieval-result.json"
grep -q 'PLATFORM-RAG-2026' "$work/retrieval-result.json"

cat >"$work/prompt-config.json" <<'JSON'
{"template":"你是企业智能体中台组装的综合 Agent。必须使用简体中文，优先遵循 Skill，按需调用已授权 Tool。Dify Flow 是你的一个 Tool，不是另一个入口。回答时区分：平台本地 RAG 证据、Dify Flow 结果、CRM MCP 结果、Native Tool 结果和用户长期记忆；不得编造未返回的数据。"}
JSON
prompt_version="$(create_resource PROMPT composite-agent-prompt "综合 Agent Prompt" "$work/prompt-config.json" prompt)"

cat >"$work/memory-config.json" <<'JSON'
{"read_enabled":true,"write_enabled":true,"write_mode":"EXPLICIT","ttl_days":90,"max_items":100,"allowed_categories":["preference","business_context"]}
JSON
memory_version="$(create_resource MEMORY_POLICY composite-agent-memory "综合 Agent Memory Policy" "$work/memory-config.json" memory)"

cat >"$work/skill-config.json" <<JSON
{"skill_md":"# 综合业务编排 Skill\n\n- 用户询问企业制度、交付口令或要求调用 Dify 时，必须调用 `dify_enterprise_knowledge_flow`。\n- 用户要求查询客户时，必须调用 `query_customer`，只读，不推断不存在的字段。\n- 用户要求算术计算时，必须调用 `calculator`。\n- 同一个问题包含多项任务时，依次调用所有需要的 Tool 后再综合回答。\n- 平台本地 Knowledge 与 Memory 会由 Runtime 注入上下文，回答时明确说明其作用。","tool_version_ids":["${dify_tool_version}","${mcp_tool_version}","${calculator_tool_version}"],"knowledge_version_ids":["${knowledge_version}"]}
JSON
skill_version="$(create_resource SKILL composite-orchestration-skill "综合业务编排 Skill" "$work/skill-config.json" skill)"

# Assemble and publish Agent V1.
cat >"$work/agent.json" <<JSON
{"slug":"composite-enterprise-agent","display_name":"企业综合智能体（Dify Flow Tool）","description":"由中台 Runtime 组合 Dify Flow、平台 RAG、CRM MCP、Skill、Native Tool 与 Memory","draft_spec":{"builder":{"id":"react","version":"1"},"assembly_schema":"v2","model_version_id":"${chat_model_version}","prompt_version_id":"${prompt_version}","skill_version_ids":["${skill_version}"],"tool_version_ids":["${dify_tool_version}","${mcp_tool_version}","${calculator_tool_version}"],"mcp_connection_version_ids":["${mcp_connection_version}"],"knowledge_version_ids":["${knowledge_version}"],"memory_policy_version_id":"${memory_version}"}}
JSON
post_json /agents "$work/agent.json" "$work/agent-result.json"
agent_id="$(json_value "$work/agent-result.json" agent_id)"
printf '{}' >"$work/empty.json"
post_json "/agents/${agent_id}/versions" "$work/empty.json" "$work/agent-version.json"
agent_version="$(json_value "$work/agent-version.json" agent_version_id)"
post_json "/agent-versions/${agent_version}/publish" "$work/empty.json" "$work/agent-published.json"

cat >"$work/deployment.json" <<JSON
{"agent_id":"${agent_id}","name":"composite-enterprise-agent-prod","description":"综合能力验收 Deployment"}
JSON
post_json /deployments "$work/deployment.json" "$work/deployment-result.json"
deployment_id="$(json_value "$work/deployment-result.json" deployment_id)"
cat >"$work/revision.json" <<JSON
{"agent_version_id":"${agent_version}","overrides":{}}
JSON
post_json "/deployments/${deployment_id}/revisions" "$work/revision.json" "$work/revision-result.json"
revision_id="$(json_value "$work/revision-result.json" deployment_revision_id)"
post_json "/deployments/${deployment_id}/revisions/${revision_id}/activate" "$work/empty.json" "$work/deployment-active.json"

# Explicit user-owned long-term memory for the same Deployment.
cat >"$work/memory-item.json" <<JSON
{"deployment_id":"${deployment_id}","category":"preference","content":"用户偏好：使用简体中文，回答简洁，并按来源分点说明。"}
JSON
post_json /memory-items "$work/memory-item.json" "$work/memory-item-result.json"

cat >"$work/run.json" <<JSON
{"deployment_id":"${deployment_id}","message":"请完成四项任务并按来源总结：1）调用 Dify 企业知识 Flow 查询标准交付口令；2）调用 CRM MCP 查询客户 CUST-001；3）用计算器计算 17*23；4）结合平台本地知识说明浏览器上传文件的规则。请结合我的长期偏好回答。"}
JSON
curl -fsS -c "$cookies" -b "$cookies" -H "X-CSRF-Token: ${csrf}" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: acceptance-$(date +%s)" --data-binary "@$work/run.json" \
  "$base/deployments/${deployment_id}/runs" >"$work/run-result.json"
run_id="$(json_value "$work/run-result.json" run_id)"
for _ in $(seq 1 90); do
  curl -fsS -c "$cookies" -b "$cookies" "$base/runs/${run_id}" >"$work/run-status.json"
  run_status="$(json_value "$work/run-status.json" status)"
  case "$run_status" in COMPLETED|FAILED|CANCELLED) break;; esac
  sleep 2
done
curl -fsS -c "$cookies" -b "$cookies" "$base/runs/${run_id}/detail" >"$work/run-detail.json"
python3 - "$work/run-detail.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
events=p.get("events",[])
outputs=[e.get("data",{}).get("content") for e in events if e.get("event")=="runtime.output"]
tools=[e.get("data",{}).get("tool") for e in events if e.get("event")=="tool.completed"]
print(json.dumps({
 "agent_id":p["manifest"]["resource_versions"].get("agent_definition_id"),
 "deployment_id":p["run"]["deployment_id"],
 "run_id":p["run"]["run_id"],
 "status":p["run"]["status"],
 "manifest_hash":p["manifest"]["manifest_hash"],
 "resource_types":sorted({r["type"] for r in p["manifest"].get("resources",[])}),
 "secret_refs":p["manifest"].get("secret_refs",{}),
 "tools_completed":tools,
 "dify_rag_events":sum(e.get("event")=="dify.rag.retrieved" for e in events),
 "platform_rag_events":sum(e.get("event")=="rag.retrieved" for e in events),
 "memory_read_events":sum(e.get("event")=="memory.read" for e in events),
 "output":outputs[-1] if outputs else None,
},ensure_ascii=False))
PY
test "$run_status" = COMPLETED
