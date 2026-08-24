# Enterprise Agent Platform V1.5 测试执行报告（2026-08-24）

## 1. 执行结论

本轮完成后端全量回归、前端类型检查、生产构建、源码/产物 UTF-8 检查，以及本地生产 Bundle 的浏览器逐页验收。自动化基线为 **126 passed**；前端生产构建成功；登录、导航、资源卡片向导、中文创建智能体、Agent Builder、运行治理、Secret 治理与权限矩阵均通过自动化或浏览器验证。

Docker 未安装在当前工作站，因此 PostgreSQL + pgvector、Redis、MinIO、独立 Worker 和全部 Demo Provider 的 Compose 组合脚本已经固化，但本轮不能把“脚本已存在”写成“全栈已通过”。它是后续服务器部署前的强制 Gate。

## 2. 测试环境

- 操作系统：Windows 10，中文路径工作区 `D:\移动工作\Agent Platform`。
- Python：CPython 3.12；后端测试使用 FastAPI TestClient 与真实 Provider Adapter 边界。
- Console：Vue 3、TypeScript、Vite 生产 Bundle。
- 浏览器：Codex 内置浏览器，访问本地生产 `dist`；`scripts/serve_console_acceptance.py` 只负责静态 SPA fallback 和 `/api` 反代。
- 本地浏览器 API：内存存储、Mock IAM、Ticket 登录、非 Secure 测试 Cookie。生产仍固定 PostgreSQL、Redis、RuoYi 密码/验证码和 HTTPS `__Host-` Cookie。

## 3. 自动化执行与结果

### 后端全量

执行：`D:\agent-platform-test-venv\Scripts\python.exe -m pytest agent-server/tests -q`

结果：`126 passed, 2 warnings in 10.04s`。告警分别来自 Starlette TestClient 的上游弃用提示，以及中文工作区下 pytest cache 目录的写权限；均不是应用失败，也没有跳过案例。

新增重点覆盖：

- 外部 Model、Dify、MCP、RAGFlow 失败后保留安全 Draft，重测、Validate、Publish Gate。
- Dify、RAGFlow、Remote Knowledge、MCP 的真实协议 Adapter 与业务响应。
- CRM、工单、Dify、三类 Knowledge 的自主能力选择及最终回答。
- Skill 与长期 Memory 固定加载，未授权能力在模型 Registry 前过滤。
- 同一 Agent 的长沙与财务两个 RuoYi 用户获得不同的 Dify、MCP 单工具、MCP Connection、HTTP Tool 和 Knowledge Registry；无权限资源的名称、Schema、外部 ID 与版本 ID 均不泄漏。
- 资源产品命令在发布时原子写入业务语义、不可变版本和 RuoYi 用户/角色/部门 Grant；非法发布范围在任何资源写入前拒绝。
- Secret 稳定引用支持轮换与停用；响应和审计只保留短指纹与状态，不返回 Key、密文或 `secret_ref`。
- 受控 HTTP Tool 支持 GET/POST/PUT/PATCH、安全 Path 参数、固定 Header 和固定字段响应映射，并拒绝 Authorization、Cookie、Host 与代理/转发 Header。
- 会话历史排除当前 Run 重复消息，最近 20 条/40,000 字符进入模型；长期 Memory 显式新增、消息保存与删除保持 Deployment + RuoYi 用户隔离。
- PDF/DOCX 文件签名验证、真实解析、中文内容与 chunk 保真；伪造 DOCX 拒绝。
- Grant 新增、撤销、跨租户不可撤销及撤销审计。
- 中文 Deployment 业务名称优先展示，技术 Slug 不暴露为主名称。

### Console

- `npx vue-tsc --noEmit`：通过。
- `npm run build`：通过，71 modules transformed。
- Bundle：`dist/assets/index-C90XfV0F.js` 289.38 kB，`index-BKVv2OCI.css` 47.55 kB。
- `scripts/check_frontend_utf8.py agent-console/src agent-console/dist`：通过。
- `<select multiple>`、Unicode replacement character 和常见中文 mojibake 扫描：无命中。

## 4. 浏览器验收案例

### BROWSER-001：登录与会话

步骤：加载生产 Bundle，使用 `dev-ticket` 交换本地测试会话；进入管理控制台；刷新 `/console/governance`。

结果：通过。登录页、侧边栏、概览均为正常简体中文；Mock IAM 自动显示 Ticket，真实 RuoYi 模式仍显示用户名、密码和验证码；刷新后会话有效，没有 `Agent Platform session is required`。本地 HTTP 必须使用普通测试 Cookie 名；生产 HTTPS 继续使用 `__Host-ap_session`。

### BROWSER-002：一级页面与 Router URL

逐一点击并核对：

| 页面 | URL | 主标题 |
|---|---|---|
| 智能体管理 | `/console/agents` | 智能体管理 |
| 能力中心 | `/console/capabilities` | 能力中心 |
| 系统连接 | `/console/connections` | 系统连接 |
| 知识库运营 | `/console/knowledge` | 知识库 |
| 运行治理 | `/console/runs` | 运行治理 |
| 权限与审计 | `/console/governance` | 权限与审计 |

结果：全部通过；没有 422 占位页或乱码。

### BROWSER-003：资源接入 Wizard

步骤：能力中心点击“入驻新资源”，选择“发布 Dify 应用”，进入连接与测试。

结果：通过。弹窗以卡片选择能力/外部应用/连接器；四步流程显示“选择来源、连接与测试、能力信息与权限、发布复核”；Dify 页面展示 Base URL、Chatflow/Workflow、Tool Name、一次性 App API Key、业务线、对象、场景、涉及数据、开场白和建议问题。页面明确 Key 只进入后端 Vault。

### BROWSER-006：生产 Bundle 中文与直接路由复验

步骤：以全新浏览器标签直接打开 `/console/capabilities`，等待会话恢复和并行目录加载；打开资源入驻向导并检查卡片、步骤条、按钮和中文说明；读取浏览器 error/warn 日志。

结果：通过。直接 URL 保持不变，主标题为“能力中心”，页面和弹窗无 `????`、替换字符或 mojibake，新标签控制台没有 error/warn。

### BROWSER-007：页面拆分后的会话与 Trace

步骤：从智能体广场打开一个未配置 Memory Policy 的测试智能体，确认会话自动创建；发送“请回复组件验收成功”，等待 Run 完成并检查 Trace 与最终回答。

结果：通过。页面显示“该智能体未启用长期记忆”，不会再请求 Memory API；Run 完成后 Trace 自动收起，标题显示耗时、工具/RAG/Memory 计数，最终回答固定在 Trace 下方。浏览器控制台没有 error/warn。该回归同时验证了独立 `ChatWorkspacePage`、`CapabilityListPage`、`CapabilityDetailPage` 与 `ResourceOnboardingWizard` 拆分后的生产 Bundle。

### BROWSER-004：中文智能体创建与 Builder

数据：智能体“浏览器验收智能体”，部署“浏览器验收-开发”。

结果：第一次浏览器测试发现中文部署名被直接当技术标识而返回 422；修复后复测通过。列表显示中文业务部署名，编辑 URL 稳定，进入唯一三栏 Builder，包含可用范围卡片、能力搜索/Provider/风险筛选、当前配置和预检/发布操作。

### BROWSER-005：权限新增与业务名称

数据：目标“浏览器验收智能体”，主体“Demo Department”，动作 VIEW/RUN。

结果：通过。选择 Deployment 后动作自动收敛为“查看、运行智能体”；保存后授权卡片主标题为业务名称，部门显示 Demo Department，不以 UUID 为主内容。页面显示授权 1、审计 7。

撤销按钮弹出了浏览器原生确认；浏览器控制层未能代替用户确认该弹窗，因此没有把此 UI 动作标为通过。DELETE API、租户隔离、列表清除和 `resource_grant.delete` 审计已由自动化案例完整通过。

## 5. 全栈业务组合 Gate

脚本：`scripts/accept_business_stack.py`。

它只调用公开 API，并创建唯一后缀数据：

1. OpenAI-compatible Tool Calling 模型与 1024 维 Embedding 模型。
2. Prompt、显式 Memory Policy。
3. Dify Chatflow Tool，真实参数发现、调用和 RAG 引用。
4. CRM MCP Connection，发现并注册 `query_customer` 与 `list_customer_orders` 两个独立 Tool。
5. 受控 HTTP 工单 Tool。
6. Local Knowledge：后端接收一个 PDF 和一个含中文考勤规定的 DOCX，Worker 构建 pgvector Index。
7. RAGFlow Connection：发现人事、财务、客服三个 Dataset，并固定注册人事 Knowledge。
8. Remote HTTP Knowledge：固定 `knowledge_id=enterprise-hr` 和响应 Mapping。
9. Skill：绑定 CRM、工单、本地与 RAGFlow Knowledge，并编译业务测试案例。
10. Agent/Deployment/Revision：组装上述资源、发布预检、激活。
11. 创建一条显式长期 Memory，并在每个 Run 断言 `memory.read count=1`。
12. 独立会话执行 6 个问题：CRM、本地 Knowledge、RAGFlow、企业知识 API、HTTP 工单、Dify。
13. 在同一 Conversation 连续执行“项目代号是星河”与“项目代号是什么”，断言第二个 Run 加载两条历史消息并回答“星河”；新会话不得继承该会话历史。

每个 Run 必须断言：状态 COMPLETED；实际 Tool 与问题对应；事件类型存在；Memory 固定加载；输出为简体中文最终回答；Run Detail 不含 `demo-provider-key`。连续对话还必须断言历史消息不重复写入且 `conversation.history.loaded` 数量正确。

服务器执行结果：`PASSED`。目标为 4 核 4G Ubuntu 24.04 单机，Docker Compose 2.40.3；PostgreSQL/pgvector、Redis、MinIO、API、单 Worker、Console、CRM MCP 和 Enterprise Demo 服务全部通过健康检查。完整安全报告保存在服务器：`/home/ubuntu/agent-platform-releases/9a7b77e/test-artifacts/business-stack-20260824.json`。

实际验收证据：

- MCP 发现 `query_customer`、`list_customer_orders`，Run `63bd1335-f89e-46f1-994d-8dd397859fb6` 实际调用 `query_customer`。
- Local Knowledge 上传 PDF 与中文 DOCX，检索命中 2 条；Run `5d036360-f77a-4b00-9b54-65d72abd70bd` 实际调用对应 `knowledge_search`。
- RAGFlow 发现“人事制度库、财务制度库、客服知识库”三个 Dataset；Run `022a28e4-c449-4004-9fdc-549784ff664d` 返回人事制度检索结果。
- Remote HTTP Knowledge Run `8a9dabcc-43ba-4b62-8b79-2fbf901d6065`、HTTP 工单 Run `bdb4183d-2b6a-429c-b3af-ef1d7619bbbf`、Dify Flow Run `483cece6-50d7-4df1-9b91-fa77b7614dab` 均实际调用并完成。
- 每个 Run 均加载长期 Memory 1 条；同一 Conversation 第二个 Run 加载 2 条历史消息并回答“当前会话中的项目代号是星河。”
- 运行详情未出现演示 Provider Key；验收 API/Worker/Provider 日志未发现 Traceback、Exception、Critical 或 Secret Leak。
- 验收容器执行完已停止，独立数据卷和 4.3KB JSON 报告保留；生产数据库、Redis 与 MinIO 数据卷未被替换。

## 6. 服务器部署结果与剩余外部 Gate

- 已完成迁移前 PostgreSQL 备份：`/home/ubuntu/agent-platform/backups/pre-9a7b77e-20260824-1114.dump`；旧代码目录和 Compose 配置保持可回退。
- 已部署提交批次到 `/home/ubuntu/agent-platform-releases/9a7b77e`，生产 API、Worker、Console、PostgreSQL、Redis、MinIO、CRM MCP 与 Enterprise Demo 均 healthy。
- 已通过服务器完整组合 Gate；本地后端全量为 `126 passed`，Console 为 `71 modules transformed`，UTF-8 扫描通过。
- IP 验收入口为 `http://106.53.3.169:5173/`；页面、同源 `/api/v1/healthz` 与真实 RuoYi Captcha 接口均返回 200。HTTP 会话仅通过 `deploy/agent-platform-ip/docker-compose.ip.yml` 显式启用，正式 RuoYi HTTPS 配置仍固定 `__Host-` Secure Cookie。
- 公网 80/TCP 可达并由 Caddy跳转 HTTPS；服务器本机 HTTPS 返回 200，但外部 443/TCP 被腾讯云入口重置且 Caddy 未收到请求。需要在轻量服务器防火墙确认 443/TCP 规则后，才能恢复域名浏览器验收。
- 真实 RuoYi 双用户/部门的授权矩阵已由自动化覆盖；若要求对生产现存账号做人工 UI 取证，需要用户在验证码页面完成一次登录。
- 用户真实 RAGFlow 仍需提供可访问的 Endpoint 与一次性 API Key；当前 V1.5 已以协议真实的内置三 Dataset 服务完成 Provider、权限、漂移与 Runtime Gate。
