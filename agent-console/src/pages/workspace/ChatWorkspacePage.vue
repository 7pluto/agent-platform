<script setup lang="ts">
import type {
  AgentWorkbenchItem,
  CatalogItem,
  ConversationMessage,
  ConversationRecord,
  MemoryItem,
  RunEvent,
} from '../../api'

defineProps<{
  selectedAgent: AgentWorkbenchItem
  conversations: ConversationRecord[]
  selectedConversationId: string
  memoryEnabled: boolean
  memory: MemoryItem[]
  messages: ConversationMessage[]
  currentCapabilities: CatalogItem[]
  runEvents: RunEvent[]
  traceDuration: string
  traceToolCalls: number
  traceRagHits: number
  traceMemoryCount: number
  reply: string
  loading: boolean
  conversationCreating: boolean
  memorySaving: boolean
  openConversationCreator: () => void
  newConversation: () => void | Promise<void>
  selectConversation: (conversation: ConversationRecord) => void | Promise<void>
  openConversationRename: (conversation: ConversationRecord) => void
  createLongTermMemory: (content?: string, sourceRunId?: string) => void | Promise<void>
  deleteLongTermMemory: (memory: MemoryItem) => void | Promise<void>
  renameCurrentConversation: () => void | Promise<void>
  sendMessage: () => void | Promise<void>
  shortTime: (value?: string) => string
  traceEventLabel: (event: string) => string
  traceEventSummary: (event: RunEvent) => string
  backToAgents: () => void
}>()

const conversationCreatorOpen = defineModel<boolean>('conversationCreatorOpen', { required: true })
const conversationTitle = defineModel<string>('conversationTitle', { required: true })
const memoryCreatorOpen = defineModel<boolean>('memoryCreatorOpen', { required: true })
const memoryCategory = defineModel<string>('memoryCategory', { required: true })
const memoryContent = defineModel<string>('memoryContent', { required: true })
const conversationRenameOpen = defineModel<boolean>('conversationRenameOpen', { required: true })
const conversationRenameTitle = defineModel<string>('conversationRenameTitle', { required: true })
const traceExpanded = defineModel<boolean>('traceExpanded', { required: true })
const message = defineModel<string>('message', { required: true })
</script>

<template>
<section class="page-content chat-page">
        <div class="detail-header">
<button class="text-link" @click="backToAgents">‹ 返回智能体广场</button>
<div>
<p class="eyebrow">{{ selectedAgent.deployment_name }}</p>
<h1>{{ selectedAgent.display_name }}</h1>
<p>{{ selectedAgent.description }}</p>
</div>
<button class="button ghost" @click="openConversationCreator">＋ 新建会话</button>
</div>
<div v-if="conversationCreatorOpen" class="modal-backdrop" @click.self="conversationCreatorOpen = false">
<section class="compact-modal" role="dialog" aria-modal="true" aria-label="新建会话">
<header><div><p class="eyebrow">NEW CONVERSATION</p><h2>新建会话</h2><p>会话只属于当前智能体；历史上下文不会与其他会话混用。</p></div><button class="icon-button" aria-label="关闭" @click="conversationCreatorOpen = false">×</button></header>
<div class="compact-modal-body"><label>会话名称（可选）<input v-model="conversationTitle" maxlength="100" placeholder="例如：考勤制度咨询" /></label><p class="field-hint">不填写时使用“新会话”；发送第一条消息后也可按内容重命名。</p></div>
<footer><button class="button ghost" @click="conversationCreatorOpen = false">取消</button><button class="button primary" :disabled="conversationCreating" @click="newConversation">{{ conversationCreating ? '创建中…' : '创建会话' }}</button></footer>
</section>
</div>
        <div class="chat-layout">
<aside class="conversation-panel">
<h3>会话</h3>
<div v-for="item in conversations" :key="item.conversation_id" :class="['conversation-item-row', { active: item.conversation_id === selectedConversationId }]">
<button class="conversation-item" @click="selectConversation(item)"><b>{{ item.title || '未命名会话' }}</b><small>{{ shortTime(item.updated_at) }}</small></button>
<button class="conversation-rename" aria-label="重命名会话" title="重命名" @click="openConversationRename(item)">✎</button>
</div>
<div class="memory-summary">
<div class="memory-summary-heading"><h3>长期记忆</h3><button v-if="memoryEnabled" class="text-link" @click="memoryCreatorOpen = true">＋ 新增</button></div>
<p v-if="!memoryEnabled">该智能体未启用长期记忆</p>
<p v-else-if="!memory.length">当前用户在此智能体下还没有长期记忆</p>
<article v-for="item in memory" :key="item.memory_id" class="memory-item">
<span><small>{{ item.category }}</small><b>{{ item.content }}</b></span>
<button class="icon-button" :disabled="memorySaving" aria-label="删除记忆" @click="deleteLongTermMemory(item)">×</button>
</article>
</div>
</aside>
<section class="chat-main product-card">
<header>
<div>
<b>当前会话</b>
<small>{{ selectedAgent.display_name }} · {{ currentCapabilities.length }} 项能力已挂载</small>
</div>
</header>
<div class="message-list">
<p v-if="!messages.length" class="empty-copy">开始提问，当前会话的历史上下文会自动保留。</p>
<div v-for="item in messages" :key="item.message_id" :class="['message', item.role.toLowerCase()]">
<span>{{ item.content }}</span>
<button v-if="memoryEnabled && item.role !== 'SYSTEM'" class="message-memory-action" :disabled="memorySaving" @click="createLongTermMemory(item.content, item.source_run_id)">保存为记忆</button>
</div>
<details v-if="runEvents.length" class="trace-panel" :open="traceExpanded" @toggle="traceExpanded = ($event.target as HTMLDetailsElement).open">
<summary>
<span>运行过程</span>
<small>{{ loading ? '执行中' : runEvents.some(item => item.event === 'runtime.failed' || item.event === 'run.failed') ? '运行失败' : '已完成' }} · {{ traceDuration }} · {{ traceToolCalls }} 次工具 · {{ traceRagHits }} 条知识 · {{ traceMemoryCount }} 条记忆</small>
</summary>
<article v-for="event in runEvents" :key="event.sequence" class="trace-event">
<span class="trace-dot" />
<div><b>{{ traceEventLabel(event.event) }}</b><p>{{ traceEventSummary(event) }}</p>
<details class="trace-raw"><summary>查看原始事件</summary><pre>{{ JSON.stringify(event.data, null, 2) }}</pre></details></div>
</article>
</details>
<div v-if="reply" class="answer">
<p>最终回答</p>{{ reply }}</div>
</div>
<footer class="composer">
<textarea v-model="message" rows="3" placeholder="请输入你希望智能体完成的任务" @keydown.ctrl.enter="sendMessage" />
<button class="button primary" :disabled="loading || !message.trim()" @click="sendMessage">{{ loading ? '运行中…' : '发送' }}</button>
</footer>
</section>
</div>
<div v-if="memoryCreatorOpen" class="modal-backdrop" @click.self="memoryCreatorOpen = false">
<section class="compact-modal" role="dialog" aria-modal="true" aria-label="新增长期记忆">
<header><div><p class="eyebrow">LONG-TERM MEMORY</p><h2>新增长期记忆</h2><p>仅保存你明确填写的内容，并只在当前智能体、当前账号下跨会话加载。</p></div><button class="icon-button" aria-label="关闭" @click="memoryCreatorOpen = false">×</button></header>
<div class="compact-modal-body"><label>分类<input v-model="memoryCategory" maxlength="64" placeholder="preference" /></label><label>记忆内容<textarea v-model="memoryContent" rows="5" maxlength="4000" placeholder="例如：回答时使用简体中文，并优先给出结论。" /></label></div>
<footer><button class="button ghost" :disabled="memorySaving" @click="memoryCreatorOpen = false">取消</button><button class="button primary" :disabled="memorySaving || !memoryContent.trim()" @click="createLongTermMemory()">{{ memorySaving ? '保存中…' : '保存记忆' }}</button></footer>
</section>
</div>
<div v-if="conversationRenameOpen" class="modal-backdrop" @click.self="conversationRenameOpen = false">
<section class="compact-modal" role="dialog" aria-modal="true" aria-label="重命名会话">
<header><div><p class="eyebrow">RENAME CONVERSATION</p><h2>重命名会话</h2></div><button class="icon-button" aria-label="关闭" @click="conversationRenameOpen = false">×</button></header>
<div class="compact-modal-body"><label>会话名称<input v-model="conversationRenameTitle" maxlength="100" @keyup.enter="renameCurrentConversation" /></label></div>
<footer><button class="button ghost" :disabled="conversationCreating" @click="conversationRenameOpen = false">取消</button><button class="button primary" :disabled="conversationCreating || !conversationRenameTitle.trim()" @click="renameCurrentConversation">{{ conversationCreating ? '保存中…' : '保存名称' }}</button></footer>
</section>
</div>
      </section>
</template>

