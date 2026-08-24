<script setup lang="ts">
import type { IngestJob, KnowledgeDocument, KnowledgeIndex, KnowledgeOverview, ResourceListItem } from '../../api'

type RetrievalHit = { document_id: string; chunk_number: number; content: string; score: number; title?: string; source?: string }
type ProviderFilter = 'ALL' | 'LOCAL' | 'RAGFLOW' | 'REMOTE_HTTP'

defineProps<{
  resources: ResourceListItem[]
  selected: KnowledgeOverview | null
  busy: boolean
  query: string
  providerFilter: ProviderFilter
  providerOptions: ReadonlyArray<{ readonly v: ProviderFilter; readonly n: string }>
  documents: KnowledgeDocument[]
  jobs: IngestJob[]
  indexes: KnowledgeIndex[]
  hits: RetrievalHit[]
  retrievalQuery: string
  uploadOpen: boolean
  file: File | null
}>()

const emit = defineEmits<{
  'update:query': [value: string]
  'update:providerFilter': [value: ProviderFilter]
  'update:retrievalQuery': [value: string]
  'update:uploadOpen': [value: boolean]
  refresh: []
  add: []
  open: [resource: ResourceListItem]
  build: []
  retrieve: []
  chooseFile: [event: Event]
  upload: []
}>()

function shortTime(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <section class="page-content knowledge-operations">
    <div class="page-heading">
      <div><p class="eyebrow">KNOWLEDGE CENTER</p><h1>知识库</h1><p>统一管理平台文件、RAGFlow 数据集和企业知识 API，并按 Provider 展示对应运营能力。</p></div>
      <div class="row-actions"><button class="button ghost" :disabled="busy" @click="emit('refresh')">刷新当前知识库</button><button class="button primary" @click="emit('add')">＋ 添加知识库</button></div>
    </div>
    <div class="knowledge-layout">
      <aside class="knowledge-sidebar product-card">
        <input :value="query" placeholder="搜索知识库" @input="emit('update:query', ($event.target as HTMLInputElement).value)" />
        <div class="knowledge-provider-tabs"><button v-for="item in providerOptions" :key="item.v" :class="{ active: providerFilter === item.v }" @click="emit('update:providerFilter', item.v)">{{ item.n }}</button></div>
        <button v-for="item in resources" :key="item.resource_id" :class="{ active: selected?.resource_id === item.resource_id }" @click="emit('open', item)"><span><b>{{ item.display_name }}</b><small>{{ item.description || item.slug }}</small></span><em>V{{ item.latest_version_number || '—' }}</em></button>
        <p v-if="!resources.length" class="empty-copy">当前筛选下没有知识库，可直接点击“添加知识库”。</p>
      </aside>
      <section v-if="selected" class="knowledge-workspace">
        <article class="product-card knowledge-summary">
          <div><p class="eyebrow">{{ selected.active_index_status || '尚无活跃索引' }}</p><h2>{{ selected.display_name }}</h2><p>{{ selected.description || '未填写用途说明' }}</p></div>
          <div class="detail-metrics"><span><b>{{ selected.document_count }}</b>文档</span><span><b>{{ selected.chunk_count }}</b>分块</span><span><b>V{{ selected.active_index_version || '—' }}</b>活跃索引</span></div>
        </article>
        <article v-if="selected.provider !== 'LOCAL'" class="product-card provider-source-card">
          <p class="eyebrow">{{ selected.provider_display_name }}</p><h3>外部知识库</h3><p>{{ selected.source_summary || '该知识库由外部连接提供实时检索。' }}</p>
          <dl class="provider-facts"><div><dt>连接</dt><dd>{{ selected.connection_display_name || '由平台托管' }}</dd></div><div><dt>可执行操作</dt><dd>检索测试、权限管理、使用情况、连接状态</dd></div></dl>
        </article>
        <div class="knowledge-action-grid">
          <article v-if="selected.provider === 'LOCAL'" class="product-card"><h3>1. 上传文档</h3><p>仅接受 PDF、DOCX；文件由后端校验并写入 MinIO。</p><button class="button primary" :disabled="busy" @click="emit('update:uploadOpen', true)">上传文档</button></article>
          <article v-if="selected.provider === 'LOCAL'" class="product-card"><h3>2. 构建索引</h3><p>构建新的不可变 Index Version，成功后原子激活。</p><button class="button primary" :disabled="busy || !documents.length" @click="emit('build')">开始 Ingest / 构建索引</button></article>
          <article class="product-card"><h3>{{ selected.provider === 'LOCAL' ? '3.' : '1.' }} 检索测试</h3><p>验证当前知识来源的真实召回内容和相似度。</p><textarea :value="retrievalQuery" rows="3" placeholder="输入要检索的业务问题" @input="emit('update:retrievalQuery', ($event.target as HTMLTextAreaElement).value)" /><button class="button primary" :disabled="busy || !retrievalQuery.trim()" @click="emit('retrieve')">执行检索</button></article>
        </div>
        <div v-if="uploadOpen && selected.provider === 'LOCAL'" class="modal-backdrop" @click.self="emit('update:uploadOpen', false)">
          <section class="compact-modal" role="dialog" aria-modal="true" aria-label="上传知识文档">
            <header><div><p class="eyebrow">UPLOAD DOCUMENT</p><h2>上传知识文档</h2><p>服务端校验类型并保存到 MinIO，浏览器不会直接访问对象存储。</p></div><button class="icon-button" aria-label="关闭" @click="emit('update:uploadOpen', false)">×</button></header>
            <div class="compact-modal-body"><label>选择 PDF 或 DOCX<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="emit('chooseFile', $event)" /></label><p v-if="file" class="field-hint">已选：{{ file.name }}</p><p v-else class="field-hint">单个文件将在登记后显示在当前知识库文档列表中。</p></div>
            <footer><button class="button ghost" :disabled="busy" @click="emit('update:uploadOpen', false)">取消</button><button class="button primary" :disabled="busy || !file" @click="emit('upload')">{{ busy ? '上传中…' : '上传并登记' }}</button></footer>
          </section>
        </div>
        <article v-if="selected.provider === 'LOCAL'" class="product-card knowledge-table"><div class="section-heading"><div><h2>文档</h2><p>查看解析和安全校验状态。</p></div></div><table><thead><tr><th>文件名</th><th>状态</th><th>上传时间</th></tr></thead><tbody><tr v-for="item in documents" :key="item.document_id"><td>{{ item.filename }}</td><td><span class="status-pill">{{ item.status }}</span></td><td>{{ shortTime(item.created_at) }}</td></tr></tbody></table><p v-if="!documents.length" class="empty-copy">暂无文档。</p></article>
        <div v-if="selected.provider === 'LOCAL'" class="knowledge-bottom-grid">
          <article class="product-card"><h2>Ingest 任务</h2><div v-for="job in jobs" :key="job.job_id" class="reference-item"><b>{{ job.status }}</b><small>{{ shortTime(job.created_at) }} · {{ job.error_code || '无错误' }}</small></div><p v-if="!jobs.length" class="empty-copy">尚无构建任务。</p></article>
          <article class="product-card"><h2>索引版本</h2><div v-for="index in indexes" :key="index.index_version_id" class="reference-item"><b>Index V{{ index.version_number }}</b><small>{{ index.status }} · {{ index.embedding_model }} · {{ shortTime(index.created_at) }}</small></div><p v-if="!indexes.length" class="empty-copy">尚无索引版本。</p></article>
        </div>
        <article v-if="hits.length" class="product-card"><h2>检索命中</h2><div v-for="hit in hits" :key="`${hit.document_id}-${hit.chunk_number}`" class="retrieval-hit"><b>{{ hit.title || `Chunk ${hit.chunk_number}` }} · Score {{ hit.score.toFixed(4) }}</b><p>{{ hit.content }}</p><small>{{ hit.source || selected.provider_display_name }}</small></div></article>
      </section>
      <div v-else class="empty-panel">从左侧选择一个知识库开始运营。</div>
    </div>
  </section>
</template>
