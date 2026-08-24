<script setup lang="ts">
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
</script>

<template>
<section class="page-content">
<div class="page-heading">
<div>
<p class="eyebrow">CAPABILITY CENTER</p>
<h1>能力中心</h1>
<p>管理可组装进智能体的模型、提示词、技能、工具与记忆策略；连接和知识库分别治理。</p>
</div>
<button class="button primary" @click="openResourceWizard">＋ 入驻新资源</button>
</div>
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
<option value="TOOL">工具 / Dify</option>
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
<p>{{ item.description || item.slug }}</p>
<div class="tag-list compact">
<span>{{ item.source_type }}</span>
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

