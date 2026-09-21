# auth 模块执行计划书（MVP-2 候选人侧）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：auth（candidate 角色、候选人注册、多角色权限守卫基座）
**所属包**：`backend/app/auth/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.1（角色与权限守卫收紧）、§4.6（面试者账号与权限）、§5.2（`user` 实体）、§8（auth API）、§9（安全）
**前置依赖**：core（[module-00](./2026-09-15-module-00-core-plan.md)）、auth MVP-1（[module-01](./2026-09-15-module-01-auth-plan.md)）
**本模块被谁依赖**：[module-12 interview](./2026-09-20-module-12-interview-invitation-plan.md)（凭邀请创建候选人账号）、[module-13 practice](./2026-09-20-module-13-practice-plan.md)、[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)、[module-16 权限守卫补全](./2026-09-20-module-16-permission-guard-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- 角色三种：**`admin` / `hr` / `candidate`**（§4.1）
- 候选人账号两种来源：**邀请码激活**（绑定面试）与**自助注册**（仅刷题），后者由配置项 `CANDIDATE_SELF_REGISTER` 控制，**默认开启**（§4.1）
- **普通 HR 不可自行注册**（§4.1）——本次新增的自助注册**只产出 candidate 角色**，不改变该约束
- 数据隔离：**candidate 只能访问自己的 `practice_*` 数据，以及自己被邀请且已接受的面试**（§4.1、§4.6）
- **权限守卫收紧**：HR 侧路由显式校验角色（admin/hr），候选人侧路由校验 candidate；**权限工具需支持多角色判定**（§4.1）
- 统一响应格式 **`{code, message, detail}`**（§7）
- 安全：**密码哈希存储、JWT 过期、参数校验防注入**（§9）
- 统一前缀 `/api`，**除登录与候选人自助注册外均需 JWT**（§8）
- **仍是单机 PC 端，技术栈不做任何变更**（§2）
- 候选人不得查看逐题分、维度分与雷达图（§1.3、§4.9）——本模块不涉及，但候选人角色的引入不得削弱该约束

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.1、§4.6）

| 子职责 | 内容 | PRD |
|---|---|---|
| 角色扩展 | `user.role` 枚举增加 `candidate`，并提供对应迁移 | §4.1、§5.2 |
| 候选人注册 | 公开的自助注册端点，**只创建 candidate 角色账号** | §4.1、§4.6 |
| 凭邀请建号 | 供 `interview` 调用的「按邀请创建/复用候选人账号」service 入口 | §4.1、§4.8 |
| **多角色守卫基座** | 在 `core.deps` 增加支持多角色判定的依赖工厂，作为全项目守卫收紧的地基 | §4.1 |
| 配置项 | 新增自助注册开关 | §4.1 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **邀请码实体本身**（`interview_invitation` 表、接受/撤销端点） | PRD §5.2 把该表归入 `interview` 包。本模块只提供「凭邀请建号」这一**被调用**能力，不持有邀请数据，从而避免 `auth ↔ interview` 双向依赖 |
| **候选人资料**（姓名、手机号、简历、头像） | PRD §1.3 明确不做简历上传与解析；候选人的业务身份已由 `interview.candidate_name` 承载 |
| **admin 创建 candidate** | PRD §4.1 只允许 admin 指定 `admin`/`hr`。候选人账号必须来自「自助注册」或「凭邀请激活」，保证每个候选人账号都与刷题或某场面试有真实关联 |
| **候选人数据隔离的判据实现** | 「是否持有该面试的有效邀请」这一判据由 `interview` 模块实现（数据在它那里）。auth 只保证**候选人不会被当作 HR 处理** |
| 找回密码 / 改密码 / Refresh Token | 同 module-01 §1.2，PRD 未要求 |
| 候选人社交能力（排行榜、积分、成就） | PRD §1.3 明确不做 |

### 1.3 依赖方向

```
auth.router ──→ auth.service ──→ auth.repository ──→ user 表
                    │
                    └──→ core.security / core.exceptions

auth ──→ core（单向）
interview ──→ auth.service（凭邀请建号；interview 本就依赖 auth）
core ✗→ auth（get_current_user 内延迟导入 User，见 module-00 §1.3）
auth ✗→ interview / practice（本模块不得反向依赖任何业务模块）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/auth/models.py` | **改**：新增 `ROLE_CANDIDATE` 并扩展 `role` 枚举 |
| `backend/app/auth/schemas.py` | **改**：新增 `AnyRoleLiteral` 与 `CandidateRegisterRequest` |
| `backend/app/auth/service.py` | **改**：新增 `register_candidate`、`create_candidate_account` |
| `backend/app/auth/router.py` | **改**：新增 `POST /auth/register` |
| `backend/app/auth/repository.py` | **不改**：`get_by_username` / `create` 已够用 |

**测试文件**：新增 `backend/tests/test_auth_candidate.py`；`backend/tests/test_deps.py` 增补多角色守卫用例

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/core/deps.py` | 新增 `require_roles(*roles)`；把 `require_role` 改为它的薄封装 |
| `backend/app/core/config.py` | 新增配置项 `candidate_self_register: bool = True` |
| `backend/.env.example` | 补 `CANDIDATE_SELF_REGISTER=true` |
| `backend/alembic/versions/` | 新增迁移：扩展 `user_role` 枚举 |
| `backend/script.sql` | 同步 `role` 列定义（与 Alembic 保持一致，见 module-00 §4） |
| `backend/tests/conftest.py` | 新增 `candidate_user` / `candidate_headers` 夹具（供 module-12/13/15/16 复用） |
| `backend/app/main.py` | **不改**：auth router 已注册，新端点随 router 自动生效 |

---

## 3. 数据模型设计

### 3.1 表 `user` 的角色枚举扩展（对应 PRD §5.2）

沿用 module-01 §3.1 的 `user` 表，**只改 `role` 列的枚举取值**：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `role` | ENUM('admin','hr',**'candidate'**) | NOT NULL, DEFAULT `'hr'` | 新增第三个取值 |

**不新增任何字段、不新增任何表。**

### 3.2 设计要点

| 要点 | 理由 |
|---|---|
| **候选人 = 一种角色，而非独立表** | 登录、JWT 签发、`is_active` 禁用、`username` 唯一性全部可复用现有实现。若另建 `candidate` 表，`auth` 会出现**两套登录路径**与两套凭据存储，且 `core.deps.get_current_user` 需按身份分派，复杂度远超收益 |
| **`username` 命名空间三种角色共享** | 沿用现有唯一索引。候选人与 HR 不能同名——这是可接受的约束（单机内部系统），且换来「登录只需一个用户名」 |
| **`role` 默认值仍为 `hr`** | 现存索引与 `server_default` 不变，迁移只需扩展枚举取值，风险最小 |
| **`scope_owner_id` 本次不改语义** | 它对「非 admin 一律返回 `user.id`」的现状会把 candidate 也纳入 owner 分支。该缺陷的修复属**守卫职责**，统一在 [module-16](./2026-09-20-module-16-permission-guard-plan.md) 处理，不在此处打补丁——避免同一规则两处实现 |

### 3.3 迁移设计（Alembic，**本模块风险最高的改动**）

| 步 | 操作 |
|---|---|
| 1 | `op.alter_column('user','role', existing_type=Enum('admin','hr',name='user_role'), type_=Enum('admin','hr','candidate',name='user_role'), existing_nullable=False, existing_server_default='hr')` |
| 2 | 同步更新 `backend/script.sql` 中 `user.role` 的列定义 |

**`downgrade()` 必须显式失败而非静默丢数据**：

| 情况 | 行为 |
|---|---|
| 库中不存在 `role='candidate'` 的行 | 正常执行反向 `alter_column`，收回枚举取值 |
| 库中存在 candidate 行 | **抛错终止**（`RuntimeError`），提示先处理候选人账号；不得静默删除用户或改写其角色 |

> **为何要这条保护**：MySQL 收回 ENUM 取值时，存量值会被写入为**空字符串或截断值**——这是静默的数据损坏。显式失败优于静默损坏（与 module-01 §10「初始 admin 不放迁移」同一取舍原则）。候选人账号可能已绑定邀请（`interview_invitation.candidate_user_id`），删号会造成链接悬空。

---

## 4. 接口契约

### 4.1 对外 REST API（对应 PRD §8）

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/auth/register` | **新增**：候选人自助注册（仅刷题） | **公开** | 201 |
| POST | `/api/auth/login` | 登录（三种角色共用） | 公开 | 200 |
| GET | `/api/auth/me` | 当前用户信息 | 登录 | 200 |
| POST/GET/PATCH | `/api/users*` | 用户管理（**仅 admin，且只可指派 admin/hr**） | admin | 不变 |

### 4.2 请求 / 响应结构

**POST `/api/auth/register`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `username` | str | 必填，1–50 字符，全局唯一 |
| 请求 | `password` | str | 必填，**最少 8 字符**，最多 128 |
| 响应 | user 对象 | — | `id` / `username` / `role`(=`candidate`) / `is_active` / `created_at`，**不含 `password_hash`** |
| 响应 | **不含 `token`** | — | 见 §5.1 |

**`role` 的输出取值**：`GET /auth/me` 与 `POST /auth/login` 的 `user.role` 现在可能返回 `candidate`。schema 层区分两个字面量类型：

| 类型 | 取值 | 用途 |
|---|---|---|
| `RoleLiteral`（**保持不变**） | `Literal["admin","hr"]` | `UserCreate` / `UserUpdate` 的可**指派**角色 |
| `AnyRoleLiteral`（**新增**） | `Literal["admin","hr","candidate"]` | 文档与类型标注；`UserOut.role` 现为 `str`，**不改**，避免影响既有响应契约 |

> **为何 `UserOut.role` 不收紧为字面量**：它是既有对外契约（461 条用例已覆盖），收紧会改变响应校验行为。`AnyRoleLiteral` 只用于明确「存在第三个角色」这一事实。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `register_candidate(db, username: str, password: str) -> User` | User | **校验自助注册开关** → 校验唯一 → 哈希 → 落库（`role=candidate`） |
| `create_candidate_account(db, username: str, password: str) -> User` | User | **不校验开关**；供 `interview` 凭邀请建号用（§5.2） |

沿用（不改）：`login`、`get_user_by_id`、`create_user`、`list_users`、`update_user`、`scope_owner_id`。

新增 service 内部常量：`ROLE_CANDIDATE = "candidate"`（与 `models.ROLE_ADMIN` / `ROLE_HR` 同处定义）。

### 4.4 repository 层方法签名

**不改**：`get_by_username(db, username)` 与 `create(db, username, password_hash, role)` 已满足两个新 service 方法的需要。

### 4.5 需在 `core.deps` 补齐的依赖

| 依赖签名 | 行为 |
|---|---|
| `require_roles(*roles: str) -> Callable[..., User]` | **新增**。依赖工厂；`user.role not in roles` → `ForbiddenError`（403） |
| `require_role(role: str) -> Callable[..., User]` | **改为薄封装**：`return require_roles(role)`。既有调用点（`auth/router.py` 的三处 admin 守卫）行为不变 |

**`require_roles` 的使用约定（全项目统一，module-16 逐路由落地）**

| 端点归属 | 守卫写法 |
|---|---|
| HR 侧（position / question / interview / evaluation） | `Depends(require_roles("admin", "hr"))` |
| 候选人侧（candidate / practice） | `Depends(require_roles("candidate"))` |
| 仅 admin（`/users*`） | `Depends(require_role("admin"))` 或 `require_roles("admin")` |

> **`admin` 不自动通过候选人侧守卫**：候选人是**终端用户**角色，admin 无正当理由代其刷题或作答。与 HR 侧不同（admin 在 HR 侧本就该通行），候选人侧必须**精确匹配**，否则 admin 一旦调用就会污染候选人的练习数据与作答归属。

### 4.6 需在 `core.config` 新增的配置项

| 配置键 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `CANDIDATE_SELF_REGISTER` | bool | 否 | `True` | 候选人自助注册开关（§4.1）。关闭后候选人只能凭邀请码建号 |

`.env.example` 必须补该键。

---

## 5. 业务流程设计

### 5.1 候选人自助注册流程

```
1. 读配置 CANDIDATE_SELF_REGISTER；为 False → BusinessError（409）「候选人自助注册已关闭」
2. schemas 层校验 username 1–50、password ≥ 8
3. service 查 username 是否被占用（三种角色共用命名空间）
   → 已占用 → BusinessError（409）「用户名已被占用」   ← 不区分占用者角色
4. bcrypt 哈希密码
5. 落库 role='candidate'；并发唯一索引冲突 → 捕获 IntegrityError → 转 BusinessError
6. 返回用户信息（剥离 password_hash）
```

| 设计决策 | 说明 |
|---|---|
| **注册成功的响应不发 token** | 注册与登录是两个动作。否则「签发 token」会有两条路径（`login` 与 `register`），JWT 载荷与有效期逻辑出现第二处实现。前端在注册成功后自动调用 `/auth/login`，用户无感知 |
| **用户名占用不区分角色** | 若回答「该用户名是 HR 账号」，等于提供了一个账号角色探测接口。统一文案「用户名已被占用」 |
| **不校验 `is_active`** | 注册产生的是全新账号，不存在禁用状态 |

### 5.2 凭邀请创建 / 复用候选人账号（供 interview 调用，对应 PRD §4.8）

`interview` 在接受邀请码时调用 `auth.service.create_candidate_account`。该方法的语义与开关无关，但**必须守住三条规则**：

```
1. 按 username 查用户
2. 不存在            → 创建 role='candidate' 的新账号，返回
3. 存在且 role='candidate'  → **校验 password 是否一致**：
                            一致 → 复用该账号并返回（不报错、不改密码）
                            不符 → UnauthorizedError（401）「用户名或密码错误」
4. 存在且 role 为 admin/hr → BusinessError（409）「用户名已被占用」
                               ← 绝不允许把 HR / admin 账号绑定到候选人邀请上
```

| 规则 | 为何必要 |
|---|---|
| 第 3 步复用而非报错 | 候选人可能已自助注册了刷题账号，再用邀请码时不应被迫换用户名 |
| **第 3 步必须校验密码**（2026-09-21 修正） | 原先「直接复用、不看密码」等于**知道对方用户名就能把自己的邀请码绑到对方账号上**，进而进入对方的面试。加上密码校验后，「不能重置他人密码」与「不能绑他人账号」两个风险一起消掉 |
| 第 3 步密码不符返回 **401** | 用与登录失败**完全相同**的文案「用户名或密码错误」，不新增可区分的信号。残余的「该用户名是否存在」可探测性只对**持有有效邀请码**的人成立，而邀请码一次性、高熵、私发，无法规模化（PRD §7） |
| 第 4 步硬拒绝 | 若允许，HR 账号会被写进 `interview_invitation.candidate_user_id`，从而获得候选人才有的「查看脱敏反馈」通道，且身份语义自相矛盾——这是**越权入口** |
| 不校验 `CANDIDATE_SELF_REGISTER` | 该开关控制的是「开放注册」，不是「凭邀请建号」。关闭自助注册后，邀请码仍是候选人的唯一入口，必须可用 |
| 密码由调用方传入 | 由 `interview` 的接受邀请端点决定（候选人在该请求中提交 username + password）。**账号已存在时它的角色是「身份凭据」而不是「新密码」** —— 这正是上面那条校验的含义 |

### 5.3 多角色守卫语义（`require_roles`）

```
require_roles(*roles):
  返回依赖函数 _dep(user = Depends(get_current_user)):
      user.role not in roles → ForbiddenError（403）「无权限执行此操作」
      否则返回 user
```

| 要点 | 说明 |
|---|---|
| **精确匹配，不做层级包含** | 不存在「admin 包含 hr」的隐式规则。HR 侧路由必须显式写 `require_roles("admin","hr")`。理由：隐式层级会在新增角色时产生难以预期的放行，显式列出是最容易评审的形式 |
| **角色仍每次查库** | 沿用 module-00 §5.2「JWT 载荷不放角色」，守卫判定的是当次请求读出的最新角色。管理员改角色**立即生效**，已有测试 `test_role_change_takes_effect_immediately` 覆盖该行为 |
| **`require_role` 保留** | 既有三处 admin 守卫不动，降低本次改动面 |

### 5.4 数据隔离的边界声明（本模块提供什么、不提供什么）

| 项 | 归属 |
|---|---|
| 「当前用户是谁」「角色是什么」 | auth（`get_current_user`） |
| 「HR 可见范围 = 自己创建的」 | auth（`scope_owner_id`，module-01 §5.3） |
| **「候选人可见范围 = 自己已接受的邀请所对应面试」** | **interview 模块实现**（数据在 `interview_invitation`） |
| 「候选人不会被当作 HR 处理」 | auth（多角色守卫，module-16 逐路由落地） |

> 候选人隔离判据**不能**复用 `created_by`：候选人不是面试的创建者（`interview.created_by` 是 HR），按 `created_by` 过滤会让候选人看不到任何自己的面试。因此候选人的可见性必须有独立判据，这是 PRD §4.1「不能复用 `created_by` 判据」的直接含义。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 自助注册已关闭 | `BUSINESS_ERROR` | 409 | 候选人自助注册已关闭，请使用邀请码激活 |
| 用户名已被占用（注册 / 凭邀请建号） | `BUSINESS_ERROR` | 409 | 用户名已被占用 |
| 密码长度不足 8 位 | `VALIDATION_ERROR` | 400 | 密码长度不能少于 8 位（`detail` 含字段名） |
| 用户名长度非法 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail` 含字段名） |
| 用 candidate token 调用 `/users*` | `FORBIDDEN` | 403 | 无权限执行此操作（既有行为，module-16 复查） |
| 角色不在 `require_roles` 允许集内 | `FORBIDDEN` | 403 | 无权限执行此操作 |

> **「自助注册已关闭」为何用 409 而非 403/404**：请求本身完全合法，拒绝的原因是**服务器配置不允许该业务动作**，属业务规则冲突。选 409 可以**不新增错误码**——全项目错误码表（module-00 §6.3）保持八个不变，这是它作为「收敛错误码」设计的价值。建议 `detail` 携带 `{"reason": "self_register_disabled"}` 便于前端区分。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `backend/tests/test_auth_candidate.py`（新增）

| 测试 | 断言 |
|---|---|
| `test_register_candidate_success` | 201，返回 user 且 `role == "candidate"`，**响应体无 `password_hash`** |
| `test_register_candidate_response_has_no_token` | 响应体**不含** `token` 字段（§5.1 决策） |
| `test_register_candidate_password_hashed` | 库中 `password_hash` ≠ 明文且以 bcrypt 前缀开头 |
| `test_register_candidate_duplicate_username` | 409 `BUSINESS_ERROR`，message 为「用户名已被占用」 |
| `test_register_candidate_username_taken_by_hr_same_message` | 占用者是 HR 时，**错误码与文案与占用者是候选人时完全一致**（不泄露角色） |
| `test_register_candidate_short_password` | 400 `VALIDATION_ERROR`，`detail.fields` 含 `password` |
| `test_register_candidate_disabled_by_config` | `CANDIDATE_SELF_REGISTER=false` 时 → 409 `BUSINESS_ERROR`，`detail.reason == "self_register_disabled"` |
| `test_register_candidate_does_not_create_hr` | 请求体无论传什么，落库 `role` 恒为 `candidate`（**请求体不接受 `role` 字段**） |
| `test_candidate_can_login` | 注册后可用该凭据登录，返回 token 且 `user.role == "candidate"` |
| `test_candidate_can_call_me` | 用 candidate token 调 `/auth/me` → 200，返回自身信息 |
| `test_candidate_cannot_call_users` | 用 candidate token 调 `GET /users` → 403 `FORBIDDEN` |
| `test_create_candidate_account_new` | service 直调：新用户名 → 创建 `role=candidate` |
| `test_create_candidate_account_reuses_candidate` | 已存在 candidate 且**密码一致** → **返回同一账号**，不报错、不新建、密码不变 |
| `test_create_candidate_account_rejects_wrong_password` | 已存在 candidate 但**密码不符** → 401 `UNAUTHORIZED`「用户名或密码错误」（§5.2 第 3 步，2026-09-21 新增） |
| `test_create_candidate_account_rejects_hr` | 已存在 hr（或 admin）同名账号 → 409 `BUSINESS_ERROR`（§5.2 第 4 步） |
| `test_create_candidate_account_ignores_self_register_flag` | 开关关闭时仍可凭邀请建号（§5.2） |
| `test_admin_cannot_assign_candidate_role` | `POST /users` 传 `role="candidate"` → 400 `VALIDATION_ERROR`（`RoleLiteral` 不含 candidate） |
| `test_admin_cannot_patch_to_candidate` | `PATCH /users/{id}` 传 `role="candidate"` → 400 |

### 7.2 `backend/tests/test_deps.py`（增补）

| 测试 | 断言 |
|---|---|
| `test_require_roles_single_pass` | 角色在允许集内 → 放行 |
| `test_require_roles_multi_pass_admin` | `require_roles("admin","hr")` + admin 用户 → 放行 |
| `test_require_roles_multi_pass_hr` | `require_roles("admin","hr")` + hr 用户 → 放行 |
| `test_require_roles_reject_candidate_on_hr_guard` | candidate 用户 → 403 `FORBIDDEN` |
| `test_require_roles_reject_admin_on_candidate_guard` | `require_roles("candidate")` + admin 用户 → **403**（§4.5 的精确匹配规则） |
| `test_require_roles_reject_hr_on_candidate_guard` | hr 用户 → 403 |
| `test_require_role_still_equals_require_roles` | `require_role("admin")` 与 `require_roles("admin")` 行为一致（薄封装未走样） |
| `test_require_roles_requires_auth` | 无 token → 401 `UNAUTHORIZED`（守卫不绕过登录校验） |

### 7.3 `backend/tests/conftest.py`（增补夹具）

| 夹具 | 说明 |
|---|---|
| `candidate_user` | 由 `service.register_candidate` 创建的标准候选人账号 |
| `candidate_headers` | 该用户的 `Authorization` 头 |

> 这两个夹具是 module-12 / module-13 / module-16 测试的公共前置，必须在本模块落地。

### 7.4 迁移测试

| 测试 | 断言 |
|---|---|
| `test_role_enum_includes_candidate` | 迁移后 `user.role` 可写入 `"candidate"` |
| `test_downgrade_protected_when_candidate_exists` | 存在 candidate 行时执行 `downgrade()` → **抛错**，且该行数据未被改写（§3.3） |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 9.1：角色枚举与迁移

- [ ] `models.py` 新增 `ROLE_CANDIDATE`，扩展 `role` 枚举
- [ ] 生成迁移（§3.3 步 1），实现带保护的 `downgrade()`
- [ ] 同步 `backend/script.sql` 中 `user.role` 列定义
- [ ] 写 §7.4 两条迁移测试
- [ ] 运行 `alembic upgrade head` 与 `downgrade` 验证
- [ ] 提交

### Task 9.2：配置项与开关

- [ ] `core/config.py` 新增 `candidate_self_register`
- [ ] `.env.example` 补键
- [ ] 写失败测试：`get_settings().candidate_self_register` 默认为 `True`，可由环境变量覆盖为 `False`
- [ ] 运行确认通过
- [ ] 提交

### Task 9.3：多角色守卫（`core.deps`）

- [ ] 写 §7.2 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `require_roles`，并把 `require_role` 改为薄封装
- [ ] 运行确认通过；跑 `test_auth.py` 确认既有 admin 守卫未回归
- [ ] 提交

### Task 9.4：schema 定义

- [ ] 新增 `AnyRoleLiteral`、`CandidateRegisterRequest`
- [ ] 写失败测试：`CandidateRegisterRequest` **不接收** `role` 字段；`UserCreate` 传 `candidate` 报 400
- [ ] 运行确认通过
- [ ] 提交

### Task 9.5：候选人注册

- [ ] 写 §7.1 中 `test_register_*` 与 `test_candidate_*` 失败测试
- [ ] 运行确认失败
- [ ] 实现 `service.register_candidate` 与 `POST /auth/register`
- [ ] 运行确认通过
- [ ] 提交

### Task 9.6：凭邀请建号

- [ ] 写 `test_create_candidate_account_*` 四条失败测试（**含拒绝 hr 同名**）
- [ ] 运行确认失败
- [ ] 实现 `service.create_candidate_account`
- [ ] 运行确认通过
- [ ] 提交

### Task 9.7：测试夹具与全量回归

- [ ] `conftest.py` 新增 `candidate_user` / `candidate_headers`
- [ ] 运行 `pytest tests/ -q`，**461 条既有用例全部通过**（重点看 `test_auth.py`、`test_deps.py`、`test_architecture.py`）
- [ ] 提交

---

## 9. 验收标准

- [ ] `user.role` 枚举含 `candidate`，迁移可升降级；**有候选人数据时降级会显式报错**
- [ ] `POST /api/auth/register` 公开可访问，只创建 candidate 账号，响应**不含 token**、**不含 `password_hash`**
- [ ] `CANDIDATE_SELF_REGISTER=false` 时注册返回 409 且 `detail.reason == "self_register_disabled"`；但凭邀请建号仍可用
- [ ] 用户名占用（无论占用者角色）返回**同一**错误码与文案
- [ ] 凭邀请建号遇到同名 hr/admin 账号时**拒绝**，不会把 HR 账号绑到候选人邀请上
- [ ] `require_roles("admin","hr")` 放行 admin 与 hr、拒绝 candidate；`require_roles("candidate")` **拒绝 admin 与 hr**
- [ ] `require_role` 行为与改动前完全一致
- [ ] admin 无法通过 `/users` 创建或改成 candidate 角色
- [ ] candidate 调用 `/users*` 一律 403
- [ ] `conftest.py` 提供 `candidate_user` / `candidate_headers`
- [ ] 既有 461 条用例**零回归**，新增 auth 与 deps 用例全部通过

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **MySQL ENUM 收回取值会静默损坏数据** | `downgrade()` 检测到 candidate 行即抛错 | 静默把 `role` 写成空串是最糟的结果；候选人账号还挂着邀请外键 |
| **自助注册默认开启** | 默认 `True` | 本项目交付定位是**可开箱演示**（离线 Mock 也能跑通刷题闭环）。生产部署应置为 `false` 并只走邀请码——写入 README 的部署说明（module-16 §7 收尾项） |
| 候选人角色落入 `scope_owner_id` 的 owner 分支 | 本次不打补丁，统一在 module-16 修 | 避免同一隔离规则两处实现、两处漂移 |
| 三角色共享 `username` 命名空间 | 接受 | 单机内部系统；换得「一个用户名登录三种角色」的简单模型 |
| `AnyRoleLiteral` 与 `RoleLiteral` 并存 | 接受 | `UserOut.role` 是既有对外契约，不因新增角色而改变其校验行为 |
| 给 `AIProvider` 增方法是否会影响本模块 | 无 | 本模块不触及 `ai`；新增 AI 方法见 [module-11](./2026-09-20-module-11-ai-plan.md) |
| 注册与登录分成两步 | 接受一次额外请求 | 避免 JWT 签发出现第二条实现路径；前端在注册成功后自动登录，用户无感知 |
