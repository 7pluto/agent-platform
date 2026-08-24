<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AgentWorkbenchItem, AuditEvent, IamSubject, ResourceGrant, ResourceListItem } from '../../api'

const props = defineProps<{
  grants: ResourceGrant[]
  audits: AuditEvent[]
  resources: ResourceListItem[]
  agents: AgentWorkbenchItem[]
  users: IamSubject[]
  roles: IamSubject[]
  departments: IamSubject[]
  loading: boolean
}>()
const emit = defineEmits<{
  refresh: []
  create: [payload: { subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string; resource_type: string; resource_id: string; actions: string[] }]
  revoke: [grant: ResourceGrant]
}>()

const tab = ref<'GRANTS' | 'AUDIT'>('GRANTS')
const query = ref('')
const targetKey = ref('')
const subjectType = ref<'USER' | 'ROLE' | 'DEPT'>('DEPT')
const subjectId = ref('')
const actions = ref<string[]>([])

const targets = computed(() => [
  ...props.agents.map(item => ({ key: `DEPLOYMENT:${item.deployment_id}`, type: 'DEPLOYMENT', id: item.deployment_id, name: item.display_name, description: '智能体可见与运行入口' })),
  ...props.resources.map(item => ({ key: `${item.resource_type}:${item.resource_id}`, type: item.resource_type, id: item.resource_id, name: item.display_name, description: item.description || item.source_type })),
])
const selectedTarget = computed(() => targets.value.find(item => item.key === targetKey.value))
const availableActions = computed(() => selectedTarget.value?.type === 'DEPLOYMENT' ? ['VIEW', 'RUN'] : ['VIEW', 'USE', 'EDIT', 'PUBLISH', 'MANAGE'])
const subjects = computed(() => subjectType.value === 'USER' ? props.users : subjectType.value === 'ROLE' ? props.roles : props.departments)

watch(selectedTarget, () => { actions.value = selectedTarget.value?.type === 'DEPLOYMENT' ? ['VIEW', 'RUN'] : ['VIEW', 'USE'] })
watch(subjectType, () => { subjectId.value = '' })

const targetNames = computed(() => new Map(targets.value.map(item => [`${item.type}:${item.id}`, item.name])))
const subjectNames = computed(() => new Map([...props.users, ...props.roles, ...props.departments].map(item => [`${item.type}:${item.external_id}`, item.display_name])))
const filteredGrants = computed(() => props.grants.filter(item => {
  const text = `${targetName(item)} ${subjectName(item)} ${item.actions.join(' ')}`.toLowerCase()
  return text.includes(query.value.trim().toLowerCase())
}))
const filteredAudits = computed(() => props.audits.filter(item => `${item.action} ${item.actor_id} ${item.resource_type} ${item.resource_id}`.toLowerCase().includes(query.value.trim().toLowerCase())))

function targetName(item: Pick<ResourceGrant, 'resource_type' | 'resource_id'>) { return targetNames.value.get(`${item.resource_type}:${item.resource_id}`) || `${item.resource_type} · ${item.resource_id.slice(0, 8)}…` }
function subjectName(item: Pick<ResourceGrant, 'subject_type' | 'subject_id'>) { return subjectNames.value.get(`${item.subject_type}:${item.subject_id}`) || item.subject_id }
function shortTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }
function actionLabel(value: string) { return ({ VIEW: '查看', USE: '使用能力', EDIT: '编辑', PUBLISH: '发布', MANAGE: '管理授权', RUN: '运行智能体' } as Record<string, string>)[value] || value }
function submit() {
  if (!selectedTarget.value || !subjectId.value || !actions.value.length) return
  emit('create', { subject_type: subjectType.value, subject_id: subjectId.value, resource_type: selectedTarget.value.type, resource_id: selectedTarget.value.id, actions: actions.value })
}
</script>

<template>
  <section class="page-content permission-audit-page">
    <div class="page-heading"><div><p class="eyebrow">AUTHORIZATION & AUDIT</p><h1>权限与审计</h1><p>RuoYi 提供用户、角色和部门；本平台独立决定谁能查看、使用、编辑、发布或运行每项能力。</p></div><button class="button ghost" :disabled="loading" @click="emit('refresh')">{{ loading ? '刷新中…' : '刷新权限数据' }}</button></div>
    <nav class="governance-tabs"><button :class="{ active: tab === 'GRANTS' }" @click="tab = 'GRANTS'">授权规则 <span>{{ grants.length }}</span></button><button :class="{ active: tab === 'AUDIT' }" @click="tab = 'AUDIT'">审计记录 <span>{{ audits.length }}</span></button></nav>

    <template v-if="tab === 'GRANTS'">
      <article class="product-card grant-composer">
        <div class="section-heading"><div><h2>新增授权</h2><p>智能体的 VIEW/RUN 与其内部 Dify、RAG、MCP、Tool 的 USE 相互独立；未授权能力不会暴露给该用户的模型。</p></div></div>
        <div class="grant-form">
          <label>授权对象<select v-model="targetKey"><option value="">请选择智能体或能力</option><optgroup label="智能体"><option v-for="item in agents" :key="item.deployment_id" :value="`DEPLOYMENT:${item.deployment_id}`">{{ item.display_name }} · 智能体</option></optgroup><optgroup label="能力资源"><option v-for="item in resources" :key="item.resource_id" :value="`${item.resource_type}:${item.resource_id}`">{{ item.display_name }} · {{ item.resource_type }}</option></optgroup></select><small>{{ selectedTarget?.description || '使用业务名称选择，不需要识别 UUID。' }}</small></label>
          <label>RuoYi 主体类型<select v-model="subjectType"><option value="DEPT">部门</option><option value="ROLE">角色</option><option value="USER">用户</option></select></label>
          <label>RuoYi 主体<select v-model="subjectId"><option value="">请选择</option><option v-for="item in subjects" :key="item.external_id" :value="item.external_id">{{ item.display_name }} · {{ item.external_id }}</option></select></label>
          <fieldset><legend>允许动作</legend><label v-for="item in availableActions" :key="item"><input v-model="actions" type="checkbox" :value="item" />{{ actionLabel(item) }}</label></fieldset>
          <button class="button primary" :disabled="loading || !targetKey || !subjectId || !actions.length" @click="submit">保存授权</button>
        </div>
      </article>
      <div class="filter-bar product-card"><input v-model="query" placeholder="按能力、智能体、用户、角色或部门搜索" /></div>
      <div class="grant-grid">
        <article v-for="item in filteredGrants" :key="item.grant_id" class="product-card grant-card">
          <header><div><span class="type-badge">{{ item.resource_type === 'DEPLOYMENT' ? '智能体' : item.resource_type }}</span><h3>{{ targetName(item) }}</h3></div><span :class="['status-pill', item.effect === 'ALLOW' ? 'success' : 'blocked']">{{ item.effect === 'ALLOW' ? '允许' : '拒绝' }}</span></header>
          <p><b>{{ item.subject_type === 'DEPT' ? '部门' : item.subject_type === 'ROLE' ? '角色' : '用户' }}：</b>{{ subjectName(item) }}</p>
          <div class="tag-list"><span v-for="action in item.actions" :key="action">{{ actionLabel(action) }}</span></div>
          <footer><small>{{ shortTime(item.created_at) }} · {{ item.created_by }}</small><button class="text-link danger" @click="emit('revoke', item)">撤销</button></footer>
        </article>
        <div v-if="!filteredGrants.length" class="empty-panel">当前筛选下没有授权规则。</div>
      </div>
    </template>

    <template v-else>
      <div class="filter-bar product-card"><input v-model="query" placeholder="按操作、执行人或对象搜索审计记录" /></div>
      <section class="product-card audit-list"><article v-for="item in filteredAudits" :key="item.audit_event_id"><span class="audit-dot" /><div><b>{{ item.action }}</b><p>{{ item.resource_type }} · {{ targetNames.get(`${item.resource_type}:${item.resource_id}`) || item.resource_id }}</p><small>{{ shortTime(item.occurred_at) }} · 操作人 {{ item.actor_id }}</small></div></article><p v-if="!filteredAudits.length" class="empty-copy">当前筛选下没有审计记录。</p></section>
    </template>
  </section>
</template>

<style scoped>
.governance-tabs { display: flex; gap: 8px; margin: 18px 0; }
.governance-tabs button { border: 0; border-radius: 12px; background: var(--surface-muted); color: var(--muted); padding: 11px 16px; font-weight: 700; cursor: pointer; }
.governance-tabs button.active { background: var(--primary-soft); color: var(--primary); }
.governance-tabs span { margin-left: 6px; }
.grant-composer { padding: 20px; margin-bottom: 16px; }
.grant-form { display: grid; grid-template-columns: 1.4fr .6fr 1fr; gap: 14px; align-items: end; }
.grant-form label { display: grid; gap: 7px; font-weight: 700; }
.grant-form label small { color: var(--muted); font-weight: 400; }
.grant-form fieldset { grid-column: 1 / -2; display: flex; flex-wrap: wrap; gap: 12px; border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
.grant-form fieldset label { display: flex; align-items: center; gap: 6px; font-weight: 500; }
.filter-bar { padding: 13px; margin-bottom: 16px; }
.filter-bar input { width: 100%; }
.grant-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.grant-card { padding: 18px; display: grid; gap: 13px; }
.grant-card header, .grant-card footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.grant-card h3 { margin: 8px 0 0; }
.grant-card footer small { color: var(--muted); }
.audit-list { padding: 8px 20px; }
.audit-list article { display: grid; grid-template-columns: 14px 1fr; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--border); }
.audit-dot { width: 10px; height: 10px; margin-top: 5px; border-radius: 50%; background: var(--primary); }
.audit-list p { margin: 5px 0; color: var(--muted); }
.audit-list small { color: var(--muted); }
@media (max-width: 1050px) { .grant-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .grant-form { grid-template-columns: 1fr 1fr; } }
@media (max-width: 700px) { .grant-grid, .grant-form { grid-template-columns: 1fr; } .grant-form fieldset { grid-column: auto; } }
</style>
