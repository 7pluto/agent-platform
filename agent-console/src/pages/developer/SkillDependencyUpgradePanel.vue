<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

export interface VersionSnapshot {
  version_id: string
  version_number: number
  content_hash: string
  config_preview: Record<string, unknown>
}
export interface UpgradeItem {
  dependency_type: 'TOOL' | 'KNOWLEDGE'
  resource_id: string
  display_name: string
  current: VersionSnapshot
  latest: VersionSnapshot
  upgrade_available: boolean
  upgrade_allowed: boolean
  changed_fields: string[]
  message: string
}
export interface UpgradeReport {
  skill_resource_id: string
  skill_version_id: string
  skill_version_number: number
  based_on_draft: boolean
  dependencies: UpgradeItem[]
  upgrades_available: number
}

const props = defineProps<{
  resourceId: string
  toolVersionIds: string[]
  knowledgeVersionIds: string[]
  refreshSignal?: number
}>()
const emit = defineEmits<{
  upgrade: [payload: { dependencyType: 'TOOL' | 'KNOWLEDGE'; fromVersionId: string; toVersionId: string }]
  remove: [payload: { dependencyType: 'TOOL' | 'KNOWLEDGE'; currentVersionId: string; latestVersionId: string }]
  loaded: [report: UpgradeReport]
}>()

const report = ref<UpgradeReport | null>(null)
const loading = ref(false)
const error = ref('')
const expanded = ref(new Set<string>())

const pendingCount = computed(() => report.value?.dependencies.filter(item => item.upgrade_available && item.upgrade_allowed && !isLatestSelected(item)).length || 0)

function selectedIds(type: 'TOOL' | 'KNOWLEDGE') {
  return type === 'TOOL' ? props.toolVersionIds : props.knowledgeVersionIds
}
function isLatestSelected(item: UpgradeItem) {
  return selectedIds(item.dependency_type).includes(item.latest.version_id)
}
function isSelected(item: UpgradeItem) {
  const selected = selectedIds(item.dependency_type)
  return selected.includes(item.current.version_id) || selected.includes(item.latest.version_id)
}
function toggleDiff(item: UpgradeItem) {
  const next = new Set(expanded.value)
  if (next.has(item.resource_id)) next.delete(item.resource_id)
  else next.add(item.resource_id)
  expanded.value = next
}
function shortHash(value: string) { return value.slice(0, 10) }
function json(value: Record<string, unknown>) { return JSON.stringify(value, null, 2) }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/v1/developer/resources/${props.resourceId}/dependency-upgrades`, { credentials: 'same-origin' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(String(payload.message || payload.detail || payload.code || `HTTP ${response.status}`))
    report.value = payload as UpgradeReport
    emit('loaded', report.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function chooseUpgrade(item: UpgradeItem) {
  if (!item.upgrade_available || !item.upgrade_allowed || isLatestSelected(item)) return
  emit('upgrade', {
    dependencyType: item.dependency_type,
    fromVersionId: item.current.version_id,
    toVersionId: item.latest.version_id,
  })
}
function removeDependency(item: UpgradeItem) {
  emit('remove', {
    dependencyType: item.dependency_type,
    currentVersionId: item.current.version_id,
    latestVersionId: item.latest.version_id,
  })
}

watch(() => [props.resourceId, props.refreshSignal], () => void load())
onMounted(load)
</script>

<template>
  <section class="upgrade-panel">
    <header>
      <div>
        <span>DEPENDENCY VERSIONS</span>
        <h4>依赖版本</h4>
        <p>Skill 永远锁定具体 Published Version。这里可以查看差异、显式升级或移除依赖。</p>
      </div>
      <div class="upgrade-summary" :class="{ ready: pendingCount > 0 }">
        <b>{{ pendingCount }}</b>
        <small>项可升级</small>
      </div>
    </header>

    <p v-if="error" class="panel-message error">{{ error }}</p>
    <p v-else-if="loading" class="panel-message">正在检查依赖版本…</p>
    <p v-else-if="!report?.dependencies.length" class="panel-message">当前 Skill 没有 Tool / Knowledge 依赖。</p>

    <div v-else class="upgrade-list">
      <article v-for="item in report.dependencies" :key="`${item.dependency_type}:${item.resource_id}`" class="upgrade-item" :class="{ removed: !isSelected(item) }">
        <div class="upgrade-main">
          <div class="upgrade-name">
            <span>{{ item.dependency_type === 'TOOL' ? 'Tool' : 'Knowledge' }}</span>
            <div><b>{{ item.display_name }}</b><small>{{ isSelected(item) ? item.message : '已在当前编辑表单中移除，保存草稿后生效' }}</small></div>
          </div>

          <div class="version-route">
            <div><small>当前锁定</small><b>V{{ item.current.version_number }}</b><code>{{ shortHash(item.current.content_hash) }}</code></div>
            <span>→</span>
            <div :class="{ latest: item.upgrade_available }"><small>最新发布</small><b>V{{ item.latest.version_number }}</b><code>{{ shortHash(item.latest.content_hash) }}</code></div>
          </div>

          <div class="upgrade-actions">
            <button v-if="item.upgrade_available" class="diff-button" @click="toggleDiff(item)">{{ expanded.has(item.resource_id) ? '收起差异' : '查看差异' }}</button>
            <span v-else class="latest-badge">已是最新</span>
            <button v-if="item.upgrade_available && isSelected(item)" class="upgrade-button" :disabled="!item.upgrade_allowed || isLatestSelected(item)" @click="chooseUpgrade(item)">{{ isLatestSelected(item) ? `已选择 V${item.latest.version_number}` : item.upgrade_allowed ? `升级到 V${item.latest.version_number}` : '无 USE 权限' }}</button>
            <button v-if="isSelected(item)" class="remove-button" @click="removeDependency(item)">移除</button>
            <span v-else class="removed-badge">待移除</span>
          </div>
        </div>

        <div v-if="expanded.has(item.resource_id)" class="diff-area">
          <div class="changed-fields"><b>变化字段</b><span v-for="field in item.changed_fields" :key="field">{{ field }}</span><small v-if="!item.changed_fields.length">内容哈希变化，但可展示结构字段无变化</small></div>
          <div class="diff-columns">
            <section><header>V{{ item.current.version_number }} 当前</header><pre>{{ json(item.current.config_preview) }}</pre></section>
            <section><header>V{{ item.latest.version_number }} 最新</header><pre>{{ json(item.latest.config_preview) }}</pre></section>
          </div>
        </div>
      </article>
    </div>

    <footer v-if="report?.dependencies.length">升级或移除都只修改当前编辑表单；点击“保存草稿”后才写入 Skill Draft。</footer>
  </section>
</template>

<style scoped>
.upgrade-panel{margin:14px 0;padding:16px;border:1px solid #d8d5ff;border-radius:14px;background:#faf9ff}.upgrade-panel>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.upgrade-panel>header span{color:#6941c6;font-size:10px;font-weight:800;letter-spacing:.08em}.upgrade-panel h4{margin:3px 0 4px;font-size:16px}.upgrade-panel p{margin:0;color:#667085;font-size:12px;line-height:1.5}.upgrade-summary{min-width:70px;padding:8px 10px;border-radius:10px;background:#f2f4f7;text-align:center}.upgrade-summary.ready{background:#fffaeb;color:#b54708}.upgrade-summary b,.upgrade-summary small{display:block}.upgrade-summary b{font-size:20px}.upgrade-summary small{font-size:10px}.panel-message{padding:20px;text-align:center}.panel-message.error{color:#b42318}.upgrade-list{display:grid;gap:10px;margin-top:14px}.upgrade-item{overflow:hidden;border:1px solid #e4e7ec;border-radius:12px;background:#fff}.upgrade-item.removed{opacity:.62}.upgrade-main{padding:13px;display:grid;grid-template-columns:minmax(180px,1.2fr) minmax(230px,1fr) auto;gap:14px;align-items:center}.upgrade-name{display:flex;gap:9px;align-items:flex-start}.upgrade-name>span{padding:4px 7px;border-radius:999px;background:#eeebff;color:#5925dc;font-size:10px;font-weight:800}.upgrade-name div{display:grid;gap:3px}.upgrade-name small{color:#667085}.version-route{display:flex;align-items:center;justify-content:center;gap:9px}.version-route>div{display:grid;gap:2px;min-width:78px;padding:7px 9px;border-radius:8px;background:#f9fafb}.version-route>div.latest{background:#ecfdf3}.version-route small{color:#667085;font-size:9px}.version-route code{color:#98a2b3;font-size:9px}.upgrade-actions{display:flex;gap:7px;align-items:center;justify-content:flex-end}.upgrade-actions button{border:0;border-radius:8px;padding:8px 10px;font-size:11px;font-weight:700;cursor:pointer}.diff-button{background:#f2f4f7;color:#344054}.upgrade-button{background:#5b4ee5;color:#fff}.upgrade-button:disabled{opacity:.45;cursor:default}.remove-button{background:#fef3f2;color:#b42318}.latest-badge,.removed-badge{padding:5px 8px;border-radius:999px;font-size:10px;font-weight:700}.latest-badge{background:#ecfdf3;color:#067647}.removed-badge{background:#f2f4f7;color:#667085}.diff-area{padding:13px;border-top:1px solid #eaecf0;background:#fcfcfd}.changed-fields{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:10px}.changed-fields b{font-size:11px}.changed-fields span{padding:3px 6px;border-radius:6px;background:#fff4ed;color:#b93815;font-size:10px}.changed-fields small{color:#667085}.diff-columns{display:grid;grid-template-columns:1fr 1fr;gap:10px}.diff-columns section{min-width:0;border:1px solid #e4e7ec;border-radius:9px;background:#fff}.diff-columns header{padding:7px 9px;border-bottom:1px solid #eaecf0;font-size:11px;font-weight:800}.diff-columns pre{max-height:230px;overflow:auto;margin:0;padding:10px;white-space:pre-wrap;word-break:break-all;color:#344054;font-size:10px;line-height:1.5}.upgrade-panel>footer{margin-top:10px;color:#6941c6;font-size:11px;font-weight:600}@media(max-width:900px){.upgrade-main{grid-template-columns:1fr}.version-route{justify-content:flex-start}.upgrade-actions{justify-content:flex-start}.diff-columns{grid-template-columns:1fr}}
</style>
