# AI 智能面试助手 —— API 接口文档

> **面向对象：前端 / 客户端开发者。** 每个接口都给出「提交方式 · URL · 参数 · 响应 · 示例」，
> 可直接照抄对接。
>
> 文中所有状态码、错误码与业务规则，均为**已被 461 条测试用例验证过的实际行为**
> （见 [API 接口测试报告](../tests/2026-09-17-API接口测试报告.md)），不是设计意图的转述。

| 项 | 内容 |
|---|---|
| API 版本 | `0.1.0` |
| 基础路径 | `/api` |
| 服务框架 | FastAPI（Python 3.11+） |
| 数据格式 | JSON，UTF-8（`utf8mb4`） |
| 认证方式 | JWT Bearer Token |
| 接口总数 | **26 个 method-route / 17 条路径** |
| 契约验证 | `backend/tests/` **461 条用例，0 失败** |
| 交互式文档 | `GET /docs`（Swagger UI）、`GET /openapi.json` |

> **关于 `422`**：下文错误表中不会出现 422。FastAPI 默认的参数校验状态码已被全局
> 收口为 **`400 VALIDATION_ERROR`**，`/openapi.json` 里标注的 422 不生效，以本文档为准。

---

## 目录

- [一、5 分钟接入](#一5-分钟接入)
- [二、通用约定](#二通用约定)
- [三、接口总览](#三接口总览)
- [四、系统](#四系统)
- [五、认证与用户](#五认证与用户)
- [六、岗位](#六岗位)
- [七、题库](#七题库)
- [八、面试](#八面试)
- [九、评估](#九评估)
- [十、数据模型](#十数据模型)
- [十一、完整流程示例](#十一完整流程示例)
- [十二、前端对接要点](#十二前端对接要点)
- [十三、附录](#十三附录)

---

## 一、5 分钟接入

### 1.1 基址

| 环境 | 前端请求的基址 | 说明 |
|---|---|---|
| 后端直接托管前端（`一键启动.bat`） | `/api` | **同源**，前端与后端都是 `http://127.0.0.1:8000` |
| Vite 开发服务器（`npm run dev`） | `/api` | Vite 把 `/api` 代理到 `http://127.0.0.1:8000` |
| 直连后端（curl / Postman） | `http://127.0.0.1:8000/api` | — |

**前端代码一律写相对路径 `/api/...`**，两种模式都不需要处理 CORS。用 Postman 调试时才用完整地址。

### 1.2 一次最小调用

```js
// 1) 登录拿 token
const res = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin12345' }),
});
const { token, user } = await res.json();

// 2) 带着 token 调业务接口
const list = await fetch('/api/interviews', {
  headers: { Authorization: `Bearer ${token}` },
}).then((r) => r.json());
```

### 1.3 前端需要知道的三件事

1. **除了登录和健康检查，所有接口都要 `Authorization: Bearer <token>`**。
2. **所有错误响应结构完全一致**（`{code, message, detail}`），写一个统一拦截器即可。
3. **评估进度是 SSE 流，且必须带 `Authorization` 头** —— 所以**不能用浏览器原生
   `EventSource`**，要用 `fetch` + `ReadableStream`。完整实现见 [§12.2](#122-sse-必须用-fetch--readablestream)。

---

## 二、通用约定

### 2.1 服务地址与部署约束

| 环境 | 地址 |
|---|---|
| 本地开发 | `http://localhost:8000` |
| 前端代理 | Vite 将 `/api` 代理至 `http://localhost:8000` |

> ⚠️ **后端必须单进程运行**：`uvicorn app.main:app --workers 1`。
> 评估的 SSE 运行注册表是**进程内**的内存结构，多 worker 会让
> `POST /evaluate` 与 `GET /evaluation/stream` 落在不同进程而无法衔接。

### 2.2 认证

除 `POST /api/auth/login` 与 `GET /api/health` 外，**所有接口都需要认证**。

```http
Authorization: Bearer <token>
```

| 项 | 说明 |
|---|---|
| token 获取 | `POST /api/auth/login` 响应中的 `token` 字段 |
| token 内容 | `sub`（用户 id）、`iat`、`exp`；**不包含 role** |
| 默认有效期 | 720 分钟（12 小时），由 `JWT_EXPIRE_MINUTES` 配置 |
| 过期策略 | 过期后需**重新登录**（未实现 refresh token） |

**三个与 token 相关的重要行为**（均已被测试固定）：

1. **角色不缓存在 JWT 里** —— admin 把某 hr 提升为 admin 后，该用户**用旧 token 即可立即访问**
   `/api/users`，无需重新登录。前端若缓存了 `user.role`，需注意这一点。
2. **账号被禁用后旧 token 立即失效**（每次请求都回查数据库的 `is_active`）。
3. **伪造 / 篡改 / 换密钥签发的 token** 返回 `401 INVALID_TOKEN`，与「未携带 token」的
   `401 UNAUTHORIZED` 区分开 —— 前端可以据此区分「需要跳登录」与「登录态被顶掉」。

### 2.3 统一响应格式

**所有**错误响应共用同一结构：

```json
{
  "code": "BUSINESS_ERROR",
  "message": "当前状态下不可修改回答，请先回退到进行中",
  "detail": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | string | 机器可读的错误码，用于前端分支判断，见 §2.4 |
| `message` | string | **可直接展示给用户的中文文案** —— 文案由后端维护，前端不要自己编 |
| `detail` | object \| null | 结构化补充信息，见下 |

**参数校验失败的 `detail`**：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数不合法",
  "detail": {
    "fields": [
      { "field": "password", "message": "String should have at least 8 characters", "type": "string_too_short" }
    ]
  }
}
```

`detail.fields[].field` 可直接用于把错误定位到具体表单项。

**状态机非法迁移的 `detail`**：

```json
{
  "code": "BUSINESS_ERROR",
  "message": "不允许从「进行中」迁移到「进行中」",
  "detail": { "from": "ongoing", "to": "ongoing" }
}
```

**维度不属岗位的 `detail`**：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "该维度不属于岗位的评估维度",
  "detail": { "dimension": "沟通能力", "allowed": ["专业能力", "逻辑思维"] }
}
```

### 2.4 错误码表

| code | HTTP | 触发场景 | 典型 message |
|---|---|---|---|
| `VALIDATION_ERROR` | 400 | 字段越界、枚举非法、维度不属岗位 | `请求参数不合法`（默认）· `该维度不属于岗位的评估维度` |
| `UNAUTHORIZED` | 401 | 未携带 token、密码错误、账号被禁用 | `未认证`（默认）· `用户名或密码错误` · `账号已禁用，请联系管理员` |
| `INVALID_TOKEN` | 401 | token 过期 / 篡改 / 换密钥签发 | `登录状态已失效，请重新登录` |
| `FORBIDDEN` | 403 | 访问他人资源、非 admin 访问管理接口 | `无权限执行此操作`（默认）· `无权限访问该岗位` · `无权限访问该面试` |
| `NOT_FOUND` | 404 | 资源不存在、题目不属该面试 | `资源不存在`（默认）· `岗位不存在` · `面试不存在` · `题目不属于该面试` |
| `BUSINESS_ERROR` | 409 | 状态机非法迁移、重名、被引用不可删 | `业务规则冲突`（默认）· `该岗位名称已存在` · `该岗位已被题库或面试引用，无法删除` |
| `INTERNAL_ERROR` | 500 | 未预期异常（**响应体不含堆栈**） | `服务器内部错误` |
| `AI_PROVIDER_ERROR` | 502 | AI 出题失败（事务整体回滚，无残留数据） | `AI 服务调用失败，请稍后重试` |

> 表中「默认」为异常类自带的文案；业务代码可在抛出时覆盖为更具体的文案
> （如 `面试不存在`），未覆盖时回落到默认值。**前端展示 `message` 即可，不必自己映射**。

### 2.5 数据隔离规则

| 角色 | 可见范围 |
|---|---|
| `hr` | **仅自己创建的数据**（岗位 / 题目 / 面试三个列表均按 `created_by` 过滤） |
| `admin` | **全部数据**（不做过滤） |

单条资源的判定顺序（全项目统一，前端可据此设计提示文案）：

1. 记录不存在 → `404 NOT_FOUND`
2. 记录存在但不属于当前用户 → `403 FORBIDDEN`（**有意暴露资源存在性**）

题目额外遵循：**隔离键是题目自身的 `created_by`**，与所属岗位的创建者无关。

### 2.6 通用行为约定

| 项 | 约定 |
|---|---|
| 分页 | **不提供**。所有列表接口返回全量数组 |
| 排序 | 岗位 / 题目 / 用户按 `id` **升序**；面试列表按 `id` **降序**（新的在前）；面试内题目按 `seq` 升序 |
| 时间格式 | ISO 8601 字符串，如 `2026-09-17T10:30:00`（**无时区后缀**，按本地时间处理） |
| 脱敏 | 任何用户相关响应**都不会出现 `password_hash`** |
| 删除 | 均为物理删除；用户不做物理删除，只能禁用（`is_active: false`） |
| 请求体 | 除 `DELETE` 与动词端点外均需 `Content-Type: application/json` |

---

## 三、接口总览

| # | 提交方式 | URL | 鉴权 | 说明 |
|---:|---|---|---|---|
| 1 | `GET` | `/api/health` | 无 | 健康检查 |
| 2 | `POST` | `/api/auth/login` | 无 | 登录，签发 JWT |
| 3 | `GET` | `/api/auth/me` | 登录 | 当前登录用户信息 |
| 4 | `POST` | `/api/users` | admin | 创建用户 |
| 5 | `GET` | `/api/users` | admin | 用户列表 |
| 6 | `PATCH` | `/api/users/{user_id}` | admin | 改角色 / 启用禁用 |
| 7 | `POST` | `/api/positions` | 登录 | 创建岗位 |
| 8 | `GET` | `/api/positions` | 登录 | 岗位列表（可按名模糊搜） |
| 9 | `GET` | `/api/positions/{position_id}` | 登录 | 岗位详情 |
| 10 | `PUT` | `/api/positions/{position_id}` | 登录 | 更新岗位（全量替换） |
| 11 | `DELETE` | `/api/positions/{position_id}` | 登录 | 删除岗位 |
| 12 | `POST` | `/api/questions` | 登录 | 创建题目 |
| 13 | `GET` | `/api/questions` | 登录 | 题目列表（多维筛选） |
| 14 | `GET` | `/api/questions/{question_id}` | 登录 | 题目详情 |
| 15 | `PUT` | `/api/questions/{question_id}` | 登录 | 更新题目（全量替换） |
| 16 | `DELETE` | `/api/questions/{question_id}` | 登录 | 删除题目 |
| 17 | `POST` | `/api/interviews` | 登录 | 创建面试（**同步出题**） |
| 18 | `GET` | `/api/interviews` | 登录 | 面试列表 |
| 19 | `GET` | `/api/interviews/{interview_id}` | 登录 | 面试详情（含题目与回答） |
| 20 | `PATCH` | `/api/interviews/{interview_id}` | 登录 | 更新候选人信息 |
| 21 | `POST` | `/api/interviews/{interview_id}/answers` | 登录 | 录入 / 修改某题回答 |
| 22 | `POST` | `/api/interviews/{interview_id}/complete` | 登录 | 标记完成 |
| 23 | `POST` | `/api/interviews/{interview_id}/rollback` | 登录 | 回退到进行中 |
| 24 | `POST` | `/api/interviews/{interview_id}/evaluate` | 登录 | 触发评估（202） |
| 25 | `GET` | `/api/interviews/{interview_id}/evaluation/stream` | 登录 | **SSE** 评估进度 |
| 26 | `GET` | `/api/interviews/{interview_id}/report` | 登录 | 获取完整报告 |

---

## 四、系统

### 4.1 健康检查

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/health` |
| 鉴权 | **不需要** |

**参数**：无。

**响应 `200`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 恒为 `"ok"` |

```json
{ "status": "ok" }
```

**错误**：无。服务不可达时前端会拿到网络错误而非此处定义的错误码。

> 用途：前端可在启动时探活，或在 `NETWORK_ERROR` 时提示用户检查后端是否已启动。

---

## 五、认证与用户

### 5.1 登录

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/auth/login` |
| 鉴权 | **不需要** |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `username` | string | 是 | 1–50 字符 | 用户名 |
| `password` | string | 是 | 1–128 字符 | 密码 |

**请求示例**

```json
{ "username": "admin", "password": "admin12345" }
```

**响应 `200`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `token` | string | JWT，后续所有请求放在 `Authorization: Bearer` 中 |
| `user` | object | 用户对象，见 [§10.1](#101-userout) |

**响应示例**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiaWF0IjoxNzg5Njk1OTgxLCJleHAiOjE3ODk3MzkxODF9.vaa3RgLJ2TCfpEQkf8Xt2GGdS7CRWv5DI6GWQOdI8vE",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "is_active": true,
    "created_at": "2026-09-16T03:34:02"
  }
}
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 缺少 `username` 或 `password` | `请求参数不合法` |
| 401 | `UNAUTHORIZED` | 用户名不存在**或**密码错误 | `用户名或密码错误` |
| 401 | `UNAUTHORIZED` | 账号已禁用 | `账号已禁用，请联系管理员` |

> **防用户名枚举**：前两种情况（用户名不存在 / 密码错误）的响应**完全相同**，
> 且服务端在用户不存在时也执行一次哈希比对以拉平响应时间。前端不要试图区分二者。

### 5.2 当前登录用户

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/auth/me` |
| 鉴权 | 需要 |

**参数**：无。

**响应 `200`** —— 用户对象（[§10.1](#101-userout)），**不含 `password_hash`**。

```json
{
  "id": 1,
  "username": "admin",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-09-16T03:34:02"
}
```

**错误**

| HTTP | code | 触发场景 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 未携带 token |
| 401 | `INVALID_TOKEN` | token 无效 / 过期 / 篡改 |
| 401 | `UNAUTHORIZED` | 用户已被禁用或删除 |

> 建议：应用启动时先调一次 `/auth/me` 刷新用户信息，避免展示过期的角色。

### 5.3 创建用户（仅 admin）

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/users` |
| 鉴权 | **仅 `admin`** |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `username` | string | 是 | 1–50 字符 | **全局唯一** |
| `password` | string | 是 | **最少 8 字符**，最多 128 | 明文传输，服务端 bcrypt 后入库 |
| `role` | string | 是 | `admin` \| `hr` | 枚举，其他值 400 |

```json
{ "username": "hr_zhang", "password": "hr12345678", "role": "hr" }
```

**响应 `201`** —— 用户对象（[§10.1](#101-userout)）。

```json
{
  "id": 2,
  "username": "hr_zhang",
  "role": "hr",
  "is_active": true,
  "created_at": "2026-09-17T10:00:00"
}
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 密码少于 8 位 / 角色非法 / 用户名超长 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 非 admin 调用 | `无权限执行此操作` |
| 409 | `BUSINESS_ERROR` | 用户名已存在 | `用户名已存在` |

### 5.4 用户列表（仅 admin）

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/users` |
| 鉴权 | **仅 `admin`** |

**参数**：无（不分页）。

**响应 `200`** —— 用户对象数组，按 `id` 升序。

**错误**：`403 FORBIDDEN`（非 admin）。

### 5.5 修改角色 / 启用禁用（仅 admin）

| 项 | 内容 |
|---|---|
| 提交方式 | `PATCH` |
| URL | `/api/users/{user_id}` |
| 鉴权 | **仅 `admin`** |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `user_id` | integer | 目标用户 id |

**请求体**（两个字段**均可选**，只传需要改的）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `role` | string \| null | `admin` \| `hr` | 改角色 |
| `is_active` | boolean \| null | — | `false` 即禁用，旧 token 立即失效 |

**请求示例**

```json
{ "role": "admin" }
```

```json
{ "is_active": false }
```

**响应 `200`** —— 更新后的用户对象。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 非 admin 调用 | `无权限执行此操作` |
| 404 | `NOT_FOUND` | 目标用户不存在 | `用户不存在` |
| 409 | `BUSINESS_ERROR` | **admin 修改自己的角色或状态** | `不能修改自己的角色或状态` |

> 防自锁死：admin 不能把自己降级或禁用，否则系统将没有任何管理员。
> 前端应在界面上直接禁用「当前登录 admin 自己那一行」的开关。

---

## 六、岗位

岗位字段：名称、JD、**评估维度列表**。评估维度是后续出题与多维评分的基准。

### 6.1 创建岗位

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/positions` |
| 鉴权 | 需要 |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | 1–100 字符 | **同一创建人下唯一** |
| `jd` | string | 是 | 1–10000 字符 | 岗位描述 |
| `evaluation_dimensions` | string[] | 是 | 1–10 个，单项 1–50 字符 | 评估维度 |

**请求示例**

```json
{
  "name": "后端工程师",
  "jd": "负责后端服务的开发与维护，要求熟悉 Python 与数据库设计。",
  "evaluation_dimensions": ["沟通能力", "专业能力", "逻辑思维", "文化契合"]
}
```

**评估维度校验规则**

| 规则 | 说明 | 违反结果 |
|---|---|---|
| 数量 | 1–10 个 | `400 VALIDATION_ERROR` |
| 单项长度 | 1–50 字符 | `400` |
| 不可为空串 | 纯空白视同空 | `400` |
| 去重 | **strip 后不区分大小写**去重（`"Communication"` 与 `"communication"` 视为重复，`" 沟通 "` 与 `"沟通"` 视为重复） | `400` |
| 落库形态 | 保存 **strip 后、保留原始大小写**的值 | — |

**响应 `201`** —— 岗位对象（[§10.2](#102-positionout)）。

```json
{
  "id": 1,
  "name": "后端工程师",
  "jd": "负责后端服务的开发与维护，要求熟悉 Python 与数据库设计。",
  "evaluation_dimensions": ["沟通能力", "专业能力", "逻辑思维", "文化契合"],
  "created_by": 2,
  "created_at": "2026-09-17T10:00:00"
}
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 维度为空 / 超 10 个 / 重复 / 超长；`name`、`jd` 越界 | `请求参数不合法` |
| 409 | `BUSINESS_ERROR` | 同一创建人下名称重复 | `该岗位名称已存在` |

> 跨创建人可以重名 —— 两个 hr 各自建一个「后端工程师」是允许的。

### 6.2 岗位列表

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/positions` |
| 鉴权 | 需要 |

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `keyword` | string | 否 | 按 `name` 服务端模糊匹配（`LIKE %keyword%`） |

**请求示例**

```http
GET /api/positions?keyword=后端 HTTP/1.1
Authorization: Bearer <token>
```

**响应 `200`** —— 岗位对象数组，按 `id` 升序。hr 仅见自己的，admin 见全部。无分页。

### 6.3 岗位详情

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/positions/{position_id}` |
| 鉴权 | 需要 |

**路径参数**：`position_id`（integer）

**响应 `200`** —— 岗位对象。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 404 | `NOT_FOUND` | 岗位不存在 | `岗位不存在` |
| 403 | `FORBIDDEN` | 岗位属于他人 | `无权限访问该岗位` |

### 6.4 更新岗位

| 项 | 内容 |
|---|---|
| 提交方式 | `PUT` |
| URL | `/api/positions/{position_id}` |
| 鉴权 | 需要 |

**全量替换语义** —— 请求体字段与创建时**完全相同**（`name` / `jd` / `evaluation_dimensions` 均必填）。

> `evaluation_dimensions` 是**整体替换**而非追加：传 `["C"]` 后，原来的 `["A","B"]` 变成 `["C"]`。
> 前端编辑表单要提交完整数组，不是差量。

**响应 `200`** —— 更新后的岗位对象。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 维度非法 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 岗位属于他人 | `无权限访问该岗位` |
| 404 | `NOT_FOUND` | 岗位不存在 | `岗位不存在` |
| 409 | `BUSINESS_ERROR` | 改名后与其他岗位撞名 | `该岗位名称已存在` |

> 改名与改 JD 不影响已完成的面试；**改维度只影响此后新触发**的评估，不重算历史评估。

### 6.5 删除岗位

| 项 | 内容 |
|---|---|
| 提交方式 | `DELETE` |
| URL | `/api/positions/{position_id}` |
| 鉴权 | 需要 |

**参数**：仅路径参数 `position_id`。**无请求体。**

**响应 `204`** —— **无响应体**。前端不要对该状态码调用 `response.json()`。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 岗位属于他人 | `无权限访问该岗位` |
| 404 | `NOT_FOUND` | 岗位不存在 | `岗位不存在` |
| 409 | `BUSINESS_ERROR` | 被题库或面试引用 | `该岗位已被题库或面试引用，无法删除` |

> 删除保护覆盖**两类引用**：岗位下存在题目、**或**存在引用该岗位的面试
> （哪怕该岗位下一道题都没有）。由外键 `ON DELETE RESTRICT` 保证。

---

## 七、题库

### 7.1 创建题目

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/questions` |
| 鉴权 | 需要 |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `position_id` | integer | 是 | 岗位须存在且当前用户可见 | — |
| `category` | string \| null | 否 | 1–50 字符 | `"通用"` |
| `dimension` | string | 是 | 1–50 字符，**必须属于该岗位的评估维度** | — |
| `content` | string | 是 | **5–2000 字符** | — |
| `difficulty` | string | 否 | `easy` \| `medium` \| `hard` | `"medium"` |
| `tags` | string[] | 否 | ≤10 个，单个 1–20 字符，strip 后去重 | `[]` |

> ⚠️ `source` **不可由客户端指定** —— 即使请求体里传了 `"source": "ai"`，落库仍为 `"bank"`。
> 该字段只由服务端在 AI 出题时写入。

**请求示例**

```json
{
  "position_id": 1,
  "category": "行为面试",
  "dimension": "沟通能力",
  "content": "请描述一次你处理线上故障的完整过程。",
  "difficulty": "medium",
  "tags": ["故障处理", "沟通"]
}
```

**响应 `201`** —— 题目对象（[§10.3](#103-questionout)）。

```json
{
  "id": 1,
  "position_id": 1,
  "category": "行为面试",
  "dimension": "沟通能力",
  "content": "请描述一次你处理线上故障的完整过程。",
  "difficulty": "medium",
  "tags": ["故障处理", "沟通"],
  "source": "bank",
  "created_by": 2,
  "created_at": "2026-09-17T10:05:00"
}
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `content` 少于 5 或多于 2000；`tags` 超限；`difficulty` 非法 | `请求参数不合法` |
| 400 | `VALIDATION_ERROR` | `dimension` 不属该岗位 | `该维度不属于岗位的评估维度`（`detail.allowed` 含合法维度） |
| 403 | `FORBIDDEN` | 岗位属于他人 | `无权限访问该岗位` |
| 404 | `NOT_FOUND` | 岗位不存在 | `岗位不存在` |

> 维度匹配是 **strip 后精确匹配**（区分大小写）。前端应把该岗位的
> `evaluation_dimensions` 渲染成下拉选择，从源头避免 400。

### 7.2 题目列表

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/questions` |
| 鉴权 | 需要 |

**查询参数**（多个条件之间为 **AND** 关系）

| 参数 | 类型 | 必填 | 匹配方式 |
|---|---|---|---|
| `position_id` | integer | 否 | 按岗位过滤 |
| `category` | string | 否 | **精确**匹配 |
| `dimension` | string | 否 | **精确**匹配 |
| `source` | string | 否 | `bank` \| `ai` |
| `keyword` | string | 否 | 按 `content` 模糊匹配 |

**请求示例**

```http
GET /api/questions?position_id=1&dimension=沟通能力&source=bank HTTP/1.1
Authorization: Bearer <token>
```

**响应 `200`** —— 题目对象数组，按 `id` 升序。

> 筛选**不会越过数据隔离边界**：即便筛选条件完全匹配，hr 也只会看到自己的题目。
> 无分页。

### 7.3 题目详情

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/questions/{question_id}` |
| 鉴权 | 需要 |

**响应 `200`** —— 题目对象。

**错误**：`404 NOT_FOUND`（`题目不存在`）/ `403 FORBIDDEN`。

### 7.4 更新题目

| 项 | 内容 |
|---|---|
| 提交方式 | `PUT` |
| URL | `/api/questions/{question_id}` |
| 鉴权 | 需要 |

**全量替换语义**，请求体字段与创建时相同（`tags` 整体替换）。

> `position_id` **可以改** —— 改到其他岗位时会**重新校验** `dimension` 是否属于新岗位，
> 不属于则 `400`。前端换岗位时应同步刷新维度下拉并清空已选维度。

**响应 `200`** —— 更新后的题目对象。

### 7.5 删除题目

| 项 | 内容 |
|---|---|
| 提交方式 | `DELETE` |
| URL | `/api/questions/{question_id}` |
| 鉴权 | 需要 |

**响应 `204`** —— **无响应体**。

**错误**：`409 BUSINESS_ERROR`（`该题目已被面试引用，无法删除`）。

---

## 八、面试

### 8.1 状态机

```
draft ──► ongoing ──► completed ──► evaluating ──► evaluated
             ▲            │              │             │
             │            │              │             │
             └────────────┴──────────────┴─────────────┘
                  回退（rollback）
```

| 状态 | 含义 |
|---|---|
| `draft` | 事务内的瞬时值，**从不落库**（创建即 `ongoing`） |
| `ongoing` | 进行中，可录入 / 修改回答 |
| `completed` | 已标记完成，回答锁定 |
| `evaluating` | 评估中，所有数据锁定 |
| `evaluated` | 已评估，可查看报告、可重新评估 |

**全部合法迁移（8 条）**

| 从 → 到 | 触发入口 | 副作用 |
|---|---|---|
| `draft` → `ongoing` | 创建面试（事务内） | — |
| `ongoing` → `completed` | `POST /complete` | 设置 `completed_at` |
| `completed` → `evaluating` | 触发评估 | — |
| `completed` → `ongoing` | `POST /rollback` | 清空 `completed_at` |
| `evaluating` → `evaluated` | 评估成功 | — |
| `evaluating` → `completed` | 评估失败 | — |
| `evaluated` → `evaluating` | 重新评估 | — |
| `evaluated` → `ongoing` | `POST /rollback` | 清空 `completed_at` |

**其余 17 种组合一律拒绝**，返回 `409 BUSINESS_ERROR`，`detail` 为 `{"from": ..., "to": ...}`。

**各状态下的操作矩阵**（前端据此禁用按钮）

| 操作 | draft | ongoing | completed | evaluating | evaluated |
|---|---|---|---|---|---|
| 查看详情 | ✗ | ✓ | ✓ | ✓ | ✓ |
| 改候选人信息 | ✗ | ✓ | ✓ | ✗ | ✗ |
| 录入 / 修改回答 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 标记完成 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 回退到进行中 | ✗ | ✗ | ✓ | ✗ | ✓ |
| 触发评估 | ✗ | ✗ | ✓ | ✗ | ✓（重评） |

### 8.2 创建面试（同步出题）

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews` |
| 鉴权 | 需要 |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `position_id` | integer | 是 | 岗位须存在且可见 | 面试依据的岗位 |
| `candidate_name` | string | 是 | 1–100 字符 | 候选人姓名 |
| `candidate_contact` | string \| null | 否 | ≤200 字符 | 联系方式 |

**请求示例**

```json
{ "position_id": 1, "candidate_name": "张三", "candidate_contact": "13800000000" }
```

**响应 `201`** —— 面试详情对象（[§10.5](#105-interviewdetail)）。

```json
{
  "id": 1,
  "position_id": 1,
  "position_name": "后端工程师",
  "candidate_name": "张三",
  "candidate_contact": "13800000000",
  "status": "ongoing",
  "created_at": "2026-09-17T10:10:00",
  "completed_at": null,
  "question_count": 8,
  "answered_count": 0,
  "jd": "负责后端服务的开发与维护…",
  "evaluation_dimensions": ["沟通能力", "专业能力", "逻辑思维", "文化契合"],
  "questions": [
    {
      "interview_question_id": 1,
      "seq": 1,
      "content": "请描述一次你处理线上故障的完整过程。",
      "dimension": "沟通能力",
      "source": "bank",
      "answer": null,
      "recorded_at": null
    }
  ]
}
```

> 上面的 `questions` **只展示了第 1 条**，实际返回 8 条（`question_count` 与
> `len(questions)` 一致）。
>
> ⚠️ **注意 `interview_question_id` ≠ `id`**。保存回答时用的是
> `questions[].interview_question_id`，不是面试 id，也不是题目 id。

**出题组装规则**（同步完成，是创建接口的一部分 —— 所以这个接口**比其他接口慢**）

配置项：`QUESTION_COUNT_FROM_BANK`（默认 **5**，记作 N）、`QUESTION_COUNT_FROM_AI`（默认 **3**，记作 M）。

1. 取该岗位下当前用户可见的题库题目
2. 丢弃 `dimension` 已不在岗位维度列表中的题目（岗位维度改过之后的历史题）
3. 按维度分组，组内按 `id` 升序
4. 按岗位维度顺序**轮询抽取**，每轮每维度取 1 题，直至抽满 N 题或各维度抽空 —— 实际抽到 K 题
5. AI 补齐 `need_ai = M + (N − K)` 题 —— **保证总题数恒为 N + M = 8**，题库不足时由 AI 补足，**不报错**
6. AI 生成的题目**落回题库**（`source = 'ai'`，`created_by` = 面试创建者）
7. 合并：题库题在前（按抽取顺序），AI 题在后；`seq` 从 1 连续编号
8. 为每题写入三个快照：`content_snapshot` / `dimension_snapshot` / `source_snapshot`

| 场景 | 结果 |
|---|---|
| 题库充足 | 8 题（5 题库 + 3 AI） |
| 题库只有 3 题 | 8 题（3 题库 + 5 AI） |
| 题库为空 | 8 题（全部 AI） |
| 相同数据状态 | 出题结果**完全确定**（可复现） |

**快照语义**：题目内容、维度、来源在出题时冻结。此后修改题库题干**不会**改变历史面试的显示内容。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 姓名越界、`position_id` 缺失 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 岗位属于他人 | `无权限访问该岗位` |
| 404 | `NOT_FOUND` | 岗位不存在 | `岗位不存在` |
| 502 | `AI_PROVIDER_ERROR` | **AI 出题失败** | `AI 服务调用失败，请稍后重试` |

> AI 失败时**整个事务回滚** —— 面试与 AI 题目都不会残留，前端可直接重试创建。

### 8.3 面试列表

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews` |
| 鉴权 | 需要 |

**参数**：无（**不支持筛选，也不分页**）。

**响应 `200`** —— 面试列表项数组（[§10.4](#104-interviewlistitem)），按 `id` **降序**（新的在前）。

| 字段 | 说明 |
|---|---|
| `question_count` | 题目总数 |
| `answered_count` | **非空**回答数（空串表示未作答，不计入） |

```json
[
  {
    "id": 2,
    "position_id": 1,
    "position_name": "后端工程师",
    "candidate_name": "李四",
    "candidate_contact": null,
    "status": "completed",
    "created_at": "2026-09-17T11:00:00",
    "completed_at": "2026-09-17T11:20:00",
    "question_count": 8,
    "answered_count": 8
  }
]
```

### 8.4 面试详情

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}` |
| 鉴权 | 需要 |

**响应 `200`** —— 面试详情（[§10.5](#105-interviewdetail)），`questions` 按 `seq` 升序。

> 未作答的题目，`answer` 与 `recorded_at` 均为 `null`。

**错误**：`404 NOT_FOUND`（`面试不存在`）/ `403 FORBIDDEN`（`无权限访问该面试`）。

### 8.5 更新候选人信息

| 项 | 内容 |
|---|---|
| 提交方式 | `PATCH` |
| URL | `/api/interviews/{interview_id}` |
| 鉴权 | 需要 |

**请求体**（均可选）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `candidate_name` | string \| null | 1–100 字符 | 候选人姓名 |
| `candidate_contact` | string \| null | ≤200 字符 | 传 `null` 表示**清空** |

> 该接口**只改候选人信息，不改状态**。状态迁移一律走动词端点
> （`/complete`、`/rollback`），以避免绕过迁移的前置条件与副作用。

**响应 `200`** —— 更新后的面试详情。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 姓名越界 | `请求参数不合法` |
| 409 | `BUSINESS_ERROR` | 状态为 `evaluating` 或 `evaluated` | `评估中或已评估的面试不可修改候选人信息` |

### 8.6 录入 / 修改回答

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/answers` |
| 鉴权 | 需要 |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `interview_question_id` | integer | 是 | 必须属于该面试 | — |
| `content` | string | 否 | ≤10000 字符，**允许空串** | `""` |

**请求示例**

```json
{ "interview_question_id": 1, "content": "我在上一家公司负责过…" }
```

**响应 `200`** —— 单条题目对象（[§10.6](#106-questionitem)）。

```json
{
  "interview_question_id": 1,
  "seq": 1,
  "content": "请描述一次你处理线上故障的完整过程。",
  "dimension": "沟通能力",
  "source": "bank",
  "answer": "我在上一家公司负责过…",
  "recorded_at": "2026-09-17T10:15:00"
}
```

**幂等语义**：唯一键落在 `interview_question_id` 上 —— **重复保存是更新而非新增**，
同一道面试题永远只有一条回答记录，`recorded_at` 为最后录入时间。前端可以放心地
「每答一题就保存一次」。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `content` 超过 10000 字符 | `请求参数不合法` |
| 404 | `NOT_FOUND` | 面试不存在 / `interview_question_id` 不属于该面试 | `面试不存在` · `题目不属于该面试` |
| 409 | `BUSINESS_ERROR` | 面试非 `ongoing` | `当前状态下不可修改回答，请先回退到进行中` |

### 8.7 标记完成

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/complete` |
| 鉴权 | 需要 |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 面试详情，`status` 为 `completed`，`completed_at` 非空。

**错误**：`409 BUSINESS_ERROR`（当前状态不是 `ongoing`，**含重复调用**）。

### 8.8 回退到进行中

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/rollback` |
| 鉴权 | 需要 |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 面试详情，`status` 为 `ongoing`，`completed_at` 被**清空**。

**错误**：`409 BUSINESS_ERROR`（当前状态不是 `completed` 或 `evaluated`；
**`evaluating` 下不允许回退**）。

---

## 九、评估

### 9.1 触发评估

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/evaluate` |
| 鉴权 | 需要 |

**参数**：仅路径参数。**无请求体。**

**响应 `202`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | 面试 id |
| `status` | string | 恒为 `"evaluating"` |
| `stream_url` | string | SSE 流地址，如 `/api/interviews/1/evaluation/stream` |

```json
{
  "interview_id": 1,
  "status": "evaluating",
  "stream_url": "/api/interviews/1/evaluation/stream"
}
```

> ⚠️ 状态码是 **202 不是 200**。前端判断成功时请用 `response.ok`（202 属于 2xx），
> 而不是 `status === 200`。

**幂等**：若该面试已有正在运行的评估，**不会重复触发**，同样返回 `202` 与**相同的 `stream_url`**。

**孤儿自愈**：若状态为 `evaluating` 但进程内没有对应的运行记录（进程重启遗留），
会先自动回退到 `completed` 再重新开始 —— 面试不会永久卡在「评估中」。

**错误**

| HTTP | code | 触发场景 |
|---|---|---|
| 404 | `NOT_FOUND` | 面试不存在 |
| 403 | `FORBIDDEN` | 面试属于他人 |
| 409 | `BUSINESS_ERROR` | 当前状态不是 `completed` 或 `evaluated`（`detail` 含 from/to） |

> 后端**立即返回**，评估在后台线程中进行。必须单 worker 部署（§2.1）。

### 9.2 SSE 流式评估进度

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}/evaluation/stream` |
| 鉴权 | **需要，且必须走请求头** |

```http
GET /api/interviews/1/evaluation/stream HTTP/1.1
Authorization: Bearer <token>
Accept: text/event-stream
```

> ⚠️ **不能用浏览器原生 `EventSource`** —— 它无法设置自定义请求头，而本项目鉴权
> 完全依赖 `Authorization`。把 JWT 放进 query string 会泄漏到服务器日志、代理日志
> 与浏览器历史。**必须用 `fetch` + `ReadableStream`**，完整实现见 [§12.2](#122-sse-必须用-fetch--readablestream)。

**响应头**

| 头 | 值 |
|---|---|
| `Content-Type` | `text/event-stream; charset=utf-8` |
| `Cache-Control` | `no-cache` |
| `Connection` | `keep-alive` |
| `X-Accel-Buffering` | `no`（阻止 nginx 缓冲流式响应） |

**事件契约**

| 事件名 | 触发时机 | `data` 字段 |
|---|---|---|
| `question` | 每评完一道题 | `interview_question_id` · `seq` · `index`(1 起) · `total` · `dimension` · `score` · `comment` |
| `dimension` | 每评完一个维度 | `dimension` · `index`(1 起) · `total` · `score` · `comment` |
| `report` | 汇总完成 | `overall_score` · `conclusion` · `strengths`[] · `weaknesses`[] |
| `done` | 全部完成且已落库 | `status`: `"evaluated"` |
| `error` | 评估失败（状态已回退） | `code` · `message` |
| `ping` | 心跳，每 15 秒 | 无（注释行 `: ping`，**不产出事件**） |

**事件顺序**：`question`（按 `seq` 升序，共 N 条）→ `dimension`（按维度顺序，共 M 条）→ `report`（恰好 1 条）→ `done` **或** `error`。

> **`done` 与 `error` 互斥且必有其一** —— 流不会在没有终结事件的情况下静默结束。
> 前端应以这两个事件之一作为「关闭连接」的信号。

**报文示例**

```
event: question
data: {"interview_question_id":1,"seq":1,"index":1,"total":8,"dimension":"沟通能力","score":7.0,"comment":"回答基本切题…"}

event: question
data: {"interview_question_id":2,"seq":2,"index":2,"total":8,"dimension":"专业能力","score":6.0,"comment":"…"}

event: dimension
data: {"dimension":"沟通能力","index":1,"total":3,"score":7.0,"comment":"沟通能力维度表现中等…"}

event: report
data: {"overall_score":6.5,"conclusion":"整体表现良好，建议结合岗位要求综合评估。","strengths":["沟通能力（7.0）：表现较好","专业能力（7.0）：表现较好"],"weaknesses":["逻辑思维（6.0）：有待提升","文化契合（6.0）：有待提升"]}

event: done
data: {"status":"evaluated"}

: ping
```

**连接生命周期与断线重连**

| 场景 | 行为 |
|---|---|
| 连接时评估已在运行 | **先重放已推送的全部事件**，再实时转发后续事件 |
| 连接时评估已完成、运行记录仍在 | 重放完整事件序列（含 `done`）后关闭 |
| 连接时评估已完成、运行记录已被清理 | 从数据库**合成**完整事件序列后关闭 |
| 状态非 `evaluated` 且无运行记录 | 推送 `error`（`BUSINESS_ERROR` / `当前无可用的评估进度`）后关闭 |
| 客户端断开 | **只移除订阅者，后台评估继续执行**；重连后从头重放 |
| 评估中途失败 | 推送 `error`，状态回退到 `completed`，数据库无残留，可重新触发 |

> **重放是设计特性而非缺陷**：刷新页面 / 断线重连后，前端会重新收到从第 1 条开始的
> 完整事件序列。前端累加进度时应**按 `index` 覆盖而非追加**，避免出现重复行。

`error` 事件的 `code` 取值：`AI_PROVIDER_ERROR`（AI 调用失败）、`INTERNAL_ERROR`（落库等内部错误）。

**错误**：`401`（未认证）/ `403`（他人面试）/ `404`（面试不存在）。

### 9.3 获取报告

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}/report` |
| 鉴权 | 需要 |

**参数**：仅路径参数。

**响应 `200`** —— 完整报告（[§10.7](#107-reportdetail)）。

```json
{
  "interview_id": 1,
  "candidate_name": "张三",
  "position_name": "后端工程师",
  "overall_score": 6.5,
  "conclusion": "整体表现良好，建议结合岗位要求综合评估。",
  "strengths": [
    "沟通能力（7.0）：表现较好",
    "专业能力（7.0）：表现较好"
  ],
  "weaknesses": [
    "逻辑思维（6.0）：有待提升",
    "文化契合（6.0）：有待提升"
  ],
  "evaluated_at": "2026-09-17T10:30:00",
  "dimension_scores": [
    { "dimension": "沟通能力", "score": 7.0, "comment": "表达清晰，条理分明。" },
    { "dimension": "专业能力", "score": 7.0, "comment": "技术基础扎实。" },
    { "dimension": "逻辑思维", "score": 6.0, "comment": "分析深度有待加强。" },
    { "dimension": "文化契合", "score": 6.0, "comment": "价值观基本一致。" }
  ],
  "question_scores": [
    {
      "interview_question_id": 1,
      "seq": 1,
      "content": "请描述一次你处理线上故障的完整过程。",
      "dimension": "沟通能力",
      "answer": "我在上一家公司负责过…",
      "score": 7.0,
      "comment": "回答基本切题，能说清处理步骤。"
    }
  ]
}
```

> 上面这组数字是**自洽的**：`overall_score` 是 4 个维度分的算术平均
> （(7+7+6+6)/4 = 6.5）；`strengths` 收录 ≥ 6.5 的维度、`weaknesses` 收录 < 6.5 的维度；
> 6.5 落在「整体表现良好」区间。`dimension_scores` 的条数**等于岗位的维度数**。

> **报告可独立渲染**：`question_scores[].content` / `dimension` / `answer` 取自
> **面试快照**，无需再发第二次请求去查题目或回答。`evaluated_at` 为报告最后更新时间。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 409 | `BUSINESS_ERROR` | 状态不是 `evaluated` | `评估尚未完成` |

> 前端刷新报告页时，若拿到 `409 评估尚未完成`，应回到 SSE 流继续等待，
> 而不是当成错误提示。

---

## 十、数据模型

### 10.1 UserOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `username` | string | 全局唯一 |
| `role` | string | `admin` \| `hr` |
| `is_active` | boolean | 禁用后旧 token 立即失效 |
| `created_at` | datetime | |

### 10.2 PositionOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `name` | string | 同一创建人下唯一 |
| `jd` | string | |
| `evaluation_dimensions` | string[] | 已 strip、保留原始大小写 |
| `created_by` | integer | 数据隔离键 |
| `created_at` | datetime | |

### 10.3 QuestionOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `position_id` | integer | |
| `category` | string | 未指定时为 `"通用"` |
| `dimension` | string | 必属该岗位的评估维度 |
| `content` | string | 题干 |
| `difficulty` | string | `easy` \| `medium` \| `hard` |
| `tags` | string[] | |
| `source` | string | `bank` \| `ai` |
| `created_by` | integer | 数据隔离键 |
| `created_at` | datetime | |

### 10.4 InterviewListItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `position_id` | integer | |
| `position_name` | string | 关联岗位名 |
| `candidate_name` | string | |
| `candidate_contact` | string \| null | |
| `status` | string | 见 [§8.1](#81-状态机) |
| `created_at` | datetime | |
| `completed_at` | datetime \| null | 回退时清空 |
| `question_count` | integer | 题目总数 |
| `answered_count` | integer | **非空**回答数 |

### 10.5 InterviewDetail

继承 `InterviewListItem`，并新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| `jd` | string | 岗位 JD |
| `evaluation_dimensions` | string[] | 岗位**当前**的维度 |
| `questions` | QuestionItem[] | 按 `seq` 升序 |

### 10.6 QuestionItem

面试内的题目。`interview_question_id` 是保存回答时使用的 id。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | **保存回答时使用这个 id** |
| `seq` | integer | 从 1 连续 |
| `content` | string | 取自出题时的快照 |
| `dimension` | string | 取自快照 |
| `source` | string | `bank` \| `ai`，取自快照 |
| `answer` | string \| null | 未作答案为 `null` |
| `recorded_at` | datetime \| null | 最后录入时间 |

### 10.7 ReportDetail

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | |
| `candidate_name` | string | |
| `position_name` | string | |
| `overall_score` | number | 0.0–10.0，1 位小数 |
| `conclusion` | string | 综合结论 |
| `strengths` | string[] | 优点，取自维度分 **≥ 6.5** 的维度，**永不为空**（无则给占位文案 `本次面试暂无明显优势维度`） |
| `weaknesses` | string[] | 待改进，取自维度分 **< 6.5** 的维度，**永不为空**（无则给 `本次面试暂无明显薄弱维度`） |
| `evaluated_at` | datetime | 报告最后更新时间 |
| `dimension_scores` | DimensionScoreItem[] | 供雷达图 |
| `question_scores` | QuestionScoreItem[] | 逐题明细，按 `seq` 升序 |

**DimensionScoreItem**

| 字段 | 类型 |
|---|---|
| `dimension` | string |
| `score` | number |
| `comment` | string |

**QuestionScoreItem**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | |
| `seq` | integer | |
| `content` | string | 快照题干 |
| `dimension` | string | 快照维度 |
| `answer` | string \| null | 候选人回答 |
| `score` | number | 0.0–10.0，1 位小数 |
| `comment` | string | 评语 |

---

## 十一、完整流程示例

一次完整的面试生命周期（`PROVIDER_NAME=mock`）。

### 11.1 curl 版

```bash
# 0. 登录
curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin12345"}'
# → {"token":"eyJ...","user":{...}}

TOKEN="eyJ..."

# 1. 建岗位（4 个评估维度）
curl -s -X POST http://localhost:8000/api/positions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"后端工程师","jd":"负责后端服务开发…","evaluation_dimensions":["沟通能力","专业能力","逻辑思维","文化契合"]}'
# → {"id":1, ...}

# 2. 建一道手工题
curl -s -X POST http://localhost:8000/api/questions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"position_id":1,"dimension":"沟通能力","content":"请描述一次你处理线上故障的完整过程。"}'
# → {"id":1,"source":"bank", ...}

# 3. 创建面试 —— 同步出题，共 8 题（seq 1..8）
curl -s -X POST http://localhost:8000/api/interviews \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"position_id":1,"candidate_name":"张三"}'
# → {"id":1,"status":"ongoing","question_count":8,"questions":[...]}

# 4. 逐题录入回答（用 interview_question_id）
curl -s -X POST http://localhost:8000/api/interviews/1/answers \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"interview_question_id":1,"content":"我在上一家公司负责过…"}'

# 5. 标记完成
curl -s -X POST http://localhost:8000/api/interviews/1/complete \
  -H "Authorization: Bearer $TOKEN"
# → {"status":"completed","completed_at":"2026-09-17T10:20:00"}

# 6. 触发评估
curl -s -X POST http://localhost:8000/api/interviews/1/evaluate \
  -H "Authorization: Bearer $TOKEN"
# → {"interview_id":1,"status":"evaluating","stream_url":"/api/interviews/1/evaluation/stream"}

# 7. 订阅 SSE（-N 关闭 curl 的缓冲）
curl -N http://localhost:8000/api/interviews/1/evaluation/stream \
  -H "Authorization: Bearer $TOKEN"
# → event: question / dimension / report / done …

# 8. 读取完整报告
curl -s http://localhost:8000/api/interviews/1/report \
  -H "Authorization: Bearer $TOKEN"
# → {"overall_score":6.5,"conclusion":"…", ...}

# 9.（可选）回退后修改回答并重新完成
curl -s -X POST http://localhost:8000/api/interviews/1/rollback -H "Authorization: Bearer $TOKEN"
```

### 11.2 前端 JS 版

```js
const BASE = '/api';

async function request(method, path, body) {
  const token = localStorage.getItem('token');

  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    // fetch 本身失败（后端没起、断网）—— 没有 HTTP 状态码可读
    const err = new Error('网络连接失败，请检查后端服务');
    err.code = 'NETWORK_ERROR';
    throw err;
  }

  if (res.status === 204) return null;              // 删除接口无响应体

  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(payload?.message || `请求失败（${res.status}）`);
    err.code = payload?.code || 'UNKNOWN';
    err.detail = payload?.detail || null;
    err.status = res.status;
    throw err;                                       // 文案直接用后端的 message
  }
  return payload;
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
};

// 用法
const { token } = await api.post('/auth/login', { username: 'admin', password: 'admin12345' });
localStorage.setItem('token', token);

const positions = await api.get('/positions?keyword=后端');
const interview = await api.post('/interviews', { position_id: 1, candidate_name: '张三' });
await api.post(`/interviews/${interview.id}/answers`, {
  interview_question_id: interview.questions[0].interview_question_id,
  content: '…',
});
```

---

## 十二、前端对接要点

### 12.1 统一错误处理

后端所有错误都返回 `{code, message, detail}`，因此前端只需一个拦截器：

```js
function toUserMessage(err) {
  switch (err.code) {
    case 'NETWORK_ERROR':   return '无法连接服务器，请确认后端已启动';
    case 'UNAUTHORIZED':    return err.message;   // 后端已给中文文案，如「用户名或密码错误」
    case 'INVALID_TOKEN':   return '登录已过期，请重新登录';   // 同时清 token 并跳登录
    case 'FORBIDDEN':       return err.message;   // 如「无权限访问该面试」
    case 'NOT_FOUND':       return '内容不存在或已被删除';
    case 'BUSINESS_ERROR':  return err.message;   // 状态机冲突等，文案直接可用
    case 'AI_PROVIDER_ERROR': return 'AI 服务暂时不可用，请稍后重试';
    case 'INTERNAL_ERROR':  return '服务器出错了，请稍后重试';
    default:                return err.message || '操作失败，请重试';
  }
}
```

> **不要自己重写业务文案**：`message` 是后端维护的、经过测试固定的中文文案
> （如 `该岗位已被题库或面试引用，无法删除`），直接展示即可。

**`detail.fields` 用于表单级联报错**：

```js
if (err.code === 'VALIDATION_ERROR' && err.detail?.fields) {
  for (const f of err.detail.fields) {
    showFieldError(f.field, f.message);   // f.field 就是请求体里的字段名
  }
}
```

**401 的两种处理**（推荐在拦截器里统一做）：

| code | 前端动作 |
|---|---|
| `UNAUTHORIZED` | 若来自登录接口 → 提示「用户名或密码错误」；否则 → 清 token，跳登录 |
| `INVALID_TOKEN` | 清 token，跳登录，提示「登录已过期」 |

### 12.2 SSE 必须用 `fetch` + `ReadableStream`

`EventSource` 无法设置 `Authorization` 头，所以必须手写读取循环。
下面这段**改写到自本项目前端实际使用的实现**（`frontend/src/sse.js`，
其中分帧逻辑被抽成纯函数以便单测），可直接复用：

```js
const TERMINAL_EVENTS = new Set(['done', 'error']);

export function sseConnect(path, handlers) {
  const controller = new AbortController();
  const token = localStorage.getItem('token');

  fetch(path, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      Accept: 'text/event-stream',
    },
    signal: controller.signal,
  })
    .then(async (response) => {
      if (response.status === 401) {
        localStorage.removeItem('token');
        handlers.onUnauthorized?.();
        return;
      }
      if (!response.ok) throw new Error(`连接失败（${response.status}）`);
      if (!response.body) throw new Error('响应不支持流式读取');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 按空行切分事件块；尾部不完整部分必须留在 buffer 里
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop();

        for (const block of blocks) {
          const event = parseBlock(block);
          if (!event) continue;                     // 注释行（心跳）不产出事件
          handlers.onEvent?.(event.name, event.data);
          if (TERMINAL_EVENTS.has(event.name)) {
            handlers.onClose?.();
            return;                                  // done / error 一到就收工
          }
        }
      }
      handlers.onClose?.();
    })
    .catch((error) => {
      if (error.name === 'AbortError') return;       // 主动关闭不算错误
      handlers.onError?.(error);                     // 不自动重连，由页面决定
    });

  return { close: () => controller.abort() };
}

function parseBlock(block) {
  let name = 'message';
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith(':')) continue;              // 心跳注释
    if (line.startsWith('event:')) name = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
  }
  if (!dataLines.length) return null;
  try {
    return { name, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    return { name, data: { raw: dataLines.join('\n') } };   // 畸形 JSON 不崩流
  }
}

// 用法
sseConnect(`/api/interviews/${id}/evaluation/stream`, {
  onEvent(name, data) {
    if (name === 'question')   updateQuestionProgress(data);
    if (name === 'dimension')  updateRadar(data);
    if (name === 'report')     showReportSummary(data);
    if (name === 'error')      toast(data.message);
  },
  onClose() { refreshReport(); },     // done 或 error 后刷新完整报告
  onUnauthorized() { gotoLogin(); },
});
```

**三个容易踩的坑**：

| 坑 | 说明 |
|---|---|
| **跨块缓冲** | 一个事件可能被切成两个 chunk。尾部不完整的内容**必须留在 buffer**，与下一个 chunk 拼接后再切 —— 否则会丢事件。上面用 `blocks.pop()` 正是为此。 |
| **心跳不产事件** | `: ping` 是注释行，解析时必须跳过，不能当成事件名。 |
| **重放会重复** | 断线重连后后端**从头重放**全部事件。前端累加进度时要按 `index` / `seq` **覆盖**而不是追加。 |

### 12.3 状态机驱动的 UI

面试详情页的按钮可用性**直接由 `status` 决定**，不需要额外的接口探测：

```js
const can = {
  editAnswer: interview.status === 'ongoing',
  complete:   interview.status === 'ongoing',
  rollback:   ['completed', 'evaluated'].includes(interview.status),
  evaluate:   ['completed', 'evaluated'].includes(interview.status),
  editCandidate: ['ongoing', 'completed'].includes(interview.status),
};
```

这样即便前端状态过期，点击后也只会拿到 `409 BUSINESS_ERROR`（后端是唯一权威）。

### 12.4 其他注意事项

| 项 | 说明 |
|---|---|
| **`interview_question_id`** | 保存回答用的是 `questions[].interview_question_id`，**不是** `seq`，也不是题目 id |
| **`204` 无响应体** | 删除接口返回 204，不要对其调用 `.json()` |
| **`202` 不是失败** | 触发评估返回 202，用 `response.ok` 判断 |
| **创建面试可能较慢** | 该接口**同步出题**。`PROVIDER_NAME=mock`（默认）时几乎瞬时返回；切到真实大模型后耗时会显著上升，前端应准备 loading 态并放宽超时 |
| **列表不分页** | 所有列表返回全量数组；数据量大时靠前端自己控制渲染 |
| **时间无时区** | 形如 `2026-09-17T10:30:00`，按本地时间解析 |

---

## 十三、附录

### 13.1 评审要点（实现侧）

| 项 | 结论 |
|---|---|
| 评分制式 | 统一 **0–10 分**，全部保留 1 位小数；数据库用 `DECIMAL(3,1)`（定点，避免浮点误差累积到总分） |
| 总分算法 | 各维度分的算术平均（Mock Provider 规则） |
| 维度缺失 | Provider 少返回维度时**按实际写入，不补齐、不伪造**；雷达图按实际维度数渲染 |
| 重新评估 | **替换语义** —— 逐题评分与维度评分先清后写，条数不翻倍；报告 upsert 并更新 `updated_at` |
| 失败隔离 | 先推后写：结果在最后一次性落库；失败时数据库要么是上一次的完整结果，要么是这一次的完整结果 |
| AI 调用 | 真实 Provider 失败时**不自动降级到 Mock**，而是报 502 并允许重试 |
| SSE 竞态 | 重放窗口的竞态已修复（`stream_events` 订阅与快照同临界区），保证 `done`/`error` 不会静默丢失 |

### 13.2 文档维护

| 项 | 说明 |
|---|---|
| 契约事实来源 | 各模块 `app/*/schemas.py`（请求 / 响应模型）与 `app/*/router.py`（端点声明） |
| 行为验证来源 | [API 接口测试报告](../tests/2026-09-17-API接口测试报告.md) —— **461 条用例，0 失败** |
| 机器可读契约 | `GET /openapi.json`（注意其中标注的 `422` 已被全局收口为 `400`） |
| 变更时同步 | 修改 `schemas.py` 或路由后，需同步更新本文档与 `docs/tests/` 下的测试报告 |
