# AI 智能面试助手 —— API 接口文档

> 本文档依据 [API 接口测试报告](../tests/2026-09-17-API接口测试报告.md) 整理，
> 请求 / 响应字段取自各模块的 Pydantic 模型（`app/*/schemas.py`），
> 状态码、错误码与业务规则均为**已被 461 条测试用例验证过的实际行为**。

| 项 | 内容 |
|---|---|
| API 版本 | `0.1.0` |
| 基础路径 | `/api` |
| 服务框架 | FastAPI（Python 3.11+） |
| 数据格式 | JSON，UTF-8（`utf8mb4`） |
| 认证方式 | JWT Bearer Token |
| 交互式文档 | `GET /docs`（Swagger UI）、`GET /openapi.json` |
| 契约验证 | `backend/tests/` 461 条用例，0 失败 |

---

## 一、通用约定

### 1.1 服务地址与部署约束

| 环境 | 地址 |
|---|---|
| 本地开发 | `http://localhost:8000` |
| 前端代理 | Vite 将 `/api` 代理至 `http://localhost:8000` |

> **必须单进程运行**：`uvicorn app.main:app --workers 1`。
> 评估的 SSE 运行注册表是**进程内**的，多 worker 会导致 `POST /evaluate` 与
> `GET /evaluation/stream` 落在不同进程而无法衔接（详见 §7.3）。

### 1.2 认证

除 `POST /api/auth/login` 与 `GET /api/health` 外，**所有接口都需要认证**。

```http
Authorization: Bearer <token>
```

| 项 | 说明 |
|---|---|
| token 获取 | `POST /api/auth/login` 返回的 `token` 字段 |
| token 内容 | `sub`（用户 id）、`iat`、`exp`；**不包含 role** |
| 默认有效期 | 720 分钟（12 小时），由 `JWT_EXPIRE_MINUTES` 配置 |
| 过期策略 | 过期后需**重新登录**（未实现 refresh token） |

**三个与 token 相关的重要行为**（均已被测试固定）：

1. 角色不缓存在 JWT 里 —— admin 把某 hr 提升为 admin 后，该用户**用旧 token 即可立即访问**
   `/api/users`，无需重新登录。
2. 账号被禁用后，其**已签发的旧 token 立即失效**（每次请求都回查数据库的 `is_active`）。
3. 伪造 / 篡改 / 换密钥签发的 token 返回 `401 INVALID_TOKEN`，与「未携带 token」的
   `401 UNAUTHORIZED` 区分开。

### 1.3 统一响应格式

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
| `code` | string | 机器可读的错误码，见 §1.4 |
| `message` | string | 可直接展示给用户的中文文案 |
| `detail` | object \| null | 结构化补充信息；参数校验错误时含字段级明细 |

参数校验失败的 `detail` 结构：

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

状态机非法迁移的 `detail` 携带起止状态：

```json
{
  "code": "BUSINESS_ERROR",
  "message": "不允许从「进行中」迁移到「进行中」",
  "detail": { "from": "ongoing", "to": "ongoing" }
}
```

### 1.4 错误码表

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

> 表中「默认」为异常类自带的 `default_message`；业务代码可在抛出时覆盖为更具体的文案
> （如 `面试不存在`），未覆盖时回落到默认值。

> **注意**：FastAPI 默认的参数校验状态码是 `422`，本项目已全局收口为
> **`400 VALIDATION_ERROR`**。OpenAPI 文档中标注的 `422` 不生效，请以 400 为准。

### 1.5 数据隔离规则

| 角色 | 可见范围 |
|---|---|
| `hr` | **仅自己创建的数据**（岗位 / 题目 / 面试三个列表均按 `created_by` 过滤） |
| `admin` | **全部数据**（不做过滤） |

单条资源的判定顺序（全项目统一）：

1. 记录不存在 → `404 NOT_FOUND`
2. 记录存在但不属于当前用户 → `403 FORBIDDEN`（**有意暴露资源存在性**，见 module-08 §7.3-5）

题目额外遵循：**隔离键是题目自身的 `created_by`**，与所属岗位的创建者无关。

### 1.6 通用行为约定

| 项 | 约定 |
|---|---|
| 分页 | **不提供**。所有列表接口返回全量数组（MVP 明确不分页） |
| 排序 | 岗位 / 题目 / 用户按 `id` 升序；面试列表按 `id` **降序**（新的在前）；面试内题目按 `seq` 升序 |
| 时间格式 | ISO 8601 字符串，如 `2026-09-17T10:30:00` |
| 脱敏 | 任何用户相关响应**都不会出现 `password_hash`** |
| 删除 | 均为物理删除；用户不做物理删除，只能禁用 |

---

## 二、系统

### 2.1 健康检查

```http
GET /api/health
```

无需鉴权。

**响应 `200`**

```json
{ "status": "ok" }
```

---

## 三、认证与用户管理

### 3.1 登录

```http
POST /api/auth/login
```

无需鉴权。

**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `username` | string | 是 | 1–50 字符 |
| `password` | string | 是 | 1–128 字符 |

```json
{ "username": "hr_zhang", "password": "hr12345678" }
```

**响应 `200`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `token` | string | JWT，用于后续所有请求 |
| `user` | object | 用户对象（见 §9.1） |

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": { "id": 2, "username": "hr_zhang", "role": "hr", "is_active": true, "created_at": "2026-09-17T10:00:00" }
}
```

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 用户名不存在 **或** 密码错误 | `UNAUTHORIZED` | 401 |
| 账号已禁用 | `UNAUTHORIZED` | 401 |

> 前两种情况的响应**完全相同**（`{"code":"UNAUTHORIZED","message":"用户名或密码错误"}`），
> 且服务端在用户不存在时也执行一次哈希比对以拉平响应时间 —— 防止用户名枚举。

### 3.2 当前登录用户

```http
GET /api/auth/me
```

**响应 `200`** —— 用户对象（§9.1），不含 `password_hash`。

**错误**：`401 UNAUTHORIZED`（未携带 token）/ `401 INVALID_TOKEN`（token 无效）/ `401 UNAUTHORIZED`（用户已被禁用或删除）。

### 3.3 创建用户（仅 admin）

```http
POST /api/users
```

**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `username` | string | 是 | 1–50 字符，**全局唯一** |
| `password` | string | 是 | **最少 8 字符**，最多 128 |
| `role` | string | 是 | `admin` \| `hr` |

**响应 `201`** —— 用户对象（§9.1）。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 非 admin 调用 | `FORBIDDEN` | 403 |
| 用户名已存在 | `BUSINESS_ERROR` | 409（`用户名已存在`） |
| 密码少于 8 位 / 角色非法 | `VALIDATION_ERROR` | 400 |

### 3.4 用户列表（仅 admin）

```http
GET /api/users
```

**响应 `200`** —— 用户对象数组，按 `id` 升序。无分页。

**错误**：`403 FORBIDDEN`（非 admin）。

### 3.5 修改角色 / 启用禁用（仅 admin）

```http
PATCH /api/users/{user_id}
```

**路径参数**：`user_id`（integer）

**请求体**（两个字段均可选，只传需要改的）

| 字段 | 类型 | 约束 |
|---|---|---|
| `role` | string \| null | `admin` \| `hr` |
| `is_active` | boolean \| null | `false` 即禁用 |

**响应 `200`** —— 更新后的用户对象。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 非 admin 调用 | `FORBIDDEN` | 403 |
| 目标用户不存在 | `NOT_FOUND` | 404（`用户不存在`） |
| **admin 修改自己**（角色或状态） | `BUSINESS_ERROR` | 409（`不能修改自己的角色或状态`） |

> 防自锁死：admin 不能把自己降级或禁用，否则系统将没有任何管理员。

---

## 四、岗位

岗位字段：名称、JD、**评估维度列表**。评估维度是后续出题与多维评分的基准。

### 4.1 创建岗位

```http
POST /api/positions
```

**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `name` | string | 是 | 1–100 字符，**同一创建人下唯一** |
| `jd` | string | 是 | 1–10000 字符 |
| `evaluation_dimensions` | string[] | 是 | 见下方维度规则 |

**响应 `201`**

| 字段 | 类型 |
|---|---|
| `id` | integer |
| `name` | string |
| `jd` | string |
| `evaluation_dimensions` | string[] |
| `created_by` | integer |
| `created_at` | datetime |

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

**评估维度校验规则**

| 规则 | 说明 | 违反结果 |
|---|---|---|
| 数量 | 1–10 个 | `400 VALIDATION_ERROR` |
| 单项长度 | 1–50 字符 | `400` |
| 不可为空串 | 纯空白视同空 | `400` |
| 去重 | **strip 后不区分大小写**去重（`"Communication"` 与 `"communication"` 视为重复，`" 沟通 "` 与 `"沟通"` 视为重复） | `400` |
| 落库形态 | 保存 **strip 后、保留原始大小写**的值 | — |

**错误**：`409 BUSINESS_ERROR`（`该岗位名称已存在`，同一创建人重名）。

### 4.2 岗位列表

```http
GET /api/positions
```

**查询参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `keyword` | string | 可选，按 `name` 服务端模糊匹配（`LIKE %keyword%`） |

**响应 `200`** —— 岗位对象数组，按 `id` 升序。hr 仅见自己的，admin 见全部。无分页。

### 4.3 岗位详情

```http
GET /api/positions/{position_id}
```

**响应 `200`** —— 岗位对象。

**错误**：`404 NOT_FOUND`（`岗位不存在`）/ `403 FORBIDDEN`（`无权限访问该岗位`）。

### 4.4 更新岗位

```http
PUT /api/positions/{position_id}
```

**全量替换语义** —— 请求体字段与创建时相同（`name` / `jd` / `evaluation_dimensions` 均必填）。
`evaluation_dimensions` 是**整体替换**而非追加：传 `["C"]` 后原 `["A","B"]` 变为 `["C"]`。

**响应 `200`** —— 更新后的岗位对象。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 改名撞同创建人已有岗位名 | `BUSINESS_ERROR` | 409 |
| 维度非法 | `VALIDATION_ERROR` | 400 |
| 他人岗位 / 不存在 | `FORBIDDEN` / `NOT_FOUND` | 403 / 404 |

> 改名与改 JD 不影响已完成的面试；改维度只影响**此后新触发**的评估，不重算历史评估。

### 4.5 删除岗位

```http
DELETE /api/positions/{position_id}
```

**响应 `204`** —— **无响应体**。

**错误**：`409 BUSINESS_ERROR`（`该岗位已被题库或面试引用，无法删除`）。

> 删除保护由外键 `ON DELETE RESTRICT` 保证，覆盖**两类引用**：岗位下存在题目、
> 或存在引用该岗位的面试（哪怕该岗位下一道题都没有）。

---

## 五、题库

### 5.1 创建题目

```http
POST /api/questions
```

**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `position_id` | integer | 是 | 岗位须存在且当前用户可见 |
| `category` | string \| null | 否 | 1–50 字符，默认 `"通用"` |
| `dimension` | string | 是 | 1–50 字符，**必须属于该岗位的评估维度**（strip 后精确匹配） |
| `content` | string | 是 | **5–2000 字符** |
| `difficulty` | string | 否 | `easy` \| `medium` \| `hard`，默认 `medium` |
| `tags` | string[] | 否 | ≤10 个，单个 1–20 字符，strip 后去重，默认 `[]` |

> `source` **不可由客户端指定** —— 即使请求体里传了 `source: "ai"`，落库仍为 `"bank"`。

**响应 `201`**

| 字段 | 类型 |
|---|---|
| `id` | integer |
| `position_id` | integer |
| `category` | string |
| `dimension` | string |
| `content` | string |
| `difficulty` | string |
| `tags` | string[] |
| `source` | string（`bank` \| `ai`） |
| `created_by` | integer |
| `created_at` | datetime |

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 岗位不存在 | `NOT_FOUND` | 404 |
| 岗位不可见（他人的） | `FORBIDDEN` | 403 |
| 维度不属该岗位 | `VALIDATION_ERROR` | 400（`detail.allowed` 含合法维度列表） |
| `content` 过短 / 过长、`tags` 超限、`difficulty` 非法 | `VALIDATION_ERROR` | 400 |

### 5.2 题目列表

```http
GET /api/questions
```

**查询参数**（多个条件之间为 **AND** 关系）

| 参数 | 类型 | 匹配方式 |
|---|---|---|
| `position_id` | integer | 按岗位过滤 |
| `category` | string | **精确**匹配 |
| `dimension` | string | **精确**匹配 |
| `source` | string | `bank` \| `ai` |
| `keyword` | string | 按 `content` 模糊匹配 |

**响应 `200`** —— 题目对象数组，按 `id` 升序。筛选**不会越过数据隔离边界**：即便筛选条件完全匹配，也只会返回自己（hr）或全部（admin）的题目。无分页。

### 5.3 题目详情

```http
GET /api/questions/{question_id}
```

**响应 `200`** —— 题目对象。

**错误**：`404 NOT_FOUND`（`题目不存在`）/ `403 FORBIDDEN`。

### 5.4 更新题目

```http
PUT /api/questions/{question_id}
```

**全量替换语义**，字段与创建时相同（`tags` 整体替换）。

`position_id` **可以改** —— 改到其他岗位时会**重新校验** `dimension` 是否属于新岗位，不属于则 `400`。

**响应 `200`** —— 更新后的题目对象。

### 5.5 删除题目

```http
DELETE /api/questions/{question_id}
```

**响应 `204`** —— **无响应体**。

**错误**：`409 BUSINESS_ERROR`（`该题目已被面试引用，无法删除`）。

---

## 六、面试

### 6.1 状态机

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

**各状态下的操作矩阵**

| 操作 | draft | ongoing | completed | evaluating | evaluated |
|---|---|---|---|---|---|
| 查看详情 | ✗ | ✓ | ✓ | ✓ | ✓ |
| 改候选人信息 | ✗ | ✓ | ✓ | ✗ | ✗ |
| 录入 / 修改回答 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 标记完成 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 回退到进行中 | ✗ | ✗ | ✓ | ✗ | ✓ |
| 触发评估 | ✗ | ✗ | ✓ | ✗ | ✓（重评） |

### 6.2 创建面试（同步出题）

```http
POST /api/interviews
```

**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `position_id` | integer | 是 | 岗位须存在且可见 |
| `candidate_name` | string | 是 | 1–100 字符 |
| `candidate_contact` | string \| null | 否 | ≤200 字符 |

**响应 `201`** —— 面试详情对象（§9.4）。

**出题组装规则**（同步完成，是创建接口的一部分）

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

| 场景 | code | HTTP |
|---|---|---|
| 岗位不存在 / 不可见 | `NOT_FOUND` / `FORBIDDEN` | 404 / 403 |
| 候选人姓名越界 | `VALIDATION_ERROR` | 400 |
| **AI 出题失败** | `AI_PROVIDER_ERROR` | **502** |

> AI 失败时**整个事务回滚** —— 面试与 AI 题目都不会残留，客户端可直接重试。

### 6.3 面试列表

```http
GET /api/interviews
```

**响应 `200`** —— 面试列表项数组（§9.3），按 `id` **降序**。无分页、无筛选参数。

`question_count` 为题目总数；`answered_count` 只统计**非空回答**（空串表示未作答，不计入）。

### 6.4 面试详情

```http
GET /api/interviews/{interview_id}
```

**响应 `200`** —— 面试详情（§9.4），`questions` 按 `seq` 升序。

未作答的题目 `answer` 与 `recorded_at` 均为 `null`。

### 6.5 更新候选人信息

```http
PATCH /api/interviews/{interview_id}
```

**请求体**（均可选）

| 字段 | 类型 | 约束 |
|---|---|---|
| `candidate_name` | string \| null | 1–100 字符 |
| `candidate_contact` | string \| null | ≤200 字符，传 `null` 表示清空 |

> 该接口**只改候选人信息，不改状态**。状态迁移一律走动词端点（`/complete`、`/rollback`），
> 以避免绕过迁移的前置条件与副作用。

**响应 `200`** —— 更新后的面试详情。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 面试处于 `evaluating` 或 `evaluated` | `BUSINESS_ERROR` | 409（`评估中或已评估的面试不可修改候选人信息`） |
| 姓名越界 | `VALIDATION_ERROR` | 400 |

### 6.6 录入 / 修改回答

```http
POST /api/interviews/{interview_id}/answers
```

**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `interview_question_id` | integer | 是 | 必须属于该面试 |
| `content` | string | 否 | ≤10000 字符，**允许空串**（表示候选人未作答），默认 `""` |

**响应 `200`** —— 单条题目对象（§9.5）。

**幂等语义**：唯一键落在 `interview_question_id` 上 —— **重复保存是更新而非新增**，
同一道面试题永远只有一条回答记录，`recorded_at` 为最后录入时间。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 面试非 `ongoing` | `BUSINESS_ERROR` | 409（`当前状态下不可修改回答，请先回退到进行中`） |
| `interview_question_id` 不属于该面试 | `NOT_FOUND` | 404（`题目不属于该面试`） |
| `content` 超过 10000 字符 | `VALIDATION_ERROR` | 400 |

### 6.7 标记完成

```http
POST /api/interviews/{interview_id}/complete
```

无请求体。

**响应 `200`** —— 面试详情，`status` 为 `completed`，`completed_at` 非空。

**错误**：`409 BUSINESS_ERROR`（当前状态不是 `ongoing`，含重复调用）。

### 6.8 回退到进行中

```http
POST /api/interviews/{interview_id}/rollback
```

无请求体。

**响应 `200`** —— 面试详情，`status` 为 `ongoing`，`completed_at` 被**清空**。

**错误**：`409 BUSINESS_ERROR`（当前状态不是 `completed` 或 `evaluated`；`evaluating` 下不允许回退）。

---

## 七、评估

### 7.1 触发评估

```http
POST /api/interviews/{interview_id}/evaluate
```

无请求体。

**响应 `202`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | 面试 id |
| `status` | string | 恒为 `"evaluating"` |
| `stream_url` | string | SSE 流地址，如 `/api/interviews/1/evaluation/stream` |

**幂等**：若该面试已有正在运行的评估，**不会重复触发**，同样返回 `202` 与**相同的 `stream_url`**。

**孤儿自愈**：若状态为 `evaluating` 但进程内没有对应的运行记录（进程重启遗留），
会先自动回退到 `completed` 再重新开始 —— 面试不会永久卡在「评估中」。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 面试不存在 / 不可见 | `NOT_FOUND` / `FORBIDDEN` | 404 / 403 |
| 当前状态不是 `completed` 或 `evaluated` | `BUSINESS_ERROR` | 409（`detail` 含 from/to） |

> 后端**立即返回**，评估在后台线程中进行。必须单 worker 部署（§1.1）。

### 7.2 获取报告

```http
GET /api/interviews/{interview_id}/report
```

**响应 `200`** —— 完整报告（§9.6）。

**错误**

| 场景 | code | HTTP |
|---|---|---|
| 状态不是 `evaluated` | `BUSINESS_ERROR` | 409（`评估尚未完成`） |
| 面试不存在 / 不可见 | `NOT_FOUND` / `FORBIDDEN` | 404 / 403 |

> 报告可以独立渲染：`question_scores[].content` / `dimension` / `answer` 取自**面试快照**，
> 无需再发第二次请求。`evaluated_at` 为报告最后更新时间。

### 7.3 SSE 流式评估进度

```http
GET /api/interviews/{interview_id}/evaluation/stream
Authorization: Bearer <token>
```

**必须通过 `Authorization` 请求头认证** —— 客户端需使用 `fetch` + `ReadableStream` 读取，
**不能用 `EventSource`**（它无法设置请求头，把 JWT 放进 query string 会泄漏到日志与浏览器历史）。

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
| `ping` | 心跳，每 15 秒 | 无（注释行 `: ping`） |

**事件顺序**：`question`（按 `seq` 升序，共 N 条）→ `dimension`（按维度顺序，共 M 条）→ `report`（恰好 1 条）→ `done` 或 `error`。

> **`done` 与 `error` 互斥且必有其一** —— 流不会在没有终结事件的情况下静默结束。

**报文示例**

```
event: question
data: {"interview_question_id":1,"seq":1,"index":1,"total":8,"dimension":"沟通能力","score":7.0,"comment":"回答基本切题…"}

event: dimension
data: {"dimension":"沟通能力","index":1,"total":3,"score":7.0,"comment":"沟通能力维度表现中等…"}

event: report
data: {"overall_score":7.3,"conclusion":"整体表现良好…","strengths":["专业能力（8.0）：表现较好"],"weaknesses":["逻辑思维（6.0）：有待提升"]}

event: done
data: {"status": "evaluated"}

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

`error` 事件的 `code` 取值：`AI_PROVIDER_ERROR`（AI 调用失败）、`INTERNAL_ERROR`（落库等内部错误）。

**错误**：`401`（未认证）/ `403`（他人面试）/ `404`（面试不存在）。

---

## 八、完整流程示例

以下为一次完整的面试生命周期（`PROVIDER_NAME=mock`，`TOKEN` 为登录后取得）。

```bash
# 0. 登录
curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"hr_zhang","password":"hr12345678"}'
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

# 4. 逐题录入回答（先用 interview_question_id）
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

# 7. 订阅 SSE（注意用 -N 关闭缓冲；浏览器端用 fetch + ReadableStream）
curl -N http://localhost:8000/api/interviews/1/evaluation/stream \
  -H "Authorization: Bearer $TOKEN"
# → event: question / dimension / report / done …

# 8. 读取完整报告
curl -s http://localhost:8000/api/interviews/1/report \
  -H "Authorization: Bearer $TOKEN"
# → {"overall_score":7.3,"conclusion":"…","strengths":[…],"weaknesses":[…],"dimension_scores":[…],"question_scores":[…]}

# 9.（可选）回退后修改回答并重新完成
curl -s -X POST http://localhost:8000/api/interviews/1/rollback -H "Authorization: Bearer $TOKEN"
```

---

## 九、数据模型

### 9.1 UserOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `username` | string | 全局唯一 |
| `role` | string | `admin` \| `hr` |
| `is_active` | boolean | 禁用后旧 token 立即失效 |
| `created_at` | datetime | |

### 9.2 PositionOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `name` | string | 同一创建人下唯一 |
| `jd` | string | |
| `evaluation_dimensions` | string[] | 已 strip、保留原始大小写 |
| `created_by` | integer | 数据隔离键 |
| `created_at` | datetime | |

### 9.3 InterviewListItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `position_id` | integer | |
| `position_name` | string | 关联岗位名 |
| `candidate_name` | string | |
| `candidate_contact` | string \| null | |
| `status` | string | 见 §6.1 |
| `created_at` | datetime | |
| `completed_at` | datetime \| null | 回退时清空 |
| `question_count` | integer | 题目总数 |
| `answered_count` | integer | **非空**回答数 |

### 9.4 InterviewDetail

继承 `InterviewListItem`，并新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| `jd` | string | 岗位 JD |
| `evaluation_dimensions` | string[] | 岗位**当前**的维度 |
| `questions` | QuestionItem[] | 按 `seq` 升序 |

### 9.5 QuestionItem（面试内的题目）

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | **保存回答时使用这个 id** |
| `seq` | integer | 从 1 连续 |
| `content` | string | 取自出题时的快照 |
| `dimension` | string | 取自快照 |
| `source` | string | `bank` \| `ai`，取自快照 |
| `answer` | string \| null | 未作答案为 `null` |
| `recorded_at` | datetime \| null | 最后录入时间 |

### 9.6 ReportDetail

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | |
| `candidate_name` | string | |
| `position_name` | string | |
| `overall_score` | number | 0.0–10.0，1 位小数 |
| `conclusion` | string | 综合结论 |
| `strengths` | string[] | 优点，**永不为空**（无则给占位文案） |
| `weaknesses` | string[] | 待改进，**永不为空** |
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

## 十、评审要点

| 项 | 结论 |
|---|---|
| 评分制式 | 统一 **0–10 分**，全部保留 1 位小数；数据库用 `DECIMAL(3,1)`（定点，避免浮点误差累积到总分） |
| 总分算法 | 各维度分的算术平均（Mock Provider 规则） |
| 维度缺失 | Provider 少返回维度时**按实际写入，不补齐、不伪造**；雷达图按实际维度数渲染 |
| 重新评估 | **替换语义** —— 逐题评分与维度评分先清后写，条数不翻倍；报告 upsert 并更新 `updated_at` |
| 失败隔离 | 先推后写：结果在最后一次性落库；失败时数据库要么是上一次的完整结果，要么是这一次的完整结果 |
| AI 调用 | 真实 Provider 失败时**不自动降级到 Mock**，而是报 502 并允许重试 |

---

## 附：文档维护

| 项 | 说明 |
|---|---|
| 契约事实来源 | 各模块 `app/*/schemas.py`（请求 / 响应模型）与 `app/*/router.py`（端点声明） |
| 行为验证来源 | [`docs/tests/2026-09-17-API接口测试报告.md`](../tests/2026-09-17-API接口测试报告.md) —— 461 条用例 0 失败 |
| 机器可读契约 | `GET /openapi.json`（注意其中标注的 `422` 已被全局收口为 `400`） |
| 变更时同步 | 修改 `schemas.py` 或路由后，需同步更新本文档与 `docs/tests/` 下的测试报告 |
