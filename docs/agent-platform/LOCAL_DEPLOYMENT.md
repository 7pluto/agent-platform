# Non-Docker Deployment and Verification

Docker/Compose is optional and is not required for local development, test, or deployment acceptance. Start the services natively on Windows or Linux with the supplied scripts.

## Development (memory mode)

```powershell
.\scripts\start-api.ps1
.\scripts\start-console.ps1
```

The API starts on port 8000 and the Console on port 5173. Development uses mock IAM and in-memory storage by default.

## External infrastructure mode

Use an externally provisioned PostgreSQL and Redis instance; Docker is not part of this path. Set `AGENT_DATABASE_URL`, `AGENT_REDIS_URL`, and `AGENT_SESSION_ENCRYPTION_KEY`, then run migrations and start the API:

```powershell
cd agent-server
$env:AGENT_STORAGE_MODE='postgres'
$env:AGENT_SESSION_STORAGE_MODE='redis'
$env:AGENT_DATABASE_URL='postgresql+asyncpg://...'
$env:AGENT_REDIS_URL='redis://...'
alembic upgrade head
..\scripts\start-api.ps1 -Storage postgres -SessionStorage redis -Iam ruoyi -Environment prod
```

Production additionally requires RuoYi endpoint settings and a real session encryption key. The current production validator keeps the in-process runtime disabled until a separate worker is implemented.

## Regression

```powershell
.\scripts\test.ps1
```

This performs Ruff, pytest, offline Alembic SQL generation, and the Console production build without Docker.