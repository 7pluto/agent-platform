<script setup lang="ts">
import type { AgentWorkbenchItem, CatalogItem, ResourceListItem, RunObservabilitySummary } from '../../api'

defineProps<{ agents: AgentWorkbenchItem[]; resources: ResourceListItem[]; catalog: CatalogItem[]; observability: RunObservabilitySummary | null }>()
const emit = defineEmits<{ refreshObservability: []; showAgents: []; openAgent: [agent: AgentWorkbenchItem] }>()
</script>

<template>
  <section class="page-content">
    <div class="page-hero compact"><div><p class="eyebrow">ADMIN OVERVIEW</p><h1>智能体运营概览</h1><p>从资源、智能体、知识和运行四个维度管理企业 AI 能力。</p></div></div>
    <div class="metric-grid">
      <article class="metric product-card"><small>已部署智能体</small><strong>{{ agents.filter(item => item.active).length }}</strong><span>可供业务用户使用</span></article>
      <article class="metric product-card"><small>资源 Definition</small><strong>{{ resources.length }}</strong><span>可版本化、可授权</span></article>
      <article class="metric product-card"><small>已发布版本</small><strong>{{ catalog.length }}</strong><span>可被 Agent 组装</span></article>
      <article class="metric product-card"><small>需要关注</small><strong>{{ resources.filter(item => item.health === 'UNHEALTHY' || item.health === 'DEGRADED').length }}</strong><span>异常或需关注的资源</span></article>
    </div>
    <section class="product-card overview-section observability-panel">
      <div class="section-heading"><div><h2>运行观测</h2><p>仅汇总状态与事件计数，不显示对话内容、工具参数或密钥。</p></div><button class="button ghost" @click="emit('refreshObservability')">刷新指标</button></div>
      <div v-if="observability" class="metric-grid compact-metrics">
        <article class="metric"><small>采样 Run</small><strong>{{ observability.sampled_runs }}</strong><span>最近租户运行记录</span></article>
        <article class="metric"><small>完成率</small><strong>{{ observability.completion_rate == null ? '—' : `${Math.round(observability.completion_rate * 100)}%` }}</strong><span>终态 {{ observability.terminal_runs }} 次</span></article>
        <article class="metric"><small>平均耗时</small><strong>{{ observability.average_duration_ms == null ? '—' : `${(observability.average_duration_ms / 1000).toFixed(1)}s` }}</strong><span>从启动到终态</span></article>
        <article class="metric"><small>能力调用</small><strong>{{ observability.tool_calls }}</strong><span>RAG {{ observability.rag_retrievals }} · 拒绝 {{ observability.denied_capability_calls }}</span></article>
      </div>
      <p v-else class="muted">暂无可展示的运行观测数据，或当前账号无管理权限。</p>
    </section>
    <section class="product-card overview-section"><div class="section-heading"><div><h2>最近智能体</h2><p>进入配置查看能力组合、版本与运行。</p></div><button class="button ghost" @click="emit('showAgents')">查看全部</button></div><div class="simple-list"><button v-for="item in agents.slice(0, 5)" :key="item.deployment_id" @click="emit('openAgent', item)"><span class="list-avatar">{{ item.display_name.slice(0, 1) }}</span><span><b>{{ item.display_name }}</b><small>{{ item.deployment_name }} · Revision {{ item.revision_number || '—' }}</small></span><em>{{ item.active ? '已启用' : '未启用' }}</em></button></div></section>
  </section>
</template>
