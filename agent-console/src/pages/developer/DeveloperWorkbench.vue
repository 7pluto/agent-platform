<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

interface Principal {
  external_user_id: string
  display_name: string
  role_codes: string[]
  dept_ids: string[]
}

interface CatalogItem {
  version_id: string
  resource_id: string
  resource_type: string
  display_name: string
  description?: string
  version_number: number
  status: string
  summary: string
  dependencies: string[]
  owner_user_id?: string
  owner_dept_id?: string
  source_type: string
  one_line_summary?: string
  when_to_use?: string
  when_not_to_use?: string
  input_summary?: string
  output_summary?: string
  risk_level: string
  read_only: boolean
  tags: string[]
  health: string
}

const props = defineProps<{
  principal: Principal
  csrfToken: string
}>()

const emit = defineEmits<{ logout: [] }>()

type View = 'MINE' | 'AVAILABLE' | 'CREATE'
type CreateType = 'PROMPT' | 'TOOL' | 'SKILL'

const view = ref<View>('MINE')
const mine = ref<CatalogItem[]>([])
const available = ref<CatalogItem[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const query = ref('')
const typeFilter = ref('ALL')
const selected = ref<CatalogItem | null>(null)
const createType = ref<CreateType>('PROMPT')

const form = ref({
  displayName: '',
  slug: '',
  description: '',
  oneLineSummary: '',
  whenToUse: '',
  whenNotToUse: '',
  inputSummary: '',
  outputSummary: '',
  riskLevel: 'LOW' as 'LOW' | 'MEDIUM' | 'HIGH',
  readOnly: true,
  tags: '',
  publicationScope: 'PERSONAL' as 'PERSONAL' | 'OWNER_DEPT',
  template: '你是一个企业智能助手。请严格遵循业务规则回答问题。',
  nativeName: 'echo' as 'current_time' | 'calculator' | 'echo',
  toolName: 'echo_tool',
  inputSchema: '{\n  "type": "object",\n  "properties": {\n    "text": { "type": "string" }\n  }\n}',
  skillMd: '# 业务技能\n\n## 目标\n说明这个 Skill 要完成的业务任务。\n\n## 执行规则\n1. 判断用户意图。\n2. 只调用已授权的依赖能力。\n3. 返回清晰的业务结果。',
  toolVersionIds: [] as string[],
  knowledgeVersionIds: [] as string[],
})

const typeMeta: Record<string, { label: string; role: string }> = {
  MODEL: { label: 'Model', role: '提供推理能力，由平台管理员接入。' },
  PROMPT: { label: 'Prompt', role: '定义角色、规则、回答边界和行为约束。' },
  SKILL: { label: 'Skill', role: '把业务方法、Tool 和 Knowledge 组合成可复用能力包。' },
  TOOL: { label: 'Tool', role: '执行确定性动作，例如计算、查时间或调用业务系统。' },
  KNOWLEDGE: { label: 'Knowledge', role: '提供可检索的业务知识和文档依据。' },
  MEMORY_POLICY: { label: 'Memory', role: '控制跨会话长期记忆。' },
  MCP_CONNECTION: { label: 'MCP', role: '外部能力连接本身，不直接作为业务动作使用。' },
}

const visibleItems = computed(() => {
  const source = view.value === 'MINE' ? mine.value : available.value
  const needle = query.value.trim().toLowerCase()
  return source.filter(item => {
    if (typeFilter.value !== 'ALL' && item.resource_type !== typeFilter.value) return false
    if (!needle) return true
    return `${item.display_name} ${item.description || ''} ${item.one_line_summary || ''} ${item.when_to_use || ''}`.toLowerCase().includes(needle)
  })
})

const availableTools = computed(() => available.value.filter(item => item.resource_type === 'TOOL'))
const availableKnowledge = computed(() => available.value.filter(item => item.resource_type === 'KNOWLEDGE'))
const myCounts = computed(() => mine.value.reduce<Record<string, number>>((result, item) => {
  result[item.resource_type] = (result[item.resource_type] || 0) + 1
  return result
}, {}))

function typeLabel(type: string) { return typeMeta[type]?.label || type }
function typeRole(type: string) { return typeMeta[type]?.role || '可复用 AI 资源。' }
function sourceLabel(source: string) {
  return ({ PLATFORM_NATIVE: '平台原生', DIFY: 'Dify', MCP: 'MCP', HTTP: 'HTTP API', RAGFLOW: 'RAGFlow', OPENAI_COMPATIBLE: '模型服务' } as Record<string, string>)[source] || source
}
function semanticReady(item: CatalogItem) {
  return Boolean(item.one_line_summary && item.when_to_use && item.input_summary && item.output_summary)
}
function slugify(value: string) {
  const ascii = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63)
  return ascii.length >= 3 ? ascii : `resource-${Date.now().toString(36)}`
}
function toggleDependency(field: 'toolVersionIds' | 'knowledgeVersionIds', id: string) {
  const set = new Set(form.value[field])
  if (set.has(id)) set.delete(id); else set.add(id)
  form.value[field] = [...set]
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  if (init.method && init.method !== 'GET') headers.set('X-CSRF-Token', props.csrfToken)
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { credentials: 'same-origin', ...init, headers })
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map(item => typeof item === 'object' && item && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item)).join('；')
      : String(payload.message || payload.detail || payload.code || `HTTP ${response.status}`)
    throw new Error(detail)
  }
  return payload as T
}

async function refresh() {
  loading.value = true; error.value = ''
  try {
    const [owned, usable] = await Promise.all([
      request<CatalogItem[]>('/api/v1/developer/resources/mine'),
      request<CatalogItem[]>('/api/v1/developer/resources/available'),
    ])
    mine.value = owned
    available.value = usable
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { loading.value = false }
}

function resetForm(type = createType.value) {
  form.value = {
    displayName: '', slug: '', description: '', oneLineSummary: '', whenToUse: '', whenNotToUse: '', inputSummary: '', outputSummary: '',
    riskLevel: 'LOW', readOnly: true, tags: '', publicationScope: 'PERSONAL',
    template: '你是一个企业智能助手。请严格遵循业务规则回答问题。',
    nativeName: 'echo', toolName: 'echo_tool', inputSchema: '{\n  "type": "object",\n  "properties": {\n    "text": { "type": "string" }\n  }\n}',
    skillMd: '# 业务技能\n\n## 目标\n说明这个 Skill 要完成的业务任务。\n\n## 执行规则\n1. 判断用户意图。\n2. 只调用已授权的依赖能力。\n3. 返回清晰的业务结果。',
    toolVersionIds: [], knowledgeVersionIds: [],
  }
  createType.value = type
}

function commonPayload() {
  return {
    slug: form.value.slug.trim() || slugify(form.value.displayName),
    display_name: form.value.displayName.trim(),
    description: form.value.description.trim() || form.value.oneLineSummary.trim(),
    one_line_summary: form.value.oneLineSummary.trim(),
    when_to_use: form.value.whenToUse.trim(),
    ...(form.value.whenNotToUse.trim() ? { when_not_to_use: form.value.whenNotToUse.trim() } : {}),
    input_summary: form.value.inputSummary.trim(),
    output_summary: form.value.outputSummary.trim(),
    risk_level: form.value.riskLevel,
    read_only: form.value.readOnly,
    tags: form.value.tags.split(',').map(item => item.trim()).filter(Boolean),
    publication_scope: form.value.publicationScope,
    publication_subjects: [],
  }
}

function validateForm() {
  if (!form.value.displayName.trim()) return '请填写资源名称。'
  if (!form.value.oneLineSummary.trim() || !form.value.whenToUse.trim()) return '请说明资源能做什么，以及什么时候使用。'
  if (!form.value.inputSummary.trim() || !form.value.outputSummary.trim()) return '请说明输入和输出。'
  if (createType.value === 'PROMPT' && !form.value.template.trim()) return 'Prompt 内容不能为空。'
  if (createType.value === 'TOOL') {
    if (!/^[A-Za-z][A-Za-z0-9_]{1,63}$/.test(form.value.toolName.trim())) return 'Tool Name 必须以字母开头，只包含字母、数字、下划线。'
    try {
      const schema = JSON.parse(form.value.inputSchema)
      if (!schema || schema.type !== 'object') return '输入 Schema 必须是 type=object 的 JSON Schema。'
    } catch { return '输入 Schema 不是有效 JSON。' }
  }
  if (createType.value === 'SKILL' && !form.value.skillMd.trim().startsWith('#')) return 'SKILL.md 必须以 Markdown 标题开始。'
  return ''
}

async function createResource() {
  const validation = validateForm()
  if (validation) { error.value = validation; return }
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const common = commonPayload()
    if (createType.value === 'PROMPT') {
      await request('/api/v1/developer/resources/prompts', { method: 'POST', body: JSON.stringify({ ...common, template: form.value.template }) })
    } else if (createType.value === 'TOOL') {
      await request('/api/v1/developer/resources/native-tools', {
        method: 'POST', body: JSON.stringify({ ...common, native_name: form.value.nativeName, tool_name: form.value.toolName.trim(), input_schema: JSON.parse(form.value.inputSchema) }),
      })
    } else {
      await request('/api/v1/developer/resources/skills', {
        method: 'POST', body: JSON.stringify({ ...common, skill_md: form.value.skillMd, tool_version_ids: form.value.toolVersionIds, knowledge_version_ids: form.value.knowledgeVersionIds }),
      })
    }
    notice.value = `${typeLabel(createType.value)} 已发布，并已自动归你所有。现在可以在“我的资源”查看。`
    await refresh()
    view.value = 'MINE'
    resetForm(createType.value)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { saving.value = false }
}

watch(createType, type => resetForm(type))
onMounted(refresh)
</script>

<template>
  <main class="developer-shell">
    <aside class="developer-sidebar">
      <div class="developer-brand"><span>A</span><div><b>开发工作台</b><small>Agent Platform</small></div></div>
      <div class="developer-identity"><div class="avatar">{{ principal.display_name.slice(0, 1) }}</div><div><b>{{ principal.display_name }}</b><small>{{ principal.external_user_id }}</small></div></div>
      <nav>
        <button :class="{ active: view === 'MINE' }" @click="view = 'MINE'; selected = null"><span>01</span><div><b>我的资源</b><small>我开发和维护的能力</small></div><em>{{ mine.length }}</em></button>
        <button :class="{ active: view === 'AVAILABLE' }" @click="view = 'AVAILABLE'; selected = null"><span>02</span><div><b>可用资源</b><small>我拥有 USE 权限的能力</small></div><em>{{ available.length }}</em></button>
        <button :class="{ active: view === 'CREATE' }" @click="view = 'CREATE'; selected = null"><span>03</span><div><b>创建资源</b><small>Prompt / Skill / Native Tool</small></div><em>＋</em></button>
      </nav>
      <section class="developer-boundary"><b>开发者负责什么？</b><p>把业务能力做成可复用资源。Agent 的最终组装、运行授权和治理仍由管理员负责。</p></section>
      <button class="logout-button" @click="emit('logout')">退出登录</button>
    </aside>

    <section class="developer-content">
      <header class="developer-topbar"><div><span>RUOYI DEVELOPER</span><b>{{ view === 'MINE' ? '我的资源' : view === 'AVAILABLE' ? '可用资源' : '创建资源' }}</b></div><button @click="refresh">刷新</button></header>

      <p v-if="error" class="dev-message error">{{ error }}</p>
      <p v-if="notice" class="dev-message success">{{ notice }}</p>

      <template v-if="view !== 'CREATE'">
        <section class="developer-hero">
          <div>
            <p>{{ view === 'MINE' ? 'MY RESOURCES' : 'AUTHORIZED CATALOG' }}</p>
            <h1>{{ view === 'MINE' ? '把开发成果沉淀成资源' : '看看你可以复用哪些能力' }}</h1>
            <span v-if="view === 'MINE'">资源创建后自动归你所有；发布后的能力可以被管理员授权并组装进 Agent。</span>
            <span v-else>这里只展示当前 RuoYi 身份真正拥有 USE 权限的已发布资源；没有权限的能力不会出现在这里。</span>
          </div>
          <button v-if="view === 'MINE'" class="primary-action" @click="view = 'CREATE'">＋ 创建新资源</button>
        </section>

        <section v-if="view === 'MINE'" class="resource-stats">
          <article><small>Prompt</small><b>{{ myCounts.PROMPT || 0 }}</b><span>规则与角色</span></article>
          <article><small>Skill</small><b>{{ myCounts.SKILL || 0 }}</b><span>业务能力包</span></article>
          <article><small>Tool</small><b>{{ myCounts.TOOL || 0 }}</b><span>可执行动作</span></article>
          <article><small>其他</small><b>{{ mine.length - (myCounts.PROMPT || 0) - (myCounts.SKILL || 0) - (myCounts.TOOL || 0) }}</b><span>外部或知识能力</span></article>
        </section>

        <div class="developer-filters">
          <input v-model="query" placeholder="搜索资源名称、用途或适用场景" />
          <select v-model="typeFilter"><option value="ALL">全部类型</option><option value="PROMPT">Prompt</option><option value="SKILL">Skill</option><option value="TOOL">Tool</option><option value="KNOWLEDGE">Knowledge</option><option value="MODEL">Model</option><option value="MEMORY_POLICY">Memory</option></select>
        </div>

        <div class="developer-resource-grid">
          <button v-for="item in visibleItems" :key="item.resource_id" class="developer-resource-card" @click="selected = item">
            <header><span>{{ typeLabel(item.resource_type) }}</span><em>{{ sourceLabel(item.source_type) }}</em></header>
            <h3>{{ item.display_name }}</h3>
            <p>{{ item.one_line_summary || item.description || item.summary }}</p>
            <div class="resource-role"><b>它负责</b><span>{{ typeRole(item.resource_type) }}</span></div>
            <small>适用：{{ item.when_to_use || '尚未填写适用场景' }}</small>
            <footer><div><span>V{{ item.version_number }}</span><span>{{ item.risk_level }}</span><span>{{ item.read_only ? '只读' : '可写' }}</span></div><strong>{{ semanticReady(item) ? '已可用于组装' : '说明待完善' }}</strong></footer>
          </button>
          <p v-if="loading" class="empty-state">正在加载资源…</p>
          <p v-else-if="!visibleItems.length" class="empty-state">当前没有符合条件的资源。</p>
        </div>
      </template>

      <template v-else>
        <section class="developer-hero create-hero"><div><p>CREATE RESOURCE</p><h1>创建一个可复用能力</h1><span>开发阶段先支持 Prompt、Skill 和平台 Native Tool。不要从“做一个 Agent”开始，先把稳定能力沉淀成资源。</span></div></section>
        <div class="create-type-switch">
          <button :class="{ active: createType === 'PROMPT' }" @click="createType = 'PROMPT'"><b>Prompt</b><span>角色、规则、回答边界</span></button>
          <button :class="{ active: createType === 'SKILL' }" @click="createType = 'SKILL'"><b>Skill</b><span>业务方法 + Tool / Knowledge</span></button>
          <button :class="{ active: createType === 'TOOL' }" @click="createType = 'TOOL'"><b>Native Tool</b><span>确定性可执行动作</span></button>
        </div>

        <section class="resource-editor">
          <aside class="editor-guide">
            <p>当前资源</p><h3>{{ typeLabel(createType) }}</h3><strong>{{ typeRole(createType) }}</strong>
            <ol><li>先说明业务价值</li><li>再配置技术内容</li><li>最后发布成为版本</li></ol>
            <div v-if="createType === 'SKILL'" class="skill-tip"><b>Skill 不是 Tool 列表</b><p>Skill 描述“怎么完成一类业务任务”，依赖的 Tool / Knowledge 会自动在 Agent 发布预检时展开。</p></div>
          </aside>

          <div class="editor-form">
            <section><div class="form-section-title"><span>01</span><div><b>这个资源是什么？</b><small>先让其他开发者和管理员看懂，再谈配置。</small></div></div>
              <div class="form-grid"><label>资源名称<input v-model="form.displayName" placeholder="例如：员工制度问答规则" /></label><label>Slug<input v-model="form.slug" :placeholder="form.displayName ? slugify(form.displayName) : 'employee-policy'" /></label><label class="wide">一句话能力<input v-model="form.oneLineSummary" placeholder="用一句业务语言说明它能解决什么问题" /></label><label class="wide">补充说明<textarea v-model="form.description" rows="2" placeholder="可选：背景、边界或开发说明" /></label></div>
            </section>

            <section><div class="form-section-title"><span>02</span><div><b>什么时候该使用？</b><small>这些信息会直接展示给 Agent 管理员。</small></div></div>
              <div class="form-grid"><label>何时使用<textarea v-model="form.whenToUse" rows="3" placeholder="例如：用户询问员工制度、考勤、请假规则时" /></label><label>何时不要使用<textarea v-model="form.whenNotToUse" rows="3" placeholder="可选：例如涉及薪酬审批时不要使用" /></label><label>输入说明<textarea v-model="form.inputSummary" rows="3" placeholder="这个能力需要什么输入" /></label><label>输出说明<textarea v-model="form.outputSummary" rows="3" placeholder="会返回什么结果" /></label></div>
            </section>

            <section><div class="form-section-title"><span>03</span><div><b>{{ createType === 'PROMPT' ? 'Prompt 内容' : createType === 'TOOL' ? 'Tool 配置' : 'Skill 方法与依赖' }}</b><small>这里才是技术配置。</small></div></div>
              <label v-if="createType === 'PROMPT'" class="wide code-field">System Prompt<textarea v-model="form.template" rows="12" /></label>
              <div v-else-if="createType === 'TOOL'" class="form-grid"><label>内置实现<select v-model="form.nativeName"><option value="current_time">current_time · 当前时间</option><option value="calculator">calculator · 计算器</option><option value="echo">echo · 回显测试</option></select></label><label>Tool Name<input v-model="form.toolName" /></label><label class="wide code-field">输入 JSON Schema<textarea v-model="form.inputSchema" rows="10" /></label></div>
              <div v-else class="skill-editor"><label class="wide code-field">SKILL.md<textarea v-model="form.skillMd" rows="14" /></label>
                <div class="dependency-section"><div><b>可使用的 Tool</b><small>只显示当前 RuoYi 身份拥有 USE 权限的 Tool。</small></div><div class="dependency-grid"><label v-for="item in availableTools" :key="item.version_id" :class="{ selected: form.toolVersionIds.includes(item.version_id) }"><input type="checkbox" :checked="form.toolVersionIds.includes(item.version_id)" @change="toggleDependency('toolVersionIds', item.version_id)" /><span><b>{{ item.display_name }}</b><small>{{ item.one_line_summary || item.summary }}</small></span></label><p v-if="!availableTools.length">暂无可用 Tool。</p></div></div>
                <div class="dependency-section"><div><b>可使用的 Knowledge</b><small>Skill 可声明知识依赖，Agent 组装时会一起校验。</small></div><div class="dependency-grid"><label v-for="item in availableKnowledge" :key="item.version_id" :class="{ selected: form.knowledgeVersionIds.includes(item.version_id) }"><input type="checkbox" :checked="form.knowledgeVersionIds.includes(item.version_id)" @change="toggleDependency('knowledgeVersionIds', item.version_id)" /><span><b>{{ item.display_name }}</b><small>{{ item.one_line_summary || item.summary }}</small></span></label><p v-if="!availableKnowledge.length">暂无可用 Knowledge。</p></div></div>
              </div>
            </section>

            <section><div class="form-section-title"><span>04</span><div><b>风险与发布范围</b><small>开发阶段先支持个人或责任部门范围。</small></div></div>
              <div class="form-grid"><label>风险等级<select v-model="form.riskLevel"><option value="LOW">低</option><option value="MEDIUM">中</option><option value="HIGH">高</option></select></label><label>发布范围<select v-model="form.publicationScope"><option value="PERSONAL">仅我自己</option><option value="OWNER_DEPT" :disabled="!principal.dept_ids.length">责任部门可用</option></select></label><label class="check-row"><input v-model="form.readOnly" type="checkbox" />这是只读能力</label><label>标签<input v-model="form.tags" placeholder="制度, 人事, 查询" /></label></div>
            </section>

            <footer class="editor-actions"><button class="secondary-action" @click="resetForm()">清空</button><button class="primary-action" :disabled="saving" @click="createResource">{{ saving ? '发布中…' : `发布 ${typeLabel(createType)}` }}</button></footer>
          </div>
        </section>
      </template>
    </section>

    <div v-if="selected" class="resource-preview-backdrop" @click.self="selected = null">
      <aside class="resource-preview-panel"><button class="preview-close" @click="selected = null">×</button><p>{{ typeLabel(selected.resource_type) }} · {{ sourceLabel(selected.source_type) }} · V{{ selected.version_number }}</p><h2>{{ selected.display_name }}</h2><strong>{{ selected.one_line_summary || selected.description || selected.summary }}</strong><div class="preview-role"><b>在 Agent 中负责</b><span>{{ typeRole(selected.resource_type) }}</span></div><dl><dt>何时使用</dt><dd>{{ selected.when_to_use || '尚未填写' }}</dd><dt>何时不使用</dt><dd>{{ selected.when_not_to_use || '无额外限制' }}</dd><dt>输入</dt><dd>{{ selected.input_summary || '尚未填写' }}</dd><dt>输出</dt><dd>{{ selected.output_summary || '尚未填写' }}</dd><dt>风险</dt><dd>{{ selected.risk_level }} · {{ selected.read_only ? '只读' : '可写' }}</dd><dt>依赖</dt><dd>{{ selected.dependencies.length ? `${selected.dependencies.length} 项资源依赖` : '无直接依赖' }}</dd><dt>Owner</dt><dd>{{ selected.owner_user_id || '—' }}</dd></dl><div class="preview-ready" :class="{ incomplete: !semanticReady(selected) }">{{ semanticReady(selected) ? '该资源业务说明完整，可以交给 Agent 管理员组装。' : '该资源业务说明不完整，建议补齐后再用于 Agent。' }}</div></aside>
    </div>
  </main>
</template>

<style scoped>
* { box-sizing: border-box; }
.developer-shell { min-height:100vh; display:grid; grid-template-columns:260px minmax(0,1fr); background:#f7f8fb; color:#101828; font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif; }
.developer-sidebar { position:sticky; top:0; height:100vh; padding:20px 16px; background:#111827; color:white; display:flex; flex-direction:column; gap:20px; }
.developer-brand,.developer-identity { display:flex; align-items:center; gap:11px; }
.developer-brand>span { width:34px; height:34px; border-radius:10px; display:grid; place-items:center; background:#6d5dfc; font-weight:900; }
.developer-brand div,.developer-identity div { display:grid; gap:2px; }.developer-brand small,.developer-identity small { color:#98a2b3; font-size:11px; }
.avatar { width:38px; height:38px; border-radius:50%; display:grid!important; place-items:center; background:#344054; color:#fff; font-weight:800; }
.developer-identity { padding:13px; border:1px solid #344054; border-radius:12px; background:#1d2939; }
.developer-sidebar nav { display:grid; gap:7px; }.developer-sidebar nav button { display:grid; grid-template-columns:25px 1fr auto; align-items:center; gap:9px; width:100%; border:0; border-radius:11px; padding:12px; color:#d0d5dd; background:transparent; text-align:left; cursor:pointer; }.developer-sidebar nav button.active { background:#312e81; color:white; }.developer-sidebar nav button>span { color:#a5b4fc; font-size:11px; font-weight:800; }.developer-sidebar nav button div { display:grid; gap:2px; }.developer-sidebar nav button small { color:#98a2b3; font-size:11px; }.developer-sidebar nav button em { min-width:24px; height:24px; border-radius:999px; display:grid; place-items:center; background:#344054; font-style:normal; font-size:11px; }
.developer-boundary { margin-top:auto; padding:13px; border:1px solid #344054; border-radius:12px; background:#1d2939; }.developer-boundary p { margin:6px 0 0; color:#98a2b3; font-size:12px; line-height:1.55; }.logout-button { border:1px solid #475467; border-radius:10px; padding:10px; color:#d0d5dd; background:transparent; cursor:pointer; }
.developer-content { min-width:0; }.developer-topbar { height:66px; padding:0 28px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid #eaecf0; background:white; }.developer-topbar div { display:grid; gap:2px; }.developer-topbar span { color:#7f56d9; font-size:10px; font-weight:800; letter-spacing:.1em; }.developer-topbar button { border:1px solid #d0d5dd; border-radius:8px; padding:8px 12px; background:white; cursor:pointer; }
.dev-message { margin:16px 28px 0; padding:11px 14px; border-radius:9px; }.dev-message.error { background:#fef3f2; color:#b42318; }.dev-message.success { background:#ecfdf3; color:#067647; }
.developer-hero { margin:26px 28px 18px; padding:26px; border-radius:18px; display:flex; justify-content:space-between; gap:20px; align-items:end; background:linear-gradient(135deg,#312e81,#5b4ee5); color:white; }.developer-hero p { margin:0 0 6px; color:#c7d2fe; font-size:11px; font-weight:800; letter-spacing:.1em; }.developer-hero h1 { margin:0 0 7px; font-size:28px; }.developer-hero span { color:#e0e7ff; line-height:1.55; }.create-hero { align-items:start; }
.primary-action,.secondary-action { border:0; border-radius:10px; padding:11px 16px; font-weight:700; cursor:pointer; }.primary-action { background:#fff; color:#4338ca; }.secondary-action { background:#f2f4f7; color:#344054; }.editor-actions .primary-action { background:#5b4ee5; color:white; }.primary-action:disabled { opacity:.5; cursor:default; }
.resource-stats { margin:0 28px 18px; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }.resource-stats article { padding:16px; border:1px solid #e4e7ec; border-radius:14px; background:white; display:grid; gap:3px; }.resource-stats small,.resource-stats span { color:#667085; }.resource-stats b { font-size:24px; }
.developer-filters { margin:0 28px 16px; padding:12px; display:grid; grid-template-columns:minmax(0,1fr) 170px; gap:10px; border:1px solid #e4e7ec; border-radius:13px; background:white; }.developer-filters input,.developer-filters select,.editor-form input,.editor-form select,.editor-form textarea { width:100%; border:1px solid #d0d5dd; border-radius:9px; padding:9px 10px; background:white; color:#101828; font:inherit; }.editor-form textarea { resize:vertical; line-height:1.55; }
.developer-resource-grid { margin:0 28px 32px; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }.developer-resource-card { min-height:270px; padding:17px; border:1px solid #e4e7ec; border-radius:15px; background:white; text-align:left; cursor:pointer; display:grid; align-content:start; gap:10px; }.developer-resource-card:hover { border-color:#a4a0f7; box-shadow:0 8px 24px rgba(16,24,40,.07); }.developer-resource-card header,.developer-resource-card footer { display:flex; justify-content:space-between; gap:8px; align-items:center; }.developer-resource-card header span { padding:4px 8px; border-radius:999px; background:#eeebff; color:#5145cd; font-size:11px; font-weight:800; }.developer-resource-card header em { color:#667085; font-size:11px; font-style:normal; }.developer-resource-card h3,.developer-resource-card p { margin:0; }.developer-resource-card p { color:#344054; line-height:1.5; }.resource-role { padding:9px; border-radius:9px; background:#f9fafb; display:grid; gap:3px; font-size:12px; }.resource-role span,.developer-resource-card>small { color:#667085; line-height:1.45; }.developer-resource-card footer { margin-top:auto; padding-top:8px; border-top:1px solid #f2f4f7; }.developer-resource-card footer div { display:flex; gap:6px; }.developer-resource-card footer div span { color:#667085; font-size:10px; }.developer-resource-card footer strong { color:#067647; font-size:11px; }.empty-state { grid-column:1/-1; padding:40px; text-align:center; color:#667085; }
.create-type-switch { margin:0 28px 16px; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }.create-type-switch button { padding:15px; border:1px solid #e4e7ec; border-radius:13px; background:white; text-align:left; display:grid; gap:4px; cursor:pointer; }.create-type-switch button.active { border-color:#6958e8; background:#f5f3ff; }.create-type-switch span { color:#667085; font-size:12px; }
.resource-editor { margin:0 28px 36px; display:grid; grid-template-columns:230px minmax(0,1fr); gap:16px; align-items:start; }.editor-guide { position:sticky; top:82px; padding:18px; border:1px solid #e4e7ec; border-radius:15px; background:white; }.editor-guide>p { margin:0; color:#7f56d9; font-size:10px; font-weight:800; letter-spacing:.08em; }.editor-guide h3 { margin:5px 0; }.editor-guide>strong { display:block; color:#475467; font-size:13px; line-height:1.5; }.editor-guide ol { padding-left:20px; color:#667085; line-height:1.9; font-size:13px; }.skill-tip { margin-top:14px; padding:11px; border-radius:10px; background:#fffaeb; color:#7a2e0e; }.skill-tip p { margin:4px 0 0; font-size:12px; line-height:1.5; }
.editor-form { display:grid; gap:14px; }.editor-form>section { padding:20px; border:1px solid #e4e7ec; border-radius:15px; background:white; }.form-section-title { display:flex; gap:10px; align-items:start; margin-bottom:16px; }.form-section-title>span { min-width:28px; height:28px; border-radius:8px; display:grid; place-items:center; background:#eeebff; color:#5145cd; font-size:11px; font-weight:800; }.form-section-title div { display:grid; gap:3px; }.form-section-title small { color:#667085; }.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:13px; }.editor-form label { display:grid; gap:7px; color:#344054; font-size:13px; font-weight:700; }.editor-form label.wide,.code-field { grid-column:1/-1; }.code-field textarea { font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; }.check-row { display:flex!important; align-items:center; gap:8px!important; }.check-row input { width:auto!important; }
.skill-editor { display:grid; gap:15px; }.dependency-section { display:grid; gap:9px; }.dependency-section>div:first-child { display:grid; gap:3px; }.dependency-section small { color:#667085; }.dependency-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }.dependency-grid label { grid-template-columns:auto 1fr!important; align-items:start; padding:10px; border:1px solid #e4e7ec; border-radius:10px; cursor:pointer; }.dependency-grid label.selected { border-color:#6958e8; background:#f5f3ff; }.dependency-grid input { width:auto!important; margin-top:3px; }.dependency-grid span { display:grid; gap:3px; }.editor-actions { display:flex; justify-content:flex-end; gap:9px; }
.resource-preview-backdrop { position:fixed; inset:0; z-index:40; background:rgba(16,24,40,.34); display:flex; justify-content:flex-end; }.resource-preview-panel { width:min(520px,92vw); height:100%; padding:28px; background:white; overflow:auto; position:relative; }.preview-close { position:absolute; top:16px; right:16px; border:0; background:transparent; font-size:25px; cursor:pointer; }.resource-preview-panel>p { margin:0 0 6px; color:#7f56d9; font-size:12px; font-weight:700; }.resource-preview-panel h2 { margin:0 0 10px; }.resource-preview-panel>strong { display:block; line-height:1.55; }.preview-role { margin:18px 0; padding:13px; border-radius:11px; background:#f5f3ff; display:grid; gap:4px; }.preview-role span { color:#5145cd; line-height:1.5; }.resource-preview-panel dl { display:grid; grid-template-columns:90px 1fr; gap:10px; }.resource-preview-panel dt { color:#667085; }.resource-preview-panel dd { margin:0; line-height:1.5; }.preview-ready { margin-top:20px; padding:12px; border-radius:10px; background:#ecfdf3; color:#067647; }.preview-ready.incomplete { background:#fffaeb; color:#7a2e0e; }
@media(max-width:1180px){.developer-resource-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.resource-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:860px){.developer-shell{grid-template-columns:1fr}.developer-sidebar{position:static;height:auto}.developer-sidebar nav{grid-template-columns:repeat(3,1fr)}.developer-boundary{margin-top:0}.resource-editor{grid-template-columns:1fr}.editor-guide{position:static}.developer-resource-grid{grid-template-columns:1fr}}
@media(max-width:640px){.developer-sidebar nav{grid-template-columns:1fr}.developer-resource-grid,.developer-hero,.resource-stats,.developer-filters,.create-type-switch,.resource-editor{margin-left:14px;margin-right:14px}.resource-stats,.create-type-switch,.form-grid,.dependency-grid{grid-template-columns:1fr}.developer-filters{grid-template-columns:1fr}.developer-hero{align-items:start;flex-direction:column}}
</style>
