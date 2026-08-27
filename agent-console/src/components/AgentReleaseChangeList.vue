<script setup lang="ts">
import { computed } from 'vue'
import type { CatalogItem, ConfigurationValidation } from '../api'

const props = defineProps<{
  catalog: CatalogItem[]
  baseline: CatalogItem[]
  specification: Record<string, unknown>
  validation: ConfigurationValidation | null
}>()

type ChangeKind = 'ADDED' | 'REMOVED' | 'UPGRADED' | 'DOWNGRADED'
interface DependencyChange {
  kind: ChangeKind
  resourceType: string
  displayName: string
  before?: CatalogItem
  after?: CatalogItem
}
interface ReleaseChange extends DependencyChange {
  dependencyChanges: DependencyChange[]
}

const fields: Array<{ type: string; field: string; many: boolean }> = [
  { type: 'MODEL', field: 'model_version_id', many: false },
  { type: 'PROMPT', field: 'prompt_version_id', many: false },
  { type: 'SKILL', field: 'skill_version_ids', many: true },
  { type: 'TOOL', field: 'tool_version_ids', many: true },
  { type: 'KNOWLEDGE', field: 'knowledge_version_ids', many: true },
  { type: 'MEMORY_POLICY', field: 'memory_policy_version_id', many: false },
]

const byVersionId = computed(() => new Map(props.catalog.map(item => [item.version_id, item])))
const baselineByVersionId = computed(() => new Map(props.baseline.map(item => [item.version_id, item])))

function currentVersionIds(): string[] {
  const result: string[] = []
  for (const item of fields) {
    const raw = props.specification[item.field]
    if (item.many) {
      if (Array.isArray(raw)) result.push(...raw.map(String))
    } else if (raw) result.push(String(raw))
  }
  return result
}

const currentCapabilities = computed(() => currentVersionIds().map(id => byVersionId.value.get(id) || baselineByVersionId.value.get(id)).filter(Boolean) as CatalogItem[])
const keyOf = (item: CatalogItem) => `${item.resource_type}:${item.resource_id}`

function versionChange(before: CatalogItem, after: CatalogItem): ChangeKind | null {
  if (before.version_id === after.version_id) return null
  return after.version_number >= before.version_number ? 'UPGRADED' : 'DOWNGRADED'
}

function dependencyChanges(before: CatalogItem, after: CatalogItem): DependencyChange[] {
  if (before.resource_type !== 'SKILL' || after.resource_type !== 'SKILL') return []
  const beforeItems = before.dependencies.map(id => byVersionId.value.get(id) || baselineByVersionId.value.get(id)).filter(Boolean) as CatalogItem[]
  const afterItems = after.dependencies.map(id => byVersionId.value.get(id) || baselineByVersionId.value.get(id)).filter(Boolean) as CatalogItem[]
  const beforeMap = new Map(beforeItems.map(item => [item.resource_id, item]))
  const afterMap = new Map(afterItems.map(item => [item.resource_id, item]))
  const ids = new Set([...beforeMap.keys(), ...afterMap.keys()])
  const result: DependencyChange[] = []
  for (const id of ids) {
    const oldItem = beforeMap.get(id)
    const newItem = afterMap.get(id)
    if (!oldItem && newItem) result.push({ kind: 'ADDED', resourceType: newItem.resource_type, displayName: newItem.display_name, after: newItem })
    else if (oldItem && !newItem) result.push({ kind: 'REMOVED', resourceType: oldItem.resource_type, displayName: oldItem.display_name, before: oldItem })
    else if (oldItem && newItem) {
      const kind = versionChange(oldItem, newItem)
      if (kind) result.push({ kind, resourceType: newItem.resource_type, displayName: newItem.display_name, before: oldItem, after: newItem })
    }
  }
  return result
}

const changes = computed<ReleaseChange[]>(() => {
  const beforeMap = new Map(props.baseline.map(item => [keyOf(item), item]))
  const afterMap = new Map(currentCapabilities.value.map(item => [keyOf(item), item]))
  const keys = new Set([...beforeMap.keys(), ...afterMap.keys()])
  const result: ReleaseChange[] = []
  for (const key of keys) {
    const before = beforeMap.get(key)
    const after = afterMap.get(key)
    if (!before && after) result.push({ kind: 'ADDED', resourceType: after.resource_type, displayName: after.display_name, after, dependencyChanges: [] })
    else if (before && !after) result.push({ kind: 'REMOVED', resourceType: before.resource_type, displayName: before.display_name, before, dependencyChanges: [] })
    else if (before && after) {
      const kind = versionChange(before, after)
      if (kind) result.push({ kind, resourceType: after.resource_type, displayName: after.display_name, before, after, dependencyChanges: dependencyChanges(before, after) })
    }
  }
  const order: Record<ChangeKind, number> = { DOWNGRADED: 0, REMOVED: 1, UPGRADED: 2, ADDED: 3 }
  return result.sort((a, b) => order[a.kind] - order[b.kind] || a.resourceType.localeCompare(b.resourceType) || a.displayName.localeCompare(b.displayName))
})

const unchangedCount = computed(() => {
  const before = new Map(props.baseline.map(item => [keyOf(item), item.version_id]))
  return currentCapabilities.value.filter(item => before.get(keyOf(item)) === item.version_id).length
})
const indirectChangeCount = computed(() => changes.value.reduce((sum, item) => sum + item.dependencyChanges.length, 0))

function typeLabel(type: string) {
  return ({ MODEL: 'Model', PROMPT: 'Prompt', SKILL: 'Skill', TOOL: 'Tool', KNOWLEDGE: 'Knowledge', MEMORY_POLICY: 'Memory' } as Record<string, string>)[type] || type
}
function kindLabel(kind: ChangeKind) {
  return ({ ADDED: '新增', REMOVED: '移除', UPGRADED: '升级', DOWNGRADED: '降级' } as Record<ChangeKind, string>)[kind]
}
function routeLabel(change: DependencyChange) {
  if (change.kind === 'ADDED') return `新增 V${change.after?.version_number}`
  if (change.kind === 'REMOVED') return `移除 V${change.before?.version_number}`
  return `V${change.before?.version_number} → V${change.after?.version_number}`
}
</script>

<template>
  <section class="release-change-list">
    <header>
      <div><p>RELEASE CHANGESET</p><h3>本次 Revision 将发生什么</h3><span>以当前已发布 Revision 为基线，对比即将发布的 Draft。这里只展示显式版本变化，不会自动升级任何资源。</span></div>
      <div class="counts"><b>{{ changes.length }}</b><small>直接变化</small><b>{{ indirectChangeCount }}</b><small>依赖变化</small></div>
    </header>

    <div v-if="!changes.length" class="no-change"><b>资源版本没有变化</b><span>{{ unchangedCount }} 项能力保持原版本。若你只调整了可用范围或运行策略，仍可继续发布。</span></div>

    <div v-else class="change-grid">
      <article v-for="change in changes" :key="`${change.resourceType}:${change.displayName}`" :class="['change-card', change.kind.toLowerCase()]">
        <div class="change-heading"><span>{{ typeLabel(change.resourceType) }}</span><em>{{ kindLabel(change.kind) }}</em></div>
        <h4>{{ change.displayName }}</h4>
        <div class="version-route">
          <template v-if="change.kind === 'ADDED'"><small>当前 Revision</small><b>未使用</b><i>→</i><small>发布后</small><b>V{{ change.after?.version_number }}</b></template>
          <template v-else-if="change.kind === 'REMOVED'"><small>当前 Revision</small><b>V{{ change.before?.version_number }}</b><i>→</i><small>发布后</small><b>移除</b></template>
          <template v-else><small>当前 Revision</small><b>V{{ change.before?.version_number }}</b><i>→</i><small>发布后</small><b>V{{ change.after?.version_number }}</b></template>
        </div>
        <p v-if="change.before && change.after && change.before.content_hash !== change.after.content_hash">内容哈希：{{ change.before.content_hash.slice(0, 8) }} → {{ change.after.content_hash.slice(0, 8) }}</p>

        <section v-if="change.dependencyChanges.length" class="dependency-changes">
          <b>这个 Skill 同时改变了依赖</b>
          <div v-for="dependency in change.dependencyChanges" :key="`${dependency.resourceType}:${dependency.displayName}`">
            <span>{{ typeLabel(dependency.resourceType) }} · {{ dependency.displayName }}</span>
            <em :class="dependency.kind.toLowerCase()">{{ kindLabel(dependency.kind) }} · {{ routeLabel(dependency) }}</em>
          </div>
        </section>
      </article>
    </div>

    <footer>
      <span>{{ unchangedCount }} 项直接能力保持不变</span>
      <strong v-if="validation?.warnings.length">{{ validation.warnings.length }} 条预检提醒，请确认后再发布</strong>
      <strong v-else>预检未发现额外提醒</strong>
    </footer>
  </section>
</template>

<style scoped>
.release-change-list{display:grid;gap:14px;padding:18px;border:1px solid #d8d5ff;border-radius:16px;background:#faf9ff}.release-change-list>header{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.release-change-list header p{margin:0;color:#6958e8;font-size:10px;font-weight:800;letter-spacing:.09em}.release-change-list h3{margin:4px 0}.release-change-list header span{display:block;max-width:720px;color:#667085;font-size:12px;line-height:1.55}.counts{display:grid;grid-template-columns:auto auto;gap:2px 8px;align-items:baseline;padding:9px 12px;border-radius:12px;background:#fff}.counts b{font-size:18px}.counts small{color:#667085;font-size:10px}.no-change{display:grid;gap:4px;padding:14px;border:1px solid #abefc6;border-radius:12px;background:#ecfdf3;color:#067647}.no-change span{font-size:12px}.change-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.change-card{padding:14px;border:1px solid #e4e7ec;border-left:4px solid #7f56d9;border-radius:12px;background:#fff}.change-card.removed,.change-card.downgraded{border-left-color:#d92d20}.change-card.added{border-left-color:#079455}.change-heading{display:flex;justify-content:space-between;gap:10px}.change-heading span{color:#475467;font-size:10px;font-weight:800}.change-heading em{font-style:normal;font-size:10px;font-weight:800;color:#6941c6}.change-card.removed .change-heading em,.change-card.downgraded .change-heading em{color:#b42318}.change-card.added .change-heading em{color:#067647}.change-card h4{margin:6px 0 10px}.version-route{display:grid;grid-template-columns:auto auto 18px auto auto;gap:6px;align-items:center;padding:8px 9px;border-radius:9px;background:#f9fafb}.version-route small{color:#667085;font-size:9px}.version-route b{font-size:11px}.version-route i{text-align:center;color:#98a2b3;font-style:normal}.change-card>p{margin:8px 0 0;color:#98a2b3;font-size:10px}.dependency-changes{display:grid;gap:6px;margin-top:11px;padding-top:10px;border-top:1px solid #eaecf0}.dependency-changes>b{font-size:11px}.dependency-changes>div{display:flex;justify-content:space-between;gap:10px;align-items:center}.dependency-changes span{font-size:10px;color:#475467}.dependency-changes em{font-size:10px;font-style:normal;font-weight:700;color:#6941c6}.dependency-changes em.added{color:#067647}.dependency-changes em.removed,.dependency-changes em.downgraded{color:#b42318}.release-change-list>footer{display:flex;justify-content:space-between;gap:12px;padding-top:10px;border-top:1px solid #e4e7ec;color:#667085;font-size:11px}.release-change-list>footer strong{color:#475467}@media(max-width:900px){.change-grid{grid-template-columns:1fr}.release-change-list>header,.release-change-list>footer{flex-direction:column}.version-route{grid-template-columns:1fr 1fr 18px 1fr 1fr}}
</style>
