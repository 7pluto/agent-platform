<script setup lang="ts">
import type { ResourceListItem, SecretRecord } from '../../api'
import SecretVaultPanel from '../../features/secrets/SecretVaultPanel.vue'

defineProps<{
  resources: ResourceListItem[]
  loading: boolean
  secrets: SecretRecord[]
  secretLoading: boolean
  secretSaving: boolean
}>()

const emit = defineEmits<{
  add: []
  open: [resource: ResourceListItem]
  refreshSecrets: []
  rotateSecret: [secret: SecretRecord, value: string]
  disableSecret: [secret: SecretRecord]
}>()

function healthLabel(value: string) {
  return ({ HEALTHY: '健康', DEGRADED: '需关注', UNHEALTHY: '异常', UNKNOWN: '未检查' } as Record<string, string>)[value] || value
}

function shortTime(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <section class="page-content">
    <div class="page-heading">
      <div>
        <p class="eyebrow">SYSTEM CONNECTIONS</p>
        <h1>系统连接</h1>
        <p>集中管理 MCP 与 RAGFlow 基础连接。连接本身不直接组装进智能体，发现后的工具或知识库才进入能力目录。</p>
      </div>
      <button class="button primary" @click="emit('add')">＋ 新增连接</button>
    </div>

    <div class="connection-summary-grid">
      <article class="product-card">
        <span>MCP</span>
        <strong>{{ resources.filter(item => item.resource_type === 'MCP_CONNECTION').length }}</strong>
        <small>发现业务工具并独立授权</small>
      </article>
      <article class="product-card">
        <span>RAGFlow</span>
        <strong>{{ resources.filter(item => item.resource_type === 'KNOWLEDGE_CONNECTION').length }}</strong>
        <small>发现数据集并注册知识库</small>
      </article>
    </div>

    <div class="resource-card-grid">
      <button v-for="item in resources" :key="item.resource_id" class="resource-card product-card" @click="emit('open', item)">
        <div class="resource-card-top">
          <span class="type-badge">{{ item.resource_type === 'MCP_CONNECTION' ? 'MCP 连接' : 'RAGFlow 连接' }}</span>
          <span :class="['status-pill', item.lifecycle_status === 'ARCHIVED' ? 'blocked' : 'success']">{{ item.lifecycle_status === 'ARCHIVED' ? '已归档' : '已发布' }}</span>
        </div>
        <h3>{{ item.display_name }}</h3>
        <p>{{ item.description || '尚未填写业务说明' }}</p>
        <div class="tag-list compact">
          <span>{{ item.source_type }}</span>
          <span>{{ healthLabel(item.health) }}</span>
          <span>V{{ item.latest_version_number || '—' }}</span>
          <span>{{ item.referenced_by_count }} 个引用</span>
        </div>
        <footer>
          <small>负责人：{{ item.owner_user_id || '历史导入' }}</small>
          <small>{{ shortTime(item.updated_at) }}</small>
        </footer>
      </button>
      <p v-if="loading" class="empty-copy">加载中…</p>
      <p v-else-if="!resources.length" class="empty-copy">尚未登记系统连接。</p>
    </div>

    <SecretVaultPanel
      :secrets="secrets"
      :loading="secretLoading"
      :saving="secretSaving"
      @refresh="emit('refreshSecrets')"
      @rotate="(secret, value) => emit('rotateSecret', secret, value)"
      @disable="secret => emit('disableSecret', secret)"
    />
  </section>
</template>
