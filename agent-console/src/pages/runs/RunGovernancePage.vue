<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RunDetail, RunObservabilitySummary, RunRecord } from '../../api'

const props = defineProps<{
  runs: RunRecord[]
  summary: RunObservabilitySummary | null
  selected: RunDetail | null
  loading: boolean
}>()

const emit = defineEmits<{ refresh: []; open: [run: RunRecord]; close: [] }>()
const query = ref('')
const status = ref('ALL')
const rawOpen = ref(false)

const filteredRuns = computed(() => props.runs.filter(run => {
  const matchesStatus = status.value === 'ALL' || run.status === status.value
  const text = `${run.run_id} ${run.message} ${run.user_id} ${run.deployment_id}`.toLowerCase()
  return matchesStatus && text.includes(query.value.trim().toLowerCase())
}))

function shortTime(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
function shortId(value?: string) { return value ? `${value.slice(0, 8)}…` : '—' }
function statusLabel(value: string) {
  return ({ PENDING: '等待执行', RUNNING: '执行中', COMPLETED: '已完成', FAILED: '失败', CANCELLED: '已取消' } as Record<string, string>)[value] || value
}
function eventTitle(value: string) {
  return ({
    'run.created': 'Run 已创建', 'run.claimed': 'Worker 已领取', 'run.started': '开始执行', 'run.completed': 'Run 已完成', 'run.failed': 'Run 失败',
    'manifest.created': 'Manifest 已冻结', 'manifest.resources.resolved': '能力版本已解析', 'runtime.started': '运行时已启动',
    'runtime.capabilities.registered': '权限裁剪完成', 'conversation.history.loaded': '会话历史已加载', 'skills.loaded': 'Skill 已加载', 'memory.read': '长期记忆已加载',
    'tool.started': '调用业务能力', 'tool.completed': '业务能力返回', 'tool.denied': '能力权限拒绝', 'rag.retrieved': '知识检索完成',
    'dify.flow.completed': 'Dify Flow 完成', 'dify.rag.retrieved': 'Dify RAG 命中', 'runtime.output': '最终回答已生成', 'runtime.failed': '运行时失败',
  } as Record<string, string>)[value] || value
}
function eventSummary(event: RunDetail['events'][number]) {
  const data = event.data
  if (event.event === 'runtime.capabilities.registered') return `${data.tool_count || 0} 项可用，${data.filtered_capability_count || 0} 项因权限过滤`
  if (event.event === 'tool.started' || event.event === 'tool.completed') return String(data.tool || '业务能力')
  if (event.event === 'tool.denied') return String(data.message || '当前账号没有使用该能力的权限')
  if (event.event === 'rag.retrieved') return `${data.provider || 'Knowledge'} · ${data.chunk_count || 0} 条命中`
  if (event.event === 'memory.read') return `${data.count || 0} 条长期记忆`
  if (event.event === 'conversation.history.loaded') return `${data.count || 0} 条历史消息${data.trimmed ? ' · 已裁剪' : ''}`
  if (event.event === 'runtime.output') return String(data.content || '').slice(0, 160)
  if (event.event === 'runtime.failed') return `${data.code || 'RUNTIME_EXECUTION_FAILED'} · ${data.error_type || ''}`
  return Object.keys(data).length ? Object.entries(data).slice(0, 3).map(([key, value]) => `${key}: ${String(value)}`).join(' · ') : '已记录'
}
</script>

<template>
  <section class="page-content run-governance-page">
    <div class="page-heading">
      <div><p class="eyebrow">RUN GOVERNANCE</p><h1>运行治理</h1><p>按 Run 查看状态、实际能力调用、权限裁剪、知识命中、Memory、Manifest 与故障原因。</p></div>
      <button class="button ghost" :disabled="loading" @click="emit('refresh')">{{ loading ? '刷新中…' : '刷新运行数据' }}</button>
    </div>
    <div class="run-summary-grid">
      <article class="product-card"><span>采样 Run</span><strong>{{ summary?.sampled_runs || 0 }}</strong><small>当前治理窗口</small></article>
      <article class="product-card"><span>完成率</span><strong>{{ summary?.completion_rate == null ? '—' : `${(summary.completion_rate * 100).toFixed(1)}%` }}</strong><small>{{ summary?.failed_runs || 0 }} 个失败</small></article>
      <article class="product-card"><span>实际工具调用</span><strong>{{ summary?.tool_calls || 0 }}</strong><small>{{ summary?.rag_retrievals || 0 }} 次知识检索</small></article>
      <article class="product-card"><span>权限拒绝</span><strong>{{ summary?.denied_capability_calls || 0 }}</strong><small>只统计实际调用</small></article>
    </div>
    <div class="filter-bar product-card"><input v-model="query" placeholder="搜索问题、Run ID、用户或 Deployment" /><select v-model="status"><option value="ALL">全部状态</option><option value="PENDING">等待执行</option><option value="RUNNING">执行中</option><option value="COMPLETED">已完成</option><option value="FAILED">失败</option><option value="CANCELLED">已取消</option></select></div>
    <div class="run-governance-layout">
      <section class="run-list product-card">
        <button v-for="run in filteredRuns" :key="run.run_id" :class="{ active: selected?.run.run_id === run.run_id }" @click="emit('open', run)">
          <span><b>{{ run.message }}</b><small>{{ shortTime(run.created_at) }} · {{ run.user_id }}</small></span>
          <em :class="['status-pill', run.status === 'FAILED' ? 'blocked' : run.status === 'COMPLETED' ? 'success' : '']">{{ statusLabel(run.status) }}</em>
        </button>
        <p v-if="!filteredRuns.length" class="empty-copy">当前筛选下没有 Run。</p>
      </section>
      <section v-if="selected" class="run-detail-workspace">
        <article class="product-card run-detail-heading"><div><button class="text-link" @click="emit('close')">关闭详情</button><p class="eyebrow">RUN {{ shortId(selected.run.run_id) }}</p><h2>{{ selected.run.message }}</h2><p>{{ selected.run.user_id }} · {{ shortTime(selected.run.created_at) }}</p></div><span :class="['status-pill', selected.run.status === 'FAILED' ? 'blocked' : 'success']">{{ statusLabel(selected.run.status) }}</span></article>
        <article class="product-card run-manifest-summary"><h3>执行快照</h3><dl><div><dt>Manifest Hash</dt><dd>{{ shortId(selected.manifest.manifest_hash) }}</dd></div><div><dt>Runtime</dt><dd>{{ selected.manifest.harness.type }} · {{ selected.manifest.harness.version }}</dd></div><div><dt>Deployment Revision</dt><dd>{{ shortId(selected.manifest.deployment_revision_id) }}</dd></div><div><dt>不可变资源</dt><dd>{{ selected.manifest.resources.length }} 项</dd></div></dl><div class="tag-list compact"><span v-for="item in selected.manifest.resources" :key="`${item.type}-${item.version_id}`">{{ item.type }}</span></div></article>
        <article class="product-card run-readable-timeline"><div class="section-heading"><div><h3>运行时间线</h3><p>默认展示可读摘要；原始数据已经过统一脱敏和限长。</p></div><button class="button ghost" @click="rawOpen = !rawOpen">{{ rawOpen ? '收起原始事件' : '查看原始事件' }}</button></div>
          <ol><li v-for="event in selected.events" :key="event.sequence"><span>{{ event.sequence }}</span><div><b>{{ eventTitle(event.event) }}</b><p>{{ eventSummary(event) }}</p><small>{{ shortTime(event.occurred_at) }}</small><pre v-if="rawOpen">{{ JSON.stringify(event.data, null, 2) }}</pre></div></li></ol>
        </article>
      </section>
      <div v-else class="empty-panel">选择一个 Run 查看完整运行快照与时间线。</div>
    </div>
  </section>
</template>

<style scoped>
.run-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
.run-summary-grid article { padding: 18px; display: grid; gap: 7px; }
.run-summary-grid span, .run-summary-grid small { color: var(--muted); }
.run-summary-grid strong { font-size: 28px; }
.filter-bar { display: grid; grid-template-columns: minmax(240px, 1fr) 190px; gap: 12px; padding: 14px; }
.run-governance-layout { display: grid; grid-template-columns: minmax(300px, .72fr) minmax(0, 1.55fr); gap: 18px; margin-top: 18px; align-items: start; }
.run-list { overflow: hidden; }
.run-list > button { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 16px; border: 0; border-bottom: 1px solid var(--border); background: transparent; text-align: left; cursor: pointer; }
.run-list > button:hover, .run-list > button.active { background: var(--surface-muted); }
.run-list span { display: grid; gap: 5px; min-width: 0; }
.run-list b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-list small { color: var(--muted); }
.run-detail-workspace { display: grid; gap: 16px; min-width: 0; }
.run-detail-heading { padding: 20px; display: flex; justify-content: space-between; gap: 16px; }
.run-manifest-summary, .run-readable-timeline { padding: 20px; }
.run-manifest-summary dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.run-manifest-summary dl > div { padding: 12px; border-radius: 12px; background: var(--surface-muted); }
.run-manifest-summary dt { color: var(--muted); font-size: 12px; }
.run-manifest-summary dd { margin: 5px 0 0; font-weight: 700; overflow-wrap: anywhere; }
.run-readable-timeline ol { list-style: none; padding: 0; margin: 18px 0 0; display: grid; gap: 0; }
.run-readable-timeline li { display: grid; grid-template-columns: 34px 1fr; gap: 12px; padding-bottom: 18px; }
.run-readable-timeline li > span { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; color: var(--primary); background: var(--primary-soft); font-size: 12px; font-weight: 800; }
.run-readable-timeline li > div { border-bottom: 1px solid var(--border); padding-bottom: 14px; min-width: 0; }
.run-readable-timeline p { color: var(--muted); margin: 6px 0; overflow-wrap: anywhere; }
.run-readable-timeline small { color: var(--muted); }
.run-readable-timeline pre { max-height: 300px; overflow: auto; padding: 12px; border-radius: 10px; background: #111827; color: #e5e7eb; font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 1100px) { .run-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .run-governance-layout { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .run-summary-grid, .filter-bar, .run-manifest-summary dl { grid-template-columns: 1fr; } }
</style>
