# Control Plane and Run Resolution

## Lifecycle

```text
Agent Definition -> Draft Version -> Published Version
-> Deployment -> Deployment Revision -> Activate Revision -> Run
```

Published Agent Versions are immutable. A Deployment Revision may reference only a published Version from the Deployment's Agent. Activation moves only the Deployment's active revision pointer, making rollback an explicit pointer change.

## APIs

- `POST /api/v1/agents`, `GET /api/v1/agents`
- `GET /api/v1/agents/{agent_id}/versions`
- `GET /api/v1/deployments`, `GET /api/v1/deployments/{deployment_id}/revisions`
- `POST /api/v1/agents/{agent_id}/versions`
- `POST /api/v1/agent-versions/{agent_version_id}/publish`
- `POST /api/v1/deployments`
- `POST /api/v1/deployments/{deployment_id}/revisions`
- `POST /api/v1/deployments/{deployment_id}/revisions/{revision_id}/activate`
- `GET /api/v1/deployments/{deployment_id}/resolve`

Agent Draft, Version specification, and Deployment Revision overrides reject plaintext secret-bearing keys (such as `api_key`, `password`, or `token`). Only opaque `secret_ref`/`secret_refs` references are permitted, so credentials cannot flow into persisted specs, audit records, or execution manifests.

Run creation resolves the active revision before the Run row is created. The resulting Execution Manifest records the Agent Definition, Agent Version content hash, and Deployment Revision ID. A deployment without an active revision is rejected.

## Resource assembly provenance

The resolver distinguishes `DIRECT` bindings selected in an Agent Version from `TRANSITIVE` bindings introduced by a Skill or MCP Tool. New Runs use Execution Manifest schema V3 and record a dependency path for each resolved immutable resource. V2 manifests remain readable and executable for historical replay.

For V3, a Skill is assembled into the system context as approved guidance and its dependent tools are registered normally. It is no longer presented to the model as a synthetic `skill_use_*` tool; the model decides whether to call the actual Tool, MCP, Dify Flow, or Knowledge Retriever.

## Runtime development mode

`AGENT_RUNTIME_EXECUTION_MODE=in_process` remains a local deterministic compatibility mode. Compose deployments use `AGENT_RUNTIME_EXECUTION_MODE=worker`: the API creates `PENDING` records only; the single Worker claims an identifier-only scheduler row, enters a tenant-scoped transaction, then resolves the frozen Manifest and executes the selected runtime. The scheduler never reads messages, manifests, prompts, documents or Memory across tenants.

## Browser mutation protection

All state-changing Control Plane and Run APIs using the BFF cookie require the X-CSRF-Token obtained during ticket exchange. Missing or stale tokens return 403 CSRF_INVALID. Read APIs remain cookie-authenticated but do not require the header. Resource-grant policy and audit coverage are detailed in GOVERNANCE.md.
