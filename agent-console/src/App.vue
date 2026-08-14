<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { consolePaths } from './app/navigation'
import {
  api, type AgentWorkbenchItem, type CatalogItem, type ConfigurationDraft,
  type ConfigurationValidation, type ConversationMessage, type ConversationRecord,
  type DeploymentCapabilities, type IamSubject, type IngestJob, type KnowledgeDocument, type KnowledgeIndex,
  type KnowledgeOverview, type MemoryItem, type Principal, type ResourceDetail, type ResourceListItem, type RunEvent,
} from './api'
import AgentModuleBoard from './components/AgentModuleBoard.vue'

type Space = 'workspace' | 'console'
type WorkspaceView = 'agents' | 'chat'
type ConsoleView = 'overview' | 'agents' | 'resources' | 'knowledge' | 'runs' | 'permissions'
type ResourceType = 'ALL' | 'MODEL' | 'PROMPT' | 'SKILL' | 'TOOL' | 'MCP_CONNECTION' | 'KNOWLEDGE' | 'MEMORY_POLICY'

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
const selectedAgent = ref<AgentWorkbenchItem | null>(null)
const selectedResource = ref<ResourceDetail | null>(null)
const selectedKnowledge = ref<KnowledgeOverview | null>(null)
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
const builderStep = ref(1)
const builderSaving = ref(false)
const builderPublishing = ref(false)
const agentPublicationScope = ref<'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'>('PERSONAL')
const agentPublicationSubjects = ref<string[]>([])
const showAdvancedJson = ref(false)
const draftJson = ref('{}')
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
  type: 'PROMPT', displayName: '', slug: '', description: '', template: '', skillMd: '', nativeName: 'echo',
  oneLineSummary: '', whenToUse: '', whenNotToUse: '', inputSummary: '', outputSummary: '', riskLevel: 'LOW', readOnly: true,
  ownerUserId: '', ownerDeptId: '', tags: '',
  businessLine: '', dataInvolved: '', audience: '', usageScenarios: '', developerUserIds: [] as string[],
  publicationScope: 'PERSONAL' as 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS', publicationSubjects: [] as string[],
  embeddingModelVersionId: '', ttlDays: 30, maxItems: 50, categories: 'preference',
  modelBaseUrl: 'https://api.siliconflow.cn/v1', modelName: '', modelApiKey: '', modelMode: 'CHAT',
  mcpEndpoint: '', mcpApiKey: '', mcpTimeout: 10,
  difyBaseUrl: '', difyApiKey: '', difyFlowType: 'CHATFLOW', difyToolName: '', difyTimeout: 90,
  difyBusinessLine: '', difyDataInvolved: '', difyAudience: '', difyUsageScenarios: '', difyDeveloperUserIds: [] as string[],
  difyOpeningStatement: '', difySuggestedQuestions: '', difyPublicationScope: 'PERSONAL' as 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS',
  difyPublicationSubjects: [] as string[],
  skillToolVersionIds: [] as string[], skillKnowledgeVersionIds: [] as string[],
})
const knowledgeQuery = ref('')
const selectedKnowledgeVersionId = ref('')
const knowledgeDocuments = ref<KnowledgeDocument[]>([])
const knowledgeIndexes = ref<KnowledgeIndex[]>([])
const knowledgeJobs = ref<IngestJob[]>([])
const knowledgeFile = ref<File | null>(null)
const knowledgeUploadOpen = ref(false)
const knowledgeRetrievalQuery = ref('')
const knowledgeRetrievalHits = ref<Array<{ document_id: string; chunk_number: number; content: string; score: number }>>([])
const knowledgeBusy = ref(false)

const conversations = ref<ConversationRecord[]>([])
const selectedConversationId = ref('')
const selectedThreadId = ref('')
const conversationCreatorOpen = ref(false)
const conversationCreating = ref(false)
const conversationTitle = ref('')
const messages = ref<ConversationMessage[]>([])
const memory = ref<MemoryItem[]>([])
const message = ref('')
const reply = ref('')
const runEvents = ref<RunEvent[]>([])
const traceExpanded = ref(false)
const activeRunId = ref('')

const isAdmin = computed(() => Boolean(principal.value?.role_codes.includes('admin') || principal.value?.role_codes.includes('agent_admin')))
const currentCapabilities = computed(() => agentDetail.value?.capabilities || [])
const selectedSpec = computed<Record<string, unknown>>(() => draft.value?.specification || {})
const capabilityGroups = computed(() => {
  const grouped: Record<string, CatalogItem[]> = {}
  for (const item of currentCapabilities.value)
    (grouped[item.resource_type] ||= []).push(item)
  return grouped
})
const draftCapabilityGroups = computed(() => {
  const selected = new Set<string>()
  const spec = selectedSpec.value
  for (const key of ['model_version_id', 'prompt_version_id', 'memory_policy_version_id']) {
    if (spec[key]) selected.add(String(spec[key]))
  }
  for (const key of ['skill_version_ids', 'tool_version_ids', 'mcp_connection_version_ids', 'knowledge_version_ids']) {
    for (const id of (spec[key] as string[] || [])) selected.add(String(id))
  }
  const grouped: Record<string, CatalogItem[]> = {}
  for (const item of catalog.value.filter(item => selected.has(item.version_id)))
    (grouped[item.resource_type] ||= []).push(item)
  return grouped
})
const selectedSkillDependencies = computed(() => {
  const selected = new Set(selectedValues('skill_version_ids'))
  const direct = new Set(selectedValues('tool_version_ids').concat(selectedValues('knowledge_version_ids')))
  return catalog.value.filter(item => item.dependencies.length && selected.has(item.version_id)).flatMap(skill =>
    skill.dependencies.map(id => ({ skill: skill.display_name, item: catalog.value.find(candidate => candidate.version_id === id), direct: direct.has(id) })))
})

function typeLabel(type: string) {
  return ({ MODEL: '模型', PROMPT: '提示词', SKILL: '技能', TOOL: '工具', MCP_CONNECTION: 'MCP 连接', KNOWLEDGE: '知识库', MEMORY_POLICY: '记忆策略' } as Record<string, string>)[type] || type
}
function statusLabel(status?: string) {
  return ({ PUBLISHED: '已发布', DRAFT: '草稿', ACTIVE: '运行中', AVAILABLE: '可用', UNAVAILABLE: '不可用' } as Record<string, string>)[status || ''] || status || '—'
}
function shortTime(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '暂无' }
function requestId() { return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}` }
function consoleTitle(view: ConsoleView) {
  return ({ overview: '概览', agents: '智能体管理', resources: '资源中心', knowledge: '知识库运营', runs: '运行治理', permissions: '权限与审计' } as Record<ConsoleView, string>)[view]
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
    'console-connections': 'resources', 'console-connection-detail': 'resources',
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
  await Promise.all([loadAgents(), loadResources(), loadCatalog()])
}
async function loadCatalog() { if (isAdmin.value) catalog.value = await api.catalog() }
async function openResourceWizard() {
  resourceComposerOpen.value = true; resourceWizardStep.value = 1
  difyPublishResult.value = null
  resourceForm.value.ownerUserId ||= principal.value?.external_user_id || ''
  try {
    const [users, departments, roles] = await Promise.all([api.searchIamSubjects('USER'), api.searchIamSubjects('DEPT'), api.searchIamSubjects('ROLE')])
    iamUsers.value = users.items; iamDepartments.value = departments.items; iamRoles.value = roles.items
  } catch { /* Upstream directory may be unavailable; current principal remains a valid owner. */ }
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
    const message = validateResourceSemantics(); if (message) { error.value = message; return }
  }
  if (resourceWizardStep.value === 3 && resourceForm.value.type === 'DIFY_FLOW') {
    const message = validateDifyApplication(); if (message) { error.value = message; return }
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
    const data = await api.workbenchResources(resourceQuery.value, resourceType.value === 'ALL' ? '' : resourceType.value)
    resources.value = data.items
  } finally { resourceLoading.value = false }
}
async function openResource(item: ResourceListItem, updateRoute = true) {
  selectedKnowledge.value = null
  selectedResource.value = await api.workbenchResource(item.resource_id)
  populateDescriptorForm()
  if (updateRoute) void router.push(`/console/capabilities/${item.resource_id}`)
}
async function openKnowledge(item: ResourceListItem, updateRoute = true) {
  selectedResource.value = await api.workbenchResource(item.resource_id)
  selectedKnowledge.value = await api.workbenchKnowledge(item.resource_id)
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
  if (!selectedResource.value || !confirm(`确认删除资源“${selectedResource.value.resource.display_name}”？此操作仅允许删除未被引用、且没有知识文档的资源。`)) return
  try {
    await api.deleteWorkbenchResource(selectedResource.value.resource.resource_id, csrf.value)
    selectedResource.value = null; selectedKnowledge.value = null
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
  const slug = slugify(form.displayName)
  const deploymentName = form.deploymentName.trim() || `${form.displayName.trim()}-生产`
  agentCreating.value = true; error.value = ''
  try {
    const agent = await api.createAgent(slug, form.displayName.trim(), csrf.value, form.description.trim(), {})
    const version = await api.createVersion(agent.agent_id, csrf.value)
    await api.publishVersion(version.agent_version_id, csrf.value)
    const deployment = await api.createDeployment(agent.agent_id, deploymentName, csrf.value)
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
    draftJson.value = JSON.stringify(draft.value.specification, null, 2)
    agentPublicationScope.value = agentDetail.value.publication_scope || 'PERSONAL'
    agentPublicationSubjects.value = (agentDetail.value.publication_subjects || [])
      .filter(subject => !(subject.subject_type === 'USER' && subject.subject_id === principal.value?.external_user_id))
      .map(subject => difySubjectValue(subject.subject_type, subject.subject_id))
    validation.value = null; builderStep.value = 1
    space.value = 'console'; consoleView.value = 'agents'
    void router.push(`/console/agents/${item.deployment_id}/edit`)
  } else {
    space.value = 'workspace'; workspaceView.value = 'chat'
    void router.push(`/workspace/agents/${item.deployment_id}/chat`)
    await openConversation(item.deployment_id)
  }
}
function closeDetail() { selectedResource.value = null; if (space.value === 'workspace') selectedAgent.value = null }

function setSingle(field: string, value: string) {
  if (!draft.value) return
  draft.value.specification = { ...draft.value.specification, [field]: value || undefined }
  draftJson.value = JSON.stringify(draft.value.specification, null, 2)
}
function setMany(field: string, event: Event) {
  if (!draft.value) return
  const values = Array.from((event.target as HTMLSelectElement).selectedOptions).map(option => option.value)
  draft.value.specification = { ...draft.value.specification, [field]: values }
  draftJson.value = JSON.stringify(draft.value.specification, null, 2)
}
function toggleDraftCapability(field: string, versionId: string) { toggleMany(field, versionId) }
function toggleMany(field: string, versionId: string) {
  if (!draft.value) return
  const values = new Set(selectedValues(field))
  if (values.has(versionId)) values.delete(versionId)
  else values.add(versionId)
  draft.value.specification = { ...draft.value.specification, [field]: [...values] }
  draftJson.value = JSON.stringify(draft.value.specification, null, 2)
}
function isSelected(field: string, versionId: string) {
  return field.endsWith('_ids') ? selectedValues(field).includes(versionId) : selectedValue(field) === versionId
}
function selectedValue(field: string) { return String(selectedSpec.value[field] || '') }
function selectedValues(field: string) { return (selectedSpec.value[field] as string[] || []) }
function catalogFor(type: string) { return catalog.value.filter(item => item.resource_type === type) }
function embeddingModels() { return catalogFor('MODEL').filter(item => /embedding|bge|embed/i.test(`${item.summary} ${item.display_name}`)) }
function optionLabel(item: CatalogItem) { return `${item.display_name} · V${item.version_number} · ${statusLabel(item.status)}` }
function slugify(value: string) {
  const ascii = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63)
  return ascii.length >= 3 ? ascii : `resource-${Date.now().toString(36)}`
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
async function createTypedResource() {
  const form = resourceForm.value
  const semanticsError = validateResourceSemantics()
  if (semanticsError) { error.value = semanticsError; return }
  if (form.type === 'KNOWLEDGE' && !form.embeddingModelVersionId) { error.value = '知识库必须选择 Embedding 模型版本。'; return }
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

const knowledgeResources = computed(() => resources.value.filter(item =>
  item.resource_type === 'KNOWLEDGE'
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
function applyAdvancedJson() {
  try {
    if (!draft.value) return
    draft.value.specification = JSON.parse(draftJson.value)
    error.value = ''
  } catch { error.value = '高级 JSON 格式不正确，请修正后再应用。' }
}
async function saveDraft() {
  if (!selectedAgent.value || !draft.value) return
  builderSaving.value = true; error.value = ''
  try {
    draft.value = await api.saveConfigurationDraft(selectedAgent.value.deployment_id, {
      specification: draft.value.specification, base_revision_id: draft.value.base_revision_id, lock_version: draft.value.lock_version,
    }, csrf.value)
    draftJson.value = JSON.stringify(draft.value.specification, null, 2)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { builderSaving.value = false }
}
async function preflight() {
  if (!selectedAgent.value || !draft.value) return
  await saveDraft()
  validation.value = await api.validateConfigurationDraft(selectedAgent.value.deployment_id, { specification: draft.value.specification, base_revision_id: draft.value.base_revision_id }, csrf.value)
  builderStep.value = 5
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
  memory.value = await api.listMemory(deploymentId)
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
<button :class="{ active: consoleView === 'resources' }" @click="goConsole('resources')">资源中心</button>
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

      <section v-if="space === 'workspace' && workspaceView === 'agents'" class="page-content">
        <div class="page-hero">
<div>
<p class="eyebrow">AGENT WORKSPACE</p>
<h1>选择一个智能体开始工作</h1>
<p>智能体按你的租户和权限提供模型、知识、工具与记忆能力。</p>
</div>
</div>
        <div class="toolbar">
<div>
<h2>智能体广场</h2>
<span>{{ agents.filter(item => item.active).length }} 个可用智能体</span>
</div>
<input v-model="agentQuery" placeholder="搜索智能体名称或用途" />
</div>
        <div v-if="agentLoading" class="empty-panel">正在加载智能体…</div>
<div v-else-if="!agents.length" class="empty-panel">当前没有可用智能体。</div>
        <div v-else class="agent-grid">
<article v-for="item in agents" :key="item.deployment_id" class="agent-card product-card">
<div class="agent-card-top">
<div class="agent-logo">{{ item.display_name.slice(0, 1) }}</div>
<span :class="['status-pill', item.active ? 'success' : 'neutral']">{{ item.active ? '已启用' : '未启用' }}</span>
</div>
<h3>{{ item.display_name }}</h3>
<p>{{ item.description || '面向企业任务的智能体' }}</p>
<div class="tag-list">
<span v-for="(count, type) in item.capability_counts" :key="type">{{ count }} {{ typeLabel(type) }}</span>
</div>
<footer>
<small>最近运行：{{ shortTime(item.last_run_at) }}</small>
<button class="button primary" :disabled="!item.active" @click="openAgent(item)">开始对话</button>
</footer>
</article>
</div>
      </section>

      <section v-else-if="space === 'workspace' && workspaceView === 'chat' && selectedAgent" class="page-content chat-page">
        <div class="detail-header">
<button class="text-link" @click="workspaceView = 'agents'">‹ 返回智能体广场</button>
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
<button v-for="item in conversations" :key="item.conversation_id" :class="['conversation-item', { active: item.conversation_id === selectedConversationId }]" @click="selectConversation(item)">
<b>{{ item.title || '未命名会话' }}</b>
<small>{{ shortTime(item.updated_at) }}</small>
</button>
<div class="memory-summary">
<h3>长期记忆</h3>
<p>{{ memory.length ? `已加载 ${memory.length} 条个人记忆` : '当前没有长期记忆' }}</p>
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
<div v-for="item in messages" :key="item.message_id" :class="['message', item.role.toLowerCase()]">{{ item.content }}</div>
<details v-if="runEvents.length" class="trace-panel" :open="traceExpanded">
<summary>
<span>运行过程</span>
<small>{{ loading ? '执行中' : '已完成' }} · {{ runEvents.length }} 个事件</small>
</summary>
<article v-for="event in runEvents" :key="event.sequence">
<b>{{ event.event }}</b>
<p>{{ JSON.stringify(event.data) }}</p>
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
      </section>

      <section v-else-if="space === 'console' && consoleView === 'overview'" class="page-content">
<div class="page-hero compact">
<div>
<p class="eyebrow">ADMIN OVERVIEW</p>
<h1>智能体运营概览</h1>
<p>从资源、智能体、知识和运行四个维度管理企业 AI 能力。</p>
</div>
</div>
<div class="metric-grid">
<article class="metric product-card">
<small>已部署智能体</small>
<strong>{{ agents.filter(item => item.active).length }}</strong>
<span>可供业务用户使用</span>
</article>
<article class="metric product-card">
<small>资源 Definition</small>
<strong>{{ resources.length }}</strong>
<span>可版本化、可授权</span>
</article>
<article class="metric product-card">
<small>已发布版本</small>
<strong>{{ catalog.length }}</strong>
<span>可被 Agent 组装</span>
</article>
<article class="metric product-card">
<small>需要关注</small>
<strong>0</strong>
<span>当前无阻断告警</span>
</article>
</div>
<section class="product-card overview-section">
<div class="section-heading">
<div>
<h2>最近智能体</h2>
<p>进入配置查看能力组合、版本与运行。</p>
</div>
<button class="button ghost" @click="consoleView = 'agents'">查看全部</button>
</div>
<div class="simple-list">
<button v-for="item in agents.slice(0, 5)" :key="item.deployment_id" @click="openAgent(item, true)">
<span class="list-avatar">{{ item.display_name.slice(0, 1) }}</span>
<span>
<b>{{ item.display_name }}</b>
<small>{{ item.deployment_name }} · Revision {{ item.revision_number || '—' }}</small>
</span>
<em>{{ item.active ? '已启用' : '未启用' }}</em>
</button>
</div>
</section>
</section>

      <section v-else-if="space === 'console' && consoleView === 'resources'" class="page-content">
<div class="page-heading">
<div>
<p class="eyebrow">RESOURCE CENTER</p>
<h1>资源中心</h1>
<p>从名称、来源、负责人、版本与引用关系管理企业 AI 能力。</p>
</div>
<button class="button primary" @click="openResourceWizard">＋ 入驻新资源</button>
</div>
<div v-if="resourceComposerOpen" class="modal-backdrop resource-wizard-backdrop" @click.self="resourceComposerOpen = false">
<section class="resource-composer resource-wizard-modal" role="dialog" aria-modal="true" aria-label="资源入驻向导">
<header>
<div>
<h2>资源入驻向导</h2>
<p>先定义它是什么、何时使用和谁负责，再进行技术配置与发布。</p>
</div>
<button class="icon-button" aria-label="关闭" @click="resourceComposerOpen = false">×</button>
</header>
<div class="wizard-steps"><span v-for="item in [{n:1,t:'选择类别'},{n:2,t:'能力语义'},{n:3,t:'专属配置'},{n:4,t:'确认发布'}]" :key="item.n" :class="{ active: resourceWizardStep === item.n, done: resourceWizardStep > item.n }"><b>{{ item.n }}</b>{{ item.t }}</span></div>
<div v-if="resourceWizardStep === 1" class="resource-kind-picker">
<button :class="{ selected: resourceCategory === 'CAPABILITY' }" @click="selectResourceCategory('CAPABILITY')"><b>可组装能力</b><p>最终会出现在 Agent Assembly：Model、Prompt、Skill、Tool、Knowledge、Memory Policy。</p></button>
<button :class="{ selected: resourceCategory === 'EXTERNAL_APP' }" @click="selectResourceCategory('EXTERNAL_APP')"><b>发布 Dify 应用</b><p>参考智能体广场登记应用信息、RuoYi 可用范围并测试连接，最终生成可组装 External Tool。</p></button>
<button :class="{ selected: resourceCategory === 'CONNECTOR' }" @click="selectResourceCategory('CONNECTOR')"><b>连接器 / 基础设施</b><p>登记 MCP Connection；发现后的业务 Tool 才进入 Agent Assembly。</p></button>
<div class="resource-type-tiles" v-if="resourceCategory === 'CAPABILITY'">
<button v-for="item in [{v:'MODEL',n:'模型',d:'对话推理或 Embedding'},{v:'PROMPT',n:'提示词',d:'角色、边界和回答规则'},{v:'SKILL',n:'技能',d:'业务指令 + Tool/Knowledge 依赖'},{v:'TOOL',n:'原生工具',d:'平台受控实现'},{v:'KNOWLEDGE',n:'知识库',d:'文档、索引和检索'},{v:'MEMORY_POLICY',n:'记忆策略',d:'长期记忆读写边界'}]" :key="item.v" :class="{ selected: resourceForm.type === item.v }" @click="resourceForm.type = item.v"><b>{{ item.n }}</b><small>{{ item.d }}</small></button>
</div>
<div class="resource-type-tiles" v-else-if="resourceCategory === 'CONNECTOR'"><button class="selected"><b>MCP Connection</b><small>连接、发现后注册 MCP Tool</small></button></div>
<div class="resource-type-tiles" v-else><button class="selected"><b>Dify Flow Tool</b><small>业务应用登记 + 参数发现 + RuoYi 授权 + Tool 发布</small></button></div>
</div>
<div v-else-if="resourceWizardStep === 2" class="resource-form semantics-form">
<label>业务名称<input v-model="resourceForm.displayName" placeholder="如：企业知识问答提示词" />
</label>
<label>Slug（可选）<input v-model="resourceForm.slug" placeholder="自动由名称生成" />
</label>
<label class="wide-field">一句话能力<input v-model="resourceForm.oneLineSummary" placeholder="例：按客户编号查询 CRM 基本信息" /></label>
<label class="wide-field">详细说明<textarea v-model="resourceForm.description" rows="3" placeholder="业务目标、能力范围和边界" /></label>
<label>何时使用<textarea v-model="resourceForm.whenToUse" rows="3" placeholder="例：回答客户基本信息和归属部门问题时" /></label>
<label>何时不使用<textarea v-model="resourceForm.whenNotToUse" rows="3" placeholder="例：不用于修改客户数据" /></label>
<label>输入说明<textarea v-model="resourceForm.inputSummary" rows="3" placeholder="用户需要提供什么" /></label>
<label>输出说明<textarea v-model="resourceForm.outputSummary" rows="3" placeholder="资源会返回什么" /></label>
<label>RuoYi 负责人<select v-model="resourceForm.ownerUserId"><option :value="principal?.external_user_id">{{ principal?.display_name }}（当前用户）</option><option v-for="item in iamUsers" :key="item.external_id" :value="item.external_id">{{ item.display_name }} · {{ item.external_id }}</option></select></label>
<label>责任部门<select v-model="resourceForm.ownerDeptId"><option value="">不指定</option><option v-for="item in iamDepartments" :key="item.external_id" :value="item.external_id">{{ item.display_name }}</option></select></label>
<label>风险等级<select v-model="resourceForm.riskLevel"><option value="LOW">低</option><option value="MEDIUM">中</option><option value="HIGH">高</option></select></label>
<label class="check-label"><input v-model="resourceForm.readOnly" type="checkbox" />只读，不修改外部数据</label>
<label class="wide-field">标签<input v-model="resourceForm.tags" placeholder="客服, CRM, 只读" /></label>
<template v-if="resourceForm.type !== 'DIFY_FLOW'">
<div class="dify-section-title wide-field"><b>业务运营信息</b><span>记录资源归属、使用对象和安全说明；可用范围在下一步专属配置中设置。</span></div>
<label>所属业务线<input v-model="resourceForm.businessLine" placeholder="例如：人力资源、客服、研发" /></label>
<label>使用对象<input v-model="resourceForm.audience" placeholder="例如：全体员工、客服人员" /></label>
<label class="wide-field">使用场景<textarea v-model="resourceForm.usageScenarios" rows="2" placeholder="说明在什么业务任务中使用此资源" /></label>
<label class="wide-field">涉及数据<textarea v-model="resourceForm.dataInvolved" rows="2" placeholder="说明会处理的数据类别，供安全审查" /></label>
</template>
</div>
<div v-else-if="resourceWizardStep === 3" class="resource-form">
<template v-if="resourceForm.type === 'MODEL'">
<label>Endpoint<input v-model="resourceForm.modelBaseUrl" placeholder="https://api.example.com/v1" /></label>
<label>模型名<input v-model="resourceForm.modelName" placeholder="Qwen/Qwen3-8B" /></label>
<label>模型用途<select v-model="resourceForm.modelMode"><option value="CHAT">对话 / Tool Calling</option><option value="EMBEDDING">Embedding</option></select></label>
<label class="wide-field">API Key<input v-model="resourceForm.modelApiKey" type="password" autocomplete="new-password" placeholder="仅本次提交，后端加密保存" /></label>
</template>
<template v-else-if="resourceForm.type === 'PROMPT'">
<label class="wide-field">提示词模板<textarea v-model="resourceForm.template" rows="5" placeholder="定义 Agent 的系统提示词" />
</label>
</template>
<template v-else-if="resourceForm.type === 'SKILL'">
<label class="wide-field">SKILL.md<textarea v-model="resourceForm.skillMd" rows="7" placeholder="# Skill\n描述技能目标、边界与使用方式" />
</label>
<label>依赖工具<select v-model="resourceForm.skillToolVersionIds" multiple><option v-for="item in catalogFor('TOOL')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option></select></label>
<label>依赖知识库<select v-model="resourceForm.skillKnowledgeVersionIds" multiple><option v-for="item in catalogFor('KNOWLEDGE')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option></select></label>
</template>
<template v-else-if="resourceForm.type === 'TOOL'">
<label>原生工具<select v-model="resourceForm.nativeName">
<option value="echo">Echo</option>
<option value="calculator">Calculator</option>
<option value="current_time">Current Time</option>
</select>
</label>
</template>
<template v-else-if="resourceForm.type === 'DIFY_FLOW'">
<div class="dify-section-title wide-field"><b>1. Dify 应用连接</b><span>使用 Dify 应用 API 地址和 App API Key；Key 仅提交到后端 Vault。</span></div>
<label>Dify API Base URL<input v-model="resourceForm.difyBaseUrl" placeholder="https://dify.example.com/v1" /></label>
<label>应用类型<select v-model="resourceForm.difyFlowType"><option value="CHATFLOW">Chatflow</option><option value="WORKFLOW">Workflow</option></select></label>
<label>Tool Name<input v-model="resourceForm.difyToolName" placeholder="enterprise_knowledge_flow" /></label>
<label>调用超时（秒）<input v-model.number="resourceForm.difyTimeout" type="number" min="1" max="300" /></label>
<label class="wide-field">App API Key<input v-model="resourceForm.difyApiKey" type="password" autocomplete="new-password" placeholder="仅本次提交；保存后不回显" /></label>
<div class="dify-section-title wide-field"><b>2. 应用运营信息</b><span>沿用智能体广场的业务登记逻辑，供资源详情和组装人员判断用途。</span></div>
<label>所属业务线<input v-model="resourceForm.difyBusinessLine" placeholder="如：人力资源、客户服务" /></label>
<label>使用对象<input v-model="resourceForm.difyAudience" placeholder="如：全体员工、客服人员" /></label>
<label class="wide-field">使用场景<textarea v-model="resourceForm.difyUsageScenarios" rows="3" placeholder="描述用户在什么任务中使用这个 Dify 应用" /></label>
<label class="wide-field">涉及数据<textarea v-model="resourceForm.difyDataInvolved" rows="3" placeholder="列出会发送到 Dify 或由 Dify 返回的数据类型，供安全审查" /></label>
<label class="wide-field">开场白<textarea v-model="resourceForm.difyOpeningStatement" rows="3" placeholder="可选；留空时读取 Dify 应用参数" /></label>
<label class="wide-field">建议问题（每行一个）<textarea v-model="resourceForm.difySuggestedQuestions" rows="3" placeholder="如何查询员工制度？&#10;帮我总结这份材料" /></label>
<p class="dify-security-note wide-field">确认发布时后端会先读取 Dify 参数并校验凭据，再创建 Tool V1、资源语义和版本级 VIEW/USE 授权。任一步校验失败都不会返回可用资源。</p>
</template>
<template v-else-if="resourceForm.type === 'MCP_CONNECTION'">
<label class="wide-field">Streamable HTTP Endpoint<input v-model="resourceForm.mcpEndpoint" placeholder="https://mcp.example.com/mcp" /></label>
<label>超时（秒）<input v-model.number="resourceForm.mcpTimeout" type="number" min="1" max="60" /></label>
<label>API Key（可选）<input v-model="resourceForm.mcpApiKey" type="password" autocomplete="new-password" placeholder="Bearer token" /></label>
</template>
<template v-else-if="resourceForm.type === 'KNOWLEDGE'">
<label>Embedding 模型版本<select v-model="resourceForm.embeddingModelVersionId">
<option value="">请选择已发布 Embedding 模型</option>
<option v-for="item in embeddingModels()" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
</template>
<template v-else-if="resourceForm.type === 'MEMORY_POLICY'">
<label>TTL（天）<input v-model.number="resourceForm.ttlDays" type="number" min="1" />
</label>
<label>最大条数<input v-model.number="resourceForm.maxItems" type="number" min="1" />
</label>
<label class="wide-field">允许分类（逗号分隔）<input v-model="resourceForm.categories" />
</label>
</template>
<div class="dify-section-title wide-field"><b>RuoYi 可用范围</b><span>选择谁可以查看和使用该资源；负责人始终保留管理权限。</span></div>
<template v-if="resourceForm.type === 'DIFY_FLOW'">
<label>可用范围<select v-model="resourceForm.difyPublicationScope"><option value="PERSONAL">仅负责人</option><option value="OWNER_DEPT">责任部门可用</option><option value="SELECTED_SUBJECTS">指定用户 / 角色 / 部门</option></select></label>
<label v-if="resourceForm.difyPublicationScope === 'SELECTED_SUBJECTS'" class="wide-field">指定 RuoYi 范围<select v-model="resourceForm.difyPublicationSubjects" multiple><option v-for="item in difyPublicationOptions()" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
</template>
<template v-else>
<label>可用范围<select v-model="resourceForm.publicationScope"><option value="PERSONAL">仅负责人</option><option value="OWNER_DEPT">责任部门可用</option><option value="SELECTED_SUBJECTS">指定用户 / 角色 / 部门</option></select></label>
<label v-if="resourceForm.publicationScope === 'SELECTED_SUBJECTS'" class="wide-field">指定 RuoYi 范围<select v-model="resourceForm.publicationSubjects" multiple><option v-for="item in difyPublicationOptions()" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
</template>
</div>
<div v-else class="resource-publish-review">
<div class="semantic-preview"><span class="type-badge">{{ resourceCategory === 'CAPABILITY' ? '可组装能力' : resourceCategory === 'EXTERNAL_APP' ? 'Dify 外部应用' : '连接器' }}</span><h3>{{ resourceForm.displayName }}</h3><strong>{{ resourceForm.oneLineSummary }}</strong><p>{{ resourceForm.description }}</p><dl><dt>何时使用</dt><dd>{{ resourceForm.whenToUse }}</dd><dt>输入</dt><dd>{{ resourceForm.inputSummary }}</dd><dt>输出</dt><dd>{{ resourceForm.outputSummary }}</dd><dt>负责人</dt><dd>{{ iamUsers.find(item => item.external_id === resourceForm.ownerUserId)?.display_name || principal?.display_name }}</dd><dt>风险</dt><dd>{{ resourceForm.riskLevel }} · {{ resourceForm.readOnly ? '只读' : '可写' }}</dd><dt>可用范围</dt><dd>{{ {PERSONAL:'仅负责人',OWNER_DEPT:'责任部门',SELECTED_SUBJECTS:'指定主体'}[resourceForm.type === 'DIFY_FLOW' ? resourceForm.difyPublicationScope : resourceForm.publicationScope] }}</dd><template v-if="resourceForm.type === 'DIFY_FLOW'"><dt>业务线</dt><dd>{{ resourceForm.difyBusinessLine }}</dd><dt>使用对象</dt><dd>{{ resourceForm.difyAudience }}</dd></template></dl></div>
<div class="publish-note"><b>{{ resourceCategory === 'EXTERNAL_APP' ? '测试 Dify 并发布为可组装 Tool' : resourceCategory === 'CAPABILITY' ? '发布后可进入 Agent Assembly' : '这是基础设施，不直接组装进 Agent' }}</b><p v-if="resourceCategory === 'CONNECTOR'">MCP 连接发布后需要发现并注册 Tool。</p><p v-if="resourceCategory === 'EXTERNAL_APP'">将读取 Dify 输入参数、加密保存 Key，并在确认发布时按 RuoYi 可用范围创建资源授权。</p></div>
</div>
<footer>
<button class="button ghost" @click="resourceWizardStep === 1 ? resourceComposerOpen = false : resourceWizardStep--">{{ resourceWizardStep === 1 ? '取消' : '上一步' }}</button>
<button v-if="resourceWizardStep < 4" class="button primary" @click="nextResourceWizardStep">下一步</button>
<button v-else class="button primary" :disabled="resourceSaving" @click="createTypedResource">{{ resourceSaving ? '测试并发布中…' : '确认发布 V1' }}</button>
</footer>
</section>
</div>
<div class="filter-bar product-card">
<input v-model="resourceQuery" placeholder="搜索资源名称、Slug 或说明" />
<select v-model="resourceType">
<option value="ALL">全部类型</option>
<option value="MODEL">模型</option>
<option value="PROMPT">提示词</option>
<option value="SKILL">技能</option>
<option value="TOOL">工具 / Dify</option>
<option value="MCP_CONNECTION">MCP 连接</option>
<option value="KNOWLEDGE">知识库</option>
<option value="MEMORY_POLICY">记忆策略</option>
</select>
</div>
<div class="resource-card-grid">
<button v-for="item in resources" :key="item.resource_id" class="resource-card product-card" @click="item.resource_type === 'KNOWLEDGE' ? openKnowledge(item) : openResource(item)">
<div class="resource-card-top">
<span class="type-badge">{{ typeLabel(item.resource_type) }}</span>
<span :class="['status-pill', item.lifecycle_status === 'ARCHIVED' ? 'blocked' : 'success']">{{ item.lifecycle_status === 'ARCHIVED' ? '已归档' : '可用' }}</span>
</div>
<h3>{{ item.display_name }}</h3>
<p>{{ item.description || item.slug }}</p>
<div class="tag-list compact">
<span>{{ item.source_type }}</span>
<span>V{{ item.latest_version_number || '—' }}</span>
<span>{{ item.referenced_by_count }} 个引用</span>
</div>
<footer>
<small>负责人：{{ item.owner_user_id || '历史导入' }}</small>
<small>{{ shortTime(item.updated_at) }}</small>
</footer>
</button>
<p v-if="resourceLoading" class="empty-copy">加载中…</p>
<p v-else-if="!resources.length" class="empty-copy">暂无符合条件的资源。</p>
</div>
</section>

      <section v-else-if="space === 'console' && consoleView === 'knowledge'" class="page-content knowledge-operations">
<div class="page-heading">
<div><p class="eyebrow">KNOWLEDGE OPERATIONS</p><h1>知识库运营</h1><p>管理文档、Ingest 任务、索引版本和检索效果，文件经 API 上传到 MinIO。</p></div>
<button class="button ghost" :disabled="knowledgeBusy" @click="refreshKnowledgeOperations">刷新当前知识库</button>
</div>
<div class="knowledge-layout">
<aside class="knowledge-sidebar product-card">
<input v-model="knowledgeQuery" placeholder="搜索知识库" />
<button v-for="item in knowledgeResources" :key="item.resource_id" :class="{ active: selectedKnowledge?.resource_id === item.resource_id }" @click="openKnowledgeOperations(item)">
<span><b>{{ item.display_name }}</b><small>{{ item.description || item.slug }}</small></span>
<em>V{{ item.latest_version_number || '—' }}</em>
</button>
<p v-if="!knowledgeResources.length" class="empty-copy">尚无知识库，请先在资源中心创建。</p>
</aside>
<section v-if="selectedKnowledge" class="knowledge-workspace">
<article class="product-card knowledge-summary">
<div><p class="eyebrow">{{ selectedKnowledge.active_index_status || '尚无活跃索引' }}</p><h2>{{ selectedKnowledge.display_name }}</h2><p>{{ selectedKnowledge.description || '未填写用途说明' }}</p></div>
<div class="detail-metrics"><span><b>{{ selectedKnowledge.document_count }}</b>文档</span><span><b>{{ selectedKnowledge.chunk_count }}</b>分块</span><span><b>V{{ selectedKnowledge.active_index_version || '—' }}</b>活跃索引</span></div>
</article>
<div class="knowledge-action-grid">
<article class="product-card"><h3>1. 上传文档</h3><p>仅接受 PDF、DOCX；点击后在弹窗中选择文件，由后端校验并写入 MinIO。</p><button class="button primary" :disabled="knowledgeBusy" @click="knowledgeUploadOpen = true">上传文档</button></article>
<article class="product-card"><h3>2. 构建索引</h3><p>从已上传文档构建新的不可变 Index Version，成功后原子激活。</p><button class="button primary" :disabled="knowledgeBusy || !knowledgeDocuments.length" @click="buildKnowledgeIndex">开始 Ingest / 构建索引</button></article>
<article class="product-card"><h3>3. 检索测试</h3><p>验证当前活跃索引的召回片段和相似度。</p><textarea v-model="knowledgeRetrievalQuery" rows="3" placeholder="输入要检索的业务问题" /><button class="button primary" :disabled="knowledgeBusy || !knowledgeRetrievalQuery.trim()" @click="runKnowledgeRetrievalTest">执行检索</button></article>
</div>
<div v-if="knowledgeUploadOpen" class="modal-backdrop" @click.self="knowledgeUploadOpen = false">
<section class="compact-modal" role="dialog" aria-modal="true" aria-label="上传知识文档">
<header><div><p class="eyebrow">UPLOAD DOCUMENT</p><h2>上传知识文档</h2><p>文件将由服务端校验类型并保存到 MinIO，不会让浏览器直接访问对象存储。</p></div><button class="icon-button" aria-label="关闭" @click="knowledgeUploadOpen = false">×</button></header>
<div class="compact-modal-body"><label>选择 PDF 或 DOCX<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="chooseKnowledgeFile" /></label><p v-if="knowledgeFile" class="field-hint">已选：{{ knowledgeFile.name }}</p><p v-else class="field-hint">单个文件将在登记后显示在当前知识库文档列表中。</p></div>
<footer><button class="button ghost" :disabled="knowledgeBusy" @click="knowledgeUploadOpen = false">取消</button><button class="button primary" :disabled="knowledgeBusy || !knowledgeFile" @click="uploadKnowledgeFile">{{ knowledgeBusy ? '上传中…' : '上传并登记' }}</button></footer>
</section>
</div>
<article class="product-card knowledge-table"><div class="section-heading"><div><h2>文档</h2><p>查看解析和安全校验状态。</p></div></div><table><thead><tr><th>文件名</th><th>状态</th><th>上传时间</th></tr></thead><tbody><tr v-for="item in knowledgeDocuments" :key="item.document_id"><td>{{ item.filename }}</td><td><span class="status-pill">{{ item.status }}</span></td><td>{{ shortTime(item.created_at) }}</td></tr></tbody></table><p v-if="!knowledgeDocuments.length" class="empty-copy">暂无文档。</p></article>
<div class="knowledge-bottom-grid">
<article class="product-card"><h2>Ingest 任务</h2><div v-for="job in knowledgeJobs" :key="job.job_id" class="reference-item"><b>{{ job.status }}</b><small>{{ shortTime(job.created_at) }} · {{ job.error_code || '无错误' }}</small></div><p v-if="!knowledgeJobs.length" class="empty-copy">尚无构建任务。</p></article>
<article class="product-card"><h2>索引版本</h2><div v-for="index in knowledgeIndexes" :key="index.index_version_id" class="reference-item"><b>Index V{{ index.version_number }}</b><small>{{ index.status }} · {{ index.embedding_model }} · {{ shortTime(index.created_at) }}</small></div><p v-if="!knowledgeIndexes.length" class="empty-copy">尚无索引版本。</p></article>
</div>
<article v-if="knowledgeRetrievalHits.length" class="product-card"><h2>检索命中</h2><div v-for="hit in knowledgeRetrievalHits" :key="`${hit.document_id}-${hit.chunk_number}`" class="retrieval-hit"><b>Chunk {{ hit.chunk_number }} · Score {{ hit.score.toFixed(4) }}</b><p>{{ hit.content }}</p></div></article>
</section>
<div v-else class="empty-panel">从左侧选择一个知识库开始运营。</div>
</div>
</section>

      <section v-else-if="space === 'console' && consoleView === 'agents'" class="page-content">
<div class="page-heading">
<div>
<p class="eyebrow">AGENT MANAGEMENT</p>
<h1>智能体管理</h1>
<p>按 Deployment 管理当前能力组合、Revision 和发布流程。</p>
</div>
</div>
<div class="filter-bar product-card">
<input v-model="agentQuery" placeholder="搜索智能体或部署名称" />
<select v-model="agentActive">
<option value="ALL">全部状态</option>
<option value="true">已启用</option>
<option value="false">未启用</option>
</select>
</div>
<section class="agent-create-action"><button class="button primary" @click="openAgentCreator">＋ 新增智能体</button></section>
<div v-if="agentCreatorOpen" class="modal-backdrop" @click.self="agentCreatorOpen = false">
<section class="resource-composer agent-creator agent-create-modal" role="dialog" aria-modal="true" aria-label="新增智能体">
<header><div><p class="eyebrow">CREATE AGENT</p><h2>新增智能体</h2><p>先建立智能体和生产部署，再进入组装工作台选择模型、技能、工具、知识库和记忆。</p></div><button class="icon-button" aria-label="关闭" @click="agentCreatorOpen = false">×</button></header>
<div class="resource-form">
<label>智能体名称<input v-model="agentCreateForm.displayName" maxlength="128" placeholder="例如：员工制度助手" /></label>
<label>部署名称<input v-model="agentCreateForm.deploymentName" maxlength="64" placeholder="例如：员工制度助手-生产" /></label>
<label class="wide-field">用途说明<textarea v-model="agentCreateForm.description" rows="3" maxlength="1000" placeholder="说明它面向谁、解决什么问题；后续可在配置工作台选择资源并发布。" /></label>
</div>
<footer><button class="button ghost" @click="agentCreatorOpen = false">取消</button><button class="button primary" :disabled="agentCreating" @click="createAgentFromForm">{{ agentCreating ? '创建中…' : '创建并进入配置' }}</button></footer>
</section>
</div>
<div class="table-card product-card">
<table>
<thead>
<tr>
<th>智能体</th>
<th>Deployment</th>
<th>当前能力</th>
<th>Revision</th>
<th>最近运行</th>
<th>
</th>
</tr>
</thead>
<tbody>
<tr v-for="item in agents" :key="item.deployment_id">
<td>
<b>{{ item.display_name }}</b>
<small>{{ item.description || '—' }}</small>
</td>
<td>{{ item.deployment_name }}</td>
<td>
<div class="tag-list compact">
<span v-for="(count, type) in item.capability_counts" :key="type">{{ count }} {{ typeLabel(type) }}</span>
</div>
</td>
<td>V{{ item.revision_number || '—' }}</td>
<td>{{ shortTime(item.last_run_at) }}</td>
<td class="row-actions">
<button class="text-link" @click="openAgent(item, true)">配置</button>
<button class="text-link danger" @click="deleteAgent(item)">删除</button>
</td>
</tr>
</tbody>
</table>
</div>
        <section v-if="selectedAgent && agentDetail && draft" class="builder product-card">
<header class="builder-header">
<div>
<button class="text-link" @click="selectedAgent = null; agentDetail = null; draft = null">‹ 返回列表</button>
<p class="eyebrow">CONFIGURE AGENT</p>
<h2>{{ selectedAgent.display_name }}</h2>
<p>基于 Revision {{ agentDetail.agent_version_number }} 创建配置草稿；发布后生成不可变新版本。</p>
</div>
<div>
<button class="button ghost" :disabled="builderSaving" @click="saveDraft">{{ builderSaving ? '保存中…' : '保存草稿' }}</button>
<button class="button primary" @click="preflight">预检并发布</button>
</div>
</header>
<section class="agent-publication-policy">
<div><p class="eyebrow">AVAILABILITY</p><h3>可用范围与运行授权</h3><p>选择谁可以看到、创建会话并运行此智能体。发布新 Revision 时范围立即生效。</p></div>
<label>可运行范围<select v-model="agentPublicationScope"><option value="PERSONAL">仅发布人</option><option value="OWNER_DEPT">指定一个部门</option><option value="SELECTED_SUBJECTS">指定用户 / 角色 / 部门</option></select></label>
<label v-if="agentPublicationScope === 'OWNER_DEPT'">可运行部门<select v-model="agentPublicationSubjects"><option value="">请选择 RuoYi 部门</option><option v-for="item in iamDepartments" :key="item.external_id" :value="difySubjectValue('DEPT', item.external_id)">{{ item.display_name }}</option></select></label>
<label v-else-if="agentPublicationScope === 'SELECTED_SUBJECTS'">指定范围<select multiple v-model="agentPublicationSubjects"><option v-for="item in difyPublicationOptions()" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
</section>
<AgentModuleBoard :catalog="catalog" :specification="draft.specification" :validation="validation" :publishing="builderPublishing" @single="setSingle" @many="toggleDraftCapability" @preflight="preflight" @publish="publishDraft" />
<div class="stepper">
<button v-for="item in [{n:1,t:'基础信息'},{n:2,t:'模型与提示词'},{n:3,t:'技能与工具'},{n:4,t:'知识与记忆'},{n:5,t:'预检发布'}]" :key="item.n" :class="{ active: builderStep === item.n, done: builderStep > item.n }" @click="builderStep = item.n">
<span>{{ item.n }}</span>{{ item.t }}</button>
</div>
<div class="builder-layout">
<section class="builder-form">
<template v-if="builderStep === 1">
<h3>当前配置说明</h3>
<p>Agent 名称和 Deployment 元数据保持稳定；本次调整只会创建新的 Agent Version 与 Revision。</p>
<div class="info-box">
<b>当前部署</b>
<span>{{ selectedAgent.deployment_name }}</span>
<b>基础 Revision</b>
<span>{{ draft.base_revision_id?.slice(0, 8) }}</span>
<b>草稿状态</b>
<span>版本 {{ draft.lock_version }} · {{ shortTime(draft.updated_at) }}</span>
</div>
<div class="info-box publication-box">
<b>发布运行范围</b>
<select v-model="agentPublicationScope">
<option value="PERSONAL">仅发布人（个人试用）</option>
<option value="OWNER_DEPT">指定一个部门</option>
<option value="SELECTED_SUBJECTS">指定部门、角色或用户</option>
</select>
<template v-if="agentPublicationScope === 'OWNER_DEPT'">
<b>可运行部门</b>
<select v-model="agentPublicationSubjects">
<option value="">请选择 RuoYi 部门</option>
<option v-for="item in iamDepartments" :key="item.external_id" :value="difySubjectValue('DEPT', item.external_id)">{{ item.display_name }}</option>
</select>
</template>
<template v-else-if="agentPublicationScope === 'SELECTED_SUBJECTS'">
<b>可运行范围</b>
<select multiple v-model="agentPublicationSubjects">
<option v-for="item in difyPublicationOptions()" :key="item.value" :value="item.value">{{ item.label }}</option>
</select>
<small>可多选部门、角色和用户；范围外成员不能创建会话或运行此智能体。</small>
</template>
</div>
</template>
<template v-else-if="builderStep === 2">
<h3>模型与提示词</h3>
<label>对话模型<select :value="selectedValue('model_version_id')" @change="setSingle('model_version_id', ($event.target as HTMLSelectElement).value)">
<option value="">请选择模型</option>
<option v-for="item in catalogFor('MODEL')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
<label>系统提示词<select :value="selectedValue('prompt_version_id')" @change="setSingle('prompt_version_id', ($event.target as HTMLSelectElement).value)">
<option value="">不使用提示词</option>
<option v-for="item in catalogFor('PROMPT')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
</template>
<template v-else-if="builderStep === 3">
<h3>Skills 与 Tools</h3>
<label>已发布技能<select multiple :value="selectedValues('skill_version_ids')" @change="setMany('skill_version_ids', $event)">
<option v-for="item in catalogFor('SKILL')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
<label>直接工具（含 Dify Flow）<select multiple :value="selectedValues('tool_version_ids')" @change="setMany('tool_version_ids', $event)">
<option v-for="item in catalogFor('TOOL')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
<label>MCP 连接<select multiple :value="selectedValues('mcp_connection_version_ids')" @change="setMany('mcp_connection_version_ids', $event)">
<option v-for="item in catalogFor('MCP_CONNECTION')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
</template>
<template v-else-if="builderStep === 4">
<h3>知识与长期记忆</h3>
<label>知识库<select multiple :value="selectedValues('knowledge_version_ids')" @change="setMany('knowledge_version_ids', $event)">
<option v-for="item in catalogFor('KNOWLEDGE')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
<label>Memory Policy<select :value="selectedValue('memory_policy_version_id')" @change="setSingle('memory_policy_version_id', ($event.target as HTMLSelectElement).value)">
<option value="">不启用长期记忆</option>
<option v-for="item in catalogFor('MEMORY_POLICY')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
</template>
<template v-else>
<h3>发布预检</h3>
<div v-if="!validation" class="empty-copy">点击“预检并发布”校验资源授权、依赖、模型与知识索引。</div>
<div v-else>
<div :class="['validation-result', validation.valid ? 'ok' : 'blocked']">
<b>{{ validation.valid ? '预检通过' : '存在阻断问题' }}</b>
<p v-for="issue in validation.blocking_errors" :key="issue.code">{{ issue.message }}</p>
<p v-for="issue in validation.warnings" :key="issue.code">{{ issue.message }}</p>
</div>
<div class="change-grid">
<div>
<b>新增能力</b>
<p>{{ validation.changes.added.join('、') || '无' }}</p>
</div>
<div>
<b>移除能力</b>
<p>{{ validation.changes.removed.join('、') || '无' }}</p>
</div>
</div>
<button class="button primary" :disabled="!validation.valid || builderPublishing" @click="publishDraft">{{ builderPublishing ? '发布中…' : '确认发布并激活新 Revision' }}</button>
</div>
</template>
<details class="advanced-json">
<summary @click="showAdvancedJson = !showAdvancedJson">高级 JSON 配置</summary>
<textarea v-model="draftJson" rows="14" />
<button class="button ghost" @click="applyAdvancedJson">应用 JSON</button>
</details>
</section>
<aside class="assembly-summary">
<h3>当前组装</h3>
<p>已选资源会在发布前进行递归授权与依赖校验。</p>
<section v-for="(items, type) in draftCapabilityGroups" :key="type">
<b>{{ typeLabel(type) }} · {{ items.length }}</b>
<span v-for="item in items" :key="item.version_id">{{ item.display_name }} <small>V{{ item.version_number }}</small>
</span>
</section>
<p v-if="!Object.keys(draftCapabilityGroups).length" class="empty-copy">尚未选择能力。</p>
</aside>
</div>
</section>
      </section>

      <section v-else-if="space === 'console'" class="page-content">
<div class="page-heading">
<div>
<p class="eyebrow">{{ consoleView.toUpperCase() }}</p>
<h1>{{ consoleTitle(consoleView) }}</h1>
<p>该模块将在下一轮接入列表、详情和批量治理操作；现有业务能力保持可用。</p>
</div>
</div>
<div class="empty-panel">请从资源中心或智能体管理进入当前已产品化的详情与配置流程。</div>
</section>
    </section>

    <aside v-if="selectedResource" class="detail-drawer">
<header>
<div>
<p class="eyebrow">{{ typeLabel(selectedResource.resource.resource_type) }} · {{ selectedResource.source }}</p>
<h2>{{ selectedResource.resource.display_name }}</h2>
<p>{{ selectedResource.resource.description || selectedResource.resource.slug }}</p>
</div>
<button class="icon-button" @click="selectedResource = null; selectedKnowledge = null">×</button>
</header>
<div class="drawer-body">
<section class="detail-metrics">
<span>
<b>{{ selectedResource.resource.published_version_count }}</b> 发布版本</span>
<span>
<b>{{ selectedResource.resource.referenced_by_count }}</b> Agent 引用</span>
<span>
<b>{{ selectedResource.grants_count }}</b> 授权规则</span>
</section>
<section class="metadata-list">
<h3>来源与说明</h3>
<div class="resource-semantics" v-if="selectedResource.one_line_summary">
<strong>{{ selectedResource.one_line_summary }}</strong>
<dl><dt>何时使用</dt><dd>{{ selectedResource.when_to_use }}</dd><dt>何时不使用</dt><dd>{{ selectedResource.when_not_to_use || '无额外限制' }}</dd><dt>输入</dt><dd>{{ selectedResource.input_summary }}</dd><dt>输出</dt><dd>{{ selectedResource.output_summary }}</dd><dt>风险</dt><dd>{{ selectedResource.risk_level }} · {{ selectedResource.read_only ? '只读' : '可写' }}</dd></dl>
</div>
<p>
<b>来源：</b>{{ selectedResource.source }}</p>
<p>
<b>负责人：</b>{{ selectedResource.resource.owner_user_id || selectedResource.created_by || '历史导入' }}</p>
<p v-if="selectedResource.resource.owner_dept_id">
<b>责任部门：</b>{{ selectedResource.resource.owner_dept_id }}</p>
<p>
<b>创建时间：</b>{{ shortTime(selectedResource.created_at) }}</p>
<p>
<b>资源标识：</b>{{ selectedResource.resource.slug }}</p>
<p v-if="selectedResource.usage_guidance">
<b>使用说明：</b>{{ selectedResource.usage_guidance }}</p>
<div class="tag-list compact">
<span v-for="tag in selectedResource.resource.tags" :key="tag">{{ tag }}</span>
</div>
<button class="button ghost" @click="descriptorEditing = !descriptorEditing">{{ descriptorEditing ? '取消编辑' : '编辑资源信息' }}</button>
<div v-if="descriptorEditing" class="resource-form">
<label>负责人<select v-model="descriptorForm.owner_user_id"><option :value="principal?.external_user_id">{{ principal?.display_name }}（当前用户）</option><option v-for="item in iamUsers" :key="item.external_id" :value="item.external_id">{{ item.display_name }} · {{ item.external_id }}</option></select>
</label>
<label>责任部门<select v-model="descriptorForm.owner_dept_id"><option value="">不指定</option><option v-for="item in iamDepartments" :key="item.external_id" :value="item.external_id">{{ item.display_name }}</option></select>
</label>
<label>来源<select v-model="descriptorForm.source_type">
<option value="PLATFORM_NATIVE">平台原生</option>
<option value="OPENAI_COMPATIBLE">OpenAI Compatible</option>
<option value="MCP">MCP</option>
<option value="DIFY">Dify</option>
<option value="IMPORT">历史导入</option>
</select>
</label>
<label>标签<input v-model="descriptorForm.tags" placeholder="用逗号分隔" />
</label>
<label class="wide-field">一句话能力<input v-model="descriptorForm.one_line_summary" /></label>
<label>何时使用<textarea v-model="descriptorForm.when_to_use" rows="3" /></label>
<label>何时不使用<textarea v-model="descriptorForm.when_not_to_use" rows="3" /></label>
<label>输入说明<textarea v-model="descriptorForm.input_summary" rows="3" /></label>
<label>输出说明<textarea v-model="descriptorForm.output_summary" rows="3" /></label>
<label>风险等级<select v-model="descriptorForm.risk_level"><option value="LOW">低</option><option value="MEDIUM">中</option><option value="HIGH">高</option></select></label>
<label class="check-label"><input v-model="descriptorForm.read_only" type="checkbox" />只读资源</label>
<label class="wide-field">使用说明<textarea v-model="descriptorForm.usage_guidance" rows="3" />
</label>
<button class="button primary" :disabled="resourceSaving" @click="saveDescriptor">保存资源信息</button>
</div>
</section>
<section v-if="selectedResource.resource.source_type === 'DIFY'" class="dify-detail-section">
<h3>Dify 应用信息</h3>
<div class="dify-detail-grid">
<span><small>应用类型</small><b>{{ selectedResource.safe_config.flow_type || '—' }}</b></span>
<span><small>Tool Name</small><b>{{ selectedResource.safe_config.tool_name || '—' }}</b></span>
<span><small>业务线</small><b>{{ (selectedResource.safe_config.application_profile as Record<string, unknown>)?.business_line || '—' }}</b></span>
<span><small>可用范围</small><b>{{ (selectedResource.safe_config.application_profile as Record<string, unknown>)?.publication_scope || '—' }}</b></span>
</div>
<p><b>使用对象：</b>{{ (selectedResource.safe_config.application_profile as Record<string, unknown>)?.audience || '未填写' }}</p>
<p><b>使用场景：</b>{{ (selectedResource.safe_config.application_profile as Record<string, unknown>)?.usage_scenarios || '未填写' }}</p>
<p><b>涉及数据：</b>{{ (selectedResource.safe_config.application_profile as Record<string, unknown>)?.data_involved || '未填写' }}</p>
<div class="dify-input-contract">
<b>发现到的 Dify 输入</b>
<pre>{{ JSON.stringify(selectedResource.safe_config.dify_input_form || [], null, 2) }}</pre>
</div>
<p class="dify-security-note">API Key 已保存在平台 Vault，详情和 API 响应均不返回密钥值或 secret_ref。</p>
</section>
<section v-if="selectedKnowledge">
<h3>知识库内容</h3>
<div class="detail-metrics">
<span>
<b>{{ selectedKnowledge.document_count }}</b> 文档</span>
<span>
<b>{{ selectedKnowledge.chunk_count }}</b> 分块</span>
<span>
<b>V{{ selectedKnowledge.active_index_version || '—' }}</b> 活跃索引</span>
</div>
<p class="empty-copy">Embedding：{{ selectedKnowledge.embedding_model || '尚未构建索引' }}</p>
<article v-for="doc in selectedKnowledge.documents" :key="doc.document_id" class="document-card">
<div>
<b>{{ doc.filename }}</b>
<span>{{ doc.status }} · {{ doc.chunk_count }} chunks</span>
</div>
<p>{{ doc.preview || '文档尚未完成解析或索引。' }}</p>
</article>
<article v-for="index in selectedKnowledge.indexes" :key="index.version_number" class="reference-item">
<b>索引 V{{ index.version_number }}</b>
<small>{{ index.status }} · {{ index.embedding_model }} · {{ shortTime(index.created_at) }}</small>
</article>
</section>
<section>
<h3>版本</h3>
<article v-for="version in selectedResource.versions" :key="version.version_id" class="version-card">
<div>
<b>V{{ version.version_number }}</b>
<span class="status-pill success">{{ statusLabel(version.status) }}</span>
</div>
<p>{{ version.summary }}</p>
<small>{{ version.content_hash.slice(0, 12) }}</small>
</article>
</section>
<section v-if="selectedResource.dependency_graph.length">
<h3>版本依赖</h3>
<article v-for="node in selectedResource.dependency_graph" :key="node.version_id" class="reference-item">
<b>{{ node.display_name }}</b>
<small>{{ node.resource_type }} · {{ node.dependencies.length ? `依赖 ${node.dependencies.length} 项资源` : '无直接依赖' }}</small>
<div v-if="node.dependencies.length" class="dependency-list">
<span v-for="dependency in node.dependencies" :key="dependency.version_id">
{{ dependency.display_name }} · {{ typeLabel(dependency.resource_type) }} · V{{ dependency.version_number || '—' }}
</span>
</div>
</article>
</section>
<section>
<h3>授权与有效权限</h3>
<p v-if="!selectedResource.effective_permissions.length" class="empty-copy">当前用户没有额外授权规则。</p>
<article v-for="permission in selectedResource.effective_permissions" :key="`${permission.origin}-${permission.subject_id || ''}-${permission.actions.join('-')}`" class="reference-item">
<b>{{ permission.origin }} · {{ permission.effect }}</b>
<small>{{ permission.subject_id || '当前资源' }} · {{ permission.actions.join(' / ') }}</small>
</article>
</section>
<section>
<h3>引用关系</h3>
<p v-if="!selectedResource.references.length" class="empty-copy">当前未被 Agent Version 引用。</p>
<article v-for="item in selectedResource.references" :key="`${item.agent_id}-${item.version_number}`" class="reference-item">
<b>{{ item.display_name }}</b>
<small>{{ item.kind }} · V{{ item.version_number }}</small>
</article>
</section>
<section>
<h3>安全配置摘要</h3>
<pre>{{ JSON.stringify(selectedResource.safe_config, null, 2) }}</pre>
</section>
<footer class="drawer-footer">
<button class="button danger" @click="deleteResource">删除此资源</button>
</footer>
</div>
</aside>
    <div v-if="selectedResource" class="drawer-backdrop" @click="selectedResource = null" />
    <p v-if="error" class="toast error">{{ error }}</p>
  </main>
</template>
