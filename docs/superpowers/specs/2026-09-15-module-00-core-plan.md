# core 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：core（基础设施 / 横切关注点）
**所属包**：`backend/app/core/`（应用装配入口为 `backend/app/main.py`）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)

---

## Global Constraints（全局约束，摘自 PRD）

- 架构：**前后端分离**，后端纯 API，不渲染页面（PRD §2）
- 后端：**Python + FastAPI**（PRD §2）
- 数据库：**MySQL**（PRD §2）
- 后端分层：**router → service → repository → MySQL，严格单向依赖**（PRD §2、§3.2）
- 模块组织：**每个模块独立 Python package**（PRD §2、§3.3）
- 统一响应格式：**`{code, message, detail}`**，router 层集中包装（PRD §7）
- 安全：**密码哈希存储（bcrypt/argon2）；JWT 过期与刷新；参数校验防注入**（PRD §9）
- 统一前缀 `/api`，**除登录外均需 JWT**（PRD §8）
- 可测试性：三层可独立测试；AI Provider 可 Mock（PRD §9、§10）
- 可维护性：模块边界清晰，依赖单向（PRD §9）
- 仅 PC 端（PRD §2）

---

## 0. 本模块与 PRD 的对应关系

PRD §3.3 的模块表列出了六个业务/能力包（`auth` / `position` / `question` / `interview` / `evaluation` / `ai`），**未单独列出 `core`**。但 PRD 同时提出了若干**跨模块的强制要求**，它们必须有唯一的落点：

| PRD 要求 | 出处 | 若无 core 则落在哪里 |
|---|---|---|
| 分层 `router → service → repository` 的公共底座 | §2、§3.2 | 每个模块各自重复实现，必然发散 |
| 统一响应格式 `{code, message, detail}` | §7 | 无统一落点，各模块自行编造错误体 |
| 密码哈希（bcrypt/argon2）、JWT | §9 | 与 `auth` 业务逻辑混杂 |
| 数据库连接与声明式 Base | §2 | 无统一落点 |
| 「除登录外均需 JWT」的鉴权依赖 | §8 | 每个模块重复实现鉴权 |
| 参数校验防注入 | §9 | 无统一落点 |

因此本计划将 `core` 作为**第七个 package** 显式建立，定位为**横切基础设施**，不承载任何业务。它不扩大 PRD 的功能范围——六个业务模块的能力清单保持不变，`core` 只是把 PRD 已要求的横切能力集中到一处，以满足「模块边界清晰、依赖单向」（PRD §9）的可维护性目标。

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | 对应 PRD |
|---|---|---|
| 配置管理 | 从环境变量 / `.env` 读取全部可配置项，集中暴露 | §2 |
| 数据库会话 | SQLAlchemy engine、Session 工厂、声明式 Base | §2 |
| 安全原语 | 密码哈希与校验、JWT 签发与解码 | §9 |
| 异常体系 | 统一业务异常层级 + 统一错误响应格式 | §7 |
| 依赖注入 | 请求级 DB 会话、当前用户解析、角色校验 | §8 |
| 应用装配 | FastAPI 实例、CORS、全局异常处理器、健康检查 | §2、§3 |

### 1.2 边界（明确不做）

- **不包含任何业务表**：`Base` 只提供声明式基类，不定义业务实体。
- **不包含业务逻辑**：登录、出题、评估等一律在各自业务模块的 service 中。
- **不反向依赖业务模块**：core 不得 import `auth` / `position` / `question` / `ai` / `interview` / `evaluation`。
- **不实现数据隔离的过滤逻辑**：core 只提供「当前用户」这一事实；具体按 `created_by` 过滤由各业务模块的 repository 负责（PRD §4.1 的数据隔离要求）。
- **不做审计日志、限流、监控**：不在 PRD 范围。

### 1.3 依赖方向

```
所有业务模块 ──→ core（单向）
core ──→ SQLAlchemy / PyJWT / bcrypt / pydantic-settings / FastAPI
core ✗→ 任何业务模块
```

**唯一例外的处理**：`deps.get_current_user` 需要查询 User 表。为保持 core 不依赖 `auth`，该依赖通过**函数体内延迟导入**（`auth.models.User`）实现。

| 方案 | 评价 |
|---|---|
| core 顶层 import `auth.models` | 形成 `core ↔ auth` 循环依赖，破坏 PRD §9 的「依赖单向」 |
| 把 `get_current_user` 放进 `auth` 模块 | 可行，但会使每个业务模块都要依赖 `auth.deps` 而非统一的 `core.deps`，鉴权落点不唯一 |
| **函数体内延迟导入（本设计采用）** | 保住依赖单向，同时让鉴权依赖有唯一落点 |

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/core/__init__.py` | 包标识 |
| `backend/app/core/config.py` | 全部配置项的定义与加载 |
| `backend/app/core/db.py` | engine、SessionLocal、Base、会话生命周期 |
| `backend/app/core/security.py` | 密码哈希 / 校验、JWT 签发 / 解码 |
| `backend/app/core/exceptions.py` | 异常层级与错误码常量 |
| `backend/app/core/deps.py` | FastAPI 依赖：DB 会话、当前用户、角色校验 |
| `backend/app/main.py` | FastAPI 装配：实例、CORS、异常处理器、路由注册、健康检查 |
| `backend/requirements.txt` | 依赖清单 |
| `backend/.env.example` | 配置样例（**不含真实密钥**） |
| `backend/alembic.ini` | Alembic 配置 |
| `backend/alembic/env.py` | 迁移环境（读配置、导入全部模型） |

**测试文件**：`backend/tests/conftest.py`、`backend/tests/test_health.py`、`backend/tests/test_security.py`、`backend/tests/test_exceptions.py`

---

## 3. 配置项设计（`config.py`）

采用 pydantic-settings，来源优先级：**环境变量 > `.env` 文件 > 默认值**。

| 配置键 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `DATABASE_URL` | str | **是** | — | MySQL 连接串，形如 `mysql+pymysql://user:pwd@host:3306/db` |
| `JWT_SECRET` | str | **是** | — | 签名密钥，生产环境必须为强随机值 |
| `JWT_ALGORITHM` | str | 否 | `HS256` | 签名算法 |
| `JWT_EXPIRE_MINUTES` | int | 否 | `720`（12 小时） | Token 有效期 |
| `PROVIDER_NAME` | str | 否 | `mock` | AI Provider：`mock` \| `openai`（PRD §6） |
| `OPENAI_API_KEY` | str \| None | 否 | `None` | 真实 Provider 所需；`mock` 模式可为空 |
| `OPENAI_BASE_URL` | str \| None | 否 | `None` | 真实 Provider 的 API 地址 |
| `OPENAI_MODEL` | str \| None | 否 | `None` | 模型名 |
| `QUESTION_COUNT_FROM_BANK` | int | 否 | `5` | 出题时从题库抽取的题数 **N**（PRD §4.4） |
| `QUESTION_COUNT_FROM_AI` | int | 否 | `3` | 出题时由 AI 补充的题数 **M**（PRD §4.4） |
| `AI_TIMEOUT_SECONDS` | int | 否 | `30` | AI 调用超时 |
| `AI_MAX_RETRIES` | int | 否 | `1` | AI 失败重试次数（PRD §7：重试 1 次） |
| `CORS_ORIGINS` | list[str] | 否 | `["http://localhost:5173"]` | 允许的前端来源（Vite 开发端口） |
| `SQL_ECHO` | bool | 否 | `false` | 是否打印 SQL |
| `BCRYPT_ROUNDS` | int | 否 | `12` | bcrypt 代价因子 |
| `ADMIN_USERNAME` | str | 否 | `admin` | seed 初始管理员用（PRD §4.1） |
| `ADMIN_PASSWORD` | str | 否 | `admin12345` | seed 初始管理员用；**生产必须覆盖** |

**设计约定**

- 通过单例访问函数 `get_settings()` 获取，内部缓存，便于测试覆盖。
- **启动时校验必填项**：缺失则给出明确报错并终止启动（fail fast），而非运行到一半才失败。
- `.env.example` 必须包含全部键，值用占位符，**不得包含真实密钥**。
- `JWT_SECRET` 若为默认占位值，启动时应打印显著警告。

---

## 4. 数据访问基础设计（`db.py`）

| 导出 | 类型 | 说明 |
|---|---|---|
| `engine` | SQLAlchemy `Engine` | 由 `DATABASE_URL` 创建；`SQL_ECHO` 控制回显 |
| `SessionLocal` | `sessionmaker[Session]` | `autocommit=False`、`autoflush=False`、`expire_on_commit=False` |
| `Base` | `DeclarativeBase` 子类 | 所有业务模型继承；**不定义任何业务字段** |
| `get_db` | 生成器函数 | 请求级会话：yield Session，`finally` 中 close；异常时 rollback |

**设计要点**

| 要点 | 理由 |
|---|---|
| **事务边界在 service 层** | repository 只做单次数据操作，commit / rollback 由 service 显式控制。PRD §5.3 的「出题组装」与 §5.3 的「评估落库」都是跨多表的原子操作，必须有统一的事务所有者 |
| `expire_on_commit=False` | 避免 commit 后访问对象属性触发额外查询或 `DetachedInstanceError` |
| **`alembic/env.py` 必须 import 全部业务模型** | 否则自动生成迁移会漏表。这是 Alembic 最常见的踩坑点 |
| 字符集 `utf8mb4` | 中文题干、候选人姓名、JD 均需完整 Unicode 支持 |

---

## 5. 安全原语设计（`security.py`）

### 5.1 接口契约

| 函数签名 | 返回 | 失败行为 |
|---|---|---|
| `hash_password(raw: str) -> str` | bcrypt 哈希串 | 不失败 |
| `verify_password(raw: str, hashed: str) -> bool` | 是否匹配 | 哈希格式非法时返回 `False`（**不抛异常**） |
| `create_access_token(user_id: int) -> str` | 编码后的 JWT | 不失败 |
| `decode_token(token: str) -> int` | 解出的 `user_id` | 过期 / 签名错误 / 格式错误 → 抛 `InvalidTokenError`（401） |

### 5.2 JWT 载荷设计

| Claim | 值 | 说明 |
|---|---|---|
| `sub` | `str(user_id)` | JWT 规范要求 `sub` 为字符串 |
| `iat` | 签发时间（UTC） | — |
| `exp` | `iat + JWT_EXPIRE_MINUTES` | PRD §9 要求的「JWT 过期」 |

**设计要点**

- **载荷中不放角色**。角色每次请求从数据库读取，保证「管理员改角色 / 禁用账号」**立即生效**，不必等 token 过期。代价是每请求一次主键查询。
- `decode_token` **不做数据库查询**，保持纯函数，便于单测。

### 5.3 ⚠️ 关于 PRD §9「JWT 过期与刷新」的处理方案（**需你确认**）

PRD §9 原文为「**JWT 过期与刷新**」。「刷新」有两种实现路径，成本差异显著：

| 方案 | 实现内容 | 成本 | 评价 |
|---|---|---|---|
| **A. 过期后重新登录（本设计默认采用）** | 仅实现 `exp` 过期校验；前端收到 401 时跳登录页 | 极低 | 把「刷新」理解为「过期后重新获取 token」。内网 HR 系统 12 小时有效期下，每天登录一次即可 |
| B. 滑动续期 | 每次请求若 token 剩余有效期低于阈值，在响应头返回新 token，前端替换 | 低 | 体验接近永不过期；但 401 处理逻辑要多一条分支 |
| C. Refresh Token | 签发 access + refresh 两枚 token；refresh 用于换取新 access，需存储、轮换与吊销 | 中高 | 适合公网多端场景；MVP 引入会牵出 token 存储表与吊销机制 |

**本设计默认采用 A**，并在验收标准中标注。若你要求 B 或 C，请在评审本文件时指出——**A 改为 B 是 core 模块内的小改动（约 1 个函数 + 前端 1 处处理）；A 改为 C 会新增一张表与一组端点，属于范围扩大**。

---

## 6. 异常体系设计（`exceptions.py`）

### 6.1 异常层级

| 异常类 | 基类 | 默认 HTTP | 默认 code |
|---|---|---|---|
| `AppError` | `Exception` | 400 | `APP_ERROR` |
| `ValidationError` | `AppError` | 400 | `VALIDATION_ERROR` |
| `UnauthorizedError` | `AppError` | 401 | `UNAUTHORIZED` |
| `InvalidTokenError` | `UnauthorizedError` | 401 | `INVALID_TOKEN` |
| `ForbiddenError` | `AppError` | 403 | `FORBIDDEN` |
| `NotFoundError` | `AppError` | 404 | `NOT_FOUND` |
| `BusinessError` | `AppError` | 409 | `BUSINESS_ERROR` |
| `AIProviderError` | `AppError` | 502 | `AI_PROVIDER_ERROR` |
| `InternalError` | `AppError` | 500 | `INTERNAL_ERROR` |

### 6.2 统一错误响应格式（**PRD §7 的强制要求**）

所有错误响应体固定为三字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | str | 机器可读的错误码（上表 code 列） |
| `message` | str | 面向用户的简短说明（**中文**，可直接展示给用户） |
| `detail` | object \| null | 附加信息（字段级校验错误、非法状态迁移的 from/to 等） |

### 6.3 错误码总表（**core 定义，全模块引用**）

| code | HTTP | 触发场景 | 对应 PRD |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | 未携带 token / 凭据错误 | §7 |
| `INVALID_TOKEN` | 401 | token 过期 / 签名错误 | §9 |
| `FORBIDDEN` | 403 | 角色不足、访问他人数据 | §4.1、§7 |
| `NOT_FOUND` | 404 | 资源不存在 | §7 |
| `VALIDATION_ERROR` | 400 | 请求参数非法（**PRD §7 的 422/400 统一收口为 400**） | §7 |
| `BUSINESS_ERROR` | 409 | 业务规则冲突（非法状态迁移、被引用不可删） | §7 |
| `AI_PROVIDER_ERROR` | 502 | AI 调用失败（重试后仍失败） | §7 |
| `INTERNAL_ERROR` | 500 | 未预期异常兜底 | §7 |

> **关于 PRD §7 的「422/400」**：FastAPI 对请求体校验失败默认返回 422。本设计在全局处理器中把 `RequestValidationError` **统一转换为 400 `VALIDATION_ERROR`**，使全项目错误码收敛为一张表。这是对 PRD「参数校验（422/400）」二选一收口的实现。

### 6.4 全局异常处理器（在 `main.py` 注册）

| 处理器 | 触发 | 行为 |
|---|---|---|
| `AppError` 处理器 | 业务异常 | 按异常自带的 code / status 输出三字段 |
| `RequestValidationError` 处理器 | FastAPI 参数校验失败（默认 422） | 转为 **400 + `VALIDATION_ERROR`**，`detail` 携带字段级错误列表 |
| `Exception` 兜底处理器 | 未预期异常 | 记日志（含堆栈），对外只返回 **500 + `INTERNAL_ERROR`**，**不泄漏堆栈** |

---

## 7. 依赖注入设计（`deps.py`）

| 依赖 | 签名 | 行为 |
|---|---|---|
| `get_db` | `() -> Generator[Session]` | 复用 `db.py` 的实现 |
| `get_token` | `(authorization: str = Header(...)) -> str` | 解析 `Authorization: Bearer <token>`；缺失或格式错误 → `UnauthorizedError` |
| `get_current_user` | `(db: Session, token: str) -> User` | `decode_token` → 查 User → 校验启用状态 → 返回 User |
| `require_role` | `(role: str) -> Callable[[User], User]` | 依赖工厂：校验 `user.role == role`，否则 `ForbiddenError` |

**设计要点**

- `get_current_user` 返回的对象是各业务模块做数据隔离的**唯一依据**（PRD §4.1：HR 仅见自己的数据）。各模块用 `user.id` 过滤 `created_by`，用 `user.role` 判断是否 admin。
- `require_role` 用**工厂模式**，便于在 router 上以 `Depends(require_role("admin"))` 声明式使用（PRD §8 中 `/users` 仅 admin 可访问）。
- `get_current_user` 内部对 `auth.models.User` 采用**延迟导入**（理由见 §1.3）。

---

## 8. 应用装配设计（`main.py`）

| 装配项 | 设计 | 依据 |
|---|---|---|
| FastAPI 实例 | `app = FastAPI(title="AI 智能面试助手 API")` | §2 |
| CORS | 来自 `CORS_ORIGINS`；允许 `Authorization` 头 | §3.1（前后端分离） |
| 异常处理器 | 注册 §6.4 的三个处理器 | §7 |
| 路由注册 | 依次注册各业务模块 router，**统一前缀 `/api`** | §8 |
| 健康检查 | `GET /api/health` → 200 `{"status": "ok"}`，**无需鉴权** | 部署探活所需 |

**路由注册顺序**（按 PRD §3.3 的依赖方向）：

```
auth → position → question → interview → evaluation
```

`ai` 模块**不注册 router**——PRD §6 将其定位为被 `interview` / `evaluation` 调用的能力包，无对外 HTTP 端点。

---

## 9. 测试设计

### 9.1 夹具设计（`conftest.py`）

| 夹具 | 作用域 | 说明 |
|---|---|---|
| `engine` | session | 测试库 engine |
| `db` | function | 每个测试一个会话，测试后回滚，保证隔离 |
| `client` | function | `TestClient(app)`，**依赖覆盖 `get_db` 指向测试会话** |
| `admin_user` | function | seed 一个 admin 角色用户 |
| `hr_user` | function | seed 一个 hr 角色用户 |
| `admin_headers` / `hr_headers` | function | 便捷夹具，返回带 `Authorization` 头的 dict |

> **依赖覆盖是硬性要求**：`client` 夹具必须通过 `app.dependency_overrides[get_db]` 注入测试会话，否则测试会打真实库（PRD §10 要求 repository 连测试库测 CRUD）。

**测试库选型**：优先 **MySQL 测试库**，与生产同构——PRD §2 指定 MySQL，而 `evaluation_dimensions` / `tags` / `strengths` 等字段使用 JSON 列，SQLite 与 MySQL 的 JSON 行为存在差异。若本地无 MySQL，可用 SQLite 内存库快速跑通大部分用例，但 **JSON 列相关用例必须在 MySQL 下验证**。

### 9.2 测试点

| 测试 | 断言 | 依据 |
|---|---|---|
| `test_health_ok` | `GET /api/health` → 200 且 body 为 `{"status": "ok"}` | §2 |
| `test_health_no_auth_required` | 不带 token 也能 200 | §8（仅登录公开） |
| `test_hash_and_verify_password` | 同一明文哈希两次结果**不同**（含盐）；`verify` 对正确明文为真、错误明文为假 | §9 |
| `test_hash_not_plaintext` | 哈希串 ≠ 明文 | §9 |
| `test_verify_password_bad_hash` | 传入非法哈希串返回 `False` 而非抛异常 | §9 |
| `test_create_and_decode_token` | 签发后解码得回同一 `user_id` | §9 |
| `test_decode_expired_token` | 构造过期 token → 抛 `InvalidTokenError` | §9 |
| `test_decode_tampered_token` | 篡改签名 → 抛 `InvalidTokenError` | §9 |
| `test_validation_error_shape` | 发一个非法请求体 → **400** 且响应体为 `{code, message, detail}` 三字段 | §7 |
| `test_validation_error_detail_has_fields` | `detail` 含字段级错误列表 | §7 |
| `test_unhandled_exception_shape` | 触发未预期异常 → 500 + `INTERNAL_ERROR`，响应体**不含堆栈** | §7 |
| `test_all_error_codes_have_chinese_message` | 各异常类的默认 `message` 为可直接展示的中文 | §7 |

---

## 10. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟，遵循「先写失败测试 → 跑到失败 → 最小实现 → 跑到通过 → 提交」。**提交信息由你指定**。

### Task 0.1：目录结构与依赖清单

- [ ] 建立 `backend/` 目录树（`app/core`、`app/<各业务模块>`、`tests`、`alembic`）
- [ ] 编写 `requirements.txt`：fastapi、uvicorn[standard]、sqlalchemy、pymysql、pydantic、pydantic-settings、pyjwt、bcrypt、httpx、sse-starlette、alembic、pytest
- [ ] 编写 `.env.example`（§3 全部键，占位值）
- [ ] 提交

### Task 0.2：配置（`config.py`）

- [ ] 写失败测试：缺必填项（`DATABASE_URL` / `JWT_SECRET`）时应报错；提供全部项时 `get_settings()` 返回正确类型
- [ ] 运行测试，确认失败
- [ ] 实现 `Settings` 与 `get_settings()` 单例（含 fail fast 校验）
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.3：数据库基础（`db.py`）

- [ ] 写失败测试：`get_db()` 可 yield 一个 Session 且退出时关闭
- [ ] 运行测试，确认失败
- [ ] 实现 `engine` / `SessionLocal` / `Base` / `get_db`
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.4：安全原语（`security.py`）

- [ ] 写 §9.2 中 5 个密码 / token 相关失败测试
- [ ] 运行测试，确认失败
- [ ] 实现 `hash_password` / `verify_password` / `create_access_token` / `decode_token`
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.5：异常体系（`exceptions.py`）

- [ ] 写失败测试：各异常类的默认 code / status / message 正确；`InvalidTokenError` 继承自 `UnauthorizedError`
- [ ] 运行测试，确认失败
- [ ] 实现 §6.1 的异常层级与 §6.3 的错误码常量
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.6：应用装配与健康检查（`main.py`）

- [ ] 写失败测试：`GET /api/health` 返回 200 且无需鉴权
- [ ] 运行测试，确认失败
- [ ] 实现 FastAPI 实例、CORS、§6.4 三个异常处理器、健康检查
- [ ] 运行测试，确认通过（含 `test_validation_error_shape`、`test_unhandled_exception_shape`）
- [ ] 提交

### Task 0.7：依赖注入（`deps.py`，前半）

> `get_current_user` / `require_role` 依赖 `auth.models.User` 存在，故拆到 auth 模块的 Task 1.4 补齐。本节只做不依赖 User 的部分。

- [ ] 写失败测试：缺失 `Authorization` 头 → 401 `UNAUTHORIZED`；非 `Bearer` 前缀 → 401
- [ ] 运行测试，确认失败
- [ ] 实现 `get_db` 透传与 `get_token`
- [ ] 运行测试，确认通过
- [ ] 提交

### Task 0.8：测试夹具（`conftest.py`）

- [ ] 建立 `engine` / `db` / `client` 夹具与 **`get_db` 依赖覆盖**
- [ ] 建立 `admin_user` / `hr_user` / `admin_headers` / `hr_headers` 夹具
- [ ] 跑通 Task 0.2–0.7 的全部测试
- [ ] 提交

> `admin_user` / `hr_user` 夹具依赖 `auth.models.User`，可与 Task 1.1 合并执行。

### Task 0.9：Alembic 初始化

- [ ] 配置 `alembic.ini` 与 `alembic/env.py`（读 `DATABASE_URL`；**import 全部模型**）
- [ ] 生成初始迁移（此阶段无业务表，生成空迁移以验证链路）
- [ ] 验证 `alembic upgrade head` 可执行
- [ ] 提交

---

## 11. 验收标准

- [ ] `GET /api/health` 无需鉴权返回 200 `{"status": "ok"}`
- [ ] 所有错误响应（400/401/403/404/409/500/502）body 均为 `{code, message, detail}` **三字段**
- [ ] 请求体校验失败返回 **400**（非 422），`detail` 含字段级错误
- [ ] 500 响应**不泄漏堆栈信息**
- [ ] 各异常类的默认 `message` 为可直接展示给用户的中文
- [ ] `hash_password` 对同一明文产生**不同**哈希；`verify_password` 对非法哈希返回 `False` 不抛异常
- [ ] `create_access_token` → `decode_token` 往返得到同一 `user_id`
- [ ] 过期 / 篡改 token 抛出 `InvalidTokenError`（401）
- [ ] JWT 载荷中**不含角色**（角色每次查库，保证权限变更立即生效）
- [ ] `alembic upgrade head` 可正常执行
- [ ] **core 中不存在对任何业务模块的顶层 import**
- [ ] 全部 core 测试通过

---

## 12. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| PRD §3.3 未列 `core` | 显式新增为第七个 package | PRD 的横切要求（统一错误格式、分层底座、JWT、DB 连接）必须有唯一落点，否则各模块重复实现并发散，违背 §9 的可维护性目标。**不扩大功能范围** |
| core 不依赖 auth，但 `get_current_user` 需查 User | 函数体内延迟导入 | 保住依赖单向；`get_current_user` 语义上是横切关注点 |
| **PRD §9「JWT 刷新」如何落地** | **默认方案 A：过期后重新登录** | 见 §5.3。改 B 是 core 内小改动；改 C 会新增表与端点，属范围扩大——**请评审时确认** |
| 角色放 JWT 还是每次查库 | 每次查库 | 权限变更立即生效；代价是每请求一次主键查询，可接受 |
| 测试库用 MySQL 还是 SQLite | **优先 MySQL**（与生产同构） | PRD §2 指定 MySQL，且多个字段用 JSON 列，SQLite 行为有差异。SQLite 仅作快速跑通用的降级选项 |
| PRD §7 的「422/400」 | 统一收口为 400 | 使全项目错误码收敛为一张表；避免同一类错误出现两种状态码 |
| `JWT_SECRET` 缺失时 | 启动即报错（fail fast） | 避免用默认密钥跑在生产；显式失败优于静默不安全 |
