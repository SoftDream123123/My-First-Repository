# auth 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：auth（用户、登录、JWT、角色、数据隔离）
**所属包**：`backend/app/auth/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.1（用户与鉴权）、§5.2（`user` 实体）、§8（auth API）、§9（安全）
**前置依赖**：core（[2026-09-15-module-00-core-plan.md](./2026-09-15-module-00-core-plan.md)）

> **MVP-2 增量（2026-09-20）**：新增第三个角色 `candidate`、候选人自助注册、多角色守卫基座（`require_roles`）。本文档的 §1.1、§1.2、§3.1、§4.1、§4.5、§5.3、§10 已按增量同步修正；**增量部分的完整契约以 [module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md) 为准**。角色守卫逐路由落地见 [module-16](./2026-09-20-module-16-permission-guard-plan.md)。

---

## Global Constraints（全局约束，摘自 PRD）

- 后端分层：**router → service → repository → MySQL，严格单向依赖**（§2、§3.2）
- 每个模块独立 Python package（§2、§3.3）
- 统一响应格式：**`{code, message, detail}`**（§7）
- 安全：**密码哈希存储（bcrypt/argon2）；JWT 过期与刷新；参数校验防注入**（§9）
- 统一前缀 `/api`，**除登录外均需 JWT**（§8）
- **数据隔离：普通 HR 只能访问自己创建的数据；admin 可访问全部**（§4.1）
- 可测试性：三层可独立测试（§9、§10）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.1）

| 子职责 | 内容 | PRD |
|---|---|---|
| 用户实体 | `user` 表的定义与迁移 | §5.2 |
| 认证 | 用户名 + 密码登录，签发 JWT | §4.1 |
| 授权 | 角色（`admin` / `hr`）定义与角色校验依赖 | §4.1 |
| 初始管理员 | 通过脚本 seed 内置 admin | §4.1 |
| 用户管理 | admin 创建用户、查询列表、改角色、启用/禁用 | §4.1 |
| **数据隔离基座** | 提供「当前用户可见数据范围」的统一判定，供所有业务模块复用 | §4.1 |
| **候选人角色**（MVP-2） | `candidate` 角色的定义、迁移与账号创建路径 | §4.1、§4.6 |
| **多角色守卫基座**（MVP-2） | `require_roles(*roles)`：支持多角色判定的依赖工厂，HR 侧守卫的地基 | §4.1 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **HR / admin 自助注册** | PRD §4.1 明确「普通 HR 不可自行注册」，HR 与 admin 只能由 admin 创建。**MVP-2 起存在一处例外**：候选人可自助注册，但只产出 `candidate` 角色、只带刷题权限——该约束本身不变（见 [module-09](./2026-09-20-module-09-auth-plan.md)） |
| **admin 创建 candidate**（MVP-2 补充） | PRD §4.1 只允许 admin 指定 `admin`/`hr`。候选人账号只能来自自助注册或凭邀请激活，保证其与刷题或某场面试有真实关联 |
| **找回密码 / 改密码** | 不在 PRD 范围 |
| **Refresh Token** | 见 core 模块计划书 §5.3——PRD §9「JWT 过期与刷新」默认按「过期后重新登录」落地，**该决策待评审确认** |
| **审计日志** | 不在 PRD 范围 |
| **业务模块的数据过滤逻辑** | auth 只提供「范围判定」，具体 SQL 过滤在各业务模块的 repository 中执行（见 §5.3） |
| **物理删除用户** | 见 §3.2 |

### 1.3 依赖方向

```
auth.router ──→ auth.service ──→ auth.repository ──→ user 表
                    │
                    └──→ core.security / core.exceptions

auth ──→ core（单向）
其他业务模块 ──→ auth（通过 core.deps.get_current_user 与 auth.service.scope_owner_id）
core ✗→ auth（get_current_user 内延迟导入 User，见 core 计划书 §1.3）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/auth/__init__.py` | 包标识 |
| `backend/app/auth/models.py` | `User` 模型定义 |
| `backend/app/auth/schemas.py` | 请求 / 响应 Pydantic 模型 |
| `backend/app/auth/repository.py` | `user` 表数据访问（纯 CRUD，无业务判断） |
| `backend/app/auth/service.py` | 登录、用户管理、可见范围判定 |
| `backend/app/auth/router.py` | `/api/auth/*`、`/api/users/*` 端点 |
| `backend/scripts/seed_admin.py` | 初始化 admin 账号脚本（PRD §4.1） |

**测试文件**：`backend/tests/test_auth.py`、`backend/tests/test_deps.py`

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/core/deps.py` | 补齐 `get_current_user`、`require_role`（core Task 0.7 拆出的部分） |
| `backend/app/main.py` | 注册 auth router |
| `backend/alembic/versions/` | 新增 `user` 表迁移 |

---

## 3. 数据模型设计

### 3.1 表 `user`（对应 PRD §5.2 的 `user` 实体）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `username` | VARCHAR(50) | NOT NULL, **UNIQUE**, INDEX | 登录名 |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt 哈希，**永不返回给客户端** |
| `role` | ENUM('admin','hr','candidate') | NOT NULL, DEFAULT `'hr'` | 角色（PRD §4.1）；第三个取值 `candidate` 为 **MVP-2 新增** |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | 禁用后不可登录 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |

**PRD §5.2 对 `user` 的字段列表为 `id, username, password_hash, role`。本设计新增两个字段：**

| 新增字段 | 为何必要 |
|---|---|
| `is_active` | PRD §8 的 `PATCH /users/{id}` 明确要求支持「**禁用**」。没有该字段则无法实现——这是补齐，不是扩展 |
| `created_at` | 用户管理界面的基础信息；且与其余所有实体保持一致的审计字段 |

### 3.2 设计要点

| 要点 | 理由 |
|---|---|
| **`username` 唯一索引** | 并发创建同名用户时由数据库兜底报错，service 捕获后转 `BUSINESS_ERROR`；不依赖「先查后插」的竞态检查 |
| **`password_hash` 长度 255** | bcrypt 输出固定 60 字符，留余量以便未来切换到 argon2 |
| **角色用 ENUM 而非字符串** | 与 MySQL ENUM 对齐，避免脏数据 |
| **不存明文密码、不存密码盐** | 盐由 bcrypt 内嵌在哈希串中（PRD §9 要求的哈希存储） |
| **`is_active` 而非删除用户** | 面试、岗位、题目均通过 `created_by` 关联用户。物理删除会造成孤儿数据（外键悬空），故只做禁用 |

---

## 4. 接口契约

### 4.1 对外 REST API（对应 PRD §8）

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/auth/login` | 登录，返回 JWT | **公开** | 200 |
| POST | `/api/auth/register` | **MVP-2 新增**：候选人自助注册（只产出 candidate 角色，仅刷题） | **公开** | 201 |
| GET | `/api/auth/me` | 当前用户信息 | 登录 | 200 |
| POST | `/api/users` | 创建用户 | **admin** | 201 |
| GET | `/api/users` | 用户列表 | **admin** | 200 |
| PATCH | `/api/users/{id}` | 改角色 / 启用禁用 | **admin** | 200 |

### 4.2 请求 / 响应结构

**POST `/api/auth/login`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `username` | str | 必填，1–50 字符 |
| 请求 | `password` | str | 必填，1–128 字符 |
| 响应 | `token` | str | JWT |
| 响应 | `user.id` | int | — |
| 响应 | `user.username` | str | — |
| 响应 | `user.role` | str | `admin` \| `hr` |

**GET `/api/auth/me`** → user 对象：`id`、`username`、`role`、`is_active`、`created_at`。**不含 `password_hash`**。

**POST `/api/users`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `username` | str | 必填，1–50 字符，全局唯一 |
| 请求 | `password` | str | 必填，**最少 8 字符** |
| 请求 | `role` | str | 必填，`admin` \| `hr` |
| 响应 | `id` / `username` / `role` / `is_active` / `created_at` | — | **不含 `password_hash`** |

**GET `/api/users`** → user 对象数组（不含 `password_hash`）。**MVP 不分页**（内部系统用户量小，YAGNI）。

**PATCH `/api/users/{id}`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `role` | str \| 可选 | `admin` \| `hr` |
| 请求 | `is_active` | bool \| 可选 | — |
| 响应 | user 对象 | — | — |

> **防呆规则（写进 service）**：admin **不得**通过本接口把自己降级或禁用（避免把自己锁死，导致系统无人可管）。触发时返回 `BUSINESS_ERROR`。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `login(db, username: str, password: str) -> LoginResult` | token + user | 校验凭据、校验启用状态、签发 JWT |
| `get_user_by_id(db, user_id: int) -> User \| None` | User | 供 `core.deps.get_current_user` 使用 |
| `create_user(db, username: str, password: str, role: str) -> User` | User | 校验唯一性、哈希后落库 |
| `list_users(db) -> list[User]` | User 列表 | — |
| `update_user(db, actor: User, user_id: int, role: str \| None, is_active: bool \| None) -> User` | User | 含 §4.2 的防呆规则 |
| `scope_owner_id(user: User) -> int \| None` | `None` 或 `user.id` | **数据隔离统一判定**（见 §5.3） |

`LoginResult` 为 service 层返回结构，字段：`token: str`、`user: User`。

### 4.4 repository 层方法签名

| 方法签名 | 返回 |
|---|---|
| `get_by_id(db, user_id: int) -> User \| None` | User |
| `get_by_username(db, username: str) -> User \| None` | User |
| `create(db, username: str, password_hash: str, role: str) -> User` | User |
| `list_all(db) -> list[User]` | User 列表 |
| `update(db, user: User, **fields) -> User` | User |

**分层约定**：repository 只做数据操作，**不做**「密码是否正确」「用户名是否重复」这类判断——那属于 service。

### 4.5 需在 `core.deps` 补齐的依赖

| 依赖签名 | 行为 |
|---|---|
| `get_current_user(db: Session, token: str) -> User` | `decode_token` → `get_user_by_id` → 不存在或 `is_active=False` → `UnauthorizedError` |
| `require_role(role: str) -> Callable` | 依赖工厂；`user.role != role` → `ForbiddenError` |
| `require_roles(*roles: str) -> Callable` | **MVP-2 新增**：依赖工厂，多角色判定；`user.role not in roles` → `ForbiddenError`。`require_role` 改为对它的薄封装。用法与「精确匹配、无角色层级」规则见 [module-09 §4.5、§5.3](./2026-09-20-module-09-auth-plan.md) |

---

## 5. 业务流程设计

### 5.1 登录流程（PRD §4.1）

```
1. 按 username 查用户
2. 用户不存在 或 密码不匹配  →  统一返回 401 UNAUTHORIZED「用户名或密码错误」
3. 用户 is_active = False      →  返回 401 UNAUTHORIZED「账号已禁用」
4. 签发 JWT（载荷 sub=user.id, iat, exp；不含 role，见 core §5.2）
5. 返回 token + user 信息
```

| 安全设计 | 说明 |
|---|---|
| **不区分「用户不存在」与「密码错误」** | 第 2 步对两种情况返回**完全相同**的错误码与文案，避免用户名枚举攻击 |
| **时序攻击加固（可选）** | 用户不存在时也执行一次 dummy 哈希比对以拉平响应时间。内外网风险不同，**标记为可选加固项** |

### 5.2 创建用户流程

```
1. schemas 层校验密码长度 ≥ 8
2. service 校验 username 未被占用（友好报错）
3. bcrypt 哈希密码
4. 落库；并发触发唯一索引冲突 → 捕获 IntegrityError → 转 BUSINESS_ERROR
5. 返回用户信息（剥离 password_hash）
```

### 5.3 数据隔离的统一约定（**本模块对全项目最重要的产出**）

PRD §4.1 要求「普通 HR 只能访问自己创建的数据；admin 可访问全部」。该要求横跨 position / question / interview 三个模块，必须有一个统一的判定入口，否则会各写各的。

**统一模式**：所有业务模块的 repository 查询方法接收 `owner_id: int | None` 参数，由 service 用 `scope_owner_id(user)` 的结果填充。

| 调用方角色 | `scope_owner_id(user)` 返回 | repository 行为 |
|---|---|---|
| admin | `None` | **不过滤**，返回全部数据（PRD §4.1） |
| hr | `user.id` | 追加 `WHERE created_by = :owner_id`（PRD §4.1） |
| candidate（**MVP-2**） | — | **抛 `ForbiddenError`**：候选人不拥有任何 HR 数据，不得落入 owner 分支。改动与理由见 [module-16 §4](./2026-09-20-module-16-permission-guard-plan.md) |

> **候选人的可见范围不由本函数表达**：候选人的判据是「是否持有该面试的有效邀请」（数据在 `interview_invitation`），因此候选人**不能**复用 `created_by`——候选人不是面试的创建者，按 `created_by` 过滤会让其看不到任何自己的面试（PRD §4.1 的原话即为此意）。该判据由 `interview` 模块实现（见 [module-12](./2026-09-20-module-12-interview-invitation-plan.md)）；刷题取题则明确**不做** `created_by` 过滤（见 [module-10 §5.5](./2026-09-20-module-10-question-plan.md)）。

**访问单条数据时的统一模式**：

```
1. repository.get_by_id(id) → 为 None 则 NotFoundError（404）
2. owner_id = scope_owner_id(user)
3. owner_id 非 None 且 != 记录.created_by → ForbiddenError（403）
4. 返回
```

> **为何返回 403 而非 404**：语义明确——资源存在但无权访问。此模式被 position / question / interview / evaluation 统一复用。**注意**：直接返回 403 会暴露「该 id 存在」，对内部 HR 系统可接受；若未来面向多租户应改为 404。

### 5.4 初始管理员 seed（PRD §4.1）

| 项 | 设计 |
|---|---|
| 位置 | `backend/scripts/seed_admin.py` |
| 来源 | 命令行手动执行（**不做自动迁移 seed**） |
| 凭据 | 读 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 配置（core §3） |
| **幂等性** | 若同名用户已存在则**跳过**，不报错、不覆盖密码 |
| 输出 | 打印创建结果；若使用默认密码，打印显著警告 |

> **为何不放进 Alembic 数据迁移**：迁移应是**结构变更**的载体，把有副作用的账号创建写进迁移会导致回滚语义混乱；且生产环境不应在迁移中静默创建已知密码的账号。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 未带 token | `UNAUTHORIZED` | 401 | 未认证 |
| token 过期 / 篡改 | `INVALID_TOKEN` | 401 | 登录状态已失效，请重新登录 |
| 用户名或密码错误 | `UNAUTHORIZED` | 401 | 用户名或密码错误 |
| 账号被禁用 | `UNAUTHORIZED` | 401 | 账号已禁用，请联系管理员 |
| 非 admin 访问 `/users` | `FORBIDDEN` | 403 | 无权限执行此操作 |
| 用户不存在（`/users/{id}`） | `NOT_FOUND` | 404 | 用户不存在 |
| 用户名已存在 | `BUSINESS_ERROR` | 409 | 用户名已存在 |
| 密码长度不足 | `VALIDATION_ERROR` | 400 | 密码长度不能少于 8 位（`detail` 含字段名） |
| admin 操作自己 | `BUSINESS_ERROR` | 409 | 不能修改自己的角色或状态 |

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `backend/tests/test_auth.py`

| 测试 | 断言 |
|---|---|
| `test_login_success` | 正确凭据 → 200，返回 `token` 与 `user`，且 `user` 中**无** `password_hash` |
| `test_login_wrong_password` | 401 `UNAUTHORIZED` |
| `test_login_unknown_username` | 401，且错误码与文案**与密码错误完全一致** |
| `test_login_disabled_user` | 401 |
| `test_password_stored_hashed` | 库中 `password_hash` ≠ 明文，且以 bcrypt 前缀开头 |
| `test_me_without_token` | 401 `UNAUTHORIZED` |
| `test_me_with_invalid_token` | 401 `INVALID_TOKEN` |
| `test_me_with_valid_token` | 200，返回正确用户 |
| `test_create_user_as_admin` | 201，用户落库 |
| `test_create_user_as_hr_forbidden` | 403 `FORBIDDEN` |
| `test_create_user_duplicate_username` | 409 `BUSINESS_ERROR` |
| `test_create_user_short_password` | 400 `VALIDATION_ERROR` |
| `test_list_users_as_admin` | 200，返回全部用户，**均不含** `password_hash` |
| `test_list_users_as_hr_forbidden` | 403 |
| `test_update_user_role` | 200，角色变更生效 |
| `test_update_user_disable` | 200，`is_active=False` 后该用户登录返回 401 |
| `test_admin_cannot_modify_self` | 409 `BUSINESS_ERROR` |
| `test_role_change_takes_effect_immediately` | hr 升为 admin 后，**用同一个旧 token** 即可访问 `/users`（验证角色不缓存于 JWT） |
| `test_all_user_responses_exclude_password_hash` | 遍历三个端点，响应体中均不出现 `password_hash` |

### 7.2 `backend/tests/test_deps.py`

| 测试 | 断言 |
|---|---|
| `test_get_current_user_missing_header` | 401 `UNAUTHORIZED` |
| `test_get_current_user_bad_scheme` | 非 `Bearer` 前缀 → 401 |
| `test_get_current_user_disabled` | 用户被禁用后，其旧 token 访问 → 401 |
| `test_require_role_pass` | 角色匹配 → 放行 |
| `test_require_role_reject` | 角色不匹配 → 403 `FORBIDDEN` |
| `test_scope_owner_id_admin` | admin → `None` |
| `test_scope_owner_id_hr` | hr → `user.id` |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 1.1：`User` 模型与迁移

- [ ] 定义 `User` 模型（§3.1 全字段、唯一索引、ENUM 角色）
- [ ] 在 `alembic/env.py` 中确保导入 `auth.models`
- [ ] 生成迁移并执行 `alembic upgrade head`
- [ ] 验证表结构与索引正确
- [ ] 提交

### Task 1.2：schema 定义

- [ ] 定义 `LoginRequest`、`LoginResponse`、`UserOut`、`UserCreate`、`UserUpdate`
- [ ] 写失败测试：`UserOut` **不包含** `password_hash` 字段
- [ ] 运行确认失败 → 修正 → 通过
- [ ] 提交

### Task 1.3：repository 层

- [ ] 写失败测试：`create` 后可按 username 查回；`get_by_id` 不存在返回 `None`
- [ ] 运行确认失败
- [ ] 实现 §4.4 的五个方法
- [ ] 运行确认通过
- [ ] 提交

### Task 1.4：补齐 `core.deps`

- [ ] 写 `test_deps.py` 中 §7.2 的失败测试
- [ ] 运行确认失败
- [ ] 实现 `get_current_user`（**延迟导入 `User`**）与 `require_role` 工厂
- [ ] 运行确认通过
- [ ] 提交

### Task 1.5：登录与当前用户

- [ ] 写 `test_login_*` 与 `test_me_*` 失败测试（**含「未知用户名与错误密码响应完全一致」**）
- [ ] 运行确认失败
- [ ] 实现 `service.login` 与 `/auth/login`、`/auth/me` 端点
- [ ] 在 `main.py` 注册 auth router
- [ ] 运行确认通过
- [ ] 提交

### Task 1.6：用户管理（admin）

- [ ] 写 §7.1 中 `test_create_user_*`、`test_list_users_*`、`test_update_user_*`、`test_admin_cannot_modify_self` 失败测试
- [ ] 运行确认失败
- [ ] 实现 `service.create_user` / `list_users` / `update_user` 与 `/users` 三个端点（`require_role("admin")` 保护）
- [ ] 运行确认通过
- [ ] 提交

### Task 1.7：数据隔离基座

- [ ] 写 `test_scope_owner_id_*` 失败测试
- [ ] 运行确认失败
- [ ] 实现 `scope_owner_id`
- [ ] 运行确认通过
- [ ] 提交

### Task 1.8：seed admin 脚本

- [ ] 编写 `backend/scripts/seed_admin.py`：读配置、**幂等**创建 admin
- [ ] 手动验证：空库执行 → 可登录；**重复执行 → 不报错、不重复创建、不覆盖密码**
- [ ] 提交

### Task 1.9：全量回归

- [ ] 运行 `pytest backend/tests/test_auth.py backend/tests/test_deps.py -v`，全部通过
- [ ] 运行 core 模块测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] `POST /api/auth/login` 正确凭据返回 token；错误凭据返回 401 且**不区分**「用户不存在」与「密码错误」
- [ ] 禁用用户无法登录；**已登录用户的旧 token 在禁用后也立即失效**
- [ ] `GET /api/auth/me` 无 token → 401，有效 token → 返回用户信息
- [ ] 所有用户相关响应中**均不含** `password_hash`
- [ ] 数据库中密码字段为 bcrypt 哈希，不等于明文
- [ ] 非 admin 访问 `/api/users*` 一律 403
- [ ] admin 无法修改自己的角色或启用状态（409）
- [ ] 角色变更**立即生效**，无需重新登录
- [ ] `scope_owner_id(admin)` 返回 `None`、`scope_owner_id(hr)` 返回 `user.id`
- [ ] seed 脚本**幂等**（重复执行不重复创建、不覆盖密码）
- [ ] 全部 auth / deps 测试通过

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| `user` 表需新增 `is_active` | 新增 | PRD §8 的 `PATCH /users/{id}` 明确要求「禁用」，无此字段无法实现。属补齐 |
| 角色放 JWT 还是每次查库 | **每次查库** | 权限变更/禁用立即生效（有专门测试覆盖）；代价是每请求一次主键查询，可接受 |
| 「先查重再插入」的并发竞态 | 依赖唯一索引 + 捕获 `IntegrityError` | 唯一索引是最终防线，查重只为友好报错 |
| 用户不存在时的响应时间差异（时序攻击） | **标记为可选加固** | 内网 HR 系统风险低；如加固则补 dummy 哈希比对 |
| 是否物理删除用户 | **不删，只 `is_active=False`** | 避免 `created_by` 外键悬空（position / question / interview 均引用该字段） |
| 用户列表是否分页 | **不分页** | 内部系统用户量小（YAGNI） |
| 初始 admin 是否放 Alembic 数据迁移 | **不放，独立脚本** | 迁移应只承载结构变更；生产不应在迁移中静默创建已知密码的账号 |
| 数据隔离返回 403 还是 404 | **403** | 语义明确；内部系统可接受信息暴露。多租户场景应改 404 |
| **（MVP-2）第三角色引入后存量路由无守卫** | 新建独立文档 [module-16](./2026-09-20-module-16-permission-guard-plan.md) 逐路由补全，且**必须与 module-09 同批发布** | 加入 `candidate` 后，只校验「已登录」的 HR 路由会被候选人越权调用。该风险不属于 auth 模块内部，但由本次角色扩展引入，故在此登记 |
| **（MVP-2）MySQL ENUM 收回取值会静默损坏数据** | 迁移的 `downgrade()` 检测到 candidate 行即抛错 | 见 [module-09 §3.3](./2026-09-20-module-09-auth-plan.md) |
