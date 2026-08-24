<script setup lang="ts">
import type {
  IamSubject,
  KnowledgeOverview,
  McpDiscoveredTool,
  Principal,
  ResourceDetail,
  ResourceImpact,
  ResourceValidationRun,
} from '../../api'
import DiscoveryDriftPanel from '../../components/DiscoveryDriftPanel.vue'
import PublicationScopePicker from '../../features/permissions/PublicationScopePicker.vue'

type DetailTab = 'OVERVIEW' | 'VERSIONS' | 'GOVERNANCE' | 'TECHNICAL'
type DescriptorForm = {
  owner_user_id: string
  owner_dept_id: string
  source_type: string
  source_ref: string
  usage_guidance: string
  one_line_summary: string
  when_to_use: string
  when_not_to_use: string
  input_summary: string
  output_summary: string
  risk_level: string
  read_only: boolean
  tags: string
  lifecycle_status: string
}
type McpToolDraft = {
  selected: boolean
  displayName: string
  slug: string
  description: string
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
  readOnly: boolean
  publicationScope: 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'
  ownerDeptId: string
  publicationSubjects: string[]
}

defineProps<{
  selectedResource: ResourceDetail
  selectedKnowledge: KnowledgeOverview | null
  resourceImpact: ResourceImpact | null
  principal: Principal | null
  iamUsers: IamSubject[]
  iamDepartments: IamSubject[]
  iamRoles: IamSubject[]
  resourceSaving: boolean
  mcpDiscoveredTools: McpDiscoveredTool[]
  mcpDiscovering: boolean
  mcpRegistering: boolean
  validationRunsByVersion: Record<string, ResourceValidationRun[]>
  csrf: string
  closeDetail: () => void
  typeLabel: (value: string) => string
  healthLabel: (value: string) => string
  statusLabel: (value: string) => string
  shortTime: (value?: string) => string
  saveDescriptor: () => void | Promise<void>
  discoverSelectedMcpTools: () => void | Promise<void>
  registerSelectedMcpTools: () => void | Promise<void>
  canRetryResourceVersion: () => boolean
  retryValidateAndPublish: (versionId: string) => void | Promise<void>
  deleteResource: () => void | Promise<void>
}>()

const resourceDetailTab = defineModel<DetailTab>('resourceDetailTab', { required: true })
const descriptorEditing = defineModel<boolean>('descriptorEditing', { required: true })
const descriptorForm = defineModel<DescriptorForm>('descriptorForm', { required: true })
const mcpToolDrafts = defineModel<Record<string, McpToolDraft>>('mcpToolDrafts', { required: true })
</script>

<template>
<aside class="detail-drawer resource-detail-page">
<header>
<div>
<button class="text-link" @click="closeDetail">‹ 返回列表</button>
<p class="eyebrow">{{ typeLabel(selectedResource.resource.resource_type) }} · {{ selectedResource.source }}</p>
<h2>{{ selectedResource.resource.display_name }}</h2>
<p>{{ selectedResource.resource.description || selectedResource.resource.slug }}</p>
</div>
<button class="icon-button" aria-label="关闭详情" @click="closeDetail">×</button>
</header>
<nav class="resource-detail-tabs" aria-label="资源详情导航">
<button :class="{ active: resourceDetailTab === 'OVERVIEW' }" @click="resourceDetailTab = 'OVERVIEW'">概览</button>
<button :class="{ active: resourceDetailTab === 'VERSIONS' }" @click="resourceDetailTab = 'VERSIONS'">版本与依赖</button>
<button :class="{ active: resourceDetailTab === 'GOVERNANCE' }" @click="resourceDetailTab = 'GOVERNANCE'">权限与引用</button>
<button :class="{ active: resourceDetailTab === 'TECHNICAL' }" @click="resourceDetailTab = 'TECHNICAL'">技术摘要</button>
</nav>
<div class="drawer-body">
<section v-if="resourceDetailTab === 'OVERVIEW'" class="detail-metrics">
<span>
<b>{{ selectedResource.resource.published_version_count }}</b> 发布版本</span>
<span>
<b>{{ selectedResource.resource.referenced_by_count }}</b> Agent 引用</span>
<span>
<b>{{ selectedResource.grants_count }}</b> 授权规则</span>
<span><b>{{ healthLabel(selectedResource.resource.health) }}</b> 运行健康</span>
</section>
<section v-if="resourceDetailTab === 'OVERVIEW'" class="metadata-list">
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
<section v-if="resourceDetailTab === 'OVERVIEW' && selectedResource.resource.source_type === 'DIFY'" class="dify-detail-section">
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
<section v-if="resourceDetailTab === 'OVERVIEW' && selectedResource.resource.resource_type === 'MCP_CONNECTION'" class="mcp-discovery-section">
<div class="section-heading"><div><h3>MCP 工具发现与纳管</h3><p>从当前连接实时读取 tools/list；每个 Tool 独立成为资源、独立设置 RuoYi 使用权限。</p></div><button class="button primary" :disabled="mcpDiscovering" @click="discoverSelectedMcpTools">{{ mcpDiscovering ? '发现中…' : '发现工具' }}</button></div>
<p v-if="!mcpDiscoveredTools.length" class="empty-copy">点击“发现工具”查看该 MCP 服务当前提供的业务能力。</p>
<div v-else class="mcp-tool-grid">
<article v-for="item in mcpDiscoveredTools" :key="item.name" :class="['mcp-tool-card', { managed: item.managed, selected: mcpToolDrafts[item.name]?.selected }]">
<header><label class="mcp-tool-select"><input v-if="!item.managed" v-model="mcpToolDrafts[item.name].selected" type="checkbox" /><span><b>{{ item.name }}</b><small>{{ item.description || '上游未提供说明' }}</small></span></label><span :class="['status-pill', item.binding_status === 'CHANGED' || item.binding_status === 'MISSING' ? 'blocked' : 'success']">{{ item.managed ? ({MANAGED:'已纳管',CHANGED:'Schema 已变化',MISSING:'上游已删除'}[item.binding_status || 'MANAGED']) : '可接入' }}</span></header>
<div class="tag-list compact"><span>{{ Object.keys((item.input_schema.properties as Record<string, unknown>) || {}).length }} 个输入</span><span>独立授权</span></div>
<div v-if="!item.managed && mcpToolDrafts[item.name]?.selected" class="mcp-tool-form">
<label>业务名称<input v-model="mcpToolDrafts[item.name].displayName" /></label><label>Slug<input v-model="mcpToolDrafts[item.name].slug" /></label>
<label class="wide-field">业务说明<textarea v-model="mcpToolDrafts[item.name].description" rows="2" /></label>
<label>风险等级<select v-model="mcpToolDrafts[item.name].riskLevel"><option value="LOW">低</option><option value="MEDIUM">中</option><option value="HIGH">高</option></select></label><label class="check-label"><input v-model="mcpToolDrafts[item.name].readOnly" type="checkbox" />只读工具</label>
<PublicationScopePicker class="wide-field" v-model:scope="mcpToolDrafts[item.name].publicationScope" v-model:subjects="mcpToolDrafts[item.name].publicationSubjects" v-model:owner-dept-id="mcpToolDrafts[item.name].ownerDeptId" :users="iamUsers" :departments="iamDepartments" :roles="iamRoles" personal-label="仅当前负责人" />
</div>
</article>
</div>
<div v-if="mcpDiscoveredTools.some(item => !item.managed && mcpToolDrafts[item.name]?.selected)" class="mcp-register-actions"><p>只会发布已勾选 Tool；上游 Schema 由服务器可信发现结果写入，前端不能伪造。</p><button class="button primary" :disabled="mcpRegistering" @click="registerSelectedMcpTools">{{ mcpRegistering ? '发布中…' : '发布选中工具' }}</button></div>
</section>
<section v-if="resourceDetailTab === 'OVERVIEW' && selectedKnowledge">
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
<DiscoveryDriftPanel
  v-if="resourceDetailTab === 'VERSIONS'"
  :versions="selectedResource.versions"
  :csrf="csrf"
  :supported="['DIFY', 'MCP', 'HTTP', 'RAGFLOW'].includes(selectedResource.resource.source_type || selectedResource.source)"
/>
<section v-if="resourceDetailTab === 'VERSIONS'">
<h3>版本</h3>
<article v-for="version in selectedResource.versions" :key="version.version_id" class="version-card">
<div>
<b>V{{ version.version_number }}</b>
<span :class="['status-pill', version.status === 'DRAFT' ? 'blocked' : 'success']">{{ statusLabel(version.status) }}</span>
</div>
<p>{{ version.summary }}</p>
<div v-if="validationRunsByVersion[version.version_id]?.length" class="version-validation-summary">
<span :class="['status-pill', validationRunsByVersion[version.version_id][0].status === 'SUCCEEDED' ? 'success' : 'blocked']">{{ validationRunsByVersion[version.version_id][0].validation_type }} · {{ validationRunsByVersion[version.version_id][0].status === 'SUCCEEDED' ? '通过' : '失败' }}</span>
<small>{{ validationRunsByVersion[version.version_id][0].result.message || validationRunsByVersion[version.version_id][0].result.code || '已记录验证结果' }}</small>
</div>
<button v-if="version.status === 'DRAFT' && canRetryResourceVersion()" class="button primary" :disabled="resourceSaving" @click="retryValidateAndPublish(version.version_id)">{{ resourceSaving ? '验证中…' : '重新测试、验证并发布' }}</button>
<small>{{ version.content_hash.slice(0, 12) }}</small>
</article>
</section>
<section v-if="resourceDetailTab === 'VERSIONS' && selectedResource.dependency_graph.length">
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
<section v-if="resourceDetailTab === 'GOVERNANCE'">
<h3>授权与有效权限</h3>
<p v-if="!selectedResource.effective_permissions.length" class="empty-copy">当前用户没有额外授权规则。</p>
<article v-for="permission in selectedResource.effective_permissions" :key="`${permission.origin}-${permission.subject_id || ''}-${permission.actions.join('-')}`" class="reference-item">
<b>{{ permission.origin }} · {{ permission.effect }}</b>
<small>{{ permission.subject_id || '当前资源' }} · {{ permission.actions.join(' / ') }}</small>
</article>
</section>
<section v-if="resourceDetailTab === 'GOVERNANCE'">
<h3>引用关系</h3>
<p v-if="!selectedResource.references.length" class="empty-copy">当前未被 Agent Version 引用。</p>
<article v-for="item in selectedResource.references" :key="`${item.agent_id}-${item.version_number}`" class="reference-item">
<b>{{ item.display_name }}</b>
<small>{{ item.kind }} · V{{ item.version_number }}</small>
</article>
</section>
<section v-if="resourceDetailTab === 'GOVERNANCE' && resourceImpact" class="impact-panel">
<div class="impact-heading"><div><h3>变更影响</h3><p>归档或删除前必须先确认智能体、依赖资源、授权和近期运行影响。</p></div><span :class="['status-pill', resourceImpact.can_delete ? 'success' : 'blocked']">{{ resourceImpact.can_delete ? '允许删除' : '禁止物理删除' }}</span></div>
<div class="detail-metrics"><span><b>{{ resourceImpact.agent_versions.length }}</b> Agent 版本</span><span><b>{{ resourceImpact.active_deployments.length }}</b> 活跃部署</span><span><b>{{ resourceImpact.dependent_resources.length }}</b> 依赖资源</span><span><b>{{ resourceImpact.recent_run_count }}</b> 近 30 天运行</span><span><b>{{ resourceImpact.grant_count }}</b> 授权规则</span><span><b>{{ resourceImpact.knowledge_document_count }}</b> 知识文档</span></div>
<article v-for="item in resourceImpact.active_deployments" :key="item.deployment_id" class="reference-item"><b>{{ item.name }}</b><small>活跃 Revision {{ item.revision_number }}</small></article>
<article v-for="item in resourceImpact.dependent_resources" :key="item.resource_id" class="reference-item"><b>{{ item.display_name }}</b><small>{{ typeLabel(item.resource_type) }} 依赖当前资源</small></article>
</section>
<section v-if="resourceDetailTab === 'TECHNICAL'" class="technical-summary">
<h3>安全配置摘要</h3>
<p>这里只展示后端脱敏后的结构，密钥、Token 与 Vault 引用不会返回前端。</p>
<pre>{{ JSON.stringify(selectedResource.safe_config, null, 2) }}</pre>
</section>
<footer class="drawer-footer">
<button class="button danger" :disabled="resourceImpact ? !resourceImpact.can_delete : false" @click="deleteResource">{{ resourceImpact && !resourceImpact.can_delete ? '资源使用中，不能删除' : '删除此资源' }}</button>
</footer>
</div>
</aside>
</template>

