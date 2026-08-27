<script setup lang="ts">
import { ref } from 'vue'
import type { AgentWorkbenchItem, CatalogItem, ConfigurationDraft, ConfigurationValidation, DeploymentCapabilities, IamSubject } from '../../api'
import AgentModuleBoard from '../../components/AgentModuleBoard.vue'
import AgentReleaseChangeList from '../../components/AgentReleaseChangeList.vue'
import PublicationScopePicker from '../../features/permissions/PublicationScopePicker.vue'
import AgentRevisionCompare from './AgentRevisionCompare.vue'

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
const publishConfirmOpen = ref(false)

const emit = defineEmits<{
  openCreator: []
  create: []
  open: [agent: AgentWorkbenchItem]
  delete: [agent: AgentWorkbenchItem]
  closeBuilder: []
  saveDraft: []
  single: [field: string, versionId: string]
  many: [field: string, versionId: string]
  preflight: []
  publish: []
}>()

function forwardVersionReplace(field: string, fromVersionId: string, toVersionId: string) {
  if (field.endsWith('_ids')) {
    emit('many', field, fromVersionId)
    emit('many', field, toVersionId)
  } else {
    emit('single', field, toVersionId)
  }
}
function requestPublish() { publishConfirmOpen.value = true }
function confirmPublish() {
  publishConfirmOpen.value = false
  emit('publish')
}
function shortTime(value?: string) { if (!value) return '暂无'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }
function typeLabel(value: string) { return ({ MODEL: '模型', PROMPT: '提示词', SKILL: '技能', TOOL: '工具', KNOWLEDGE: '知识库', MEMORY_POLICY: '记忆' } as Record<string, string>)[value] || value }
function scopeLabel(value: string) { return ({ PERSONAL: '仅发布人', OWNER_DEPT: '责任部门', SELECTED_SUBJECTS: '指定 RuoYi 主体' } as Record<string, string>)[value] || value }
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
      <header class="builder-header"><div><button class="text-link" @click="emit('closeBuilder')">‹ 返回列表</button><p class="eyebrow">CONFIGURE AGENT</p><h2>{{ agents.find(item => item.deployment_id === detail?.deployment_id)?.display_name || '智能体配置' }}</h2><p>基于当前 Agent V{{ detail?.agent_version_number }} 创建配置草稿；资源版本只会在你显式选择后变化，发布后生成不可变新版本。</p></div><div><button class="button ghost" :disabled="saving" @click="emit('saveDraft')">{{ saving ? '保存中…' : '保存草稿' }}</button></div></header>
      <section class="agent-publication-policy"><div><p class="eyebrow">AVAILABILITY</p><h3>可用范围与运行授权</h3><p>选择谁可以看到、创建会话并运行此智能体。发布新 Revision 时范围立即生效。</p></div><PublicationScopePicker v-model:scope="publicationScope" v-model:subjects="publicationSubjects" :users="users" :departments="departments" :roles="roles" personal-label="仅发布人" /></section>
      <AgentModuleBoard
        :catalog="catalog"
        :specification="draft.specification"
        :validation="validation"
        :publishing="publishing"
        @single="(field, id) => emit('single', field, id)"
        @many="(field, id) => emit('many', field, id)"
        @replace="forwardVersionReplace"
        @preflight="emit('preflight')"
        @publish="requestPublish"
      />

      <AgentRevisionCompare
        :deployment-id="detail.deployment_id"
        :active-revision-id="detail.active_revision_id"
        :users="users"
        :departments="departments"
        :roles="roles"
      />
    </section>

    <div v-if="publishConfirmOpen && detail && draft && validation" class="modal-backdrop release-confirm-backdrop" @click.self="publishConfirmOpen = false">
      <section class="release-confirm" role="dialog" aria-modal="true" aria-label="确认发布智能体版本">
        <header>
          <div><p class="eyebrow">CONFIRM RELEASE</p><h2>确认发布新的 Agent Version / Revision</h2><p>发布后不会覆盖当前 Revision。请先确认资源版本变化和由 Skill 带来的依赖变化。</p></div>
          <button class="icon-button" aria-label="关闭" @click="publishConfirmOpen = false">×</button>
        </header>

        <AgentReleaseChangeList :catalog="catalog" :baseline="detail.capabilities" :specification="draft.specification" :validation="validation" />

        <section class="release-audience-summary">
          <div><small>当前 Agent Version</small><b>V{{ detail.agent_version_number }}</b><span>发布后生成新的不可变版本</span></div>
          <div><small>运行授权范围</small><b>{{ scopeLabel(publicationScope) }}</b><span>{{ publicationScope === 'SELECTED_SUBJECTS' ? `${publicationSubjects.length} 个指定主体` : '随本次 Revision 一起生效' }}</span></div>
          <div><small>预检结果</small><b>{{ validation.valid ? '通过' : '阻塞' }}</b><span>{{ validation.warnings.length }} 条提醒</span></div>
        </section>

        <footer>
          <button class="button ghost" @click="publishConfirmOpen = false">返回继续修改</button>
          <button class="button primary" :disabled="publishing || !validation.valid" @click="confirmPublish">{{ publishing ? '发布中…' : '确认并发布新 Revision' }}</button>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.release-confirm-backdrop{z-index:60}.release-confirm{display:grid;gap:16px;width:min(1080px,94vw);max-height:92vh;overflow:auto;padding:20px;border-radius:18px;background:#fff;box-shadow:0 24px 80px rgba(16,24,40,.2)}.release-confirm>header{display:flex;justify-content:space-between;gap:16px}.release-confirm>header h2{margin:4px 0}.release-confirm>header p:last-child{margin:0;color:#667085}.release-audience-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.release-audience-summary>div{display:grid;gap:4px;padding:12px;border:1px solid #e4e7ec;border-radius:12px;background:#f9fafb}.release-audience-summary small,.release-audience-summary span{color:#667085;font-size:10px}.release-audience-summary b{font-size:13px}.release-confirm>footer{display:flex;justify-content:flex-end;gap:10px;padding-top:4px}@media(max-width:800px){.release-audience-summary{grid-template-columns:1fr}.release-confirm>footer{flex-direction:column-reverse}.release-confirm>footer button{width:100%}}
</style>
