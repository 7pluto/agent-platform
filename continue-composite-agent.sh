#!/usr/bin/env bash
set -euo pipefail
base="http://127.0.0.1:8000/api/v1"
cookies="$(mktemp)" work="$(mktemp -d)"
trap 'rm -rf "$work" "$cookies"' EXIT
chmod 700 "$work"; chmod 600 "$cookies"

json_value(){ python3 - "$1" "$2" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding="utf-8"))
for p in sys.argv[2].split('.'): v=v[p]
print(v)
PY
}
curl -fsS -c "$cookies" -b "$cookies" -H 'Content-Type: application/json' -d '{"ticket_code":"dev-ticket"}' "$base/auth/exchange" >"$work/login.json"
csrf="$(json_value "$work/login.json" csrf_token)"
post_json(){ curl -fsS -c "$cookies" -b "$cookies" -H "X-CSRF-Token: ${csrf}" -H 'Content-Type: application/json' --data-binary "@$2" "$base$1" >"$3"; }

curl -fsS -c "$cookies" -b "$cookies" "$base/resources" >"$work/resources.json"
resource_id(){ python3 - "$work/resources.json" "$1" <<'PY'
import json,sys
print(next(x["resource_id"] for x in json.load(open(sys.argv[1],encoding="utf-8")) if x["slug"]==sys.argv[2]))
PY
}
version_id(){ curl -fsS -c "$cookies" -b "$cookies" "$base/resources/$1/versions" >"$work/versions.json"; python3 - "$work/versions.json" <<'PY'
import json,sys
items=json.load(open(sys.argv[1],encoding="utf-8")); print(next(x["resource_version_id"] for x in reversed(items) if x["status"]=="PUBLISHED"))
PY
}
create_resource(){ local type="$1" slug="$2" name="$3" config="$4" prefix="$5"; python3 - "$type" "$slug" "$name" "$config" "$work/$prefix-def-req.json" <<'PY'
import json,sys
json.dump({"resource_type":sys.argv[1],"slug":sys.argv[2],"display_name":sys.argv[3],"draft_config":json.load(open(sys.argv[4],encoding="utf-8"))},open(sys.argv[5],"w",encoding="utf-8"),ensure_ascii=False)
PY
post_json /resources "$work/$prefix-def-req.json" "$work/$prefix-def.json"; rid="$(json_value "$work/$prefix-def.json" resource_id)"; python3 - "$config" "$work/$prefix-ver-req.json" <<'PY'
import json,sys
json.dump({"config":json.load(open(sys.argv[1],encoding="utf-8"))},open(sys.argv[2],"w",encoding="utf-8"),ensure_ascii=False)
PY
post_json "/resources/$rid/versions" "$work/$prefix-ver-req.json" "$work/$prefix-ver.json"; vid="$(json_value "$work/$prefix-ver.json" resource_version_id)"; echo '{}' >"$work/empty.json"; post_json "/resource-versions/$vid/publish" "$work/empty.json" "$work/$prefix-pub.json"; printf %s "$vid"; }

knowledge_version="$(version_id "$(resource_id platform-delivery-knowledge)")"
calculator_tool_version="$(version_id "$(resource_id calculator-tool)")"
mcp_connection_version="$(version_id "$(resource_id demo-crm-connection)")"
mcp_tool_version="$(version_id "$(resource_id query-customer)")"
dify_tool_version="b72f2cc6-ccfb-4c50-955c-760e3ec175db"
chat_model_version="c0f13386-9fa7-4445-bb15-bed64476eb0d"

# Formal queued build and retrieval acceptance.
echo "{\"knowledge_resource_version_id\":\"$knowledge_version\"}" >"$work/build.json"
post_json /knowledge/indexes/build "$work/build.json" "$work/job.json"; job="$(json_value "$work/job.json" job_id)"
for _ in $(seq 1 90); do curl -fsS -c "$cookies" -b "$cookies" "$base/knowledge/ingest-jobs?knowledge_resource_version_id=$knowledge_version" >"$work/jobs.json"; status="$(python3 - "$work/jobs.json" "$job" <<'PY'
import json,sys
print(next((x["status"] for x in json.load(open(sys.argv[1])) if x["job_id"]==sys.argv[2]),"UNKNOWN"))
PY
)"; case "$status" in COMPLETED) break;; FAILED) cat "$work/jobs.json"; exit 1;; esac; sleep 2; done; test "$status" = COMPLETED
echo "{\"knowledge_resource_version_id\":\"$knowledge_version\",\"query\":\"浏览器应该如何上传文件？\",\"top_k\":3}" >"$work/retrieve.json"
post_json /knowledge/retrieval-test "$work/retrieve.json" "$work/hits.json"; grep -q PLATFORM-RAG-2026 "$work/hits.json"

cat >"$work/prompt.json" <<'JSON'
{"template":"你是企业智能体中台组装的综合 Agent。必须使用简体中文，优先遵循 Skill，按需调用已授权 Tool。Dify Flow 是你的一个 Tool，不是另一个入口。回答时区分平台本地 RAG、Dify Flow、CRM MCP、Native Tool和长期记忆，不得编造。"}
JSON
prompt_version="$(create_resource PROMPT composite-agent-prompt "综合 Agent Prompt" "$work/prompt.json" prompt)"
cat >"$work/memory.json" <<'JSON'
{"read_enabled":true,"write_enabled":true,"write_mode":"EXPLICIT","ttl_days":90,"max_items":100,"allowed_categories":["preference","business_context"]}
JSON
memory_version="$(create_resource MEMORY_POLICY composite-agent-memory "综合 Agent Memory Policy" "$work/memory.json" memory)"
cat >"$work/skill.json" <<JSON
{"skill_md":"# 综合业务编排 Skill\n- 查询企业交付口令时必须调用 dify_enterprise_knowledge_flow。\n- 查询客户时必须调用 query_customer。\n- 算术必须调用 calculator。\n- 多任务必须调用所有所需 Tool 后综合回答。\n- 明确区分平台 RAG、Dify Flow、MCP、Native Tool 和 Memory。","tool_version_ids":["$dify_tool_version","$mcp_tool_version","$calculator_tool_version"],"knowledge_version_ids":["$knowledge_version"]}
JSON
skill_version="$(create_resource SKILL composite-orchestration-skill "综合业务编排 Skill" "$work/skill.json" skill)"

cat >"$work/agent.json" <<JSON
{"slug":"composite-enterprise-agent","display_name":"企业综合智能体（Dify Flow Tool）","description":"中台组合 Dify Flow、平台 RAG、CRM MCP、Skill、Native Tool 与 Memory","draft_spec":{"builder":{"id":"react","version":"1"},"assembly_schema":"v2","model_version_id":"$chat_model_version","prompt_version_id":"$prompt_version","skill_version_ids":["$skill_version"],"tool_version_ids":["$dify_tool_version","$mcp_tool_version","$calculator_tool_version"],"mcp_connection_version_ids":["$mcp_connection_version"],"knowledge_version_ids":["$knowledge_version"],"memory_policy_version_id":"$memory_version"}}
JSON
post_json /agents "$work/agent.json" "$work/agent-out.json"; agent="$(json_value "$work/agent-out.json" agent_id)"; echo '{}' >"$work/empty.json"
post_json "/agents/$agent/versions" "$work/empty.json" "$work/agent-ver.json"; agent_ver="$(json_value "$work/agent-ver.json" agent_version_id)"; post_json "/agent-versions/$agent_ver/publish" "$work/empty.json" "$work/agent-pub.json"
echo "{\"agent_id\":\"$agent\",\"name\":\"composite-enterprise-agent-prod\",\"description\":\"综合能力验收 Deployment\"}" >"$work/deploy.json"; post_json /deployments "$work/deploy.json" "$work/deploy-out.json"; deployment="$(json_value "$work/deploy-out.json" deployment_id)"
echo "{\"agent_version_id\":\"$agent_ver\",\"overrides\":{}}" >"$work/rev.json"; post_json "/deployments/$deployment/revisions" "$work/rev.json" "$work/rev-out.json"; revision="$(json_value "$work/rev-out.json" deployment_revision_id)"; post_json "/deployments/$deployment/revisions/$revision/activate" "$work/empty.json" "$work/active.json"

echo "{\"deployment_id\":\"$deployment\",\"category\":\"preference\",\"content\":\"用户偏好：简体中文、简洁、按来源分点说明。\"}" >"$work/memitem.json"; post_json /memory-items "$work/memitem.json" "$work/memitem-out.json"
echo "{\"deployment_id\":\"$deployment\",\"message\":\"完成四项任务并按来源总结：调用 Dify Flow 查询标准交付口令；调用 CRM MCP 查询客户 CUST-001；用计算器计算17*23；结合平台本地知识说明浏览器上传规则。结合我的长期偏好回答。\"}" >"$work/run.json"
curl -fsS -c "$cookies" -b "$cookies" -H "X-CSRF-Token: $csrf" -H 'Content-Type: application/json' -H "Idempotency-Key: acceptance-$(date +%s)" --data-binary "@$work/run.json" "$base/deployments/$deployment/runs" >"$work/run-out.json"; run="$(json_value "$work/run-out.json" run_id)"
for _ in $(seq 1 120); do curl -fsS -c "$cookies" -b "$cookies" "$base/runs/$run" >"$work/run-status.json"; run_status="$(json_value "$work/run-status.json" status)"; case "$run_status" in COMPLETED|FAILED|CANCELLED) break;; esac; sleep 2; done
curl -fsS -c "$cookies" -b "$cookies" "$base/runs/$run/detail" >"$work/detail.json"
python3 - "$work/detail.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8")); events=p["events"]
print(json.dumps({"agent_id":p["manifest"]["resource_versions"].get("agent_definition_id"),"deployment_id":p["run"]["deployment_id"],"run_id":p["run"]["run_id"],"status":p["run"]["status"],"manifest_hash":p["manifest"]["manifest_hash"],"resource_types":sorted({x["type"] for x in p["manifest"]["resources"]}),"secret_refs":p["manifest"]["secret_refs"],"tools_completed":[e["data"].get("tool") for e in events if e["event"]=="tool.completed"],"dify_rag_events":sum(e["event"]=="dify.rag.retrieved" for e in events),"platform_rag_events":sum(e["event"]=="rag.retrieved" for e in events),"memory_read_events":sum(e["event"]=="memory.read" for e in events),"output":next((e["data"].get("content") for e in reversed(events) if e["event"]=="runtime.output"),None)},ensure_ascii=False))
PY
test "$run_status" = COMPLETED
