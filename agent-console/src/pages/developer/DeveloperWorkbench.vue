<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

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

interface ResourceVersion {
  resource_version_id: string
  resource_id: string
  resource_type: string
  version_number: number
  status: 'DRAFT' | 'PUBLISHED' | 'DEPRECATED'
  config: Record<string, unknown>
  content_hash: string
  created_by: string
  created_at?: string
  published_at?: string
}

interface ResourceSemantics {
  one_line_summary: string
  when_to_use: string
  when_not_to_use?: string
  input_summary: string
  output_summary: string
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH'
  read_only: boolean
  tags: string[]
  publication_scope: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'
}

interface DeveloperResourceDetail {
  resource_id: string
  resource_type: 'PROMPT' | 'TOOL' | 'SKILL' | string
  slug: string
  display_name: string
  description?: string
  editable: boolean
  semantics: ResourceSemantics
  versions: ResourceVersion[]
  active_draft_version_id?: string
  base_version_id?: string
  editable_config: Record<string, unknown>
}

const props = defineProps<{
  principal: Principal
  csrfToken: string
}>()
const emit = defineEmits<{ logout: [] }>()

type View = 'MINE' | 'AVAILABLE' | 'CREATE' | 'EDIT'
type CreateType = 'PROMPT' | 'TOOL' | 'SKILL'

const view = ref<View>('MINE')
const mine = ref<CatalogItem[]>([])
const available = ref<CatalogItem[]>([])
const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const error = ref('')
const notice = ref('')
const query = ref('')
const typeFilter = ref('ALL')
const selected = ref<CatalogItem | null>(null)
const resourceDetail = ref<DeveloperResourceDetail | null>(null)
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
const activeDraft = computed(() => resourceDetail.value?.versions.find(item => item.status === 'DRAFT') || null)
const latestPublished = computed(() => resourceDetail.value?.versions.find(item => item.status === 'PUBLISHED') || null)
const editingVersionNumber = computed(() => activeDraft.value?.version_number || ((latestPublished.value?.version_number || 0) + 1))
const editorTitle = computed(() => view.value === 'EDIT' && resourceDetail.value
  ? `${resourceDetail.value.display_name} · V${editingVersionNumber.value}`
  : `创建 ${typeLabel(createType.value)}`)

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
function shortTime(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
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
  createType.value = type
  form.value = {
    displayName: '', slug: '', description: '', oneLineSummary: '', whenToUse: '', whenNotToUse: '', inputSummary: '', outputSummary: '',
    riskLevel: 'LOW', readOnly: true, tags: '', publicationScope: 'PERSONAL',
    template: '你是一个企业智能助手。请严格遵循业务规则回答问题。',
    nativeName: 'echo', toolName: 'echo_tool', inputSchema: '{\n  "type": "object",\n  "properties": {\n    "text": { "type": "string" }\n  }\n}',
    skillMd: '# 业务技能\n\n## 目标\n说明这个 Skill 要完成的业务任务。\n\n## 执行规则\n1. 判断用户意图。\n2. 只调用已授权的依赖能力。\n3. 返回清晰的业务结果。',
    toolVersionIds: [], knowledgeVersionIds: [],
  }
}
function switchCreateType(type: CreateType) {
  if (view.value !== 'CREATE') return
  resetForm(type)
}
function commonCreatePayload() {
  return {
    slug: form.value.slug.trim() || slugify(form.value.displayName),
    display_name: form.value.displayName.trim(),
    description: form.value.description.trim() || form.value.oneLineSummary.trim(),
    ...semanticPayload(),
  }
}
function semanticPayload() {
  return {
    one_line_summary: form.value.oneLineSummary.trim(),
    when_to_use: form.value.whenToUse.trim(),
    ...(form.value.whenNotToUse.trim() ? { when_not_to_use: form.value.whenNotToUse.trim() } : {}),
    input_summary: form.value.inputSummary.trim(),
    output_summary: form.value.outputSummary.trim(),
    risk_level: form.value.riskLevel,
    read_only: form.value.readOnly,
    tags: form.value.tags.split(',').map(item => item.trim()).filter(Boolean),
    publication_scope: view.value === 'EDIT' ? 'PERSONAL' : form.value.publicationScope,
    publication_subjects: [],
  }
}
function resourceConfig() {
  if (createType.value === 'PROMPT') return { template: form.value.template }
  if (createType.value === 'TOOL') return {
    kind: 'NATIVE',
    native_name: form.value.nativeName,
    tool_name: form.value.toolName.trim(),
    description: form.value.description.trim() || form.value.oneLineSummary.trim(),
    input_schema: JSON.parse(form.value.inputSchema),
  }
  return {
    skill_md: form.value.skillMd,
    tool_version_ids: form.value.toolVersionIds,
    knowledge_version_ids: form.value.knowledgeVersionIds,
  }
}
function validateForm() {
  if (view.value === 'CREATE' && !form.value.displayName.trim()) return '请填写资源名称。'
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
    const common = commonCreatePayload()
    if (createType.value === 'PROMPT') {
      await request('/api/v1/developer/resources/prompts', { method: 'POST', body: JSON.stringify({ ...common, template: form.value.template }) })
    } else if (createType.value === 'TOOL') {
      const config = resourceConfig()
      await request('/api/v1/developer/resources/native-tools', {
        method: 'POST', body: JSON.stringify({ ...common, native_name: config.native_name, tool_name: config.tool_name, input_schema: config.input_schema }),
      })
    } else {
      const config = resourceConfig()
      await request('/api/v1/developer/resources/skills', {
        method: 'POST', body: JSON.stringify({ ...common, skill_md: config.skill_md, tool_version_ids: config.tool_version_ids, knowledge_version_ids: config.knowledge_version_ids }),
      })
    }
    notice.value = `${typeLabel(createType.value)} V1 已发布，并已自动归你所有。`
    await refresh()
    view.value = 'MINE'
    resetForm(createType.value)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { saving.value = false }
}

function fillVersionForm(detail: DeveloperResourceDetail) {
  const type = detail.resource_type as CreateType
  createType.value = type
  const config = detail.editable_config || {}
  form.value = {
    displayName: detail.display_name,
    slug: detail.slug,
    description: detail.description || '',
    oneLineSummary: detail.semantics.one_line_summary || '',
    whenToUse: detail.semantics.when_to_use || '',
    whenNotToUse: detail.semantics.when_not_to_use || '',
    inputSummary: detail.semantics.input_summary || '',
    outputSummary: detail.semantics.output_summary || '',
    riskLevel: detail.semantics.risk_level || 'LOW',
    readOnly: detail.semantics.read_only,
    tags: (detail.semantics.tags || []).join(', '),
    publicationScope: 'PERSONAL',
    template: String(config.template || ''),
    nativeName: (config.native_name as 'current_time' | 'calculator' | 'echo') || 'echo',
    toolName: String(config.tool_name || 'echo_tool'),
    inputSchema: JSON.stringify(config.input_schema || { type: 'object', properties: {} }, null, 2),
    skillMd: String(config.skill_md || '# 业务技能\n'),
    toolVersionIds: Array.isArray(config.tool_version_ids) ? config.tool_version_ids.map(String) : [],
    knowledgeVersionIds: Array.isArray(config.knowledge_version_ids) ? config.knowledge_version_ids.map(String) : [],
  }
}

async function openVersionEditor(item: CatalogItem) {
  loading.value = true; error.value = ''; notice.value = ''
  try {
    const detail = await request<DeveloperResourceDetail>(`/api/v1/developer/resources/${item.resource_id}`)
    resourceDetail.value = detail
    if (!detail.editable) {
      selected.value = item
      error.value = '当前开发阶段仅支持编辑 Prompt、Skill 和平台 Native Tool；外部能力请回连接器侧维护。'
      return
    }
    fillVersionForm(detail)
    selected.value = null
    view.value = 'EDIT'
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { loading.value = false }
}

async function reloadVersionDetail() {
  if (!resourceDetail.value) return
  const detail = await request<DeveloperResourceDetail>(`/api/v1/developer/resources/${resourceDetail.value.resource_id}`)
  resourceDetail.value = detail
  fillVersionForm(detail)
}

async function saveDraft() {
  if (!resourceDetail.value) return
  const validation = validateForm()
  if (validation) { error.value = validation; return }
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const body = JSON.stringify({ ...semanticPayload(), config: resourceConfig() })
    if (resourceDetail.value.active_draft_version_id) {
      await request(`/api/v1/developer/resources/${resourceDetail.value.resource_id}/versions/${resourceDetail.value.active_draft_version_id}`, { method: 'PUT', body })
      notice.value = `V${editingVersionNumber.value} 草稿已更新。旧的已发布版本没有变化。`
    } else {
      await request(`/api/v1/developer/resources/${resourceDetail.value.resource_id}/versions`, { method: 'POST', body })
      notice.value = `V${editingVersionNumber.value} 草稿已创建。发布前可以继续修改。`
    }
    await reloadVersionDetail()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { saving.value = false }
}

async function publishDraft() {
  if (!resourceDetail.value?.active_draft_version_id) return
  publishing.value = true; error.value = ''; notice.value = ''
  try {
    const version = activeDraft.value
    await request(`/api/v1/developer/resources/${resourceDetail.value.resource_id}/versions/${resourceDetail.value.active_draft_version_id}/publish`, { method: 'POST' })
    notice.value = `V${version?.version_number || ''} 已发布。已有 Agent 仍锁定原 Version，新组装或新 Revision 才会选择新版本。`
    await refresh()
    await reloadVersionDetail()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { publishing.value = false }
}

function leaveEditor() {
  resourceDetail.value = null
  view.value = 'MINE'
  error.value = ''
}

onMounted(refresh)
</script>

<template>
  <main class="developer-shell">
    <aside class="developer-sidebar">
      <div class="developer-brand"><span>A</span><div><b>开发工作台</b><small>Agent Platform</small></div></div>
      <div class="developer-identity"><div class="avatar">{{ principal.display_name.slice(0, 1) }}</div><div><b>{{ principal.display_name }}</b><small>{{ principal.external_user_id }}</small></div></div>
      <nav>
        <button :class="{ active: view === 'MINE' || view === 'EDIT' }" @click="leaveEditor"><span>01</span><div><b>我的资源</b><small>开发、编辑和版本迭代</small></div><em>{{ mine.length }}</em></button>
        <button :class="{ active: view === 'AVAILABLE' }" @click="view = 'AVAILABLE'; selected = null; resourceDetail = null"><span>02</span><div><b>可用资源</b><small>我拥有 USE 权限的能力</small></div><em>{{ available.length }}</em></button>
        <button :class="{ active: view === 'CREATE' }" @click="view = 'CREATE'; selected = null; resourceDetail = null; resetForm('PROMPT')"><span>03</span><div><b>创建资源</b><small>Prompt / Skill / Native Tool</small></div><em>＋</em></button>
      </nav>
      <section class="developer-boundary"><b>版本规则</b><p>已发布版本不可修改。编辑资源会创建新 Draft；发布 V2 不会自动改变仍锁定 V1 的 Agent。</p></section>
      <button class="logout-button" @click="emit('logout')">退出登录</button>
    </aside>

    <section class="developer-content">
      <header class="developer-topbar"><div><span>RUOYI DEVELOPER</span><b>{{ view === 'MINE' ? '我的资源' : view === 'AVAILABLE' ? '可用资源' : view === 'CREATE' ? '创建资源' : editorTitle }}</b></div><button @click="refresh">刷新资源</button></header>

      <p v-if="error" class="dev-message error">{{ error }}</p>
      <p v-if="notice" class="dev-message success">{{ notice }}</p>

      <template v-if="view === 'MINE' || view === 'AVAILABLE'">
        <section class="developer-hero">
          <div><p>{{ view === 'MINE' ? 'MY RESOURCES' : 'AUTHORIZED CATALOG' }}</p><h1>{{ view === 'MINE' ? '持续演进你的能力资源' : '复用已有企业能力' }}</h1><span v-if="view === 'MINE'">打开自己的资源可以查看版本历史、创建 Draft、反复编辑并发布新版本。</span><span v-else>这里只展示当前 RuoYi 身份真正拥有 USE 权限的已发布资源。</span></div>
          <button v-if="view === 'MINE'" class="primary-action" @click="view = 'CREATE'; resetForm('PROMPT')">＋ 创建新资源</button>
        </section>

        <section v-if="view === 'MINE'" class="resource-stats">
          <article><small>Prompt</small><b>{{ myCounts.PROMPT || 0 }}</b><span>规则与角色</span></article>
          <article><small>Skill</small><b>{{ myCounts.SKILL || 0 }}</b><span>业务能力包</span></article>
          <article><small>Tool</small><b>{{ myCounts.TOOL || 0 }}</b><span>可执行动作</span></article>
          <article><small>全部资源</small><b>{{ mine.length }}</b><span>当前 Owner 资产</span></article>
        </section>

        <div class="developer-filters"><input v-model="query" placeholder="搜索资源名称、用途或适用场景" /><select v-model="typeFilter"><option value="ALL">全部类型</option><option value="PROMPT">Prompt</option><option value="SKILL">Skill</option><option value="TOOL">Tool</option><option value="KNOWLEDGE">Knowledge</option><option value="MODEL">Model</option><option value="MEMORY_POLICY">Memory</option></select></div>

        <div class="developer-resource-grid">
          <article v-for="item in visibleItems" :key="item.resource_id" class="developer-resource-card">
            <header><span>{{ typeLabel(item.resource_type) }}</span><em>{{ sourceLabel(item.source_type) }}</em></header>
            <h3>{{ item.display_name }}</h3><p>{{ item.one_line_summary || item.description || item.summary }}</p>
            <div class="resource-role"><b>它负责</b><span>{{ typeRole(item.resource_type) }}</span></div>
            <small>适用：{{ item.when_to_use || '尚未填写适用场景' }}</small>
            <div class="version-line"><b>当前 V{{ item.version_number }}</b><span>{{ item.status }}</span><span>{{ item.risk_level }} 风险</span></div>
            <footer><button @click="selected = item">查看详情</button><button v-if="view === 'MINE'" class="edit-button" @click="openVersionEditor(item)">编辑 / 新建版本</button><strong v-else>{{ semanticReady(item) ? '可复用' : '说明待完善' }}</strong></footer>
          </article>
          <p v-if="loading" class="empty-state">正在加载资源…</p><p v-else-if="!visibleItems.length" class="empty-state">当前没有符合条件的资源。</p>
        </div>
      </template>

      <template v-else-if="view === 'CREATE' || view === 'EDIT'">
        <section class="developer-hero create-hero"><div><p>{{ view === 'EDIT' ? 'VERSION EDITOR' : 'CREATE RESOURCE' }}</p><h1>{{ view === 'EDIT' ? editorTitle : '创建一个可复用能力' }}</h1><span v-if="view === 'EDIT'">基于当前已发布版本继续演进。先保存 Draft，确认后再发布；历史版本保持不变。</span><span v-else>开发阶段先支持 Prompt、Skill 和平台 Native Tool。</span></div><button v-if="view === 'EDIT'" class="primary-action" @click="leaveEditor">返回我的资源</button></section>

        <div v-if="view === 'CREATE'" class="create-type-switch">
          <button :class="{ active: createType === 'PROMPT' }" @click="switchCreateType('PROMPT')"><b>Prompt</b><span>角色、规则、回答边界</span></button>
          <button :class="{ active: createType === 'SKILL' }" @click="switchCreateType('SKILL')"><b>Skill</b><span>业务方法 + Tool / Knowledge</span></button>
          <button :class="{ active: createType === 'TOOL' }" @click="switchCreateType('TOOL')"><b>Native Tool</b><span>确定性可执行动作</span></button>
        </div>

        <section class="resource-editor">
          <aside class="editor-guide">
            <p>{{ view === 'EDIT' ? 'VERSION HISTORY' : 'CURRENT RESOURCE' }}</p><h3>{{ typeLabel(createType) }}</h3><strong>{{ typeRole(createType) }}</strong>
            <template v-if="view === 'EDIT' && resourceDetail">
              <div class="version-safety"><b>不会覆盖旧版本</b><p>发布 V{{ editingVersionNumber }} 后，旧 Agent 继续使用自己锁定的 Version ID。</p></div>
              <div class="version-history"><article v-for="version in resourceDetail.versions" :key="version.resource_version_id"><div><b>V{{ version.version_number }}</b><span :class="version.status.toLowerCase()">{{ version.status === 'DRAFT' ? '草稿' : version.status === 'PUBLISHED' ? '已发布' : '已停用' }}</span></div><small>{{ version.status === 'PUBLISHED' ? shortTime(version.published_at) : '可继续编辑' }}</small><code>{{ version.content_hash.slice(0, 10) }}</code></article></div>
            </template>
            <ol v-else><li>先说明业务价值</li><li>再配置技术内容</li><li>发布成为 V1</li></ol>
          </aside>

          <div class="editor-form">
            <section><div class="form-section-title"><span>01</span><div><b>这个资源是什么？</b><small>{{ view === 'EDIT' ? '资源身份保持不变，本次修改形成新版本。' : '先让其他开发者和管理员看懂。' }}</small></div></div>
              <div v-if="view === 'EDIT' && resourceDetail" class="identity-lock"><span><small>资源名称</small><b>{{ resourceDetail.display_name }}</b></span><span><small>Slug</small><b>{{ resourceDetail.slug }}</b></span><span><small>资源 ID</small><b>{{ resourceDetail.resource_id.slice(0, 8) }}…</b></span></div>
              <div v-else class="form-grid"><label>资源名称<input v-model="form.displayName" placeholder="例如：员工制度问答规则" /></label><label>Slug<input v-model="form.slug" :placeholder="form.displayName ? slugify(form.displayName) : 'employee-policy'" /></label><label class="wide">补充说明<textarea v-model="form.description" rows="2" /></label></div>
              <label class="wide inline-field">一句话能力<input v-model="form.oneLineSummary" placeholder="用一句业务语言说明它能解决什么问题" /></label>
            </section>

            <section><div class="form-section-title"><span>02</span><div><b>什么时候该使用？</b><small>这些信息会直接展示给 Agent 管理员。</small></div></div><div class="form-grid"><label>何时使用<textarea v-model="form.whenToUse" rows="3" /></label><label>何时不要使用<textarea v-model="form.whenNotToUse" rows="3" /></label><label>输入说明<textarea v-model="form.inputSummary" rows="3" /></label><label>输出说明<textarea v-model="form.outputSummary" rows="3" /></label></div></section>

            <section><div class="form-section-title"><span>03</span><div><b>{{ createType === 'PROMPT' ? 'Prompt 内容' : createType === 'TOOL' ? 'Tool 配置' : 'Skill 方法与依赖' }}</b><small>保存 Draft 前会重新校验配置与依赖权限。</small></div></div>
              <label v-if="createType === 'PROMPT'" class="wide code-field">System Prompt<textarea v-model="form.template" rows="12" /></label>
              <div v-else-if="createType === 'TOOL'" class="form-grid"><label>内置实现<select v-model="form.nativeName"><option value="current_time">current_time · 当前时间</option><option value="calculator">calculator · 计算器</option><option value="echo">echo · 回显测试</option></select></label><label>Tool Name<input v-model="form.toolName" /></label><label class="wide code-field">输入 JSON Schema<textarea v-model="form.inputSchema" rows="10" /></label></div>
              <div v-else class="skill-editor"><label class="wide code-field">SKILL.md<textarea v-model="form.skillMd" rows="14" /></label>
                <div class="dependency-section"><div><b>Tool 依赖</b><small>只显示当前身份拥有 USE 的已发布 Tool。</small></div><div class="dependency-grid"><label v-for="item in availableTools" :key="item.version_id" :class="{ selected: form.toolVersionIds.includes(item.version_id) }"><input type="checkbox" :checked="form.toolVersionIds.includes(item.version_id)" @change="toggleDependency('toolVersionIds', item.version_id)" /><span><b>{{ item.display_name }} · V{{ item.version_number }}</b><small>{{ item.one_line_summary || item.summary }}</small></span></label><p v-if="!availableTools.length">暂无可用 Tool。</p></div></div>
                <div class="dependency-section"><div><b>Knowledge 依赖</b><small>依赖仍然锁定具体 Published Version。</small></div><div class="dependency-grid"><label v-for="item in availableKnowledge" :key="item.version_id" :class="{ selected: form.knowledgeVersionIds.includes(item.version_id) }"><input type="checkbox" :checked="form.knowledgeVersionIds.includes(item.version_id)" @change="toggleDependency('knowledgeVersionIds', item.version_id)" /><span><b>{{ item.display_name }} · V{{ item.version_number }}</b><small>{{ item.one_line_summary || item.summary }}</small></span></label><p v-if="!availableKnowledge.length">暂无可用 Knowledge。</p></div></div>
              </div>
            </section>

            <section><div class="form-section-title"><span>04</span><div><b>{{ view === 'EDIT' ? '版本说明与风险' : '风险与发布范围' }}</b><small>{{ view === 'EDIT' ? '权限仍绑定逻辑资源，本次只产生新版本。' : '开发阶段先支持个人或责任部门范围。' }}</small></div></div><div class="form-grid"><label>风险等级<select v-model="form.riskLevel"><option value="LOW">低</option><option value="MEDIUM">中</option><option value="HIGH">高</option></select></label><label v-if="view === 'CREATE'">发布范围<select v-model="form.publicationScope"><option value="PERSONAL">仅我自己</option><option value="OWNER_DEPT" :disabled="!principal.dept_ids.length">责任部门可用</option></select></label><label class="check-row"><input v-model="form.readOnly" type="checkbox" />这是只读能力</label><label>标签<input v-model="form.tags" placeholder="制度, 人事, 查询" /></label></div></section>

            <footer v-if="view === 'CREATE'" class="editor-actions"><button class="secondary-action" @click="resetForm(createType)">清空</button><button class="primary-action dark" :disabled="saving" @click="createResource">{{ saving ? '发布中…' : `发布 ${typeLabel(createType)} V1` }}</button></footer>
            <footer v-else class="editor-actions version-actions"><div><b v-if="activeDraft">V{{ activeDraft.version_number }} 当前为草稿</b><b v-else>下一版本：V{{ editingVersionNumber }}</b><small>{{ activeDraft ? '可以反复保存，直到确认发布。' : '第一次保存会创建新的 Draft。' }}</small></div><button class="secondary-action" :disabled="saving || publishing" @click="saveDraft">{{ saving ? '保存中…' : activeDraft ? `更新 V${activeDraft.version_number} 草稿` : `保存为 V${editingVersionNumber} 草稿` }}</button><button class="primary-action dark" :disabled="!activeDraft || saving || publishing" @click="publishDraft">{{ publishing ? '发布中…' : activeDraft ? `发布 V${activeDraft.version_number}` : '先保存草稿' }}</button></footer>
          </div>
        </section>
      </template>
    </section>

    <div v-if="selected" class="resource-preview-backdrop" @click.self="selected = null"><aside class="resource-preview-panel"><button class="preview-close" @click="selected = null">×</button><p>{{ typeLabel(selected.resource_type) }} · {{ sourceLabel(selected.source_type) }} · V{{ selected.version_number }}</p><h2>{{ selected.display_name }}</h2><strong>{{ selected.one_line_summary || selected.description || selected.summary }}</strong><div class="preview-role"><b>在 Agent 中负责</b><span>{{ typeRole(selected.resource_type) }}</span></div><dl><dt>何时使用</dt><dd>{{ selected.when_to_use || '尚未填写' }}</dd><dt>何时不使用</dt><dd>{{ selected.when_not_to_use || '无额外限制' }}</dd><dt>输入</dt><dd>{{ selected.input_summary || '尚未填写' }}</dd><dt>输出</dt><dd>{{ selected.output_summary || '尚未填写' }}</dd><dt>风险</dt><dd>{{ selected.risk_level }} · {{ selected.read_only ? '只读' : '可写' }}</dd><dt>依赖</dt><dd>{{ selected.dependencies.length ? `${selected.dependencies.length} 项资源依赖` : '无直接依赖' }}</dd><dt>Owner</dt><dd>{{ selected.owner_user_id || '—' }}</dd></dl><div class="preview-ready">已发布版本不会因为后续编辑自动变化。</div><button v-if="selected.owner_user_id === principal.external_user_id" class="primary-action dark full" @click="openVersionEditor(selected)">编辑 / 新建版本</button></aside></div>
  </main>
</template>

<style scoped>
*{box-sizing:border-box}.developer-shell{min-height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr);background:#f7f8fb;color:#101828;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.developer-sidebar{position:sticky;top:0;height:100vh;padding:20px 16px;background:#111827;color:#fff;display:flex;flex-direction:column;gap:20px}.developer-brand,.developer-identity{display:flex;align-items:center;gap:11px}.developer-brand>span{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:#6d5dfc;font-weight:900}.developer-brand div,.developer-identity div{display:grid;gap:2px}.developer-brand small,.developer-identity small{color:#98a2b3;font-size:11px}.avatar{width:38px;height:38px;border-radius:50%;display:grid!important;place-items:center;background:#344054;font-weight:800}.developer-identity{padding:13px;border:1px solid #344054;border-radius:12px;background:#1d2939}.developer-sidebar nav{display:grid;gap:7px}.developer-sidebar nav button{display:grid;grid-template-columns:25px 1fr auto;align-items:center;gap:9px;width:100%;border:0;border-radius:11px;padding:12px;color:#d0d5dd;background:transparent;text-align:left;cursor:pointer}.developer-sidebar nav button.active{background:#312e81;color:#fff}.developer-sidebar nav button>span{color:#a5b4fc;font-size:11px;font-weight:800}.developer-sidebar nav button div{display:grid;gap:2px}.developer-sidebar nav button small{color:#98a2b3;font-size:11px}.developer-sidebar nav button em{min-width:24px;height:24px;border-radius:999px;display:grid;place-items:center;background:#344054;font-style:normal;font-size:11px}.developer-boundary{margin-top:auto;padding:13px;border:1px solid #344054;border-radius:12px;background:#1d2939}.developer-boundary p{margin:6px 0 0;color:#98a2b3;font-size:12px;line-height:1.55}.logout-button{border:1px solid #475467;border-radius:10px;padding:10px;color:#d0d5dd;background:transparent;cursor:pointer}.developer-content{min-width:0}.developer-topbar{height:66px;padding:0 28px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eaecf0;background:#fff}.developer-topbar div{display:grid;gap:2px}.developer-topbar span{color:#7f56d9;font-size:10px;font-weight:800;letter-spacing:.1em}.developer-topbar button{border:1px solid #d0d5dd;border-radius:8px;padding:8px 12px;background:#fff;cursor:pointer}.dev-message{margin:16px 28px 0;padding:11px 14px;border-radius:9px}.dev-message.error{background:#fef3f2;color:#b42318}.dev-message.success{background:#ecfdf3;color:#067647}.developer-hero{margin:26px 28px 18px;padding:26px;border-radius:18px;display:flex;justify-content:space-between;gap:20px;align-items:end;background:linear-gradient(135deg,#312e81,#5b4ee5);color:#fff}.developer-hero p{margin:0 0 6px;color:#c7d2fe;font-size:11px;font-weight:800;letter-spacing:.1em}.developer-hero h1{margin:0 0 7px;font-size:28px}.developer-hero span{color:#e0e7ff;line-height:1.55}.create-hero{align-items:start}.primary-action,.secondary-action{border:0;border-radius:10px;padding:11px 16px;font-weight:700;cursor:pointer}.primary-action{background:#fff;color:#4338ca}.primary-action.dark{background:#5b4ee5;color:#fff}.primary-action.full{width:100%;margin-top:14px}.secondary-action{background:#f2f4f7;color:#344054}.primary-action:disabled,.secondary-action:disabled{opacity:.5;cursor:default}.resource-stats{margin:0 28px 18px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.resource-stats article{padding:16px;border:1px solid #e4e7ec;border-radius:14px;background:#fff;display:grid;gap:3px}.resource-stats small,.resource-stats span{color:#667085}.resource-stats b{font-size:24px}.developer-filters{margin:0 28px 16px;padding:12px;display:grid;grid-template-columns:minmax(0,1fr) 170px;gap:10px;border:1px solid #e4e7ec;border-radius:13px;background:#fff}.developer-filters input,.developer-filters select,.editor-form input,.editor-form select,.editor-form textarea{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:9px 10px;background:#fff;color:#101828;font:inherit}.editor-form textarea{resize:vertical;line-height:1.55}.developer-resource-grid{margin:0 28px 32px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.developer-resource-card{min-height:290px;padding:17px;border:1px solid #e4e7ec;border-radius:15px;background:#fff;display:grid;align-content:start;gap:10px}.developer-resource-card:hover{border-color:#a4a0f7;box-shadow:0 8px 24px rgba(16,24,40,.07)}.developer-resource-card header,.developer-resource-card footer{display:flex;justify-content:space-between;gap:8px;align-items:center}.developer-resource-card header span{padding:4px 8px;border-radius:999px;background:#eeebff;color:#5145cd;font-size:11px;font-weight:800}.developer-resource-card header em{color:#667085;font-size:11px;font-style:normal}.developer-resource-card h3,.developer-resource-card p{margin:0}.developer-resource-card p{color:#344054;line-height:1.5}.resource-role{padding:9px;border-radius:9px;background:#f9fafb;display:grid;gap:3px;font-size:12px}.resource-role span,.developer-resource-card>small{color:#667085;line-height:1.45}.version-line{display:flex;gap:8px;align-items:center;padding-top:8px;color:#667085;font-size:11px}.version-line b{color:#344054}.developer-resource-card footer{margin-top:auto;padding-top:10px;border-top:1px solid #f2f4f7}.developer-resource-card footer button{border:0;background:transparent;color:#475467;font-weight:700;cursor:pointer}.developer-resource-card footer .edit-button{color:#5b4ee5}.developer-resource-card footer strong{color:#067647;font-size:11px}.empty-state{grid-column:1/-1;padding:40px;text-align:center;color:#667085}.create-type-switch{margin:0 28px 16px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.create-type-switch button{padding:15px;border:1px solid #e4e7ec;border-radius:13px;background:#fff;text-align:left;display:grid;gap:4px;cursor:pointer}.create-type-switch button.active{border-color:#6958e8;background:#f5f3ff}.create-type-switch span{color:#667085;font-size:12px}.resource-editor{margin:0 28px 36px;display:grid;grid-template-columns:240px minmax(0,1fr);gap:16px;align-items:start}.editor-guide{position:sticky;top:82px;padding:18px;border:1px solid #e4e7ec;border-radius:15px;background:#fff}.editor-guide>p{margin:0;color:#7f56d9;font-size:10px;font-weight:800;letter-spacing:.08em}.editor-guide h3{margin:5px 0}.editor-guide>strong{display:block;color:#475467;font-size:13px;line-height:1.5}.editor-guide ol{padding-left:20px;color:#667085;line-height:1.9;font-size:13px}.version-safety{margin-top:14px;padding:11px;border-radius:10px;background:#eef4ff;color:#3538cd}.version-safety p{margin:5px 0 0;font-size:12px;line-height:1.5}.version-history{margin-top:14px;display:grid;gap:8px}.version-history article{padding:10px;border:1px solid #eaecf0;border-radius:10px;display:grid;gap:5px}.version-history article div{display:flex;justify-content:space-between;align-items:center}.version-history span{font-size:10px;padding:3px 7px;border-radius:999px}.version-history span.draft{background:#fffaeb;color:#b54708}.version-history span.published{background:#ecfdf3;color:#067647}.version-history small{color:#667085}.version-history code{font-size:10px;color:#98a2b3}.editor-form{display:grid;gap:14px}.editor-form>section{padding:20px;border:1px solid #e4e7ec;border-radius:15px;background:#fff}.form-section-title{display:flex;gap:10px;align-items:start;margin-bottom:15px}.form-section-title>span{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;background:#eeebff;color:#5145cd;font-size:11px;font-weight:800}.form-section-title div{display:grid;gap:2px}.form-section-title small{color:#667085}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.editor-form label{display:grid;gap:6px;font-size:13px;font-weight:700}.wide{grid-column:1/-1}.inline-field{margin-top:12px}.code-field textarea{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.check-row{display:flex!important;align-items:center;gap:8px}.check-row input{width:auto}.identity-lock{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.identity-lock span{padding:11px;border-radius:10px;background:#f9fafb;display:grid;gap:3px}.identity-lock small{color:#667085}.skill-editor{display:grid;gap:14px}.dependency-section{display:grid;gap:8px}.dependency-section>div:first-child{display:grid;gap:2px}.dependency-section small{color:#667085}.dependency-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.dependency-grid label{display:flex;align-items:start;gap:8px;padding:10px;border:1px solid #e4e7ec;border-radius:10px;cursor:pointer}.dependency-grid label.selected{border-color:#6958e8;background:#f5f3ff}.dependency-grid input{width:auto;margin-top:2px}.dependency-grid span{display:grid;gap:3px}.editor-actions{padding:15px 18px;border:1px solid #e4e7ec;border-radius:14px;background:#fff;display:flex;justify-content:flex-end;gap:10px;align-items:center}.version-actions>div{margin-right:auto;display:grid;gap:3px}.version-actions small{color:#667085}.resource-preview-backdrop{position:fixed;inset:0;z-index:100;background:rgba(16,24,40,.45);display:flex;justify-content:flex-end}.resource-preview-panel{width:min(440px,92vw);height:100%;padding:26px;background:#fff;overflow:auto}.preview-close{float:right;border:0;background:transparent;font-size:24px;cursor:pointer}.resource-preview-panel>p{color:#7f56d9;font-size:11px;font-weight:800}.resource-preview-panel h2{margin:7px 0}.resource-preview-panel>strong{display:block;line-height:1.55}.preview-role{margin:16px 0;padding:12px;border-radius:10px;background:#f9fafb;display:grid;gap:4px}.resource-preview-panel dl{display:grid;grid-template-columns:90px 1fr;gap:10px 12px}.resource-preview-panel dt{color:#667085}.resource-preview-panel dd{margin:0}.preview-ready{margin-top:16px;padding:11px;border-radius:10px;background:#ecfdf3;color:#067647}@media(max-width:1100px){.developer-resource-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.resource-editor{grid-template-columns:1fr}.editor-guide{position:static}.resource-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.developer-shell{grid-template-columns:1fr}.developer-sidebar{position:static;height:auto}.developer-resource-grid,.resource-stats,.create-type-switch,.form-grid,.dependency-grid,.identity-lock{grid-template-columns:1fr}.developer-filters{grid-template-columns:1fr}.developer-hero{align-items:start;flex-direction:column}.resource-editor,.developer-resource-grid,.developer-filters,.resource-stats,.developer-hero,.create-type-switch{margin-left:14px;margin-right:14px}.version-actions{align-items:stretch;flex-direction:column}.version-actions>div{margin-right:0}}
</style>
