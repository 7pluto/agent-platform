<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SecretRecord } from '../../api'

const props = defineProps<{
  secrets: SecretRecord[]
  loading: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  refresh: []
  rotate: [secret: SecretRecord, value: string]
  disable: [secret: SecretRecord]
}>()

const selected = ref<SecretRecord | null>(null)
const value = ref('')
const activeCount = computed(() => props.secrets.filter(item => item.status === 'ACTIVE').length)

function shortTime(input?: string) {
  if (!input) return '尚未使用'
  const date = new Date(input)
  return Number.isNaN(date.getTime()) ? input : date.toLocaleString('zh-CN', { hour12: false })
}

function fingerprint(value: string) {
  return value ? `${value.slice(0, 8)}…${value.slice(-6)}` : '—'
}

function beginRotate(secret: SecretRecord) {
  selected.value = secret
  value.value = ''
}

function close() {
  if (props.saving) return
  selected.value = null
  value.value = ''
}

function submit() {
  if (!selected.value || !value.value.trim()) return
  const secret = selected.value
  const nextValue = value.value
  selected.value = null
  value.value = ''
  emit('rotate', secret, nextValue)
}
</script>

<template>
  <section class="secret-vault product-card">
    <header class="secret-vault-heading">
      <div>
        <p class="eyebrow">CREDENTIAL VAULT</p>
        <h2>凭据保险库</h2>
        <p>统一治理模型、Dify、MCP、RAGFlow 和企业接口凭据。平台只展示不可逆指纹，永不回显密钥值。</p>
      </div>
      <div class="secret-vault-actions">
        <span class="status-pill success">{{ activeCount }} 个生效中</span>
        <button class="button ghost" :disabled="loading" @click="emit('refresh')">刷新</button>
      </div>
    </header>

    <div class="secret-card-grid">
      <article v-for="item in secrets" :key="item.secret_id" class="secret-card">
        <div class="resource-card-top">
          <span class="type-badge">平台托管凭据</span>
          <span :class="['status-pill', item.status === 'ACTIVE' ? 'success' : 'blocked']">
            {{ item.status === 'ACTIVE' ? '生效中' : '已停用' }}
          </span>
        </div>
        <h3>{{ item.name }}</h3>
        <dl>
          <dt>安全指纹</dt><dd>{{ fingerprint(item.fingerprint) }}</dd>
          <dt>最近使用</dt><dd>{{ shortTime(item.last_used_at) }}</dd>
          <dt>最近轮换</dt><dd>{{ item.rotated_at ? shortTime(item.rotated_at) : '尚未轮换' }}</dd>
          <dt>创建人</dt><dd>{{ item.created_by }}</dd>
        </dl>
        <footer>
          <button class="button ghost" :disabled="item.status !== 'ACTIVE'" @click="beginRotate(item)">轮换凭据</button>
          <button class="button danger" :disabled="item.status !== 'ACTIVE' || saving" @click="emit('disable', item)">停用</button>
        </footer>
      </article>
      <p v-if="loading" class="empty-copy">正在读取凭据目录…</p>
      <p v-else-if="!secrets.length" class="empty-copy">尚无平台托管凭据。新增模型或外部连接后会自动登记在这里。</p>
    </div>
  </section>

  <div v-if="selected" class="modal-backdrop" @click.self="close">
    <section class="modal-card compact-modal">
      <header>
        <div><p class="eyebrow">ROTATE CREDENTIAL</p><h2>轮换凭据</h2></div>
        <button class="icon-button" aria-label="关闭" @click="close">×</button>
      </header>
      <p>正在轮换“{{ selected.name }}”。已发布资源继续引用同一个安全标识，无需修改 Agent 配置或重新发布。</p>
      <label>新密钥值
        <input v-model="value" type="password" autocomplete="new-password" placeholder="仅本次提交，不会再次显示" @keyup.enter="submit" />
      </label>
      <p class="field-hint">提交后旧值立即失效；审计日志只记录新指纹，不记录密钥内容。</p>
      <footer class="modal-actions">
        <button class="button ghost" :disabled="saving" @click="close">取消</button>
        <button class="button primary" :disabled="saving || !value.trim()" @click="submit">{{ saving ? '轮换中…' : '确认轮换' }}</button>
      </footer>
    </section>
  </div>
</template>
