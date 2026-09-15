# auth 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：auth（认证与用户管理）
**所属包**：`backend/app/auth/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp.md](../plans/2026-09-15-ai-interview-assistant-mvp.md)
**设计规格**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 任务**：Task 1
**前置依赖**：core 模块（计划书 [2026-09-15-module-00-core-plan.md](./2026-09-15-module-00-core-plan.md)）

---

## Global Constraints（全局约束）

- 后端严格分层：`router → service → repository → MySQL`，只允许自上而下依赖，不跨层调用、不反向依赖。
- 每个模块独立 Python package（`backend/app/<module>/`）。
- 评分统一 0–10 分制（逐题、维度、总分）。
- 数据隔离：普通 HR 仅见自己创建的数据，admin 见全部。
- 仅 PC 端，不做移动端响应式。
- 统一错误响应格式 `{code, message, detail}`。
- 密码哈希存储（bcrypt），JWT 鉴权。

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 |
|---|---|
| 用户实体 | User 表的定义与迁移 |
| 认证 | 用户名 + 密码登录，签发 JWT；解析当前用户 |
| 授权 | 角色（admin / hr）定义与角色校验依赖 |
| 用户管理 | admin 创建用户、查询用户列表、改角色、启用/禁用 |
| 数据隔离基座 | 提供「当前用户可见数据范围」的统一判定，供所有业务模块复用 |

### 1.2 边界（明确不做）

- **不做注册**：MVP 无自助注册，用户只能由 admin 创建（PRD §4.1）。
- **不做找回密码 / 改密码**：不在 MVP 范围。
- **不做刷新 token**：MVP 仅签发与校验，过期后重新登录。
- **不做审计日志**：不在 MVP 范围。
- **不实现业务模块的数据过滤逻辑**：auth 只提供「范围判定」，具体 SQL 过滤在各业务模块的 repository 中执行。

### 1.3 依赖方向

```
auth.router ──→ auth.service ──→ auth.repository ──→ User 表
                    │
                    └──→ core.security / core.exceptions

auth ──→ core（单向）
其他业务模块 ──→ auth（通过 core.deps.get_current_user 与 scope_owner_id）
core 不依赖 auth（get_current_user 内延迟导入 User，见 core 计划书 §1.3）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/auth/__init__.py` | 包标识 |
| `backend/app/auth/models.py` | `User` 模型定义 |
| `backend/app/auth/schemas.py` | 请求 / 响应 Pydantic 模型 |
| `backend/app/auth/repository.py` | User 表的数据访问（纯 CRUD，无业务判断） |
| `backend/app/auth/service.py` | 登录、用户管理、可见范围判定 |
| `backend/app/auth/router.py` | `/api/auth/*`、`/api/users/*` 端点 |
| `backend/scripts/seed_admin.py` | 初始化 admin 账号的脚本 |

**测试文件**：`backend/tests/test_auth.py`、`backend/tests/test_deps.py`

**本模块需修改的上游文件**：

| 文件 | 修改内容 |
|---|---|
| `backend/app/core/deps.py` | 补齐 `get_current_user`、`require_role`（core Task 0.7 拆出的部分） |
| `backend/app/core/config.py` | 新增 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`BCRYPT_ROUNDS` |
| `backend/app/main.py` | 注册 auth router |
| `backend/alembic/versions/` | 新增 User 表迁移 |

---

## 3. 数据模型设计

### 3.1 表 `user`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `username` | VARCHAR(50) | NOT NULL, **UNIQUE**, INDEX | 登录名 |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt 哈希，永不返回给客户端 |
| `role` | ENUM('admin','hr') | NOT NULL, DEFAULT 'hr' | 角色 |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | 禁用后不可登录 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |

> **对 PRD §5.2 的补充说明**：PRD 中 `user` 字段列表为示意简写。因 PRD §4.1 与 API 概览要求 `PATCH /users/{id}` 支持「改角色 / 禁用」，本设计增加 `is_active` 字段。此为必要补充，非范围扩大。

### 3.2 设计要点

- **`username` 唯一索引**：并发创建同名用户时由数据库兜底报错，service 捕获后转 `BUSINESS_ERROR`（而非依赖「先查后插」的竞态检查）。
- **`password_hash` 长度 255**：bcrypt 输出固定 60 字符，留余量以便未来切换算法（如 argon2）。
- **角色用枚举而非字符串**：与 MySQL ENUM 对齐，避免脏数据。
- **不存明文密码、不存密码盐**：盐由 bcrypt 内嵌在哈希串中。
- **`is_active` 而非删除用户**：面试记录通过 `created_by` 关联用户，物理删除会造成孤儿数据，故只做禁用。

---

## 4. 接口契约

### 4.1 对外 REST API

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/auth/login` | 登录，返回 JWT + 用户信息 | 公开 | 200 |
| GET | `/api/auth/me` | 获取当前登录用户 | 登录 | 200 |
| POST | `/api/users` | 创建用户 | admin | 201 |
| GET | `/api/users` | 用户列表 | admin | 200 |
| PATCH | `/api/users/{id}` | 改角色 / 启用禁用 | admin | 200 |

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

**GET `/api/auth/me`** → 响应 `user` 对象（`id`、`username`、`role`、`is_active`、`created_at`）。**不含 `password_hash`**。

**POST `/api/users`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `username` | str | 必填，1–50 字符，全局唯一 |
| 请求 | `password` | str | 必填，**最少 8 字符** |
| 请求 | `role` | str | 必填，`admin` \| `hr` |
| 响应 | `id` / `username` / `role` / `is_active` / `created_at` | — | 不含 `password_hash` |

**GET `/api/users`** → 响应为 user 对象数组（不含 `password_hash`）。MVP 不分页（用户量小）。

**PATCH `/api/users/{id}`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `role` | str \| 可选 | `admin` \| `hr` |
| 请求 | `is_active` | bool \| 可选 | — |
| 响应 | user 对象 | — | — |

> **防呆规则（写进 service）**：admin **不得**通过本接口把自己降级或禁用（避免把自己锁死）。触发时返回 `BUSINESS_ERROR`。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `login(db: Session, username: str, password: str) -> LoginResult` | token + user | 校验凭据、校验启用状态、签发 JWT |
| `get_user_by_id(db: Session, user_id: int) -> User \| None` | User | 供 deps 使用 |
| `create_user(db: Session, username: str, password: str, role: str) -> User` | User | 校验用户名唯一、密码策略、哈希后落库 |
| `list_users(db: Session) -> list[User]` | User 列表 | — |
| `update_user(db: Session, actor: User, user_id: int, role: str \| None, is_active: bool \| None) -> User` | 更新后 User | 含 §4.2 防呆规则 |
| `scope_owner_id(user: User) -> int \| None` | `None` 或 `user.id` | **数据隔离统一判定**：admin → `None`（不过滤）；hr → `user.id` |

`LoginResult` 为 service 层返回的数据结构，字段：`token: str`、`user: User`。

### 4.4 repository 层方法签名

| 方法签名 | 返回 |
|---|---|
| `get_by_id(db: Session, user_id: int) -> User \| None` | User |
| `get_by_username(db: Session, username: str) -> User \| None` | User |
| `create(db: Session, username: str, password_hash: str, role: str) -> User` | User |
| `list_all(db: Session) -> list[User]` | User 列表 |
| `update(db: Session, user: User, **fields) -> User` | User |

**分层约定**：repository 只做数据操作，**不做**「密码是否正确」「用户名是否重复」这类判断——那属于 service。

### 4.5 core.deps 补齐的依赖

| 依赖签名 | 行为 |
|---|---|
| `get_current_user(db: Session, token: str) -> User` | 解码 token → `get_user_by_id` → 不存在或 `is_active=False` → `UnauthorizedError` |
| `require_role(role: str) -> Callable` | 依赖工厂；`user.role != role` → `ForbiddenError` |

---

## 5. 业务流程设计

### 5.1 登录流程

```
1. 按 username 查用户
2. 用户不存在 或 密码不匹配  →  统一返回 401 UNAUTHORIZED「用户名或密码错误」
3. 用户 is_active = False      →  返回 401 UNAUTHORIZED「账号已禁用」
4. 签发 JWT（载荷 sub=user.id, iat, exp）
5. 返回 token + user 信息
```

> **安全设计**：第 2 步对「用户名不存在」与「密码错误」返回**完全相同的错误码与文案**，避免用户名枚举攻击。且**先查库再校验密码**的写法下，用户不存在时也应执行一次 dummy 哈希比对以拉平响应时间（MVP 可选，本设计**标记为可选加固项**）。

### 5.2 创建用户流程

```
1. 校验密码长度 ≥ 8（schemas 层）
2. 校验 username 未被占用（service，友好报错）
3. bcrypt 哈希密码
4. 落库；若并发触发唯一索引冲突 → 捕获 IntegrityError → 转 BUSINESS_ERROR
5. 返回用户信息（剥离 password_hash）
```

### 5.3 数据隔离的统一约定（**本模块对全项目最重要的产出**）

其他所有业务模块的 repository 查询都遵循同一模式：

| 调用方角色 | `scope_owner_id(user)` 返回 | repository 行为 |
|---|---|---|
| admin | `None` | 不过滤，返回全部数据 |
| hr | `user.id` | 追加 `WHERE created_by = :owner_id` |

**落地约定**：各业务模块的 repository 方法统一接收 `owner_id: int | None` 参数；`owner_id is None` 表示不限制。service 用 `scope_owner_id(user)` 的结果填充该参数。

**访问单条数据时**：repository 按 `id` 取回后，由 service 校验 `scope_owner_id` 是否匹配，不匹配返回 `ForbiddenError`（而非 `NotFoundError`，以明确语义）。

---

## 6. 错误处理

| 场景 | code | HTTP | message 示例 |
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

## 7. 测试设计

`backend/tests/test_auth.py`

| 测试 | 断言 |
|---|---|
| `test_login_success` | 正确凭据 → 200，返回 `token` 与 `user`，且 `user` 中**无** `password_hash` |
| `test_login_wrong_password` | 401 `UNAUTHORIZED` |
| `test_login_unknown_username` | 401，且错误码与文案**与密码错误完全一致** |
| `test_login_disabled_user` | 401 |
| `test_me_without_token` | 401 `UNAUTHORIZED` |
| `test_me_with_invalid_token` | 401 `INVALID_TOKEN` |
| `test_me_with_valid_token` | 200，返回正确用户 |
| `test_create_user_as_admin` | 201，用户落库，密码在库中为哈希（不等于明文） |
| `test_create_user_as_hr_forbidden` | 403 `FORBIDDEN` |
| `test_create_user_duplicate_username` | 409 `BUSINESS_ERROR` |
| `test_create_user_short_password` | 400 `VALIDATION_ERROR` |
| `test_list_users_as_admin` | 200，返回全部用户，**均不含** `password_hash` |
| `test_list_users_as_hr_forbidden` | 403 |
| `test_update_user_role` | 200，角色变更生效 |
| `test_update_user_disable` | 200，`is_active=False` 后该用户登录返回 401 |
| `test_admin_cannot_modify_self` | 409 `BUSINESS_ERROR` |
| `test_role_change_takes_effect_immediately` | hr 升为 admin 后，**用同一个旧 token** 即可访问 `/users`（验证角色不缓存于 token） |

`backend/tests/test_deps.py`

| 测试 | 断言 |
|---|---|
| `test_get_current_user_missing_header` | 401 `UNAUTHORIZED` |
| `test_get_current_user_bad_scheme` | 非 `Bearer` 前缀 → 401 |
| `test_require_role_pass` | 角色匹配 → 放行 |
| `test_require_role_reject` | 角色不匹配 → 403 `FORBIDDEN` |
| `test_scope_owner_id_admin` | admin → `None` |
| `test_scope_owner_id_hr` | hr → `user.id` |

---

## 8. 任务分解（TDD 步骤，无代码）

### Task 1.1：User 模型与迁移

- [ ] 定义 `User` 模型（§3.1 全字段、唯一索引、ENUM 角色）
- [ ] 在 `alembic/env.py` 中确保导入 `auth.models`
- [ ] 生成迁移并执行 `alembic upgrade head`
- [ ] 验证表结构与索引正确
- [ ] 提交

### Task 1.2：schema 定义

- [ ] 定义 `LoginRequest`、`LoginResponse`、`UserOut`、`UserCreate`、`UserUpdate`
- [ ] 写失败测试：`UserOut` 不包含 `password_hash` 字段
- [ ] 运行测试确认失败 → 修正 → 通过
- [ ] 提交

### Task 1.3：repository 层

- [ ] 写失败测试：`create` 后可按 username 查回；`get_by_id` 不存在返回 `None`
- [ ] 运行测试确认失败
- [ ] 实现 §4.4 的五个方法
- [ ] 运行测试确认通过
- [ ] 提交

### Task 1.4：补齐 core.deps

- [ ] 写 `test_deps.py` 中 §7 的五条失败测试
- [ ] 运行测试确认失败
- [ ] 实现 `get_current_user`（延迟导入 `User`）与 `require_role` 工厂
- [ ] 运行测试确认通过
- [ ] 提交

### Task 1.5：登录与当前用户

- [ ] 写 `test_login_*` 与 `test_me_*` 失败测试（含「未知用户名与错误密码响应一致」）
- [ ] 运行测试确认失败
- [ ] 实现 `service.login` 与 `/auth/login`、`/auth/me` 端点
- [ ] 在 `main.py` 注册 auth router
- [ ] 运行测试确认通过
- [ ] 提交

### Task 1.6：用户管理（admin）

- [ ] 写 `test_create_user_*`、`test_list_users_*`、`test_update_user_*`、`test_admin_cannot_modify_self` 失败测试
- [ ] 运行测试确认失败
- [ ] 实现 `service.create_user` / `list_users` / `update_user` 与 `/users` 三个端点
- [ ] 运行测试确认通过
- [ ] 提交

### Task 1.7：数据隔离基座

- [ ] 写 `test_scope_owner_id_*` 失败测试
- [ ] 运行测试确认失败
- [ ] 实现 `scope_owner_id`
- [ ] 运行测试确认通过
- [ ] 提交

### Task 1.8：seed admin 脚本

- [ ] 在 `core/config.py` 增加 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`BCRYPT_ROUNDS`
- [ ] 编写 `backend/scripts/seed_admin.py`：若 admin 已存在则跳过（幂等），否则创建
- [ ] 手动验证：空库执行脚本 → 可登录；重复执行 → 不报错、不重复创建
- [ ] 提交

### Task 1.9：全量回归

- [ ] 运行 `pytest backend/tests/test_auth.py backend/tests/test_deps.py -v`，全部通过
- [ ] 运行 core 模块测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] `POST /api/auth/login` 正确凭据返回 token；错误凭据返回 401 且**不区分**「用户不存在」与「密码错误」
- [ ] 禁用用户无法登录
- [ ] `GET /api/auth/me` 无 token → 401，有效 token → 返回用户信息
- [ ] 所有用户相关响应中**均不含** `password_hash`
- [ ] 数据库中密码字段为 bcrypt 哈希，不等于明文
- [ ] 非 admin 访问 `/api/users*` 一律 403
- [ ] admin 无法修改自己的角色或启用状态
- [ ] 角色变更**立即生效**，无需重新登录
- [ ] `scope_owner_id(admin)` 返回 `None`、`scope_owner_id(hr)` 返回 `user.id`
- [ ] seed 脚本幂等
- [ ] 全部 auth / deps 测试通过

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| 角色放 JWT 还是每次查库 | 每次查库 | 权限变更立即生效；代价是每请求一次主键查询，可接受 |
| 「先查重再插入」的并发竞态 | 依赖唯一索引 + 捕获 IntegrityError | 唯一索引是最终防线，查重只为友好报错 |
| 用户不存在时响应时间差异（时序攻击） | MVP 标记为**可选加固** | 内网 HR 系统风险低；如加固则补 dummy 哈希比对 |
| 是否物理删除用户 | 不删，只 `is_active=False` | 避免 `created_by` 外键悬空 |
| 用户列表是否分页 | 不分页 | 内部系统用户量小，YAGNI |
| `is_active` 字段不在 PRD 显式列出 | 补齐 | PRD 的 `PATCH /users/{id}` 要求「禁用」，无此字段则无法实现 |
