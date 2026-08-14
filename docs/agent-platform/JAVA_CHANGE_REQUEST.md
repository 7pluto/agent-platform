# Java Change Request

- 编号：JCR-000
- 状态：Closed - No Java Change Required
- 决策级别：L1
- 日期：2026-08-10

## 1. 结论

```text
Java 侧无开发任务。
```

Agent Platform 由 Python 主动适配现有 RuoYi 接口。Coding Agent 默认禁止修改：

```text
D:\GmccProjectGit\智能体广场\OaDeepSeekAdmin-Service-dev
```

## 2. 复用接口

```text
登录换票：POST /MTIwMngt/oadeepseek/service/client/ticketLogin
当前用户：GET  /MTIwMngt/oadeepseek/service/ydbg/org/getUserinfo
部门列表：GET  /MTIwMngt/oadeepseek/service/ydbg/org/listDept
下级部门：GET  /MTIwMngt/oadeepseek/service/ydbg/org/listSubDept/{deptId}
用户搜索：GET  /MTIwMngt/oadeepseek/service/ydbg/org/user/list?name=
```

## 3. Java 变更清单

| 项目 | 结论 |
|---|---|
| 新增 Java Module | 无 |
| 新增 Controller/DTO/Service | 无 |
| 修改现有认证逻辑 | 无 |
| 修改用户/部门/角色/菜单 | 无 |
| 数据库迁移 | 无 |
| RuoYi 前端修改 | 无 |
| Agent Platform 表或业务逻辑 | 无 |

## 4. Python 侧承担的工作

- 实现 `RuoYiIamProvider`。
- 实现 OA Ticket 到 RuoYi Token 的服务端交换。
- 调用当前用户接口并映射 `ExternalIdentityContext`。
- 实现 `iam_tenant_mapping`及 `TenantContext`。
- 代理用户/部门目录查询。
- 实现 BFF Session、CSRF、缓存、超时和 Fail-Closed。
- 实现 `MockIamProvider`，使 Python 和 Console 开发不依赖 Java 联调进度。

## 5. L2 重新开启条件

只有真实环境契约测试证明以下最低字段无法通过现有接口获得时，才允许新建 Java 任务：

```text
userId
orgId
dept/subDept
roles[].roleKey
```

若触发 L2，Java 负责人收到的任务上限为：

```http
GET /internal/v1/iam/context

可选且需要单独证明必要性：
GET /internal/v1/iam/directory/search
```

约束：

- 独立薄模块。
- 只读。
- Context 只能来源于当前 Bearer Token。
- 无 `userId/roleId`身份模拟参数。
- 无数据库变更。
- 无原认证逻辑修改。
- 无公网 Ingress。
- 由 Java 负责人实施并回归；Coding Agent不得直接提交到RuoYi仓库。

在Java任务完成前，Agent Platform继续使用 `MockIamProvider`和冻结契约开发，不得阻塞其他Phase。
