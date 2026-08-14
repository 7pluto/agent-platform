# Enterprise Agent Platform V1 Implementation Plan

## 1. 目标与固定边界

建设独立于业务系统的企业智能体中台。完整V1包含：

- Agent Definition、Version、Deployment、Deployment Revision。
- Model、Prompt、Skill、Tool、MCP、Knowledge Base和Memory Policy。
- Resource Grant、Tenant Isolation和Audit。
- Conversation、Thread、Message、Run、Run Step、Run Event和Execution Manifest。
- 独立Console、Playground、Run详情、Trace和基础Eval。
- Compose、Kubernetes/Helm、迁移、备份恢复和运维文档。

固定原则：

- Python主动适配RuoYi；RuoYi不感知Agent Platform领域。
- 当前IAM结论为L1，Java零改造。
- Coding Agent不得修改RuoYi仓库。
- AI资源授权只存在于Agent Platform。
- Runtime通过 `RuntimeAdapter`隔离开源Harness。
- Tenant是硬边界，默认拒绝和Fail Closed。
- 每个Run绑定不可变Execution Manifest。

## 2. 代码与部署结构

```text
agent-platform/
├── agent-console/
├── agent-server/
│   └── app/
│       ├── api/
│       ├── control_plane/
│       ├── integrations/
│       │   ├── iam/
│       │   ├── model/
│       │   ├── mcp/
│       │   └── observability/
│       └── runtime/
│           ├── harness/
│           ├── resolver/
│           ├── manifest/
│           ├── executor/
│           ├── tools/
│           ├── rag/
│           └── memory/
├── migrations/
├── deploy/
└── docs/agent-platform/
```

技术栈：Vue 3/TypeScript/Vite/Pinia/Naive UI；Python 3.12/FastAPI/SQLAlchemy 2/Alembic/LangGraph；PostgreSQL/pgvector、Redis、MinIO、OpenTelemetry和Langfuse。

Python使用同一镜像运行：

- `api`：BFF、Control API、SSE和查询。
- `worker`：Run、Ingest和Eval固定任务类型。

不建设通用分布式任务平台。

## 3. IAM实施结论

IAM不再进入方案探索，直接执行：

```text
读取既有RuoYi扫描结果
-> 冻结L1接口
-> 真实Token契约验证
-> RuoYiIamProvider
-> MockIamProvider
-> BFF Session
-> TenantContext
```

权威文档：

- `RUOYI_INTEGRATION_DECISION.md`
- `IAM_INTEGRATION.md`
- `JAVA_CHANGE_REQUEST.md`

Java协作当前为关闭状态。若真实契约测试触发L2，Coding Agent只更新Java任务单和可选参考Patch，由Java负责人实施；Agent Platform继续使用Mock开发。

## 4. 开源复用的串行决策

Phase 0不得同时实现多个Harness。顺序固定为：

```text
1. LangGraph官方能力基线
2. DeerFlow Harness PoC
   - 通过：采用DeerFlow RuntimeAdapter，停止DeepAgents研究
   - 失败：记录硬门槛证据，进入步骤3
3. DeepAgents PoC
   - 通过：采用DeepAgents RuntimeAdapter
   - 失败：回退LangGraph轻量Harness
4. langchain-mcp-adapters PoC
```

Harness硬门槛：

- 可按Execution Manifest动态注入Model、Prompt、Skill和Tool。
- 不依赖其前端、账号、Sandbox、Browser、Shell、IM Gateway或复杂Sub-agent。
- 支持PostgreSQL Checkpoint、Thread恢复、Streaming和取消。
- 不使用跨租户进程全局状态。
- 平台API和数据库不暴露Harness私有Schema。
- 许可证、固定版本、SBOM和升级方式可接受。

输出 `OPEN_SOURCE_REUSE.md`，状态只能是 `DIRECT_REUSE/WRAP/REFERENCE_ONLY/NOT_USED`。

## 5. 领域和版本模型

核心生命周期：

```text
Agent Definition
-> Immutable Agent Version
-> Deployment
-> Immutable Deployment Revision
-> Execution Manifest
-> Run
```

- Definition和Draft可编辑。
- Published Version不可编辑。
- Deployment是稳定入口；每次修改生成Revision。
- 激活和回滚只切换Revision指针。
- Scalar Override采用替换；集合采用显式 `add/remove`。
- Model、Prompt、Skill、Tool及MCP配置必须有可追踪版本或修订。
- Knowledge Base通过Index Version构建并原子切换。

Skill定义Instructions、Tool依赖和Knowledge依赖，但不隐含任何权限。

Tool统一为：

- `NATIVE`
- `MCP`
- `RAG`

## 6. Execution Manifest可复现性

Manifest除资源和策略版本外，必须记录实际Runtime代码版本：

```json
{
  "schema_version": "1",
  "runtime": {
    "version": "1.0.0",
    "git_commit": "<commit>",
    "image_digest": "sha256:<digest>"
  },
  "builder": {
    "id": "react",
    "version": "1"
  },
  "harness": {
    "type": "deerflow|deepagents|langgraph",
    "version": "<locked-version>"
  }
}
```

完整Manifest还包含：

- Tenant、Run和Deployment Revision。
- 全部资源Version ID、规范化配置和内容Hash。
- Knowledge Index Version。
- Resource Grant/Tool Policy/Memory Policy版本。
- Native Tool实现版本。
- `secret_ref`，不包含Secret明文。
- Manifest自身Hash和生成时间。

CI构建时生成Runtime元数据并注入镜像；Worker只能使用自身真实版本生成Manifest，禁止由客户端提交。

## 7. Tenant、RLS与Worker

所有租户业务表启用应用层过滤和PostgreSQL RLS。API事务执行：

```sql
SET LOCAL app.tenant_id = '<trusted-tenant-id>';
SET LOCAL app.user_id = '<trusted-user-id>';
```

Worker不得持有 `BYPASSRLS`。数据库角色分为：

### `worker_scheduler`

- 只能读取最小跨租户Run Queue列。
- 只能执行原子领取操作。
- 可取得 `run_id、tenant_id、lease_until、attempt`。
- 无权读取Prompt、Message、Manifest、RAG或Memory正文。

### `worker_tenant`

领取后必须：

```text
关闭scheduler事务
-> 开启新tenant事务
-> SET LOCAL app.tenant_id
-> 根据run_id重新读取Run
-> ResourceResolver
-> Manifest
-> Runtime/RAG/Memory/MCP
```

数据库函数或受控存储过程完成跨租户领取，返回最小字段。后台维护任务使用独立受限角色，不复用API或Worker用户。

## 8. Thread并发与Run状态

V1硬性规定：

```text
同一个 thread_id 同时最多一个 Active Run。
```

Active执行状态仅为 `RUNNING/CANCEL_REQUESTED`。同一Thread可以存在多个 `PENDING` Run，但只能按创建顺序将其中一个提升为 `RUNNING`。

数据库保证方式：

- PostgreSQL部分唯一索引约束每个Thread在 `RUNNING/CANCEL_REQUESTED` 状态下最多一条Run，或使用等价的Thread Lease表；`PENDING` 不进入该唯一索引。
- Worker领取前持有Thread级事务锁。
- Run终态后释放Lease并唤醒下一个PENDING Run。
- 不同Thread可以并行。
- 取消PENDING Run不修改Checkpoint；取消RUNNING Run在安全边界协作式停止。

Run状态固定为：

```text
PENDING
RUNNING
COMPLETED
FAILED
CANCEL_REQUESTED
CANCELLED
```

终态事件只能写入一次。

## 9. Runtime、RAG与Memory

运行链路：

```text
鉴权/授权/幂等
-> 创建PENDING Run
-> Scheduler领取Run和Tenant
-> Tenant事务
-> ResourceResolver
-> Execution Manifest
-> RuntimeAdapter
-> LangGraph Checkpoint/Event
-> 唯一终态
```

- 自动重试只适用于只读或明确幂等Tool。
- 写Tool结果不确定时不得自动重放。
- MCP使用 `langchain-mcp-adapters`；Streamable HTTP为租户默认传输。
- stdio只允许平台固定白名单，用户不能提交命令和参数。
- RAG在SQL/Vector查询阶段加入Tenant、KB和ACL过滤。
- Memory命名空间为 `(tenant_id, deployment_id, user_id)`。
- 不支持跨用户长期Memory。

## 10. API与Console

主要运行API：

```text
POST /api/v1/deployments/{deployment_id}/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/events
POST /api/v1/runs/{run_id}/cancel
```

- Run创建要求 `Idempotency-Key`并返回202。
- SSE支持 `Last-Event-ID`恢复。
- 网络断开不自动取消Run。
- 事件包含Schema Version、Event ID、Sequence、Run/Thread/Trace ID和Data。

Console包含：

- Agent Definition、Version、Deployment和Revision。
- Model、Prompt、Skill、Tool、MCP和Knowledge。
- Resource Grant和IAM Subject选择。
- Playground。
- Conversation、Run列表和Run详情。
- Response、Events、Tools、RAG、Memory、Manifest和Trace页签。

## 11. 实施顺序

### Stage 0：冻结外部契约

1. 读取既有RuoYi扫描结果。
2. 维护 `RUOYI_INTEGRATION_DECISION.md`。
3. 关闭或更新 `JAVA_CHANGE_REQUEST.md`。
4. 冻结 `IAM_INTEGRATION.md`。
5. 实现MockIamProvider。

### Stage 1：Runtime技术选型

6. LangGraph基线PoC。
7. DeerFlow PoC；仅失败后执行DeepAgents PoC。
8. MCP Adapter PoC。
9. 输出 `OPEN_SOURCE_REUSE.md`和Runtime ADR。

### Stage 2：安全最小纵向链路

10. 建立Alembic、核心数据库和RLS。
11. 实现BFF Session、RuoYiIamProvider、TenantContext。
12. 实现Worker Scheduler/Tenant双角色。
13. 实现Model、Prompt、REACT Agent、Deployment、Resolver和Manifest。
14. 实现Thread单Active Run、Checkpoint、SSE和基础Playground。

### Stage 3：企业治理

15. Version、Deployment Revision、发布、激活和回滚。
16. Resource Grant、Audit及完整资源管理Console。
17. ROUTER和服务端注册CUSTOM Builder。

### Stage 4：扩展能力

18. Skill、Native Tool、Tool Policy和MCP。
19. File、MinIO、Ingest Job、pgvector RAG和Index Version。
20. Short-term Checkpoint和User Long-term Memory。

### Stage 5：运行治理与交付

21. 完整Run Detail、OTel、Langfuse和基础Eval。
22. Compose、Helm、迁移Job、备份恢复和安全加固。
23. DEV -> TEST -> UAT -> PROD验收。

每个Stage必须同时交付迁移、API、Console、权限、审计、测试和观测，不允许形成纯后端大阶段。

## 12. 测试与发布门槛

### IAM

- Java仓库Git Diff为空。
- 无Java数据库迁移。
- 有效、过期、注销、禁用和伪造Token行为正确。
- Browser中不存在RuoYi Token。
- IAM失败时无任何身份或工具降级。

### Tenant/RLS

- Tenant A无法读取或写入Tenant B的任意资源。
- Scheduler只能看到队列最小字段。
- Worker Tenant事务无法跨Tenant读取Manifest、RAG和Memory。
- Worker数据库Role不具有 `BYPASSRLS`。

### Runtime

- 同一Thread不会同时运行两个Run。
- 两个Worker竞争同一Thread时只有一个成功领取。
- Worker崩溃后Lease和Checkpoint可安全恢复。
- Manifest包含资源和Runtime代码版本，Hash稳定。
- Published Version不可修改，历史Revision可回滚。

### Security

- Skill依赖越权在模型调用前失败。
- MCP SSRF、恶意Redirect和stdio命令注入失败。
- 跨租户RAG和Memory结果为零。
- Secret不出现在API、日志、事件、Manifest、Trace和镜像。

### 交付

- Compose一条命令启动演示环境。
- 两个API、两个Worker副本滚动重启不丢失Thread、Run和Event。
- Mock模型下支持50个并发活跃Run。
- 所有Critical/High安全问题关闭或有正式豁免。

## 13. V1不包含

- 旧智能体广场数据或接口迁移。
- RuoYi Agent菜单、AI表或Java Runtime。
- A2A和复杂自主多智能体。
- 可视化图编排。
- 用户代码、Sandbox、Browser/Code Agent。
- 复杂HITL和审批引擎。
- GraphRAG、自动模型路由和计费。
- 通用分布式任务平台。
- 跨用户共享Memory。
