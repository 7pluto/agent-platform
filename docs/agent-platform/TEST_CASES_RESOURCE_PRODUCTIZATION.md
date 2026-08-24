# 资源产品化补充验收案例

本文补充 MCP 单工具治理与 Skill 产品化发布的可重复验收步骤。它与 `TEST_CASES_V1_5.md` 一起维护，不替代最终真实业务组合运行验收。

## MCP-REGISTER-001：发现结果按单个工具发布并授权

前置条件：已发布一个 MCP Connection，上游至少返回两个工具；准备两个权限范围不同的 RuoYi 测试主体。

步骤：

1. 在连接详情执行实时发现，确认每个工具显示“可注册、已管理、定义已变化或已移除”。
2. 只勾选其中一个工具，填写业务名称、用途、风险级别和只读属性。
3. 为该工具单独选择 RuoYi 用户、角色或部门范围并批量发布。
4. 使用有权限和无权限的账号分别打开同一个 Agent，并检查能力摘要与运行时 Tool Registry。

预期：

- 发现结果不能直接作为 Agent 能力；每个选中工具生成独立、不可变的 Tool Version。
- 未选择工具不发布；工具权限可与 MCP Connection 权限分开治理。
- 无 `USE` 权限的工具名称、Schema、版本 ID 和连接信息均不进入模型上下文。
- 其他已授权能力仍正常运行。

当前证据：后端发现与批量注册测试通过，Console 单工具卡片选择与独立授权类型检查通过。自动化入口为 `tests/test_mcp.py`；真实 MCP 业务运行纳入 `BIZ-002`。

## SKILL-PUBLISH-001：Skill 依赖与业务样例受控发布

前置条件：当前租户存在已发布且当前管理员可使用的 Tool 或 Knowledge Version。

步骤：

1. 新增 Skill，填写带一级标题的 `SKILL.md`、适用/不适用场景和至少一个业务测试样例。
2. 通过依赖卡片选择 Tool/Knowledge，不手填版本 ID。
3. 配置 RuoYi 可用范围并发布。
4. 在 Skill 详情确认依赖名称、版本、测试数量和授权范围。

预期：

- 依赖必须已发布、租户一致且类型正确。
- 无标题的 `SKILL.md`、重复依赖或空业务样例均拒绝发布。
- 发布响应、详情、Trace 和审计不返回未脱敏配置。
- Skill 的 `USE` 不自动授予其依赖资源的 `USE`。

当前证据：自动化通过，入口为 `tests/test_skill_product.py`。

## BIZ-PROTOCOL-001：Dify 真实协议发现与调用

步骤：使用固定 App Key 访问演示 Dify `/parameters`，再以 Chatflow blocking 模式提交“员工考勤管理办法”。

预期：参数变量 `query` 被自动发现；调用返回业务回答、会话标识和 RAG 引用；Key 只出现在 Authorization Header，不进入请求体、响应或 Trace。

当前证据：`tests/test_demo_enterprise_services.py` 与 `tests/test_demo_provider_adapters.py::test_dify_adapter_runs_real_demo_protocol` 自动化通过。

## BIZ-PROTOCOL-002：RAGFlow 三数据集发现与固定数据集检索

步骤：发现人事、财务、客服三个 Dataset；选择人事 Dataset 注册 Knowledge；提交“考勤异常怎么处理”。

预期：一个 Dataset 对应一个 Knowledge；检索请求的 Dataset ID 来自已发布配置，模型只能传 `query/top_k`；结果归一化为 Knowledge Hit 并保留文档来源。

当前证据：`tests/test_demo_enterprise_services.py` 与 `tests/test_demo_provider_adapters.py::test_ragflow_and_remote_knowledge_adapters_run_real_demo_protocol` 自动化通过。

## BIZ-PROTOCOL-003：MCP 多工具发现、独立调用与授权边界

步骤：对 CRM MCP 执行 `tools/list`，分别调用“查询客户”和“查询最近订单”。

预期：发现两个独立 Schema；每个工具可单独注册与授权；调用结果为 UTF-8 中文业务数据；未授权工具不进入模型 Tool Registry。

当前证据：`tests/test_demo_provider_adapters.py::test_mcp_adapter_discovers_and_invokes_independently_governable_tools` 与 `tests/test_permission_matrix.py` 自动化通过。

## BIZ-RUNTIME-001：组合 Agent 自主选择能力并生成最终回答

固定 Agent 能力：企业 Skill、长期 Memory、CRM MCP、RAGFlow 人事知识库、受控工单 HTTP Tool、Dify 企业流程，以及一个当前账号未授权的能力。

测试问题与预期：

| 问题 | 实际应选能力 | 关键 Trace |
|---|---|---|
| 查询客户信息 | `query_customer` | `tool.started/completed` |
| 员工考勤管理办法 | `knowledge_search_hr` | `rag.retrieved` |
| 查询工单处理状态 | `ticket_query` | `tool.started/completed` |
| 使用 Dify 流程查询制度 | `dify_enterprise_flow` | `dify.flow.completed` |

共同预期：Memory 每次固定加载一条；Skill 在模型前加载；模型只调用一个与问题匹配的已授权能力；受限能力只计入过滤数量，名称和 Schema 不暴露；工具结果返回模型后生成中文最终回答。

当前证据：`tests/test_business_agent_runtime.py` 四个参数化业务场景自动化通过。Compose 中的真实 API、Worker、PostgreSQL/RLS、Redis、MinIO 容器级闭环仍是部署前最终门禁。

## PROVIDER-DRAFT-001：外部连接失败保留 Draft

覆盖 Model、Dify、MCP 与 RAGFlow。

步骤：分别提交错误 Key、不可用地址或上游错误；在能力/连接详情查看版本与验证记录；修复连接后重新测试、验证并发布。

预期：

- 首次失败返回稳定错误码，密钥值不出现在响应、验证记录或审计中。
- Definition 与不可执行 Draft Version 被保留，Published 目录和 Agent Builder 不出现该版本。
- MCP/RAGFlow 即使直接调用发布 API，也因缺少成功 Validate 返回 `RESOURCE_VALIDATION_REQUIRED`。
- 修复后 Test 和 Validate 都生成新记录；只有 Validate 成功后才允许发布，原失败记录不被覆盖。

当前证据：`tests/test_dify_product_draft.py` 与 `tests/test_provider_draft_gates.py` 自动化通过；资源详情的版本卡片已显示最新验证结果和恢复入口。

## UI-PERMISSION-001：RuoYi 可用范围卡片

检查资源发布、MCP 单工具发布和 Agent Revision 发布三个入口。

预期：均使用同一个“仅发布人 / 指定部门 / 指定用户角色部门”卡片组件；主体以业务名称为主、外部 ID 为辅；正式流程中不存在多选下拉；选择结果仍提交稳定的 `USER/ROLE/DEPT + external_id`，不复制 RuoYi 用户表。

当前证据：Vue 类型检查通过，`agent-console/src` 多选下拉与乱码模式扫描均无命中。

## HTTP-TOOL-PRODUCT-001：受控业务 API 产品化

步骤：通过统一资源向导配置固定 Endpoint、GET/POST/PUT/PATCH、固定 Path 或 `{{path_parameter}}`、输入 Schema、Query/Body 模板、固定业务 Header、固定字段响应映射、超时、测试参数和 RuoYi 可用范围。

预期：

- Path 参数只能替换一个安全编码后的路径段；`C/001` 编码为 `C%2F001`，不能通过 `..` 或 URL 片段改变主机和路径边界。
- Header 模板只接受字符串值，拒绝 Authorization、Cookie、Host、Proxy 和 Forwarded 等敏感 Header；认证只能由 Vault 注入。
- 响应映射只支持固定点路径和字段映射，不执行 Python、Shell、JavaScript 或表达式。
- 真实调用测试成功后才发布；业务语义、版本、Descriptor 和 RuoYi Grant 由一个后端命令完成。
- Trace 与模型观察结果经过 ObservationPolicy，不记录原始凭据或无限响应体。

当前证据：`tests/test_http_tool.py`、`tests/test_product_governance.py::test_http_tool_product_api_tests_and_creates_ruoyi_grant` 自动化通过。

## SECRET-GOVERNANCE-001：稳定 Secret 引用轮换与停用

步骤：管理员在“系统连接 → 凭据保险箱”查看凭据，输入新值执行轮换，再执行停用；检查 API 响应、审计和资源详情。

预期：

- 页面只显示名称、状态、短指纹、最后使用/轮换时间和创建人，不显示 Key、密文或 `secret_ref`。
- 轮换保持同一个内部引用，更新密文和指纹，不要求 Dify/MCP/RAGFlow/HTTP Knowledge 重新发布版本。
- 停用后 Provider 解析返回稳定错误，Agent 发布预检和运行不得继续调用该凭据。
- 轮换请求中的新 Key 不进入响应、审计数据或日志。

当前证据：`tests/test_api_security.py::test_secret_rotation_and_disable_never_return_or_audit_secret_value` 自动化通过；Console 轮换/停用界面通过类型检查与生产构建。
