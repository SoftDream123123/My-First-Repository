# core 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：core（基础设施 / 横切关注点）
**所属包**：`backend/app/core/`（app 装配入口为 `backend/app/main.py`）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp.md](../plans/2026-09-15-ai-interview-assistant-mvp.md)
**设计规格**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 任务**：Task 0

---

## Global Constraints（全局约束）

- 后端严格分层：`router → service → repository → MySQL`，只允许自上而下依赖，不跨层调用、不反向依赖。
- 每个模块独立 Python package（`backend/app/<module>/`）。
- AI 通过抽象接口接入，真实 Provider 与 Mock Provider 可配置切换，代码不写死。
- 评分统一 0–10 分制（逐题、维度、总分）。
- 出题同步、评估流式（SSE）。
- 数据隔离：普通 HR 仅见自己创建的数据，admin 见全部。
- 仅 PC 端，不做移动端响应式。
- 统一错误响应格式 `{code, message, detail}`。
- 密码哈希存储（bcrypt），JWT 鉴权。

---

## 1. 模块职责与边界

### 1.1 职责

core 是**横切基础设施**，不属于任何业务域。它提供其他所有模块都要用的原语：

| 子职责 | 内容 |
|---|---|
| 配置管理 | 从环境变量 / `.env` 读取全部可配置项，集中暴露 |
| 数据库会话 | SQLAlchemy engine、Session 工厂、声明式 Base |
| 安全原语 | 密码哈希与校验、JWT 签发与解码 |
| 异常体系 | 统一业务异常层级 + 统一错误响应格式 |
| 依赖注入 | 请求级 DB 会话、当前用户解析、角色校验依赖 |
| 应用装配 | FastAPI 实例、CORS、全局异常处理器、健康检查 |

### 1.2 边界（明确不做）

- **不包含任何业务表**：core 不定义业务实体，`Base` 只提供声明式基类。
- **不包含业务逻辑**：登录、出题、评估等一律在各自业务模块的 service 中。
- **不反向依赖业务模块**：core 不得 import `auth` / `position` / `question` / `ai` / `interview` / `evaluation`。
- **不做数据隔离的实现**：core 只提供「当前用户」这一事实，具体按 `created_by` 过滤由各业务模块的 repository 负责。

### 1.3 依赖方向

```
所有业务模块 ──→ core（单向，core 不反向依赖任何业务模块）
core ──→ SQLAlchemy / PyJWT / bcrypt / pydantic-settings / FastAPI
```

> **唯一例外说明**：`deps.get_current_user` 需要查询 User 表。为保持 core 不依赖 `auth`，该依赖通过**延迟导入**（在函数体内 import `auth.models.User`）实现，或在 `auth` 模块中提供一个 `get_current_user` 覆盖版本。**本设计采用延迟导入方案**，理由：避免循环依赖，且 `get_current_user` 语义上属于横切关注点。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/core/config.py` | 全部配置项的定义与加载 |
| `backend/app/core/db.py` | engine、SessionLocal、Base、会话生命周期 |
| `backend/app/core/security.py` | 密码哈希 / 校验、JWT 签发 / 解码 |
| `backend/app/core/exceptions.py` | 异常层级与错误码常量 |
| `backend/app/core/deps.py` | FastAPI 依赖：DB 会话、当前用户、角色校验 |
| `backend/app/main.py` | FastAPI 装配：实例、CORS、异常处理器、路由注册、健康检查 |
| `backend/requirements.txt` | 依赖清单 |
| `backend/.env.example` | 配置样例（不含真实密钥） |
| `backend/alembic.ini` | Alembic 配置 |
| `backend/alembic/env.py` | 迁移环境（读取 config，导入全部模型以生成迁移） |

**测试文件**：`backend/tests/conftest.py`（夹具）、`backend/tests/test_health.py`（冒烟）

---

## 3. 配置项设计（config.py）

`Settings` 采用 pydantic-settings，来源优先级：环境变量 > `.env` 文件 > 默认值。

| 配置键 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `DATABASE_URL` | str | 是 | — | MySQL 连接串，形如 `mysql+pymysql://user:pwd@host:3306/db` |
| `JWT_SECRET` | str | 是 | — | JWT 签名密钥，生产环境必须为强随机值 |
| `JWT_ALGORITHM` | str | 否 | `HS256` | 签名算法 |
| `JWT_EXPIRE_MINUTES` | int | 否 | `720`（12 小时） | Token 有效期 |
| `PROVIDER_NAME` | str | 否 | `mock` | AI Provider 选择：`mock` \| `openai` |
| `OPENAI_API_KEY` | str \| None | 否 | `None` | 真实 Provider 所需；`mock` 模式下可为空 |
| `OPENAI_BASE_URL` | str \| None | 否 | `None` | 真实 Provider 的 API 地址 |
| `OPENAI_MODEL` | str \| None | 否 | `None` | 模型名 |
| `QUESTION_COUNT_FROM_BANK` | int | 否 | `5` | 出题时从题库抽取的题数 N |
| `QUESTION_COUNT_FROM_AI` | int | 否 | `3` | 出题时由 AI 补充的题数 M |
| `AI_TIMEOUT_SECONDS` | int | 否 | `30` | AI 调用超时 |
| `AI_MAX_RETRIES` | int | 否 | `1` | AI 调用失败重试次数（PRD 规定重试 1 次） |
| `CORS_ORIGINS` | list[str] | 否 | `["http://localhost:5173"]` | 允许的前端来源（Vite 默认端口） |
| `SQL_ECHO` | bool | 否 | `false` | 是否打印 SQL（调试用） |

**设计约定**：

- 配置通过**单例访问函数** `get_settings()` 获取，内部缓存，便于测试时覆盖。
- 启动时**校验必填项**：缺失必填项应给出明确报错，而非运行到一半才失败。
- `.env.example` 必须包含全部键，值用占位符，**不得包含真实密钥**。

---

## 4. 数据访问基础设计（db.py）

| 导出 | 类型 | 说明 |
|---|---|---|
| `engine` | SQLAlchemy `Engine` | 由 `DATABASE_URL` 创建；连接池参数按默认；`SQL_ECHO` 控制回显 |
| `SessionLocal` | `sessionmaker[Session]` | `autocommit=False`、`autoflush=False`、`expire_on_commit=False` |
| `Base` | `DeclarativeBase` 子类 | 所有业务模型继承；**不定义任何业务字段** |
| `get_db` | 生成器函数 | 请求级会话：yield Session，请求结束在 finally 中 close；异常时 rollback |

**设计要点**：

- **事务边界在 service 层**：repository 只做单次数据操作，commit / rollback 由 service 显式控制，便于「出题组装」「评估落库」这类跨多表的原子操作。
- **`expire_on_commit=False`**：避免 commit 后访问对象属性触发额外查询或 DetachedInstanceError。
- **模型注册**：`alembic/env.py` 必须 import 全部业务模型，否则自动生成迁移会漏表。

---

## 5. 安全原语设计（security.py）

### 5.1 接口契约

| 函数签名 | 返回 | 失败行为 |
|---|---|---|
| `hash_password(raw: str) -> str` | bcrypt 哈希串 | 不失败 |
| `verify_password(raw: str, hashed: str) -> bool` | 是否匹配 | 哈希格式非法时返回 `False`（不抛异常） |
| `create_access_token(user_id: int) -> str` | 编码后的 JWT | 不失败 |
| `decode_token(token: str) -> int` | 解出的 `user_id` | 过期 / 签名错误 / 格式错误 → 抛 `InvalidTokenError`（401） |

### 5.2 JWT 载荷设计

| Claim | 值 |
|---|---|
| `sub` | `str(user_id)`（JWT 规范要求 sub 为字符串） |
| `iat` | 签发时间（UTC） |
| `exp` | `iat + JWT_EXPIRE_MINUTES` |

**设计要点**：

- 载荷中**不放角色**。角色每次请求从数据库读取，保证「管理员改角色 / 禁用账号」立即生效，不必等 token 过期。
- `decode_token` **不做数据库查询**，保持纯函数，便于单测。

---

## 6. 异常体系设计（exceptions.py）

### 6.1 异常层级

| 异常类 | 基类 | 默认 HTTP 状态 | 默认 code |
|---|---|---|---|
| `AppError` | `Exception` | 400 | `APP_ERROR` |
| `NotFoundError` | `AppError` | 404 | `NOT_FOUND` |
| `ForbiddenError` | `AppError` | 403 | `FORBIDDEN` |
| `UnauthorizedError` | `AppError` | 401 | `UNAUTHORIZED` |
| `BusinessError` | `AppError` | 409 | `BUSINESS_ERROR` |
| `InvalidTokenError` | `UnauthorizedError` | 401 | `INVALID_TOKEN` |
| `AIProviderError` | `AppError` | 502 | `AI_PROVIDER_ERROR` |
| `ValidationError` | `AppError` | 400 | `VALIDATION_ERROR` |

### 6.2 统一错误响应格式

所有错误响应体固定为三字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | str | 机器可读的错误码（上表 code 列） |
| `message` | str | 面向用户的简短说明 |
| `detail` | object \| null | 附加信息（如字段级校验错误、非法状态迁移的 from/to） |

### 6.3 错误码总表（core 定义，全模块引用）

| code | HTTP | 触发场景 |
|---|---|---|
| `UNAUTHORIZED` | 401 | 未携带 token |
| `INVALID_TOKEN` | 401 | token 过期 / 签名错误 |
| `FORBIDDEN` | 403 | 角色不足、访问他人数据 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `VALIDATION_ERROR` | 400 | 请求参数非法 |
| `BUSINESS_ERROR` | 409 | 业务规则冲突（如非法状态迁移、被引用不可删） |
| `AI_PROVIDER_ERROR` | 502 | AI 调用失败（重试后仍失败） |
| `INTERNAL_ERROR` | 500 | 未预期异常兜底 |

### 6.4 全局异常处理器（在 main.py 注册）

| 处理器 | 触发 | 行为 |
|---|---|---|
| `AppError` 处理器 | 业务异常 | 按异常自带 code / status 输出三字段 |
| `RequestValidationError` 处理器 | 请求体 / 查询参数校验失败（FastAPI 422） | 转成 400 + `VALIDATION_ERROR`，`detail` 携带字段级错误列表 |
| `Exception` 兜底处理器 | 未预期异常 | 记日志（含堆栈），对外只返回 500 + `INTERNAL_ERROR`，**不泄漏堆栈** |

---

## 7. 依赖注入设计（deps.py）

| 依赖 | 签名 | 行为 |
|---|---|---|
| `get_db` | `() -> Generator[Session]` | 从 db.py 透传（或直接复用） |
| `get_token` | `(authorization: str = Header(...)) -> str` | 解析 `Authorization: Bearer <token>`；缺失 → `UnauthorizedError` |
| `get_current_user` | `(db: Session, token: str) -> User` | `decode_token` → 查 User → 校验启用状态 → 返回 User；用户不存在 / 已禁用 → `UnauthorizedError` |
| `require_role` | `(role: str) -> Callable[[User], User]` | 依赖工厂：返回的依赖校验 `user.role == role`，否则 `ForbiddenError` |

**设计要点**：

- `get_current_user` 的返回对象是各业务模块做数据隔离的**唯一依据**（通过 `user.id` / `user.role`）。
- `require_role` 用**工厂模式**，便于在 router 上以 `Depends(require_role("admin"))` 声明式使用。
- `get_current_user` 内部对 `auth.models.User` 采用**延迟导入**（见 §1.3）。

---

## 8. 应用装配设计（main.py）

| 装配项 | 设计 |
|---|---|
| FastAPI 实例 | `app = FastAPI(title="AI 智能面试助手 API")` |
| CORS | 来自 `CORS_ORIGINS`；允许 `Authorization` 头；允许必要方法 |
| 异常处理器 | 注册 §6.4 的三个处理器 |
| 路由注册 | 依次注册各模块 router，统一前缀 `/api` |
| 健康检查 | `GET /api/health` → 200 `{"status": "ok"}`，**无需鉴权** |

**路由注册顺序**（体现模块依赖）：

```
auth → position → question → interview → evaluation
```

`ai` 模块**不注册 router**（它是服务端内部能力，无对外 HTTP 端点）。

---

## 9. 测试设计

### 9.1 夹具设计（conftest.py）

| 夹具 | 作用域 | 说明 |
|---|---|---|
| `engine` | session | 测试库 engine（推荐 SQLite 内存库；若用 MySQL 则为独立测试库） |
| `db` | function | 每个测试一个事务级会话，测试后回滚，保证隔离 |
| `client` | function | `TestClient(app)`，依赖覆盖 `get_db` 指向测试会话 |
| `admin_user` | function | seed 一个 admin 角色用户 |
| `hr_user` | function | seed 一个 hr 角色用户 |
| `admin_headers` / `hr_headers` | function | 便捷夹具，返回带 `Authorization` 头的 dict |

> **依赖覆盖**：`client` 夹具必须通过 `app.dependency_overrides[get_db]` 注入测试会话，否则测试会打真实库。

### 9.2 测试点

| 测试 | 断言 |
|---|---|
| `test_health_ok` | `GET /api/health` 返回 200 且 body 为 `{"status": "ok"}` |
| `test_health_no_auth_required` | 不带 token 也能 200 |
| `test_hash_and_verify_password` | 同一明文哈希两次结果不同（含盐）；`verify` 对正确明文为真、错误明文为假 |
| `test_verify_password_bad_hash` | 传入非法哈希串返回 `False` 而非抛异常 |
| `test_create_and_decode_token` | 签发后解码得回同一 `user_id` |
| `test_decode_expired_token` | 构造过期 token → 抛 `InvalidTokenError` |
| `test_decode_tampered_token` | 篡改签名 → 抛 `InvalidTokenError` |
| `test_validation_error_shape` | 发一个非法请求体 → 400 且响应体为 `{code, message, detail}` 三字段 |
| `test_unhandled_exception_shape` | 触发未预期异常 → 500 + `INTERNAL_ERROR`，响应体**不含堆栈** |

---

## 10. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟，遵循「先写失败测试 → 跑到失败 → 最小实现 → 跑到通过 → 提交」。

### Task 0.1：目录结构与依赖清单

- [ ] 建立 `backend/` 目录树（`app/core`、`app/<各业务模块>`、`tests`、`alembic`）
- [ ] 编写 `requirements.txt`：fastapi、uvicorn[standard]、sqlalchemy、pymysql、pydantic、pydantic-settings、pyjwt、bcrypt、httpx、sse-starlette、alembic、pytest
- [ ] 编写 `.env.example`（全部键，占位值）
- [ ] 提交

### Task 0.2：配置（config.py）

- [ ] 写失败测试：缺必填项时应报错；提供了全部项时 `get_settings()` 返回正确类型
- [ ] 运行测试，确认失败
- [ ] 实现 `Settings` 与 `get_settings()` 单例
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.3：数据库基础（db.py）

- [ ] 写失败测试：`get_db()` 可 yield 一个 Session 且退出时关闭
- [ ] 运行测试，确认失败
- [ ] 实现 `engine` / `SessionLocal` / `Base` / `get_db`
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.4：安全原语（security.py）

- [ ] 写 §9.2 中 4 个密码 / token 相关失败测试
- [ ] 运行测试，确认失败
- [ ] 实现四个函数
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.5：异常体系（exceptions.py）

- [ ] 写失败测试：各异常类默认 code / status 正确
- [ ] 运行测试，确认失败
- [ ] 实现异常层级与错误码常量
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.6：应用装配与健康检查（main.py）

- [ ] 写失败测试：`GET /api/health` 返回 200 且无需鉴权
- [ ] 运行测试，确认失败
- [ ] 实现 FastAPI 实例、CORS、三个异常处理器、健康检查
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.7：依赖注入（deps.py）

> 依赖 `auth.models.User` 存在。若 auth 模块尚未实现，本任务可与 auth 模块的「模型定义」子步骤合并执行。**本计划将 deps 拆为两部分**：`get_db` / `get_token` 在此完成；`get_current_user` / `require_role` 在 auth 模块 Task 1.4 中补齐（此时 User 模型已存在）。

- [ ] 写失败测试：缺失 `Authorization` 头 → 401 `UNAUTHORIZED`
- [ ] 运行测试，确认失败
- [ ] 实现 `get_db`、`get_token`
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.8：测试夹具（conftest.py）

- [ ] 建立 `engine` / `db` / `client` 夹具与依赖覆盖
- [ ] 建立 `admin_user` / `hr_user` / 对应 headers 夹具
- [ ] 跑通 Task 0.2–0.7 的全部测试
- [ ] 提交

### Task 0.9：Alembic 初始化

- [ ] 配置 `alembic.ini` 与 `alembic/env.py`（读 `DATABASE_URL`；import 全部模型）
- [ ] 生成初始迁移（此阶段无业务表，可生成空迁移验证链路）
- [ ] 验证 `alembic upgrade head` 可执行
- [ ] 提交

---

## 11. 验收标准

- [ ] `GET /api/health` 无需鉴权返回 200 `{"status": "ok"}`
- [ ] 所有错误响应（400/401/403/404/409/500/502）body 均为 `{code, message, detail}` 三字段
- [ ] 500 响应不泄漏堆栈信息
- [ ] `hash_password` 对同一明文产生不同哈希；`verify_password` 对非法哈希返回 `False` 不抛异常
- [ ] `create_access_token` → `decode_token` 往返得到同一 `user_id`
- [ ] 过期 / 篡改 token 抛出 `InvalidTokenError`（401）
- [ ] `alembic upgrade head` 可正常执行
- [ ] core 中不存在对任何业务模块的顶层 import
- [ ] 全部 core 测试通过

---

## 12. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| core 不依赖 auth，但 `get_current_user` 需查 User 表 | 采用函数体内延迟导入 | 避免循环依赖；`get_current_user` 语义上是横切关注点 |
| 测试用 SQLite 还是 MySQL | 默认 SQLite 内存库 | 快、无外部依赖；若用到 MySQL 特有语法（JSON 字段需注意）则切独立测试库 |
| `evaluation_dimensions` / `tags` 用 JSON 列 | 依赖 SQLAlchemy `JSON` 类型 | SQLite 与 MySQL 8 均支持，测试与生产行为一致 |
| JWT 中是否放角色 | 不放，每次查库 | 保证改角色 / 禁用立即生效 |
