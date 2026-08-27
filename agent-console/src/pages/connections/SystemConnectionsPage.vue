<script setup lang="ts">
import { ref } from 'vue'
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

const installingDemoMcp = ref(false)
const installNotice = ref('')
const installError = ref('')

function healthLabel(value: string) {
  return ({ HEALTHY: '健康', DEGRADED: '需关注', UNHEALTHY: '异常', UNKNOWN: '未检查' } as Record<string, string>)[value] || value
}

function shortTime(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function installDemoMcps() {
  if (installingDemoMcp.value) return
  installingDemoMcp.value = true
  installNotice.value = ''
  installError.value = ''
  try {
    const sessionResponse = await fetch('/api/v1/auth/session', { credentials: 'same-origin' })
    if (!sessionResponse.ok) throw new Error('登录会话已失效')
    const session = await sessionResponse.json() as { csrf_token: string }
    const response = await fetch('/api/v1/admin/common-mcp/install', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': session.csrf_token },
    })
    const payload = await response.json().catch(() => ({})) as {
      created_connections?: number
      existing_connections?: number
      created_tools?: number
      existing_tools?: number
      failed?: number
      message?: string
      detail?: string
    }
    if (!response.ok) throw new Error(payload.message || payload.detail || `HTTP ${response.status}`)
    installNotice.value = `MCP 已处理：连接新增 ${payload.created_connections || 0} / 已有 ${payload.existing_connections || 0}，Tool 新增 ${payload.created_tools || 0} / 已有 ${payload.existing_tools || 0}`
    if (payload.failed) {
      installError.value = `${payload.failed} 个 MCP 服务安装失败，请确认 demo-crm-mcp、demo-ticket-mcp、demo-ops-mcp 已随 Docker Compose 启动。`
    } else {
      window.setTimeout(() => window.location.reload(), 900)
    }
  } catch (err) {
    installError.value = err instanceof Error ? err.message : String(err)
  } finally {
    installingDemoMcp.value = false
  }
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
      <div class="connection-actions">
        <button class="button ghost" :disabled="installingDemoMcp" @click="installDemoMcps">{{ installingDemoMcp ? '正在发现 MCP…' : '安装演示 MCP' }}</button>
        <button class="button primary" @click="emit('add')">＋ 新增连接</button>
      </div>
    </div>

    <div class="demo-mcp-hint product-card">
      <div><span>DEVELOPMENT STARTER</span><b>CRM · 工单 · 运维</b><small>一键建立 3 个只读 MCP Connection，并通过真实 tools/list 将 8 个能力纳管为 Tool Resource。</small></div>
      <p v-if="installNotice" class="install-notice">{{ installNotice }}</p>
      <p v-if="installError" class="install-error">{{ installError }}</p>
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

<style scoped>
.connection-actions{display:flex;gap:8px;align-items:center}.demo-mcp-hint{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px;margin-bottom:14px}.demo-mcp-hint>div{display:grid;gap:3px}.demo-mcp-hint span{color:#7f56d9;font-size:10px;font-weight:800;letter-spacing:.08em}.demo-mcp-hint small{color:#667085}.install-notice,.install-error{margin:0;padding:8px 10px;border-radius:9px;font-size:11px}.install-notice{background:#ecfdf3;color:#067647}.install-error{background:#fef3f2;color:#b42318}@media(max-width:760px){.connection-actions,.demo-mcp-hint{align-items:stretch;flex-direction:column}.connection-actions button{width:100%}}
</style>
