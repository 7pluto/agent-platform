<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

interface CatalogItem {
  version_id: string; resource_id: string; resource_type: string; display_name: string; version_number: number; source_type: string;
  one_line_summary?: string; when_to_use?: string; input_summary?: string; output_summary?: string; risk_level: string; read_only: boolean; tags: string[]
}
interface ModelOption { model_version_id: string; display_name: string; version_number: number; model_name: string }
interface PlaygroundResult { resource_version_id: string; resource_type: string; kind: string; mode: string; elapsed_ms: number; output: unknown; tool_calls: Array<{name:string;arguments:Record<string,unknown>;output:unknown}>; metadata: Record<string,unknown> }
const props = defineProps<{ csrfToken: string }>()
const emit = defineEmits<{ close: [] }>()
const resources = ref<CatalogItem[]>([])
const models = ref<ModelOption[]>([])
const selected = ref<CatalogItem | null>(null)
const typeFilter = ref('ALL')
const query = ref('')
const argumentsText = ref('{}')
const message = ref('')
const modelVersionId = ref('')
const topK = ref(3)
const running = ref(false)
const error = ref('')
const result = ref<PlaygroundResult | null>(null)

const playable = computed(() => resources.value.filter(item => ['PROMPT','SKILL','TOOL','KNOWLEDGE'].includes(item.resource_type)))
const visible = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return playable.value.filter(item => (typeFilter.value === 'ALL' || item.resource_type === typeFilter.value) && (!needle || `${item.display_name} ${item.one_line_summary||''} ${item.when_to_use||''}`.toLowerCase().includes(needle)))
})
const needsModel = computed(() => selected.value && ['PROMPT','SKILL'].includes(selected.value.resource_type))
const needsMessage = computed(() => selected.value && ['PROMPT','SKILL','KNOWLEDGE'].includes(selected.value.resource_type))
function typeLabel(value: string) { return ({PROMPT:'Prompt',SKILL:'Skill',TOOL:'Tool',KNOWLEDGE:'Knowledge'} as Record<string,string>)[value] || value }
function sourceLabel(value: string) { return ({PLATFORM_NATIVE:'Native',MCP:'MCP',HTTP:'HTTP',DIFY:'Dify',LOCAL_FILE:'Local',RAGFLOW:'RAGFlow'} as Record<string,string>)[value] || value }
function pretty(value: unknown) { try { return JSON.stringify(value, null, 2) } catch { return String(value) } }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  if (init.method && init.method !== 'GET') headers.set('X-CSRF-Token', props.csrfToken)
  if (init.body) headers.set('Content-Type','application/json')
  const response = await fetch(path,{credentials:'same-origin',...init,headers})
  const payload = await response.json().catch(() => ({})) as Record<string,unknown>
  if (!response.ok) throw new Error(String(payload.message || payload.detail || payload.code || `HTTP ${response.status}`))
  return payload as T
}
async function load() {
  error.value = ''
  try {
    const [items, modelItems] = await Promise.all([
      request<CatalogItem[]>('/api/v1/developer/resources/available'),
      request<ModelOption[]>('/api/v1/developer/external/models/chat'),
    ])
    resources.value = items; models.value = modelItems
    if (!selected.value && playable.value.length) choose(playable.value[0])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
}
function choose(item: CatalogItem) {
  selected.value = item; result.value = null; error.value = ''; argumentsText.value = '{}'; message.value = ''; topK.value = 3
  if (['PROMPT','SKILL'].includes(item.resource_type) && !modelVersionId.value && models.value.length) modelVersionId.value = models.value[0].model_version_id
}
function parseArguments() {
  if (!argumentsText.value.trim()) return {}
  try { const value = JSON.parse(argumentsText.value); if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(); return value as Record<string,unknown> }
  catch { throw new Error('Arguments 必须是 JSON Object。') }
}
async function run() {
  if (!selected.value) return
  running.value = true; error.value = ''; result.value = null
  try {
    const body: Record<string,unknown> = { arguments: parseArguments(), message: message.value, top_k: topK.value }
    if (needsModel.value && modelVersionId.value) body.model_version_id = modelVersionId.value
    result.value = await request<PlaygroundResult>(`/api/v1/developer/playground/${selected.value.version_id}/run`, {method:'POST',body:JSON.stringify(body)})
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { running.value = false }
}
onMounted(load)
</script>

<template>
  <div class="overlay">
    <main class="shell">
      <header><div><span>RESOURCE PLAYGROUND</span><h1>资源独立测试</h1><p>先把单个能力跑通，再交给 Agent Builder。测试调用与正式 Runtime 复用同一执行客户端。</p></div><button class="close" @click="emit('close')">×</button></header>
      <p v-if="error" class="error">{{error}}</p>
      <section class="layout">
        <aside class="catalog">
          <div class="filters"><input v-model="query" placeholder="搜索资源"/><select v-model="typeFilter"><option value="ALL">全部</option><option value="PROMPT">Prompt</option><option value="SKILL">Skill</option><option value="TOOL">Tool</option><option value="KNOWLEDGE">Knowledge</option></select></div>
          <button v-for="item in visible" :key="item.version_id" :class="['resource',{active:selected?.version_id===item.version_id}]" @click="choose(item)"><div><span>{{typeLabel(item.resource_type)}}</span><em>{{sourceLabel(item.source_type)}} · V{{item.version_number}}</em></div><b>{{item.display_name}}</b><p>{{item.one_line_summary||item.input_summary||'尚无业务说明'}}</p></button><p v-if="!visible.length" class="empty">没有可测试资源。</p>
        </aside>
        <section v-if="selected" class="runner">
          <div class="resource-head"><div><span>{{typeLabel(selected.resource_type)}} · {{sourceLabel(selected.source_type)}} · V{{selected.version_number}}</span><h2>{{selected.display_name}}</h2><p>{{selected.one_line_summary}}</p></div><div class="badges"><i>{{selected.risk_level}}</i><i>{{selected.read_only?'READ ONLY':'WRITE'}}</i></div></div>
          <div class="contract"><article><small>何时使用</small><p>{{selected.when_to_use||'未填写'}}</p></article><article><small>输入契约</small><p>{{selected.input_summary||'按资源定义提供输入。'}}</p></article><article><small>输出契约</small><p>{{selected.output_summary||'返回资源定义的结果。'}}</p></article></div>
          <section class="test-form"><div class="section-title"><span>01</span><div><b>测试输入</b><small v-if="selected.resource_type==='TOOL'">直接执行 Tool；MCP / HTTP / Dify 都会触发真实上游调用。</small><small v-else-if="selected.resource_type==='KNOWLEDGE'">直接执行检索，不经过 Agent。</small><small v-else>选择 Chat Model 后真实执行；不选 Model 时返回 Prompt / Skill Preview。</small></div></div>
            <label v-if="needsMessage">{{selected.resource_type==='KNOWLEDGE'?'检索问题':'测试问题'}}<textarea v-model="message" rows="5" :placeholder="selected.resource_type==='KNOWLEDGE'?'例如：公司的报销流程是什么？':'输入一个真实业务问题'"/></label>
            <label v-if="selected.resource_type==='TOOL'" class="code">Arguments JSON<textarea v-model="argumentsText" rows="10" placeholder="{}"/></label>
            <label v-if="selected.resource_type==='KNOWLEDGE'">Top K<input v-model.number="topK" type="number" min="1" max="10"/></label>
            <label v-if="needsModel">测试 Chat Model<select v-model="modelVersionId"><option value="">不调用模型，只预览</option><option v-for="model in models" :key="model.model_version_id" :value="model.model_version_id">{{model.display_name}} · V{{model.version_number}} · {{model.model_name}}</option></select><small v-if="!models.length">当前账号没有被授权的可用 Chat Model，因此只能预览 Prompt / Skill。</small></label>
            <button class="run" :disabled="running" @click="run">{{running?'正在执行…':'▶ 运行测试'}}</button>
          </section>
          <section v-if="result" class="result"><div class="result-head"><div><span>02</span><div><b>测试结果</b><small>{{result.kind}} · {{result.mode}} · {{result.elapsed_ms}} ms</small></div></div><i>SUCCESS</i></div><pre>{{pretty(result.output)}}</pre><template v-if="result.tool_calls.length"><h3>Skill Tool Trace</h3><article v-for="(call,index) in result.tool_calls" :key="`${call.name}-${index}`"><b>{{index+1}}. {{call.name}}</b><small>Arguments</small><pre>{{pretty(call.arguments)}}</pre><small>Output</small><pre>{{pretty(call.output)}}</pre></article></template><details v-if="Object.keys(result.metadata||{}).length"><summary>Metadata</summary><pre>{{pretty(result.metadata)}}</pre></details></section>
        </section>
        <section v-else class="runner empty-runner">请选择一个资源开始测试。</section>
      </section>
    </main>
  </div>
</template>

<style scoped>
*{box-sizing:border-box}.overlay{position:fixed;inset:0;z-index:210;overflow:auto;background:#f6f7fb;color:#101828;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.shell{max-width:1500px;margin:auto;padding:22px 28px 48px}.shell>header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;padding:12px 0 22px}.shell>header span{color:#7f56d9;font-size:11px;font-weight:900;letter-spacing:.12em}.shell>header h1{margin:4px 0 5px;font-size:30px}.shell>header p{margin:0;color:#667085}.close{width:42px;height:42px;border:1px solid #d0d5dd;border-radius:12px;background:#fff;font-size:24px;cursor:pointer}.error{margin:0 0 14px;padding:11px 14px;border-radius:10px;background:#fef3f2;color:#b42318}.layout{display:grid;grid-template-columns:330px minmax(0,1fr);gap:15px;align-items:start}.catalog,.runner{border:1px solid #e4e7ec;border-radius:16px;background:#fff}.catalog{position:sticky;top:14px;max-height:calc(100vh - 40px);overflow:auto;padding:12px}.filters{display:grid;grid-template-columns:1fr 105px;gap:7px;padding-bottom:10px}.filters input,.filters select,.test-form input,.test-form select,.test-form textarea{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:9px 10px;background:#fff;color:#101828;font:inherit}.resource{width:100%;display:grid;gap:7px;padding:12px;border:1px solid transparent;border-radius:11px;background:transparent;text-align:left;cursor:pointer}.resource:hover{background:#f9fafb}.resource.active{border-color:#8b7cf6;background:#f9f5ff}.resource>div{display:flex;justify-content:space-between}.resource span{color:#6941c6;font-size:10px;font-weight:900}.resource em{font-style:normal;color:#98a2b3;font-size:10px}.resource p{margin:0;color:#667085;font-size:12px;line-height:1.45}.empty{padding:25px;text-align:center;color:#98a2b3}.runner{padding:20px}.empty-runner{min-height:300px;display:grid;place-items:center;color:#98a2b3}.resource-head{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid #eaecf0;padding-bottom:17px}.resource-head span{color:#6941c6;font-size:10px;font-weight:900}.resource-head h2{margin:4px 0}.resource-head p{margin:0;color:#667085}.badges{display:flex;gap:5px;align-items:flex-start}.badges i{padding:4px 7px;border-radius:999px;background:#f2f4f7;color:#475467;font-size:9px;font-style:normal}.contract{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:14px 0}.contract article{padding:11px;border-radius:10px;background:#f9fafb}.contract small{color:#667085}.contract p{margin:5px 0 0;font-size:12px;line-height:1.5}.test-form{padding:17px;border:1px solid #eaecf0;border-radius:13px;display:grid;gap:12px}.section-title,.result-head>div{display:flex;gap:9px;align-items:flex-start}.section-title>span,.result-head>div>span{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;background:#eeebff;color:#5925dc;font-size:10px;font-weight:900}.section-title div,.result-head>div>div{display:grid;gap:2px}.section-title small,.result-head small{color:#667085}.test-form label{display:grid;gap:6px;font-size:12px;font-weight:700}.test-form label>small{color:#667085;font-weight:400}.test-form textarea{resize:vertical;line-height:1.5}.code textarea,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.run{justify-self:start;border:0;border-radius:10px;padding:11px 18px;background:#111827;color:#fff;font-weight:800;cursor:pointer}.run:disabled{opacity:.55}.result{margin-top:14px;padding:17px;border:1px solid #d1fadf;border-radius:13px;background:#fcfffd}.result-head{display:flex;justify-content:space-between;align-items:flex-start}.result-head i{padding:4px 8px;border-radius:999px;background:#ecfdf3;color:#067647;font-size:9px;font-style:normal}.result>pre,.result article pre,.result details pre{max-height:360px;overflow:auto;padding:12px;border-radius:9px;background:#111827;color:#e5e7eb;font-size:11px;white-space:pre-wrap;word-break:break-word}.result article{padding-top:11px;border-top:1px solid #d1fadf}.result article small{display:block;margin:7px 0 3px;color:#667085}.result h3{font-size:14px;margin-top:18px}@media(max-width:900px){.layout{grid-template-columns:1fr}.catalog{position:static;max-height:none}.contract{grid-template-columns:1fr}}@media(max-width:560px){.shell{padding:14px}.filters{grid-template-columns:1fr}.resource-head{display:grid}.shell>header h1{font-size:25px}}
</style>