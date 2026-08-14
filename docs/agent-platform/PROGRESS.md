# Enterprise Agent Platform Progress

## Current Stage

Stage 4 foundation: resource registry, Agent Assembly V2, worker deployment and capability primitives.

## Completed

- Model version registry, secret references and connection gating.
- Generic versioned registry for Prompt, Skill, Native Tool, MCP Server/Connection, Knowledge and Memory Policy.
- Agent Builder V2 uses resource version selectors; legacy free-text resource references are rejected for V2 only while old Agent versions remain executable.
- Resource versions are immutable after publish; V2 publish and Run resolve direct and Skill dependencies before a model call.
- Compose now contains a single worker, pgvector PostgreSQL, MinIO and internal demo CRM MCP service.
- Long-term Memory schema/API is tenant, deployment and RuoYi-user scoped.
- MCP Streamable HTTP discovery boundary and internal CRM MCP demonstration server are available.
- Discovered MCP tools can be registered as immutable Tool Versions for Agent Builder selection.
- Qwen/OpenAI-compatible executions now run through a LangGraph model node.
- Published Memory Policy and Knowledge resources are resolved into the model runtime; `memory.read` and `rag.retrieved` events make the use visible.
- Run governance now provides tenant/user-scoped Run lists and replay-safe Run Detail (immutable Manifest plus persisted event trace).
- Knowledge Center exposes real document, index-version and worker-job state; a build request only queues the Worker.
- My Memory is policy-aware: reads and explicit writes resolve the active Deployment Memory Policy, its `USE` grant, write mode and category allowlist.
- Command-line acceptance against the deployed RuoYi account covers password/captcha/session/CSRF, resource publish/immutability, Agent Assembly V2, Deployment Revision activation and rollback, independent Worker runs, idempotency, SSE replay, cancellation, MCP discovery/invocation, API-to-MinIO PDF/DOCX upload, empty-ingest failure, Memory CRUD, IAM directories and audit events without invoking Qwen or Embedding.
- Resource Grant actions are now constrained to `VIEW/USE/EDIT/PUBLISH/MANAGE/RUN`; MCP Connections require a matching hostname `egress_allowlist` and a bounded timeout. Memory Policy validation now enforces TTL/category/item limits, and explicit writes enforce TTL plus active-item count.
- Dify Chatflow/Workflow is a versioned `DIFY_FLOW` Tool, not an alternative Agent entrypoint. The runtime composes it with platform Skill, Native Tool, MCP, Knowledge/RAG and Memory and records Dify/RAG Tool events in Run Detail.
- Provider/business credentials now follow one locked policy: the UI submits a Key once to a dedicated atomic registration API; the API tests the connection, encrypts the value into the tenant Vault and persists only `vault://UUID` plus a fingerprint. Model, Embedding, Dify Flow and authenticated MCP use this path.
- New definitions and versions reject `env://` with `VAULT_SECRET_REF_REQUIRED`, including versions that would otherwise inherit a legacy draft config. `env://` remains read-only runtime compatibility for replaying historical versions. The server `.env` contains only platform master/infrastructure bootstrap secrets.
- The Resource Center now includes guided Dify Flow and MCP Connection registration forms. API Key fields use password inputs, are cleared after submission and are not available through generic JSON configuration.
- The OpenAI-compatible multi-Tool loop now returns malformed JSON arguments to the model for bounded correction rather than failing the Run immediately, with a `tool.arguments.invalid` event for traceability.

## Database Migrations

- `0009_resource_registry`
- `0010_memory_items`
- `0011_run_scheduler_queue`
- `0012_knowledge_rag`
- `0013_knowledge_files`
- `0014_ingest_jobs`
- `0015_grant_action_constraint` (implemented locally; production migration execution is pending because the final SSH command was blocked by Codex execution limits)
- `0016_secret_vault` (deployed; tenant RLS and encrypted secret storage)

## Verification

- `python -m pytest -q`: 44 passed.
- Python compileall: passed for application and tests after the Vault-only and runtime recovery changes. The new malformed-Tool-argument and Vault persistence contract tests are present; the current workstation has no local pytest executable.
- `npm run build`: passed locally and in the production Docker build (Vue type check plus Vite production build).
- Production `/api/v1/healthz`: HTTP 200 after deployment. All published keyed resources use `vault://`; a new `env://` write returns 422 `VAULT_SECRET_REF_REQUIRED`. Dify CHATFLOW connection test returned retrieval available, and MCP discovery returned `query_customer`.

## Known Gaps

- Knowledge file upload is browser-to-Agent API-to-private MinIO (not browser-to-MinIO). The API enforces PDF/DOCX signature checks and a 20 MB limit before persisting the tenant-scoped object and document record.
- MCP connection creation is guided; registering selected discovered tools can be made more visual in a later Console iteration.
- Evaluation datasets, scorecards and aggregated trace/metric dashboards remain Stage 5 work.
- One pre-Vault, unpublished model DRAFT remains with a legacy `env://` reference as an audit/migration artifact. It cannot be assembled into a Run, and every new write is Vault-only.
# 2026-08-13 — Conversation and Agent Workbench

- Conversation is now Deployment-scoped; the aggregate API creates one Conversation and one Thread.
- Runs require a trusted Conversation/Thread pair, persist USER/ASSISTANT messages idempotently, and load up to 20 historical messages / 40,000 characters.
- Long-term Memory remains `(tenant, deployment, RuoYi user)` scoped and explicit-only; source Run idempotency is enforced.
- Added readable resource-version catalog, safe Deployment capability summaries, atomic Agent Version + Revision publication, and Revision activation/rollback UI.
- Console now provides Conversation switching, explicit Memory controls, collapsible live Run trace, final answer below trace, resource name/version cards, and Agent configuration.
- Verification: 55 backend tests pass; Python compileall and Console `vue-tsc --noEmit` pass.
- Production deployment is complete: API, Worker and Console were rebuilt on `2026-08-13`; migration `0017_conversation_workbench` is applied and Alembic reports it as `head`. RuoYi password-mode IAM override remains active.

# 2026-08-13 — Product Workspaces and Configuration Drafts

- Console is reorganized into separate user Workspace and administrator Console shells; the user path focuses on Agent discovery and conversations, while the administrator path exposes overview, Agent management and Resource Center.
- Resource Center now has searchable type filters, business-readable list rows, a safe detail drawer (versions, references, grants count and redacted configuration) and typed V1 creators for Prompt, Skill, Native Tool, Knowledge and Memory Policy.
- Agent management provides Deployment-centric rows and a five-step configuration workbench with persistent draft, safe resource selectors, assembly summary, validation/change preview and explicit publish activation.
- Migration `0018_configuration_drafts` adds a tenant-RLS configuration draft table. Publication checks the base Revision and clears the draft atomically after a successful immutable Version/Revision activation.
- Verification: 56 backend tests, Python compileall and Console Vue type check pass; production API/Worker/Console rebuilt successfully and Alembic reports `0018_configuration_drafts (head)`.
# Stage 4.6 — Resource semantics and Agent assembly productization

- Added resource descriptor migration `0019_resource_descriptors`: owner, responsibility department, safe source metadata, usage guidance, tags and lifecycle state overlay both registry resources and legacy Model records without rewriting immutable versions.
- Resource Catalog and Resource Detail now return business-oriented owner/source/health metadata, dependency graph and safe effective-permission explanation.
- Agent dependency resolution now marks direct and transitive bindings. New Run manifests are V3 and record `binding_origin` and `dependency_path`; V2 replay stays compatible.
- LangGraph OpenAI-compatible Runtime composes V3 Skills into the system prompt and registers their actual dependencies instead of exposing `skill_use_*` pseudo-tools.
- Console Resource Center is upgraded from a flat table to a resource-card catalog; the resource drawer supports editing descriptor metadata and displays dependency/authorization detail.
- Replaced the legacy flat Agent selector stepper with a module-based assembly board for Model/Prompt, Skill/Tool, Knowledge/Memory and publish preflight; Skill dependencies are expanded by business name and new configurations consume MCP through discovered Tool versions rather than selecting raw connection URLs.
- Fixed the persistent Resource Catalog session-detachment failure and verified the production administrator catalog exposes 19 published versions with complete owner/source metadata. The Resource Center now unifies 22 definitions across Model, Prompt, Skill, Tool, MCP, Knowledge and Memory Policy; Model detail is supported and dependency detail resolves names/types/versions instead of displaying UUID-only counts.
- Verification: focused backend control-plane/workbench/runtime suite passes (16 tests), Console Vue type check and production Docker build pass, all runtime containers are healthy, and `https://agent.chenwh.xin/api/v1/auth/mode` returns HTTP 200.
- Replaced the Knowledge Operations placeholder with an operational workspace: business-readable KB selection, API-mediated PDF/DOCX upload, document status, ingest job submission/status, immutable index history and retrieval testing.
- Reworked Resource creation into type-specific onboarding for OpenAI-compatible Model, Prompt, Skill with explicit Tool/Knowledge dependencies, Native Tool, Dify Flow Tool, MCP Connection, Knowledge and Memory Policy. Chinese display names now receive valid generated slugs, descriptions are persisted, Knowledge only offers embedding-oriented Models, and FastAPI 422 details render as field-level errors instead of a bare HTTP status.
- Stage 4R resource onboarding now separates Agent-assemblable capabilities from Connector/infrastructure entries and uses a four-step wizard: category, business semantics, type-specific configuration and publish preview. Every newly onboarded resource requires a one-line capability, when-to-use, input/output contract, RuoYi-backed owner, risk/read-only classification and dependencies before publish.
- Migrations `0020_resource_semantics` and `0021_resource_semantics_backfill` add and backfill the semantic descriptor for existing resources. Resource Detail and Agent Assembly expose business meaning and usage guidance; MCP Connection is explicitly infrastructure and must produce a discovered Tool before Agent assembly.

# 2026-08-13 — Dify application publishing aligned with 智能体广场

- Split Dify onboarding from the generic Connector form. Dify is now published as an external business application that produces an immutable `DIFY_FLOW` Tool; MCP Connection remains infrastructure.
- The Console Dify flow mirrors the useful parts of the existing 智能体广场 publishing form: business line, audience, usage scenarios, data involved, co-developers, opening statement, suggested questions and a RuoYi-backed publication scope.
- Added `POST /api/v1/dify-applications`, which validates the Dify App credential, discovers `/parameters`, generates the Tool input schema, stores the Key only in the tenant Vault, publishes Tool V1, writes the semantic descriptor and creates version-level `VIEW/USE` grants for selected RuoYi users, roles or departments.
- Kept `POST /api/v1/dify-flow-tools` as a compatibility API for existing automation. New Console onboarding uses the product command API.
- Resource Detail now shows Dify application profile and discovered inputs while redacting `secret_ref`, credentials and authorization fields.
- Fixed Workflow observations so Dify `outputs` reach the model; Chatflow observations retain the existing bounded compatibility contract.
- Verification: Console `vue-tsc --noEmit` passes; Dify runtime, resource registry and Runtime adapter suites pass (14 tests); Python compileall passes.
- Production deployment completed on the existing single-node Compose host. API, Worker and Console were rebuilt; `/api/v1/healthz` is healthy, OpenAPI exposes `/api/v1/dify-applications`, and the deployed Console asset is `index-C-3vjnnb.js`. The pre-deploy backup is `backups/dify-application-publish-20260813` on the server.

# 2026-08-14 — Resource publication profile and Agent department scope

- Resource descriptors now carry shared business publication metadata (business line, data classification, audience, usage scenarios, co-developers and publication scope) instead of reserving it for Dify alone. Resource list/detail APIs expose only safe, readable metadata. Migrations use compact Alembic IDs because the existing production `alembic_version.version_num` column is `varchar(32)`.
- Agent configuration publishing now includes a RuoYi-backed run audience: personal trial, one department, or selected departments/roles/users. The selected subjects become `DEPLOYMENT/RUN` grants; a republish replaces only grants generated by the prior publication profile, so removed departments immediately lose Run access while independently managed grants remain untouched.
- Deployment capability summaries return the safe current publication scope for the configuration UI; credentials, source configs and Vault values are never part of this response.
- Verification: Python compileall, Console `vue-tsc --noEmit`, and focused workbench/resource/governance tests (8 passed).
