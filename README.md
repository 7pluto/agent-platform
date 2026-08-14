# Enterprise Agent Platform

第一阶段实现已建立独立Console和FastAPI最小纵向链路：

```text
Mock/RuoYi IAM -> BFF Session -> TenantContext -> Run/Thread -> SSE Events
```

## 本地启动

### Python API

```powershell
cd agent-server
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e .
$env:AGENT_APP_ENV='dev'
$env:AGENT_IAM_MODE='mock'
uvicorn app.main:app --reload --port 8000
```

开发Ticket固定为 `dev-ticket`。

### Console

```powershell
cd agent-console
npm install
npm run dev
```

访问 `http://localhost:5173`，使用 `dev-ticket`建立开发会话。

### Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## 当前实现边界

- `MockIamProvider`用于dev/test；生产环境拒绝Mock Provider。
- `RuoYiIamProvider`已按冻结的L1接口实现Ticket、当前用户、用户/部门目录调用。
- Session Store支持内存与Redis；Compose 默认启用 Redis，Token仍只以Fernet密文存储在服务端。
- PostgreSQL核心表、Alembic迁移和RLS上下文边界已建立；Compose 默认使用 PostgresRunStore 与 RedisSessionStore。
- Compose使用PostgreSQL Run Store：同一Thread单一Active Run、PENDING排队、取消与事件序列规则均持久化。
- API只创建Run；独立Worker领取最小调度记录后进入租户事务执行。LangGraph、Qwen兼容模型、MinIO、pgvector、MCP演示服务与长期Memory均已有Stage 4基础实现。

## Stage 1 Runtime边界

- Run创建时生成不可变、可哈希且不含Secret明文的 `ExecutionManifest`。
- `RuntimeAdapter`、`RuntimeExecutor`、`MockRuntimeAdapter`和`LangGraphBaselineAdapter`已建立；Compose 默认使用 LangGraph 基线。
- `GET /api/v1/runs/{run_id}/manifest`提供Manifest读取接口。
- 开源复用按LangGraph基线 -> DeerFlow -> DeepAgents串行评估，见 `docs/agent-platform/OPEN_SOURCE_REUSE.md`。

PostgreSQL/RLS边界见 `docs/agent-platform/PERSISTENCE_RLS.md`；当前开发环境仍使用内存存储。

控制面与Run解析见 `docs/agent-platform/CONTROL_PLANE.md`。
授权与审计边界见 docs/agent-platform/GOVERNANCE.md。

实施决策见 `docs/agent-platform/`。
