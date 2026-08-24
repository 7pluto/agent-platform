<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { consolePaths } from './app/navigation'
import {
  api, type AgentWorkbenchItem, type AuditEvent, type CatalogItem, type ConfigurationDraft,
  type ConfigurationValidation, type ConversationMessage, type ConversationRecord,
  type DeploymentCapabilities, type IamSubject, type IngestJob, type KnowledgeDocument, type KnowledgeIndex,
  type KnowledgeOverview, type McpDiscoveredTool, type MemoryItem, type Principal, type ResourceDetail, type ResourceGrant, type ResourceImpact, type ResourceListItem, type ResourceValidationRun, type RunDetail, type RunEvent, type RunObservabilitySummary, type RunRecord, type SecretRecord,
} from './api'
import SystemConnectionsPage from './pages/connections/SystemConnectionsPage.vue'
import KnowledgeOperationsPage from './pages/knowledge/KnowledgeOperationsPage.vue'
import RunGovernancePage from './pages/runs/RunGovernancePage.vue'
import PermissionAuditPage from './pages/permissions/PermissionAuditPage.vue'
import AgentMarketplacePage from './pages/workspace/AgentMarketplacePage.vue'
import ChatWorkspacePage from './pages/workspace/ChatWorkspacePage.vue'
import ConsoleOverviewPage from './pages/overview/ConsoleOverviewPage.vue'
import AgentManagementPage from './pages/agents/AgentManagementPage.vue'
import CapabilityDetailPage from './pages/capabilities/CapabilityDetailPage.vue'
import CapabilityListPage from './pages/capabilities/CapabilityListPage.vue'

type Space = 'workspace' | 'console'
type WorkspaceView = 'agents' | 'chat'
type ConsoleView = 'overview' | 'agents' | 'resources' | 'connections' | 'knowledge' | 'runs' | 'permissions'
type ResourceType = 'ALL' | 'MODEL' | 'PROMPT' | 'SKILL' | 'TOOL' | 'MCP_CONNECTION' | 'KNOWLEDGE_CONNECTION' | 'KNOWLEDGE' | 'MEMORY_POLICY'

const router = useRouter()
const route = useRoute()

const principal = ref<Principal | null>(null)
const csrf = ref('')
const authMode = ref<'ticket' | 'password'>('password')
const username = ref('admin')
const password = ref('')
const captchaCode = ref('')
const captchaImage = ref('')
const captchaUuid = ref('')
const ticket = ref('dev-ticket')
const error = ref('')
const loading = ref(false)

const space = ref<Space>('workspace')
const workspaceView = ref<WorkspaceView>('agents')
const consoleView = ref<ConsoleView>('overview')
const agents = ref<AgentWorkbenchItem[]>([])
const resources = ref<ResourceListItem[]>([])
const catalog = ref<CatalogItem[]>([])
const observability = ref<RunObservabilitySummary | null>(null)
const governanceRuns = ref<RunRecord[]>([])
const selectedGovernanceRun = ref<RunDetail | null>(null)
const runGovernanceLoading = ref(false)
const permissionGrants = ref<ResourceGrant[]>([])
const auditEvents = ref<AuditEvent[]>([])
const permissionLoading = ref(false)
const secrets = ref<SecretRecord[]>([])
const secretLoading = ref(false)
const secretSaving = ref(false)
const selectedAgent = ref<AgentWorkbenchItem | null>(null)
const selectedResource = ref<ResourceDetail | null>(null)
const resourceImpact = ref<ResourceImpact | null>(null)
const validationRunsByVersion = ref<Record<string, ResourceValidationRun[]>>({})
const selectedKnowledge = ref<KnowledgeOverview | null>(null)
const resourceDetailTab = ref<'OVERVIEW' | 'VERSIONS' | 'GOVERNANCE' | 'TECHNICAL'>('OVERVIEW')
const descriptorEditing = ref(false)
const descriptorForm = ref({ owner_user_id: '', owner_dept_id: '', source_type: 'PLATFORM_NATIVE', source_ref: '', usage_guidance: '', one_line_summary: '', when_to_use: '', when_not_to_use: '', input_summary: '', output_summary: '', risk_level: 'LOW', read_only: true, tags: '', lifecycle_status: 'ACTIVE' })
const resourceQuery = ref('')
const resourceType = ref<ResourceType>('ALL')
const agentQuery = ref('')
const agentActive = ref<'ALL' | 'true' | 'false'>('ALL')
const resourceLoading = ref(false)
const agentLoading = ref(false)
const agentCreatorOpen = ref(false)
const agentCreating = ref(false)
const agentCreateForm = ref({ displayName: '', description: '', deploymentName: '' })

const agentDetail = ref<DeploymentCapabilities | null>(null)
const draft = ref<ConfigurationDraft | null>(null)
const validation = ref<ConfigurationValidation | null>(null)
const builderSaving = ref(false)
const builderPublishing = ref(false)
const agentPublicationScope = ref<'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'>('PERSONAL')
const agentPublicationSubjects = ref<string[]>([])
const resourceComposerOpen = ref(false)
const resourceSaving = ref(false)
const moduleWorkbenchOpen = ref(true)
const resourceWizardStep = ref(1)
const resourceCategory = ref<'CAPABILITY' | 'CONNECTOR' | 'EXTERNAL_APP'>('CAPABILITY')
const iamUsers = ref<IamSubject[]>([])
const iamDepartments = ref<IamSubject[]>([])
const iamRoles = ref<IamSubject[]>([])
const difyPublishResult = ref<{ grants: number; inputs: number; invocationTested: boolean } | null>(null)
const resourceForm = ref({
  type: 'PROMPT', displayName: '', slug: '', description: '', template: '', skillMd: '', skillTests: '', nativeName: 'echo', toolMode: 'NATIVE' as 'NATIVE' | 'HTTP',
  oneLineSummary: '', whenToUse: '', whenNotToUse: '', inputSummary: '', outputSummary: '', riskLevel: 'LOW', readOnly: true,
  ownerUserId: '', ownerDeptId: '', tags: '',
  businessLine: '', dataInvolved: '', audience: '', usageScenarios: '', developerUserIds: [] as string[],
  publicationScope: 'PERSONAL' as 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS', publicationSubjects: [] as string[],
  embeddingModelVersionId: '', ttlDays: 30, maxItems: 50, categories: 'preference',
  modelBaseUrl: 'https://api.siliconflow.cn/v1', modelName: '', modelApiKey: '', modelMode: 'CHAT',
  mcpEndpoint: '', mcpApiKey: '', mcpTimeout: 10,
  ragflowEndpoint: '', ragflowApiKey: '', ragflowTimeout: 20, knowledgeSource: 'LOCAL' as 'LOCAL' | 'RAGFLOW' | 'REMOTE_HTTP', ragflowConnectionVersionId: '', ragflowDatasetId: '',
  remoteKnowledgeEndpoint: '', remoteKnowledgePath: '/search', remoteKnowledgeMethod: 'POST' as 'GET' | 'POST', remoteKnowledgeTimeout: 15,
  remoteKnowledgeApiKey: '', remoteKnowledgeQueryField: 'query', remoteKnowledgeTopKField: 'top_k', remoteKnowledgeStaticBody: '{}',
  remoteKnowledgeItemsPath: 'items', remoteKnowledgeIdField: 'id', remoteKnowledgeContentField: 'content', remoteKnowledgeTitleField: 'title',
  remoteKnowledgeScoreField: 'score', remoteKnowledgeMetadataField: 'metadata', remoteKnowledgeTestQuery: '员工考勤管理办法',
  httpEndpoint: '', httpPath: '/', httpMethod: 'GET' as 'GET' | 'POST' | 'PUT' | 'PATCH', httpToolName: '', httpApiKey: '', httpTimeout: 15,
  httpInputSchema: '{"type":"object","properties":{}}', httpQueryTemplate: '{}', httpBodyTemplate: '', httpHeaderTemplate: '{}', httpResponseMapping: '{}', httpTestArguments: '{}',
  difyBaseUrl: '', difyApiKey: '', difyFlowType: 'CHATFLOW', difyToolName: '', difyTimeout: 90,
  difyBusinessLine: '', difyDataInvolved: '', difyAudience: '', difyUsageScenarios: '', difyDeveloperUserIds: [] as string[],
  difyOpeningStatement: '', difySuggestedQuestions: '', difyPublicationScope: 'PERSONAL' as 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS',
  difyPublicationSubjects: [] as string[],
  skillToolVersionIds: [] as string[], skillKnowledgeVersionIds: [] as string[],
})
const knowledgeQuery = ref('')
const knowledgeProviderFilter = ref<'ALL' | 'LOCAL' | 'RAGFLOW' | 'REMOTE_HTTP'>('ALL')
const knowledgeProviderOptions = [
  { v: 'ALL', n: '全部' }, { v: 'LOCAL', n: '平台托管' }, { v: 'RAGFLOW', n: 'RAGFlow' }, { v: 'REMOTE_HTTP', n: '外部 API' },
] as const
const selectedKnowledgeVersionId = ref('')
const knowledgeDocuments = ref<KnowledgeDocument[]>([])
const knowledgeIndexes = ref<KnowledgeIndex[]>([])
const knowledgeJobs = ref<IngestJob[]>([])
const knowledgeFile = ref<File | null>(null)
const knowledgeUploadOpen = ref(false)
const knowledgeRetrievalQuery = ref('')
const knowledgeRetrievalHits = ref<Array<{ document_id: string; chunk_number: number; content: string; score: number; title?: string; source?: string }>>([])
const knowledgeBusy = ref(false)
const ragflowDatasets = ref<Array<{ id: string; name: string; description?: string }>>([])
const ragflowDiscovering = ref(false)
type McpToolDraft = { selected: boolean; displayName: string; slug: string; description: string; riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'; readOnly: boolean; publicationScope: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'; ownerDeptId: string; publicationSubjects: string[] }
const mcpDiscoveredTools = ref<McpDiscoveredTool[]>([])
const mcpToolDrafts = ref<Record<string, McpToolDraft>>({})
const mcpDiscovering = ref(false)
const mcpRegistering = ref(false)

const conversations = ref<ConversationRecord[]>([])
const selectedConversationId = ref('')
const selectedThreadId = ref('')
const conversationCreatorOpen = ref(false)
const conversationCreating = ref(false)
const conversationTitle = ref('')
const conversationRenameOpen = ref(false)
const conversationRenameId = ref('')
const conversationRenameTitle = ref('')
const messages = ref<ConversationMessage[]>([])
const memory = ref<MemoryItem[]>([])
const memoryCreatorOpen = ref(false)
const memoryContent = ref('')
const memoryCategory = ref('preference')
const memorySaving = ref(false)
const message = ref('')
const reply = ref('')
const runEvents = ref<RunEvent[]>([])
const traceExpanded = ref(false)
const activeRunId = ref('')

const isAdmin = computed(() => Boolean(principal.value?.role_codes.includes('admin') || principal.value?.role_codes.includes('agent_admin')))
const currentCapabilities = computed(() => agentDetail.value?.capabilities || [])
const memoryEnabled = computed(() => currentCapabilities.value.some(item => item.resource_type === 'MEMORY_POLICY'))
const selectedSpec = computed<Record<string, unknown>>(() => draft.value?.specification || {})
const capabilityGroups = computed(() => {
  const grouped: Record<string, CatalogItem[]> = {}
  for (const item of currentCapabilities.value)
    (grouped[item.resource_type] ||= []).push(item)
  return grouped
})

function typeLabel(type: string) {
  return ({ MODEL: '模型', PROMPT: '提示词', SKILL: '技能', TOOL: '工具', MCP_CONNECTION: 'MCP 连接', KNOWLEDGE: '知识库', MEMORY_POLICY: '记忆策略' } as Record<string, string>)[type] || type
}
function statusLabel(status?: string) {
  return ({ PUBLISHED: '已发布', DRAFT: '草稿', ACTIVE: '运行中', AVAILABLE: '可用', UNAVAILABLE: '不可用' } as Record<string, string>)[status || ''] || status || '—'
}
function healthLabel(status?: string) { return ({ HEALTHY: '健康', DEGRADED: '需关注', UNHEALTHY: '异常', UNKNOWN: '未检查' } as Record<string, string>)[status || 'UNKNOWN'] || '未检查' }
function shortTime(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '暂无' }
function traceEventLabel(event: string) {
  return ({
    'run.created': 'Run 已创建', 'manifest.created': '执行清单已冻结', 'run.claimed': 'Worker 已领取任务', 'run.started': '开始执行',
    'runtime.started': '运行时已启动', 'manifest.resources.resolved': '能力版本已解析', 'runtime.capabilities.registered': '权限裁剪完成',
    'conversation.history.loaded': '会话历史已加载', 'memory.read': '长期记忆已加载', 'skills.loaded': '业务技能已加载',
    'tool.started': '调用业务能力', 'tool.completed': '业务能力返回', 'tool.denied': '能力调用被权限拒绝', 'tool.arguments.invalid': '工具参数自动纠正',
    'rag.retrieved': '知识检索完成', 'dify.flow.completed': 'Dify Flow 执行完成', 'dify.rag.retrieved': 'Dify 知识检索完成',
    'runtime.step': '模型推理步骤完成', 'runtime.output': '最终回答已生成', 'runtime.completed': '运行时执行完成',
    'runtime.failed': '运行时执行失败', 'run.completed': 'Run 已完成', 'run.failed': 'Run 已失败', 'run.cancelled': 'Run 已取消',
  } as Record<string, string>)[event] || event
}
function traceEventSummary(event: RunEvent) {
  const data = event.data as Record<string, unknown>
  if (event.event === 'runtime.capabilities.registered') return `${data.tool_count || 0} 项能力可用，${data.filtered_capability_count || 0} 项因权限被过滤`
  if (event.event === 'conversation.history.loaded') return `${data.count || 0} 条历史消息${data.trimmed ? '，已按上下文上限裁剪' : ''}`
  if (event.event === 'memory.read') return `${data.count || 0} 条长期记忆`
  if (event.event === 'skills.loaded') return `${data.count || 0} 个 Skill`
  if (event.event === 'tool.started') return `正在调用 ${String(data.tool || '工具')}`
  if (event.event === 'tool.completed') return `${String(data.tool || '工具')} 已返回结果`
  if (event.event === 'tool.denied') return String(data.message || '当前账号没有使用该能力的权限')
  if (event.event === 'rag.retrieved') return `${String(data.provider || 'Knowledge')} 返回 ${data.chunk_count || 0} 条知识片段`
  if (event.event === 'dify.flow.completed') return `${String(data.tool || 'Dify')} 已完成，关联 ${data.retriever_resource_count || 0} 条检索内容`
  if (event.event === 'runtime.failed') return `${String(data.code || 'RUNTIME_EXECUTION_FAILED')} · ${String(data.error_type || '运行异常')}`
  if (event.event === 'manifest.resources.resolved') return `${Array.isArray(data.resources) ? data.resources.length : 0} 个不可变资源版本`
  return shortTime(event.occurred_at)
}
const traceToolCalls = computed(() => runEvents.value.filter(item => item.event === 'tool.started').length)
const traceRagHits = computed(() => runEvents.value.filter(item => item.event === 'rag.retrieved').reduce((count, item) => count + Number(item.data.chunk_count || 0), 0))
const traceMemoryCount = computed(() => Number(runEvents.value.find(item => item.event === 'memory.read')?.data.count || 0))
const traceDuration = computed(() => {
  if (runEvents.value.length < 2) return '—'
  const start = new Date(runEvents.value[0].occurred_at).getTime()
  const end = new Date(runEvents.value[runEvents.value.length - 1].occurred_at).getTime()
  return Number.isFinite(start) && Number.isFinite(end) ? `${Math.max(0, end - start)}ms` : '—'
})
function requestId() { return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}` }
function consoleTitle(view: ConsoleView) {
  return ({ overview: '概览', agents: '智能体管理', resources: '能力中心', connections: '系统连接', knowledge: '知识库运营', runs: '运行治理', permissions: '权限与审计' } as Record<ConsoleView, string>)[view]
}
function goWorkspaceAgents() { void router.push('/workspace/agents') }
function goConsole(view: ConsoleView) { void router.push(consolePaths[view]) }

async function applyRouteState() {
  const name = String(route.name || '')
  if (name === 'workspace-agents') { space.value = 'workspace'; workspaceView.value = 'agents'; return }
  if (name === 'workspace-agent-chat') {
    space.value = 'workspace'; workspaceView.value = 'chat'
    const item = agents.value.find(value => value.deployment_id === String(route.params.id))
    if (item && selectedAgent.value?.deployment_id !== item.deployment_id) await openAgent(item)
    return
  }
  if (!name.startsWith('console-')) return
  space.value = 'console'
  const view = ({
    'console-overview': 'overview', 'console-agents': 'agents', 'console-agent-edit': 'agents',
    'console-capabilities': 'resources', 'console-capability-detail': 'resources',
    'console-knowledge': 'knowledge', 'console-knowledge-detail': 'knowledge',
    'console-connections': 'connections', 'console-connection-detail': 'connections',
    'console-runs': 'runs', 'console-run-detail': 'runs', 'console-governance': 'permissions',
  } as Record<string, ConsoleView>)[name]
  if (view) consoleView.value = view
  const resourceId = typeof route.params.id === 'string' ? route.params.id : ''
  if (name === 'console-capability-detail' || name === 'console-connection-detail') {
    const item = resources.value.find(value => value.resource_id === resourceId)
    if (item && selectedResource.value?.resource.resource_id !== item.resource_id) await openResource(item, false)
  }
  if (name === 'console-knowledge-detail') {
    const item = resources.value.find(value => value.resource_id === resourceId)
    if (item && selectedKnowledge.value?.resource_id !== item.resource_id) await openKnowledge(item, false)
  }
  if (name === 'console-run-detail' && resourceId) {
    if (selectedGovernanceRun.value?.run.run_id !== resourceId) {
      try { selectedGovernanceRun.value = await api.runDetail(resourceId) }
      catch { selectedGovernanceRun.value = null }
    }
  } else if (name === 'console-runs') selectedGovernanceRun.value = null
}

async function refreshCaptcha() {
  const data = await api.ruoyiCaptcha()
  captchaImage.value = data.image; captchaUuid.value = data.uuid; captchaCode.value = ''
}
async function login() {
  loading.value = true; error.value = ''
  try {
    const session = authMode.value === 'password'
      ? await api.ruoyiLogin(username.value, password.value, captchaCode.value, captchaUuid.value)
      : await api.exchange(ticket.value)
    principal.value = session.principal; csrf.value = session.csrf_token
    space.value = isAdmin.value ? 'console' : 'workspace'
    await refreshData(); await applyRouteState()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err); if (authMode.value === 'password') await refreshCaptcha() }
  finally { loading.value = false }
}
async function loadSession() {
  try {
    const session = await api.session()
    principal.value = session.principal; csrf.value = session.csrf_token
    space.value = isAdmin.value ? 'console' : 'workspace'
    await refreshData(); await applyRouteState()
  } catch {
    authMode.value = (await api.authMode()).mode
    if (authMode.value === 'password') await refreshCaptcha()
  }
}
async function logout() { await api.logout(); principal.value = null; selectedAgent.value = null; selectedResource.value = null }

async function refreshData() {
  await Promise.all([loadAgents(), loadResources(), loadCatalog(), loadObservability(), loadGovernanceRuns(), loadPermissionData(), loadSecrets()])
}
async function loadCatalog() { if (isAdmin.value) catalog.value = await api.catalog() }
async function loadObservability() {
  if (!isAdmin.value) { observability.value = null; return }
  try { observability.value = await api.runObservability() } catch { observability.value = null }
}
async function loadGovernanceRuns() {
  if (!isAdmin.value) { governanceRuns.value = []; return }
  runGovernanceLoading.value = true
  try { governanceRuns.value = await api.listRuns() }
  catch { governanceRuns.value = [] }
  finally { runGovernanceLoading.value = false }
}
async function refreshRunGovernance() {
  await Promise.all([loadGovernanceRuns(), loadObservability()])
  if (selectedGovernanceRun.value) {
    try { selectedGovernanceRun.value = await api.runDetail(selectedGovernanceRun.value.run.run_id) }
    catch { selectedGovernanceRun.value = null }
  }
}
async function openGovernanceRun(run: RunRecord) {
  runGovernanceLoading.value = true
  try {
    selectedGovernanceRun.value = await api.runDetail(run.run_id)
    await router.push(`/console/runs/${run.run_id}`)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { runGovernanceLoading.value = false }
}
function closeGovernanceRun() {
  selectedGovernanceRun.value = null
  void router.push('/console/runs')
}
async function loadPermissionData() {
  if (!isAdmin.value) { permissionGrants.value = []; auditEvents.value = []; return }
  permissionLoading.value = true
  try {
    const [grants, audits, users, departments, roles] = await Promise.all([
      api.listResourceGrants(csrf.value), api.listAuditEvents(), api.searchIamSubjects('USER'), api.searchIamSubjects('DEPT'), api.searchIamSubjects('ROLE'),
    ])
    permissionGrants.value = grants; auditEvents.value = audits
    iamUsers.value = users.items; iamDepartments.value = departments.items; iamRoles.value = roles.items
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { permissionLoading.value = false }
}

async function loadSecrets() {
  if (!isAdmin.value) { secrets.value = []; return }
  secretLoading.value = true
  try { secrets.value = await api.listSecrets() }
  catch { secrets.value = [] }
  finally { secretLoading.value = false }
}

async function rotateSecret(secret: SecretRecord, value: string) {
  secretSaving.value = true; error.value = ''
  try {
    await api.rotateSecret(secret.secret_id, value, csrf.value)
    await Promise.all([loadSecrets(), loadPermissionData()])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { secretSaving.value = false }
}

async function disableSecret(secret: SecretRecord) {
  if (!confirm(`确认停用“${secret.name}”？仍引用该凭据的模型或外部能力将无法调用，直至替换或重新启用。`)) return
  secretSaving.value = true; error.value = ''
  try {
    await api.disableSecret(secret.secret_id, csrf.value)
    await Promise.all([loadSecrets(), loadPermissionData()])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { secretSaving.value = false }
}
async function createPermissionGrant(payload: { subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string; resource_type: string; resource_id: string; actions: string[] }) {
  permissionLoading.value = true; error.value = ''
  try { await api.createResourceGrant(payload, csrf.value); await loadPermissionData() }
  catch (err) { error.value = err instanceof Error ? err.message : String(err); permissionLoading.value = false }
}
async function revokePermissionGrant(grant: ResourceGrant) {
  if (!window.confirm('确认撤销这条授权吗？撤销后相关用户、角色或部门将立即失去对应权限。')) return
  permissionLoading.value = true; error.value = ''
  try { await api.deleteResourceGrant(grant.grant_id, csrf.value); await loadPermissionData() }
  catch (err) { error.value = err instanceof Error ? err.message : String(err); permissionLoading.value = false }
}
async function openResourceWizard() {
  resourceComposerOpen.value = true; resourceWizardStep.value = 1
  difyPublishResult.value = null
  resourceForm.value.ownerUserId ||= principal.value?.external_user_id || ''
  try {
    const [users, departments, roles] = await Promise.all([api.searchIamSubjects('USER'), api.searchIamSubjects('DEPT'), api.searchIamSubjects('ROLE')])
    iamUsers.value = users.items; iamDepartments.value = departments.items; iamRoles.value = roles.items
  } catch { /* Upstream directory may be unavailable; current principal remains a valid owner. */ }
}
async function openConnectionWizard() {
  consoleView.value = 'resources'
  await router.push(consolePaths.resources)
  await openResourceWizard()
  selectResourceCategory('CONNECTOR')
}
async function openKnowledgeWizard() {
  consoleView.value = 'resources'
  await router.push(consolePaths.resources)
  await openResourceWizard()
  selectResourceCategory('CAPABILITY')
  resourceForm.value.type = 'KNOWLEDGE'
}
async function discoverRagflowDatasets() {
  const connectionVersionId = resourceForm.value.ragflowConnectionVersionId
  if (!connectionVersionId) { error.value = '请先选择已发布的 RAGFlow 连接。'; return }
  ragflowDiscovering.value = true; error.value = ''
  try {
    ragflowDatasets.value = await api.discoverRagflowDatasets(connectionVersionId, csrf.value)
    if (!ragflowDatasets.value.length) error.value = '该 RAGFlow 连接没有发现可接入的数据集。'
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { ragflowDiscovering.value = false }
}
function latestSelectedResourceVersionId() {
  const versions = selectedResource.value?.versions || []
  return [...versions].sort((a, b) => b.version_number - a.version_number)[0]?.version_id || ''
}
async function discoverSelectedMcpTools() {
  const versionId = latestSelectedResourceVersionId()
  if (!versionId) return
  mcpDiscovering.value = true; error.value = ''
  try {
    await loadIamDirectory()
    mcpDiscoveredTools.value = await api.discoverMcpTools(versionId, csrf.value)
    mcpToolDrafts.value = Object.fromEntries(mcpDiscoveredTools.value.map(item => [item.name, {
      selected: false, displayName: item.description?.trim() || item.name, slug: slugify(item.name), description: item.description || '',
      riskLevel: 'LOW', readOnly: true, publicationScope: 'PERSONAL', ownerDeptId: '', publicationSubjects: [],
    } satisfies McpToolDraft]))
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { mcpDiscovering.value = false }
}
function mcpDraftSubjects(draft: McpToolDraft) {
  return draft.publicationSubjects.map(value => {
    const [subject_type, ...parts] = value.split(':')
    return { subject_type: subject_type as 'USER' | 'ROLE' | 'DEPT', subject_id: parts.join(':') }
  }).filter(item => item.subject_id)
}
async function registerSelectedMcpTools() {
  const connectionVersionId = latestSelectedResourceVersionId()
  const selected = mcpDiscoveredTools.value.filter(item => !item.managed && mcpToolDrafts.value[item.name]?.selected)
  if (!selected.length) { error.value = '请至少选择一个尚未纳管的 MCP Tool。'; return }
  for (const item of selected) {
    const draft = mcpToolDrafts.value[item.name]
    if (!draft.displayName.trim() || !/^[a-z][a-z0-9-]{2,63}$/.test(draft.slug)) { error.value = `${item.name} 需要业务名称和有效 Slug。`; return }
  }
  mcpRegistering.value = true; error.value = ''
  try {
    const tools = selected.map(item => {
      const draft = mcpToolDrafts.value[item.name]
      const fields = Object.keys((item.input_schema?.properties as Record<string, unknown>) || {})
      return {
        tool_name: item.name, slug: draft.slug, display_name: draft.displayName.trim(), description: draft.description.trim() || undefined,
        owner_user_id: principal.value?.external_user_id || '', ...(draft.ownerDeptId ? { owner_dept_id: draft.ownerDeptId } : {}),
        one_line_summary: draft.description.trim() || `通过 MCP 执行“${draft.displayName}”`,
        when_to_use: `当用户请求与“${draft.displayName}”直接相关时`, when_not_to_use: draft.readOnly ? '不用于修改外部业务数据' : undefined,
        input_summary: fields.length ? `输入字段：${fields.join('、')}` : '无需业务参数', output_summary: '返回 MCP 业务工具的结构化结果',
        risk_level: draft.riskLevel, read_only: draft.readOnly, tags: ['MCP', draft.readOnly ? '只读' : '可写'],
        publication_scope: draft.publicationScope, publication_subjects: mcpDraftSubjects(draft),
      }
    })
    await api.registerMcpToolsBatch({ connection_version_id: connectionVersionId, tools }, csrf.value)
    await Promise.all([loadResources(), loadCatalog()])
    await discoverSelectedMcpTools()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { mcpRegistering.value = false }
}
function selectResourceCategory(category: 'CAPABILITY' | 'CONNECTOR' | 'EXTERNAL_APP') {
  resourceCategory.value = category
  resourceForm.value.type = category === 'CAPABILITY' ? 'PROMPT' : category === 'CONNECTOR' ? 'MCP_CONNECTION' : 'DIFY_FLOW'
}
function validateResourceSemantics() {
  const form = resourceForm.value
  if (!form.displayName.trim()) return '请填写资源业务名称。'
  if (!form.oneLineSummary.trim()) return '请用一句话说明这个资源能做什么。'
  if (!form.whenToUse.trim()) return '请说明什么时候应该使用该资源。'
  if (!form.inputSummary.trim() || !form.outputSummary.trim()) return '请说明输入和输出。'
  if (!form.ownerUserId.trim()) return '请选择 RuoYi 资源负责人。'
  const scope = form.type === 'DIFY_FLOW' ? form.difyPublicationScope : form.publicationScope
  const subjects = form.type === 'DIFY_FLOW' ? form.difyPublicationSubjects : form.publicationSubjects
  if (scope === 'OWNER_DEPT' && !form.ownerDeptId) return '责任部门范围必须选择责任部门'
  if (scope === 'SELECTED_SUBJECTS' && !subjects.length) return '指定范围至少选择一个 RuoYi 用户、角色或部门'
  return ''
}
async function saveNewResourceDescriptor(resourceId: string, sourceType: string) {
  const form = resourceForm.value
  await api.updateResourceDescriptor(resourceId, {
    owner_user_id: form.ownerUserId.trim(), owner_dept_id: form.ownerDeptId || undefined,
    source_type: sourceType, usage_guidance: form.whenToUse.trim(), one_line_summary: form.oneLineSummary.trim(),
    when_to_use: form.whenToUse.trim(), when_not_to_use: form.whenNotToUse.trim() || undefined,
    input_summary: form.inputSummary.trim(), output_summary: form.outputSummary.trim(), risk_level: form.riskLevel,
    read_only: form.readOnly, tags: form.tags.split(',').map(item => item.trim()).filter(Boolean), lifecycle_status: 'ACTIVE',
    business_line: form.businessLine.trim() || undefined, data_involved: form.dataInvolved.trim() || undefined,
    audience: form.audience.trim() || undefined, usage_scenarios: form.usageScenarios.trim() || undefined,
    developer_user_ids: form.developerUserIds, publication_scope: form.publicationScope,
  }, csrf.value)
}
function difySubjectValue(type: 'USER' | 'ROLE' | 'DEPT', id: string) { return `${type}:${id}` }
function difyPublicationOptions() {
  return [
    ...iamDepartments.value.map(item => ({ value: difySubjectValue('DEPT', item.external_id), label: `部门 · ${item.display_name}` })),
    ...iamRoles.value.map(item => ({ value: difySubjectValue('ROLE', item.external_id), label: `角色 · ${item.display_name}` })),
    ...iamUsers.value.map(item => ({ value: difySubjectValue('USER', item.external_id), label: `用户 · ${item.display_name}` })),
  ]
}
function difyPublicationSubjects() {
  return resourceForm.value.difyPublicationSubjects.map((value) => {
    const [subject_type, ...parts] = value.split(':')
    return { subject_type: subject_type as 'USER' | 'ROLE' | 'DEPT', subject_id: parts.join(':') }
  }).filter(item => item.subject_id)
}
function resourcePublicationSubjects() {
  return resourceForm.value.publicationSubjects.map((value) => {
    const [subject_type, ...parts] = value.split(':')
    return { subject_type: subject_type as 'USER' | 'ROLE' | 'DEPT', subject_id: parts.join(':') }
  }).filter(item => item.subject_id)
}
async function publishResourceAudience(resourceType: string, resourceVersionId: string) {
  const form = resourceForm.value
  const subjects: Array<{ subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string; actions: string[] }> = [{
    subject_type: 'USER', subject_id: form.ownerUserId.trim(), actions: ['VIEW', 'USE', 'EDIT', 'PUBLISH', 'MANAGE'],
  }]
  if (form.publicationScope === 'OWNER_DEPT') {
    if (!form.ownerDeptId) throw new Error('部门范围必须选择责任部门')
    subjects.push({ subject_type: 'DEPT', subject_id: form.ownerDeptId, actions: ['VIEW', 'USE'] })
  }
  if (form.publicationScope === 'SELECTED_SUBJECTS') {
    const selected = resourcePublicationSubjects()
    if (!selected.length) throw new Error('指定范围至少选择一个 RuoYi 用户、角色或部门')
    subjects.push(...selected.map(item => ({ ...item, actions: ['VIEW', 'USE'] })))
  }
  const merged = new Map<string, typeof subjects[number]>()
  for (const subject of subjects) {
    const key = `${subject.subject_type}:${subject.subject_id}`
    const prior = merged.get(key)
    if (prior) prior.actions = [...new Set([...prior.actions, ...subject.actions])]
    else merged.set(key, subject)
  }
  await Promise.all([...merged.values()].map(subject => api.createResourceGrant({ ...subject, resource_type: resourceType, resource_id: resourceVersionId }, csrf.value)))
}
function agentPublicationBindings() {
  return agentPublicationSubjects.value.map((value) => {
    const [subject_type, ...parts] = value.split(':')
    return { subject_type: subject_type as 'USER' | 'ROLE' | 'DEPT', subject_id: parts.join(':') }
  }).filter(item => item.subject_id)
}
async function loadIamDirectory() {
  try {
    const [users, departments, roles] = await Promise.all([api.searchIamSubjects('USER'), api.searchIamSubjects('DEPT'), api.searchIamSubjects('ROLE')])
    iamUsers.value = users.items; iamDepartments.value = departments.items; iamRoles.value = roles.items
  } catch { /* Directory is upstream-owned; publishing validation remains server-side. */ }
}
function validateDifyApplication() {
  const form = resourceForm.value
  if (!form.difyBaseUrl.trim() || !form.difyApiKey.trim() || !form.difyToolName.trim()) return 'Dify 应用需要 API Base URL、App API Key 和 Tool Name。'
  if (!/^[A-Za-z][A-Za-z0-9_]{1,63}$/.test(form.difyToolName.trim())) return 'Tool Name 必须以字母开头，只能包含字母、数字和下划线。'
  if (!form.difyBusinessLine.trim()) return '请填写 Dify 应用所属业务线。'
  if (!form.difyAudience.trim() || !form.difyUsageScenarios.trim()) return '请填写使用对象和使用场景。'
  if (form.difyPublicationScope === 'OWNER_DEPT' && !form.ownerDeptId) return '部门可用必须选择责任部门。'
  if (form.difyPublicationScope === 'SELECTED_SUBJECTS' && !form.difyPublicationSubjects.length) return '指定范围至少选择一个 RuoYi 用户、角色或部门。'
  return ''
}
function nextResourceWizardStep() {
  if (resourceWizardStep.value === 2) {
    const form = resourceForm.value
    if (form.type === 'DIFY_FLOW') {
      if (!form.difyBaseUrl.trim() || !form.difyApiKey.trim() || !form.difyToolName.trim()) { error.value = '请先填写 Dify 连接、App API Key 和 Tool Name。'; return }
      if (!/^[A-Za-z][A-Za-z0-9_]{1,63}$/.test(form.difyToolName.trim())) { error.value = 'Tool Name 必须以字母开头，只能包含字母、数字和下划线。'; return }
    }
    if (form.type === 'MCP_CONNECTION' && !form.mcpEndpoint.trim()) { error.value = '请先填写 MCP Streamable HTTP Endpoint。'; return }
    if (form.type === 'KNOWLEDGE_CONNECTION' && (!form.ragflowEndpoint.trim() || !form.ragflowApiKey.trim())) { error.value = '请先填写 RAGFlow Endpoint 和 API Key。'; return }
    if (form.type === 'MODEL' && (!form.modelBaseUrl.trim() || !form.modelName.trim() || !form.modelApiKey.trim())) { error.value = '请先填写模型 Endpoint、模型名和 API Key。'; return }
  }
  if (resourceWizardStep.value === 2 && resourceForm.value.type === 'TOOL' && resourceForm.value.toolMode === 'HTTP') {
    const message = validateHttpTool(); if (message) { error.value = message; return }
  }
  if (resourceWizardStep.value === 3) {
    const message = validateResourceSemantics(); if (message) { error.value = message; return }
    if (resourceForm.value.type === 'DIFY_FLOW') {
      const difyMessage = validateDifyApplication(); if (difyMessage) { error.value = difyMessage; return }
    }
  }
  error.value = ''; resourceWizardStep.value = Math.min(4, resourceWizardStep.value + 1)
}
async function loadAgents() {
  agentLoading.value = true
  try {
    const data = await api.workbenchAgents(agentQuery.value, agentActive.value === 'ALL' ? '' : agentActive.value)
    agents.value = data.items
  } finally { agentLoading.value = false }
}
async function loadResources() {
  if (!isAdmin.value) return
  resourceLoading.value = true
  try {
    const data = await api.workbenchResources(resourceQuery.value, '')
    resources.value = data.items
  } finally { resourceLoading.value = false }
}
async function openResource(item: ResourceListItem, updateRoute = true) {
  selectedKnowledge.value = null
  mcpDiscoveredTools.value = []; mcpToolDrafts.value = {}
  selectedResource.value = await api.workbenchResource(item.resource_id)
  validationRunsByVersion.value = Object.fromEntries(await Promise.all(
    selectedResource.value.versions.map(async version => [version.version_id, await api.listResourceValidationRuns(version.version_id)] as const),
  ))
  try { resourceImpact.value = await api.workbenchResourceImpact(item.resource_id) } catch { resourceImpact.value = null }
  resourceDetailTab.value = 'OVERVIEW'
  populateDescriptorForm()
  if (updateRoute) {
    const connection = item.resource_type === 'MCP_CONNECTION' || item.resource_type === 'KNOWLEDGE_CONNECTION'
    void router.push(connection ? `/console/connections/${item.resource_id}` : `/console/capabilities/${item.resource_id}`)
  }
}
function canRetryResourceVersion() {
  if (!selectedResource.value) return false
  return selectedResource.value.resource.resource_type === 'MCP_CONNECTION'
    || selectedResource.value.resource.resource_type === 'KNOWLEDGE_CONNECTION'
    || selectedResource.value.source === 'DIFY'
    || selectedResource.value.resource.source_type === 'DIFY'
}
async function retryValidateAndPublish(versionId: string) {
  if (!selectedResource.value) return
  resourceSaving.value = true; error.value = ''
  const resource = selectedResource.value.resource
  try {
    await api.testResourceVersion(versionId, csrf.value)
    const validation = await api.validateResourceVersion(versionId, csrf.value)
    if (validation.status !== 'SUCCEEDED') throw new Error(String(validation.result.message || validation.result.code || '连接验证失败'))
    await api.publishResourceVersion(versionId, csrf.value)
    await openResource(resource, false)
    resourceDetailTab.value = 'VERSIONS'
    await Promise.all([loadResources(), loadCatalog()])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { resourceSaving.value = false }
}
async function openKnowledge(item: ResourceListItem, updateRoute = true) {
  selectedResource.value = await api.workbenchResource(item.resource_id)
  selectedKnowledge.value = await api.workbenchKnowledge(item.resource_id)
  try { resourceImpact.value = await api.workbenchResourceImpact(item.resource_id) } catch { resourceImpact.value = null }
  resourceDetailTab.value = 'OVERVIEW'
  populateDescriptorForm()
  if (updateRoute) void router.push(`/console/knowledge/${item.resource_id}`)
}
function populateDescriptorForm() {
  if (!selectedResource.value) return
  const value = selectedResource.value.resource
  descriptorEditing.value = false
  descriptorForm.value = {
    owner_user_id: value.owner_user_id || selectedResource.value.created_by || '', owner_dept_id: value.owner_dept_id || '', source_type: value.source_type || 'PLATFORM_NATIVE', source_ref: '', usage_guidance: selectedResource.value.usage_guidance || '',
    one_line_summary: selectedResource.value.one_line_summary || '', when_to_use: selectedResource.value.when_to_use || '', when_not_to_use: selectedResource.value.when_not_to_use || '', input_summary: selectedResource.value.input_summary || '', output_summary: selectedResource.value.output_summary || '', risk_level: selectedResource.value.risk_level || 'LOW', read_only: selectedResource.value.read_only ?? true,
    tags: (value.tags || []).join(', '), lifecycle_status: value.lifecycle_status || 'ACTIVE',
  }
}
async function saveDescriptor() {
  if (!selectedResource.value || !descriptorForm.value.owner_user_id.trim()) return
  resourceSaving.value = true
  try {
    selectedResource.value = await api.updateResourceDescriptor(selectedResource.value.resource.resource_id, {
      ...descriptorForm.value,
      owner_user_id: descriptorForm.value.owner_user_id.trim(),
      owner_dept_id: descriptorForm.value.owner_dept_id.trim() || undefined,
      source_ref: descriptorForm.value.source_ref.trim() || undefined,
      usage_guidance: descriptorForm.value.usage_guidance.trim() || undefined,
      tags: descriptorForm.value.tags.split(',').map(item => item.trim()).filter(Boolean),
    }, csrf.value)
    descriptorEditing.value = false
    await Promise.all([loadResources(), loadCatalog()])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { resourceSaving.value = false }
}
async function deleteResource() {
  if (!selectedResource.value) return
  if (resourceImpact.value && !resourceImpact.value.can_delete) {
    resourceDetailTab.value = 'GOVERNANCE'
    error.value = '该资源仍被智能体、其他资源或知识文档使用，不能物理删除。请先查看影响范围。'
    return
  }
  if (!confirm(`确认删除资源“${selectedResource.value.resource.display_name}”？该资源当前无引用，删除后不可恢复。`)) return
  try {
    await api.deleteWorkbenchResource(selectedResource.value.resource.resource_id, csrf.value)
    closeDetail()
    await Promise.all([loadResources(), loadCatalog(), loadAgents()])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
}
async function deleteAgent(item: AgentWorkbenchItem) {
  if (!confirm(`确认删除智能体“${item.display_name}”？已有会话或运行记录的智能体会被保护，不能删除。`)) return
  try {
    await api.deleteWorkbenchDeployment(item.deployment_id, csrf.value)
    if (selectedAgent.value?.deployment_id === item.deployment_id) { selectedAgent.value = null; agentDetail.value = null; draft.value = null }
    await loadAgents()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
}
function openAgentCreator() {
  agentCreateForm.value = { displayName: '', description: '', deploymentName: '' }
  agentCreatorOpen.value = true
}
async function createAgentFromForm() {
  const form = agentCreateForm.value
  if (!form.displayName.trim()) { error.value = '请填写智能体名称'; return }
  const slug = slugify(form.displayName, 'agent')
  const deploymentDisplayName = form.deploymentName.trim() || `${form.displayName.trim()}-生产`
  const deploymentName = slugify(deploymentDisplayName, 'deployment')
  agentCreating.value = true; error.value = ''
  try {
    const agent = await api.createAgent(slug, form.displayName.trim(), csrf.value, form.description.trim(), {})
    const version = await api.createVersion(agent.agent_id, csrf.value)
    await api.publishVersion(version.agent_version_id, csrf.value)
    const deployment = await api.createDeployment(agent.agent_id, deploymentName, csrf.value, deploymentDisplayName)
    const revision = await api.createRevision(deployment.deployment_id, version.agent_version_id, csrf.value)
    await api.activateRevision(deployment.deployment_id, revision.deployment_revision_id, csrf.value)
    await Promise.all([loadAgents(), loadCatalog()])
    agentCreatorOpen.value = false
    const created = agents.value.find(item => item.deployment_id === deployment.deployment_id)
    if (created) await openAgent(created, true)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { agentCreating.value = false }
}
async function openAgent(item: AgentWorkbenchItem, configure = false) {
  selectedAgent.value = item
  agentDetail.value = await api.deploymentCapabilities(item.deployment_id)
  if (configure && isAdmin.value) {
    await loadIamDirectory()
    draft.value = await api.configurationDraft(item.deployment_id)
    agentPublicationScope.value = agentDetail.value.publication_scope || 'PERSONAL'
    agentPublicationSubjects.value = (agentDetail.value.publication_subjects || [])
      .filter(subject => !(subject.subject_type === 'USER' && subject.subject_id === principal.value?.external_user_id))
      .map(subject => difySubjectValue(subject.subject_type, subject.subject_id))
    validation.value = null
    space.value = 'console'; consoleView.value = 'agents'
    void router.push(`/console/agents/${item.deployment_id}/edit`)
  } else {
    space.value = 'workspace'; workspaceView.value = 'chat'
    void router.push(`/workspace/agents/${item.deployment_id}/chat`)
    await openConversation(item.deployment_id)
  }
}
function closeDetail() {
  const wasKnowledge = selectedResource.value?.resource.resource_type === 'KNOWLEDGE'
  const wasConnection = ['MCP_CONNECTION', 'KNOWLEDGE_CONNECTION'].includes(selectedResource.value?.resource.resource_type || '')
  selectedResource.value = null; selectedKnowledge.value = null; resourceImpact.value = null
  if (space.value === 'workspace') selectedAgent.value = null
  else void router.push(wasKnowledge ? consolePaths.knowledge : wasConnection ? consolePaths.connections : consolePaths.resources)
}

function setSingle(field: string, value: string) {
  if (!draft.value) return
  draft.value.specification = { ...draft.value.specification, [field]: value || undefined }
}
function toggleDraftCapability(field: string, versionId: string) { toggleMany(field, versionId) }
function toggleMany(field: string, versionId: string) {
  if (!draft.value) return
  const values = new Set(selectedValues(field))
  if (values.has(versionId)) values.delete(versionId)
  else values.add(versionId)
  draft.value.specification = { ...draft.value.specification, [field]: [...values] }
}
function selectedValues(field: string) { return (selectedSpec.value[field] as string[] || []) }
function catalogFor(type: string) { return catalog.value.filter(item => item.resource_type === type) }
function embeddingModels() { return catalogFor('MODEL').filter(item => /embedding|bge|embed/i.test(`${item.summary} ${item.display_name}`)) }
function optionLabel(item: CatalogItem) { return `${item.display_name} · V${item.version_number} · ${statusLabel(item.status)}` }
function slugify(value: string, prefix = 'resource') {
  const ascii = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63)
  return ascii.length >= 3 ? ascii : `${prefix}-${Date.now().toString(36)}`
}
function resourceDraftConfig() {
  const form = resourceForm.value
  if (form.type === 'PROMPT') return { template: form.template || '你是一个企业智能助手。' }
  if (form.type === 'SKILL') return { skill_md: form.skillMd || '# Skill\nUse approved tools only.', tool_version_ids: form.skillToolVersionIds, knowledge_version_ids: form.skillKnowledgeVersionIds }
  if (form.type === 'TOOL') return { kind: 'NATIVE', native_name: form.nativeName }
  if (form.type === 'KNOWLEDGE') return { embedding_model_version_id: form.embeddingModelVersionId, retrieval_top_k: 5 }
  if (form.type === 'MEMORY_POLICY') return { write_mode: 'EXPLICIT', read_enabled: true, write_enabled: true, ttl_days: form.ttlDays, max_items: form.maxItems, allowed_categories: form.categories.split(',').map(item => item.trim()).filter(Boolean) }
  return {}
}
function parseJsonValue(value: string, label: string, emptyValue: Record<string, unknown> | unknown[] | undefined = undefined) {
  if (!value.trim()) return emptyValue
  try { return JSON.parse(value) as Record<string, unknown> | unknown[] } catch { throw new Error(`${label} 必须是有效 JSON。`) }
}
function validateHttpTool() {
  const form = resourceForm.value
  if (!form.httpEndpoint.trim() || !form.httpToolName.trim()) return 'HTTP Tool 需要固定 API Endpoint 和 Tool Name。'
  if (!form.httpPath.startsWith('/')) return 'HTTP Tool 路径必须以 / 开头。'
  if (!/^[A-Za-z][A-Za-z0-9_]{1,63}$/.test(form.httpToolName.trim())) return 'HTTP Tool Name 必须以字母开头，只能包含字母、数字和下划线。'
  const input = parseJsonValue(form.httpInputSchema, '输入 Schema')
  if (!input || Array.isArray(input) || input.type !== 'object') return '输入 Schema 必须是 type 为 object 的 JSON Schema。'
  const query = parseJsonValue(form.httpQueryTemplate, 'Query 模板', {})
  const body = parseJsonValue(form.httpBodyTemplate, 'Body 模板')
  const headers = parseJsonValue(form.httpHeaderTemplate, 'Header 模板', {})
  const response = parseJsonValue(form.httpResponseMapping, '响应映射', {})
  const test = parseJsonValue(form.httpTestArguments, '测试参数', {})
  if (query && !Array.isArray(query) && typeof query !== 'object') return 'Query 模板必须是对象。'
  if (body !== undefined && typeof body !== 'object') return 'Body 模板必须是对象或数组。'
  if (!headers || Array.isArray(headers) || typeof headers !== 'object') return 'Header 模板必须是对象。'
  if (!response || Array.isArray(response) || typeof response !== 'object') return '响应映射必须是对象。'
  if (test && (Array.isArray(test) || typeof test !== 'object')) return '测试参数必须是对象。'
  return ''
}
function validateRemoteKnowledge() {
  const form = resourceForm.value
  if (!form.remoteKnowledgeEndpoint.trim()) return '外部知识 API 需要固定 Endpoint。'
  if (!form.remoteKnowledgePath.startsWith('/')) return '检索路径必须以 / 开头。'
  if (!form.remoteKnowledgeQueryField.trim() || !form.remoteKnowledgeTopKField.trim()) return '请填写问题和数量字段名。'
  if (!form.remoteKnowledgeItemsPath.trim() || !form.remoteKnowledgeContentField.trim()) return '请填写结果列表路径和正文字段。'
  if (!form.remoteKnowledgeTestQuery.trim()) return '发布前必须提供一条真实检索测试问题。'
  const staticBody = parseJsonValue(form.remoteKnowledgeStaticBody, '固定请求参数', {})
  if (!staticBody || Array.isArray(staticBody) || typeof staticBody !== 'object') return '固定请求参数必须是 JSON 对象。'
  return ''
}
function parseSkillTests(value: string) {
  const tests = value.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const separator = line.includes('=>') ? '=>' : '|'
    const [input, ...expected] = line.split(separator)
    return { input: input.trim(), expected_behavior: expected.join(separator).trim() }
  })
  if (!tests.length || tests.some(item => !item.input || !item.expected_behavior)) throw new Error('Skill 测试案例每行必须使用“用户问题 => 期望行为”。')
  return tests
}
function toggleSkillDependency(field: 'skillToolVersionIds' | 'skillKnowledgeVersionIds', versionId: string) {
  const values = new Set(resourceForm.value[field])
  if (values.has(versionId)) values.delete(versionId); else values.add(versionId)
  resourceForm.value[field] = [...values]
}
async function createTypedResource() {
  const form = resourceForm.value
  const semanticsError = validateResourceSemantics()
  if (semanticsError) { error.value = semanticsError; return }
  if (form.type === 'KNOWLEDGE' && form.knowledgeSource === 'LOCAL' && !form.embeddingModelVersionId) { error.value = '平台文件知识库必须选择 Embedding 模型版本。'; return }
  if (form.type === 'KNOWLEDGE' && form.knowledgeSource === 'RAGFLOW' && (!form.ragflowConnectionVersionId || !form.ragflowDatasetId)) { error.value = '请选择 RAGFlow 连接并发现、选择数据集。'; return }
  if (form.type === 'KNOWLEDGE' && form.knowledgeSource === 'REMOTE_HTTP') { const message = validateRemoteKnowledge(); if (message) { error.value = message; return } }
  resourceSaving.value = true; error.value = ''
  try {
    const slug = (form.slug.trim() || slugify(form.displayName)).toLowerCase()
    if (!/^[a-z][a-z0-9-]{2,63}$/.test(slug)) { error.value = 'Slug 必须以小写字母开头，且只能包含小写字母、数字和连字符。'; return }
    if (form.type === 'MODEL') {
      if (!form.modelBaseUrl.trim() || !form.modelName.trim() || !form.modelApiKey.trim()) throw new Error('模型接入需要 Endpoint、模型名和 API Key。')
      const modelVersion = await api.createModelWithSecret({ slug, display_name: form.displayName.trim(), base_url: form.modelBaseUrl.trim(), model: form.modelName.trim(), api_key: form.modelApiKey, model_mode: form.modelMode as 'CHAT' | 'EMBEDDING' }, csrf.value)
      await saveNewResourceDescriptor(modelVersion.model_id, 'OPENAI_COMPATIBLE')
      await publishResourceAudience('MODEL', modelVersion.model_version_id)
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'MCP_CONNECTION') {
      if (!form.mcpEndpoint.trim()) throw new Error('MCP 连接需要 Streamable HTTP Endpoint。')
      const mcpVersion = await api.createMcpConnection({ slug, display_name: form.displayName.trim(), endpoint: form.mcpEndpoint.trim(), timeout_seconds: form.mcpTimeout, api_key: form.mcpApiKey || null, auth_header: 'Authorization', auth_scheme: 'Bearer' }, csrf.value)
      await saveNewResourceDescriptor(mcpVersion.resource_id, 'MCP')
      await publishResourceAudience('MCP_CONNECTION', mcpVersion.resource_version_id)
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'KNOWLEDGE_CONNECTION') {
      if (!form.ragflowEndpoint.trim() || !form.ragflowApiKey.trim()) throw new Error('RAGFlow 连接需要 Endpoint 和 API Key。')
      const connection = await api.createRagflowConnection({ slug, display_name: form.displayName.trim(), endpoint: form.ragflowEndpoint.trim(), api_key: form.ragflowApiKey, timeout_seconds: form.ragflowTimeout }, csrf.value)
      form.ragflowApiKey = ''
      await saveNewResourceDescriptor(connection.resource_id, 'RAGFLOW')
      await publishResourceAudience('KNOWLEDGE_CONNECTION', connection.resource_version_id)
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'KNOWLEDGE' && form.knowledgeSource === 'RAGFLOW') {
      await api.registerRagflowKnowledge({
        connection_version_id: form.ragflowConnectionVersionId, dataset_id: form.ragflowDatasetId, slug,
        display_name: form.displayName.trim(), description: form.description.trim() || undefined,
        owner_user_id: form.ownerUserId.trim(), ...(form.ownerDeptId ? { owner_dept_id: form.ownerDeptId } : {}),
        one_line_summary: form.oneLineSummary.trim(), when_to_use: form.whenToUse.trim(),
        ...(form.whenNotToUse.trim() ? { when_not_to_use: form.whenNotToUse.trim() } : {}),
        input_summary: form.inputSummary.trim(), output_summary: form.outputSummary.trim(),
        risk_level: form.riskLevel as 'LOW' | 'MEDIUM' | 'HIGH', read_only: form.readOnly,
        tags: form.tags.split(',').map(item => item.trim()).filter(Boolean),
        ...(form.businessLine.trim() ? { business_line: form.businessLine.trim() } : {}),
        ...(form.dataInvolved.trim() ? { data_involved: form.dataInvolved.trim() } : {}),
        ...(form.audience.trim() ? { audience: form.audience.trim() } : {}),
        ...(form.usageScenarios.trim() ? { usage_scenarios: form.usageScenarios.trim() } : {}),
        publication_scope: form.publicationScope, publication_subjects: resourcePublicationSubjects(),
      }, csrf.value)
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'KNOWLEDGE' && form.knowledgeSource === 'REMOTE_HTTP') {
      await api.createRemoteHttpKnowledge({
        slug, display_name: form.displayName.trim(), description: form.description.trim() || form.oneLineSummary.trim(),
        endpoint: form.remoteKnowledgeEndpoint.trim(), search_path: form.remoteKnowledgePath.trim(), method: form.remoteKnowledgeMethod,
        timeout_seconds: form.remoteKnowledgeTimeout, ...(form.remoteKnowledgeApiKey ? { api_key: form.remoteKnowledgeApiKey } : {}),
        auth_header: 'Authorization', auth_scheme: 'Bearer', query_field: form.remoteKnowledgeQueryField.trim(), top_k_field: form.remoteKnowledgeTopKField.trim(),
        static_body: parseJsonValue(form.remoteKnowledgeStaticBody, '固定请求参数', {}) as Record<string, unknown>, items_path: form.remoteKnowledgeItemsPath.trim(),
        id_field: form.remoteKnowledgeIdField.trim() || 'id', content_field: form.remoteKnowledgeContentField.trim(), title_field: form.remoteKnowledgeTitleField.trim() || 'title',
        ...(form.remoteKnowledgeScoreField.trim() ? { score_field: form.remoteKnowledgeScoreField.trim() } : {}), metadata_field: form.remoteKnowledgeMetadataField.trim() || 'metadata',
        test_query: form.remoteKnowledgeTestQuery.trim(), test_top_k: 3,
        owner_user_id: form.ownerUserId.trim(), ...(form.ownerDeptId ? { owner_dept_id: form.ownerDeptId } : {}),
        one_line_summary: form.oneLineSummary.trim(), when_to_use: form.whenToUse.trim(),
        ...(form.whenNotToUse.trim() ? { when_not_to_use: form.whenNotToUse.trim() } : {}),
        input_summary: form.inputSummary.trim(), output_summary: form.outputSummary.trim(), risk_level: form.riskLevel as 'LOW' | 'MEDIUM' | 'HIGH',
        read_only: form.readOnly, tags: form.tags.split(',').map(item => item.trim()).filter(Boolean),
        ...(form.businessLine.trim() ? { business_line: form.businessLine.trim() } : {}), ...(form.dataInvolved.trim() ? { data_involved: form.dataInvolved.trim() } : {}),
        ...(form.audience.trim() ? { audience: form.audience.trim() } : {}), ...(form.usageScenarios.trim() ? { usage_scenarios: form.usageScenarios.trim() } : {}),
        publication_scope: form.publicationScope, publication_subjects: resourcePublicationSubjects(),
      }, csrf.value)
      form.remoteKnowledgeApiKey = ''
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'SKILL') {
      if (!form.skillMd.trim().startsWith('#')) throw new Error('SKILL.md 必须以 Markdown 标题开头。')
      const result = await api.createSkillProduct({
        slug, display_name: form.displayName.trim(), description: form.description.trim() || form.oneLineSummary.trim(), skill_md: form.skillMd,
        tool_version_ids: form.skillToolVersionIds, knowledge_version_ids: form.skillKnowledgeVersionIds, test_cases: parseSkillTests(form.skillTests),
      }, csrf.value)
      await saveNewResourceDescriptor(result.resource_id, 'PLATFORM_NATIVE')
      await publishResourceAudience('SKILL', result.resource_version_id)
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'TOOL' && form.toolMode === 'HTTP') {
      const httpError = validateHttpTool(); if (httpError) throw new Error(httpError)
      const inputSchema = parseJsonValue(form.httpInputSchema, '输入 Schema') as Record<string, unknown>
      const queryTemplate = parseJsonValue(form.httpQueryTemplate, 'Query 模板', {})
      const bodyTemplate = parseJsonValue(form.httpBodyTemplate, 'Body 模板')
      const headerTemplate = parseJsonValue(form.httpHeaderTemplate, 'Header 模板', {}) as Record<string, string>
      const responseMapping = parseJsonValue(form.httpResponseMapping, '响应映射', {}) as Record<string, unknown>
      const testArguments = parseJsonValue(form.httpTestArguments, '测试参数', {}) as Record<string, unknown>
      await api.createHttpTool({
        slug, display_name: form.displayName.trim(), description: form.description.trim() || form.oneLineSummary.trim(),
        tool_name: form.httpToolName.trim(), endpoint: form.httpEndpoint.trim(), path: form.httpPath.trim(), method: form.httpMethod,
        input_schema: inputSchema, ...(queryTemplate !== undefined ? { query_template: queryTemplate } : {}), ...(bodyTemplate !== undefined ? { body_template: bodyTemplate } : {}),
        header_template: headerTemplate, response_mapping: responseMapping,
        timeout_seconds: form.httpTimeout, ...(form.httpApiKey ? { api_key: form.httpApiKey } : {}), auth_header: 'Authorization', auth_scheme: 'Bearer', test_arguments: testArguments,
        owner_user_id: form.ownerUserId.trim(), ...(form.ownerDeptId ? { owner_dept_id: form.ownerDeptId } : {}),
        one_line_summary: form.oneLineSummary.trim(), when_to_use: form.whenToUse.trim(),
        ...(form.whenNotToUse.trim() ? { when_not_to_use: form.whenNotToUse.trim() } : {}),
        input_summary: form.inputSummary.trim(), output_summary: form.outputSummary.trim(), risk_level: form.riskLevel as 'LOW' | 'MEDIUM' | 'HIGH',
        read_only: form.readOnly, tags: form.tags.split(',').map(item => item.trim()).filter(Boolean),
        ...(form.businessLine.trim() ? { business_line: form.businessLine.trim() } : {}), ...(form.dataInvolved.trim() ? { data_involved: form.dataInvolved.trim() } : {}),
        ...(form.audience.trim() ? { audience: form.audience.trim() } : {}), ...(form.usageScenarios.trim() ? { usage_scenarios: form.usageScenarios.trim() } : {}),
        publication_scope: form.publicationScope, publication_subjects: resourcePublicationSubjects(),
      }, csrf.value)
      form.httpApiKey = ''
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]); return
    }
    if (form.type === 'DIFY_FLOW') {
      const difyError = validateDifyApplication(); if (difyError) throw new Error(difyError)
      const result = await api.createDifyFlowTool({
        slug, display_name: form.displayName.trim(), description: form.description.trim() || form.oneLineSummary.trim(),
        flow_type: form.difyFlowType as 'CHATFLOW' | 'WORKFLOW', base_url: form.difyBaseUrl.trim(), api_key: form.difyApiKey,
        tool_name: form.difyToolName.trim(), timeout_seconds: form.difyTimeout, test_query: '请回复 OK',
        owner_user_id: form.ownerUserId.trim(), owner_dept_id: form.ownerDeptId || undefined,
        one_line_summary: form.oneLineSummary.trim(), when_to_use: form.whenToUse.trim(), when_not_to_use: form.whenNotToUse.trim() || undefined,
        input_summary: form.inputSummary.trim(), output_summary: form.outputSummary.trim(), risk_level: form.riskLevel, read_only: form.readOnly,
        tags: form.tags.split(',').map(item => item.trim()).filter(Boolean), business_line: form.difyBusinessLine.trim(),
        data_involved: form.difyDataInvolved.trim() || undefined, audience: form.difyAudience.trim(), usage_scenarios: form.difyUsageScenarios.trim(),
        developer_user_ids: form.difyDeveloperUserIds, opening_statement: form.difyOpeningStatement.trim() || undefined,
        suggested_questions: form.difySuggestedQuestions.split('\n').map(item => item.trim()).filter(Boolean),
        publication_scope: form.difyPublicationScope, publication_subjects: difyPublicationSubjects(),
      }, csrf.value)
      form.difyApiKey = ''
      difyPublishResult.value = { grants: result.grants_created, inputs: result.connection_test.input_form.length, invocationTested: result.connection_test.invocation_tested }
      resourceComposerOpen.value = false; await Promise.all([loadResources(), loadCatalog()]);
      const created = resources.value.find(item => item.resource_id === result.resource_version.resource_id)
      if (created) await openResource(created)
      return
    }
    const config = resourceDraftConfig()
    const definition = await api.createResource(form.type as never, slug, form.displayName.trim(), form.description.trim(), config, csrf.value)
    const version = await api.createResourceVersion(definition.resource_id, config, csrf.value)
    await api.publishResourceVersion(version.resource_version_id, csrf.value)
    await saveNewResourceDescriptor(definition.resource_id, 'PLATFORM_NATIVE')
    await publishResourceAudience(form.type, version.resource_version_id)
    resourceComposerOpen.value = false
    resourceForm.value = { ...resourceForm.value, displayName: '', slug: '', description: '', template: '', skillMd: '' }
    await Promise.all([loadResources(), loadCatalog()])
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { resourceSaving.value = false }
}

const capabilityResources = computed(() => resources.value.filter(item =>
  ['MODEL', 'PROMPT', 'SKILL', 'TOOL', 'MEMORY_POLICY'].includes(item.resource_type)
  && (resourceType.value === 'ALL' || item.resource_type === resourceType.value)))
const connectionResources = computed(() => resources.value.filter(item =>
  ['MCP_CONNECTION', 'KNOWLEDGE_CONNECTION'].includes(item.resource_type)))
const knowledgeResources = computed(() => resources.value.filter(item =>
  item.resource_type === 'KNOWLEDGE'
  && (knowledgeProviderFilter.value === 'ALL'
    || (knowledgeProviderFilter.value === 'LOCAL' && !['RAGFLOW', 'REMOTE_HTTP'].includes(item.source_type))
    || item.source_type === knowledgeProviderFilter.value)
  && (!knowledgeQuery.value || `${item.display_name} ${item.description || ''} ${item.slug}`.toLowerCase().includes(knowledgeQuery.value.toLowerCase()))))

async function openKnowledgeOperations(item: ResourceListItem) {
  selectedKnowledge.value = await api.workbenchKnowledge(item.resource_id)
  selectedKnowledgeVersionId.value = selectedKnowledge.value.resource_version_id
  await refreshKnowledgeOperations()
}

async function refreshKnowledgeOperations() {
  if (!selectedKnowledgeVersionId.value) return
  knowledgeBusy.value = true; error.value = ''
  try {
    const activeKnowledge = selectedKnowledge.value
    if (!activeKnowledge) return
    if (activeKnowledge.provider !== 'LOCAL') {
      knowledgeDocuments.value = []; knowledgeIndexes.value = []; knowledgeJobs.value = []
      selectedKnowledge.value = await api.workbenchKnowledge(activeKnowledge.resource_id)
      return
    }
    const [documents, indexes, jobs] = await Promise.all([
      api.listKnowledgeDocuments(selectedKnowledgeVersionId.value),
      api.listKnowledgeIndexes(selectedKnowledgeVersionId.value),
      api.listIngestJobs(selectedKnowledgeVersionId.value),
    ])
    knowledgeDocuments.value = documents; knowledgeIndexes.value = indexes; knowledgeJobs.value = jobs
    if (selectedKnowledge.value) selectedKnowledge.value = await api.workbenchKnowledge(selectedKnowledge.value.resource_id)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { knowledgeBusy.value = false }
}

function chooseKnowledgeFile(event: Event) {
  knowledgeFile.value = (event.target as HTMLInputElement).files?.[0] || null
}

async function uploadKnowledgeFile() {
  if (!selectedKnowledgeVersionId.value || !knowledgeFile.value) { error.value = '请选择 PDF 或 DOCX 文件。'; return }
  knowledgeBusy.value = true; error.value = ''
  try {
    await api.uploadKnowledgeDocument(selectedKnowledgeVersionId.value, knowledgeFile.value, csrf.value)
    knowledgeFile.value = null
    knowledgeUploadOpen.value = false
    await refreshKnowledgeOperations()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { knowledgeBusy.value = false }
}

async function buildKnowledgeIndex() {
  if (!selectedKnowledgeVersionId.value) return
  knowledgeBusy.value = true; error.value = ''
  try { await api.buildKnowledgeIndex(selectedKnowledgeVersionId.value, csrf.value); await refreshKnowledgeOperations() }
  catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { knowledgeBusy.value = false }
}

async function runKnowledgeRetrievalTest() {
  if (!selectedKnowledgeVersionId.value || !knowledgeRetrievalQuery.value.trim()) return
  knowledgeBusy.value = true; error.value = ''
  try { knowledgeRetrievalHits.value = await api.testKnowledgeRetrieval(selectedKnowledgeVersionId.value, knowledgeRetrievalQuery.value.trim(), 5, csrf.value) }
  catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { knowledgeBusy.value = false }
}
async function saveDraft() {
  if (!selectedAgent.value || !draft.value) return
  builderSaving.value = true; error.value = ''
  try {
    draft.value = await api.saveConfigurationDraft(selectedAgent.value.deployment_id, {
      specification: draft.value.specification, base_revision_id: draft.value.base_revision_id, lock_version: draft.value.lock_version,
    }, csrf.value)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { builderSaving.value = false }
}
async function preflight() {
  if (!selectedAgent.value || !draft.value) return
  await saveDraft()
  validation.value = await api.validateConfigurationDraft(selectedAgent.value.deployment_id, { specification: draft.value.specification, base_revision_id: draft.value.base_revision_id }, csrf.value)
}
async function publishDraft() {
  if (!selectedAgent.value || !draft.value || !validation.value?.valid) return
  const publicationSubjects = agentPublicationBindings()
  if (agentPublicationScope.value === 'OWNER_DEPT' && publicationSubjects.filter(item => item.subject_type === 'DEPT').length !== 1) {
    error.value = '部门范围需要选择一个 RuoYi 部门'; return
  }
  if (agentPublicationScope.value === 'SELECTED_SUBJECTS' && !publicationSubjects.length) {
    error.value = '指定范围至少选择一个 RuoYi 用户、角色或部门'; return
  }
  builderPublishing.value = true
  try {
    await api.publishConfiguration(selectedAgent.value.deployment_id, draft.value.specification, csrf.value, draft.value.base_revision_id, {
      publication_scope: agentPublicationScope.value, publication_subjects: publicationSubjects,
    })
    agentDetail.value = await api.deploymentCapabilities(selectedAgent.value.deployment_id)
    draft.value = await api.configurationDraft(selectedAgent.value.deployment_id)
    validation.value = null
    await loadAgents()
    error.value = ''
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { builderPublishing.value = false }
}

async function openConversation(deploymentId: string) {
  conversations.value = await api.listConversations(deploymentId)
  if (!conversations.value.length) {
    const created = await api.createConversation(deploymentId, csrf.value)
    conversations.value = [created.conversation]
    selectedConversationId.value = created.conversation.conversation_id; selectedThreadId.value = created.thread.thread_id
  } else {
    selectedConversationId.value = conversations.value[0].conversation_id
    const threads = await api.listThreads(selectedConversationId.value)
    selectedThreadId.value = threads[0]?.thread_id || ''
  }
  messages.value = selectedThreadId.value ? await api.listMessages(selectedThreadId.value) : []
  memory.value = memoryEnabled.value ? await api.listMemory(deploymentId) : []
}
async function newConversation() {
  if (!selectedAgent.value) return
  conversationCreating.value = true
  try {
    const created = await api.createConversation(selectedAgent.value.deployment_id, csrf.value, conversationTitle.value.trim() || '新会话')
    conversations.value = [created.conversation, ...conversations.value]
    selectedConversationId.value = created.conversation.conversation_id; selectedThreadId.value = created.thread.thread_id; messages.value = []
    conversationCreatorOpen.value = false
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { conversationCreating.value = false }
}
function openConversationCreator() { conversationTitle.value = ''; conversationCreatorOpen.value = true }
async function selectConversation(conversation: ConversationRecord) {
  if (!selectedAgent.value) return
  selectedConversationId.value = conversation.conversation_id
  const threads = await api.listThreads(conversation.conversation_id)
  selectedThreadId.value = threads[0]?.thread_id || ''
  messages.value = selectedThreadId.value ? await api.listMessages(selectedThreadId.value) : []
}
function openConversationRename(conversation: ConversationRecord) {
  conversationRenameId.value = conversation.conversation_id
  conversationRenameTitle.value = conversation.title || ''
  conversationRenameOpen.value = true
}
async function renameCurrentConversation() {
  if (!conversationRenameId.value || !conversationRenameTitle.value.trim()) return
  conversationCreating.value = true; error.value = ''
  try {
    const updated = await api.renameConversation(conversationRenameId.value, conversationRenameTitle.value.trim(), csrf.value)
    conversations.value = conversations.value.map(item => item.conversation_id === updated.conversation_id ? updated : item)
    conversationRenameOpen.value = false
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { conversationCreating.value = false }
}
async function createLongTermMemory(content = memoryContent.value, sourceRunId?: string) {
  if (!selectedAgent.value || !content.trim() || !memoryEnabled.value) return
  memorySaving.value = true; error.value = ''
  try {
    await api.createMemory(selectedAgent.value.deployment_id, memoryCategory.value.trim() || 'preference', content.trim(), csrf.value, sourceRunId)
    memory.value = await api.listMemory(selectedAgent.value.deployment_id)
    memoryContent.value = ''; memoryCreatorOpen.value = false
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { memorySaving.value = false }
}
async function deleteLongTermMemory(item: MemoryItem) {
  if (!selectedAgent.value || !confirm('确认删除这条长期记忆？删除后新会话将不再加载它。')) return
  memorySaving.value = true; error.value = ''
  try {
    await api.deleteMemory(item.memory_id, csrf.value)
    memory.value = await api.listMemory(selectedAgent.value.deployment_id)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { memorySaving.value = false }
}
async function sendMessage() {
  if (!selectedAgent.value || !selectedConversationId.value || !selectedThreadId.value || !message.value.trim()) return
  const content = message.value.trim(); message.value = ''; loading.value = true; reply.value = ''; runEvents.value = []; traceExpanded.value = true
  messages.value = [...messages.value, { message_id: `pending-${Date.now()}`, thread_id: selectedThreadId.value, role: 'USER', content, created_at: new Date().toISOString() }]
  try {
    const run = await api.createRun(selectedAgent.value.deployment_id, content, selectedConversationId.value, selectedThreadId.value, csrf.value)
    activeRunId.value = run.run_id
    const events = await api.events(run.run_id, csrf.value, event => runEvents.value = [...runEvents.value, event])
    if (!runEvents.value.length) runEvents.value = events
    const failure = runEvents.value.find(event => event.event === 'runtime.failed')
    const output = runEvents.value.find(event => event.event === 'runtime.output')?.data.content || runEvents.value.find(event => event.event === 'run.completed')?.data.output || runEvents.value.find(event => event.event === 'model.completed')?.data.content
    reply.value = output ? String(output) : failure ? `运行失败：${String(failure.data.code || 'RUNTIME_EXECUTION_FAILED')}。请重试；若持续失败，请在运行治理中查看该 Run 的详情。` : '运行已完成，但没有产生文本回答。请展开运行过程查看详情。'
    messages.value = await api.listMessages(selectedThreadId.value)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { loading.value = false; traceExpanded.value = false }
}

watch([resourceQuery, resourceType], () => { if (principal.value && isAdmin.value) void loadResources() })
watch([agentQuery, agentActive], () => { if (principal.value) void loadAgents() })
watch(() => route.fullPath, () => { if (principal.value) void applyRouteState() })
onMounted(loadSession)
</script>

<template>
  <main v-if="!principal" class="login-screen">
    <section class="login-card product-card">
      <div class="brand-symbol">A</div>
      <p class="eyebrow">ENTERPRISE AGENT PLATFORM</p>
<h1>企业智能体平台</h1>
      <p class="subtle">使用 RuoYi 账号进入智能体工作台。</p>
      <template v-if="authMode === 'password'">
<label>用户名<input v-model="username" />
</label>
<label>密码<input v-model="password" type="password" />
</label>
<label>验证码</label>
<div class="captcha">
<input v-model="captchaCode" />
<img :src="captchaImage" alt="验证码" @click="refreshCaptcha" />
<button class="button ghost" @click="refreshCaptcha">换一张</button>
</div>
</template>
      <template v-else>
<label>Ticket<input v-model="ticket" />
</label>
</template>
      <button class="button primary wide" :disabled="loading" @click="login">{{ loading ? '登录中…' : '登录平台' }}</button>
<p v-if="error" class="notice error">{{ error }}</p>
    </section>
  </main>

  <main v-else class="product-shell">
    <aside class="sidebar">
      <button class="sidebar-brand" @click="goWorkspaceAgents">
<span class="brand-symbol small">A</span>
<span>
<b>企业智能体平台</b>
<small>Agent Platform</small>
</span>
</button>
      <div class="space-switch">
<button :class="{ active: space === 'workspace' }" @click="goWorkspaceAgents">使用工作台</button>
<button v-if="isAdmin" :class="{ active: space === 'console' }" @click="goConsole('overview')">管理控制台</button>
</div>
      <nav v-if="space === 'workspace'" class="nav-list">
<button :class="{ active: workspaceView === 'agents' }" @click="goWorkspaceAgents">智能体广场</button>
<button :class="{ active: workspaceView === 'chat' }" :disabled="!selectedAgent" @click="selectedAgent && router.push(`/workspace/agents/${selectedAgent.deployment_id}/chat`)">我的会话</button>
</nav>
      <nav v-else class="nav-list">
<p>管理</p>
<button :class="{ active: consoleView === 'overview' }" @click="goConsole('overview')">概览</button>
<button :class="{ active: consoleView === 'agents' }" @click="goConsole('agents')">智能体管理</button>
<button :class="{ active: consoleView === 'resources' }" @click="goConsole('resources')">能力中心</button>
<button :class="{ active: consoleView === 'connections' }" @click="goConsole('connections')">系统连接</button>
<button :class="{ active: consoleView === 'knowledge' }" @click="goConsole('knowledge')">知识库运营</button>
<p>治理</p>
<button :class="{ active: consoleView === 'runs' }" @click="goConsole('runs')">运行治理</button>
<button :class="{ active: consoleView === 'permissions' }" @click="goConsole('permissions')">权限与审计</button>
</nav>
      <div class="sidebar-user">
<span class="user-avatar">{{ principal.display_name.slice(0, 1) }}</span>
<div>
<b>{{ principal.display_name }}</b>
<small>{{ isAdmin ? '平台管理员' : '平台用户' }}</small>
</div>
<button class="icon-button" title="退出" @click="logout">↗</button>
</div>
    </aside>

    <section class="content-shell">
      <header class="content-topbar">
<div>
<span class="crumb">{{ space === 'workspace' ? '使用工作台' : '管理控制台' }}</span>
<b>{{ space === 'workspace' ? (workspaceView === 'chat' ? '在线对话' : '智能体广场') : consoleTitle(consoleView) }}</b>
</div>
<button class="button ghost" @click="refreshData">刷新数据</button>
</header>

      <AgentMarketplacePage v-if="space === 'workspace' && workspaceView === 'agents'" :agents="agents" :query="agentQuery" :loading="agentLoading" @update:query="agentQuery = $event" @open="openAgent" />

<ChatWorkspacePage
        v-else-if="space === 'workspace' && workspaceView === 'chat' && selectedAgent"
        v-model:conversation-creator-open="conversationCreatorOpen"
        v-model:conversation-title="conversationTitle"
        v-model:memory-creator-open="memoryCreatorOpen"
        v-model:memory-category="memoryCategory"
        v-model:memory-content="memoryContent"
        v-model:conversation-rename-open="conversationRenameOpen"
        v-model:conversation-rename-title="conversationRenameTitle"
        v-model:trace-expanded="traceExpanded"
        v-model:message="message"
        :selected-agent="selectedAgent"
        :conversations="conversations"
        :selected-conversation-id="selectedConversationId"
        :memory-enabled="memoryEnabled"
        :memory="memory"
        :messages="messages"
        :current-capabilities="currentCapabilities"
        :run-events="runEvents"
        :trace-duration="traceDuration"
        :trace-tool-calls="traceToolCalls"
        :trace-rag-hits="traceRagHits"
        :trace-memory-count="traceMemoryCount"
        :reply="reply"
        :loading="loading"
        :conversation-creating="conversationCreating"
        :memory-saving="memorySaving"
        :open-conversation-creator="openConversationCreator"
        :new-conversation="newConversation"
        :select-conversation="selectConversation"
        :open-conversation-rename="openConversationRename"
        :create-long-term-memory="createLongTermMemory"
        :delete-long-term-memory="deleteLongTermMemory"
        :rename-current-conversation="renameCurrentConversation"
        :send-message="sendMessage"
        :short-time="shortTime"
        :trace-event-label="traceEventLabel"
        :trace-event-summary="traceEventSummary"
        :back-to-agents="goWorkspaceAgents"
      />

      <ConsoleOverviewPage v-else-if="space === 'console' && consoleView === 'overview'" :agents="agents" :resources="resources" :catalog="catalog" :observability="observability" @refresh-observability="loadObservability" @show-agents="goConsole('agents')" @open-agent="item => openAgent(item, true)" />

<CapabilityListPage
        v-else-if="space === 'console' && consoleView === 'resources'"
        v-model:resource-query="resourceQuery"
        v-model:resource-type="resourceType"
        v-model:resource-composer-open="resourceComposerOpen"
        v-model:resource-wizard-step="resourceWizardStep"
        v-model:resource-category="resourceCategory"
        v-model:resource-form="resourceForm"
        v-model:ragflow-datasets="ragflowDatasets"
        :capability-resources="capabilityResources"
        :resource-loading="resourceLoading"
        :principal="principal"
        :iam-users="iamUsers"
        :iam-departments="iamDepartments"
        :iam-roles="iamRoles"
        :resource-saving="resourceSaving"
        :ragflow-discovering="ragflowDiscovering"
        :open-resource-wizard="openResourceWizard"
        :open-resource="openResource"
        :type-label="typeLabel"
        :health-label="healthLabel"
        :short-time="shortTime"
        :select-resource-category="selectResourceCategory"
        :catalog-for="catalogFor"
        :embedding-models="embeddingModels"
        :option-label="optionLabel"
        :toggle-skill-dependency="toggleSkillDependency"
        :discover-ragflow-datasets="discoverRagflowDatasets"
        :next-resource-wizard-step="nextResourceWizardStep"
        :create-typed-resource="createTypedResource"
      />

      <SystemConnectionsPage
        v-else-if="space === 'console' && consoleView === 'connections'"
        :resources="connectionResources"
        :loading="resourceLoading"
        :secrets="secrets"
        :secret-loading="secretLoading"
        :secret-saving="secretSaving"
        @add="openConnectionWizard"
        @open="openResource"
        @refresh-secrets="loadSecrets"
        @rotate-secret="rotateSecret"
        @disable-secret="disableSecret"
      />

      <KnowledgeOperationsPage
        v-else-if="space === 'console' && consoleView === 'knowledge'"
        :resources="knowledgeResources"
        :selected="selectedKnowledge"
        :busy="knowledgeBusy"
        :query="knowledgeQuery"
        :provider-filter="knowledgeProviderFilter"
        :provider-options="knowledgeProviderOptions"
        :documents="knowledgeDocuments"
        :jobs="knowledgeJobs"
        :indexes="knowledgeIndexes"
        :hits="knowledgeRetrievalHits"
        :retrieval-query="knowledgeRetrievalQuery"
        :upload-open="knowledgeUploadOpen"
        :file="knowledgeFile"
        @update:query="knowledgeQuery = $event"
        @update:provider-filter="knowledgeProviderFilter = $event"
        @update:retrieval-query="knowledgeRetrievalQuery = $event"
        @update:upload-open="knowledgeUploadOpen = $event"
        @refresh="refreshKnowledgeOperations"
        @add="openKnowledgeWizard"
        @open="openKnowledgeOperations"
        @build="buildKnowledgeIndex"
        @retrieve="runKnowledgeRetrievalTest"
        @choose-file="chooseKnowledgeFile"
        @upload="uploadKnowledgeFile"
      />

      <AgentManagementPage
        v-else-if="space === 'console' && consoleView === 'agents'"
        v-model:query="agentQuery"
        v-model:active="agentActive"
        v-model:creator-open="agentCreatorOpen"
        v-model:create-form="agentCreateForm"
        v-model:publication-scope="agentPublicationScope"
        v-model:publication-subjects="agentPublicationSubjects"
        :agents="agents"
        :loading="agentLoading"
        :creating="agentCreating"
        :detail="agentDetail"
        :draft="draft"
        :validation="validation"
        :catalog="catalog"
        :saving="builderSaving"
        :publishing="builderPublishing"
        :users="iamUsers"
        :departments="iamDepartments"
        :roles="iamRoles"
        @open-creator="openAgentCreator"
        @create="createAgentFromForm"
        @open="item => openAgent(item, true)"
        @delete="deleteAgent"
        @close-builder="selectedAgent = null; agentDetail = null; draft = null"
        @save-draft="saveDraft"
        @single="setSingle"
        @many="toggleDraftCapability"
        @preflight="preflight"
        @publish="publishDraft"
      />

      <RunGovernancePage
        v-else-if="space === 'console' && consoleView === 'runs'"
        :runs="governanceRuns"
        :summary="observability"
        :selected="selectedGovernanceRun"
        :loading="runGovernanceLoading"
        @refresh="refreshRunGovernance"
        @open="openGovernanceRun"
        @close="closeGovernanceRun"
      />

      <PermissionAuditPage
        v-else-if="space === 'console' && consoleView === 'permissions'"
        :grants="permissionGrants"
        :audits="auditEvents"
        :resources="resources"
        :agents="agents"
        :users="iamUsers"
        :roles="iamRoles"
        :departments="iamDepartments"
        :loading="permissionLoading"
        @refresh="loadPermissionData"
        @create="createPermissionGrant"
        @revoke="revokePermissionGrant"
      />

    </section>

<CapabilityDetailPage
      v-if="selectedResource"
      v-model:resource-detail-tab="resourceDetailTab"
      v-model:descriptor-editing="descriptorEditing"
      v-model:descriptor-form="descriptorForm"
      v-model:mcp-tool-drafts="mcpToolDrafts"
      :selected-resource="selectedResource"
      :selected-knowledge="selectedKnowledge"
      :resource-impact="resourceImpact"
      :principal="principal"
      :iam-users="iamUsers"
      :iam-departments="iamDepartments"
      :iam-roles="iamRoles"
      :resource-saving="resourceSaving"
      :mcp-discovered-tools="mcpDiscoveredTools"
      :mcp-discovering="mcpDiscovering"
      :mcp-registering="mcpRegistering"
      :validation-runs-by-version="validationRunsByVersion"
      :csrf="csrf"
      :close-detail="closeDetail"
      :type-label="typeLabel"
      :health-label="healthLabel"
      :status-label="statusLabel"
      :short-time="shortTime"
      :save-descriptor="saveDescriptor"
      :discover-selected-mcp-tools="discoverSelectedMcpTools"
      :register-selected-mcp-tools="registerSelectedMcpTools"
      :can-retry-resource-version="canRetryResourceVersion"
      :retry-validate-and-publish="retryValidateAndPublish"
      :delete-resource="deleteResource"
    />
    <p v-if="error" class="toast error">{{ error }}</p>
  </main>
</template>
