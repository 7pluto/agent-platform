# Enterprise Agent Platform V1.5 测试案例与验收记录

本文档是持续维护的验收基线。每个案例必须保留测试数据、操作步骤、预期结果和证据；未执行的案例不得标记为通过。

## 1. 当前自动化基线

执行日期：2026-08-24

| 范围 | 执行方式 | 结果 | 证据 |
|---|---|---|---|
| 后端全量单元与集成测试 | `py -3.12 -m pytest -q` | 82 passed | pytest 终端结果；仅有 Windows pytest cache 目录权限告警 |
| Python 语法与模块编译 | `py -3.12 -m compileall -q app tests migrations` | 通过 | 无编译错误 |
| Console TypeScript | `npx vue-tsc --noEmit` | 通过 | 无类型错误 |
| Console 生产构建 | `npm run build` | 通过 | Vite 生成 `dist`，JS/CSS bundle 正常 |

## 2. Discovery Snapshot 与 Drift

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

## 3. 最终业务验收矩阵

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

以下案例是 V1.5 完成门槛，后续迭代继续在本文档补充步骤与证据：

| 编号 | 业务链路 | 核心验收点 | 当前状态 |
|---|---|---|---|
| BIZ-001 | Dify 连接→发现→测试→发布→Agent 调用 | 参数自动发现、凭据 Vault、Resource USE 裁剪、真实回答 | 待全链验收 |
| BIZ-002 | CRM MCP 连接→发现 Tool→批量注册→Agent 调用 | 单 Tool 独立授权、未授权 Tool 不进入模型 Tool Registry | 待全链验收 |
| BIZ-003 | 受控 HTTP 工单 API→测试→发布→Agent 调用 | 固定目标与映射、无任意代理、返回截断与脱敏 | 待全链验收 |
| BIZ-004 | 本地 PDF/DOCX→后端上传→解析→索引→检索 | tenant/KB/index/document ACL、引用 chunk 可追溯 | 待全链验收 |
| BIZ-005 | RAGFlow 连接→发现 3 个 Dataset→分别发布 Knowledge | 一个 Dataset 一个 Resource、分别授权、模型不可见 Dataset ID | 待真实 RAGFlow 环境 |
| BIZ-006 | Remote HTTP Knowledge→Mapping→检索→Agent 使用 | 仅暴露 query/top_k、固定 knowledge ID、响应规范化 | 待全链验收 |
| BIZ-007 | Agent 组装与发布 | Model/Prompt/Skill/Tool/Knowledge/Memory、发布校验、Revision 回滚 | 待 Iteration O/P |
| BIZ-008 | RuoYi 权限矩阵 | Deployment VIEW/RUN 与 Resource USE 分离，用户/角色/部门生效 | 待 Iteration Q 全矩阵 |
| BIZ-009 | Run Trace | 可读 Timeline、权限裁剪、工具/RAG/Memory 实际调用、原始事件可展开 | 待 Iteration R |
| BIZ-010 | 生命周期与影响分析 | 使用中禁止物理删除、归档/弃用、Health/Drift/Impact | 待 Iteration S |

## 4. 安全与中文显示通用断言

- 所有 API、Trace、审计、日志和前端状态不得返回 API Key、Vault 密文、Authorization、Cookie 或用户上传原文。
- 所有租户资源、快照、Grant、Run、Memory、文档与索引必须同时经过应用鉴权和 PostgreSQL RLS。
- Console 源文件、HTML 和 API 均使用 UTF-8；构建产物页面必须显示简体中文，不允许出现 `????` 或 mojibake。
- 浏览器验证码必须使用后端返回的 `data:image/...;base64` URL；验证码加载失败不得退回 `dev-ticket`。
