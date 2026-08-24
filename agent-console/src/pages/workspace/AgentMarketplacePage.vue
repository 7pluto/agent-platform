<script setup lang="ts">
import type { AgentWorkbenchItem } from '../../api'

defineProps<{ agents: AgentWorkbenchItem[]; query: string; loading: boolean }>()
const emit = defineEmits<{ 'update:query': [value: string]; open: [agent: AgentWorkbenchItem] }>()

function shortTime(value?: string) { if (!value) return '暂无'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }
function typeLabel(value: string) { return ({ MODEL: '模型', PROMPT: '提示词', SKILL: '技能', TOOL: '工具', KNOWLEDGE: '知识库', MEMORY_POLICY: '记忆' } as Record<string, string>)[value] || value }
</script>

<template>
  <section class="page-content">
    <div class="page-hero"><div><p class="eyebrow">AGENT WORKSPACE</p><h1>选择一个智能体开始工作</h1><p>智能体按你的租户和权限提供模型、知识、工具与记忆能力。</p></div></div>
    <div class="toolbar"><div><h2>智能体广场</h2><span>{{ agents.filter(item => item.active).length }} 个可用智能体</span></div><input :value="query" placeholder="搜索智能体名称或用途" @input="emit('update:query', ($event.target as HTMLInputElement).value)" /></div>
    <div v-if="loading" class="empty-panel">正在加载智能体…</div>
    <div v-else-if="!agents.length" class="empty-panel">当前没有可用智能体。</div>
    <div v-else class="agent-grid">
      <article v-for="item in agents" :key="item.deployment_id" class="agent-card product-card">
        <div class="agent-card-top"><div class="agent-logo">{{ item.display_name.slice(0, 1) }}</div><span :class="['status-pill', item.active ? 'success' : 'neutral']">{{ item.active ? '已启用' : '未启用' }}</span></div>
        <h3>{{ item.display_name }}</h3><p>{{ item.description || '面向企业任务的智能体' }}</p>
        <div class="tag-list"><span v-for="(count, type) in item.capability_counts" :key="type">{{ count }} {{ typeLabel(type) }}</span></div>
        <footer><small>最近运行：{{ shortTime(item.last_run_at) }}</small><button class="button primary" :disabled="!item.active" @click="emit('open', item)">开始对话</button></footer>
      </article>
    </div>
  </section>
</template>
