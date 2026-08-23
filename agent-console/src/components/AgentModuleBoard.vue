<script setup lang="ts">
import { computed, ref } from 'vue'
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
  preflight: []
  publish: []
}>()

type ModuleKey = 'IDENTITY' | 'SKILL_TOOL' | 'KNOWLEDGE_MEMORY'

const activeModule = ref<ModuleKey>('IDENTITY')
const search = ref('')
const provider = ref('ALL')
const risk = ref('ALL')
const preview = ref<CatalogItem | null>(null)

const modules: Array<{ key: ModuleKey; title: string; description: string; types: string[] }> = [
  { key: 'IDENTITY', title: '模型与身份', description: '推理模型、角色和回答边界', types: ['MODEL', 'PROMPT'] },
  { key: 'SKILL_TOOL', title: '技能与工具', description: 'Skill、Native、Dify、MCP Tool', types: ['SKILL', 'TOOL'] },
  { key: 'KNOWLEDGE_MEMORY', title: '知识与记忆', description: '知识检索与长期记忆策略', types: ['KNOWLEDGE', 'MEMORY_POLICY'] },
]

const currentModule = computed(() => modules.find(item => item.key === activeModule.value) || modules[0])
const sourceOptions = computed(() => [...new Set(props.catalog
  .filter(item => currentModule.value.types.includes(item.resource_type))
  .map(item => item.source_type).filter(Boolean))])
const visibleCapabilities = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return props.catalog.filter(item => {
    if (!currentModule.value.types.includes(item.resource_type)) return false
    if (provider.value !== 'ALL' && item.source_type !== provider.value) return false
    if (risk.value !== 'ALL' && item.risk_level !== risk.value) return false
    if (!needle) return true
    return `${item.display_name} ${item.description || ''} ${item.one_line_summary || ''} ${item.when_to_use || ''}`.toLowerCase().includes(needle)
  })
})

const singleField: Record<string, string> = {
  MODEL: 'model_version_id', PROMPT: 'prompt_version_id', MEMORY_POLICY: 'memory_policy_version_id',
}
const multipleField: Record<string, string> = {
  SKILL: 'skill_version_ids', TOOL: 'tool_version_ids', KNOWLEDGE: 'knowledge_version_ids',
}
const single = (field: string) => String(props.specification[field] || '')
const many = (field: string) => (props.specification[field] as string[] || [])
function selected(item: CatalogItem) {
  const field = singleField[item.resource_type] || multipleField[item.resource_type]
  return field.endsWith('_ids') ? many(field).includes(item.version_id) : single(field) === item.version_id
}
function toggle(item: CatalogItem) {
  const field = singleField[item.resource_type] || multipleField[item.resource_type]
  if (field.endsWith('_ids')) emit('many', field, item.version_id)
  else emit('single', field, selected(item) ? '' : item.version_id)
}

const selectedCapabilities = computed(() => props.catalog.filter(selected))
const moduleCount = (item: typeof modules[number]) => selectedCapabilities.value.filter(capability => item.types.includes(capability.resource_type)).length
const capabilitySummary = (item: CatalogItem) => item.one_line_summary || item.description || item.summary
const usageSummary = (item: CatalogItem) => item.when_to_use || '适用场景尚未补充'
const typeLabel = (type: string) => ({ MODEL: '模型', PROMPT: '提示词', SKILL: '技能', TOOL: '工具', KNOWLEDGE: '知识库', MEMORY_POLICY: '记忆策略' } as Record<string, string>)[type] || type
</script>

<template>
  <div class="assembly-workbench">
    <aside class="assembly-tree">
      <div class="tree-title"><p>AGENT STRUCTURE</p><h3>智能体结构</h3></div>
      <button v-for="item in modules" :key="item.key" :class="{ active: activeModule === item.key }" @click="activeModule = item.key; preview = null">
        <span>{{ String(modules.indexOf(item) + 1).padStart(2, '0') }}</span>
        <div><b>{{ item.title }}</b><small>{{ item.description }}</small></div>
        <em>{{ moduleCount(item) }}</em>
      </button>
      <div class="legacy-note" v-if="(specification.mcp_connection_version_ids as string[] || []).length">
        <b>历史连接引用</b>
        <p>当前版本仍有 MCP Connection 直连。新配置应选择发现后发布的 MCP Tool。</p>
      </div>
    </aside>

    <section class="capability-picker">
      <header>
        <div><p>CAPABILITY PICKER</p><h3>{{ currentModule.title }}</h3><span>{{ currentModule.description }}</span></div>
        <div class="picker-filters">
          <input v-model="search" placeholder="搜索名称、用途或场景" />
          <select v-model="provider"><option value="ALL">全部来源</option><option v-for="item in sourceOptions" :key="item" :value="item">{{ item }}</option></select>
          <select v-model="risk"><option value="ALL">全部风险</option><option value="LOW">低风险</option><option value="MEDIUM">中风险</option><option value="HIGH">高风险</option></select>
        </div>
      </header>
      <div class="capability-grid">
        <article v-for="item in visibleCapabilities" :key="item.version_id" :class="['capability-card', { selected: selected(item) }]">
          <div class="card-heading"><span>{{ typeLabel(item.resource_type) }}</span><em>{{ item.source_type }}</em></div>
          <h4>{{ item.display_name }}</h4>
          <p>{{ capabilitySummary(item) }}</p>
          <small>适用：{{ usageSummary(item) }}</small>
          <div class="card-meta"><span>V{{ item.version_number }}</span><span>{{ item.risk_level }} 风险</span><span>{{ item.health }}</span></div>
          <footer><button class="preview-button" @click="preview = item">查看详情</button><button class="select-button" @click="toggle(item)">{{ selected(item) ? '移除' : '添加' }}</button></footer>
        </article>
        <p v-if="!visibleCapabilities.length" class="empty-result">没有符合筛选条件的已发布能力。</p>
      </div>
      <article v-if="preview" class="capability-preview">
        <button aria-label="关闭预览" @click="preview = null">×</button>
        <p>{{ typeLabel(preview.resource_type) }} · {{ preview.source_type }} · V{{ preview.version_number }}</p>
        <h3>{{ preview.display_name }}</h3>
        <strong>{{ capabilitySummary(preview) }}</strong>
        <dl><dt>何时使用</dt><dd>{{ preview.when_to_use || '尚未说明' }}</dd><dt>何时不使用</dt><dd>{{ preview.when_not_to_use || '无额外限制' }}</dd><dt>输入</dt><dd>{{ preview.input_summary || '尚未说明' }}</dd><dt>输出</dt><dd>{{ preview.output_summary || '尚未说明' }}</dd><dt>依赖</dt><dd>{{ preview.dependencies.length ? `${preview.dependencies.length} 项，将在发布时递归校验` : '无依赖' }}</dd></dl>
      </article>
    </section>

    <aside class="assembly-summary-panel">
      <div><p>CURRENT ASSEMBLY</p><h3>当前配置</h3><span>{{ selectedCapabilities.length }} 项能力</span></div>
      <section v-for="item in modules" :key="item.key">
        <b>{{ item.title }} · {{ moduleCount(item) }}</b>
        <span v-for="capability in selectedCapabilities.filter(value => item.types.includes(value.resource_type))" :key="capability.version_id">
          {{ capability.display_name }} <small>V{{ capability.version_number }}</small>
        </span>
      </section>
      <p v-if="!selectedCapabilities.length" class="summary-empty">尚未选择能力。</p>
      <div v-if="validation" :class="['validation-result', validation.valid ? 'ok' : 'blocked']">
        <b>{{ validation.valid ? '预检通过，可以发布' : '存在阻断问题' }}</b>
        <p v-for="issue in validation.blocking_errors" :key="issue.code">{{ issue.code }} · {{ issue.message }}</p>
        <p v-for="issue in validation.warnings" :key="issue.code">{{ issue.message }}</p>
      </div>
      <div class="publish-actions">
        <button class="preflight-button" @click="emit('preflight')">执行发布预检</button>
        <button class="publish-button" :disabled="!validation?.valid || publishing" @click="emit('publish')">{{ publishing ? '发布中…' : '发布并激活 Revision' }}</button>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.assembly-workbench { display: grid; grid-template-columns: 230px minmax(0, 1fr) 280px; gap: 16px; align-items: start; }
.assembly-tree, .capability-picker, .assembly-summary-panel { border: 1px solid #e4e7ec; border-radius: 16px; background: #fff; }
.assembly-tree, .assembly-summary-panel { padding: 16px; display: grid; gap: 10px; position: sticky; top: 16px; }
.tree-title p, .capability-picker header p, .assembly-summary-panel>div>p { margin: 0; color: #6958e8; font-size: 11px; font-weight: 800; letter-spacing: .09em; }
.tree-title h3, .capability-picker h3, .assembly-summary-panel h3 { margin: 4px 0; }
.assembly-tree>button { display: grid; grid-template-columns: 28px 1fr auto; gap: 9px; align-items: center; width: 100%; padding: 12px; text-align: left; border: 1px solid transparent; border-radius: 12px; background: transparent; cursor: pointer; }
.assembly-tree>button.active { border-color: #c7bfff; background: #f4f2ff; }
.assembly-tree>button>span { color: #6958e8; font-size: 12px; font-weight: 800; }
.assembly-tree button div { display: grid; gap: 3px; }
.assembly-tree small { color: #667085; line-height: 1.35; }
.assembly-tree em { display: grid; place-items: center; min-width: 24px; height: 24px; border-radius: 999px; color: #5145cd; background: #eeebff; font-style: normal; font-weight: 700; }
.legacy-note { padding: 12px; border-radius: 12px; background: #fffaeb; color: #7a2e0e; }
.legacy-note p { margin: 5px 0 0; font-size: 12px; line-height: 1.5; }
.capability-picker { min-height: 600px; overflow: hidden; }
.capability-picker>header { padding: 18px; border-bottom: 1px solid #eaecf0; }
.capability-picker header span, .assembly-summary-panel>div>span { color: #667085; }
.picker-filters { display: grid; grid-template-columns: minmax(180px, 1fr) 140px 120px; gap: 8px; margin-top: 14px; }
.picker-filters input, .picker-filters select { min-width: 0; border: 1px solid #d0d5dd; border-radius: 9px; padding: 9px 10px; background: white; }
.capability-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 16px; }
.capability-card { display: grid; gap: 8px; padding: 14px; border: 1px solid #e4e7ec; border-radius: 13px; background: #fff; }
.capability-card.selected { border-color: #6958e8; box-shadow: 0 0 0 2px #eeeaff inset; }
.card-heading, .card-meta, .capability-card footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-heading span { padding: 3px 7px; border-radius: 999px; color: #5145cd; background: #eeeaff; font-size: 11px; font-weight: 700; }
.card-heading em, .card-meta, .capability-card small { color: #667085; font-size: 12px; font-style: normal; }
.capability-card h4, .capability-card p { margin: 0; }
.capability-card p { min-height: 42px; color: #344054; line-height: 1.5; }
.capability-card footer { margin-top: 4px; }
.capability-card footer button { border: 0; border-radius: 8px; padding: 8px 10px; cursor: pointer; }
.preview-button { color: #5145cd; background: #f4f2ff; }
.select-button { color: white; background: #5b4ee5; }
.capability-preview { position: relative; margin: 0 16px 16px; padding: 18px; border: 1px solid #c7bfff; border-radius: 14px; background: #faf9ff; }
.capability-preview>button { position: absolute; top: 10px; right: 10px; border: 0; background: transparent; font-size: 20px; cursor: pointer; }
.capability-preview p { margin: 0 0 6px; color: #6958e8; }
.capability-preview dl { display: grid; grid-template-columns: 90px 1fr; gap: 8px; margin-bottom: 0; }
.capability-preview dt { color: #667085; }
.capability-preview dd { margin: 0; }
.assembly-summary-panel section { display: grid; gap: 6px; padding-top: 10px; border-top: 1px solid #eaecf0; }
.assembly-summary-panel section span { display: flex; justify-content: space-between; gap: 8px; color: #344054; font-size: 13px; }
.assembly-summary-panel section small { color: #667085; }
.summary-empty, .empty-result { color: #667085; }
.validation-result { padding: 12px; border-radius: 10px; }
.validation-result.ok { background: #ecfdf3; color: #067647; }
.validation-result.blocked { background: #fff4f3; color: #b42318; }
.validation-result p { margin: 5px 0 0; font-size: 12px; }
.publish-actions { display: grid; gap: 8px; }
.publish-actions button { border: 0; border-radius: 10px; padding: 10px; cursor: pointer; }
.preflight-button { color: #5145cd; background: #eeeaff; }
.publish-button { color: white; background: #5b4ee5; }
.publish-button:disabled { opacity: .5; cursor: default; }
@media (max-width: 1180px) { .assembly-workbench { grid-template-columns: 200px minmax(0, 1fr); } .assembly-summary-panel { grid-column: 1 / -1; position: static; } }
@media (max-width: 820px) { .assembly-workbench { grid-template-columns: 1fr; } .assembly-tree, .assembly-summary-panel { position: static; } .capability-grid { grid-template-columns: 1fr; } .picker-filters { grid-template-columns: 1fr; } }
</style>
