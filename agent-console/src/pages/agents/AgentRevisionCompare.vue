<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { IamSubject } from '../../api'
import {
  fetchRevisionHistory,
  type RevisionCapabilitySnapshot,
  type RevisionDependencySnapshot,
  type RevisionHistoryItem,
} from '../../features/agents/revisionHistoryApi'

const props = defineProps<{
  deploymentId: string
  users: IamSubject[]
  departments: IamSubject[]
  roles: IamSubject[]
}>()

type ChangeKind = 'ADDED' | 'REMOVED' | 'UPGRADED' | 'DOWNGRADED'
interface DependencyChange {
  kind: ChangeKind
  before?: RevisionDependencySnapshot
  after?: RevisionDependencySnapshot
}
interface ResourceChange {
  kind: ChangeKind
  before?: RevisionCapabilitySnapshot
  after?: RevisionCapabilitySnapshot
  dependencyChanges: DependencyChange[]
}

const loading = ref(false)
const error = ref('')
const history = ref<RevisionHistoryItem[]>([])
const baselineId = ref('')
const targetId = ref('')

const baseline = computed(() => history.value.find(item => item.revision_id === baselineId.value) || null)
const target = computed(() => history.value.find(item => item.revision_id === targetId.value) || null)

function capabilityKey(item: RevisionCapabilitySnapshot) {
  return `${item.resource_type}:${item.resource_id}`
}
function dependencyKey(item: RevisionDependencySnapshot) {
  return `${item.resource_type}:${item.resource_id}`
}
function versionKind(before: { version_id: string; version_number: number }, after: { version_id: string; version_number: number }): ChangeKind | null {
  if (before.version_id === after.version_id) return null
  return after.version_number >= before.version_number ? 'UPGRADED' : 'DOWNGRADED'
}
function dependencyChanges(before: RevisionCapabilitySnapshot, after: RevisionCapabilitySnapshot): DependencyChange[] {
  if (before.resource_type !== 'SKILL' || after.resource_type !== 'SKILL') return []
  const beforeMap = new Map(before.dependencies.map(item => [dependencyKey(item), item] as const))
  const afterMap = new Map(after.dependencies.map(item => [dependencyKey(item), item] as const))
  const keys = new Set([...beforeMap.keys(), ...afterMap.keys()])
  const result: DependencyChange[] = []
  for (const key of keys) {
    const oldItem = beforeMap.get(key)
    const newItem = afterMap.get(key)
    if (!oldItem && newItem) result.push({ kind: 'ADDED', after: newItem })
    else if (oldItem && !newItem) result.push({ kind: 'REMOVED', before: oldItem })
    else if (oldItem && newItem) {
      const kind = versionKind(oldItem, newItem)
      if (kind) result.push({ kind, before: oldItem, after: newItem })
    }
  }
  return result
}

const changes = computed<ResourceChange[]>(() => {
  if (!baseline.value || !target.value) return []
  const beforeMap = new Map(baseline.value.capabilities.map(item => [capabilityKey(item), item] as const))
  const afterMap = new Map(target.value.capabilities.map(item => [capabilityKey(item), item] as const))
  const keys = new Set([...beforeMap.keys(), ...afterMap.keys()])
  const result: ResourceChange[] = []
  for (const key of keys) {
    const oldItem = beforeMap.get(key)
    const newItem = afterMap.get(key)
    if (!oldItem && newItem) result.push({ kind: 'ADDED', after: newItem, dependencyChanges: [] })
    else if (oldItem && !newItem) result.push({ kind: 'REMOVED', before: oldItem, dependencyChanges: [] })
    else if (oldItem && newItem) {
      const kind = versionKind(oldItem, newItem)
      if (kind) result.push({ kind, before: oldItem, after: newItem, dependencyChanges: dependencyChanges(oldItem, newItem) })
    }
  }
  const order: Record<ChangeKind, number> = { DOWNGRADED: 0, REMOVED: 1, UPGRADED: 2, ADDED: 3 }
  return result.sort((a, b) => order[a.kind] - order[b.kind] || resourceType(a).localeCompare(resourceType(b)) || displayName(a).localeCompare(displayName(b)))
})

const unchanged = computed(() => {
  if (!baseline.value || !target.value) return 0
  const before = new Map(baseline.value.capabilities.map(item => [capabilityKey(item), item.version_id] as const))
  return target.value.capabilities.filter(item => before.get(capabilityKey(item)) === item.version_id).length
})
const dependencyChangeCount = computed(() => changes.value.reduce((sum, item) => sum + item.dependencyChanges.length, 0))

function resourceType(change: ResourceChange) { return change.after?.resource_type || change.before?.resource_type || 'UNKNOWN' }
function displayName(change: ResourceChange) { return change.after?.display_name || change.before?.display_name || '未知资源' }
function versionRoute(change: ResourceChange) {
  if (change.kind === 'ADDED') return `未使用 → V${change.after?.version_number}`
  if (change.kind === 'REMOVED') return `V${change.before?.version_number} → 移除`
  return `V${change.before?.version_number} → V${change.after?.version_number}`
}
function dependencyRoute(change: DependencyChange) {
  if (change.kind === 'ADDED') return `新增 V${change.after?.version_number}`
  if (change.kind === 'REMOVED') return `移除 V${change.before?.version_number}`
  return `V${change.before?.version_number} → V${change.after?.version_number}`
}
function dependencyName(change: DependencyChange) { return change.after?.display_name || change.before?.display_name || '未知依赖' }
function dependencyType(change: DependencyChange) { return change.after?.resource_type || change.before?.resource_type || 'UNKNOWN' }
function kindLabel(kind: ChangeKind) { return ({ ADDED: '新增', REMOVED: '移除', UPGRADED: '升级', DOWNGRADED: '降级' } as Record<ChangeKind, string>)[kind] }
function typeLabel(type: string) { return ({ MODEL: 'Model', PROMPT: 'Prompt', SKILL: 'Skill', TOOL: 'Tool', KNOWLEDGE: 'Knowledge', MEMORY_POLICY: 'Memory', MCP_CONNECTION: 'MCP Connection' } as Record<string, string>)[type] || type }
function scopeLabel(scope?: string | null) { return ({ PERSONAL: '仅发布人', OWNER_DEPT: '责任部门', SELECTED_SUBJECTS: '指定 RuoYi 主体' } as Record<string, string>)[scope || ''] || scope || '未知' }
function formatTime(value: string) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }

function subjectLabel(subject: { subject_type: string; subject_id: string }) {
  const source = subject.subject_type === 'USER' ? props.users : subject.subject_type === 'ROLE' ? props.roles : props.departments
  const found = source.find(item => item.external_id === subject.subject_id)
  const prefix = ({ USER: '用户', ROLE: '角色', DEPT: '部门' } as Record<string, string>)[subject.subject_type] || subject.subject_type
  return `${prefix} · ${found?.display_name || subject.subject_id}`
}
function subjectKey(subject: { subject_type: string; subject_id: string }) { return `${subject.subject_type}:${subject.subject_id}` }
const publicationDiff = computed(() => {
  if (!baseline.value || !target.value) return { comparable: false, scopeChanged: false, added: [] as string[], removed: [] as string[] }
  const before = baseline.value.publication
  const after = target.value.publication
  if (!before.available || !after.available) return { comparable: false, scopeChanged: false, added: [] as string[], removed: [] as string[] }
  const beforeMap = new Map(before.subjects.map(item => [subjectKey(item), item] as const))
  const afterMap = new Map(after.subjects.map(item => [subjectKey(item), item] as const))
  return {
    comparable: true,
    scopeChanged: before.scope !== after.scope,
    added: [...afterMap.keys()].filter(key => !beforeMap.has(key)).map(key => subjectLabel(afterMap.get(key)!)),
    removed: [...beforeMap.keys()].filter(key => !afterMap.has(key)).map(key => subjectLabel(beforeMap.get(key)!)),
  }
})

async function load() {
  if (!props.deploymentId) return
  loading.value = true
  error.value = ''
  try {
    history.value = await fetchRevisionHistory(props.deploymentId)
    const active = history.value.find(item => item.active) || history.value[0]
    targetId.value = active?.revision_id || ''
    const older = history.value
      .filter(item => active && item.revision_number < active.revision_number)
      .sort((a, b) => b.revision_number - a.revision_number)[0]
    baselineId.value = older?.revision_id || history.value.find(item => item.revision_id !== targetId.value)?.revision_id || targetId.value
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    history.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.deploymentId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section class="revision-compare">
    <header class="compare-header">
      <div><p>REVISION HISTORY</p><h3>Revision 历史与版本对比</h3><span>选择任意两个不可变 Revision，查看直接资源、Skill 依赖和运行授权到底发生了什么变化。</span></div>
      <button class="refresh" :disabled="loading" @click="load">{{ loading ? '加载中…' : '刷新历史' }}</button>
    </header>

    <p v-if="error" class="compare-error">{{ error }}</p>
    <div v-else-if="history.length < 2" class="compare-empty">至少发布两个 Revision 后才能进行历史对比。当前已有 {{ history.length }} 个。</div>

    <template v-else>
      <div class="revision-pickers">
        <label><span>基线 Revision</span><select v-model="baselineId"><option v-for="item in history" :key="item.revision_id" :value="item.revision_id" :disabled="item.revision_id === targetId">Revision {{ item.revision_number }} · Agent V{{ item.agent_version_number }}{{ item.active ? ' · Active' : '' }}</option></select><small v-if="baseline">{{ formatTime(baseline.created_at) }} · {{ baseline.created_by }}</small></label>
        <div class="compare-arrow">→</div>
        <label><span>目标 Revision</span><select v-model="targetId"><option v-for="item in history" :key="item.revision_id" :value="item.revision_id" :disabled="item.revision_id === baselineId">Revision {{ item.revision_number }} · Agent V{{ item.agent_version_number }}{{ item.active ? ' · Active' : '' }}</option></select><small v-if="target">{{ formatTime(target.created_at) }} · {{ target.created_by }}</small></label>
      </div>

      <div v-if="baseline && target" class="compare-summary">
        <div><b>{{ changes.length }}</b><span>直接资源变化</span></div><div><b>{{ dependencyChangeCount }}</b><span>Skill 依赖变化</span></div><div><b>{{ unchanged }}</b><span>直接资源保持</span></div>
      </div>

      <section v-if="baseline && target" class="auth-diff">
        <div class="section-heading"><div><p>RUN AUTHORIZATION</p><h4>运行授权范围</h4></div><span v-if="publicationDiff.comparable && !publicationDiff.scopeChanged && !publicationDiff.added.length && !publicationDiff.removed.length" class="same">未变化</span></div>
        <div v-if="baseline.publication.available && target.publication.available" class="auth-grid">
          <article><small>Revision {{ baseline.revision_number }}</small><b>{{ scopeLabel(baseline.publication.scope) }}</b><span v-for="subject in baseline.publication.subjects" :key="subjectKey(subject)">{{ subjectLabel(subject) }}</span></article>
          <div class="compare-arrow">→</div>
          <article><small>Revision {{ target.revision_number }}</small><b>{{ scopeLabel(target.publication.scope) }}</b><span v-for="subject in target.publication.subjects" :key="subjectKey(subject)">{{ subjectLabel(subject) }}</span></article>
        </div>
        <p v-else class="snapshot-missing">其中一个 Revision 没有发布时的授权快照。平台不会用当前权限反推历史权限。</p>
        <div v-if="publicationDiff.comparable && (publicationDiff.scopeChanged || publicationDiff.added.length || publicationDiff.removed.length)" class="auth-changes">
          <span v-if="publicationDiff.scopeChanged">范围：{{ scopeLabel(baseline.publication.scope) }} → {{ scopeLabel(target.publication.scope) }}</span>
          <span v-for="item in publicationDiff.added" :key="`add-${item}`" class="added">+ {{ item }}</span>
          <span v-for="item in publicationDiff.removed" :key="`remove-${item}`" class="removed">− {{ item }}</span>
        </div>
      </section>

      <section class="resource-diff">
        <div class="section-heading"><div><p>CAPABILITY DIFF</p><h4>资源版本变化</h4></div><span v-if="!changes.length" class="same">直接资源完全一致</span></div>
        <div v-if="changes.length" class="change-grid">
          <article v-for="change in changes" :key="`${resourceType(change)}:${displayName(change)}`" :class="['change-card', change.kind.toLowerCase()]">
            <div class="change-title"><span>{{ typeLabel(resourceType(change)) }}</span><em>{{ kindLabel(change.kind) }}</em></div>
            <h5>{{ displayName(change) }}</h5><strong>{{ versionRoute(change) }}</strong>
            <small v-if="change.before && change.after && change.before.content_hash !== change.after.content_hash">hash {{ change.before.content_hash.slice(0, 8) }} → {{ change.after.content_hash.slice(0, 8) }}</small>
            <div v-if="change.dependencyChanges.length" class="dependency-diff"><b>Skill 间接依赖变化</b><div v-for="dependency in change.dependencyChanges" :key="`${dependencyType(dependency)}:${dependencyName(dependency)}`"><span>{{ typeLabel(dependencyType(dependency)) }} · {{ dependencyName(dependency) }}</span><em :class="dependency.kind.toLowerCase()">{{ kindLabel(dependency.kind) }} · {{ dependencyRoute(dependency) }}</em></div></div>
          </article>
        </div>
        <div v-else class="compare-empty compact">这两个 Revision 的直接资源 Version ID 完全相同。</div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.revision-compare{display:grid;gap:16px;margin-top:18px;padding:18px;border:1px solid #e4e7ec;border-radius:16px;background:#fff}.compare-header,.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.compare-header p,.section-heading p{margin:0;color:#6958e8;font-size:10px;font-weight:800;letter-spacing:.09em}.compare-header h3,.section-heading h4{margin:4px 0}.compare-header span{color:#667085;font-size:12px}.refresh{border:1px solid #d0d5dd;border-radius:9px;background:#fff;padding:8px 12px;cursor:pointer}.revision-pickers{display:grid;grid-template-columns:1fr 38px 1fr;gap:12px;align-items:center;padding:14px;border-radius:12px;background:#f9fafb}.revision-pickers label{display:grid;gap:6px}.revision-pickers label>span{font-size:11px;font-weight:800;color:#344054}.revision-pickers select{width:100%;padding:9px;border:1px solid #d0d5dd;border-radius:9px;background:#fff}.revision-pickers small{color:#667085}.compare-arrow{text-align:center;color:#7f56d9;font-weight:900}.compare-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.compare-summary>div{display:grid;gap:2px;padding:12px;border:1px solid #eaecf0;border-radius:10px}.compare-summary b{font-size:18px}.compare-summary span{font-size:10px;color:#667085}.auth-diff,.resource-diff{display:grid;gap:12px;padding-top:14px;border-top:1px solid #eaecf0}.same{padding:4px 8px;border-radius:999px;background:#ecfdf3;color:#067647;font-size:10px;font-weight:800}.auth-grid{display:grid;grid-template-columns:1fr 38px 1fr;gap:10px;align-items:center}.auth-grid article{display:flex;flex-wrap:wrap;gap:6px;padding:12px;border:1px solid #e4e7ec;border-radius:10px}.auth-grid article small{width:100%;color:#667085}.auth-grid article b{width:100%;margin-bottom:3px}.auth-grid article span{padding:4px 7px;border-radius:999px;background:#f2f4f7;font-size:10px}.auth-changes{display:flex;flex-wrap:wrap;gap:7px}.auth-changes span{padding:5px 8px;border-radius:8px;background:#f4f3ff;color:#5925dc;font-size:10px}.auth-changes .added{background:#ecfdf3;color:#067647}.auth-changes .removed{background:#fef3f2;color:#b42318}.snapshot-missing,.compare-empty{margin:0;padding:12px;border-radius:10px;background:#fffaeb;color:#7a2e0e;font-size:11px}.compare-empty.compact{background:#f9fafb;color:#667085}.change-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.change-card{padding:13px;border:1px solid #e4e7ec;border-left:4px solid #7f56d9;border-radius:11px}.change-card.added{border-left-color:#079455}.change-card.removed,.change-card.downgraded{border-left-color:#d92d20}.change-title{display:flex;justify-content:space-between;gap:8px}.change-title span{font-size:10px;color:#667085;font-weight:800}.change-title em{font-size:10px;font-style:normal;font-weight:800;color:#6941c6}.change-card.added .change-title em{color:#067647}.change-card.removed .change-title em,.change-card.downgraded .change-title em{color:#b42318}.change-card h5{margin:6px 0}.change-card>strong{display:block;font-size:12px}.change-card>small{display:block;margin-top:5px;color:#98a2b3}.dependency-diff{display:grid;gap:6px;margin-top:10px;padding-top:9px;border-top:1px solid #eaecf0}.dependency-diff>b{font-size:10px}.dependency-diff>div{display:flex;justify-content:space-between;gap:8px;font-size:10px}.dependency-diff em{font-style:normal;color:#6941c6}.dependency-diff em.added{color:#067647}.dependency-diff em.removed,.dependency-diff em.downgraded{color:#b42318}.compare-error{padding:12px;border-radius:10px;background:#fef3f2;color:#b42318}@media(max-width:900px){.revision-pickers,.auth-grid{grid-template-columns:1fr}.compare-arrow{transform:rotate(90deg)}.compare-summary,.change-grid{grid-template-columns:1fr}.compare-header,.section-heading{flex-direction:column}}
</style>
