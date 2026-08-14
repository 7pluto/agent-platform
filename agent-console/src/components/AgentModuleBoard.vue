<script setup lang="ts">
import { computed } from 'vue'
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

const list = (type: string) => props.catalog.filter(item => item.resource_type === type)
const single = (field: string) => String(props.specification[field] || '')
const many = (field: string) => (props.specification[field] as string[] || [])
const selected = (field: string, id: string) => field.endsWith('_ids') ? many(field).includes(id) : single(field) === id
const skillDependencies = computed(() => {
  const selectedSkills = new Set(many('skill_version_ids'))
  const direct = new Set([...many('tool_version_ids'), ...many('knowledge_version_ids')])
  return props.catalog.filter(item => selectedSkills.has(item.version_id)).flatMap(skill =>
    skill.dependencies.map(id => ({ skill: skill.display_name, item: props.catalog.find(candidate => candidate.version_id === id), direct: direct.has(id) })))
})
const capabilitySummary = (item: CatalogItem) => item.one_line_summary || item.description || item.summary
const usageSummary = (item: CatalogItem) => item.when_to_use || '适用场景尚未补充'
</script>

<template>
  <div class="agent-module-board">
    <section class="module-section">
      <header><div><span class="module-number">01</span><div><h3>模型与身份</h3><p>确定智能体的推理模型、角色和回答边界。</p></div></div><span class="module-state">{{ single('model_version_id') ? '已配置' : '待配置' }}</span></header>
      <div class="module-columns">
        <article><h4>对话模型</h4><button v-for="item in list('MODEL')" :key="item.version_id" :class="['capability-choice', { selected: selected('model_version_id', item.version_id) }]" @click="emit('single', 'model_version_id', item.version_id)"><span class="choice-icon">M</span><span><b>{{ item.display_name }}</b><small>{{ capabilitySummary(item) }}</small><small class="usage-hint">适用：{{ usageSummary(item) }}</small><em>V{{ item.version_number }} · {{ item.health }}</em></span><i>{{ selected('model_version_id', item.version_id) ? '已选择' : '选择' }}</i></button></article>
        <article><h4>系统提示词</h4><button v-for="item in list('PROMPT')" :key="item.version_id" :class="['capability-choice', { selected: selected('prompt_version_id', item.version_id) }]" @click="emit('single', 'prompt_version_id', selected('prompt_version_id', item.version_id) ? '' : item.version_id)"><span class="choice-icon">P</span><span><b>{{ item.display_name }}</b><small>{{ capabilitySummary(item) }}</small><small class="usage-hint">适用：{{ usageSummary(item) }}</small><em>V{{ item.version_number }} · {{ item.status }}</em></span><i>{{ selected('prompt_version_id', item.version_id) ? '移除' : '选择' }}</i></button></article>
      </div>
    </section>

    <section class="module-section">
      <header><div><span class="module-number">02</span><div><h3>技能与工具</h3><p>Skill 自动带入指令和依赖，模型在运行时自主决定是否调用真实工具。</p></div></div><span class="module-state">{{ many('skill_version_ids').length }} Skills · {{ many('tool_version_ids').length }} Tools</span></header>
      <div class="module-columns">
        <article><h4>业务技能</h4><button v-for="item in list('SKILL')" :key="item.version_id" :class="['capability-choice', { selected: selected('skill_version_ids', item.version_id) }]" @click="emit('many', 'skill_version_ids', item.version_id)"><span class="choice-icon">S</span><span><b>{{ item.display_name }}</b><small>{{ capabilitySummary(item) }}</small><small class="usage-hint">适用：{{ usageSummary(item) }}</small><em>V{{ item.version_number }} · 自动依赖 {{ item.dependencies.length }} 项</em></span><i>{{ selected('skill_version_ids', item.version_id) ? '移除' : '添加' }}</i></button></article>
        <article><h4>直接工具（Native / Dify / MCP Tool）</h4><button v-for="item in list('TOOL')" :key="item.version_id" :class="['capability-choice', { selected: selected('tool_version_ids', item.version_id) }]" @click="emit('many', 'tool_version_ids', item.version_id)"><span class="choice-icon">T</span><span><b>{{ item.display_name }}</b><small>{{ capabilitySummary(item) }}</small><small class="usage-hint">适用：{{ usageSummary(item) }}</small><em>{{ item.source_type }} · V{{ item.version_number }} · {{ item.health }}</em></span><i>{{ selected('tool_version_ids', item.version_id) ? '移除' : '添加' }}</i></button></article>
      </div>
      <div v-if="skillDependencies.length" class="dependency-preview"><b>由 Skill 自动引入的能力</b><article v-for="dependency in skillDependencies" :key="`${dependency.skill}-${dependency.item?.version_id || 'unknown'}`"><span>{{ dependency.skill }}</span><strong>→</strong><span>{{ dependency.item?.display_name || '未授权或不可见资源' }}</span><em>{{ dependency.direct ? '同时直接选择' : '传递依赖' }}</em></article></div>
      <p v-if="many('mcp_connection_version_ids').length" class="compat-note">当前 Revision 含 {{ many('mcp_connection_version_ids').length }} 个历史 MCP Connection 直连引用。继续兼容历史运行；新配置只选择发现后的 MCP Tool。</p>
    </section>

    <section class="module-section">
      <header><div><span class="module-number">03</span><div><h3>知识与长期记忆</h3><p>Knowledge 由模型按需检索；Memory Policy 配置后每次 Run 固定加载。</p></div></div><span class="module-state">{{ many('knowledge_version_ids').length }} Knowledge · {{ single('memory_policy_version_id') ? 'Memory On' : 'Memory Off' }}</span></header>
      <div class="module-columns">
        <article><h4>企业知识库</h4><button v-for="item in list('KNOWLEDGE')" :key="item.version_id" :class="['capability-choice', { selected: selected('knowledge_version_ids', item.version_id) }]" @click="emit('many', 'knowledge_version_ids', item.version_id)"><span class="choice-icon">K</span><span><b>{{ item.display_name }}</b><small>{{ capabilitySummary(item) }}</small><small class="usage-hint">适用：{{ usageSummary(item) }}</small><em>V{{ item.version_number }} · {{ item.health }}</em></span><i>{{ selected('knowledge_version_ids', item.version_id) ? '移除' : '添加' }}</i></button></article>
        <article><h4>Memory Policy</h4><button v-for="item in list('MEMORY_POLICY')" :key="item.version_id" :class="['capability-choice', { selected: selected('memory_policy_version_id', item.version_id) }]" @click="emit('single', 'memory_policy_version_id', selected('memory_policy_version_id', item.version_id) ? '' : item.version_id)"><span class="choice-icon">μ</span><span><b>{{ item.display_name }}</b><small>{{ capabilitySummary(item) }}</small><small class="usage-hint">适用：{{ usageSummary(item) }}</small><em>V{{ item.version_number }} · 每次 Run 固定加载</em></span><i>{{ selected('memory_policy_version_id', item.version_id) ? '停用' : '启用' }}</i></button></article>
      </div>
    </section>

    <section class="module-section preflight-section">
      <header><div><span class="module-number">04</span><div><h3>变更预检与发布</h3><p>递归校验授权、依赖、模型和知识索引，成功后生成不可变版本与 Revision。</p></div></div><button class="button primary" @click="emit('preflight')">执行预检</button></header>
      <div v-if="validation" :class="['validation-result', validation.valid ? 'ok' : 'blocked']"><b>{{ validation.valid ? '预检通过，可以发布' : '存在阻断问题' }}</b><p v-for="issue in validation.blocking_errors" :key="issue.code">{{ issue.code }} · {{ issue.message }}</p><p v-for="issue in validation.warnings" :key="issue.code">{{ issue.message }}</p><div v-if="validation.resolved_capabilities.length" class="resolved-list"><span v-for="item in validation.resolved_capabilities" :key="`${item.version_id}-${item.origin}`"><b>{{ item.display_name }}</b><small>{{ item.origin === 'DIRECT' ? '直接选择' : '自动引入' }} · {{ item.dependency_path.join(' → ') }}</small></span></div><button class="button primary" :disabled="!validation.valid || publishing" @click="emit('publish')">{{ publishing ? '发布中…' : '发布并激活新 Revision' }}</button></div>
    </section>
  </div>
</template>


