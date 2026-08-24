<script setup lang="ts">
import type { CatalogItem, IamSubject, Principal } from '../../api'
import PublicationScopePicker from '../permissions/PublicationScopePicker.vue'

type ResourceCategory = 'CAPABILITY' | 'CONNECTOR' | 'EXTERNAL_APP'
type ResourceForm = Record<string, any>
type RagflowDataset = { id: string; name: string; description?: string }

defineProps<{
  principal: Principal | null
  iamUsers: IamSubject[]
  iamDepartments: IamSubject[]
  iamRoles: IamSubject[]
  resourceSaving: boolean
  ragflowDiscovering: boolean
  selectResourceCategory: (category: ResourceCategory) => void
  catalogFor: (type: string) => CatalogItem[]
  embeddingModels: () => CatalogItem[]
  optionLabel: (item: CatalogItem) => string
  toggleSkillDependency: (field: 'skillToolVersionIds' | 'skillKnowledgeVersionIds', versionId: string) => void
  discoverRagflowDatasets: () => void | Promise<void>
  nextResourceWizardStep: () => void
  createTypedResource: () => void | Promise<void>
}>()

const resourceComposerOpen = defineModel<boolean>('resourceComposerOpen', { required: true })
const resourceWizardStep = defineModel<number>('resourceWizardStep', { required: true })
const resourceCategory = defineModel<ResourceCategory>('resourceCategory', { required: true })
const resourceForm = defineModel<ResourceForm>('resourceForm', { required: true })
const ragflowDatasets = defineModel<RagflowDataset[]>('ragflowDatasets', { required: true })

function scopeLabel(value: unknown) {
  return ({ PERSONAL: '仅负责人', OWNER_DEPT: '责任部门', SELECTED_SUBJECTS: '指定主体' } as Record<string, string>)[String(value)] || '未设置'
}
</script>

<template>
<div class="modal-backdrop resource-wizard-backdrop" @click.self="resourceComposerOpen = false">
<section class="resource-composer resource-wizard-modal" role="dialog" aria-modal="true" aria-label="资源入驻向导">
<header>
<div>
<h2>资源入驻向导</h2>
<p>先选择来源并完成连接或测试，再补充业务信息、RuoYi 可用范围并发布。</p>
</div>
<button class="icon-button" aria-label="关闭" @click="resourceComposerOpen = false">×</button>
</header>
<div class="wizard-steps"><span v-for="item in [{n:1,t:'选择来源'},{n:2,t:'连接与测试'},{n:3,t:'能力信息与权限'},{n:4,t:'发布复核'}]" :key="item.n" :class="{ active: resourceWizardStep === item.n, done: resourceWizardStep > item.n }"><b>{{ item.n }}</b>{{ item.t }}</span></div>
<div v-if="resourceWizardStep === 1" class="resource-kind-picker">
<button :class="{ selected: resourceCategory === 'CAPABILITY' }" @click="selectResourceCategory('CAPABILITY')"><b>可组装能力</b><p>最终会出现在 Agent Assembly：Model、Prompt、Skill、Tool、Knowledge、Memory Policy。</p></button>
<button :class="{ selected: resourceCategory === 'EXTERNAL_APP' }" @click="selectResourceCategory('EXTERNAL_APP')"><b>发布 Dify 应用</b><p>参考智能体广场登记应用信息、RuoYi 可用范围并测试连接，最终生成可组装 External Tool。</p></button>
<button :class="{ selected: resourceCategory === 'CONNECTOR' }" @click="selectResourceCategory('CONNECTOR')"><b>连接器 / 基础设施</b><p>登记 MCP Connection；发现后的业务 Tool 才进入 Agent Assembly。</p></button>
<div class="resource-type-tiles" v-if="resourceCategory === 'CAPABILITY'">
<button v-for="item in [{v:'MODEL',n:'模型',d:'对话推理或 Embedding'},{v:'PROMPT',n:'提示词',d:'角色、边界和回答规则'},{v:'SKILL',n:'技能',d:'业务指令 + Tool/Knowledge 依赖'},{v:'TOOL',n:'原生工具',d:'平台受控实现'},{v:'KNOWLEDGE',n:'知识库',d:'文档、索引和检索'},{v:'MEMORY_POLICY',n:'记忆策略',d:'长期记忆读写边界'}]" :key="item.v" :class="{ selected: resourceForm.type === item.v }" @click="resourceForm.type = item.v"><b>{{ item.n }}</b><small>{{ item.d }}</small></button>
</div>
<div class="resource-type-tiles" v-else-if="resourceCategory === 'CONNECTOR'"><button :class="{ selected: resourceForm.type === 'MCP_CONNECTION' }" @click="resourceForm.type = 'MCP_CONNECTION'"><b>MCP Connection</b><small>连接、发现后注册 MCP Tool</small></button><button :class="{ selected: resourceForm.type === 'KNOWLEDGE_CONNECTION' }" @click="resourceForm.type = 'KNOWLEDGE_CONNECTION'"><b>RAGFlow Connection</b><small>发现 Dataset 后纳管为 Knowledge</small></button></div>
<div class="resource-type-tiles" v-else><button class="selected"><b>Dify Flow Tool</b><small>业务应用登记 + 参数发现 + RuoYi 授权 + Tool 发布</small></button></div>
</div>
<div v-else-if="resourceWizardStep === 3" class="resource-form semantics-form">
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
<div class="dify-section-title wide-field"><b>RuoYi 可用范围</b><span>选择谁可以查看和使用该资源；负责人始终保留管理权限。</span></div>
<template v-if="resourceForm.type === 'DIFY_FLOW'">
<PublicationScopePicker class="wide-field" v-model:scope="resourceForm.difyPublicationScope" v-model:subjects="resourceForm.difyPublicationSubjects" v-model:owner-dept-id="resourceForm.ownerDeptId" :users="iamUsers" :departments="iamDepartments" :roles="iamRoles" />
</template>
<template v-else>
<PublicationScopePicker class="wide-field" v-model:scope="resourceForm.publicationScope" v-model:subjects="resourceForm.publicationSubjects" v-model:owner-dept-id="resourceForm.ownerDeptId" :users="iamUsers" :departments="iamDepartments" :roles="iamRoles" />
</template>
</div>
<div v-else-if="resourceWizardStep === 2" class="resource-form">
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
<div class="wide-field skill-dependency-picker"><b>依赖工具</b><p>Skill 只有 USE 权限不会自动取得依赖权限；发布和运行都会递归检查。</p><div><button v-for="item in catalogFor('TOOL')" :key="item.version_id" :class="{ selected: resourceForm.skillToolVersionIds.includes(item.version_id) }" @click="toggleSkillDependency('skillToolVersionIds', item.version_id)"><span>{{ item.display_name }}</span><small>{{ item.source_type }} · V{{ item.version_number }}</small></button></div></div>
<div class="wide-field skill-dependency-picker"><b>依赖知识库</b><div><button v-for="item in catalogFor('KNOWLEDGE')" :key="item.version_id" :class="{ selected: resourceForm.skillKnowledgeVersionIds.includes(item.version_id) }" @click="toggleSkillDependency('skillKnowledgeVersionIds', item.version_id)"><span>{{ item.display_name }}</span><small>{{ item.source_type }} · V{{ item.version_number }}</small></button></div></div>
<label class="wide-field">业务测试案例<textarea v-model="resourceForm.skillTests" rows="4" placeholder="查询客户编号 C001 => 调用 CRM 客户查询工具并基于结果回答&#10;询问考勤制度 => 检索员工制度知识库并引用内容" /><small class="field-hint">每行一条，格式：用户问题 => 期望行为。至少一条测试编译通过后才能发布。</small></label>
</template>
<template v-else-if="resourceForm.type === 'TOOL'">
<label>工具类型<select v-model="resourceForm.toolMode"><option value="NATIVE">平台原生工具</option><option value="HTTP">受控 HTTP Tool</option></select></label>
<template v-if="resourceForm.toolMode === 'NATIVE'"><label>原生工具<select v-model="resourceForm.nativeName"><option value="echo">Echo</option><option value="calculator">Calculator</option><option value="current_time">Current Time</option></select></label></template>
<template v-else>
<div class="dify-section-title wide-field"><b>固定外部 API</b><span>模型只能调用此固定 Endpoint + Path，参数仅来自下方 JSON Schema；不能访问任意 URL。</span></div>
<label class="wide-field">API Endpoint<input v-model="resourceForm.httpEndpoint" placeholder="https://api.example.com/service" /></label>
<label>固定路径 / 路径模板<input v-model="resourceForm.httpPath" placeholder="/v1/customers/{{customer_id}}" /><small class="field-hint">路径参数会作为单个路径段安全编码，不能改变主机或插入新路径。</small></label><label>请求方法<select v-model="resourceForm.httpMethod"><option value="GET">GET</option><option value="POST">POST</option><option value="PUT">PUT</option><option value="PATCH">PATCH</option></select></label>
<label>Tool Name<input v-model="resourceForm.httpToolName" placeholder="search_policy" /></label><label>调用超时（秒）<input v-model.number="resourceForm.httpTimeout" type="number" min="1" max="60" /></label>
<label class="wide-field">输入 JSON Schema<textarea v-model="resourceForm.httpInputSchema" rows="4" placeholder='{"type":"object","properties":{"query":{"type":"string"}}}' /></label>
<label class="wide-field">Query 模板（可选）<textarea v-model="resourceForm.httpQueryTemplate" rows="3" placeholder='{"q":"{{query}}"}' /></label>
<label class="wide-field">POST Body 模板（可选）<textarea v-model="resourceForm.httpBodyTemplate" rows="3" placeholder='{"query":"{{query}}"}' /></label>
<label class="wide-field">固定 Header 模板（可选）<textarea v-model="resourceForm.httpHeaderTemplate" rows="3" placeholder='{"X-Business-Unit":"hr","X-Request-Source":"agent-platform"}' /><small class="field-hint">Authorization、Host、Cookie、转发头等安全敏感 Header 禁止配置；认证凭据只能由 Vault 注入。</small></label>
<label class="wide-field">响应映射（可选）<textarea v-model="resourceForm.httpResponseMapping" rows="3" placeholder='{"body_path":"data","fields":{"id":"customer.id","name":"customer.name"}}' /><small class="field-hint">只支持固定点路径取值，不执行脚本或表达式。</small></label>
<label>API Key（可选）<input v-model="resourceForm.httpApiKey" type="password" autocomplete="new-password" placeholder="仅本次提交，后端保存至 Vault" /></label>
<label class="wide-field">测试参数 JSON<textarea v-model="resourceForm.httpTestArguments" rows="3" placeholder='{"query":"员工考勤管理办法"}' /></label>
</template>
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
<template v-else-if="resourceForm.type === 'KNOWLEDGE_CONNECTION'">
<label class="wide-field">RAGFlow Endpoint<input v-model="resourceForm.ragflowEndpoint" placeholder="https://ragflow.example.com" /></label>
<label>调用超时（秒）<input v-model.number="resourceForm.ragflowTimeout" type="number" min="1" max="60" /></label>
<label class="wide-field">RAGFlow API Key<input v-model="resourceForm.ragflowApiKey" type="password" autocomplete="new-password" placeholder="仅本次提交，后端保存至 Vault" /></label>
</template>
<template v-else-if="resourceForm.type === 'KNOWLEDGE'">
<label>知识来源<select v-model="resourceForm.knowledgeSource" @change="ragflowDatasets = []; resourceForm.ragflowDatasetId = ''"><option value="LOCAL">平台文件知识库（PDF / DOCX）</option><option value="RAGFLOW">RAGFlow 外部数据集</option><option value="REMOTE_HTTP">企业知识检索 API</option></select></label>
<template v-if="resourceForm.knowledgeSource === 'LOCAL'">
<label>Embedding 模型版本<select v-model="resourceForm.embeddingModelVersionId">
<option value="">请选择已发布 Embedding 模型</option>
<option v-for="item in embeddingModels()" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option>
</select>
</label>
</template>
<template v-else-if="resourceForm.knowledgeSource === 'RAGFLOW'">
<label>RAGFlow 连接<select v-model="resourceForm.ragflowConnectionVersionId" @change="ragflowDatasets = []; resourceForm.ragflowDatasetId = ''"><option value="">请选择已发布连接</option><option v-for="item in catalogFor('KNOWLEDGE_CONNECTION')" :key="item.version_id" :value="item.version_id">{{ optionLabel(item) }}</option></select></label>
<label class="button-field"><span>数据集发现</span><button class="button ghost" type="button" :disabled="ragflowDiscovering || !resourceForm.ragflowConnectionVersionId" @click="discoverRagflowDatasets">{{ ragflowDiscovering ? '发现中…' : '发现数据集' }}</button></label>
<label class="wide-field">RAGFlow 数据集<select v-model="resourceForm.ragflowDatasetId" :disabled="!ragflowDatasets.length"><option value="">{{ ragflowDatasets.length ? '请选择数据集' : '请先发现数据集' }}</option><option v-for="item in ragflowDatasets" :key="item.id" :value="item.id">{{ item.name }}{{ item.description ? ` · ${item.description}` : '' }}</option></select><small class="field-hint">数据集标识只保存在不可变资源版本中，不会发送到模型上下文。</small></label>
</template>
<template v-else>
<div class="dify-section-title wide-field"><b>固定企业知识 API</b><span>模型只会看到 query 和 top_k；Endpoint、固定参数和字段映射保存在不可变资源版本中。</span></div>
<label class="wide-field">API Endpoint<input v-model="resourceForm.remoteKnowledgeEndpoint" placeholder="https://knowledge.example.com" /></label>
<label>检索路径<input v-model="resourceForm.remoteKnowledgePath" placeholder="/search" /></label><label>请求方法<select v-model="resourceForm.remoteKnowledgeMethod"><option value="POST">POST</option><option value="GET">GET</option></select></label>
<label>超时（秒）<input v-model.number="resourceForm.remoteKnowledgeTimeout" type="number" min="1" max="60" /></label><label>API Key（可选）<input v-model="resourceForm.remoteKnowledgeApiKey" type="password" autocomplete="new-password" placeholder="仅提交一次，后端 Vault 保存" /></label>
<label>问题字段<input v-model="resourceForm.remoteKnowledgeQueryField" placeholder="query" /></label><label>数量字段<input v-model="resourceForm.remoteKnowledgeTopKField" placeholder="top_k" /></label>
<label class="wide-field">固定请求参数 JSON<textarea v-model="resourceForm.remoteKnowledgeStaticBody" rows="3" placeholder='{"knowledge_id":"hr-policy"}' /><small class="field-hint">适合固定 knowledge_id、业务域等参数；这些字段不会交给模型修改。</small></label>
<div class="dify-section-title wide-field"><b>响应字段映射</b><span>将已有系统返回结果归一化为平台 Knowledge Hit。</span></div>
<label>结果列表路径<input v-model="resourceForm.remoteKnowledgeItemsPath" placeholder="data.items" /></label><label>正文字段<input v-model="resourceForm.remoteKnowledgeContentField" placeholder="content" /></label>
<label>ID 字段<input v-model="resourceForm.remoteKnowledgeIdField" placeholder="id" /></label><label>标题字段<input v-model="resourceForm.remoteKnowledgeTitleField" placeholder="title" /></label>
<label>相似度字段<input v-model="resourceForm.remoteKnowledgeScoreField" placeholder="score（可留空）" /></label><label>元数据字段<input v-model="resourceForm.remoteKnowledgeMetadataField" placeholder="metadata" /></label>
<label class="wide-field">发布前测试问题<input v-model="resourceForm.remoteKnowledgeTestQuery" placeholder="例如：员工考勤管理办法" /><small class="field-hint">必须真实检索成功后才会发布；失败只保留不可用 Draft，不进入 Agent Builder。</small></label>
</template>
</template>
<template v-else-if="resourceForm.type === 'MEMORY_POLICY'">
<label>TTL（天）<input v-model.number="resourceForm.ttlDays" type="number" min="1" />
</label>
<label>最大条数<input v-model.number="resourceForm.maxItems" type="number" min="1" />
</label>
<label class="wide-field">允许分类（逗号分隔）<input v-model="resourceForm.categories" />
</label>
</template>
</div>
<div v-else class="resource-publish-review">
<div class="semantic-preview"><span class="type-badge">{{ resourceCategory === 'CAPABILITY' ? '可组装能力' : resourceCategory === 'EXTERNAL_APP' ? 'Dify 外部应用' : '连接器' }}</span><h3>{{ resourceForm.displayName }}</h3><strong>{{ resourceForm.oneLineSummary }}</strong><p>{{ resourceForm.description }}</p><dl><dt>何时使用</dt><dd>{{ resourceForm.whenToUse }}</dd><dt>输入</dt><dd>{{ resourceForm.inputSummary }}</dd><dt>输出</dt><dd>{{ resourceForm.outputSummary }}</dd><dt>负责人</dt><dd>{{ iamUsers.find(item => item.external_id === resourceForm.ownerUserId)?.display_name || principal?.display_name }}</dd><dt>风险</dt><dd>{{ resourceForm.riskLevel }} · {{ resourceForm.readOnly ? '只读' : '可写' }}</dd><dt>可用范围</dt><dd>{{ scopeLabel(resourceForm.type === 'DIFY_FLOW' ? resourceForm.difyPublicationScope : resourceForm.publicationScope) }}</dd><template v-if="resourceForm.type === 'DIFY_FLOW'"><dt>业务线</dt><dd>{{ resourceForm.difyBusinessLine }}</dd><dt>使用对象</dt><dd>{{ resourceForm.difyAudience }}</dd></template></dl></div>
<div class="publish-note"><b>{{ resourceCategory === 'EXTERNAL_APP' ? '测试 Dify 并发布为可组装 Tool' : resourceCategory === 'CAPABILITY' ? '发布后可进入 Agent Assembly' : '这是基础设施，不直接组装进 Agent' }}</b><p v-if="resourceCategory === 'CONNECTOR'">MCP 连接发布后需要发现并注册 Tool。</p><p v-if="resourceCategory === 'EXTERNAL_APP'">将读取 Dify 输入参数、加密保存 Key，并在确认发布时按 RuoYi 可用范围创建资源授权。</p></div>
</div>
<footer>
<button class="button ghost" @click="resourceWizardStep === 1 ? resourceComposerOpen = false : resourceWizardStep--">{{ resourceWizardStep === 1 ? '取消' : '上一步' }}</button>
<button v-if="resourceWizardStep < 4" class="button primary" @click="nextResourceWizardStep">下一步</button>
<button v-else class="button primary" :disabled="resourceSaving" @click="createTypedResource">{{ resourceSaving ? '测试并发布中…' : '确认发布 V1' }}</button>
</footer>
</section>
</div>
</template>
