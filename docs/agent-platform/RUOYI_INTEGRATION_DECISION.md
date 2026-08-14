# RuoYi Integration Decision

- 状态：Accepted
- 决策日期：2026-08-10
- 当前级别：L1（调用现有受保护接口，Java 零改造）
- 适用范围：Enterprise Agent Platform V1
- 适配责任方：Python Agent Platform

## 1. 最终结论

本项目不再扫描或重新设计 RuoYi 鉴权。根据既有代码扫描结果，V1 固定采用 L1：

```text
Agent Console
    -> FastAPI BFF
    -> RuoYiIamProvider
    -> RuoYi 现有登录/当前用户接口
    -> ExternalIdentityContext
    -> iam_tenant_mapping
    -> TenantContext
```

Java 侧开发任务为 0。Coding Agent 不得修改 RuoYi 仓库。

## 2. L0/L1/L2 定义与判定

### L0：Python 离线校验 Token

- 判定：不采用。
- 原因：现有系统使用 Sa-Token `simple-uuid` 状态型 Opaque Token，Token 语义依赖 Java/Sa-Token 服务端会话和 Redis。
- 禁止：Python 仿写 Sa-Token、直读 Sa-Token Redis Key、反序列化 Java LoginUser、仅按 UUID 是否存在判断身份。

### L1：Python 调用 RuoYi 现有接口

- 判定：采用。
- Java 代码改造：无。
- Java 数据库改造：无。
- 认证失败策略：Fail Closed。

### L2：极薄只读 IAM Adapter

- 判定：当前不启用。
- 只有 L1 无法返回稳定用户、组织、部门或角色时才可重新立项。
- Coding Agent 即使判定需要 L2，也只能更新 `JAVA_CHANGE_REQUEST.md` 和提供参考 Patch，不得直接修改 RuoYi。

## 3. 已冻结的 RuoYi 契约

### 3.1 Token

```text
认证框架：Sa-Token
Token 类型：simple-uuid / opaque server-side session
Header：Authorization
Prefix：Bearer
Cookie 读取：关闭
```

### 3.2 登录交换

V1 固定复用现有 OA Ticket 流程：

```http
POST /MTIwMngt/oadeepseek/service/client/ticketLogin
Content-Type: application/json

{
  "ticketCode": "<one-time-ticket>"
}
```

该接口返回的 RuoYi Token 只进入 FastAPI BFF，不写入浏览器存储。

### 3.3 当前用户

```http
GET /MTIwMngt/oadeepseek/service/ydbg/org/getUserinfo
Authorization: Bearer <ruoyi-token>
```

Python 以该接口成功响应作为在线 Token 校验及身份构建依据。字段映射冻结为：

| Agent Platform 字段 | RuoYi 字段 |
|---|---|
| `external_user_id` | `userId` |
| `display_name` | `nickName`，缺失时回退 `username` |
| `user_type` | `userType` |
| `external_org_id` | `orgId` |
| `external_org_name` | `orgName` |
| 主部门 | `dept.deptId/deptName` |
| 科室 | `subDept.deptId/deptName` |
| `role_codes` | `roles[].roleKey` |
| 角色显示信息 | `roles[].roleId/roleName` |

V1 不要求该接口返回 `permissionCodes`、`menuIds`、`dataScope` 或 Token TTL。AI 资源权限由 Agent Platform Resource Grant 管理。

### 3.4 目录接口

Resource Grant 的主体选择优先复用：

```http
GET /MTIwMngt/oadeepseek/service/ydbg/org/listDept
GET /MTIwMngt/oadeepseek/service/ydbg/org/listSubDept/{deptId}
GET /MTIwMngt/oadeepseek/service/ydbg/org/user/list?name=<query>
```

浏览器不得直接调用这些接口，由 Python 代理、裁剪和分页。

L1 不新增角色目录接口。V1 角色授权支持管理员按明确的 `role_code` 创建 Grant；后续若必须提供完整角色搜索，再单独评估 L2 directory endpoint。

## 4. Tenant 映射

RuoYi `orgId` 是外部组织标识，不直接作为平台租户主键。平台维护：

```text
iam_tenant_mapping
- provider = "ruoyi"
- external_org_id
- tenant_id
- status
- created_at
- updated_at
```

Python 只能根据受信任的当前用户响应完成映射。请求 Header、Query、Body 中的 `tenant_id/user_id/role_codes/dept_ids` 均不可信。

## 5. 不使用的现有能力

- 不使用 `/ydbg/app/list` 作为 Agent Platform 的 AI 资源授权来源。
- 不复用旧智能体广场的 Agent、应用、知识库、会话或权限数据。
- 不调用按任意 `roleId/userId` 返回管理信息的接口完成身份模拟。
- 不修改 RuoYi 菜单、用户、组织、角色和权限体系。

## 6. 上线前契约验证

代码扫描结论已冻结，不再重新研究 Java 工程。接入阶段只执行以下真实环境验证：

- 有效 Ticket 能换取 Token。
- 有效 Token 能取得上述身份字段。
- 无 Token、伪造 Token、过期 Token、已退出 Token 返回 401。
- 禁用或删除用户返回 401/403，不返回部分身份。
- 多角色、主部门、科室映射正确。
- RuoYi 5xx/超时被转换为 `IAM_UNAVAILABLE`。
- 响应 Schema 与本文不一致时阻止发布，不自动猜测字段。

验证结果只补充到本文，不触发重新扫描 RuoYi。
