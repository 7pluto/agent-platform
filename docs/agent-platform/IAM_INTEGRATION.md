# IAM Integration

## 1. 边界

RuoYi 是外部身份源；Agent Platform 是AI资源、授权和运行治理系统。

RuoYi负责：

- 登录和Token状态。
- 用户、组织、部门、科室、角色。

Agent Platform负责：

- Tenant映射。
- 平台角色映射。
- Resource Grant。
- Agent、Deployment、Skill、Tool、MCP、Knowledge、Memory和Run权限。

## 2. 生产拓扑

```text
Browser
  -> Agent Console
  -> FastAPI BFF（HttpOnly Session Cookie）
  -> RuoYiIamProvider（服务端 RuoYi Token）
  -> RuoYi 现有接口
```

Console和API通过同一Ingress Origin提供。RuoYi API不直接暴露给Console。

## 3. Python Provider契约

```python
class IamProvider(Protocol):
    async def exchange_ticket(self, ticket_code: str) -> UpstreamToken: ...
    async def resolve_identity(self, token: UpstreamToken) -> ExternalIdentityContext: ...
    async def search_subjects(self, subject_type, query, cursor, limit) -> SubjectPage: ...
    async def health(self) -> ProviderHealth: ...
```

`RuoYiIamProvider`实现上述契约，并只使用 `RUOYI_INTEGRATION_DECISION.md`冻结的接口。

`ExternalIdentityContext`至少包含：

```text
provider
external_user_id
external_org_id
display_name
user_type
dept_ids
role_codes
authenticated_at
upstream_expires_at | null
```

`TenantContext`由Python生成：

```text
tenant_id
external_identity
platform_roles
request_id
```

## 4. BFF登录流程

1. 现有OA入口将一次性 `appTicketCode`带到Console URL。
2. Console立即调用 `POST /api/v1/auth/exchange`，Ticket只放请求体，不写浏览器存储。
3. Python调用RuoYi `/client/ticketLogin`取得Opaque Token。
4. Python立即调用 `/ydbg/org/getUserinfo`校验Token并构建身份。
5. Python检查 `iam_tenant_mapping`。
6. Redis创建服务端Session。
7. 返回 `__Host-ap_session` Cookie；Console用 `history.replaceState`清除Ticket。

后续浏览器请求只携带Agent Platform Session Cookie。

## 5. Session与CSRF

Cookie：

```text
Name=__Host-ap_session
HttpOnly=true
Secure=true
SameSite=Lax
Path=/
Domain未设置
```

Redis会话保存：

- Session ID的HMAC/Hash。
- 使用平台密钥加密后的RuoYi Token。
- Principal最小快照。
- 允许的Tenant及当前Tenant。
- `issued_at/last_seen_at/last_introspection_at/absolute_expires_at`。
- CSRF Token。

默认策略：

- 空闲超时30分钟。
- 绝对超时8小时。
- 普通只读身份缓存最长60秒。
- 发布、部署、授权、Secret、Run启动和Tenant切换实时校验RuoYi。
- Session不得超过上游Token有效期；无法取得Token TTL时，通过在线校验控制有效性。

所有POST、PUT、PATCH、DELETE校验 `Origin/Referer`和 `X-CSRF-Token`。

## 6. Tenant和授权

- `external_org_id=orgId`。
- `iam_tenant_mapping(provider, external_org_id)`解析内部 `tenant_id`。
- 未映射、冲突或停用映射返回 `TENANT_UNMAPPED`。
- Body、Query或普通Header中的用户、租户、部门、角色字段不参与可信上下文构建。
- RuoYi角色只映射平台入口角色，不自动授予具体AI资源权限。
- Resource Grant是Agent Platform资源授权唯一事实来源。

## 7. 目录代理

Agent Platform提供统一接口：

```http
GET /api/v1/iam/subjects?type=USER|DEPT|ROLE&q=&cursor=&limit=
```

- USER代理RuoYi现有用户搜索。
- DEPT组合部门和下级部门接口。
- ROLE在L1阶段按明确 `role_code`精确录入和展示，不调用不安全的任意Role管理接口。
- 结果只包含Subject ID、类型、显示名称和必要层级信息。
- 目录结果只用于创建Grant，不替代运行时授权检查。

## 8. 错误与失败策略

| 场景 | Agent Platform响应 |
|---|---|
| 无Session | `401 AUTH_REQUIRED` |
| RuoYi Token失效 | `401 AUTH_EXPIRED`并删除Session |
| 身份有效但无权 | `403 FORBIDDEN` |
| Tenant不允许 | `403 TENANT_FORBIDDEN` |
| Tenant未映射 | `403 TENANT_UNMAPPED` |
| CSRF失败 | `403 CSRF_INVALID` |
| RuoYi超时或5xx | `503 IAM_UNAVAILABLE` |
| RuoYi响应契约错误 | `503 IAM_CONTRACT_ERROR` |

任何错误均不得降级到Dev身份、请求体身份、全局Token、公共应用或本地YAML。

## 9. MockIamProvider

- 仅允许 `APP_ENV=dev|test`。
- 使用固定Fixture模拟L1字段、Tenant映射和目录搜索。
- 生产环境检测到Mock Provider时拒绝启动。
- Contract Test必须对 `RuoYiIamProvider`和 `MockIamProvider`运行同一套用例。
- Java联调未完成时，Python、Console和E2E测试继续使用Mock，不等待Java修改。

## 10. 验收测试

- Ticket单次使用和URL清理。
- Session Fixation、Cookie重放、CSRF和开放重定向。
- 有效、伪造、过期、退出及禁用用户Token。
- 多角色、部门、科室和Tenant映射。
- Header/Body/Query身份伪造。
- 60秒读取缓存和高风险实时校验。
- RuoYi超时、5xx、Schema漂移和恢复。
- 目录分页、数据裁剪和越权访问。
- 日志、Trace、异常和API响应中无RuoYi Token。
