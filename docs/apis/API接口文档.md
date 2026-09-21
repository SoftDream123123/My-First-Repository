# AI 智能面试助手 —— API 接口文档

> **面向对象：前端 / 客户端开发者。** 每个接口都给出「提交方式 · URL · 参数 · 响应 · 示例」，
> 可直接照抄对接。
>
> 每一条状态码、错误码与业务规则都**来自本项目的计划书或 `openapi.json`**，不是凭空推测。
> 但**两者的可信度不同** —— 下表如实区分，看的时候请按需取信。

| 项 | 内容 |
|---|---|
| API 版本 | `0.1.0` |
| 文档覆盖 | **MVP-1 + MVP-2 + MVP-3**（截至 2026-09-21） |
| 基础路径 | `/api` |
| 服务框架 | FastAPI（Python 3.11+） |
| 数据格式 | JSON，UTF-8（`utf8mb4`） |
| 认证方式 | JWT Bearer Token |
| 三种角色 | `admin` · `hr`（HR / 面试官端）· `candidate`（候选人端） |
| 接口总数 | **59 个 method-route / 43 条路径** |
| 契约来源 | `GET /openapi.json`（字段与类型）+ `docs/superpowers/specs/` 各模块计划书（业务规则、状态码） |
| 交互式文档 | `GET /docs`（Swagger UI）、`GET /openapi.json` |

**关于本文件的验证基础**（如实说明，便于判断可信度）：

| 部分 | 依据 |
|---|---|
| MVP-1 的 26 个 route | 有 HTTP 层用例逐条验证，见 [API 接口测试报告（2026-09-17）](../tests/2026-09-17-API接口测试报告.md) |
| MVP-2 / MVP-3 新增的 33 个 route | **尚无专门的接口层报告**。其字段与类型取自 `app.openapi()`，业务规则与状态码取自各模块计划书 |

> 计划书是这些接口的契约来源，**不要用 `/openapi.json` 里的 422 标注反推**（见下）。

> **关于 `422`**：FastAPI 默认的参数校验状态码已被全局收口为 **`400 VALIDATION_ERROR`**，
> `/openapi.json` 里标注的 422 不生效。
>
> **全项目只有一处例外，它刻意保留 422**：简历正文超长
> （`POST` / `PUT /api/candidate/resumes`，正文 > 20000 字符）。因为该校验绕开 Pydantic、
> 由 service 层抛出业务异常实现 —— 若交给 Pydantic，会被 `main.py` 统一改写成 400，
> 与 PRD §7 要求的 422 不符。详见 [§十一](#十一简历管理候选人端)。

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
- [十、候选人端 —— 在线作答](#十候选人端--在线作答)
- [十一、简历管理（候选人端）](#十一简历管理候选人端)
- [十二、刷题练习（候选人端）](#十二刷题练习候选人端)
- [十三、数据模型](#十三数据模型)
- [十四、完整流程示例](#十四完整流程示例)
- [十五、前端对接要点](#十五前端对接要点)
- [十六、附录](#十六附录)

**两端分工**（决定每个接口该用哪种 token）：

| 端 | 角色 | 章节 |
|---|---|---|
| HR / 面试官端 | `admin` · `hr` | 四、五、六、七、八、九 |
| 候选人端 | `candidate` | 十、十一、十二 |

> ⚠️ 角色守卫是**精确匹配、无继承**：`admin` **不能**调用候选人端接口，`candidate`
> **不能**调用 HR 端接口，两个方向都返回 `403 FORBIDDEN`。详见表 [§2.2](#22-认证)。

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

1. **除了登录、健康检查、候选人自助注册这三个，所有接口都要 `Authorization: Bearer <token>`**。
   两个端的 token **不能混用**（HR 的 token 调候选人接口是 403，反之亦然）。
2. **所有错误响应结构完全一致**（`{code, message, detail}`），写一个统一拦截器即可。
3. **评估进度是 SSE 流，且必须带 `Authorization` 头** —— 所以**不能用浏览器原生
   `EventSource`**，要用 `fetch` + `ReadableStream`。完整实现见 [§15.2](#152-sse-必须用-fetch--readablestream)。

> 同一个浏览器里**两个端要同时登录**时，token 必须**按端分 key 存**（如 `hr.token` /
> `candidate.token`），不要共用一个 localStorage key，否则互相顶掉。后端不做区分，
> 同一个 key 下后登录的会覆盖先登录的。详见 [§十五](#十五前端对接要点)。

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

**只有三个接口不需要认证**：`GET /api/health`、`POST /api/auth/login`、
`POST /api/auth/register`（候选人自助注册）。其余全部需要：

```http
Authorization: Bearer <token>
```

**按路径前缀划分的角色守卫**（精确匹配，无角色继承）：

| 路径前缀 | 允许的角色 | 不符合时 |
|---|---|---|
| `/api/health`、`/api/auth/login`、`/api/auth/register` | **公开** | — |
| `/api/auth/me` | 任意已登录角色 | 401 |
| `/api/users*` | **仅 `admin`** | 403 |
| `/api/positions*`、`/api/questions*`、`/api/interviews*`（含 `report` / `export` / `stream`） | `admin` · `hr` | 403 |
| `/api/candidate/*`、`/api/practice/*` | **仅 `candidate`** | 403 |

> ⚠️ **`admin` 不通过候选人端的守卫**。`require_roles` 是集合精确匹配，不是「admin 通吃」。
> 反之 `candidate` 调 HR 端接口也是 403。两个方向都是 `403 FORBIDDEN`，
> 且**守卫先于请求体校验** —— 即使 body 是空的，角色不符仍返回 403 而不是 400。

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

**应用内抛出的错误**共用同一结构：

> ⚠️ **但有三种情况不适用** —— 它们由 Starlette 在**路由层**直接返回，
> 根本进不到项目的异常处理器，因此响应体是 `{"detail": "..."}`，**没有 `code` 字段**：
>
> | 场景 | 状态码 | 响应体 |
> |---|---|---|
> | 路径拼错（路由不存在） | 404 | `{"detail": "Not Found"}` |
> | 方法不对（如对 `/api/health` 发 `DELETE`） | 405 | `{"detail": "Method Not Allowed"}` |
>
> **前端写统一错误拦截器时必须容忍 body 里没有 `code`** —— 否则自己拼错 URL 时会崩在拦截器里。
> 这两种情况只会由前端笔误引起，正常业务流量不会遇到。
> （此结论由 `backend/tests/api/test_api_health_and_errors.py` 钉住。）

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
| `AI_PROVIDER_ERROR` | 502 | AI 调用失败（重试 1 次后仍失败）：出题 / 补题 / 准备提纲 / 评估 / 候选人反馈 | `AI 服务调用失败，请稍后重试` |
| `VALIDATION_ERROR` | **422** | **仅一处**：简历正文超过 20000 字符 | `简历正文不能超过 20000 字符` |

> 表中「默认」为异常类自带的文案；业务代码可在抛出时覆盖为更具体的文案
> （如 `面试不存在`），未覆盖时回落到默认值。**前端展示 `message` 即可，不必自己映射**。

#### AI 不可用时，「降级」与「失败」要分开处理

AI 失败**不总是**报错。有些场景按设计**静默降级**，请求仍然成功 —— 前端必须能区分，
否则会把「降级」当成「功能正常」而漏掉提示：

| 场景 | AI 失败时的表现 | 前端应做什么 |
|---|---|---|
| 出题组装（`POST /interviews`） | **502**，事务整体回滚，无残留 | 提示失败，让 HR 重试 |
| 按简历补题（`POST /interviews/{id}/questions/match`） | **502**，不动既有题目、不改面试状态 | 提示失败，可重试 |
| 准备提纲（`POST /interviews/{id}/prep`） | **502**，已生成的旧内容与 `generated_at` 不变 | 提示失败，保留页面上原有内容 |
| 流式评估 | SSE 推 `error` 事件，状态回退 `completed` | 显示失败并允许重新触发 |
| 候选人反馈生成 | **502**，不写缓存 | 提示稍后再试 |
| 刷题 —— 简答判分 | **200**，作答正常落库，`is_correct` / `score` 为 `null`，`explanation` 为「AI 判分暂时不可用，本题稍后可重判」 | 显示「未判分」，提供「重新判分」入口 |
| 刷题 —— 按简历推荐取题 | **201**，练习已创建，但 `resume_match_applied=false`（已退回普通筛选） | 当 `resume_id != null && resume_match_applied === false` 时**显示降级说明** |
| 生成参考答案（`POST /questions/{id}/reference-answer`） | **502**，题目内容不变 | 提示失败，允许手工填写 |

### 2.5 数据隔离规则

| 角色 | 可见范围 |
|---|---|
| `hr` | **仅自己创建的数据**（岗位 / 题目 / 面试三个列表均按 `created_by` 过滤） |
| `admin` | **全部数据**（不做过滤） |
| `candidate` | **仅自己的**：练习数据（`practice_*`）、自己的简历、以及**自己已接受邀请**的那几场面试的题目与本人作答 |

单条资源的判定顺序（HR 端全项目统一，前端可据此设计提示文案）：

1. 记录不存在 → `404 NOT_FOUND`
2. 记录存在但不属于当前用户 → `403 FORBIDDEN`（**有意暴露资源存在性**）

**候选人侧用的是另一套判据**，与 `created_by` 无关：

| 资源 | 判据 | 位置 |
|---|---|---|
| 面试（题目 / 作答 / 反馈 / 关联简历） | **是否存在该面试下、绑定本人、且状态为 `accepted` 的有效邀请** | `interview` 模块 |
| 简历、练习会话 | `created_by == 本人` | `resume` / `practice` 模块 |

后果有三点，前端要留意：

1. **HR 看不到候选人的简历**，除非候选人主动把简历关联到该 HR 名下的某场面试。
   此时 HR 通过 `GET /api/interviews/{id}/resume` 只读，未关联时是 **404（不是 403）**。
2. **撤销一条已接受的邀请，候选人对该场面试的访问立即失效**（后续请求 403）。
3. **候选人不能访问未被邀请、或邀请了但尚未接受的面试** —— 一律 403，不泄露面试是否存在。

> 一处**有意的例外**：练习取题（`GET /api/practice/questions`、`POST /api/practice/sessions`）
> **不按 `created_by` 过滤题库** —— 刷题取的是全库题目，这是刷题能用的前提。
> 因此候选人侧提供了一个「**有题目的岗位**」列表（`GET /api/candidate/positions`）作为筛选口径，
> 它只下发 `id` / 名称 / 题量，**不含 JD**。

题目额外遵循：**隔离键是题目自身的 `created_by`**，与所属岗位的创建者无关。

### 2.6 通用行为约定

| 项 | 约定 |
|---|---|
| 分页 | **不提供分页。** 列表接口返回数组（不是 `{items, total}` 包一层） |
| `limit` | 少数列表支持 `limit` 参数（**只有上限、没有 offset**）：简历列表 ≤ 200、练习会话列表 ≤ 100、错题本 ≤ 200。超过上限返回 400，**不静默截断** |
| 排序 | 岗位 / 题目 / 用户 / 候选人岗位筛选项按 `id` **升序**；面试列表按 `id` **降序**；面试内题目按 `seq` **升序**；邀请列表按 `created_at` **降序**；简历列表按 `updated_at` **降序**；练习会话按 `started_at` **降序**；错题本按 `answered_at` **降序** |
| 时间格式 | ISO 8601 字符串，如 `2026-09-17T10:30:00`（**无时区后缀**，按本地时间处理） |
| 脱敏 | 任何用户相关响应**都不会出现 `password_hash`**；候选人的简历响应不含 `created_by` |
| 删除 | 均为物理删除；**用户不做物理删除**，只能禁用（`is_active: false`）；被引用的岗位 / 题目 / 简历不可删，返回 409 |
| 请求体 | 除 `DELETE` 与动词端点外均需 `Content-Type: application/json`。**全量替换**的端点（`PUT /positions`、`PUT /questions`）漏传字段会按默认值处理；**部分更新**的端点（`PATCH /users`、`PATCH /interviews`、`PUT /candidate/resumes`）漏传即保持不变 |
| 幂等 | 以下操作可安全重试：交卷（`POST .../submit`，重复返回**首次**交卷时间）、触发评估（运行中重复触发返回**同一** `stream_url`）、撤销邀请（已撤销重复撤销返回 200）、按简历补题（**不重复追加**同一道题）、重新判分（已判分的题不重复调 AI） |

---

## 三、接口总览

`/api` 下共 **43 条路径 / 59 个 method-route**。「鉴权」列写的是**允许的角色**，
不带 token 一律 401，角色不符一律 403（见 [§2.2](#22-认证)）。

| # | 提交方式 | URL | 鉴权 | 说明 | 详见 |
|---:|---|---|---|---|---|
| 1 | `GET` | `/api/health` | 公开 | 健康检查 | [§4.1](#41-健康检查) |
| 2 | `POST` | `/api/auth/login` | 公开 | 登录，签发 JWT | [§5.1](#51-登录) |
| 3 | `POST` | `/api/auth/register` | 公开 | **候选人自助注册**（仅刷题权限） | [§5.6](#56-候选人自助注册) |
| 4 | `GET` | `/api/auth/me` | 任意登录 | 当前登录用户信息 | [§5.2](#52-当前登录用户) |
| 5 | `POST` | `/api/users` | `admin` | 创建用户（`hr` / `admin`） | [§5.3](#53-创建用户仅-admin) |
| 6 | `GET` | `/api/users` | `admin` | 用户列表 | [§5.4](#54-用户列表仅-admin) |
| 7 | `PATCH` | `/api/users/{user_id}` | `admin` | 改角色 / 启用禁用 | [§5.5](#55-修改角色--启用禁用仅-admin) |
| 8 | `POST` | `/api/positions` | `admin` `hr` | 创建岗位 | [§6.1](#61-创建岗位) |
| 9 | `GET` | `/api/positions` | `admin` `hr` | 岗位列表（可按名模糊搜） | [§6.2](#62-岗位列表) |
| 10 | `GET` | `/api/positions/{position_id}` | `admin` `hr` | 岗位详情 | [§6.3](#63-岗位详情) |
| 11 | `PUT` | `/api/positions/{position_id}` | `admin` `hr` | 更新岗位（全量替换） | [§6.4](#64-更新岗位) |
| 12 | `DELETE` | `/api/positions/{position_id}` | `admin` `hr` | 删除岗位（204） | [§6.5](#65-删除岗位) |
| 13 | `POST` | `/api/questions` | `admin` `hr` | 创建题目 | [§7.1](#71-创建题目) |
| 14 | `GET` | `/api/questions` | `admin` `hr` | 题目列表（多维筛选） | [§7.2](#72-题目列表) |
| 15 | `GET` | `/api/questions/{question_id}` | `admin` `hr` | 题目详情 | [§7.3](#73-题目详情) |
| 16 | `PUT` | `/api/questions/{question_id}` | `admin` `hr` | 更新题目（全量替换） | [§7.4](#74-更新题目) |
| 17 | `DELETE` | `/api/questions/{question_id}` | `admin` `hr` | 删除题目（204） | [§7.5](#75-删除题目) |
| 18 | `POST` | `/api/questions/{question_id}/reference-answer` | `admin` `hr` | **调 AI 生成参考答案与解析** | [§7.6](#76-生成参考答案与解析) |
| 19 | `POST` | `/api/interviews` | `admin` `hr` | 创建面试（**同步出题**） | [§8.2](#82-创建面试同步出题) |
| 20 | `GET` | `/api/interviews` | `admin` `hr` | 面试列表 | [§8.3](#83-面试列表) |
| 21 | `GET` | `/api/interviews/{interview_id}` | `admin` `hr` | 面试详情（含题目与回答） | [§8.4](#84-面试详情) |
| 22 | `PATCH` | `/api/interviews/{interview_id}` | `admin` `hr` | 更新候选人信息 | [§8.5](#85-更新候选人信息) |
| 23 | `POST` | `/api/interviews/{interview_id}/answers` | `admin` `hr` | 录入 / 修改某题回答 | [§8.6](#86-录入--修改回答) |
| 24 | `POST` | `/api/interviews/{interview_id}/complete` | `admin` `hr` | 标记完成 | [§8.7](#87-标记完成) |
| 25 | `POST` | `/api/interviews/{interview_id}/rollback` | `admin` `hr` | 回退到进行中 | [§8.8](#88-回退到进行中) |
| 26 | `POST` | `/api/interviews/{interview_id}/invitations` | `admin` `hr` | **生成作答邀请码**（201） | [§8.9](#89-生成作答邀请码) |
| 27 | `GET` | `/api/interviews/{interview_id}/invitations` | `admin` `hr` | 邀请列表与状态 | [§8.10](#810-邀请列表与状态) |
| 28 | `DELETE` | `/api/interviews/{interview_id}/invitations/{invitation_id}` | `admin` `hr` | 撤销邀请（**200，非 204**） | [§8.11](#811-撤销邀请) |
| 29 | `POST` | `/api/interviews/{interview_id}/prep` | `admin` `hr` | **生成 / 重新生成面试前准备提纲** | [§8.12](#812-生成--重新生成准备提纲) |
| 30 | `GET` | `/api/interviews/{interview_id}/prep` | `admin` `hr` | 查看准备提纲（未生成 404） | [§8.13](#813-查看准备提纲) |
| 31 | `PUT` | `/api/interviews/{interview_id}/prep` | `admin` `hr` | 编辑准备提纲（整体覆盖） | [§8.14](#814-编辑准备提纲) |
| 32 | `POST` | `/api/interviews/{interview_id}/questions/match` | `admin` `hr` | **按简历补题**（追加、幂等） | [§8.15](#815-按简历补题) |
| 33 | `GET` | `/api/interviews/{interview_id}/resume` | `admin` `hr` | **读取该面试关联的简历**（未关联 404） | [§8.16](#816-读取面试关联的简历) |
| 34 | `POST` | `/api/interviews/{interview_id}/evaluate` | `admin` `hr` | 触发评估（**202**） | [§9.1](#91-触发评估) |
| 35 | `GET` | `/api/interviews/{interview_id}/evaluation/stream` | `admin` `hr` | **SSE** 评估进度 | [§9.2](#92-sse-流式评估进度) |
| 36 | `GET` | `/api/interviews/{interview_id}/report` | `admin` `hr` | 获取完整报告 | [§9.3](#93-获取报告) |
| 37 | `GET` | `/api/interviews/{interview_id}/report/export` | `admin` `hr` | **导出报告为 DOCX**（文件流） | [§9.4](#94-导出报告为-docx) |
| 38 | `GET` | `/api/candidate/interviews/{interview_id}/feedback` | `candidate` | 候选人**脱敏**反馈 | [§9.5](#95-候选人脱敏反馈) |
| 39 | `GET` | `/api/candidate/positions` | `candidate` | 刷题岗位筛选项（有题目的岗位） | [§10.1](#101-刷题岗位筛选项) |
| 40 | `POST` | `/api/candidate/invitations/{code}/accept` | `candidate` | **凭邀请码激活并绑定面试** | [§10.2](#102-接受邀请码) |
| 41 | `GET` | `/api/candidate/interviews` | `candidate` | 我参与的面试列表 | [§10.3](#103-我的面试列表) |
| 42 | `GET` | `/api/candidate/interviews/{interview_id}` | `candidate` | 面试详情（仅题目与我的作答） | [§10.4](#104-面试详情候选人视图) |
| 43 | `POST` | `/api/candidate/interviews/{interview_id}/answers` | `candidate` | 保存 / 更新我的作答 | [§10.5](#105-保存--更新我的作答) |
| 44 | `POST` | `/api/candidate/interviews/{interview_id}/submit` | `candidate` | **交卷**（幂等） | [§10.6](#106-交卷) |
| 45 | `PUT` | `/api/candidate/interviews/{interview_id}/resume` | `candidate` | **关联 / 解除关联我的简历** | [§10.7](#107-关联--解除关联简历) |
| 46 | `POST` | `/api/candidate/resumes` | `candidate` | 新建我的简历 | [§11.1](#111-新建简历) |
| 47 | `GET` | `/api/candidate/resumes` | `candidate` | 我的简历列表 | [§11.2](#112-我的简历列表) |
| 48 | `GET` | `/api/candidate/resumes/{resume_id}` | `candidate` | 简历详情 | [§11.3](#113-简历详情) |
| 49 | `PUT` | `/api/candidate/resumes/{resume_id}` | `candidate` | 更新我的简历（部分更新） | [§11.4](#114-更新我的简历) |
| 50 | `DELETE` | `/api/candidate/resumes/{resume_id}` | `candidate` | 删除我的简历（204） | [§11.5](#115-删除我的简历) |
| 51 | `GET` | `/api/practice/questions` | `candidate` | 刷题取题（**不含答案与解析**） | [§12.1](#121-刷题取题预览) |
| 52 | `GET` | `/api/practice/sessions` | `candidate` | 我的练习会话列表（含进行中） | [§12.2](#122-我的练习会话列表) |
| 53 | `POST` | `/api/practice/sessions` | `candidate` | 开始一次练习（**201**） | [§12.3](#123-开始一次练习) |
| 54 | `GET` | `/api/practice/sessions/{session_id}` | `candidate` | 练习详情与进度 | [§12.4](#124-练习详情与进度) |
| 55 | `POST` | `/api/practice/sessions/{session_id}/items` | `candidate` | 提交某题作答 → **即时判分** | [§12.5](#125-提交作答即时判分) |
| 56 | `POST` | `/api/practice/items/{item_id}/rescore` | `candidate` | 对**未判分**的题重新判分 | [§12.6](#126-重新判分) |
| 57 | `POST` | `/api/practice/sessions/{session_id}/finish` | `candidate` | 结束练习，出小结 | [§12.7](#127-结束练习) |
| 58 | `GET` | `/api/practice/wrong-book` | `candidate` | 错题本（派生查询） | [§12.8](#128-错题本) |
| 59 | `GET` | `/api/practice/stats` | `candidate` | 我的练习统计 | [§12.9](#129-练习统计) |

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
| `user` | object | 用户对象，见 [§10.1](#131-userout) |

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

> **`user.role` 有三种取值**：`admin` / `hr` / `candidate`。**登录接口对三种角色是同一个**，
> 前端要根据返回的 `role` 决定跳 HR 端还是候选人端（`candidate` → `/candidate`）。
> 候选人账号的两个来源见 [§5.6](#56-候选人自助注册) 与 [§10.2](#102-接受邀请码)。

### 5.2 当前登录用户

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/auth/me` |
| 鉴权 | 任意已登录角色（`admin` / `hr` / `candidate` 均可） |

**参数**：无。

**响应 `200`** —— 用户对象（[§10.1](#131-userout)），**不含 `password_hash`**。

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

**响应 `201`** —— 用户对象（[§10.1](#131-userout)）。

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

### 5.6 候选人自助注册

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/auth/register` |
| 鉴权 | **不需要**（公开） |

候选人账号有**两个来源**，这是其中一个；另一个是凭邀请码激活（[§10.2](#102-接受邀请码)）。
自助注册的账号**只有刷题权限，不绑定任何面试**。

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `username` | string | 是 | 1–50 字符 | **全局唯一** |
| `password` | string | 是 | **最少 8 字符**，最多 128 | 明文传输，服务端 bcrypt 后入库 |

```json
{ "username": "cand_li", "password": "cand12345678" }
```

> **请求体里没有 `role`**，也无法指定。注册出来的账号**恒为 `candidate`** ——
> 与「题目创建不接受客户端指定 `source`」是同一类做法：字段不由客户端决定，
> 避免自助注册成为提权路径。

**响应 `201`** —— 用户对象（[§13.1](#131-userout)），`role` 恒为 `"candidate"`。

```json
{
  "id": 7,
  "username": "cand_li",
  "role": "candidate",
  "is_active": true,
  "created_at": "2026-09-21T09:15:00"
}
```

> ⚠️ **响应里没有 `token`**。注册成功不等于登录，前端要再调一次 [§5.1](#51-登录) 才能拿到 token。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 密码少于 8 位 / 用户名超长或为空 | `请求参数不合法` |
| 409 | `BUSINESS_ERROR` | 自助注册被配置关闭（`CANDIDATE_SELF_REGISTER=false`） | `候选人自助注册已关闭，请使用邀请码激活` |
| 409 | `BUSINESS_ERROR` | 用户名已被占用 | `用户名已被占用` |

> **两种"已被占用"的响应完全相同**，不区分被占的是候选人、HR 还是 admin 账号 ——
> 否则可以拿注册接口当「用户名是否存在于 HR 侧」的探测器。
>
> 关闭自助注册时（`CANDIDATE_SELF_REGISTER=false`）会带一个结构化 `detail`，便于前端
> 直接引导到「输入邀请码」：
>
> ```json
> { "code": "BUSINESS_ERROR",
>   "message": "候选人自助注册已关闭，请使用邀请码激活",
>   "detail": { "reason": "self_register_disabled" } }
> ```

---

## 六、岗位

岗位字段：名称、JD、**评估维度列表**。评估维度是后续出题与多维评分的基准。

### 6.1 创建岗位

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/positions` |
| 鉴权 | `admin` `hr` |

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

**响应 `201`** —— 岗位对象（[§10.2](#132-positionout)）。

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
| 鉴权 | `admin` `hr` |

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
| 鉴权 | `admin` `hr` |

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
| 鉴权 | `admin` `hr` |

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
| 鉴权 | `admin` `hr` |

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
| 鉴权 | `admin` `hr` |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `position_id` | integer | 是 | 岗位须存在且当前用户可见 | — |
| `category` | string \| null | 否 | 1–50 字符 | `"通用"` |
| `dimension` | string | 是 | 1–50 字符，**必须属于该岗位的评估维度** | — |
| `content` | string | 是 | **5–2000 字符** | — |
| `difficulty` | string | 否 | `easy` \| `medium` \| `hard` | `"medium"` |
| `tags` | string[] | 否 | ≤10 个，单个 1–20 字符，strip 后去重 | `[]` |
| `question_type` | string \| null | 否 | `single_choice` \| `short_answer` | `"short_answer"` |
| `options` | string[] \| null | 否 | 单选 **2–10 个**，每个 1–200 字符，strip 后去重；**简答题必须为空数组** | `[]` |
| `reference_answer` | string \| null | 否 | 单选**必填**且须与某个选项 strip 后相等；简答可空；≤2000 字符 | — |
| `explanation` | string \| null | 否 | 答案解析，≤2000 字符 | — |

> ⚠️ `source` **不可由客户端指定** —— 即使请求体里传了 `"source": "ai"`，落库仍为 `"bank"`。
> 该字段只由服务端在 AI 出题时写入。

**单选的三个字段是一组约束**，缺一不可（否则 400）：

| 题型 | `options` | `reference_answer` |
|---|---|---|
| `single_choice` | **2–10 个**，不可重复 | **必填**，且必须是其中一个选项 |
| `short_answer` | **必须为 `[]`**（不传即 `[]`） | 可空；留空则该题只能由 AI 判分（见 [§12.5](#125-提交作答即时判分)） |

> 默认题型是**简答**。这是刻意的：存量题目（题库里已有的纯文本题）没有选项，
> 按「简答」理解才符合事实；若默认单选，会凭空造出一批没有选项的单选题。

**请求示例**（单选题）

```json
{
  "position_id": 1,
  "category": "基础",
  "dimension": "专业能力",
  "content": "HTTP 状态码 401 表示什么？",
  "difficulty": "easy",
  "tags": ["网络"],
  "question_type": "single_choice",
  "options": ["未认证", "未授权", "资源不存在", "服务器错误"],
  "reference_answer": "未认证",
  "explanation": "401 表示身份未认证或认证失败；403 才是已认证但无权限。"
}
```

**响应 `201`** —— 题目对象（[§13.3](#133-questionout)）。

```json
{
  "id": 1,
  "position_id": 1,
  "category": "基础",
  "dimension": "专业能力",
  "content": "HTTP 状态码 401 表示什么？",
  "difficulty": "easy",
  "question_type": "single_choice",
  "options": ["未认证", "未授权", "资源不存在", "服务器错误"],
  "reference_answer": "未认证",
  "explanation": "401 表示身份未认证或认证失败；403 才是已认证但无权限。",
  "tags": ["网络"],
  "source": "bank",
  "created_by": 2,
  "created_at": "2026-09-17T10:05:00"
}
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `content` 少于 5 或多于 2000；`tags` 超限；`difficulty` / `question_type` 非法 | `请求参数不合法` |
| 400 | `VALIDATION_ERROR` | `dimension` 不属该岗位 | `该维度不属于岗位的评估维度`（`detail.allowed` 含合法维度） |
| 400 | `VALIDATION_ERROR` | 单选选项少于 2 个 / 选项重复 / **简答却带了选项** / 单选缺少参考答案 / 参考答案不在选项中 | 见下 |
| 403 | `FORBIDDEN` | 岗位属于他人 | `无权限访问该岗位` |
| 404 | `NOT_FOUND` | 岗位不存在 | `岗位不存在` |

题型相关的四条文案（`detail` 里会带出 `options` 字段名，便于定位到表单项）：

| 触发场景 | message |
|---|---|
| 单选选项少于 2 个 | `单选题至少需要 2 个选项` |
| 选项重复 | `选项不能重复` |
| 简答却带了选项 | `简答题不应包含选项` |
| 单选缺参考答案 | `单选题必须提供参考答案` |
| 参考答案不在选项中 | `参考答案必须是选项之一` |

> 维度匹配是 **strip 后精确匹配**（区分大小写）。前端应把该岗位的
> `evaluation_dimensions` 渲染成下拉选择，从源头避免 400。

### 7.2 题目列表

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/questions` |
| 鉴权 | `admin` `hr` |

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
| 鉴权 | `admin` `hr` |

**响应 `200`** —— 题目对象。

**错误**：`404 NOT_FOUND`（`题目不存在`）/ `403 FORBIDDEN`。

### 7.4 更新题目

| 项 | 内容 |
|---|---|
| 提交方式 | `PUT` |
| URL | `/api/questions/{question_id}` |
| 鉴权 | `admin` `hr` |

**全量替换语义**，请求体字段与创建时相同（`tags` 整体替换）。

> `position_id` **可以改** —— 改到其他岗位时会**重新校验** `dimension` 是否属于新岗位，
> 不属于则 `400`。前端换岗位时应同步刷新维度下拉并清空已选维度。

**响应 `200`** —— 更新后的题目对象。

### 7.5 删除题目

| 项 | 内容 |
|---|---|
| 提交方式 | `DELETE` |
| URL | `/api/questions/{question_id}` |
| 鉴权 | `admin` `hr` |

**响应 `204`** —— **无响应体**。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 题目属于他人 | `无权限访问该题目` |
| 404 | `NOT_FOUND` | 题目不存在 | `题目不存在` |
| 409 | `BUSINESS_ERROR` | 题目已被某场面试引用 | `该题目已被面试引用，无法删除` |

### 7.6 生成参考答案与解析

调 AI 为题面生成参考答案与解析并**落库**。用于补齐「先有题、后有答案」的中间态 ——
简答题可以不给参考答案（此时 [§12.5](#125-提交作答即时判分) 会退化为「未判分」），
HR 也可以在这里一键让 AI 补上，再由 HR 确认或改写。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/questions/{question_id}/reference-answer` |
| 鉴权 | `admin` `hr` |

**参数**：无。**请求体：无。**

**响应 `200`** —— 更新后的题目对象（[§13.3](#133-questionout)），
`reference_answer` 与 `explanation` 已写入。

> 是 `200` 不是 `201`：它更新的是**已有**题目，不新建资源。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 题目属于他人 | `无权限访问该题目` |
| 404 | `NOT_FOUND` | 题目不存在 | `题目不存在` |
| 409 | `BUSINESS_ERROR` | **AI 给出的答案不在该题的选项里**（仅单选题） | `AI 生成的答案不在选项中，请手工确认` |
| 502 | `AI_PROVIDER_ERROR` | AI 调用失败（重试 1 次后） | `AI 服务调用失败，请稍后重试` |

> 上面两种失败（409 / 502）**都不会改动题目**：都在写库之前中断，题目内容保持原样。
> 单选题的答案必须落在 `options` 内，AI 越界即拒绝 —— 宁可让 HR 手工填，也不能写进一个
> 永远判不对的参考答案。

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
| 鉴权 | `admin` `hr` |

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

> ⚠️ **创建面试不接受 `resume_id`**。简历由**候选人**提交，时间上晚于创建面试 ——
> HR 建面试时还不知道候选人有哪份简历。关联动作由候选人在自己那侧发起
> （[§10.7](#107-关联--解除关联简历)），HR 之后可用 [§8.16](#816-读取面试关联的简历) 读取。

**响应 `201`** —— 面试详情对象（[§13.5](#135-interviewdetail)）。

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
| 鉴权 | `admin` `hr` |

**参数**：无（**不支持筛选，也不分页**）。

**响应 `200`** —— 面试列表项数组（[§10.4](#134-interviewlistitem)），按 `id` **降序**（新的在前）。

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
| 鉴权 | `admin` `hr` |

**响应 `200`** —— 面试详情（[§13.5](#135-interviewdetail)），`questions` 按 `seq` 升序。

> 未作答的题目，`answer` 与 `recorded_at` 均为 `null`。
>
> **`resume_id` 在详情里下发，在列表里不下发**：详情页要显示「本场关联了哪份简历」，
> 列表不需要。未关联时为 `null`。简历内容本身通过 [§8.16](#816-读取面试关联的简历) 单独取。

**错误**：`404 NOT_FOUND`（`面试不存在`）/ `403 FORBIDDEN`（`无权限访问该面试`）。

### 8.5 更新候选人信息

| 项 | 内容 |
|---|---|
| 提交方式 | `PATCH` |
| URL | `/api/interviews/{interview_id}` |
| 鉴权 | `admin` `hr` |

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
| 鉴权 | `admin` `hr` |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `interview_question_id` | integer | 是 | 必须属于该面试 | — |
| `content` | string | 否 | ≤10000 字符，**允许空串** | `""` |

**请求示例**

```json
{ "interview_question_id": 1, "content": "我在上一家公司负责过…" }
```

**响应 `200`** —— 单条题目对象（[§10.6](#136-questionitem)）。

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
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 面试详情，`status` 为 `completed`，`completed_at` 非空。

**错误**：`409 BUSINESS_ERROR`（当前状态不是 `ongoing`，**含重复调用**）。

### 8.8 回退到进行中

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/rollback` |
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 面试详情，`status` 为 `ongoing`，`completed_at` 被**清空**。

**错误**：`409 BUSINESS_ERROR`（当前状态不是 `completed` 或 `evaluated`；
**`evaluating` 下不允许回退**）。

### 8.9 生成作答邀请码

给候选人一个「进这场面试」的入口。候选人凭码激活账号并绑定该场面试，之后就能在线作答。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/invitations` |
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。**无请求体。**

**响应 `201`** —— 邀请对象（[§13.9](#139-invitationview)）。

```json
{
  "id": 1,
  "interview_id": 3,
  "code": "hT9rQ2xLm4ZbN1vCk8sPwA",
  "status": "pending",
  "expires_at": "2026-09-28T10:00:00",
  "accepted_at": null,
  "candidate_username": null,
  "created_at": "2026-09-21T10:00:00"
}
```

| 字段 | 说明 |
|---|---|
| `code` | **明文**邀请码，22 字符（`secrets.token_urlsafe(16)`，约 128 位熵）。HR 需要能反复复制它，所以只明文存储、不做哈希 |
| `status` | 数据库里只有 `pending` / `accepted` / `revoked` 三个值 |
| `expires_at` | 生成时间 + `INVITATION_EXPIRE_DAYS`（默认 **7 天**） |
| `accepted_at` | 候选人接受后才非空 |
| `candidate_username` | 接受后回填的候选人账号名 |

**前置条件**：面试必须处于 `ongoing`。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |
| 409 | `BUSINESS_ERROR` | 面试不是 `ongoing`（含 `draft`） | `当前状态下不可生成邀请，请先将面试置为进行中` |

> **一场面试可以生成多条邀请**（例如发给多个候选人），互不影响；
> 每条邀请一次接受后即锁定到某个候选人账号。

### 8.10 邀请列表与状态

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}/invitations` |
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。

**响应 `200`** —— 邀请对象数组（[§13.9](#139-invitationview)），按 `created_at` **降序**。
没有邀请时返回 `[]`（不是 404）。

> ⚠️ **`status` 对外有四个取值，其中 `expired` 是派生出来的**，不落库：
> 读取时若 `pending` 且已过 `expires_at`，就显示为 `expired`。
> 之所以不用定时任务刷状态 —— 那需要常驻调度器，违反「单机、不引入中间件」的约束，
> 且进程不常驻时状态会滞后失真。**前端请以响应的 `status` 为准，不要自己按 `expires_at` 判断。**

**错误**：`403 FORBIDDEN`（面试属于他人）；`404 NOT_FOUND`（面试不存在）。

### 8.11 撤销邀请

| 项 | 内容 |
|---|---|
| 提交方式 | `DELETE` |
| URL | `/api/interviews/{interview_id}/invitations/{invitation_id}` |
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。

**响应 `200`** —— 撤销后的邀请对象（`status` 为 `revoked`）。

> ⚠️ **是 `200` 且带响应体，不是 `204`** —— 与岗位 / 题目 / 简历的删除不同。
> 前端需要拿到 `status` 才能更新列表那一行。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试或邀请不存在、邀请不属于该面试 | `邀请不存在` |
| 409 | `BUSINESS_ERROR` | **邀请已被接受** | `已接受的邀请不可撤销` |

**幂等性**：对**已撤销**的邀请重复撤销返回 `200`（不报错）；对**已过期**的邀请撤销也允许。

> 撤销一条**已接受**的邀请会**立即切断**该候选人对这场面试的访问 ——
> 后续请求一律 403。这也是 HR 收回入口的唯一手段。

### 8.12 生成 / 重新生成准备提纲

由 AI 产出面试前的工作稿：**面试提纲**（分阶段时间安排）、**考察重点**（按岗位维度）、
**问题预案**（建议提问 + 考察意图 + 可追问方向）。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/prep` |
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 准备提纲对象（[§13.10](#1310-prepout)）。

```json
{
  "interview_id": 3,
  "outline": [
    { "seq": 1, "phase": "开场与自我介绍", "duration_min": 5, "notes": "说明流程与时长" }
  ],
  "focus_points": [
    { "dimension": "专业能力", "point": "分布式事务的取舍", "reason": "简历中主导过跨库改造" }
  ],
  "question_plan": [
    { "question": "讲一次你处理线上故障的过程", "intent": "考察排查思路", "follow_ups": ["为什么先看这个指标"] }
  ],
  "generated_at": "2026-09-21T10:20:00",
  "edited_at": null
}
```

**输入**：岗位（JD + 维度）+ 候选人信息 + **简历（可选）** + 本场已有题目（可为空）。
**没有简历、甚至还没有题目（`draft`）都能生成。**

**前置条件**：面试处于 `draft` 或 `ongoing`。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |
| 409 | `BUSINESS_ERROR` | 面试已 `completed` / `evaluating` / `evaluated` | `面试已进入评估或已完成，不可再生成准备提纲` |
| 409 | `BUSINESS_ERROR` | 岗位未定义评估维度 | `岗位未定义评估维度，无法生成准备提纲` |
| 502 | `AI_PROVIDER_ERROR` | AI 调用失败（重试 1 次后） | `AI 服务调用失败，请稍后重试` |

> **重新生成 = 整体覆盖**：三个部分一次性替换，**`edited_at` 被置回 `null`**
> （因为此前 HR 的手工编辑已被整体覆盖，留着旧值会让界面谎称「已手工编辑」）。
>
> **AI 失败时旧内容不动**：若此前已有提纲，`outline` / `focus_points` / `question_plan`
> 与 `generated_at` 全部保持原样；若这是首次生成，则**不会留下任何空行**。
>
> 准备提纲**不进面试状态机** —— 「生成/编辑过提纲」与面试推进到哪一步相互正交。

### 8.13 查看准备提纲

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}/prep` |
| 鉴权 | `admin` `hr` |

**响应 `200`** —— 准备提纲对象（[§13.10](#1310-prepout)）。

**错误**：`404 NOT_FOUND`（**尚未生成** → 前端据此显示「生成准备提纲」按钮）；
`403 FORBIDDEN`（面试属于他人）；`404 NOT_FOUND`（面试不存在）。

### 8.14 编辑准备提纲

| 项 | 内容 |
|---|---|
| 提交方式 | `PUT` |
| URL | `/api/interviews/{interview_id}/prep` |
| 鉴权 | `admin` `hr` |

**请求体** —— **三个部分都必须传**，整体覆盖（不做字段级合并）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `outline` | object[] | 是 | 每项 `{seq≥1, phase, duration_min≥1, notes}` |
| `focus_points` | object[] | 是 | 每项 `{dimension, point, reason}` |
| `question_plan` | object[] | 是 | 每项 `{question, intent, follow_ups: string[]}` |

**响应 `200`** —— 更新后的提纲，`edited_at` 置为当前时间，**`generated_at` 保持不变**。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 三个部分缺任意一个 / 条目字段不合法 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | **尚未生成**（`PUT` 不会自动创建） | `准备提纲尚未生成` |
| 409 | `BUSINESS_ERROR` | 面试已 `completed` 及之后 | `面试已进入评估或已完成，不可再编辑准备提纲` |

> 「先查看再编辑」是唯一顺序：未生成时读是 404，写也是 404，**不会顺手建一条空的出来**。

### 8.15 按简历补题

在既有出题结果之上，按候选人关联的简历**追加**一批更贴合其经历的题目。
这是简历进入出题流程的**唯一通路**，也是 HR 读取候选人简历的唯一通路（见 [§8.16](#816-读取面试关联的简历)）。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/questions/match` |
| 鉴权 | `admin` `hr` |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `count` | integer \| null | 否 | **1–20** | `RESUME_MATCH_COUNT`（默认 `3`） |

```json
{ "count": 3 }
```

**响应 `200`** —— 补题结果（[§13.11](#1311-matchresult)）。

```json
{
  "added_count": 2,
  "added": [
    { "interview_question_id": 41, "seq": 9, "content": "…", "dimension": "专业能力",
      "match_reason": "候选人简历中提到主导过跨库分表改造" }
  ],
  "total_questions": 10
}
```

| 字段 | 说明 |
|---|---|
| `added_count` | 本次追加了几题 |
| `added[].seq` | **续接本场最大值**，编号连续无缺口 |
| `added[].match_reason` | AI 给出的匹配理由，**非空** —— 前端据此展示「为什么选这道题」 |
| `total_questions` | 本场**当前**题目总数（累加后的值） |

**前置条件**（两条都要满足）：面试处于 `ongoing`，且 `interview.resume_id` 非空。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `count` 不在 1–20 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |
| 409 | `BUSINESS_ERROR` | 面试非 `ongoing`（`draft` 尚无出题、`completed` 及之后冻结） | `当前状态下不可按简历补题` |
| 409 | `BUSINESS_ERROR` | **该面试尚未关联简历** | `该面试尚未关联简历` |
| 409 | `BUSINESS_ERROR` | 岗位未定义评估维度 | `岗位未定义评估维度，无法补题` |
| 409 | `BUSINESS_ERROR` | 题库里已没有可补的题（候选池耗尽） | `题库中没有可补充的题目` |
| 502 | `AI_PROVIDER_ERROR` | AI 调用失败（重试 1 次后） | `AI 服务调用失败，请稍后重试` |

**三条必须分清的行为**（前端据此决定提示什么）：

| 情形 | 表现 | 含义 |
|---|---|---|
| `added_count > 0` | `200` | 正常补到了题 |
| `added_count == 0` | **`200`（不是错误）** | AI 认为没有更相关的题 —— 正常结果，不是失败 |
| AI 不可用 | `502` | 失败；**既有题目与面试状态都不变** |

> **补题只追加、不改动、不可撤销**：新增的题与既有题一样**不提供删除接口**（沿用既有约束）。
> **幂等**：本场已有的 `question_id` 会被跳过，HR 连点不会产生重复题目；
> 重复调用仍**会继续追加**此前没出现过的题（候选人换了简历后再点一次，就是这个用法）。
>
> 新题的 `source_snapshot` 是 `resume_match`，且 `match_reason` 与它**成对出现** ——
> 非匹配来源的题 `match_reason` 恒为 `null`。
> **`match_reason` 永不下发给候选人**（见 [§10.4](#104-面试详情候选人视图)）。

### 8.16 读取面试关联的简历

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}/resume` |
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。

**响应 `200`** —— 关联的简历（[§13.8](#138-interviewresumeout)）。

```json
{
  "resume_id": 4,
  "title": "张三-后端开发",
  "content": "（简历纯文本全文）",
  "candidate_name": "张三",
  "candidate_contact": "zhangsan@example.com",
  "updated_at": "2026-09-21T09:40:00"
}
```

**权限判据是「这场面试属于我」，与简历归谁所有无关** —— HR 不通过 `created_by` 读他人简历，
而是因为**候选人主动把简历关联到了自己名下的这场面试**。这是 HR 看到候选人简历的唯一途径。
响应**不含 `created_by`**（HR 不需要知道候选人的 user id）。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |
| 404 | `NOT_FOUND` | **该面试尚未关联简历**（不是 403） | `该面试尚未关联简历` |

> ⚠️ 未关联返回的是 **404，不是 403** —— 前端据此显示「候选人尚未提供简历」，
> 而不是「你没有权限」。

---

## 九、评估

### 9.1 触发评估

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/interviews/{interview_id}/evaluate` |
| 鉴权 | `admin` `hr` |

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
> 与浏览器历史。**必须用 `fetch` + `ReadableStream`**，完整实现见 [§12.2](#152-sse-必须用-fetch--readablestream)。

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
| 鉴权 | `admin` `hr` |

**参数**：仅路径参数。

**响应 `200`** —— 完整报告（[§10.7](#137-reportdetail)）。

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

### 9.4 导出报告为 DOCX

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/interviews/{interview_id}/report/export` |
| 鉴权 | `admin` `hr` |

**查询参数**

| 参数 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `format` | string | 否 | **只支持 `docx`** | `"docx"` |

**前置条件**：面试状态必须是 `evaluated`（与 [§9.3](#93-获取报告) 同一套校验）。

**响应 `200`** —— **二进制文件流**（不是 JSON）：

```http
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="report.docx"; filename*=UTF-8''%E5%BC%A0%E4%B8%89-...
```

| 响应头 | 说明 |
|---|---|
| `Content-Type` | DOCX 的 MIME |
| `Content-Disposition` | `attachment` + **ASCII 兜底名** `report.docx` + `filename*=UTF-8''…` 中文名 |

> 中文文件名放在 `filename*`（RFC 5987 百分号编码）里，`filename=` 只留 ASCII 兜底 ——
> 现代浏览器优先取 `filename*`，老浏览器回落到 `report.docx`。
> 文件名中间的**引号、反斜杠、CR/LF、Tab 与控制字符会被剥掉**，长度上限 60 字符 ——
> 候选人姓名里塞换行也无法污染响应头。

**文档内容**：面试基本信息（岗位 / 候选人 / 面试时间）+ 总分 + 综合结论 + 优点 + 待改进
+ 逐题评分表 + 多维评分表。

> ⚠️ **DOCX 里没有雷达图**（Python 侧重画成本不划算）。需要图形的场景走 PDF。

**前端怎么下载**：这个接口需要 `Authorization` 头，**不能直接 `<a href>` 或 `window.open`**。
要先用 `fetch` 拿 `blob()`，再用 `URL.createObjectURL` 触发下载：

```js
const res = await fetch(`/api/interviews/${id}/report/export?format=docx`, {
  headers: { Authorization: `Bearer ${token}` },
});
if (!res.ok) throw new Error((await res.json()).message);
const blob = await res.blob();
const a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = '面试报告.docx';        // 或用 res.headers 里的 filename*
a.click();
URL.revokeObjectURL(a.href);
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `format` 不是 `docx` | `不支持的导出格式` |
| 403 | `FORBIDDEN` | 面试属于他人 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在，或报告行不存在 | — |
| 409 | `BUSINESS_ERROR` | 状态不是 `evaluated` | `评估尚未完成` |
| 500 | `INTERNAL_ERROR` | DOCX 组装失败 | `服务器内部错误` |

> **`format` 的校验在读报告之前** —— 传错格式即使面试还没评估，也返回 400 而不是 409。
>
> **PDF 没有后端接口**：PDF 导出走**前端浏览器打印**（`window.print()` + `@media print`），
> 雷达图沿页面上已渲染的图形，所见即所得。因此**不支持脱离浏览器的批量 / 后台导出**。
> 好处是后端挂了也能打印；DOCX 生成失败时，前端可以提示「改用导出 PDF」。

### 9.5 候选人脱敏反馈

面试评估完成后，候选人本人在自己那侧看到的反馈。**与 HR 看到的报告是两份不同受众的文本。**

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/candidate/interviews/{interview_id}/feedback` |
| 鉴权 | `candidate`（**必须持有该面试下本人已接受的有效邀请**） |

**参数**：仅路径参数。

**响应 `200`** —— 反馈对象（[§13.12](#1312-candidatefeedbackout)）。

```json
{
  "interview_id": 3,
  "level": "summary",
  "conclusion": "本场表现整体扎实：技术基础与表达都达到了岗位要求，在复杂问题的分析深度上还有提升空间。",
  "strengths": ["专业能力（7.0）：技术基础扎实", "沟通能力（7.0）：表达清晰，条理分明"],
  "weaknesses": ["逻辑思维（6.0）：分析深度有待加强", "文化契合（6.0）：价值观基本一致"],
  "overall_score": null,
  "generated_at": "2026-09-21T10:35:00"
}
```

**⚠️ 脱敏是**结构上**保证的**，不是靠前端不显示：

| 字段 | 说明 |
|---|---|
| `level` | `summary`（默认）或 `full`，**由服务端配置 `CANDIDATE_FEEDBACK_LEVEL` 决定** |
| `overall_score` | `summary` 档恒为 **`null`**；`full` 档为 0–10 的数 |
| `conclusion` | **面向本人的重写**，只讲这一场强在哪、弱在哪 |
| `strengths` / `weaknesses` | 条目与 HR 报告**逐条一致**，便于两处对照 |

**逐题分、维度分、雷达图在任何档位都不下发，且压根不在这个响应的 schema 里** ——
改档位配置也不需要重新生成反馈（存储与可见性解耦）。

> **结论里不出现去留判断。** 「建议进入下一轮 / 不建议继续推进」这类话由 HR 另行沟通，
> 不应让当事人在自助页面上读到。因此这条 `conclusion` 是**重新写的**，不是报告结论的复述 ——
> 即使把档位放开到 `full`，也**不放开**去留判断。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 未持有有效邀请（未受邀 / 尚未接受 / 已被撤销） | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |
| 409 | `BUSINESS_ERROR` | 状态不是 `evaluated` | `评估尚未完成` |
| 502 | `AI_PROVIDER_ERROR` | AI 生成失败（重试 1 次后） | `AI 服务调用失败，请稍后重试` |

> **客户端不能改档位**：请求里带 `?level=full` **无效**，档位只认服务端配置。

---

## 十、候选人端 —— 在线作答

候选人凭 **HR 生成的邀请码**激活账号并绑定某场面试后，就能在线作答；交卷后由 HR 侧继续推进评估。

**这一章的所有接口都要求 `candidate` 角色**，且数据隔离是「**是否持有该面试下本人已接受的有效邀请**」，
与 `created_by` 无关（见 [§2.5](#25-数据隔离规则)）。

完整链路（对应 [§14.3](#143-候选人端流程在线作答)）：

```
HR 生成邀请码 ──► 候选人 accept 激活并绑定 ──► 关联简历（可选）
                                                  │
                    ◄── HR 按简历补题 ─────────────┘
候选人作答 → 交卷 →【HR 标记完成 → 评估】→ 查看脱敏反馈
```

### 10.1 刷题岗位筛选项

候选人**无权访问 HR 侧的岗位接口**，而刷题取题本身取的是全库题目 ——
所以这个接口给出「**有题目的岗位**」作为筛选项，口径与取题一致。

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/candidate/positions` |
| 鉴权 | `candidate` |

**参数**：无。

**响应 `200`** —— 岗位筛选项数组（[§13.13](#1313-practicepositionout)），按 `id` 升序。

```json
[
  { "id": 1, "name": "后端工程师", "question_count": 12 },
  { "id": 3, "name": "前端工程师", "question_count": 4 }
]
```

| 字段 | 说明 |
|---|---|
| `question_count` | 该岗位当前**题目总数**（不限创建人） |
| — | **没有 `jd`，也没有 `created_by`** —— 候选人只需要一个筛选标识 |

> 题量归零的岗位会**自动从这个列表消失**（题目全被删时），无需前端过滤。

**错误**：`403 FORBIDDEN`（HR / admin 调用）。

### 10.2 接受邀请码

**候选人账号的两个来源之一**（另一个是 [§5.6 自助注册](#56-候选人自助注册)）。
凭邀请码创建的账号会**绑定该场面试**，因此同时拥有作答权限。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/candidate/invitations/{code}/accept` |
| 鉴权 | `candidate`（**调用者必须已经是登录中的候选人** —— 见下面的已知偏差） |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `code` | string | 邀请码明文（22 字符） |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `username` | string | 是 | 1–50 字符 | **由请求体决定绑定哪个账号** |
| `password` | string | 是 | **最少 8 字符**，最多 128 | 账号**已存在且是 candidate** 时会被**忽略** |

```json
{ "username": "cand_li", "password": "cand12345678" }
```

> **绑定到哪个账号由 body 里的 `username` 决定，与调用者身份无关。**
> 若该用户名已存在且角色是 `candidate`，**直接复用它，并且不校验 `password`** ——
> 候选人可能已经有一个刷题账号，不该强迫他换用户名（见下面的已知偏差）。

**响应 `200`** —— 绑定结果（[§13.14](#1314-invitationacceptresult)）。

```json
{
  "interview_id": 3,
  "interview": {
    "id": 3,
    "position_name": "后端工程师",
    "candidate_name": "李四",
    "status": "ongoing",
    "question_count": 8
  }
}
```

> ⚠️ **响应里没有 `token`**。接受邀请不等于登录，前端要再调 [§5.1](#51-登录) 拿 token。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 密码少于 8 位 / 用户名非法 | `请求参数不合法` |
| 409 | `BUSINESS_ERROR` | 邀请码**不存在 / 已过期 / 已撤销 / 已被接受** | `邀请码无效或已失效` |
| 409 | `BUSINESS_ERROR` | 用户名已被 `hr` / `admin` 占用 | `用户名已被占用` |
| 409 | `BUSINESS_ERROR` | 已接受过该面试的邀请 | `你已接受过该面试的邀请` |

> **四种失效原因返回完全相同的文案与状态码** —— 候选人不应该能从错误信息里推断出
> 「这场面试是否存在」「邀请是不是被人先用了」。
>
> **失败不留半成品**：若因用户名被 HR 占用而失败，邀请**保持 `pending`**，
> 不产生任何部分写入，候选人换个用户名可以重试。

#### ⚠️ 两处已知偏差（后端与计划书不一致，尚未修复）

计划书描述的流程是「新人凭码**一步**激活」，**当前后端实现与之有两处不符**。
接真实后端时一定会撞上，因此如实记录（发现于 2026-09-21）：

| # | 偏差 | 影响 |
|:--:|---|---|
| 1 | **本端点要求调用者已经是登录中的 `candidate`**（守卫是 `require_roles("candidate")`）。新人没有账号、也就拿不到 token，**根本无法调用** | `CANDIDATE_SELF_REGISTER=false` 时**邀请链整条断掉**：新人既注册不了，也没有 token 来 accept。开关为 `true`（默认）时，只能「先自助注册一个刷题账号 → 登录 → 再 accept」，多绕一步 |
| 2 | **绑定账号取自请求体 `username`，且对已存在的 candidate 不校验 `password`** | 拿到**任意一张有效邀请码**的人，只要知道某候选人的用户名，就能把码绑到**对方**账号上，进而进入对方的面试 |

> 前端**不要在客户端绕过**（比如先偷偷注册一个空账号再 accept）—— 那会把一个后端问题
> 变成两个。正确修法是先补 PRD，再改 router 守卫与 `auth` 的绑定逻辑。
>
> 原型（`frontend/standalone.html`）在这两点上**刻意跟计划书、不跟后端**，
> 所以在 mock 数据下是通的；切到真实后端才会暴露上面两条。

### 10.3 我的面试列表

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/candidate/interviews` |
| 鉴权 | `candidate` |

**参数**：无。

**响应 `200`** —— 面试列表项数组（[§13.15](#1315-candidateinterviewitem)）。

```json
[
  {
    "id": 3,
    "position_name": "后端工程师",
    "status": "ongoing",
    "question_count": 8,
    "answered_count": 5,
    "submitted": false,
    "resume_id": 4,
    "created_at": "2026-09-21T10:00:00"
  }
]
```

| 字段 | 说明 |
|---|---|
| `submitted` | 我是否已交卷 |
| `resume_id` | 本场关联的简历；未关联为 `null` —— **能写就必须能读**，候选人要能看到自己关联了哪一份 |
| — | 只列出**已接受邀请**的面试；未接受 / 已被撤销的都不出现 |

### 10.4 面试详情（候选人视图）

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/candidate/interviews/{interview_id}` |
| 鉴权 | `candidate`（须持有本人已接受的有效邀请） |

**响应 `200`** —— 候选人视角的详情（[§13.16](#1316-candidateinterviewdetail)）。

```json
{
  "id": 3,
  "position_name": "后端工程师",
  "status": "ongoing",
  "created_at": "2026-09-21T10:00:00",
  "submitted": false,
  "submitted_at": null,
  "resume_id": 4,
  "questions": [
    {
      "interview_question_id": 41,
      "seq": 1,
      "content": "请描述一次你处理线上故障的完整过程。",
      "dimension": "沟通能力",
      "my_answer": null
    }
  ]
}
```

**⚠️ 这个响应的字段是白名单式的**，题目对象**只有 5 个键**：

| 有 | 没有（结构上不存在） |
|---|---|
| `interview_question_id` · `seq` · `content` · `dimension` · `my_answer` | HR 的评语与评分 · 其他候选人的作答 · `created_by` · **`match_reason`** · `source` · `reference_answer` · `explanation` |

> `content` / `dimension` 取自**面试题目快照**，题库改了题干与维度也不影响正在进行的面试。
> **`match_reason` 永远不会下发** —— 那是 HR 侧的决策辅助信息。
> 未作答的题 `my_answer` 为 `null`。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 未受邀 / 尚未接受 / 邀请已被撤销 / 是别人的面试 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |

### 10.5 保存 / 更新我的作答

作答**实时保存**：每次输入变化都可以调一次，重复保存是**更新**而非新增。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/candidate/interviews/{interview_id}/answers` |
| 鉴权 | `candidate`（须持有本人已接受的有效邀请） |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `interview_question_id` | integer | 是 | **必须属于该面试** | 题目 id |
| `content` | string | 是 | ≤10000 字符，**允许空串** | 我的作答 |

```json
{ "interview_question_id": 41, "content": "我在上一家公司负责过…" }
```

**响应 `200`** —— 保存后的作答（[§13.17](#1317-candidateanswerview)）。

```json
{ "interview_question_id": 41, "content": "我在上一家公司负责过…", "submitted_at": null }
```

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `content` 超过 10000 字符 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 对该面试无有效邀请 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | **题目不属于该面试** | `题目不属于该面试` |
| 409 | `BUSINESS_ERROR` | **已交卷**，作答通道已锁 | `已交卷，不可修改作答` |
| 409 | `BUSINESS_ERROR` | 面试不是 `ongoing` | `当前状态下不可作答` |

> **锁只锁候选人自己**：交卷后候选人不能再改，但 **HR 侧不受影响**，
> 仍可修订你的作答（[§8.6](#86-录入--修改回答)）。
>
> ⚠️ HR 覆盖之后，**`answer_source` 仍然是 `candidate`** —— 它记录的是
> 「作答**最初**从哪条通道进来」，而不是「谁最后改的」。
> 数据库里另有一列 `answered_by` 记录最后修改者，但它**不在任何响应里下发**
> （HR 侧题目对象只有 [§13.6](#136-questionitem) 里那些字段）。
> 因此前端无法、也不需要区分「这条是 HR 改过的」。

### 10.6 交卷

交卷是**候选人侧的动词**，写完即锁定自己的作答通道。**不推进面试状态** ——
面试何时算完成仍由 HR 决定（[§8.7](#87-标记完成)）。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/candidate/interviews/{interview_id}/submit` |
| 鉴权 | `candidate`（须持有本人已接受的有效邀请） |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 交卷结果（[§13.18](#1318-submitresult)）。

```json
{ "interview_id": 3, "submitted_at": "2026-09-21T11:20:00", "answered_count": 5 }
```

| 字段 | 说明 |
|---|---|
| `submitted_at` | 交卷时刻 |
| `answered_count` | **非空**作答数（空串与未作答都不计） |

**行为要点**

| 行为 | 说明 |
|---|---|
| **幂等** | 重复交卷返回 **`200`**，且 `submitted_at` 仍是**第一次**的值，不会被刷新 |
| **不漏题** | 会给本场**所有**题目写 `submitted_at`，未作答的题回填空串作答 |
| **不改面试状态** | 面试仍是 `ongoing`，等 HR 标记完成 |
| **HR 已标记完成后再交卷** | 仍返回 `200` —— 幂等检查**先于**状态检查，重复交卷不算错 |

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 对该面试无有效邀请 / 是别人的面试 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 面试不存在 | `面试不存在` |

### 10.7 关联 / 解除关联简历

把**自己的一份简历**挂到这场面试上。这是 HR 能看到候选人简历的**唯一通路**，
也是「按简历补题」能生效的前提。

| 项 | 内容 |
|---|---|
| 提交方式 | `PUT` |
| URL | `/api/candidate/interviews/{interview_id}/resume` |
| 鉴权 | `candidate`（须持有本人已接受的有效邀请） |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `resume_id` | integer \| null | **是** | 传 `null` 表示**解除关联** |

```json
{ "resume_id": 4 }
```

```json
{ "resume_id": null }
```

> ⚠️ `resume_id` **必须传**，哪怕是 `null`。它是「显式的空值」而非「可选字段」——
> 「解除关联」和「这次请求没带这个字段」是两件事，不能混。传缺字段会 400。

**响应 `200`** —— 关联后的简历（[§13.8](#138-interviewresumeout)）；解除关联时返回 `null`。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 请求体缺 `resume_id` | `请求参数不合法` |
| 403 | `FORBIDDEN` | **关联的不是本人的简历** | `无权限访问该简历` |
| 403 | `FORBIDDEN` | 在**未接受邀请**的面试上操作 / 是别人的面试 | `无权限访问该面试` |
| 404 | `NOT_FOUND` | 简历不存在 | `简历不存在` |
| 409 | `BUSINESS_ERROR` | 面试已 `completed` 及之后（简历是面试的输入，面试结束即冻结） | `当前状态下不可变更简历关联` |

**规则**

| 规则 | 说明 |
|---|---|
| 一场面试只关联一份简历 | 重复关联是**替换** |
| 同一份简历可被多场面试关联 | 例如投不同岗位时另建一份，也可以复用同一份 |
| 面试进行中可以随时改 | 换一份更贴合的简历即可；**改后 HR 需重新触发补题才会生效** |
| 删除简历的前提 | 被面试或练习关联的简历**不可删除**（409，见 [§11.5](#115-删除我的简历)） |

---

## 十一、简历管理（候选人端）

简历以**纯文本粘贴**方式录入，**不做文件上传与格式解析**（MVP 明确不做）。
**写入方只有候选人**；HR 不提供简历 CRUD，只能经面试只读（[§8.16](#816-读取面试关联的简历)）。

简历**不绑定**某场面试或某次练习：同一份简历可被多场面试、多次练习复用，
`interview.resume_id` 与 `practice_session.resume_id` 只记录**引用**、不复制内容。

### 11.1 新建简历

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/candidate/resumes` |
| 鉴权 | `candidate` |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `title` | string | 是 | 1–100 字符，strip 后非空 | 简历标题 |
| `content` | string | 是 | strip 后非空，**≤20000 字符** | 简历正文（纯文本） |
| `candidate_name` | string \| null | 否 | ≤100 字符 | 姓名 |
| `candidate_contact` | string \| null | 否 | ≤200 字符 | 联系方式 |

```json
{
  "title": "张三-后端开发",
  "content": "教育经历…\n工作经历…\n项目经历…",
  "candidate_name": "张三",
  "candidate_contact": "zhangsan@example.com"
}
```

> 请求体**不含 `created_by`**，一律取自 token —— 与 `source` 同类做法，
> 避免「客户端指定归属」这种越权路径。

**响应 `201`** —— 简历对象（[§13.7](#1326-resumeout)）。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `title` / `content` 为空，或 `title` 超长 | `请求参数不合法` |
| **422** | `VALIDATION_ERROR` | **正文超过 20000 字符** | `简历正文不能超过 20000 字符` |

> ⚠️ **只有这一条是 422**，别的地方参数校验都是 400（见文首说明）。
> 原因是它刻意绕开 Pydantic、由 service 抛业务异常 —— 若交给 Pydantic，
> 会被全局处理器统一改写成 400。

### 11.2 我的简历列表

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/candidate/resumes` |
| 鉴权 | `candidate` |

**查询参数**

| 参数 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `limit` | integer | 否 | **≤200** | `50` |

**响应 `200`** —— 简历数组（[§13.7](#1326-resumeout)），按 `updated_at` **降序**（最近改的在前）。
没有简历时返回 `[]`。

> 列表**会下发 `content` 全文**。候选人的简历就是一份文本，列表页通常要显示摘要，
> 少了它就得逐条再查一次。

**错误**：`400 VALIDATION_ERROR`（`limit` > 200，**明确报错而不是静默截断**）。

### 11.3 简历详情

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/candidate/resumes/{resume_id}` |
| 鉴权 | `candidate` |

**响应 `200`** —— 简历对象（[§13.7](#1326-resumeout)）。

**错误**：`403 FORBIDDEN`（`无权限访问该简历`——是别人的简历）；`404 NOT_FOUND`（`简历不存在`）。

### 11.4 更新我的简历

| 项 | 内容 |
|---|---|
| 提交方式 | `PUT` |
| URL | `/api/candidate/resumes/{resume_id}` |
| 鉴权 | `candidate` |

**请求体** —— 四个字段**全部可选**，**只传要改的**

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string \| null | 改标题 |
| `content` | string \| null | 改正文（同样 ≤20000 字符） |
| `candidate_name` | string \| null | — |
| `candidate_contact` | string \| null | — |

> ⚠️ **是 `PUT` 但语义是「部分更新」**（按 PRD §8 定的方法名）。
> 漏传的字段**保持不变**；传显式的 `null` 也表示「不修改」。
> 因此**没有「把姓名清空」这个操作** —— 对简历这种整块文本，清空与不填在展示上等价。

**响应 `200`** —— 更新后的简历对象，`updated_at` 已刷新。

> `updated_at` 有实际用途：**候选人改了简历后，HR 需要知道手上这份是不是最新的**，
> 因此改完要重新触发补题（[§8.15](#815-按简历补题)）才会生效。

**错误**：`400`（校验）/ **`422`**（正文超长）/ `403`（别人的简历）/ `404`（不存在）。

### 11.5 删除我的简历

| 项 | 内容 |
|---|---|
| 提交方式 | `DELETE` |
| URL | `/api/candidate/resumes/{resume_id}` |
| 鉴权 | `candidate` |

**响应 `204`** —— **无响应体**。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 403 | `FORBIDDEN` | 是别人的简历 | `无权限访问该简历` |
| 404 | `NOT_FOUND` | 简历不存在 | `简历不存在` |
| 409 | `BUSINESS_ERROR` | **简历已被某场面试或某次练习关联** | `该简历已被面试或练习关联，无法删除` |

> 409 时**简历仍然存在**（事务整体回滚）。前端应提示「先解除关联再删除」，
> 并给出「去解除关联」的入口（[§10.7](#107-关联--解除关联简历)）。

---

## 十二、刷题练习（候选人端）

刷题是**独立的业务线**，与真实面试完全解耦：**不依赖 `interview`**，
练习数据也不会出现在任何面试里。取题来源是**同一个题库**（HR 建的那些题）。

**判分规则总览**（决定前端看到什么）：

| 题型 | 判分方式 | 消耗 AI？ |
|---|---|---|
| 单选 `single_choice` | **本地规则**：与参考答案 strip 后精确比对 | ❌ 不消耗 |
| 简答 `short_answer` + 有参考答案 | 调 AI 判分并取解析 | ✅ 消耗 |
| 简答 + **无参考答案** | **不调 AI**，标为「未判分」（`is_correct` / `score` 为 `null`） | ❌ 不消耗 |
| 空白作答 | 直接判错（0 分），解析为「未作答」 | ❌ 不消耗 |
| AI 判分失败 | **仍返回 200**，作答落库但标为未判分，稍后可重判 | — |

> `is_correct` 是**三态**：`true` 判对 / `false` 判错 / **`null` 未判分**。
> 「未判分」不是「判错」—— 它**不进错题本**，也**不进正确率的分母**。

### 12.1 刷题取题（预览）

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/practice/questions` |
| 鉴权 | `candidate` |

**查询参数**（AND 关系）：`position_id`、`category`、`dimension`、`difficulty`、
`question_type`、`limit`。

**响应 `200`** —— 题目预览数组（[§13.19](#1319-practicequestionout)），**不含答案与解析**。

> 这是**预览**用途（比如先看看能刷到哪些题）。真正开始练习请用
> [§12.3](#123-开始一次练习)，由服务端取题并写快照。
>
> ⚠️ 这个接口**不接受 `resume_id`**，也**不调用 AI** —— 按简历推荐只在开始练习时发生。

**错误**：`403 FORBIDDEN`（HR / admin 调用）。

### 12.2 我的练习会话列表

含**进行中**的会话 —— 候选人可以据此继续未完成的练习，或回看历史。

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/practice/sessions` |
| 鉴权 | `candidate` |

**查询参数**

| 参数 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `status` | string | 否 | `ongoing` \| `finished` | 不传 = 全部 |
| `limit` | integer | 否 | **≤100** | `20` |

**响应 `200`** —— 会话列表项数组（[§13.21](#1321-practicesessionlistitem)），
按 `started_at` **降序**。

> 列表项**不含题目明细**（那是 [§12.4](#124-练习详情与进度) 的事）—— 否则一次历史
> 拉取会顺带把 20 个会话 × 20 道题全带回来。

### 12.3 开始一次练习

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/practice/sessions` |
| 鉴权 | `candidate` |

**请求体** —— 全部可选，不选即「全库随机刷题」

| 字段 | 类型 | 必填 | 约束 | 默认值 |
|---|---|---|---|---|
| `position_id` | integer \| null | 否 | — | 不筛选 |
| `category` | string \| null | 否 | — | 不筛选 |
| `dimension` | string \| null | 否 | — | 不筛选 |
| `difficulty` | string \| null | 否 | `easy` \| `medium` \| `hard` | 不筛选 |
| `question_type` | string \| null | 否 | `single_choice` \| `short_answer` | 不筛选 |
| `size` | integer \| null | 否 | **≤20** | `PRACTICE_SESSION_SIZE_DEFAULT`（默认 `10`） |
| `resume_id` | integer \| null | 否 | **≥1**，须是本人的简历 | `null`（不按简历推荐） |

```json
{ "position_id": 1, "difficulty": "medium", "size": 10, "resume_id": 4 }
```

**响应 `201`** —— 练习详情（[§13.20](#1320-practicesessiondetail)），
`items` 里是**本次待答项**，此时都还没有作答。

```json
{
  "session": {
    "id": 7, "status": "ongoing", "position_id": 1,
    "category": null, "dimension": null, "difficulty": "medium", "question_type": null,
    "total": 10, "answered_count": 0, "correct_count": 0,
    "started_at": "2026-09-21T14:00:00", "finished_at": null
  },
  "items": [
    {
      "item_id": 61, "seq": 1,
      "question": {
        "id": 12, "position_id": 1, "category": "基础", "dimension": "专业能力",
        "difficulty": "easy", "content": "HTTP 状态码 401 表示什么？",
        "question_type": "single_choice",
        "options": ["未认证", "未授权", "资源不存在", "服务器错误"],
        "tags": ["网络"]
      },
      "user_answer": null, "is_correct": null, "score": null,
      "explanation": null, "reference_answer": null
    }
  ],
  "resume_id": 4,
  "resume_match_applied": true
}
```

**关于 `resume_id` 与 `resume_match_applied`（两个字段回答两个不同问题）**

| 字段 | 含义 |
|---|---|
| `resume_id` | 候选人**想**用哪份简历 |
| `resume_match_applied` | 系统**实际做到了没有** —— 真的用 AI 按简历选排了题才为 `true` |

> ⚠️ **降级是静默的，但必须让用户知道**：AI 失败时练习**照常创建（`201`）**，
> 只是退回普通筛选，此时 `resume_id` 非空而 `resume_match_applied = false`。
> **前端要据此显示降级说明** —— 否则用户关联了简历却拿到一堆通用题，界面上没有任何解释，
> 只能认为功能坏了。判断条件就是那两个字段的组合。

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `size` > 20 / `resume_id` < 1 | `请求参数不合法` |
| 403 | `FORBIDDEN` | `resume_id` 是别人的简历 | `无权限访问该简历` |
| 404 | `NOT_FOUND` | `resume_id` 对应的简历不存在 | `简历不存在` |
| 409 | `BUSINESS_ERROR` | 按条件取不到题 | `没有符合条件的题目，请调整筛选条件` |
| 409 | `BUSINESS_ERROR` | 触发进程内限流（默认 60 次/分钟） | `操作过于频繁，请稍后再试` |

> 409 取不到题时**不会留下空的会话记录** —— 事务整体回滚。
>
> **限流是进程内计数**（单机约束下不引入 Redis），限额 `PRACTICE_RATE_LIMIT_PER_MINUTE`
> 按候选人计、60 秒滑动窗口。

### 12.4 练习详情与进度

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/practice/sessions/{session_id}` |
| 鉴权 | `candidate` |

**响应 `200`** —— 练习详情（[§13.20](#1320-practicesessiondetail)），`items` 按 `seq` 升序。

> ⚠️ **答案与解析按题逐个解锁**：`explanation` 与 `reference_answer`
> **只有该题已提交后才非空**，未提交的题这两项恒为 `null`。
> 这是防作弊的关键 —— 不能让人一次性把答案全拉出来。前端不要提前渲染。

**错误**：`403 FORBIDDEN`（`无权限访问该练习`——是别人的会话）；`404 NOT_FOUND`（`练习不存在`）。

### 12.5 提交作答（即时判分）

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/practice/sessions/{session_id}/items` |
| 鉴权 | `candidate` |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `item_id` | integer | 是 | **必须属于该会话** | 待答项 id（注意不是题目 id） |
| `user_answer` | string | 否 | ≤5000 字符，**允许空串** | 空串 = 未作答 |

```json
{ "item_id": 61, "user_answer": "未认证" }
```

**响应 `200`** —— 判分结果（[§13.22](#1322-practiceitemresult)）。

```json
{
  "item_id": 61, "seq": 1,
  "user_answer": "未认证",
  "is_correct": true,
  "score": 10.0,
  "correct_answer": "未认证",
  "reference_answer": null,
  "explanation": "401 表示身份未认证或认证失败；403 才是已认证但无权限。",
  "progress": { "answered_count": 1, "correct_count": 1, "total": 10 }
}
```

| 字段 | 说明 |
|---|---|
| `correct_answer` | **单选题**的参考答案 |
| `reference_answer` | **简答题**的参考答案（按题型二选一，另一个为 `null`） |
| `explanation` | 解析 |
| `progress` | 会话进度的**实时重算值** |

**错误**

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `user_answer` 超长 | `请求参数不合法` |
| 403 | `FORBIDDEN` | 是别人的会话 | `无权限访问该练习` |
| 404 | `NOT_FOUND` | 会话不存在 / **题目不属于该练习** | `题目不属于该练习` |
| 409 | `BUSINESS_ERROR` | 会话已 `finished` | `本次练习已结束，不可继续作答` |

> 同一题**可以重复提交**（错题重练是正当用法）。会话的两个计数**每次提交后重算**、
> 不做累加 —— 否则重复提交会让计数超过总题数。

### 12.6 重新判分

对**未判分**的题重试判分。用于「当时 AI 不可用 / 题目还没有参考答案，后来补上了」的场景。

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/practice/items/{item_id}/rescore` |
| 鉴权 | `candidate` |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 与 [§12.5](#125-提交作答即时判分) 同构的判分结果。

> **只对未判分的题生效**。对**已判分**的题调用是**幂等**的：直接返回原结果，
> **不会重新调用 AI**，也不会改写分数。

**错误**：`403 FORBIDDEN`（是别人的作答）；`404 NOT_FOUND`（作答项不存在）。

### 12.7 结束练习

| 项 | 内容 |
|---|---|
| 提交方式 | `POST` |
| URL | `/api/practice/sessions/{session_id}/finish` |
| 鉴权 | `candidate` |

**参数**：仅路径参数。**无请求体。**

**响应 `200`** —— 练习小结（[§13.23](#1323-practicesessionsummary)）。

```json
{
  "session_id": 7, "status": "finished",
  "total": 10, "answered_count": 8, "correct_count": 5, "unscored_count": 1,
  "accuracy": 0.714,
  "by_dimension": [
    { "dimension": "专业能力", "answered": 5, "correct": 3, "accuracy": 0.6 }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `unscored_count` | **未判分**的题数（`is_correct` 为 `null`） |
| `accuracy` | 正确率。**分母是已判分数**（`answered_count - unscored_count`）；一题都没判时为 `null` |
| `by_dimension` | 按维度拆分的正确率 |

> 重复调用结束接口**幂等**（`finished_at` 不会被刷新）。

**错误**：`403 FORBIDDEN`（是别人的会话）；`404 NOT_FOUND`（会话不存在）。

### 12.8 错题本

**不单独建表**，由「判错的作答」派生查询。

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/practice/wrong-book` |
| 鉴权 | `candidate` |

**查询参数**：`position_id`、`dimension`、`question_type`、`limit`（**≤200**，默认 `50`）。

**响应 `200`** —— 错题数组（[§13.24](#1324-wrongbookitem)），按最后答错时间**降序**。

```json
[
  {
    "question_id": 12,
    "content": "HTTP 状态码 401 表示什么？",
    "options": ["未认证", "未授权", "资源不存在", "服务器错误"],
    "reference_answer": "未认证",
    "explanation": "…",
    "my_wrong_answer": "未授权",
    "wrong_count": 2,
    "last_wrong_at": "2026-09-21T14:30:00"
  }
]
```

| 字段 | 说明 |
|---|---|
| `wrong_count` | 同一道题错了几次（**按 `question_id` 去重**，一题一行） |
| `my_wrong_answer` | 最近一次的错误作答 |
| — | **未判分的题不进错题本**（`is_correct` 为 `null` 不算错） |

> 按 `question_id` 去重是刻意的：同一道题刷两次都错，列表里仍只有一行、`wrong_count` 累加 ——
> 否则错题本会被重复题目淹没。

### 12.9 练习统计

| 项 | 内容 |
|---|---|
| 提交方式 | `GET` |
| URL | `/api/practice/stats` |
| 鉴权 | `candidate` |

**参数**：无。

**响应 `200`** —— 统计对象（[§13.25](#1325-practicestats)）。

```json
{
  "total_answered": 40, "scored_count": 36, "unscored_count": 4,
  "correct_count": 24, "accuracy": 0.667, "session_count": 5,
  "by_dimension": [ { "dimension": "专业能力", "answered": 20, "scored": 18, "correct": 12, "accuracy": 0.667 } ],
  "by_type": [ { "question_type": "single_choice", "answered": 22, "scored": 22, "correct": 15, "accuracy": 0.682 } ]
}
```

| 字段 | 说明 |
|---|---|
| `total_answered` | 累计作答数（按**次**算，同一题重复提交会重复计数） |
| `scored_count` / `unscored_count` | 已判分 / 未判分 |
| `accuracy` | **分母是 `scored_count`**，不含未判分 |
| `by_dimension` / `by_type` | 按维度 / 按题型的拆分 |

> 正确率的分子分母都不含未判分的题 —— 否则 AI 不可用期间的作答会凭空拉低正确率。

---

## 十三、数据模型

### 13.1 UserOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `username` | string | 全局唯一 |
| `role` | string | `admin` \| `hr` \| **`candidate`** |
| `is_active` | boolean | 禁用后旧 token 立即失效 |
| `created_at` | datetime | |

> `POST /api/users` 只能建出 `admin` / `hr`；`candidate` 账号只能来自自助注册
> （[§5.6](#56-候选人自助注册)）或凭邀请码激活（[§10.2](#102-接受邀请码)）。

### 13.2 PositionOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `name` | string | 同一创建人下唯一 |
| `jd` | string | |
| `evaluation_dimensions` | string[] | 已 strip、保留原始大小写 |
| `created_by` | integer | 数据隔离键 |
| `created_at` | datetime | |

### 13.3 QuestionOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `position_id` | integer | |
| `category` | string | 未指定时为 `"通用"` |
| `dimension` | string | 必属该岗位的评估维度 |
| `content` | string | 题干 |
| `difficulty` | string | `easy` \| `medium` \| `hard` |
| `question_type` | string | `single_choice` \| `short_answer` |
| `options` | string[] | 单选题的选项；**简答题恒为 `[]`** |
| `reference_answer` | string \| null | 单选必有；简答可空 |
| `explanation` | string \| null | 答案解析 |
| `tags` | string[] | |
| `source` | string | `bank` \| `ai` |
| `created_by` | integer | 数据隔离键 |
| `created_at` | datetime | |

> ⚠️ `QuestionOut` 是 **HR 侧**的题目视图，**含参考答案与解析**。
> 候选人刷题看到的是 [§13.19 PracticeQuestionOut](#1319-practicequestionout)，
> 那是另一套字段（不含答案）—— 两者不是同一个模型，不要混用。

### 13.4 InterviewListItem

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

### 13.5 InterviewDetail

继承 `InterviewListItem`，并新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| `jd` | string | 岗位 JD |
| `evaluation_dimensions` | string[] | 岗位**当前**的维度 |
| `questions` | QuestionItem[] | 按 `seq` 升序 |
| `resume_id` | integer \| null | 本场关联的简历；**只有详情有，列表没有** |

> `evaluation_dimensions` 取岗位**当前**值，而 `questions[].dimension` 取**出题时的快照** ——
> 因此岗位改了维度后，历史面试的维度列不会跟着漂移。

### 13.6 QuestionItem

面试内的题目。`interview_question_id` 是保存回答时使用的 id。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | **保存回答时使用这个 id** |
| `seq` | integer | 从 1 连续 |
| `content` | string | 取自出题时的快照 |
| `dimension` | string | 取自快照 |
| `source` | string | **题目**来源快照：`bank` \| `ai` \| `resume_match` |
| `answer` | string \| null | 未作答案为 `null` |
| `recorded_at` | datetime \| null | 最后录入时间 |
| `answer_source` | string \| null | **作答**来源：`hr` \| `candidate`；无作答为 `null` |
| `match_reason` | string \| null | 仅 `source = resume_match` 的题非空，见 [§8.15](#815-按简历补题) |

> ⚠️ `source` 与 `answer_source` 是**两个不同的东西**，名字相似但语义无关：
> `source` 说的是**这道题从哪来**（题库 / AI 生成 / 简历匹配），
> `answer_source` 说的是**这条回答最初由谁录入**（HR 手工 / 候选人在线）。
> 它们不是同一个字段的两种叫法，别写混。

> `match_reason` 只在 **HR 侧**下发，候选人视图里结构上不存在（见 [§10.4](#104-面试详情候选人视图)）。

### 13.7 ReportDetail

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

### 13.8 InterviewResumeOut

HR 读到的候选人简历（[§8.16](#816-读取面试关联的简历)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `resume_id` | integer | |
| `title` | string | |
| `content` | string | 简历正文全文 |
| `candidate_name` | string \| null | |
| `candidate_contact` | string \| null | |
| `updated_at` | datetime | HR 据此判断手上这份是不是最新的 |

> **不含 `created_by` / `created_at`** —— HR 不需要知道候选人的 user id。

### 13.9 InvitationView

作答邀请（[§8.9](#89-生成作答邀请码) / [§8.10](#810-邀请列表与状态) / [§8.11](#811-撤销邀请)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 撤销时用这个 id |
| `interview_id` | integer | |
| `code` | string | 明文邀请码，22 字符 |
| `status` | string | `pending` \| `accepted` \| `revoked` \| **`expired`（派生）** |
| `expires_at` | datetime | 生成时间 + 7 天 |
| `accepted_at` | datetime \| null | |
| `candidate_username` | string \| null | 接受后回填 |
| `created_at` | datetime | |

### 13.10 PrepOut

面试前准备提纲（[§8.12](#812-生成--重新生成准备提纲)–[§8.14](#814-编辑准备提纲)）。
三个部分**要么都有、要么都没有**。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | 一场面试一份 |
| `outline` | PrepOutlineStageOut[] | 分阶段时间安排 |
| `focus_points` | PrepFocusPointOut[] | 按评估维度的考察重点 |
| `question_plan` | PrepQuestionItemOut[] | 建议提问与考察意图 |
| `generated_at` | datetime | 最近一次 **AI 生成**的时刻 |
| `edited_at` | datetime \| null | 最近一次 **HR 手工编辑**；重新生成时**置回 `null`** |

**PrepOutlineStageOut**

| 字段 | 类型 | 约束 |
|---|---|---|
| `seq` | integer | ≥1，阶段顺序 |
| `phase` | string | 阶段名 |
| `duration_min` | integer | ≥1，分钟 |
| `notes` | string | 要点 |

**PrepFocusPointOut**

| 字段 | 类型 | 说明 |
|---|---|---|
| `dimension` | string | 对应岗位维度 |
| `point` | string | 应重点验证的能力项 |
| `reason` | string | 为什么重点看它 |

**PrepQuestionItemOut**

| 字段 | 类型 | 说明 |
|---|---|---|
| `question` | string | 建议提问 |
| `intent` | string | 考察意图 |
| `follow_ups` | string[] | 可追问方向 |

### 13.11 MatchResult

按简历补题的结果（[§8.15](#815-按简历补题)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `added_count` | integer | 本次追加了几题；**`0` 是正常结果** |
| `added` | MatchAddedItem[] | 本次追加的题目 |
| `total_questions` | integer | 本场**当前**题目总数（累加后） |

**MatchAddedItem**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | |
| `seq` | integer | 续接本场最大值，连续无缺口 |
| `content` | string | 题干快照 |
| `dimension` | string | 维度快照 |
| `match_reason` | string \| null | AI 给出的匹配理由，**非空** |

### 13.12 CandidateFeedbackOut

候选人脱敏反馈（[§9.5](#95-候选人脱敏反馈)）。
**这是一个白名单模型** —— 未在此定义的字段不可能出现在响应里。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | |
| `level` | string | `summary` \| `full`，**由服务端配置决定** |
| `conclusion` | string | 面向本人的重写，**不含去留判断** |
| `strengths` | string[] | 条目与 HR 报告一致 |
| `weaknesses` | string[] | 条目与 HR 报告一致 |
| `overall_score` | number \| null | `summary` 恒为 `null`；`full` 为 0–10 |
| `generated_at` | datetime | |

> **逐题分、维度分、雷达图不在这个模型里** —— 不是「不下发」，是**结构上不存在**。
> 加字段时请先想清楚可见性，这里是候选人可见性的唯一出口。

### 13.13 PracticePositionOut

刷题岗位筛选项（[§10.1](#101-刷题岗位筛选项)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `name` | string | |
| `question_count` | integer | 该岗位当前题目总数（不限创建人） |

> **不含 `jd`，也不含 `created_by`** —— 候选人只需要一个筛选标识。

### 13.14 InvitationAcceptResult

接受邀请的结果（[§10.2](#102-接受邀请码)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | |
| `interview` | object | 见下 |

**`interview` 内联对象**

| 字段 | 类型 |
|---|---|
| `id` | integer |
| `position_name` | string |
| `candidate_name` | string |
| `status` | string |
| `question_count` | integer |

> **没有 `token`** —— 接受邀请不等于登录。

### 13.15 CandidateInterviewItem

候选人「我参与的面试」列表项（[§10.3](#103-我的面试列表)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `position_name` | string | |
| `status` | string | 面试状态 |
| `question_count` | integer | 题目总数 |
| `answered_count` | integer | 我已回答的题数（非空作答） |
| `submitted` | boolean | 我是否已交卷 |
| `resume_id` | integer \| null | 本场关联的简历，未关联为 `null` |
| `created_at` | datetime | |

### 13.16 CandidateInterviewDetail

候选人视角的面试详情（[§10.4](#104-面试详情候选人视图)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `position_name` | string | |
| `status` | string | |
| `created_at` | datetime | |
| `submitted` | boolean | |
| `submitted_at` | datetime \| null | |
| `resume_id` | integer \| null | |
| `questions` | CandidateQuestionItem[] | 按 `seq` 升序 |

**CandidateQuestionItem**（**只有这 5 个键**）

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | 作答时用这个 id |
| `seq` | integer | |
| `content` | string | 快照题干 |
| `dimension` | string | 快照维度 |
| `my_answer` | string \| null | 我的作答，未作答为 `null` |

### 13.17 CandidateAnswerView

候选人保存作答的响应（[§10.5](#105-保存--更新我的作答)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | integer | |
| `content` | string | 我的作答 |
| `submitted_at` | datetime \| null | 本场的交卷时间；未交卷为 `null` |

### 13.18 SubmitResult

交卷结果（[§10.6](#106-交卷)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | integer | |
| `submitted_at` | datetime | **首次**交卷时刻，重复交卷不刷新 |
| `answered_count` | integer | 非空作答数（空串与未作答不计） |

### 13.19 PracticeQuestionOut

刷题题目视图（[§12.1](#121-刷题取题预览) 的取题结果，以及
[§13.20 PracticeSessionDetail](#1320-practicesessiondetail) 里每题内联的 `question`）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 题目 id |
| `position_id` | integer | |
| `category` | string | |
| `dimension` | string | 取**快照** |
| `difficulty` | string | 取题库当前值 |
| `content` | string | 题干，取**快照** |
| `question_type` | string | 取**快照**（判分分支依赖它，不能漂移） |
| `options` | string[] | 取**快照** |
| `tags` | string[] | 取题库当前值 |

> ⚠️ **没有 `reference_answer`，没有 `explanation`，没有 `source`、`created_by`、`created_at`。**
> 这是防作弊的落点 —— 取题阶段就不下发答案。
> 「题干/选项/维度/题型」取快照（题库改题不影响进行中的练习），
> 「岗位/分类/难度/标签」取当前值（不参与判分，也不涉及答案泄露）。

### 13.20 PracticeSessionDetail

练习详情（[§12.3](#123-开始一次练习) 创建时返回，[§12.4](#124-练习详情与进度) 查询时返回）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `session` | PracticeSessionOut | 会话本身 |
| `items` | PracticeItemOut[] | 待答项，按 `seq` 升序 |
| `resume_id` | integer \| null | 本次关联的简历 |
| `resume_match_applied` | boolean | **是否真的**按简历选排了题；默认 `false` |

**PracticeSessionOut**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `status` | string | `ongoing` \| `finished` |
| `position_id` | integer \| null | `null` = 全库随机 |
| `category` / `dimension` / `difficulty` / `question_type` | string \| null | 本次筛选条件留痕 |
| `total` | integer | 总题数 |
| `answered_count` | integer | 已作答数 |
| `correct_count` | integer | 判对题数 |
| `started_at` | datetime | |
| `finished_at` | datetime \| null | |

**PracticeItemOut**

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_id` | integer | **提交作答时用这个 id**（不是题目 id） |
| `seq` | integer | |
| `question` | PracticeQuestionOut | 见 [§13.19](#1319-practicequestionout) |
| `user_answer` | string \| null | 未作答案为 `null`（空串表示提交了空答案） |
| `is_correct` | boolean \| null | **三态**：判对 / 判错 / `null` 未判分 |
| `score` | number \| null | |
| `explanation` | string \| null | **只有该题已提交后才非空** |
| `reference_answer` | string \| null | **只有该题已提交后才非空** |

> ⚠️ `items[].is_correct` 的 `null` 与 `false` 语义完全不同：
> `null` 是「未判分」（无参考答案，或 AI 判分失败），`false` 是「判错了」。
> 前端不要把 `null` 渲染成「答错」。

### 13.21 PracticeSessionListItem

练习会话列表项（[§12.2](#122-我的练习会话列表)）。**刻意不含题目明细。**

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | integer | |
| `status` | string | |
| `position_name` | string \| null | |
| `category` / `dimension` / `difficulty` / `question_type` | string \| null | 筛选条件留痕 |
| `total` / `answered_count` / `correct_count` | integer | |
| `started_at` | datetime | |
| `finished_at` | datetime \| null | |

### 13.22 PracticeItemResult

提交作答 / 重新判分的判分结果（[§12.5](#125-提交作答即时判分) / [§12.6](#126-重新判分)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_id` | integer | |
| `seq` | integer | |
| `user_answer` | string | |
| `is_correct` | boolean \| null | 三态，同 [§13.20](#1320-practicesessiondetail) |
| `score` | number \| null | |
| `correct_answer` | string \| null | **单选题**的参考答案 |
| `reference_answer` | string \| null | **简答题**的参考答案 |
| `explanation` | string \| null | 解析 |
| `progress` | PracticeProgress | 会话进度（实时重算值） |

**PracticeProgress**

| 字段 | 类型 |
|---|---|
| `answered_count` | integer |
| `correct_count` | integer |
| `total` | integer |

> `correct_answer` 与 `reference_answer` **按题型二选一**，另一个为 `null` ——
> 单选把答案放 `correct_answer`，简答放 `reference_answer`。前端取「非空的那个」即可。

### 13.23 PracticeSessionSummary

练习小结（[§12.7](#127-结束练习)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | integer | |
| `status` | string | 恒为 `finished` |
| `total` | integer | 总题数 |
| `answered_count` | integer | 已作答 |
| `correct_count` | integer | 判对 |
| `unscored_count` | integer | **未判分**的题数 |
| `accuracy` | number \| null | 正确率；**分母为已判分数**；一题未判时为 `null` |
| `by_dimension` | DimensionAccuracy[] | 按维度拆分 |

**DimensionAccuracy**

| 字段 | 类型 |
|---|---|
| `dimension` | string |
| `answered` | integer |
| `correct` | integer |
| `accuracy` | number \| null |

### 13.24 WrongBookItem

错题本条目（[§12.8](#128-错题本)）。**按 `question_id` 去重**，一题一行。

| 字段 | 类型 | 说明 |
|---|---|---|
| `question_id` | integer | 去重键 |
| `content` | string | 题干 |
| `options` | string[] | |
| `reference_answer` | string \| null | |
| `explanation` | string \| null | |
| `my_wrong_answer` | string | **最近一次**的错误作答 |
| `wrong_count` | integer | 同一道题错了几次 |
| `last_wrong_at` | datetime \| null | 最后答错时间 |

> **未判分的题不进错题本**（`is_correct` 为 `null` 不算错）。

### 13.25 PracticeStats

练习统计（[§12.9](#129-练习统计)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `total_answered` | integer | 累计作答数（按**次**算，同题重复提交会重复计数） |
| `scored_count` | integer | 已判分 |
| `unscored_count` | integer | 未判分 |
| `correct_count` | integer | 判对 |
| `accuracy` | number \| null | **分母是 `scored_count`** |
| `session_count` | integer | 练习会话数 |
| `by_dimension` | DimensionStats[] | 按维度 |
| `by_type` | TypeStats[] | 按题型 |

**DimensionStats**

| 字段 | 类型 |
|---|---|
| `dimension` | string |
| `answered` | integer |
| `scored` | integer |
| `correct` | integer |
| `accuracy` | number \| null |

**TypeStats**

| 字段 | 类型 |
|---|---|
| `question_type` | string |
| `answered` | integer |
| `scored` | integer |
| `correct` | integer |
| `accuracy` | number \| null |

### 13.26 ResumeOut

候选人自己的简历视图（[§11.1](#111-新建简历)–[§11.4](#114-更新我的简历)）。

> 编号排在最后是因为它是后补的，**章节顺序仍是「十一、简历管理」**，按需跳转即可。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | |
| `title` | string | |
| `content` | string | 简历正文全文；**列表也会下发**（见 [§11.2](#112-我的简历列表)） |
| `candidate_name` | string \| null | |
| `candidate_contact` | string \| null | |
| `created_at` | datetime | |
| `updated_at` | datetime | 每次更新刷新；HR 据此判断手上这份是不是最新的 |

> **不含 `created_by`** —— 候选人不需要知道自己的 user id。

---

## 十四、完整流程示例

一次完整的面试生命周期（`PROVIDER_NAME=mock`）。

### 14.1 curl 版

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

### 14.2 前端 JS 版

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

### 14.3 候选人端流程（在线作答）

从「HR 发邀请」到「候选人看到反馈」的完整一遍（`PROVIDER_NAME=mock`）。
**注意第 2 步多绕了一下** —— 那是 [§10.2 已知偏差 1](#102-接受邀请码) 导致的，不是笔误。

```bash
# ── 1. HR：给某场 ongoing 的面试生成邀请码 ──────────────────────────
curl -s -X POST http://localhost:8000/api/interviews/3/invitations \
  -H "Authorization: Bearer $HR_TOKEN"
# → {"id":1,"code":"hT9rQ2xLm4ZbN1vCk8sPwA","status":"pending", ...}
CODE="hT9rQ2xLm4ZbN1vCk8sPwA"

# ── 2. 候选人：先注册一个刷题账号，再登录，再 accept ────────────────
#     （偏差 1：accept 要求调用者已经是登录中的 candidate）
curl -s -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"cand_li","password":"cand12345678"}'
# → 201，注意响应里**没有 token**

curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"cand_li","password":"cand12345678"}'
# → {"token":"eyJ...","user":{"role":"candidate", ...}}
CAND_TOKEN="eyJ..."

curl -s -X POST "http://localhost:8000/api/candidate/invitations/$CODE/accept" \
  -H "Authorization: Bearer $CAND_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"cand_li","password":"cand12345678"}'
# → 200 {"interview_id":3,"interview":{...}}，邀请状态变 accepted

# ── 3. 候选人：建一份简历，并关联到这场面试 ──────────────────────────
curl -s -X POST http://localhost:8000/api/candidate/resumes \
  -H "Authorization: Bearer $CAND_TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"李四-后端","content":"教育经历…\n项目经历…","candidate_name":"李四"}'
# → 201 {"id":4, ...}

curl -s -X PUT http://localhost:8000/api/candidate/interviews/3/resume \
  -H "Authorization: Bearer $CAND_TOKEN" -H 'Content-Type: application/json' \
  -d '{"resume_id":4}'
# → 200 {"resume_id":4,"title":"李四-后端", ...}
#    解除关联： -d '{"resume_id":null}'

# ── 4. HR：读到简历 → 按简历补题 ────────────────────────────────────
curl -s http://localhost:8000/api/interviews/3/resume -H "Authorization: Bearer $HR_TOKEN"
# → 200（没关联过就是 404，不是 403）

curl -s -X POST http://localhost:8000/api/interviews/3/questions/match \
  -H "Authorization: Bearer $HR_TOKEN" -H 'Content-Type: application/json' \
  -d '{"count":3}'
# → {"added_count":2,"added":[{"seq":9,...,"match_reason":"…"}],"total_questions":10}

# ── 5. 候选人：逐题作答 → 交卷 ──────────────────────────────────────
curl -s http://localhost:8000/api/candidate/interviews/3 -H "Authorization: Bearer $CAND_TOKEN"
# → 拿到 questions[].interview_question_id

curl -s -X POST http://localhost:8000/api/candidate/interviews/3/answers \
  -H "Authorization: Bearer $CAND_TOKEN" -H 'Content-Type: application/json' \
  -d '{"interview_question_id":41,"content":"我在上一家公司…"}'
# → 200（可反复调，是更新不是新增）

curl -s -X POST http://localhost:8000/api/candidate/interviews/3/submit \
  -H "Authorization: Bearer $CAND_TOKEN"
# → 200 {"interview_id":3,"submitted_at":"…","answered_count":5}
#    交卷后候选人侧锁定；**面试状态仍是 ongoing**，等 HR 标记完成

# ── 6. HR：标记完成 → 触发评估 → 收 SSE 流 ──────────────────────────
curl -s -X POST http://localhost:8000/api/interviews/3/complete -H "Authorization: Bearer $HR_TOKEN"
curl -s -X POST http://localhost:8000/api/interviews/3/evaluate -H "Authorization: Bearer $HR_TOKEN"
# → 202 {"interview_id":3,"status":"evaluating","stream_url":"/api/interviews/3/evaluation/stream"}

curl -N http://localhost:8000/api/interviews/3/evaluation/stream \
  -H "Authorization: Bearer $HR_TOKEN"
# → event: question / dimension / report / done（按序）

# ── 7. 候选人：查看脱敏反馈 ─────────────────────────────────────────
curl -s http://localhost:8000/api/candidate/interviews/3/feedback \
  -H "Authorization: Bearer $CAND_TOKEN"
# → 200，只有 conclusion / strengths / weaknesses（+ level / generated_at）
#    没评估完之前是 409 评估尚未完成
```

> 第 6 步的 SSE 在 curl 里要用 `-N`（关闭缓冲）才看得到实时输出。
> 前端必须用 `fetch` + `ReadableStream`，见 [§15.2](#152-sse-必须用-fetch--readablestream)。

---

## 十五、前端对接要点

### 15.1 统一错误处理

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

### 15.2 SSE 必须用 `fetch` + `ReadableStream`

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

### 15.3 状态机驱动的 UI

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

### 15.4 其他注意事项

| 项 | 说明 |
|---|---|
| **`interview_question_id`** | 保存回答用的是 `questions[].interview_question_id`，**不是** `seq`，也不是题目 id |
| **练习提交用 `item_id`** | 刷题的 `POST /practice/sessions/{id}/items` 用的是 `items[].item_id`，**不是** `question.id` |
| **`204` 无响应体** | 岗位 / 题目 / 简历的 `DELETE` 返回 204，不要对其调用 `.json()` |
| **`200` 带响应体的「删除」** | ⚠️ **撤销邀请（`DELETE .../invitations/{id}`）返回 `200` 而不是 `204`**，需要读 `status` 更新那一行 |
| **`202` 不是失败** | 触发评估返回 202，用 `response.ok` 判断，别只看 `=== 200` |
| **`401` 与 `403` 要分开处理** | 401（`UNAUTHORIZED` / `INVALID_TOKEN`）→ 跳登录；403（`FORBIDDEN`）→ 提示无权限，**不要跳登录**（跳了也还是 403） |
| **`409` 里混着正常业务结果** | 大多数 409 是「状态不允许」，但补题的 `added_count=0` 是 **200**；别把 409 一律当成系统故障提示 |
| **创建面试可能较慢** | 该接口**同步出题**。`PROVIDER_NAME=mock`（默认）时几乎瞬时返回；切到真实大模型后耗时会显著上升，前端应准备 loading 态并放宽超时 |
| **列表不分页** | 列表返回全量数组。少数列表的 `limit` **只有上限、没有 offset**，超上限是 400 而不是截断 |
| **时间无时区** | 形如 `2026-09-17T10:30:00`，按本地时间解析 |

### 15.5 两端登录态必须按端分 key 存储

同一个浏览器里 HR 与候选人要**同时登录**时，两套 token 不能共用一个 localStorage key：

```js
// ✅ 按端分 key
localStorage.setItem('hr.token', hrToken);
localStorage.setItem('candidate.token', candidateToken);

// ❌ 共用一个 key —— 后登录的会把先登录的顶掉
localStorage.setItem('token', token);
```

`POST /api/auth/login` **对三种角色是同一个接口**，所以前端只能靠响应里的 `role` 决定
「这套 token 该存到哪个 key、该跳哪个路由」：

```js
const { token, user } = await login(username, password);
if (user.role === 'candidate') {
  localStorage.setItem('candidate.token', token);
  location.hash = '#/candidate';
} else {
  localStorage.setItem('hr.token', token);   // admin 也走 HR 端
  location.hash = '#/hr';
}
```

> 后端不做任何区分，也没有「当前登录端」的概念 —— 它只看你这次请求带的是谁的头。
> 两套 token 各自对应各自的守卫，混用一律 403。

### 15.6 下载 DOCX 必须先 `fetch` 再 `blob`

导出报告需要 `Authorization` 头，因此**不能**用 `<a href>` 或 `window.open` 直接打开
（那样带不上头，只会拿到 401）。正确做法见 [§9.4](#94-导出报告为-docx) 的示例代码：
`fetch` → 检查 `res.ok` → `res.blob()` → `URL.createObjectURL` → 触发下载 → `revokeObjectURL`。

### 15.7 三处必须由前端主动提示的边界

后端要么不下发、要么静默降级，**界面上不提示就等于功能坏了**：

| # | 场景 | 判断条件 | 应显示 |
|:--:|---|---|---|
| 1 | **刷题按简历推荐降级了** | `resume_id != null && resume_match_applied === false` | 「未按简历推荐，已退回普通筛选」并给重试入口 |
| 2 | **题目未判分** | `is_correct === null`（不是 `false`） | 「未判分」+「重新判分」按钮，**不要渲染成答错** |
| 3 | **练习答案按题解锁** | `items[].explanation` 与 `reference_answer` 在该题**未提交时恒为 `null`**（不是渲染问题，是没下发） | 未提交的题不显示参考答案区，而不是显示空白 |

> 第 3 条容易被误当成「后端漏了字段」。它是有意的：答案只在提交后下发，防止一次性把全套答案拉走。

---

## 十六、附录

### 16.1 评审要点（实现侧）

| 项 | 结论 |
|---|---|
| 评分制式 | 统一 **0–10 分**，全部保留 1 位小数；数据库用 `DECIMAL(3,1)`（定点，避免浮点误差累积到总分） |
| 总分算法 | 各维度分的算术平均（Mock Provider 规则） |
| 维度缺失 | Provider 少返回维度时**按实际写入，不补齐、不伪造**；雷达图按实际维度数渲染 |
| 重新评估 | **替换语义** —— 逐题评分与维度评分先清后写，条数不翻倍；报告 upsert 并更新 `updated_at` |
| 失败隔离 | 先推后写：结果在最后一次性落库；失败时数据库要么是上一次的完整结果，要么是这一次的完整结果 |
| AI 调用 | 真实 Provider 失败时**不自动降级到 Mock**，而是报 502 并允许重试 |
| SSE 竞态 | 重放窗口的竞态已修复（`stream_events` 订阅与快照同临界区），保证 `done`/`error` 不会静默丢失 |

### 16.2 文档维护

| 项 | 说明 |
|---|---|
| 契约事实来源 | 各模块 `app/*/schemas.py`（请求 / 响应模型）与 `app/*/router.py`（端点声明） |
| 字段与类型 | `GET /openapi.json` —— 本文档的字段表与它逐项对应 |
| 行为验证来源 | MVP-1 的 26 个 route 有 HTTP 层用例验证（[2026-09-17 测试报告](../tests/2026-09-17-API接口测试报告.md)，461 条）；**MVP-2 / MVP-3 的 33 个 route 尚无专门的接口层报告** |
| 文档覆盖 | **59 个 method-route / 43 条路径**（与 `openapi.json` 的路径数一致） |
| 变更时同步 | 改 `schemas.py` 或路由后，需同步更新本文档；新增 / 删除端点时表 [§三](#三接口总览) 的行数要与 `openapi.json` 对齐 |

**校验覆盖是否完整**（两条命令，数字应一致）：

```bash
cd backend
# 1) 本文档「接口总览」表的行数
grep -c '^| [0-9]' ../docs/apis/API接口文档.md

# 2) 实际注册的 method-route 数
python -c "from app.main import app; \
  print(sum(len(v) for v in app.openapi()['paths'].values()))"
```

### 16.3 已知偏差与例外（集中索引）

| # | 项 | 位置 |
|:--:|---|---|
| 1 | 简历正文超长保留 **422**（全项目唯一的 422） | [§11.1](#111-新建简历) |
| 2 | 邀请码激活要求调用者**已是登录中的候选人** | [§10.2 偏差 1](#102-接受邀请码) |
| 3 | `accept` 的绑定账号取自请求体，且对已存在的 candidate **不校验密码** | [§10.2 偏差 2](#102-接受邀请码) |
| 4 | 刷题取题**不按 `created_by` 过滤题库**（有意的隔离放宽） | [§2.5](#25-数据隔离规则) |
| 5 | 撤销邀请返回 **200 带体**，而其他 `DELETE` 是 204 | [§8.11](#811-撤销邀请) |
| 6 | 导出 DOCX **不含雷达图**（需要图形走前端打印 PDF） | [§9.4](#94-导出报告为-docx) |
