# PostgreSQL / RLS Persistence Boundary

## Current status

The server still defaults to `AGENT_STORAGE_MODE=memory` for direct local development and tests. `docker compose up --build` explicitly enables PostgreSQL Run storage and Redis BFF sessions after the migration Job completes.

Production safety requires `AGENT_STORAGE_MODE=postgres`. The production image leaves this variable unset intentionally until the PostgreSQL Run repository and Redis Session repository are both approved for deployment; this prevents a partially durable API from being mistaken for a fully durable deployment. The image already carries `alembic` and the migration directory so deployment can run `alembic upgrade head` before starting API/worker processes.

## Migration

```powershell
cd agent-server
$env:AGENT_DATABASE_URL='postgresql+asyncpg://agent:<password>@postgres:5432/agent_platform'
alembic upgrade head
```

Migration head `0005_active_thread_tenant_index` includes tenant, Run, Run Event, idempotency, Thread Lease, control-plane, governance, and audit tables. `0002` backfills event thread identity for databases that already applied `0001_core`; `0005` scopes the partial active-Run uniqueness index to `(tenant_id, thread_id)`. Thus one tenant Thread can have at most one `RUNNING` or `CANCEL_REQUESTED` Run, while independent tenants cannot constrain one another. `PENDING` Runs remain queueable.

## Tenant context

Every tenant transaction must call `set_local_tenant_context(session, tenant_id, user_id)`, which uses transaction-local `set_config`. Policies fail closed when `app.tenant_id` is absent. Tables are both RLS-enabled and `FORCE ROW LEVEL SECURITY` enabled.

The scheduler/worker split remains a deployment concern: the scheduler may only claim minimal queue columns, then a tenant-scoped transaction rereads the Run, Manifest, and resources. No worker role may have `BYPASSRLS`.

## Not yet switched

`PostgresRunStore` is selected when `AGENT_STORAGE_MODE=postgres`; `RedisSessionStore` is selected when `AGENT_SESSION_STORAGE_MODE=redis`. Both are enabled in Compose. The remaining verification gap is a real PostgreSQL/Redis service integration test, because Docker is not available in the current workstation environment.