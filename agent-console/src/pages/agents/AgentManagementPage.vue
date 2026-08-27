<script setup lang="ts">
import type { AgentWorkbenchItem, CatalogItem, ConfigurationDraft, ConfigurationValidation, DeploymentCapabilities, IamSubject } from '../../api'
import AgentModuleBoard from '../../components/AgentModuleBoard.vue'
import PublicationScopePicker from '../../features/permissions/PublicationScopePicker.vue'

defineProps<{
  agents: AgentWorkbenchItem[]
  loading: boolean
  creating: boolean
  detail: DeploymentCapabilities | null
  draft: ConfigurationDraft | null
  validation: ConfigurationValidation | null
  catalog: CatalogItem[]
  saving: boolean
  publishing: boolean
  users: IamSubject[]
  departments: IamSubject[]
  roles: IamSubject[]
}>()
const query = defineModel<string>('query', { required: true })
const active = defineModel<'ALL' | 'true' | 'false'>('active', { required: true })
const creatorOpen = defineModel<boolean>('creatorOpen', { required: true })
const createForm = defineModel<{ displayName: string; description: string; deploymentName: string }>('createForm', { required: true })
const publicationScope = defineModel<'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'>('publicationScope', { required: true })
const publicationSubjects = defineModel<string[]>('publicationSubjects', { required: true })

const emit = defineEmits<{
  openCreator: []
  create: []
  open: [agent: AgentWorkbenchItem]
  delete: [agent: AgentWorkbenchItem]
  closeBuilder: []
  saveDraft: []
  single: [field: string, versionId: string]
  many: [field: string, versionId: string]
  replace: [field: string, fromVersionId: string, toVersionId: string]
  preflight: []
  publish: []
}>()

function shortTime(value?: string) { if (!value) return '暂无'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }
function typeLabel(value: string) { return ({ MODEL: '模型', PROMPT: '提示词', SKILL: '技能', TOOL: '工具', KNOWLEDGE: '知识库', MEMORY_POLICY: '记忆' } as Record<string, string>)[value] || value }
</script>

<template>
  <section class="page-content">
    <div class="page-heading"><div><p class="eyebrow">AGENT MANAGEMENT</p><h1>智能体管理</h1><p>按 Deployment 管理当前能力组合、Revision 和发布流程。</p></div></div>
    <div class="filter-bar product-card"><input v-model="query" placeholder="搜索智能体或部署名称" /><select v-model="active"><option value="ALL">全部状态</option><option value="true">已启用</option><option value="false">未启用</option></select></div>
    <section class="agent-create-action"><button class="button primary" @click="emit('openCreator')">＋ 新增智能体</button></section>
    <div v-if="creatorOpen" class="modal-backdrop" @click.self="creatorOpen = false">
      <section class="resource-composer agent-creator agent-create-modal" role="dialog" aria-modal="true" aria-label="新增智能体">
        <header><div><p class="eyebrow">CREATE AGENT</p><h2>新增智能体</h2><p>先建立智能体和生产部署，再进入组装工作台选择模型、技能、工具、知识库和记忆。</p></div><button class="icon-button" aria-label="关闭" @click="creatorOpen = false">×</button></header>
        <div class="resource-form"><label>智能体名称<input v-model="createForm.displayName" maxlength="128" placeholder="例如：员工制度助手" /></label><label>部署名称<input v-model="createForm.deploymentName" maxlength="64" placeholder="例如：员工制度助手-生产" /></label><label class="wide-field">用途说明<textarea v-model="createForm.description" rows="3" maxlength="1000" placeholder="说明它面向谁、解决什么问题；后续可在配置工作台选择资源并发布。" /></label></div>
        <footer><button class="button ghost" @click="creatorOpen = false">取消</button><button class="button primary" :disabled="creating" @click="emit('create')">{{ creating ? '创建中…' : '创建并进入配置' }}</button></footer>
      </section>
    </div>
    <div class="table-card product-card"><table><thead><tr><th>智能体</th><th>Deployment</th><th>当前能力</th><th>Revision</th><th>最近运行</th><th /></tr></thead><tbody><tr v-for="item in agents" :key="item.deployment_id"><td><b>{{ item.display_name }}</b><small>{{ item.description || '—' }}</small></td><td>{{ item.deployment_name }}</td><td><div class="tag-list compact"><span v-for="(count, type) in item.capability_counts" :key="type">{{ count }} {{ typeLabel(type) }}</span></div></td><td>V{{ item.revision_number || '—' }}</td><td>{{ shortTime(item.last_run_at) }}</td><td class="row-actions"><button class="text-link" @click="emit('open', item)">配置</button><button class="text-link danger" @click="emit('delete', item)">删除</button></td></tr></tbody></table><p v-if="!loading && !agents.length" class="empty-copy">暂无符合条件的智能体。</p></div>
    <section v-if="detail && draft" class="builder product-card">
      <header class="builder-header"><div><button class="text-link" @click="emit('closeBuilder')">‹ 返回列表</button><p class="eyebrow">CONFIGURE AGENT</p><h2>{{ agents.find(item => item.deployment_id === detail?.deployment_id)?.display_name || '智能体配置' }}</h2><p>基于 Revision {{ detail?.agent_version_number }} 创建配置草稿；资源版本只会在你显式选择后变化，发布后生成不可变新版本。</p></div><div><button class="button ghost" :disabled="saving" @click="emit('saveDraft')">{{ saving ? '保存中…' : '保存草稿' }}</button></div></header>
      <section class="agent-publication-policy"><div><p class="eyebrow">AVAILABILITY</p><h3>可用范围与运行授权</h3><p>选择谁可以看到、创建会话并运行此智能体。发布新 Revision 时范围立即生效。</p></div><PublicationScopePicker v-model:scope="publicationScope" v-model:subjects="publicationSubjects" :users="users" :departments="departments" :roles="roles" personal-label="仅发布人" /></section>
      <AgentModuleBoard
        :catalog="catalog"
        :specification="draft.specification"
        :validation="validation"
        :publishing="publishing"
        @single="(field, id) => emit('single', field, id)"
        @many="(field, id) => emit('many', field, id)"
        @replace="(field, fromId, toId) => emit('replace', field, fromId, toId)"
        @preflight="emit('preflight')"
        @publish="emit('publish')"
      />
    </section>
  </section>
</template>
