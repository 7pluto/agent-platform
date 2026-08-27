<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

interface Principal { external_user_id: string; display_name: string; dept_ids: string[] }
interface ModelOption { model_id: string; model_version_id: string; display_name: string; version_number: number; provider: string; model_name: string }
interface DiscoveredTool { name: string; description?: string; input_schema: Record<string, unknown>; managed: boolean }

type Kind = 'MCP' | 'HTTP' | 'DIFY' | 'KNOWLEDGE'
const props = defineProps<{ principal: Principal; csrfToken: string }>()
const emit = defineEmits<{ close: []; installed: [] }>()
const kind = ref<Kind>('MCP')
const saving = ref(false)
const error = ref('')
const notice = ref('')
const models = ref<ModelOption[]>([])
const discovered = ref<DiscoveredTool[]>([])
const selectedMcpTools = ref<string[]>([])

const common = ref({ displayName: '', slug: '', description: '', summary: '', whenUse: '', whenNotUse: '', inputSummary: '', outputSummary: '', tags: '' })
const mcp = ref({ endpoint: 'http://demo-crm-mcp:8090/mcp', apiKey: '', timeout: 10, connectionVersionId: '' })
const http = ref({ endpoint: 'http://demo-enterprise-services:8091', path: '/customers/{{customer_id}}', method: 'GET', toolName: 'query_customer_http', inputSchema: '{\n  "type": "object",\n  "properties": {\n    "customer_id": { "type": "string" }\n  },\n  "required": ["customer_id"]\n}', queryTemplate: '{}', bodyTemplate: '', testArguments: '{\n  "customer_id": "C1001"\n}', apiKey: '' })
const dify = ref({ baseUrl: '', apiKey: '', flowType: 'CHATFLOW', toolName: 'dify_business_flow', testQuery: '请回复 OK' })
const knowledge = ref({ embeddingModelVersionId: '', files: [] as File[] })

const tabs = [
  { key: 'MCP' as const, title: 'MCP Server', copy: '发现 Server 提供的工具，再挑选能力纳管成 Tool Resource。' },
  { key: 'HTTP' as const, title: 'HTTP API', copy: '把固定业务 REST API 包装成受控 Tool，不让模型自行拼 URL。' },
  { key: 'DIFY' as const, title: 'Dify', copy: '把已有 Chatflow / Workflow 接成标准 Tool Resource。' },
  { key: 'KNOWLEDGE' as const, title: 'Knowledge', copy: '上传 PDF / DOCX，建立本地检索索引并发布 Knowledge Resource。' },
]
const defaults: Record<Kind, { name: string; slug: string; summary: string }> = {
  MCP: { name: '业务 MCP', slug: 'business-mcp', summary: '通过 MCP 发现并调用业务系统能力' },
  HTTP: { name: '业务 HTTP Tool', slug: 'business-http-tool', summary: '调用固定企业 HTTP API' },
  DIFY: { name: 'Dify 业务流', slug: 'dify-business-flow', summary: '调用已有 Dify 应用完成业务任务' },
  KNOWLEDGE: { name: '企业知识库', slug: 'enterprise-knowledge', summary: '检索上传的企业文档内容' },
}
const title = computed(() => tabs.find(item => item.key === kind.value)?.title || kind.value)

function slugify(value: string) { const s = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63); return s.length >= 3 ? s : `resource-${Date.now().toString(36)}` }
function toolInputKeys(tool: DiscoveredTool) { const props = tool.input_schema && typeof tool.input_schema.properties === 'object' && tool.input_schema.properties ? tool.input_schema.properties as Record<string, unknown> : {}; return Object.keys(props).join(', ') || 'no args' }
function tags() { return common.value.tags.split(',').map(item => item.trim()).filter(Boolean) }
function semantics() { return { one_line_summary: common.value.summary.trim() || common.value.description.trim() || common.value.displayName.trim(), when_to_use: common.value.whenUse.trim() || '当 Agent 需要调用该业务能力时使用。', ...(common.value.whenNotUse.trim() ? { when_not_to_use: common.value.whenNotUse.trim() } : {}), input_summary: common.value.inputSummary.trim() || '按能力输入契约提供参数。', output_summary: common.value.outputSummary.trim() || '返回业务系统提供的结构化结果。', risk_level: 'LOW', read_only: true, tags: tags(), publication_scope: 'PERSONAL', publication_subjects: [] } }
function baseIdentity() { const display = common.value.displayName.trim() || `${title.value} 能力`; return { display_name: display, slug: common.value.slug.trim() || slugify(display), description: common.value.description.trim() || semantics().one_line_summary } }
function resetProductInfo(value: Kind) { const item = defaults[value]; common.value = { displayName: item.name, slug: item.slug, description: '', summary: item.summary, whenUse: '', whenNotUse: '', inputSummary: '', outputSummary: '', tags: '' } }
function selectKind(value: Kind) { kind.value = value; error.value = ''; notice.value = ''; discovered.value = []; selectedMcpTools.value = []; mcp.value.connectionVersionId = ''; resetProductInfo(value) }
function parseObject(value: string, field: string, allowEmpty = true) { if (!value.trim() && allowEmpty) return undefined; try { const parsed = JSON.parse(value); if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error(); return parsed as Record<string, unknown> } catch { throw new Error(`${field} 必须是 JSON Object。`) } }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> { const headers = new Headers(init.headers || {}); if (init.method && init.method !== 'GET') headers.set('X-CSRF-Token', props.csrfToken); if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json'); const response = await fetch(path, { credentials: 'same-origin', ...init, headers }); const payload = await response.json().catch(() => ({})) as Record<string, unknown>; if (!response.ok) throw new Error(String(payload.message || payload.detail || payload.code || `HTTP ${response.status}`)); return payload as T }
async function loadModels() { try { models.value = await request<ModelOption[]>('/api/v1/developer/external/models') } catch { models.value = [] } }

async function connectMcp() {
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const payload = await request<{ resource_version_id: string }>('/api/v1/developer/external/mcp/connections', { method: 'POST', body: JSON.stringify({ ...baseIdentity(), ...semantics(), endpoint: mcp.value.endpoint.trim(), timeout_seconds: mcp.value.timeout, ...(mcp.value.apiKey.trim() ? { api_key: mcp.value.apiKey.trim() } : {}) }) })
    mcp.value.connectionVersionId = payload.resource_version_id
    discovered.value = await request<DiscoveredTool[]>(`/api/v1/developer/external/mcp/connections/${payload.resource_version_id}/discover`, { method: 'POST' })
    selectedMcpTools.value = discovered.value.filter(item => !item.managed).map(item => item.name)
    notice.value = `连接成功，发现 ${discovered.value.length} 个 Tool。请选择要纳管的能力。`
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { saving.value = false }
}
async function registerMcpTools() {
  if (!mcp.value.connectionVersionId || !selectedMcpTools.value.length) return
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const items = discovered.value.filter(item => selectedMcpTools.value.includes(item.name))
    await request('/api/v1/developer/external/mcp/tools', { method: 'POST', body: JSON.stringify({ connection_version_id: mcp.value.connectionVersionId, tools: items.map(item => ({ tool_name: item.name, slug: slugify(`mcp-${item.name}`), display_name: item.name.replace(/_/g, ' '), description: item.description || `MCP Tool ${item.name}`, one_line_summary: item.description || `调用 MCP Tool ${item.name}`, when_to_use: common.value.whenUse.trim() || `需要 ${item.description || item.name} 时使用。`, when_not_to_use: common.value.whenNotUse.trim() || '与该业务动作无关时不要使用。', input_summary: `按 MCP input schema 提供参数：${toolInputKeys(item)}`, output_summary: common.value.outputSummary.trim() || '返回 MCP Server 的结构化结果。', risk_level: 'LOW', read_only: true, tags: tags() })) }) })
    notice.value = `已纳管 ${items.length} 个 MCP Tool，可在“可用资源”和 Playground 中直接使用。`; emit('installed')
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { saving.value = false }
}
async function createHttp() {
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const inputSchema = parseObject(http.value.inputSchema, 'Input Schema', false)!
    const queryTemplate = parseObject(http.value.queryTemplate, 'Query Template')
    const bodyTemplate = parseObject(http.value.bodyTemplate, 'Body Template')
    const testArguments = parseObject(http.value.testArguments, 'Test Arguments') || {}
    await request('/api/v1/developer/external/http-tools', { method: 'POST', body: JSON.stringify({ ...baseIdentity(), ...semantics(), tool_name: http.value.toolName.trim(), endpoint: http.value.endpoint.trim(), path: http.value.path.trim(), method: http.value.method, input_schema: inputSchema, ...(queryTemplate ? { query_template: queryTemplate } : {}), ...(bodyTemplate ? { body_template: bodyTemplate } : {}), test_arguments: testArguments, ...(http.value.apiKey.trim() ? { api_key: http.value.apiKey.trim() } : {}) }) })
    notice.value = 'HTTP Tool 已完成真实测试并发布，可立即进入 Playground。'; emit('installed')
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { saving.value = false }
}
async function createDify() {
  saving.value = true; error.value = ''; notice.value = ''
  try { await request('/api/v1/developer/external/dify', { method: 'POST', body: JSON.stringify({ ...baseIdentity(), ...semantics(), flow_type: dify.value.flowType, base_url: dify.value.baseUrl.trim(), api_key: dify.value.apiKey.trim(), tool_name: dify.value.toolName.trim(), test_query: dify.value.testQuery.trim() || '请回复 OK' }) }); notice.value = 'Dify 应用连接测试成功并已纳管为 Tool Resource。'; emit('installed') }
  catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { saving.value = false }
}
function onFiles(event: Event) { knowledge.value.files = Array.from((event.target as HTMLInputElement).files || []) }
async function createKnowledge() {
  if (!knowledge.value.embeddingModelVersionId) { error.value = '请选择可用的 Embedding Model。'; return }
  if (!knowledge.value.files.length) { error.value = '请至少选择一个 PDF 或 DOCX 文件。'; return }
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const created = await request<{ resource_version: { resource_version_id: string } }>('/api/v1/developer/external/knowledge/local', { method: 'POST', body: JSON.stringify({ ...baseIdentity(), ...semantics(), embedding_model_version_id: knowledge.value.embeddingModelVersionId }) })
    const versionId = created.resource_version.resource_version_id
    for (const file of knowledge.value.files) { const data = new FormData(); data.append('file', file); await request(`/api/v1/developer/external/knowledge/${versionId}/documents`, { method: 'POST', body: data }) }
    const job = await request<{ job_id: string; status: string }>(`/api/v1/developer/external/knowledge/${versionId}/build`, { method: 'POST' })
    notice.value = `Knowledge 已发布并上传 ${knowledge.value.files.length} 个文件，索引任务 ${job.job_id.slice(0, 8)}… 已进入 ${job.status}。`; emit('installed')
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { saving.value = false }
}

onMounted(() => { void loadModels(); resetProductInfo('MCP') })
</script>

<template>
  <div class="overlay"><main class="panel">
    <header class="panel-head"><div><span>DEVELOPER CAPABILITY ONBOARDING</span><h1>接入外部能力</h1><p>外部系统只是来源；接入完成后统一沉淀成可版本化、可授权、可测试的 Tool / Knowledge Resource。</p></div><button class="close" @click="emit('close')">×</button></header>
    <section class="kind-grid"><button v-for="tab in tabs" :key="tab.key" :class="{active:kind===tab.key}" @click="selectKind(tab.key)"><b>{{tab.title}}</b><span>{{tab.copy}}</span></button></section>
    <p v-if="error" class="message error">{{error}}</p><p v-if="notice" class="message success">{{notice}}</p>
    <section class="workspace"><aside><p>RESOURCE PRODUCT INFO</p><h3>{{title}}</h3><label>资源名称<input v-model="common.displayName"/></label><label>Slug<input v-model="common.slug"/></label><label>一句话能力<textarea v-model="common.summary" rows="2"/></label><label>何时使用<textarea v-model="common.whenUse" rows="3"/></label><label>何时不要使用<textarea v-model="common.whenNotUse" rows="2"/></label><label>输入说明<textarea v-model="common.inputSummary" rows="2"/></label><label>输出说明<textarea v-model="common.outputSummary" rows="2"/></label><label>标签<input v-model="common.tags" placeholder="CRM, 查询, 只读"/></label></aside>
      <div class="technical">
        <template v-if="kind==='MCP'">
          <div class="section-title"><span>01</span><div><b>连接 MCP Server</b><small>仅支持 Streamable HTTP；连接后先真实执行 tools/list。</small></div></div>
          <div class="form-grid"><label class="wide">Endpoint<input v-model="mcp.endpoint" placeholder="https://mcp.company.com/mcp"/></label><label>Timeout (s)<input v-model.number="mcp.timeout" type="number"/></label><label>API Key（可选）<input v-model="mcp.apiKey" type="password"/></label></div><button class="primary" :disabled="saving" @click="connectMcp">{{saving?'正在连接…':'连接并发现 Tool'}}</button>
          <template v-if="discovered.length"><div class="section-title second"><span>02</span><div><b>选择要纳管的 Tool</b><small>Schema 来自 Server discovery，浏览器不能伪造。</small></div></div><div class="tool-list"><label v-for="tool in discovered" :key="tool.name" :class="{disabled:tool.managed}"><input v-model="selectedMcpTools" type="checkbox" :value="tool.name" :disabled="tool.managed"/><span><b>{{tool.name}}</b><small>{{tool.description||'无描述'}}</small><code>{{toolInputKeys(tool)}}</code></span><em>{{tool.managed?'已纳管':'可纳管'}}</em></label></div><button class="primary dark" :disabled="saving||!selectedMcpTools.length" @click="registerMcpTools">纳管 {{selectedMcpTools.length}} 个 Tool</button></template>
        </template>
        <template v-else-if="kind==='HTTP'">
          <div class="section-title"><span>01</span><div><b>定义固定 HTTP 能力</b><small>模型只能填写 Schema 参数，不能改变 Endpoint、Method 或认证。</small></div></div><div class="form-grid"><label>Endpoint<input v-model="http.endpoint"/></label><label>Path<input v-model="http.path"/></label><label>Method<select v-model="http.method"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option></select></label><label>Tool Name<input v-model="http.toolName"/></label><label class="wide code">Input Schema<textarea v-model="http.inputSchema" rows="9"/></label><label class="wide code">Query Template<textarea v-model="http.queryTemplate" rows="4"/></label><label class="wide code">Body Template（可空）<textarea v-model="http.bodyTemplate" rows="5"/></label><label class="wide code">Test Arguments<textarea v-model="http.testArguments" rows="5"/></label><label class="wide">API Key（可选）<input v-model="http.apiKey" type="password"/></label></div><button class="primary dark" :disabled="saving" @click="createHttp">{{saving?'正在测试…':'测试并发布 HTTP Tool'}}</button>
        </template>
        <template v-else-if="kind==='DIFY'">
          <div class="section-title"><span>01</span><div><b>接入 Dify App</b><small>平台会先读取应用参数并做连接测试，再生成标准 Tool Resource。</small></div></div><div class="form-grid"><label class="wide">Base URL<input v-model="dify.baseUrl" placeholder="https://api.dify.ai/v1"/></label><label>Flow Type<select v-model="dify.flowType"><option value="CHATFLOW">CHATFLOW</option><option value="WORKFLOW">WORKFLOW</option></select></label><label>Tool Name<input v-model="dify.toolName"/></label><label class="wide">API Key<input v-model="dify.apiKey" type="password"/></label><label class="wide">测试问题<input v-model="dify.testQuery"/></label></div><button class="primary dark" :disabled="saving||!dify.apiKey" @click="createDify">{{saving?'正在检查…':'连接并发布 Dify Tool'}}</button>
        </template>
        <template v-else>
          <div class="section-title"><span>01</span><div><b>创建本地 Knowledge</b><small>选择已授权的 Embedding Model，上传 PDF / DOCX 后自动进入索引任务。</small></div></div><div v-if="!models.length" class="warning">当前账号没有可用 Model。请先让管理员发布并授权一个可用于 Embedding 的 Model Version。</div><div class="form-grid"><label class="wide">Embedding Model<select v-model="knowledge.embeddingModelVersionId"><option value="">请选择</option><option v-for="model in models" :key="model.model_version_id" :value="model.model_version_id">{{model.display_name}} · V{{model.version_number}} · {{model.model_name}}</option></select></label><label class="wide file">知识文件<input type="file" multiple accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="onFiles"/><span>{{knowledge.files.length?`已选择 ${knowledge.files.length} 个文件`:'当前知识处理链仅支持 PDF / DOCX'}}</span></label></div><button class="primary dark" :disabled="saving||!models.length" @click="createKnowledge">{{saving?'正在创建与上传…':'创建 Knowledge 并建立索引'}}</button>
        </template>
      </div>
    </section>
  </main></div>
</template>

<style scoped>
*{box-sizing:border-box}.overlay{position:fixed;inset:0;z-index:200;background:#f6f7fb;overflow:auto;color:#101828;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.panel{max-width:1420px;margin:auto;padding:24px 30px 50px}.panel-head{display:flex;justify-content:space-between;gap:30px;align-items:flex-start;padding:18px 0 22px}.panel-head span{color:#6941c6;font-size:11px;font-weight:900;letter-spacing:.12em}.panel-head h1{margin:4px 0 6px;font-size:30px}.panel-head p{margin:0;color:#667085}.close{border:1px solid #d0d5dd;background:#fff;border-radius:12px;width:42px;height:42px;font-size:24px;cursor:pointer}.kind-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.kind-grid button{min-height:96px;padding:16px;border:1px solid #e4e7ec;border-radius:14px;background:#fff;text-align:left;display:grid;gap:6px;cursor:pointer}.kind-grid button.active{border-color:#7f56d9;background:#f9f5ff;box-shadow:0 0 0 1px #7f56d9}.kind-grid span{color:#667085;font-size:12px;line-height:1.45}.message{margin:14px 0 0;padding:10px 13px;border-radius:10px}.message.error{background:#fef3f2;color:#b42318}.message.success{background:#ecfdf3;color:#067647}.workspace{display:grid;grid-template-columns:330px minmax(0,1fr);gap:16px;margin-top:16px;align-items:start}.workspace>aside,.technical{border:1px solid #e4e7ec;border-radius:16px;background:#fff;padding:19px}.workspace aside{position:sticky;top:16px;display:grid;gap:11px}.workspace aside>p{margin:0;color:#7f56d9;font-size:10px;font-weight:900}.workspace aside h3{margin:0 0 4px}.workspace label,.technical label{display:grid;gap:6px;color:#344054;font-size:12px;font-weight:700}.workspace input,.workspace textarea,.workspace select{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:9px 10px;font:inherit;color:#101828;background:#fff}.workspace textarea{resize:vertical}.section-title{display:flex;gap:10px;align-items:flex-start;margin-bottom:16px}.section-title.second{margin-top:24px}.section-title>span{width:30px;height:30px;border-radius:8px;display:grid;place-items:center;background:#eeebff;color:#5925dc;font-weight:900;font-size:11px}.section-title div{display:grid;gap:2px}.section-title small{color:#667085}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:15px}.form-grid .wide{grid-column:1/-1}.code textarea{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.primary{border:0;border-radius:10px;padding:11px 15px;background:#6941c6;color:#fff;font-weight:800;cursor:pointer}.primary.dark{background:#111827}.primary:disabled{opacity:.5;cursor:default}.tool-list{display:grid;gap:8px;margin-bottom:15px}.tool-list label{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:start;padding:11px;border:1px solid #eaecf0;border-radius:10px;cursor:pointer}.tool-list label.disabled{opacity:.55}.tool-list input{width:auto;margin-top:3px}.tool-list span{display:grid;gap:2px}.tool-list small{color:#667085}.tool-list code{margin-top:4px;color:#475467;font-size:10px}.tool-list em{font-style:normal;color:#067647;font-size:10px}.warning{padding:12px;border-radius:10px;background:#fffaeb;color:#b54708;margin-bottom:14px}.file{padding:16px;border:1px dashed #98a2b3;border-radius:10px}.file span{color:#667085;font-weight:400}@media(max-width:900px){.kind-grid{grid-template-columns:repeat(2,1fr)}.workspace{grid-template-columns:1fr}.workspace>aside{position:static}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}}@media(max-width:560px){.panel{padding:14px}.kind-grid{grid-template-columns:1fr}.panel-head h1{font-size:25px}}
</style>