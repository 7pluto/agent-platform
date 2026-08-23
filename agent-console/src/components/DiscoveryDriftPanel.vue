<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, type CatalogItem, type DiscoverySnapshot, type DriftReport } from '../api'

const props = defineProps<{ versions: CatalogItem[]; csrf: string; supported: boolean }>()

const snapshots = ref<DiscoverySnapshot[]>([])
const report = ref<DriftReport | null>(null)
const loading = ref(false)
const error = ref('')

const publishedVersion = computed(() => [...props.versions]
  .filter(item => item.status === 'PUBLISHED')
  .sort((a, b) => b.version_number - a.version_number)[0])
const snapshot = computed(() => snapshots.value[0])

const statusText: Record<string, string> = {
  NO_CHANGE: '上游定义未变化',
  CHANGED: '发现上游变更',
  MISSING: '上游对象已不存在',
  UNAVAILABLE: '暂时无法连接上游',
}

function shapeSummary(value?: DiscoverySnapshot | null) {
  if (!value) return '尚未生成发布快照'
  const body = value.snapshot
  if (value.provider === 'DIFY') return `Dify ${String(body.flow_type || 'Flow')} · ${Array.isArray(body.input_form) ? body.input_form.length : 0} 个输入`
  if (value.provider === 'MCP') return `MCP Tool · ${String(body.tool_name || value.external_id)}`
  if (value.provider === 'RAGFLOW') return `RAGFlow Dataset · ${String(body.dataset_name || value.external_id)}`
  if (value.provider === 'HTTP') return `${String(body.method || 'HTTP')} ${String(body.path || '/')}`
  return `${value.provider} · ${value.external_type}`
}

async function load() {
  report.value = null
  error.value = ''
  if (!props.supported || !publishedVersion.value) { snapshots.value = []; return }
  try { snapshots.value = await api.listDiscoverySnapshots(publishedVersion.value.version_id) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '加载发布快照失败' }
}

async function check() {
  if (!publishedVersion.value) return
  loading.value = true; error.value = ''
  try {
    report.value = await api.checkResourceDrift(publishedVersion.value.version_id, props.csrf, true)
    snapshots.value = await api.listDiscoverySnapshots(publishedVersion.value.version_id)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '检查上游变化失败' }
  finally { loading.value = false }
}

watch(() => [publishedVersion.value?.version_id, props.supported], load, { immediate: true })
</script>

<template>
  <section v-if="supported" class="drift-panel">
    <div class="drift-heading">
      <div>
        <h3>上游定义与漂移</h3>
        <p>发布版本保持不变；检测到变化时自动生成待审核的新草稿。</p>
      </div>
      <button class="drift-button" :disabled="loading || !publishedVersion" @click="check">
        {{ loading ? '检查中…' : '检查上游变化' }}
      </button>
    </div>
    <div class="snapshot-card">
      <span class="provider-badge">{{ snapshot?.provider || '未快照' }}</span>
      <b>{{ shapeSummary(snapshot) }}</b>
      <small v-if="snapshot">发布指纹 {{ snapshot.schema_hash.slice(0, 12) }} · {{ new Date(snapshot.created_at).toLocaleString('zh-CN') }}</small>
      <small v-else>首次检查时会根据当前 Published Version 建立基线。</small>
    </div>
    <div v-if="report" class="drift-result" :data-status="report.status">
      <b>{{ statusText[report.status] }}</b>
      <p v-if="report.status === 'CHANGED' && report.draft_version_id">已创建新的 Draft Version，旧发布版本和既有 Run Manifest 均未修改。</p>
      <p v-else-if="report.message">{{ report.message }}</p>
      <p v-else>当前上游定义与发布快照一致。</p>
    </div>
    <p v-if="error" class="drift-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.drift-panel { display: grid; gap: 12px; }
.drift-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.drift-heading h3 { margin: 0 0 4px; }
.drift-heading p, .snapshot-card small, .drift-result p { margin: 0; color: #667085; }
.drift-button { border: 0; border-radius: 10px; padding: 9px 14px; color: white; background: #5b4ee5; cursor: pointer; white-space: nowrap; }
.drift-button:disabled { opacity: .55; cursor: default; }
.snapshot-card, .drift-result { display: grid; gap: 6px; padding: 14px; border: 1px solid #e4e7ec; border-radius: 12px; background: #fafbff; }
.provider-badge { width: fit-content; padding: 3px 8px; border-radius: 999px; color: #5145cd; background: #eeeaff; font-size: 12px; font-weight: 700; }
.drift-result[data-status='CHANGED'] { border-color: #fdb022; background: #fffaeb; }
.drift-result[data-status='MISSING'], .drift-result[data-status='UNAVAILABLE'] { border-color: #f97066; background: #fff4f3; }
.drift-result[data-status='NO_CHANGE'] { border-color: #32d583; background: #ecfdf3; }
.drift-error { margin: 0; color: #b42318; }
</style>
