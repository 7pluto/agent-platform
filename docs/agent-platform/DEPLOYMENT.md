# Deployment Baseline

The current 4-core/4-GB deployment target is Docker Compose: pgvector PostgreSQL, Redis, MinIO, API, one Worker, Console and an internal CRM MCP service. Set `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `AGENT_SESSION_ENCRYPTION_KEY` and (before enabling a real model) `QWEN_API_KEY` in `.env`; no credential is stored in the database or Console.

The Worker is the only process that executes Runs and Ingest Jobs. API instances create `PENDING` Run/Job records only. The scheduler queue contains identifiers only; it does not expose messages, manifests, prompts, documents or Memory across tenants.

`deploy/helm/agent-platform` remains a Stage 5 baseline for Kubernetes. Production deployments must create the referenced Kubernetes Secret before installation. It supplies `AGENT_DATABASE_URL`, `AGENT_REDIS_URL`, and `AGENT_SESSION_ENCRYPTION_KEY`; secrets are never placed in Helm values or ConfigMaps.

```powershell
helm lint deploy/helm/agent-platform
helm template agent-platform deploy/helm/agent-platform `
  --set api.image=registry.example/agent-server:<tag> `
  --set console.image=registry.example/agent-console:<tag> `
  --set config.ruoyiBaseUrl=https://ruoyi.example
```

The Helm chart still needs its Worker/MinIO templates before it can replace Compose. Do not deploy the chart as the Stage 4 runtime path yet.
