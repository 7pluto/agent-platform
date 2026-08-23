export interface Principal {
  provider: string
  external_user_id: string
  external_org_id: string
  tenant_id: string
  display_name: string
  role_codes: string[]
  dept_ids: string[]
}
export interface IamSubject { type: 'USER' | 'ROLE' | 'DEPT'; external_id: string; display_name: string; parent_id?: string }
export interface IamSubjectPage { items: IamSubject[]; next_cursor?: string }

export interface SessionResponse {
  principal: Principal
  csrf_token: string
}

export interface AuthModeResponse {
  mode: 'ticket' | 'password'
}

export interface RuoYiCaptcha {
  image: string
  uuid: string
}

export interface ExecutionManifest {
  schema_version: string
  tenant_id: string
  run_id: string
  thread_id: string
  deployment_id: string
  deployment_revision_id?: string
  manifest_hash: string
  harness: { type: string; version: string }
  resource_versions: Record<string, string>
  resources: Array<{ type: string; resource_id: string; version_id: string; content_hash: string }>
}

export interface RunRecord {
  run_id: string
  tenant_id: string
  user_id: string
  deployment_id: string
  thread_id: string
  message: string
  status: string
  created_at: string
  execution_manifest?: ExecutionManifest
}
export interface ConversationRecord { conversation_id: string; deployment_id?: string; title?: string; created_at: string; updated_at: string }
export interface ThreadRecord { thread_id: string; conversation_id: string; title?: string; created_at: string }
export interface ConversationSession { conversation: ConversationRecord; thread: ThreadRecord }
export interface ConversationMessage { message_id: string; thread_id: string; role: 'USER' | 'ASSISTANT' | 'SYSTEM'; content: string; source_run_id?: string; created_at: string }
export interface RunEvent {
  sequence: number
  event: string
  occurred_at: string
  data: Record<string, unknown>
}
export interface RunDetail {
  run: RunRecord
  manifest: ExecutionManifest
  events: RunEvent[]
}
export interface RunObservabilitySummary {
  sampled_runs: number
  status_counts: Record<string, number>
  terminal_runs: number
  completion_rate?: number | null
  average_duration_ms?: number | null
  tool_calls: number
  rag_retrievals: number
  denied_capability_calls: number
  failed_runs: number
  generated_at: string
}
export interface MemoryItem {
  memory_id: string
  deployment_id: string
  category: string
  content: string
  expires_at?: string
  created_at: string
  source_run_id?: string
}
export interface KnowledgeDocument {
  document_id: string
  knowledge_resource_version_id: string
  filename: string
  status: string
  created_at: string
}
export interface KnowledgeIndex {
  index_version_id: string
  version_number: number
  status: string
  embedding_model: string
  created_at: string
}
export interface IngestJob {
  job_id: string
  status: string
  error_code?: string
  created_at: string
  completed_at?: string
}

export interface AgentDefinition {
  agent_id: string
  tenant_id: string
  slug: string
  display_name: string
  description?: string
  draft_spec: Record<string, unknown>
}

export interface AgentVersion {
  agent_version_id: string
  agent_id: string
  version_number: number
  status: string
}

export interface Deployment {
  deployment_id: string
  agent_id: string
  name: string
  active_revision_id?: string
}

export interface DeploymentRevision {
  deployment_revision_id: string
  deployment_id: string
  agent_version_id: string
  revision_number: number
}


export interface ModelDefinition {
  model_id: string
  tenant_id: string
  slug: string
  display_name: string
  provider: 'openai-compatible'
  config: { base_url: string; model: string; secret_ref: string; model_mode?: 'CHAT' | 'EMBEDDING' }
}

export interface ModelVersion {
  model_version_id: string
  model_id: string
  version_number: number
  status: 'DRAFT' | 'PUBLISHED'
  provider: 'openai-compatible'
  config: { base_url: string; model: string; secret_ref: string; model_mode?: 'CHAT' | 'EMBEDDING' }
  availability: 'UNKNOWN' | 'AVAILABLE' | 'UNAVAILABLE'
  last_tested_at?: string
  last_test_error?: string
}

export interface ResourceGrant {
  grant_id: string
  tenant_id: string
  subject_type: 'USER' | 'ROLE' | 'DEPT'
  subject_id: string
  resource_type: string
  resource_id: string
  actions: string[]
  effect: 'ALLOW' | 'DENY'
  created_by: string
  created_at: string
}

export type RegistryResourceType = 'PROMPT' | 'SKILL' | 'TOOL' | 'MCP_SERVER' | 'MCP_CONNECTION' | 'KNOWLEDGE_CONNECTION' | 'KNOWLEDGE' | 'MEMORY_POLICY'
export interface RegistryResource {
  resource_id: string
  tenant_id: string
  resource_type: RegistryResourceType
  slug: string
  display_name: string
  description?: string
  draft_config: Record<string, unknown>
}
export interface RegistryResourceVersion {
  resource_version_id: string
  resource_id: string
  resource_type: RegistryResourceType
  version_number: number
  status: 'DRAFT' | 'PUBLISHED' | 'DEPRECATED'
  config: Record<string, unknown>
  content_hash: string
}
export interface DifyApplicationPublishResponse {
  resource_version: RegistryResourceVersion
  connection_test: {
    available: boolean; flow_type: string; input_form: Array<Record<string, unknown>>
    invocation_tested: boolean; has_retrieval: boolean; opening_statement?: string; suggested_questions: string[]
  }
  grants_created: number
}
export interface CatalogItem {
  version_id: string
  resource_id: string
  resource_type: string
  display_name: string
  description?: string
  version_number: number
  status: string
  content_hash: string
  summary: string
  dependencies: string[]
  owner_user_id?: string
  owner_dept_id?: string
  source_type: string
  usage_guidance?: string
  tags: string[]
  lifecycle_status: string
  health: string
  one_line_summary?: string; when_to_use?: string; when_not_to_use?: string
  input_summary?: string; output_summary?: string; risk_level: string; read_only: boolean
}
export interface DeploymentCapabilities {
  deployment_id: string
  agent_id: string
  agent_version_id: string
  agent_version_number: number
  active_revision_id: string
  editable: boolean
  specification?: Record<string, unknown>
  capabilities: CatalogItem[]
  publication_scope: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'
  publication_subjects: Array<{ subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string }>
}
export interface PageMeta { total: number; page: number; page_size: number }
export interface ResourceListItem {
  resource_id: string; resource_type: string; slug: string; display_name: string; description?: string
  latest_version_number?: number; latest_status?: string; published_version_count: number
  referenced_by_count: number; updated_at?: string; owner_user_id?: string; owner_dept_id?: string
  source_type: string; lifecycle_status: string; tags: string[]
}
export interface ResourceListPage { items: ResourceListItem[]; meta: PageMeta }
export interface ResourceDetail {
  resource: ResourceListItem; versions: CatalogItem[]; grants_count: number
  references: Array<{ kind: string; display_name: string; version_number?: number; agent_id?: string }>
  safe_config: Record<string, unknown>; source: string; created_by?: string; created_at?: string; usage_guidance?: string
  one_line_summary?: string; when_to_use?: string; when_not_to_use?: string
  input_summary?: string; output_summary?: string; risk_level: string; read_only: boolean
  dependency_graph: Array<{
    version_id: string; display_name: string; resource_type: string
    dependencies: Array<{ version_id: string; display_name: string; resource_type: string; version_number?: number }>
  }>
  effective_permissions: Array<{ origin: string; effect: string; subject_id?: string; actions: string[] }>
}
export interface DiscoverySnapshot {
  snapshot_id: string
  resource_version_id: string
  provider: string
  external_type: string
  external_id: string
  schema_hash: string
  snapshot: Record<string, unknown>
  created_at: string
}
export interface DriftReport {
  resource_version_id: string
  provider: string
  status: 'NO_CHANGE' | 'CHANGED' | 'MISSING' | 'UNAVAILABLE'
  published_schema_hash: string
  current_schema_hash?: string
  message?: string
  current_snapshot?: Record<string, unknown>
  draft_version_id?: string
  checked_at: string
}
export interface KnowledgeOverview {
  resource_id: string; resource_version_id: string; display_name: string; description?: string
  provider: 'LOCAL' | 'RAGFLOW' | 'REMOTE_HTTP' | string; provider_display_name: string
  source_summary?: string; connection_display_name?: string; supported_operations: string[]
  active_index_version?: number; active_index_status?: string; embedding_model?: string
  document_count: number; chunk_count: number
  documents: Array<{ document_id: string; filename: string; status: string; created_at?: string; chunk_count: number; preview?: string }>
  indexes: Array<{ version_number: number; status: string; embedding_model: string; created_at?: string; chunk_strategy: Record<string, unknown> }>
}
export interface AgentWorkbenchItem {
  deployment_id: string; agent_id: string; display_name: string; description?: string; deployment_name: string
  active: boolean; revision_number?: number; capability_counts: Record<string, number>; last_run_at?: string
}
export interface AgentWorkbenchPage { items: AgentWorkbenchItem[]; meta: PageMeta }
export interface ConfigurationDraft {
  draft_id: string; deployment_id: string; base_revision_id?: string; specification: Record<string, unknown>
  lock_version: number; updated_by: string; updated_at?: string
}
export interface ConfigurationValidation {
  valid: boolean; blocking_errors: Array<{ code: string; message: string }>
  warnings: Array<{ code: string; message: string }>; capabilities: CatalogItem[]
  resolved_capabilities: Array<{ version_id: string; display_name: string; resource_type: string; origin: string; dependency_path: string[] }>
  changes: { added: string[]; removed: string[]; unchanged: string[] }
}
export interface RevisionDetail {
  revision_id: string; revision_number: number; agent_version_id: string; agent_version_number: number
  created_at?: string; capabilities: CatalogItem[]
}

let activeCsrfToken = ''

async function send(path: string, init: RequestInit): Promise<{ response: Response; payload: Record<string, unknown> }> {
  const headers = new Headers(init.headers || {})
  headers.set('Content-Type', 'application/json')
  if (activeCsrfToken && headers.has('X-CSRF-Token'))
    headers.set('X-CSRF-Token', activeCsrfToken)
  const response = await fetch(path, { credentials: 'same-origin', ...init, headers })
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>
  return { response, payload }
}

function apiErrorMessage(payload: Record<string, unknown>, status: number): string {
  if (typeof payload.message === 'string') return payload.message
  if (typeof payload.code === 'string') return payload.code
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail.map((item) => {
      if (!item || typeof item !== 'object') return String(item)
      const value = item as { loc?: unknown[]; msg?: string }
      const field = (value.loc || []).filter(part => part !== 'body').join('.')
      return `${field || '请求参数'}：${value.msg || '格式不正确'}`
    })
    return messages.join('；')
  }
  if (typeof payload.detail === 'string') return payload.detail
  return `HTTP ${status}`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let result = await send(path, init)
  if (!result.response.ok && result.payload.code === 'CSRF_INVALID' && path !== '/api/v1/auth/session') {
    const refreshed = await send('/api/v1/auth/session', {})
    if (refreshed.response.ok && typeof refreshed.payload.csrf_token === 'string') {
      activeCsrfToken = refreshed.payload.csrf_token
      result = await send(path, init)
    }
  }
  if (!result.response.ok)
    throw new Error(apiErrorMessage(result.payload, result.response.status))
  if (typeof result.payload.csrf_token === 'string')
    activeCsrfToken = result.payload.csrf_token
  return result.payload as T
}
async function multipartRequest<T>(path: string, body: FormData, csrf: string): Promise<T> {
  const sendMultipart = () => fetch(path, {
    method: 'POST', credentials: 'same-origin', body,
    headers: { 'X-CSRF-Token': activeCsrfToken || csrf },
  })
  let response = await sendMultipart()
  let payload = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok && payload.code === 'CSRF_INVALID') {
    await request<SessionResponse>('/api/v1/auth/session')
    response = await sendMultipart()
    payload = await response.json().catch(() => ({})) as Record<string, unknown>
  }
  if (!response.ok)
    throw new Error(apiErrorMessage(payload, response.status))
  return payload as T
}
function browserRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
    return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}
export const api = {
  session: () => request<SessionResponse>('/api/v1/auth/session'),
  authMode: () => request<AuthModeResponse>('/api/v1/auth/mode'),
  searchIamSubjects: (type: 'USER' | 'ROLE' | 'DEPT', query = '') => request<IamSubjectPage>(`/api/v1/iam/subjects?${new URLSearchParams({ type, query, limit: '100' }).toString()}`),
  ruoyiCaptcha: () => request<RuoYiCaptcha>('/api/v1/auth/ruoyi/captcha'),
  ruoyiLogin: (username: string, password: string, code: string, uuid: string) => request<SessionResponse>('/api/v1/auth/ruoyi/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, code, uuid }),
  }),
  exchange: (ticket_code: string) => request<SessionResponse>('/api/v1/auth/exchange', {
    method: 'POST',
    body: JSON.stringify({ ticket_code }),
  }),
  logout: () => request<{ status: string }>('/api/v1/auth/logout', { method: 'POST' }),
  listAgents: () => request<AgentDefinition[]>('/api/v1/agents'),
  listDeployments: () => request<Deployment[]>('/api/v1/deployments'),
  listModels: () => request<ModelDefinition[]>('/api/v1/models'),
  listModelVersions: (modelId: string) => request<ModelVersion[]>(`/api/v1/models/${modelId}/versions`),
  createModel: (slug: string, displayName: string, config: ModelDefinition['config'], csrf: string) => request<ModelDefinition>('/api/v1/models', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({ slug, display_name: displayName, provider: 'openai-compatible', config }),
  }),
  createModelWithSecret: (payload: { slug: string; display_name: string; base_url: string; model: string; api_key: string; model_mode: 'CHAT' | 'EMBEDDING' }, csrf: string) => request<ModelVersion>('/api/v1/models/with-secret', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload),
  }),
  createModelVersion: (modelId: string, config: ModelDefinition['config'], csrf: string) => request<ModelVersion>(`/api/v1/models/${modelId}/versions`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ config }),
  }),
  testModelVersion: (versionId: string, csrf: string) => request<{ available: boolean; message: string }>(`/api/v1/model-versions/${versionId}/test`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
  }),
  publishModelVersion: (versionId: string, csrf: string) => request<ModelVersion>(`/api/v1/model-versions/${versionId}/publish`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
  }),
  listPublishedResourceVersions: (resourceType?: RegistryResourceType) => request<RegistryResourceVersion[]>(`/api/v1/resource-versions/published${resourceType ? `?resource_type=${resourceType}` : ''}`),
  listResources: (resourceType?: RegistryResourceType) => request<RegistryResource[]>(`/api/v1/resources${resourceType ? `?resource_type=${resourceType}` : ''}`),
  listResourceVersions: (resourceId: string) => request<RegistryResourceVersion[]>(`/api/v1/resources/${resourceId}/versions`),
  createResource: (resourceType: RegistryResourceType, slug: string, displayName: string, description: string, draftConfig: Record<string, unknown>, csrf: string) => request<RegistryResource>('/api/v1/resources', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({ resource_type: resourceType, slug, display_name: displayName, description: description || undefined, draft_config: draftConfig }),
  }),
  createResourceVersion: (resourceId: string, config: Record<string, unknown>, csrf: string) => request<RegistryResourceVersion>(`/api/v1/resources/${resourceId}/versions`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ config }),
  }),
  publishResourceVersion: (resourceVersionId: string, csrf: string) => request<RegistryResourceVersion>(`/api/v1/resource-versions/${resourceVersionId}/publish`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
  }),
  listDiscoverySnapshots: (resourceVersionId: string) => request<DiscoverySnapshot[]>(`/api/v1/resource-versions/${resourceVersionId}/discovery-snapshots`),
  checkResourceDrift: (resourceVersionId: string, csrf: string, createDraft = true) => request<DriftReport>(`/api/v1/resource-versions/${resourceVersionId}/drift-check`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ create_draft: createDraft }),
  }),
  testResourceVersion: (resourceVersionId: string, csrf: string) => request<{ available: boolean; flow_type: string; has_retrieval: boolean }>(`/api/v1/resource-versions/${resourceVersionId}/test`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
  }),
  createDifyFlowTool: (payload: {
    slug: string; display_name: string; description: string; flow_type: 'CHATFLOW' | 'WORKFLOW'; base_url: string
    api_key: string; tool_name: string; timeout_seconds: number; test_query: string
    owner_user_id: string; owner_dept_id?: string; one_line_summary: string; when_to_use: string; when_not_to_use?: string
    input_summary: string; output_summary: string; risk_level: string; read_only: boolean; tags: string[]
    business_line?: string; data_involved?: string; audience?: string; usage_scenarios?: string; developer_user_ids: string[]
    opening_statement?: string; suggested_questions: string[]; publication_scope: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'
    publication_subjects: Array<{ subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string }>
  }, csrf: string) => request<DifyApplicationPublishResponse>('/api/v1/dify-applications', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload),
  }),
  createMcpConnection: (payload: { slug: string; display_name: string; endpoint: string; timeout_seconds: number; api_key: string | null; auth_header: string; auth_scheme: string }, csrf: string) => request<RegistryResourceVersion>('/api/v1/mcp-connections', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload),
  }),
  createRagflowConnection: (payload: { slug: string; display_name: string; endpoint: string; api_key: string; timeout_seconds: number }, csrf: string) => request<RegistryResourceVersion>('/api/v1/ragflow-connections', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload),
  }),
  discoverRagflowDatasets: (resourceVersionId: string, csrf: string) => request<Array<{ id: string; name: string; description?: string }>>(`/api/v1/ragflow-connections/${resourceVersionId}/discover`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
  }),
  registerRagflowKnowledge: (payload: { connection_version_id: string; dataset_id: string; slug: string; display_name: string; description?: string }, csrf: string) => request<RegistryResourceVersion>('/api/v1/ragflow-knowledge/register', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload),
  }),
  createHttpTool: (payload: {
    slug: string; display_name: string; description: string; tool_name: string; endpoint: string; path: string; method: 'GET' | 'POST'
    input_schema: Record<string, unknown>; query_template?: Record<string, unknown> | unknown[]; body_template?: Record<string, unknown> | unknown[]
    timeout_seconds: number; api_key?: string; auth_header: string; auth_scheme: string; test_arguments: Record<string, unknown>
  }, csrf: string) => request<{ resource_version: RegistryResourceVersion; test_result: { status_code: number } }>('/api/v1/http-tools', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload),
  }),
  createResourceGrant: (payload: { subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string; resource_type: string; resource_id: string; actions: string[] }, csrf: string) => request('/api/v1/resource-grants', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ ...payload, effect: 'ALLOW' }),
  }),
  createAgent: (slug: string, displayName: string, csrf: string, description: string, draftSpec: Record<string, unknown>) => request<AgentDefinition>('/api/v1/agents', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({ slug, display_name: displayName, description, draft_spec: draftSpec }),
  }),
  createVersion: (agentId: string, csrf: string) => request<AgentVersion>(`/api/v1/agents/${agentId}/versions`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
    body: '{}',
  }),
  publishVersion: (versionId: string, csrf: string) => request<AgentVersion>(`/api/v1/agent-versions/${versionId}/publish`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
  }),
  createDeployment: (agentId: string, name: string, csrf: string) => request<Deployment>('/api/v1/deployments', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({ agent_id: agentId, name }),
  }),
  createRevision: (deploymentId: string, versionId: string, csrf: string) => request<DeploymentRevision>(
    `/api/v1/deployments/${deploymentId}/revisions`,
    {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf },
      body: JSON.stringify({ agent_version_id: versionId }),
    },
  ),
  activateRevision: (deploymentId: string, revisionId: string, csrf: string) => request<Deployment>(
    `/api/v1/deployments/${deploymentId}/revisions/${revisionId}/activate`,
    { method: 'POST', headers: { 'X-CSRF-Token': csrf } },
  ),
  createRun: (deployment_id: string, message: string, conversation_id: string, thread_id: string, csrf: string) => request<RunRecord>(
    `/api/v1/deployments/${deployment_id}/runs`,
    {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': browserRequestId() },
      body: JSON.stringify({ deployment_id, message, conversation_id, thread_id }),
    },
  ),
  listRuns: () => request<RunRecord[]>('/api/v1/runs'),
  runObservability: () => request<RunObservabilitySummary>('/api/v1/observability/runs/summary'),
  runDetail: (runId: string) => request<RunDetail>(`/api/v1/runs/${runId}/detail`),
  events: async (runId: string, csrf: string, onEvent?: (event: RunEvent) => void) => {
    const response = await fetch(`/api/v1/runs/${runId}/events?follow=true`, {
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrf },
    })
    if (!response.ok)
      throw new Error(`Event stream failed: ${response.status}`)
    if (!response.body) return []
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    const events: RunEvent[] = []
    const consume = (block: string) => {
      const lines = block.split(/\r?\n/)
      const eventName = lines.find(line => line.startsWith('event: '))?.slice(7) || ''
      const dataLine = lines.find(line => line.startsWith('data: '))
      if (!dataLine || !eventName || eventName === 'heartbeat') return
      try {
        const payload = JSON.parse(dataLine.slice(6)) as RunEvent
        const event: RunEvent = { ...payload, event: payload.event || eventName }
        events.push(event)
        onEvent?.(event)
      } catch { /* Ignore an incomplete/unknown SSE frame. */ }
    }
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() || ''
      blocks.forEach(consume)
      if (done) break
    }
    if (buffer.trim()) consume(buffer)
    return events
  },
  listResourceGrants: (csrf: string, resourceId?: string) => request<ResourceGrant[]>(
    `/api/v1/resource-grants${resourceId ? `?resource_id=${encodeURIComponent(resourceId)}` : ''}`,
    { headers: { 'X-CSRF-Token': csrf } },
  ),
  createRunGrant: (subjectType: ResourceGrant['subject_type'], subjectId: string, deploymentId: string, csrf: string) => request<ResourceGrant>('/api/v1/resource-grants', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({
      subject_type: subjectType,
      subject_id: subjectId,
      resource_type: 'DEPLOYMENT',
      resource_id: deploymentId,
      actions: ['RUN'],
      effect: 'ALLOW',
    }),
  }),
  listMemory: (deploymentId: string) => request<MemoryItem[]>(`/api/v1/deployments/${deploymentId}/memory-items`),
  createMemory: (deploymentId: string, category: string, content: string, csrf: string, sourceRunId?: string) => request<MemoryItem>('/api/v1/memory-items', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({ deployment_id: deploymentId, category, content, ...(sourceRunId ? { source_run_id: sourceRunId } : {}) }),
  }),
  deleteMemory: (memoryId: string, csrf: string) => request<void>(`/api/v1/memory-items/${memoryId}`, {
    method: 'DELETE', headers: { 'X-CSRF-Token': csrf },
  }),
  listKnowledgeDocuments: (resourceVersionId: string) => request<KnowledgeDocument[]>(`/api/v1/knowledge/documents?knowledge_resource_version_id=${encodeURIComponent(resourceVersionId)}`),
  listKnowledgeIndexes: (resourceVersionId: string) => request<KnowledgeIndex[]>(`/api/v1/knowledge/indexes?knowledge_resource_version_id=${encodeURIComponent(resourceVersionId)}`),
  listIngestJobs: (resourceVersionId: string) => request<IngestJob[]>(`/api/v1/knowledge/ingest-jobs?knowledge_resource_version_id=${encodeURIComponent(resourceVersionId)}`),
  buildKnowledgeIndex: (resourceVersionId: string, csrf: string) => request<{ job_id: string; status: string }>('/api/v1/knowledge/indexes/build', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ knowledge_resource_version_id: resourceVersionId }),
  }),
  uploadKnowledgeDocument: (resourceVersionId: string, file: File, csrf: string) => {
    const form = new FormData()
    form.set('knowledge_resource_version_id', resourceVersionId)
    form.set('file', file, file.name)
    return multipartRequest<KnowledgeDocument>('/api/v1/knowledge/documents/upload', form, csrf)
  },
  testKnowledgeRetrieval: (resourceVersionId: string, query: string, topK: number, csrf: string) => request<Array<{ document_id: string; chunk_number: number; content: string; score: number; index_version_id: string }>>('/api/v1/knowledge/retrieval-test', {
    method: 'POST', headers: { 'X-CSRF-Token': csrf },
    body: JSON.stringify({ knowledge_resource_version_id: resourceVersionId, query, top_k: topK }),
  }),
  createConversation: (deploymentId: string, csrf: string, title = '新会话') => request<ConversationSession>(`/api/v1/deployments/${deploymentId}/conversations`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ title }) }),
  listConversations: (deploymentId: string) => request<ConversationRecord[]>(`/api/v1/deployments/${deploymentId}/conversations`),
  listThreads: (conversationId: string) => request<ThreadRecord[]>(`/api/v1/conversations/${conversationId}/threads`),
  listMessages: (threadId: string) => request<ConversationMessage[]>(`/api/v1/threads/${threadId}/messages`),
  renameConversation: (conversationId: string, title: string, csrf: string) => request<ConversationRecord>(`/api/v1/conversations/${conversationId}`, { method: 'PATCH', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ title }) }),
  catalog: () => request<CatalogItem[]>('/api/v1/resource-version-catalog'),
  deploymentCapabilities: (deploymentId: string) => request<DeploymentCapabilities>(`/api/v1/deployments/${deploymentId}/capabilities`),
  publishConfiguration: (deploymentId: string, specification: Record<string, unknown>, csrf: string, baseRevisionId?: string, publication?: { publication_scope: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'; publication_subjects: Array<{ subject_type: 'USER' | 'ROLE' | 'DEPT'; subject_id: string }> }) => request<{ agent_version_id: string; agent_version_number: number; deployment_revision_id: string; revision_number: number }>(`/api/v1/deployments/${deploymentId}/publish-configuration`, { method: 'POST', headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': browserRequestId() }, body: JSON.stringify({ specification, ...(baseRevisionId ? { base_revision_id: baseRevisionId } : {}), ...(publication || {}) }) }),
  listRevisions: (deploymentId: string) => request<DeploymentRevision[]>(`/api/v1/deployments/${deploymentId}/revisions`),
  workbenchResources: (query = '', resourceType = '', status = '') => request<ResourceListPage>(`/api/v1/workbench/resources?${new URLSearchParams(Object.fromEntries(Object.entries({ query, resource_type: resourceType, status, page_size: '100' }).filter(([, value]) => value))).toString()}`),
  workbenchResource: (resourceId: string) => request<ResourceDetail>(`/api/v1/workbench/resources/${resourceId}`),
  updateResourceDescriptor: (resourceId: string, payload: { owner_user_id: string; owner_dept_id?: string; source_type: string; source_ref?: string; usage_guidance?: string; one_line_summary: string; when_to_use: string; when_not_to_use?: string; input_summary: string; output_summary: string; risk_level: string; read_only: boolean; tags: string[]; lifecycle_status: string; business_line?: string; data_involved?: string; audience?: string; usage_scenarios?: string; developer_user_ids?: string[]; publication_scope?: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS' }, csrf: string) => request<ResourceDetail>(`/api/v1/resources/${resourceId}/descriptor`, { method: 'PATCH', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload) }),
  deleteWorkbenchResource: (resourceId: string, csrf: string) => request<void>(`/api/v1/workbench/resources/${resourceId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } }),
  workbenchKnowledge: (resourceId: string) => request<KnowledgeOverview>(`/api/v1/workbench/knowledge/${resourceId}`),
  workbenchAgents: (query = '', active = '') => request<AgentWorkbenchPage>(`/api/v1/workbench/agents?${new URLSearchParams(Object.fromEntries(Object.entries({ query, active }).filter(([, value]) => value !== ''))).toString()}`),
  deleteWorkbenchDeployment: (deploymentId: string, csrf: string) => request<void>(`/api/v1/workbench/deployments/${deploymentId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } }),
  configurationDraft: (deploymentId: string) => request<ConfigurationDraft>(`/api/v1/deployments/${deploymentId}/configuration-draft`),
  saveConfigurationDraft: (deploymentId: string, body: Pick<ConfigurationDraft, 'specification' | 'base_revision_id' | 'lock_version'>, csrf: string) => request<ConfigurationDraft>(`/api/v1/deployments/${deploymentId}/configuration-draft`, { method: 'PUT', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(body) }),
  validateConfigurationDraft: (deploymentId: string, body: Pick<ConfigurationDraft, 'specification' | 'base_revision_id'>, csrf: string) => request<ConfigurationValidation>(`/api/v1/deployments/${deploymentId}/configuration-draft/validate`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(body) }),
  revisionDetail: (deploymentId: string, revisionId: string) => request<RevisionDetail>(`/api/v1/deployments/${deploymentId}/revisions/${revisionId}`),
}
