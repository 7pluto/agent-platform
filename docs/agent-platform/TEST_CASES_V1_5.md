# Enterprise Agent Platform V1.5 测试案例与验收记录

本文档是持续维护的验收基线。每个案例必须保留测试数据、操作步骤、预期结果和证据；未执行的案例不得标记为通过。

## 1. 当前自动化基线

执行日期：2026-08-24

| 范围 | 执行方式 | 结果 | 证据 |
|---|---|---|---|
| 后端全量单元与集成测试 | `py -3 -m pytest -q` | 87 passed | pytest 终端结果；仅有 Windows pytest cache 目录权限告警 |
| Python 语法与模块编译 | `py -3.12 -m compileall -q app tests migrations` | 通过 | 无编译错误 |
| Console TypeScript | `npx vue-tsc --noEmit` | 通过 | 无类型错误 |
| Console 生产构建 | `npm run build` | 通过 | Vite 生成 `dist`，JS/CSS bundle 正常 |

## 2. 权限裁剪业务矩阵

### PERMISSION-001：Deployment RUN 与多来源 Resource USE 分离

测试智能体固定挂载以下能力：Dify A、Dify B、CRM MCP Tool、财务 MCP Tool、受控 HTTP 工单 Tool、本地员工制度 Knowledge、RAGFlow 财务 Knowledge、Remote HTTP 客服 Knowledge。

测试账号只获得 Deployment `VIEW/RUN`，并只获得 Dify A、CRM MCP Tool 及其 Connection、HTTP Tool、本地 Knowledge、Remote HTTP Knowledge 的 `USE`；不授予 Dify B、财务 MCP Connection/Tool、RAGFlow 财务 Knowledge 的 `USE`。

步骤：

1. 用测试账号打开智能体广场，确认智能体可见并可创建会话。
2. 创建 Run，检查不可变 Manifest 中每项资源的 `use_allowed` 判定。
3. 检查 `runtime.capabilities.registered` 与实际传给模型的 Tool Registry。
4. 分别搜索已授权和未授权能力的业务名称、Tool Name、外部应用 ID、Dataset ID。

预期：

- Deployment 可见和可运行不受可选资源未授权影响。
- 已授权的 Dify、MCP 单工具、HTTP Tool、本地/Remote Knowledge 正常进入 Tool Registry。
- 未授权的 Dify B、财务 MCP Tool/Connection、RAGFlow Knowledge 不进入 Tool Registry。
- 模型上下文和 Tool Schema 中找不到受限能力名称、参数、Version ID 或外部 ID。
- 权限裁剪只影响受限能力，不阻断其他已授权能力和最终回答。

状态：运行时注册表自动化通过。证据：`tests/test_permission_matrix.py::test_runtime_registry_only_contains_use_authorized_business_capabilities`。RuoYi 多账号、角色和部门的真实环境矩阵仍需部署后执行。

### PERMISSION-002：权限变更只影响新 Run

步骤：创建 Run A 后撤销某 Tool 的 `USE`，再创建 Run B。

预期：Run A 的 Manifest 保留创建时授权快照，可用于复盘；Run B 的 Manifest 标记该资源不可用，Tool Registry 不再包含该能力；不改写旧 Agent Version、Revision 或 Run。

状态：待 PostgreSQL + RuoYi 真实环境执行。

## 3. Discovery Snapshot 与 Drift

### DRIFT-001：Dify 发布快照不保存凭据

前置条件：准备一个包含 `secret_ref`、Flow 类型和输入表单的 Published Dify Tool Version。

步骤：

1. 发布 Dify Tool Version。
2. 查询 `/resource-versions/{version_id}/discovery-snapshots`。
3. 检查快照结构和持久化记录。

预期：

- Provider 为 `DIFY`，外部类型为 `APPLICATION`。
- 快照包含 Flow 类型和输入定义，并生成 canonical `schema_hash`。
- 快照、API、审计和日志均不包含 API Key、Authorization 或 `secret_ref`。

状态：自动化通过。证据：`tests/test_discovery_drift.py::test_changed_dify_snapshot_creates_one_immutable_draft`。

### DRIFT-002：Dify 输入变化生成唯一 Draft

前置条件：Published Version 的输入为空，上游 Dify 新增必填字段 `department`。

步骤：

1. 调用漂移检查接口，保持 `create_draft=true`。
2. 再次以相同上游定义调用漂移检查。
3. 查询原 Published Version 和资源的版本列表。

预期：

- 第一次返回 `CHANGED` 并生成新 Draft Version。
- Draft 的输入 Schema 包含 `department`，旧 Published Version 内容和 hash 不变。
- 第二次返回同一个 Draft ID，不重复产生版本。

状态：自动化通过。证据：`tests/test_discovery_drift.py::test_changed_dify_snapshot_creates_one_immutable_draft`。

### DRIFT-003：受控 HTTP Tool 无虚假漂移

前置条件：发布一个固定 endpoint、method、path、input schema 和 request mapping 的 HTTP Tool。

步骤：建立发布快照并执行漂移检查。

预期：返回 `NO_CHANGE`，当前 hash 与发布 hash 相等，不创建 Draft；模型仍只能提交已声明参数，不能改变 endpoint、path 或认证配置。

状态：自动化通过。证据：`tests/test_discovery_drift.py::test_governed_http_snapshot_reports_no_change`。

### DRIFT-004：MCP Tool Schema 变化

前置条件：MCP Connection 已发布并注册 Tool V1，上游 `tools/list` 修改该 Tool 的 `inputSchema`。

步骤：对 Tool V1 执行漂移检查。

预期：返回 `CHANGED`；创建包含新 Schema 的 Draft V2；Tool V1、现有 Agent Revision 和旧 Run Manifest 不变。

状态：待真实 MCP 集成环境执行。

### DRIFT-005：MCP Tool 被删除

前置条件：已发布 MCP Tool，但上游 `tools/list` 不再返回该名称。

步骤：执行漂移检查。

预期：返回 `MISSING`；不伪造新版本；资源详情显示上游对象缺失，后续 Agent 发布校验应阻断引用该资源的新 Revision。

状态：待真实 MCP 集成环境执行。

### DRIFT-006：RAGFlow Dataset 元数据变化

前置条件：一个 RAGFlow Dataset 已注册为 Knowledge V1，上游修改 Dataset 名称或说明。

步骤：执行漂移检查。

预期：返回 `CHANGED` 并创建 Draft V2；可信 `external_dataset_id` 仍由服务器配置固定，模型不可见也不可传入。

状态：待真实 RAGFlow 环境执行。

### DRIFT-007：RAGFlow Dataset 被删除

前置条件：Knowledge V1 绑定的 Dataset 已在 RAGFlow 删除。

步骤：执行漂移检查。

预期：返回 `MISSING`，不创建无效 Draft；资源健康状态进入异常，Agent 新发布应被阻断。

状态：待真实 RAGFlow 环境执行。

### DRIFT-008：上游不可用

前置条件：Dify、MCP 或 RAGFlow 连接超时、凭据失效或服务不可达。

步骤：执行漂移检查。

预期：返回 `UNAVAILABLE` 和安全错误码；不覆盖发布快照、不修改 Published Version、不产生 Draft；响应不包含密钥。

状态：待外部 Provider 故障注入测试。

### DRIFT-009：租户隔离

前置条件：租户 A、B 各自存在资源快照。

步骤：租户 B 使用租户 A 的 Version ID 查询快照或执行漂移检查。

预期：返回不可见或拒绝；PostgreSQL RLS 同时阻止越权读取和写入。

状态：待 PostgreSQL 双租户集成测试。

## 4. Trace 与 Observation Policy

### TRACE-001：事件脱敏与限长

步骤：让 Tool 返回嵌套的 Authorization、API Key、Access Token、Secret、Cookie，以及超长字符串和超过 100 项的数组。

预期：

- 敏感字段在持久化前统一替换为 `[REDACTED]`。
- 普通字段保留；`token_count` 等非凭据指标不被误删。
- Tool/模型 observation、RAG hit 数量、单段内容和 Trace 总 payload 均受固定上限控制。
- 超限结果明确带 `_truncated` 与原始字符数，不会导致 Run 或页面崩溃。
- Manifest 记录 `observation=standard@1`，旧 Run 仍可按原 Manifest 复盘。

状态：自动化通过。证据：`tests/test_observation_policy.py`、`tests/test_worker.py`。

### TRACE-002：聊天页中文 Timeline

步骤：执行包含 Memory、Skill、MCP/HTTP Tool、Knowledge 检索的 Run。

预期：执行时 Trace 自动展开；完成或失败后自动收起；标题展示耗时、工具次数、知识命中数和 Memory 数；事件默认显示中文业务摘要；原始脱敏 JSON 仅在“查看原始事件”后出现；最终回答始终位于 Trace 下方。

状态：前端类型检查和生产构建通过；真实组合 Run 的浏览器验收待部署后执行。

## 5. 前端产品化验收

### UI-001：唯一 Agent Builder

步骤：进入任意 Deployment 配置页，依次选择模型与身份、技能与工具、知识与记忆。

预期：只有一套三栏式 Builder；支持名称/用途搜索、Provider 和风险筛选、卡片添加/移除及快速详情；能力选择器不存在 `<select multiple>` 或高级 JSON；右侧持续显示当前组装和预检阻断项；MCP Connection 不作为新配置的直接能力出现。

状态：源码结构检查、Vue 类型检查和生产构建通过；浏览器交互验收待部署后执行。

### UI-002：能力、连接与知识分区

步骤：分别访问 `/console/capabilities`、`/console/connections`、`/console/knowledge`。

预期：能力中心只展示 Model、Prompt、Skill、Tool、Memory Policy；系统连接只展示 MCP/RAGFlow Connection；知识库运营只展示 Knowledge。卡片主标题为业务名称，UUID、hash、raw config 不作为默认内容。

状态：Vue 类型检查与生产构建通过。

### UI-003：独立资源详情

步骤：从能力或连接卡片进入详情并刷新页面。

预期：详情拥有稳定 URL；以“概览、版本与依赖、权限与引用、技术摘要”分区；默认不平铺原始配置；返回列表和浏览器前进后退正常。

状态：路由、类型检查与生产构建通过；浏览器刷新验收待部署后执行。

### LIFECYCLE-001：统一健康状态

步骤：分别查看可用/不可用 Model、有/无活跃索引的 Local Knowledge、未检查的 Dify/MCP/RAGFlow 和已记录异常的外部 Provider。

预期：API 与卡片只使用 `HEALTHY / DEGRADED / UNHEALTHY / UNKNOWN`；前端显示“健康 / 需关注 / 异常 / 未检查”；“已发布”和“健康”分别展示，不能把配置完成误认为上游健康。

状态：映射自动化通过。证据：`tests/test_resource_health.py`。

### LIFECYCLE-002：删除前影响分析

步骤：依次对未使用资源、被 Skill 依赖资源、被历史 Agent Version 引用资源、被活跃 Revision 引用资源、含知识文档资源调用影响接口并尝试删除。

预期：详情“权限与引用”显示 Agent Version、活跃 Deployment、依赖资源、近 30 天 Run、Grant 和知识文档数量；有 Agent/资源/文档引用时 `can_delete=false`，按钮禁用，DELETE 再次返回 `RESOURCE_DELETE_BLOCKED`；无引用资源允许删除并记录审计。

状态：接口与 UI 已实现；PostgreSQL 组合数据验收待部署后执行。

## 6. 最终业务验收矩阵

### VALIDATE-001：外部 Knowledge 不要求本地索引

前置条件：Remote HTTP Knowledge 已发布并完成成功检索测试。

步骤：将该 Knowledge 加入 Agent Draft 并执行发布校验。

预期：校验读取 Provider Test，不返回 `KNOWLEDGE_INDEX_NOT_ACTIVE`；若 Test 不存在或失败，返回 `REMOTE_KNOWLEDGE_TEST_REQUIRED`。

状态：自动化通过。证据：`tests/test_agent_validation.py::test_remote_http_knowledge_uses_provider_test_not_local_index`。

### VALIDATE-002：RAGFlow Dataset 缺失阻断发布

前置条件：Agent Draft 引用的 RAGFlow Knowledge 对应 Dataset 已删除。

步骤：执行配置验证或直接调用发布命令。

预期：返回 `RAGFLOW_MISSING`；不创建 Agent Version 和 Revision，不切换当前 Revision。

状态：自动化通过。证据：`tests/test_agent_validation.py::test_missing_ragflow_dataset_blocks_agent_publish`；最终“不产生版本”仍需 PostgreSQL 命令级集成断言。

### VALIDATE-003：Secret 已禁用

前置条件：Dify、MCP、HTTP Tool 或外部 Knowledge 使用的 Vault Secret 已禁用。

步骤：执行 Agent 发布。

预期：返回 `SECRET_DISABLED`；响应与审计不包含密钥或密文；当前 Revision 不变。

状态：待 PostgreSQL/Vault 集成测试。

### VALIDATE-004：Provider 健康与测试门槛

前置条件：分别准备 Dify、MCP、HTTP Tool、RAGFlow、Remote HTTP Knowledge 的成功与失败状态。

步骤：逐一加入 Agent Draft 并执行发布校验。

预期：Dify 需要 Validate 且当前 Probe 成功；MCP 需要 Probe 成功；HTTP Tool 需要成功 TEST；RAGFlow 需要存在、可连接并有成功检索 TEST；Remote HTTP 需要成功检索 TEST。

状态：待真实 Provider 组合测试。

### KNOWLEDGE-REMOTE-001：企业知识 API 接入并发布

前置条件：准备一个只允许固定 Host/Path 的企业检索接口，返回结构化列表；若需要认证，准备一次性 API Key。

步骤：

1. 在“知识库 → 添加知识库”选择“企业知识检索 API”。
2. 填写固定 Endpoint、检索 Path、GET/POST、超时；填写问题字段与数量字段。
3. 在固定请求参数中设置业务系统要求的 `knowledge_id`，配置列表路径、正文、标题、分数和元数据字段。
4. 输入一条真实业务测试问题，配置 RuoYi 可用范围，确认发布。
5. 在知识库详情执行检索测试，再将其加入 Agent 并运行。

预期：

- 模型只看到 `query/top_k`，不能修改 Endpoint、Path、`knowledge_id`、认证或字段映射。
- 后端在发布前执行真实检索，失败只保留不可用 Draft，不进入 Agent Builder。
- API Key 只提交一次并写入 Vault；发布响应、详情、Trace 和审计不返回 Key 或 `secret_ref`。
- 返回结果统一为 Knowledge Hit，Agent Runtime 不包含 Remote HTTP 专属分支。
- 未获得此 Knowledge `USE` 的用户在模型 Tool Registry 中看不到名称、参数或固定 `knowledge_id`。

状态：产品发布命令自动化通过。证据：`tests/test_knowledge_providers.py::test_remote_http_knowledge_product_publish_tests_before_exposure`。真实外部接口与 Agent 组合运行待部署后执行。

以下案例是 V1.5 完成门槛，后续迭代继续在本文档补充步骤与证据：

| 编号 | 业务链路 | 核心验收点 | 当前状态 |
|---|---|---|---|
| BIZ-001 | Dify 连接→发现→测试→发布→Agent 调用 | 参数自动发现、凭据 Vault、Resource USE 裁剪、真实回答 | 待全链验收 |
| BIZ-002 | CRM MCP 连接→发现 Tool→批量注册→Agent 调用 | 单 Tool 独立授权、未授权 Tool 不进入模型 Tool Registry | 待全链验收 |
| BIZ-003 | 受控 HTTP 工单 API→测试→发布→Agent 调用 | 固定目标与映射、无任意代理、返回截断与脱敏 | 待全链验收 |
| BIZ-004 | 本地 PDF/DOCX→后端上传→解析→索引→检索 | tenant/KB/index/document ACL、引用 chunk 可追溯 | 待全链验收 |
| BIZ-005 | RAGFlow 连接→发现 3 个 Dataset→分别发布 Knowledge | 一个 Dataset 一个 Resource、分别授权、模型不可见 Dataset ID | 待真实 RAGFlow 环境 |
| BIZ-006 | Remote HTTP Knowledge→Mapping→检索→Agent 使用 | 仅暴露 query/top_k、固定 knowledge ID、响应规范化 | 接入/测试/发布自动化通过；待真实 API Run |
| BIZ-007 | Agent 组装与发布 | Model/Prompt/Skill/Tool/Knowledge/Memory、发布校验、Revision 回滚 | 待 Iteration O/P |
| BIZ-008 | RuoYi 权限矩阵 | Deployment VIEW/RUN 与 Resource USE 分离，用户/角色/部门生效 | 运行时矩阵自动化通过；待真实账号矩阵 |
| BIZ-009 | Run Trace | 可读 Timeline、权限裁剪、工具/RAG/Memory 实际调用、原始事件可展开 | 策略与前端构建通过；待真实组合 Run |
| BIZ-010 | 生命周期与影响分析 | 使用中禁止物理删除、归档/弃用、Health/Drift/Impact | Health/Impact 已实现；待真实数据与低频检查 |

## 7. 安全与中文显示通用断言

- 所有 API、Trace、审计、日志和前端状态不得返回 API Key、Vault 密文、Authorization、Cookie 或用户上传原文。
- 所有租户资源、快照、Grant、Run、Memory、文档与索引必须同时经过应用鉴权和 PostgreSQL RLS。
- Console 源文件、HTML 和 API 均使用 UTF-8；构建产物页面必须显示简体中文，不允许出现 `????` 或 mojibake。
- 浏览器验证码必须使用后端返回的 `data:image/...;base64` URL；验证码加载失败不得退回 `dev-ticket`。
