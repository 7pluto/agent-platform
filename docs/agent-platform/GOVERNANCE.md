# Authorization and Audit

## Ownership boundary

RuoYi remains the authoritative source for user, role and department identity. The Python Agent Platform reads that identity through the L1 IAM adapter and owns all Agent resource authorization. No RuoYi schema, controller, service or permission expression needs to change.

## Resource authorization

Resource grants are tenant-scoped and use an explicit default-deny model:

- Subjects are `USER`, `ROLE`, or `DEPT` identifiers from the normalized RuoYi principal.
- A grant targets `resource_type`, `resource_id`, and one or more actions.
- Supported grant effects are `ALLOW` and `DENY`; a matching `DENY` always wins.
- Platform administrators, configured with `AGENT_PLATFORM_ADMIN_ROLE_CODES` (default: `agent_admin`), retain bootstrap and control-plane access. This configuration is a deployment setting, not a RuoYi code change.
- Run creation requires the `RUN` action on the target `DEPLOYMENT`. Platform administrators bypass this resource-level check; all other principals require a matching allow grant.
- A Resource Descriptor records the responsible RuoYi user and optional responsibility department. The owner has implicit `VIEW`, `USE`, and `EDIT` for that resource's versions; `PUBLISH` and `MANAGE` continue to require an explicit grant or platform administration role.
- Department responsibility is descriptive. Access distribution always uses explicit `DEPT` grants, matching the original intelligent-agent plaza's department application assignment model.
- `GET /api/v1/resources/{resource_id}/descriptor` and `PATCH /api/v1/resources/{resource_id}/descriptor` expose safe metadata only: owner, source, usage guidance, tags, lifecycle status and effective authorization provenance. Secret refs and sensitive connection configuration remain excluded.

The API surface is:

- `POST /api/v1/resource-grants`
- `GET /api/v1/resource-grants`
- `GET /api/v1/audit-events`

Grant administration and audit reading are platform-administrator operations. Tenant isolation is also enforced in PostgreSQL through RLS on `resource_grants` and `audit_events`.

Cookie-authenticated state-changing APIs additionally require the per-session X-CSRF-Token returned by the ticket exchange. A missing or stale token fails closed with CSRF_INVALID.

## Audit scope

The control plane records tenant-scoped audit events for Agent creation, version creation and publishing, deployment creation, revision creation and activation, resource-grant changes, and run creation. Audit payloads deliberately store identifiers and non-secret metadata only; upstream RuoYi access tokens and request secrets are never recorded.

## Operational rollout

1. Configure the RuoYi L1 IAM endpoints and the role codes that are permitted to bootstrap platform administration.
2. Create Agent definitions, immutable published versions, deployments, and active revisions as a platform administrator.
3. Create explicit resource grants for non-administrative users, roles, or departments.
4. Review `audit-events` with a platform administrator and export them through the future SIEM integration if required.
