<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CatalogItem, ConfigurationValidation } from '../api'

const props = defineProps<{
  catalog: CatalogItem[]
  specification: Record<string, unknown>
  validation: ConfigurationValidation | null
  publishing: boolean
}>()
const emit = defineEmits<{
  single: [field: string, value: string]
  many: [field: string, value: string]
  replace: [field: string, fromVersionId: string, toVersionId: string]
  preflight: []
  publish: []
}>()

type ModuleKey = 'IDENTITY' | 'SKILL_TOOL' | 'KNOWLEDGE_MEMORY'
const activeModule = ref<ModuleKey>('IDENTITY')
const search = ref('')
const provider = ref('ALL')
const risk = ref('ALL')
const preview = ref<CatalogItem | null>(null)
const validationDirty = ref(false)

watch(() => props.validation, (value, previous) => {
  if (value && value !== previous) validationDirty.value = false
})
function markDirty() { validationDirty.value = true }
function requestPreflight() { emit('preflight') }

const modules: Array<{ key: ModuleKey; title: string; description: string; question: string; types: string[] }> = [
  { key: 'IDENTITY', title: '模型与规则', description: '决定谁来思考，以及回答必须遵守什么规则', question: '这个 Agent 如何思考和回答？', types: ['MODEL', 'PROMPT'] },
  { key: 'SKILL_TOOL', title: '业务能力', description: '优先选择 Skill；需要独立动作时再添加 Tool', question: '这个 Agent 能完成哪些业务任务？', types: ['SKILL', 'TOOL'] },
  { key: 'KNOWLEDGE_MEMORY', title: '知识与记忆', description: '决定它可以查什么资料，以及跨会话记住什么', question: '这个 Agent 依据什么、记住什么？', types: ['KNOWLEDGE', 'MEMORY_POLICY'] },
]
const singleField: Record<string, string> = { MODEL: 'model_version_id', PROMPT: 'prompt_version_id', MEMORY_POLICY: 'memory_policy_version_id' }
const multipleField: Record<string, string> = { SKILL: 'skill_version_ids', TOOL: 'tool_version_ids', KNOWLEDGE: 'knowledge_version_ids' }
const fieldFor = (type: string) => singleField[type] || multipleField[type] || ''
const single = (field: string) => String(props.specification[field] || '')
const many = (field: string) => (props.specification[field] as string[] || [])

function selected(item: CatalogItem) {
  const field = fieldFor(item.resource_type)
  if (!field) return false
  return field.endsWith('_ids') ? many(field).includes(item.version_id) : single(field) === item.version_id
}
const versionsByResource = computed(() => {
  const groups = new Map<string, CatalogItem[]>()
  for (const item of props.catalog) {
    const list = groups.get(item.resource_id) || []
    list.push(item)
    groups.set(item.resource_id, list)
  }
  for (const list of groups.values()) list.sort((a, b) => b.version_number - a.version_number)
  return groups
})
function versions(item: CatalogItem) { return versionsByResource.value.get(item.resource_id) || [item] }
function latestVersion(item: CatalogItem) { return versions(item)[0] || item }
function selectedVersion(item: CatalogItem) { return versions(item).find(selected) || null }
function displayedVersion(item: CatalogItem) { return selectedVersion(item) || latestVersion(item) }
function hasUpgrade(item: CatalogItem) {
  const current = selectedVersion(item)
  return Boolean(current && latestVersion(item).version_number > current.version_number)
}
function upgradeCountForModule(types: string[]) {
  return [...versionsByResource.value.values()].filter(group => {
    const current = group.find(selected)
    return current && types.includes(current.resource_type) && group[0].version_number > current.version_number
  }).length
}

const logicalCapabilities = computed(() => [...versionsByResource.value.values()].map(group => group.find(selected) || group[0]))
const currentModule = computed(() => modules.find(item => item.key === activeModule.value) || modules[0])
const sourceOptions = computed(() => [...new Set(logicalCapabilities.value.filter(item => currentModule.value.types.includes(item.resource_type)).map(item => item.source_type).filter(Boolean))])
const visibleCapabilities = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return logicalCapabilities.value.filter(item => {
    if (!currentModule.value.types.includes(item.resource_type)) return false
    if (provider.value !== 'ALL' && item.source_type !== provider.value) return false
    if (risk.value !== 'ALL' && item.risk_level !== risk.value) return false
    return !needle || `${item.display_name} ${item.description || ''} ${item.one_line_summary || ''} ${item.when_to_use || ''}`.toLowerCase().includes(needle)
  })
})

function chooseVersion(item: CatalogItem, target: CatalogItem) {
  const field = fieldFor(item.resource_type)
  if (!field) return
  const current = selectedVersion(item)
  if (current?.version_id === target.version_id) return
  if (current) emit('replace', field, current.version_id, target.version_id)
  else if (field.endsWith('_ids')) emit('many', field, target.version_id)
  else emit('single', field, target.version_id)
  preview.value = target
  markDirty()
}
function toggle(item: CatalogItem) {
  const current = selectedVersion(item)
  const field = fieldFor(item.resource_type)
  if (!field) return
  if (current) {
    if (field.endsWith('_ids')) emit('many', field, current.version_id)
    else emit('single', field, '')
  } else {
    const target = latestVersion(item)
    if (field.endsWith('_ids')) emit('many', field, target.version_id)
    else emit('single', field, target.version_id)
  }
  markDirty()
}
function upgrade(item: CatalogItem) {
  const current = selectedVersion(item)
  const latest = latestVersion(item)
  const field = fieldFor(item.resource_type)
  if (current && field && latest.version_number > current.version_number) {
    emit('replace', field, current.version_id, latest.version_id)
    markDirty()
  }
}

const selectedCapabilities = computed(() => props.catalog.filter(selected))
const indirectCapabilities = computed(() => (props.validation?.resolved_capabilities || []).filter(item => item.origin !== 'DIRECT'))
const moduleCount = (item: typeof modules[number]) => selectedCapabilities.value.filter(capability => item.types.includes(capability.resource_type)).length
const capabilitySummary = (item: CatalogItem) => item.one_line_summary || item.description || item.summary || '尚未填写业务说明'
const usageSummary = (item: CatalogItem) => item.when_to_use || '适用场景尚未补充'
const semanticReady = (item: CatalogItem) => Boolean(item.one_line_summary && item.when_to_use && item.input_summary && item.output_summary)
const typeLabel = (type: string) => ({ MODEL: '模型', PROMPT: 'Prompt', SKILL: 'Skill', TOOL: 'Tool', KNOWLEDGE: '知识库', MEMORY_POLICY: 'Memory' } as Record<string, string>)[type] || type
const resourceRole = (type: string) => ({ MODEL: '推理核心：理解问题、决策和选择工具。', PROMPT: '行为规则：定义角色、回答边界和业务约束。', SKILL: '业务能力包：描述任务方法，并锁定 Tool / Knowledge 的具体版本。', TOOL: '可执行动作：查询系统、调用接口或执行确定性操作。', KNOWLEDGE: '检索依据：提供可查询的业务知识和文档。', MEMORY_POLICY: '长期记忆：决定跨会话记住哪些信息。' } as Record<string, string>)[type] || 'Agent 可复用能力。'
const sourceLabel = (source: string) => ({ PLATFORM_NATIVE: '平台原生', OPENAI_COMPATIBLE: '模型服务', MCP: 'MCP', DIFY: 'Dify', HTTP: 'HTTP API', RAGFLOW: 'RAGFlow', LOCAL: '平台知识库' } as Record<string, string>)[source] || source
const shortHash = (value: string) => value.slice(0, 10)
function dependencyLabel(versionId: string) {
  const found = props.catalog.find(item => item.version_id === versionId)
  return found ? `${found.display_name} · V${found.version_number}` : `${versionId.slice(0, 8)}…`
}
function dependencyDiff(item: CatalogItem) {
  const current = selectedVersion(item) || item
  const latest = latestVersion(item)
  const before = new Set(current.dependencies)
  const after = new Set(latest.dependencies)
  return { added: latest.dependencies.filter(id => !before.has(id)).map(dependencyLabel), removed: current.dependencies.filter(id => !after.has(id)).map(dependencyLabel) }
}
const previewVersions = computed(() => preview.value ? versions(preview.value) : [])
const previewCurrent = computed(() => preview.value ? selectedVersion(preview.value) : null)
const previewLatest = computed(() => preview.value ? latestVersion(preview.value) : null)
const previewDiff = computed(() => preview.value ? dependencyDiff(preview.value) : { added: [], removed: [] })
</script>

<template>
  <div class="assembly-workbench">
    <aside class="assembly-tree">
      <div class="tree-title"><p>AGENT STRUCTURE</p><h3>智能体结构</h3><small>按“思考 → 做事 → 获取上下文”组装；资源升级不会自动改变当前草稿。</small></div>
      <button v-for="item in modules" :key="item.key" :class="{ active: activeModule === item.key }" @click="activeModule = item.key; preview = null"><span>{{ String(modules.indexOf(item) + 1).padStart(2, '0') }}</span><div><b>{{ item.title }}</b><small>{{ item.description }}</small></div><em>{{ moduleCount(item) }}</em><i v-if="upgradeCountForModule(item.types)">{{ upgradeCountForModule(item.types) }} 更新</i></button>
      <div class="version-rule"><b>版本规则</b><p>Agent 保存 Resource Version ID。新版本发布后这里只提示，不会自动替换。</p></div>
      <div class="legacy-note" v-if="(specification.mcp_connection_version_ids as string[] || []).length"><b>历史连接引用</b><p>新配置不要直接选 MCP Connection，应选择发现并发布后的 Tool。</p></div>
    </aside>

    <section class="capability-picker">
      <header><div><p>CAPABILITY PICKER</p><h3>{{ currentModule.title }}</h3><strong class="module-question">{{ currentModule.question }}</strong><span>{{ currentModule.description }}</span></div><div class="picker-filters"><input v-model="search" placeholder="搜索名称、用途或适用场景" /><select v-model="provider"><option value="ALL">全部来源</option><option v-for="item in sourceOptions" :key="item" :value="item">{{ sourceLabel(item) }}</option></select><select v-model="risk"><option value="ALL">全部风险</option><option value="LOW">低风险</option><option value="MEDIUM">中风险</option><option value="HIGH">高风险</option></select></div></header>
      <div class="capability-grid">
        <article v-for="item in visibleCapabilities" :key="item.resource_id" :class="['capability-card', { selected: Boolean(selectedVersion(item)), incomplete: !semanticReady(item), outdated: hasUpgrade(item) }]">
          <div class="card-heading"><span>{{ typeLabel(item.resource_type) }}</span><em>{{ sourceLabel(item.source_type) }}</em></div>
          <div v-if="hasUpgrade(item)" class="upgrade-banner"><b>当前锁定 V{{ selectedVersion(item)?.version_number }}</b><span>最新 V{{ latestVersion(item).version_number }} 可用</span></div>
          <h4>{{ item.display_name }}</h4><p>{{ capabilitySummary(item) }}</p><div class="agent-role"><b>在 Agent 中</b><span>{{ resourceRole(item.resource_type) }}</span></div><small>适用：{{ usageSummary(item) }}</small>
          <small v-if="item.resource_type === 'SKILL' && item.dependencies.length" class="dependency-note">当前显示版本锁定 {{ item.dependencies.length }} 项 Tool / Knowledge 依赖。</small><small v-if="!semanticReady(item)" class="semantic-warning">业务说明不完整，建议先查看详情再添加。</small>
          <div class="card-meta"><span>{{ selectedVersion(item) ? `已选 V${selectedVersion(item)?.version_number}` : `最新 V${latestVersion(item).version_number}` }}</span><span>{{ item.risk_level }} 风险</span><span>{{ item.health }}</span></div>
          <footer><button class="preview-button" @click="preview = displayedVersion(item)">版本与详情</button><button v-if="hasUpgrade(item)" class="upgrade-button" @click="upgrade(item)">升级到 V{{ latestVersion(item).version_number }}</button><button class="select-button" @click="toggle(item)">{{ selectedVersion(item) ? '从 Agent 移除' : `添加 V${latestVersion(item).version_number}` }}</button></footer>
        </article>
        <p v-if="!visibleCapabilities.length" class="empty-result">没有符合条件、且当前账号有 USE 权限的已发布能力。</p>
      </div>

      <article v-if="preview" class="capability-preview">
        <button aria-label="关闭预览" @click="preview = null">×</button><p>{{ typeLabel(preview.resource_type) }} · {{ sourceLabel(preview.source_type) }}</p><h3>{{ preview.display_name }}</h3><strong>{{ capabilitySummary(preview) }}</strong><div class="preview-role"><b>它在 Agent 里负责什么？</b><span>{{ resourceRole(preview.resource_type) }}</span></div>
        <section class="version-awareness"><header><div><b>版本选择</b><small>显式选择 Published Version；不会自动漂移。</small></div><span v-if="previewCurrent">Agent 当前 V{{ previewCurrent.version_number }}</span><span v-else>尚未加入 Agent</span></header><div class="version-options"><button v-for="version in previewVersions" :key="version.version_id" :class="{ active: previewCurrent?.version_id === version.version_id, latest: previewLatest?.version_id === version.version_id }" @click="chooseVersion(preview, version)"><b>V{{ version.version_number }}</b><span>{{ previewCurrent?.version_id === version.version_id ? '当前锁定' : previewLatest?.version_id === version.version_id ? '最新发布' : '历史版本' }}</span><code>{{ shortHash(version.content_hash) }}</code></button></div><div v-if="previewCurrent && previewLatest && previewCurrent.version_id !== previewLatest.version_id" class="version-diff"><div><b>V{{ previewCurrent.version_number }} → V{{ previewLatest.version_number }}</b><span>内容哈希已变化</span></div><template v-if="preview.resource_type === 'SKILL'"><p v-if="previewDiff.added.length"><b>新增依赖：</b>{{ previewDiff.added.join('；') }}</p><p v-if="previewDiff.removed.length"><b>移除依赖：</b>{{ previewDiff.removed.join('；') }}</p><p v-if="!previewDiff.added.length && !previewDiff.removed.length">Skill 的依赖版本集合未变化；业务指令或其他内容可能已更新。</p></template></div></section>
        <dl><dt>当前查看</dt><dd>V{{ preview.version_number }} · {{ shortHash(preview.content_hash) }}</dd><dt>何时使用</dt><dd>{{ preview.when_to_use || '尚未说明' }}</dd><dt>何时不使用</dt><dd>{{ preview.when_not_to_use || '无额外限制' }}</dd><dt>输入</dt><dd>{{ preview.input_summary || '尚未说明' }}</dd><dt>输出</dt><dd>{{ preview.output_summary || '尚未说明' }}</dd><dt>依赖</dt><dd>{{ preview.dependencies.length ? preview.dependencies.map(dependencyLabel).join('；') : '无依赖' }}</dd><dt>风险</dt><dd>{{ preview.risk_level }} · {{ preview.read_only ? '只读' : '可能产生写操作' }}</dd></dl>
      </article>
    </section>

    <aside class="assembly-summary-panel">
      <div><p>CURRENT ASSEMBLY</p><h3>这个 Agent 现在会什么</h3><span>{{ selectedCapabilities.length }} 项直接选择的能力</span></div>
      <section v-for="item in modules" :key="item.key"><b>{{ item.title }} · {{ moduleCount(item) }}</b><article v-for="capability in selectedCapabilities.filter(value => item.types.includes(value.resource_type))" :key="capability.version_id" class="selected-capability-summary"><div><span>{{ capability.display_name }} <small>V{{ capability.version_number }}</small></span><button v-if="hasUpgrade(capability)" @click="upgrade(capability)">有 V{{ latestVersion(capability).version_number }} · 升级</button></div><p>{{ capabilitySummary(capability) }}</p></article></section>
      <p v-if="!selectedCapabilities.length" class="summary-empty">尚未选择能力。建议先选择一个 Model 和 Prompt，再按业务任务添加 Skill。</p>
      <section v-if="indirectCapabilities.length" class="resolved-dependencies"><b>Skill 自动带入 · {{ indirectCapabilities.length }}</b><span v-for="item in indirectCapabilities" :key="`${item.version_id}-${item.origin}`">{{ item.display_name }} <small>{{ typeLabel(item.resource_type) }}</small></span><p>这些资源由 Skill 依赖自动解析；预检会检查具体版本、发布状态和 USE 权限。</p></section>
      <div v-if="validationDirty" class="validation-result stale"><b>配置已变化，需要重新预检</b><p>资源添加、移除或版本切换后，之前的预检结果不再有效。</p></div>
      <div v-else-if="validation" :class="['validation-result', validation.valid ? 'ok' : 'blocked']"><b>{{ validation.valid ? '预检通过，可以发布' : '当前 Agent 还不能发布' }}</b><p v-for="issue in validation.blocking_errors" :key="issue.code">{{ issue.message }}</p><p v-for="issue in validation.warnings" :key="issue.code">{{ issue.message }}</p></div>
      <div class="publish-actions"><button class="preflight-button" @click="requestPreflight">检查依赖与权限</button><button class="publish-button" :disabled="validationDirty || !validation?.valid || publishing" @click="emit('publish')">{{ publishing ? '发布中…' : '发布当前 Agent' }}</button></div>
    </aside>
  </div>
</template>

<style scoped>
.assembly-workbench{display:grid;grid-template-columns:230px minmax(0,1fr) 310px;gap:16px;align-items:start}.assembly-tree,.capability-picker,.assembly-summary-panel{border:1px solid #e4e7ec;border-radius:16px;background:#fff}.assembly-tree,.assembly-summary-panel{padding:16px;display:grid;gap:10px;position:sticky;top:16px}.tree-title p,.capability-picker header p,.assembly-summary-panel>div>p{margin:0;color:#6958e8;font-size:11px;font-weight:800;letter-spacing:.09em}.tree-title h3,.capability-picker h3,.assembly-summary-panel h3{margin:4px 0}.tree-title small{color:#667085;line-height:1.45}.assembly-tree>button{position:relative;display:grid;grid-template-columns:28px 1fr auto;gap:9px;align-items:center;width:100%;padding:12px;text-align:left;border:1px solid transparent;border-radius:12px;background:transparent;cursor:pointer}.assembly-tree>button.active{border-color:#c7bfff;background:#f4f2ff}.assembly-tree>button>span{color:#6958e8;font-size:12px;font-weight:800}.assembly-tree button div{display:grid;gap:3px}.assembly-tree small{color:#667085;line-height:1.35}.assembly-tree em{display:grid;place-items:center;min-width:24px;height:24px;border-radius:999px;color:#5145cd;background:#eeebff;font-style:normal;font-weight:700}.assembly-tree i{position:absolute;right:8px;top:-7px;padding:2px 6px;border-radius:999px;background:#fff4ed;color:#b93815;font-size:9px;font-style:normal;font-weight:800}.version-rule,.legacy-note{padding:12px;border-radius:12px;font-size:12px}.version-rule{background:#f5f3ff;color:#42307d}.legacy-note{background:#fffaeb;color:#7a2e0e}.version-rule p,.legacy-note p{margin:5px 0 0;line-height:1.5}.capability-picker{min-height:600px;overflow:hidden}.capability-picker>header{padding:18px;border-bottom:1px solid #eaecf0}.capability-picker header span,.assembly-summary-panel>div>span{color:#667085}.module-question{display:block;margin:8px 0 3px;color:#1d2939}.picker-filters{display:grid;grid-template-columns:minmax(180px,1fr) 140px 120px;gap:8px;margin-top:14px}.picker-filters input,.picker-filters select{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:9px;background:#fff}.capability-grid{padding:16px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.capability-card{min-height:315px;padding:15px;border:1px solid #e4e7ec;border-radius:14px;display:grid;align-content:start;gap:9px}.capability-card.selected{border-color:#8b7cf6;background:#fbfaff}.capability-card.outdated{box-shadow:inset 0 3px #f79009}.capability-card.incomplete{border-style:dashed}.card-heading{display:flex;justify-content:space-between}.card-heading span{padding:4px 8px;border-radius:999px;background:#eeebff;color:#5145cd;font-size:10px;font-weight:800}.card-heading em{color:#667085;font-size:10px;font-style:normal}.capability-card h4,.capability-card p{margin:0}.capability-card>p{color:#344054;line-height:1.45}.agent-role{padding:9px;border-radius:9px;background:#f9fafb;display:grid;gap:2px;font-size:11px}.agent-role span,.capability-card>small{color:#667085;line-height:1.45}.dependency-note{color:#6941c6!important}.semantic-warning{color:#b54708!important}.upgrade-banner{padding:8px 10px;border-radius:9px;background:#fffaeb;display:flex;justify-content:space-between;gap:8px;color:#b54708;font-size:11px}.card-meta{display:flex;gap:6px;flex-wrap:wrap}.card-meta span{padding:3px 6px;border-radius:6px;background:#f2f4f7;color:#475467;font-size:10px}.capability-card footer{margin-top:auto;display:flex;gap:7px;flex-wrap:wrap}.capability-card footer button{border:0;border-radius:8px;padding:8px 10px;font-weight:700;cursor:pointer}.preview-button{background:#f2f4f7;color:#344054}.select-button{background:#5b4ee5;color:#fff}.upgrade-button{background:#fff4ed;color:#b93815}.empty-result{grid-column:1/-1;padding:40px;text-align:center;color:#667085}.capability-preview{margin:0 16px 16px;padding:18px;border:1px solid #d6d1ff;border-radius:14px;background:#faf9ff;position:relative}.capability-preview>button{position:absolute;right:12px;top:10px;border:0;background:transparent;font-size:22px;cursor:pointer}.capability-preview>p{margin:0;color:#6941c6;font-size:11px}.capability-preview h3{margin:5px 0}.capability-preview>strong{display:block;color:#344054}.preview-role{margin:12px 0;padding:10px;border-radius:10px;background:#fff;display:grid;gap:3px}.preview-role span{color:#667085}.capability-preview dl{display:grid;grid-template-columns:95px 1fr;gap:7px;margin-bottom:0}.capability-preview dt{color:#667085;font-size:12px}.capability-preview dd{margin:0;font-size:12px;line-height:1.5}.version-awareness{margin:14px 0;padding:12px;border:1px solid #e4e7ec;border-radius:12px;background:#fff}.version-awareness>header{display:flex;justify-content:space-between;gap:10px;align-items:start}.version-awareness>header div{display:grid;gap:2px}.version-awareness>header small{color:#667085}.version-awareness>header>span{padding:4px 7px;border-radius:999px;background:#f2f4f7;font-size:10px}.version-options{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.version-options button{min-width:92px;padding:8px;border:1px solid #e4e7ec;border-radius:9px;background:#fff;display:grid;gap:2px;text-align:left;cursor:pointer}.version-options button.latest{border-color:#a6f4c5}.version-options button.active{border-color:#7f56d9;background:#f4f2ff}.version-options span,.version-options code{color:#667085;font-size:9px}.version-diff{margin-top:10px;padding:10px;border-radius:9px;background:#fffaeb;color:#7a2e0e;font-size:11px}.version-diff>div{display:flex;justify-content:space-between}.version-diff p{margin:6px 0 0;line-height:1.5}.assembly-summary-panel>section{padding:10px 0;border-top:1px solid #eaecf0}.selected-capability-summary{padding:8px 0}.selected-capability-summary>div{display:flex;justify-content:space-between;gap:8px}.selected-capability-summary span{font-weight:700}.selected-capability-summary small{color:#667085}.selected-capability-summary button{border:0;border-radius:7px;padding:4px 7px;background:#fff4ed;color:#b93815;font-size:9px;font-weight:800;cursor:pointer}.selected-capability-summary p{margin:3px 0;color:#667085;font-size:11px;line-height:1.4}.summary-empty{color:#667085;font-size:12px}.resolved-dependencies{display:grid;gap:5px}.resolved-dependencies>span{font-size:11px}.resolved-dependencies p{margin:3px 0;color:#667085;font-size:10px;line-height:1.45}.validation-result{padding:11px;border-radius:10px}.validation-result.ok{background:#ecfdf3;color:#067647}.validation-result.blocked{background:#fef3f2;color:#b42318}.validation-result.stale{background:#fffaeb;color:#b54708}.validation-result p{margin:5px 0;font-size:11px}.publish-actions{display:grid;gap:8px}.publish-actions button{border:0;border-radius:9px;padding:10px;font-weight:800;cursor:pointer}.preflight-button{background:#f2f4f7;color:#344054}.publish-button{background:#5b4ee5;color:#fff}.publish-button:disabled{opacity:.45;cursor:default}@media(max-width:1200px){.assembly-workbench{grid-template-columns:210px minmax(0,1fr)}.assembly-summary-panel{grid-column:1/-1;position:static}.capability-grid{grid-template-columns:1fr}}@media(max-width:800px){.assembly-workbench{grid-template-columns:1fr}.assembly-tree{position:static}.picker-filters{grid-template-columns:1fr}.capability-grid{grid-template-columns:1fr}}
</style>
