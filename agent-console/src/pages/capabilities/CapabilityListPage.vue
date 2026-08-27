<script setup lang="ts">
import { ref } from 'vue'
import type { CatalogItem, IamSubject, Principal, ResourceListItem } from '../../api'
import ResourceOnboardingWizard from '../../features/resource-onboarding/ResourceOnboardingWizard.vue'

type ResourceCategory = 'CAPABILITY' | 'CONNECTOR' | 'EXTERNAL_APP'
type ResourceForm = Record<string, any>
type RagflowDataset = { id: string; name: string; description?: string }

defineProps<{
  capabilityResources: ResourceListItem[]
  resourceLoading: boolean
  principal: Principal | null
  iamUsers: IamSubject[]
  iamDepartments: IamSubject[]
  iamRoles: IamSubject[]
  resourceSaving: boolean
  ragflowDiscovering: boolean
  openResourceWizard: () => void
  openResource: (resource: ResourceListItem) => void | Promise<void>
  typeLabel: (value: string) => string
  healthLabel: (value: string) => string
  shortTime: (value?: string) => string
  selectResourceCategory: (category: ResourceCategory) => void
  catalogFor: (type: string) => CatalogItem[]
  embeddingModels: () => CatalogItem[]
  optionLabel: (item: CatalogItem) => string
  toggleSkillDependency: (field: 'skillToolVersionIds' | 'skillKnowledgeVersionIds', versionId: string) => void
  discoverRagflowDatasets: () => void | Promise<void>
  nextResourceWizardStep: () => void
  createTypedResource: () => void | Promise<void>
}>()

const resourceQuery = defineModel<string>('resourceQuery', { required: true })
const resourceType = defineModel<string>('resourceType', { required: true })
const resourceComposerOpen = defineModel<boolean>('resourceComposerOpen', { required: true })
const resourceWizardStep = defineModel<number>('resourceWizardStep', { required: true })
const resourceCategory = defineModel<ResourceCategory>('resourceCategory', { required: true })
const resourceForm = defineModel<ResourceForm>('resourceForm', { required: true })
const ragflowDatasets = defineModel<RagflowDataset[]>('ragflowDatasets', { required: true })
const installingCommon = ref(false)
const commonNotice = ref('')
const commonError = ref('')

const resourceRole = (type: string) => ({
  MODEL: '负责理解问题、推理以及决定是否调用工具。',
  PROMPT: '定义 Agent 的角色、回答边界、语气和业务规则。',
  SKILL: '一套完成业务任务的方法，可组合 Tool 和 Knowledge 形成完整能力。',
  TOOL: 'Agent 可以实际执行的动作或查询能力；来源可以是 Native、MCP、Dify 或 HTTP。',
  MEMORY_POLICY: '定义 Agent 跨会话记住什么、何时写入以及保存多久。',
} as Record<string, string>)[type] || '可被 Agent 组装和复用的能力资源。'

const typeGuides = [
  { type: 'MODEL', title: '模型', question: '谁来思考？', description: '选择负责推理和 Tool Calling 的大模型。' },
  { type: 'PROMPT', title: 'Prompt', question: '它应该怎么回答？', description: '定义角色、规则和回答边界。' },
  { type: 'SKILL', title: 'Skill', question: '它会完成什么任务？', description: '业务能力包，会组织步骤、工具和知识。' },
  { type: 'TOOL', title: 'Tool', question: '它能实际做什么？', description: '查询系统、调用接口或执行确定性动作。' },
  { type: 'MEMORY_POLICY', title: 'Memory', question: '它应该记住什么？', description: '控制跨会话长期记忆策略。' },
]

async function installCommonResources() {
  if (installingCommon.value) return
  installingCommon.value = true
  commonNotice.value = ''
  commonError.value = ''
  try {
    const sessionResponse = await fetch('/api/v1/auth/session', { credentials: 'same-origin' })
    if (!sessionResponse.ok) throw new Error('登录会话已失效')
    const session = await sessionResponse.json() as { csrf_token: string }
    const response = await fetch('/api/v1/developer/resources/common/install', {
      method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': session.csrf_token },
    })
    const payload = await response.json().catch(() => ({})) as { created?: number; existing?: number; message?: string; detail?: string }
    if (!response.ok) throw new Error(payload.message || payload.detail || `HTTP ${response.status}`)
    commonNotice.value = `常用资源已就绪：新增 ${payload.created || 0}，已有 ${payload.existing || 0}`
    window.setTimeout(() => window.location.reload(), 800)
  } catch (err) {
    commonError.value = err instanceof Error ? err.message : String(err)
  } finally {
    installingCommon.value = false
  }
}
</script>

<template>
<section class="page-content">
<div class="page-heading">
<div>
<p class="eyebrow">CAPABILITY CENTER</p>
<h1>能力中心</h1>
<p>这里放的是“可以组装进 Agent 的能力”。MCP、Dify 等只是能力来源，最终应纳管成 Tool 或 Knowledge 后再参与组装。</p>
</div>
<div class="capability-actions">
<button class="button ghost" :disabled="installingCommon" @click="installCommonResources">{{ installingCommon ? '正在添加…' : '添加常用资源' }}</button>
<button class="button primary" @click="openResourceWizard">＋ 创建 / 接入资源</button>
</div>
</div>
<p v-if="commonNotice" class="common-message success">{{ commonNotice }}</p>
<p v-if="commonError" class="common-message error">{{ commonError }}</p>

<section class="capability-type-guide" aria-label="资源类型说明">
<article v-for="guide in typeGuides" :key="guide.type" :class="{ active: resourceType === guide.type }" @click="resourceType = resourceType === guide.type ? 'ALL' : guide.type">
<span>{{ guide.title }}</span>
<b>{{ guide.question }}</b>
<p>{{ guide.description }}</p>
</article>
</section>

<ResourceOnboardingWizard
  v-if="resourceComposerOpen"
  v-model:resource-composer-open="resourceComposerOpen"
  v-model:resource-wizard-step="resourceWizardStep"
  v-model:resource-category="resourceCategory"
  v-model:resource-form="resourceForm"
  v-model:ragflow-datasets="ragflowDatasets"
  :principal="principal"
  :iam-users="iamUsers"
  :iam-departments="iamDepartments"
  :iam-roles="iamRoles"
  :resource-saving="resourceSaving"
  :ragflow-discovering="ragflowDiscovering"
  :select-resource-category="selectResourceCategory"
  :catalog-for="catalogFor"
  :embedding-models="embeddingModels"
  :option-label="optionLabel"
  :toggle-skill-dependency="toggleSkillDependency"
  :discover-ragflow-datasets="discoverRagflowDatasets"
  :next-resource-wizard-step="nextResourceWizardStep"
  :create-typed-resource="createTypedResource"
/>
<div class="filter-bar product-card">
<input v-model="resourceQuery" placeholder="搜索资源名称、Slug 或说明" />
<select v-model="resourceType">
<option value="ALL">全部类型</option>
<option value="MODEL">模型</option>
<option value="PROMPT">提示词</option>
<option value="SKILL">技能</option>
<option value="TOOL">工具 / 外部能力</option>
<option value="MEMORY_POLICY">记忆策略</option>
</select>
</div>
<div class="resource-card-grid">
<button v-for="item in capabilityResources" :key="item.resource_id" class="resource-card product-card" @click="openResource(item)">
<div class="resource-card-top">
<span class="type-badge">{{ typeLabel(item.resource_type) }}</span>
<span :class="['status-pill', item.lifecycle_status === 'ARCHIVED' ? 'blocked' : 'success']">{{ item.lifecycle_status === 'ARCHIVED' ? '已归档' : '可用' }}</span>
</div>
<h3>{{ item.display_name }}</h3>
<p class="resource-business-description">{{ item.description || '尚未填写业务说明' }}</p>
<p class="resource-role-copy"><b>在 Agent 中：</b>{{ resourceRole(item.resource_type) }}</p>
<div class="tag-list compact">
<span>来源 {{ item.source_type }}</span>
<span>{{ healthLabel(item.health) }}</span>
<span>V{{ item.latest_version_number || '—' }}</span>
<span>{{ item.referenced_by_count }} 个引用</span>
</div>
<footer>
<small>负责人：{{ item.owner_user_id || '历史导入' }}</small>
<small>{{ shortTime(item.updated_at) }}</small>
</footer>
</button>
<p v-if="resourceLoading" class="empty-copy">加载中…</p>
<p v-else-if="!capabilityResources.length" class="empty-copy">暂无符合条件的能力。</p>
</div>
</section>
</template>

<style scoped>
.capability-actions{display:flex;gap:8px;align-items:center}.common-message{margin:-6px 0 14px;padding:9px 12px;border-radius:9px;font-size:12px}.common-message.success{background:#ecfdf3;color:#067647}.common-message.error{background:#fef3f2;color:#b42318}.capability-type-guide { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin-bottom:16px; }
.capability-type-guide article { padding:14px; border:1px solid #e4e7ec; border-radius:13px; background:#fff; cursor:pointer; transition:.15s ease; }
.capability-type-guide article:hover,.capability-type-guide article.active { border-color:#8b7cf6; background:#f8f7ff; }
.capability-type-guide span { color:#6958e8; font-size:12px; font-weight:800; }
.capability-type-guide b { display:block; margin-top:7px; color:#1d2939; }
.capability-type-guide p { margin:6px 0 0; color:#667085; font-size:12px; line-height:1.45; }
.resource-business-description { margin-bottom:8px; }
.resource-role-copy { margin:0; padding:9px 10px; border-radius:9px; background:#f8f9fc; color:#475467 !important; font-size:12px; line-height:1.5; }
@media (max-width:1100px){.capability-type-guide{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media (max-width:640px){.capability-type-guide{grid-template-columns:1fr}.capability-actions{align-items:stretch;flex-direction:column}.capability-actions button{width:100%}}
</style>
