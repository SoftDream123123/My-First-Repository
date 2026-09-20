# resume 模块执行计划书（MVP-3 简历）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：resume（候选人侧纯文本简历的增删改查）—— **MVP-3 新增的第九个 package**
**所属包**：`backend/app/resume/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.10（简历管理）、§5.2（`resume` 表）、§7（简历相关错误）、§8（候选人侧 resume 端点）、§9（简历的跨端流不破坏分层）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md)、[module-16 权限守卫](./2026-09-20-module-16-permission-guard-plan.md)
**本模块被谁依赖**：[module-19 interview 简历关联与补题](./2026-09-21-module-19-interview-plan.md)、[module-20 practice 按简历推荐](./2026-09-21-module-20-practice-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- 简历**只支持粘贴纯文本**，**不做文件上传与格式解析**（§1.3、§4.10）
- **写入方只有候选人**：`created_by` 恒为候选人用户 id；**HR 不提供简历 CRUD**（§4.10）
- HR 的读取权限**不在本模块判定**，由 `interview` 按邀请链判定；本模块只提供无权限过滤的数据读取（§4.10、§9）
- 数据隔离：候选人只能读写**自己的**简历（`created_by` 判据）（§4.10）
- 简历正文长度上限 **20000 字符**（§4.10）
- 删除简历时若**已被面试或练习关联** → 拒绝（409）（§4.10、§7）
- 简历**不绑定**某场面试或某次练习：同一份简历可被多场面试、多次练习复用（§4.10、§5.2）
- **`resume` 不依赖任何业务模块**；`interview` 与 `practice` 各自**单向依赖**它（§3.3、§9）
- 路由守卫 `require_roles("candidate")`；**admin 与 hr 在候选人侧不通行**（§4.1、[module-09 §4.5](./2026-09-20-module-09-auth-plan.md)）
- 简历**编辑后不影响已补的题**——题目内容与匹配理由已快照在 `interview_question` 中（§5.2）
- **仍是单机 PC 端，技术栈不变、不引入新依赖**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.10）

| 子职责 | 内容 | PRD |
|---|---|---|
| 简历录入 | 候选人粘贴纯文本创建简历（标题 + 正文 + 可选姓名/联系方式） | §4.10 |
| 简历维护 | 查看列表 / 查看详情 / 更新 / 删除 | §4.10 |
| 归属隔离 | 只能读写自己的简历（`created_by`） | §4.10 |
| 被引用保护 | 删除前由外键 `RESTRICT` 拒绝被关联的简历 | §4.10 |
| 跨包供给 | 向 `interview` / `practice` 提供**无权限过滤**的简历读取 | §9 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **HR 侧简历 CRUD** | PRD §4.10 明确「HR 不提供简历 CRUD」。HR 只读，且读的是「与某场自己名下面试关联」的简历（由 module-19 提供端点） |
| **文件上传与解析（PDF / DOCX）** | PRD §1.3 明确不做。因此本模块**不引入任何解析库**，也**不存在解析失败分支**——`content` 完全来自用户粘贴 |
| **简历与面试 / 练习的关联动作** | 关联是 `interview.resume_id` 的写入，属 `interview`（module-19 §5.x）。PRD §9 明确「判据由 `interview` 实现」 |
| **按简历匹配题目 / 推荐题目** | 属 `interview`（补题）与 `practice`（推荐），本模块只提供文本 |
| **简历的结构化解析**（技能、年限、项目经历等字段） | PRD §4.10 未要求；本模块只存整段纯文本 |
| **简历版本历史** | 只保留最新内容（`updated_at` 记录最后修改时刻）。PRD 未要求版本化 |
| **简历分享 / 导出** | PRD §1.3 明确不做报告分享；简历导出未被要求 |
| **HR 主动「索要」简历的通知** | PRD §1.3 明确不做邮件 / 通知 |

### 1.3 依赖方向

```
resume.router ──→ resume.service ──→ resume.repository ──→ resume 表

resume ──→ core / auth（单向）
resume ✗→ interview / practice / position / question / evaluation
```

```
interview ──→ resume   （HR 读简历 + 候选人关联简历）
practice  ──→ resume   （按简历推荐取题）
resume    ✗→ interview / practice
```

> **本模块是 MVP-3 里唯一「被依赖但不依赖」的节点。** `interview` 与 `practice` 各自单向依赖它，因此**不会引入 `practice ↔ interview` 循环**——这正是 PRD §9 要求的分层不变量，也是为什么简历**不能**挂在 `interview` 或 `practice` 任一端。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/resume/__init__.py` | 包标识 |
| `backend/app/resume/models.py` | `Resume` 模型 |
| `backend/app/resume/schemas.py` | 请求 / 响应模型 |
| `backend/app/resume/repository.py` | 纯 CRUD（含删除的 `IntegrityError` 转译） |
| `backend/app/resume/service.py` | 归属校验、长度校验、跨包供给契约 |
| `backend/app/resume/router.py` | `/api/candidate/resumes/*` **五个端点**（守卫 `candidate`） |

**测试文件**：`backend/tests/test_resume.py`（service 与 repository）、`backend/tests/test_resume_router.py`（端点、鉴权、隔离）

> **只有 `router.py` 一个路由文件**：本模块无 HR 侧端点，因此不需要 `candidate_router.py`。与 `practice` 同理——「候选人专属模块的单 router」是既有形态（`practice/router.py` 的 `prefix="/practice"`），本模块的 `router.py` 的 `prefix` 取 PRD §8 规定的 `/candidate/resumes`。

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/app/main.py` | 注册 resume router（前缀 `/api`），**放在 `interview` 之前** | 路由注册顺序按依赖方向；`resume` 被 `interview` 依赖 |
| **`backend/tests/test_architecture.py`** | 把 `resume` 登记进 `ALL_MODULES` / `BUSINESS_MODULES` / `LAYERED_MODULES` / `FORBIDDEN_DEPENDENCIES`；**`test_eight_modules_exist` 改名并改为九模块断言** | ⚠️ 该文件的模块名列表是**硬编码**的。不登记则本包的分层与依赖方向**不受任何测试保护**（见 §7.5） |
| `backend/tests/conftest.py` | 新增 `resume` 夹具 | 供 module-19 / module-20 / E2E 复用 |
| `backend/app/core/config.py` | 新增 `RESUME_CONTENT_MAX_LENGTH` | §3.3 |

> **不写 alembic 迁移、不同步 `backend/script.sql`**：与 MVP-2 一致，本批次**只改模型**，建表由你统一收口（PRD §11）。

---

## 3. 数据模型设计

### 3.1 表 `resume`（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 | 来源 |
|---|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 | PRD §5.2 |
| `title` | VARCHAR(100) | NOT NULL | 简历标题（如「张三-后端开发」），列表按它区分多份简历 | PRD §5.2 |
| `content` | TEXT | NOT NULL | 简历正文（纯文本），≤ 20000 字符 | PRD §5.2 |
| `candidate_name` | VARCHAR(100) | NULL | 可选；类型与 `interview.candidate_name` 对齐 | PRD §5.2 |
| `candidate_contact` | VARCHAR(200) | NULL | 可选；类型与 `interview.candidate_contact` 对齐 | PRD §5.2 |
| `created_by` | BIGINT | NOT NULL, FK → `user.id` **RESTRICT**, INDEX | **归属，数据隔离依据。恒为候选人 user id** | PRD §5.2 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — | PRD §5.2 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT NOW, **ON UPDATE NOW** | 最后修改时刻 | PRD §5.2 |

**索引**：`ix_resume_created_by`（`created_by`，服务列表查询）

**关键设计说明**

| 决策 | 理由 |
|---|---|
| **不加 `(created_by, title)` 唯一约束** | `position` 有 `uq_position_owner_name`，但简历**刻意不加**：候选人保留两份都叫「通用简历」的简历是无害的，而唯一约束会把这种正当用法变成 409。列表用 `id` 定位，重名不产生歧义 |
| **`content` 用 TEXT 而非 VARCHAR** | 20000 字符已超 MySQL `VARCHAR` 的实用上限（且行长度会顶到限制）。TEXT 无此问题，长度约束由 service 层与 schema 双层校验 |
| **`updated_at` 是本项目第一张带它的表** | 既有的 `position` / `interview` 等只记 `created_at`。简历是**唯一由用户反复编辑的自有内容**，且 PRD §4.13 明确「候选人可随时改简历，改后 HR 需重新触发补题」——HR 需要能判断手上这份是不是最新的。`ON UPDATE NOW` 由数据库保证，不依赖应用层记得写 |
| **`candidate_name` / `candidate_contact` 可空** | 简历正文里通常已含姓名与联系方式，结构字段只是**便于在列表里显示**的冗余。设 NOT NULL 会强迫候选人填两遍 |
| **`created_by` 用 `RESTRICT`** | 与全项目一致：用户不做物理删除（只置 `is_active=false`），因此该约束只是形式上的保护（§5.2 既有约定） |

### 3.2 与 `interview` / `practice_session` 的引用关系

| 引用方 | 字段 | 外键约束 | 后果 |
|---|---|---|---|
| `interview` | `resume_id`（NULL 允许） | → `resume.id` **RESTRICT** | 被面试关联的简历**不可删除** |
| `practice_session` | `resume_id`（NULL 允许） | → `resume.id` **RESTRICT** | 被练习关联的简历**不可删除** |

> **两个外键是「删除保护」的全部实现**，本模块不写任何跨表查询。这是既有模式：`position` 删除被引用时靠 `interview.position_id` 的 `RESTRICT` 拒绝（`position/repository.py` 的 `delete()` 捕获 `IntegrityError` → `BusinessError`），而不是去数 `interview` 表。
>
> **这样一来 `resume` 完全不需要感知 `interview` / `practice` 的存在**——依赖方向保持单向，架构约束可被测试钉住（§7.5）。

### 3.3 新增配置项

| 配置键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `RESUME_CONTENT_MAX_LENGTH` | int | `20000` | 简历正文长度上限（PRD §4.10）；超限 422 |

> **为何这一个进配置、而列表 `limit` 不进**：正文上限是**「打爆 AI 上下文」的护栏**，与模型上下文长度绑死，将来换模型可能需要调；列表 `limit` 是纯粹的接口卫生上限，直接由 schema 的 `Field(le=...)` 固定即可，不值得为此加一个配置键。

---

## 4. 接口契约

### 4.1 对外 REST API（守卫 `require_roles("candidate")`）

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| POST | `/api/candidate/resumes` | 新建我的简历 | 201 |
| GET | `/api/candidate/resumes` | 我的简历列表 | 200 |
| GET | `/api/candidate/resumes/{id}` | 简历详情（仅本人） | 200 |
| PUT | `/api/candidate/resumes/{id}` | 更新我的简历 | 200 |
| DELETE | `/api/candidate/resumes/{id}` | 删除我的简历（被关联则 409） | 204 |

> **路径与 `practice` 的形态差异**：`practice` 作为候选人专属模块，路径是 `/practice/*`（资源名即前缀）；`resume` 作为跨端共用资源，路径是 `/candidate/resumes/*`——因为将来若出现 HR 侧端点，它会是 `/resumes/*`（同 `question` 的 `/questions` 与 `/candidate/positions` 的对照关系）。**现在没有 HR 端点，但路径先按可加的形状留好**，避免日后改路径破坏前端。

### 4.2 请求 / 响应结构

**`ResumeOut`（候选人自己的视图）**

| 字段 | 下发 | 说明 |
|---|---|---|
| `id` | ✓ | — |
| `title` | ✓ | — |
| `content` | ✓ | 正文全文（详情与列表**都下发**） |
| `candidate_name` / `candidate_contact` | ✓ | 可能为 null |
| `created_at` / `updated_at` | ✓ | 前端显示「最后更新」 |
| `created_by` | **✗** | 候选人无需知道自己的 user id |

> **列表下发 `content` 全文**：候选人的简历是自己写的一段文本，不是长列表数据；简历数量个位数，因此「列表轻量化」在这里没有收益，反而会让编辑前的回显要多发一次请求。**这与 `practice` 会话列表刻意不下发题目明细的取舍相反**，因为那里的数据量是「会话数 × 题目数」，这里是「简历数 × 一段文本」。

**POST `/api/candidate/resumes`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `title` | str | 必填，1–100 字符（去首尾空白后非空） |
| 请求 | `content` | str | 必填，去首尾空白后 ≥ 1 字符，≤ `RESUME_CONTENT_MAX_LENGTH` |
| 请求 | `candidate_name` | str \| null | 可选，≤ 100 字符 |
| 请求 | `candidate_contact` | str \| null | 可选，≤ 200 字符 |
| 响应 | — | `ResumeOut` | — |

**GET `/api/candidate/resumes`** 查询参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `limit` | int \| 可选 | 缺省 50，上限 200（`Field(le=200)`） |

→ 返回 `ResumeOut` 数组，**按 `updated_at` 倒序**（最近改的最上面，与「继续编辑」的用途一致）。

**GET `/api/candidate/resumes/{id}`** → `ResumeOut`

**PUT `/api/candidate/resumes/{id}`**：请求体与 POST 同构，**但所有字段均可选**（部分更新语义）；未提供的字段保持不变。

> **为什么 PUT 用「部分更新」而不是整体替换**：前端「改个标题」不该要求把 20000 字的正文一起回传，否则一次改标题就是一次大请求。HTTP 语义上更贴 PATCH，但 PRD §8 已定 `PUT`——**以 PRD 为准，用 PUT 承载部分更新语义并在文档写明**，避免执行者自作主张改成 PATCH。

**DELETE `/api/candidate/resumes/{id}`** → 204（无响应体）；被关联时 409。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_resume(db, user, data: ResumeCreate) -> Resume` | 简历 | 长度校验 → 落库（§5.1） |
| `list_my_resumes(db, user, limit: int) -> list[Resume]` | 列表 | **只查本人**，按 `updated_at` 倒序（§5.2） |
| `get_my_resume(db, user, resume_id: int) -> Resume` | 简历 | 归属校验（§5.3） |
| `update_resume(db, user, resume_id: int, data: ResumeUpdate) -> Resume` | 简历 | 归属校验 → 部分更新（§5.3） |
| `delete_resume(db, user, resume_id: int) -> None` | — | 归属校验 → 删除（FK 拒绝被关联）（§5.4） |
| `load_unchecked(db, resume_id: int) -> Resume \| None` | 简历 \| None | **跨包供给：无权限过滤**（§4.5） |
| `ensure_mine(db, user, resume_id: int) -> Resume` | 简历 | **跨包供给：归属校验**（§4.5） |

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create(db, **fields) -> Resume` | 简历 | — |
| `get_by_id(db, resume_id: int) -> Resume \| None` | 简历 | **不带权限过滤** |
| `list_by_creator(db, creator_id: int, limit: int) -> list[Resume]` | 列表 | 按 `updated_at` 倒序 |
| `update(db, resume: Resume, **fields) -> Resume` | 简历 | — |
| `delete(db, resume: Resume) -> None` | — | `IntegrityError` → `BusinessError`（§5.4） |

> **`get_by_id` 不带权限过滤**，与既有 repository 约定一致（`position/repository.py`、module-03 §4.4「权限判定在 service」）。权限判定在 §5.3 的 service 层完成。

### 4.5 跨包供给契约（**本模块对外最重要的两个口子**）

`interview` 需要两件本模块的数据，二者**权限语义完全不同**，因此必须是**两个函数**：

| 函数 | 语义 | 调用方 | 为什么要分开 |
|---|---|---|---|
| `load_unchecked(db, resume_id) -> Resume \| None` | **纯读，不做任何权限判断**；不存在返回 `None` | `interview`（HR 读简历、HR 补题取文本） | HR 读的是**别人的**（候选人的）简历，用 `ensure_owner_match` 必然失败 |
| `ensure_mine(db, user, resume_id) -> Resume` | 不存在 → 404；非本人 → 403 | `interview`（候选人关联简历时校验「这份是我的」） | 候选人关联的必须是**自己的**简历 |

**为什么把这两个函数放在 `resume` 而不是让 `interview` 直接用 `resume.repository`**：

- `interview` 若直接 import `resume.repository`，就**跳过了 service 层**，破坏「router → service → repository」的分层约定——而现在**没有任何测试能拦住它**：`test_architecture.py` 的 `test_router_goes_through_service` 用的是 `_own_module_refs(path, module)`，只统计**同模块内部**的层引用。`interview/router.py` 顶层 `from app.resume import repository` 在它眼里只是「`interview` 依赖 `resume`」，完全合法。因此必须在 service 层立契约，并靠**代码评审 + 本节的显式约束**守住。
- 两个函数的**命名刻意不对称**：`load_unchecked` 带 `unchecked` 后缀，让「这里没有权限检查」在调用点一眼可见，避免有人误以为它安全；`ensure_mine` 反向，名字即保证。

> **关于 HR 的权限判据**：HR 能读某份简历，当且仅当「该简历关联到自己名下的某场面试」。这个判据**需要读 `interview` 表**，因此**只能由 `interview` 实现**（PRD §9 明确如此）。`resume` 提供 `load_unchecked` 把数据交出去，**不感知调用方身份**——这正是分层得以单向的原因。

---

## 5. 业务流程设计

### 5.1 创建简历

```
create_resume(db, user, data):
1. 规范化：title / content 去首尾空白
2. 校验 title 非空（去空白后）→ 否则 400
3. 校验 content 非空（去空白后）→ 否则 400
4. 校验 len(content) <= RESUME_CONTENT_MAX_LENGTH → 否则 422
5. repository.create(db, title, content, candidate_name, candidate_contact,
                     created_by=user.id)
6. commit；返回
```

| 要点 | 说明 |
|---|---|
| **`created_by` 由 service 从 `user.id` 取，绝不从请求体读** | 让客户端有机会指定归属是最常见的一类越权漏洞。请求体里**没有** `created_by` 字段（§4.2） |
| **长度校验在 service，且 422 而非 400** | PRD §7 明确「简历正文超长 → 422」。因此 Pydantic 层**不**用 `max_length`（那会被全局处理器收口成 400，见 `main.py` 的 `handle_validation_error`），而是在 service 抛 422 的业务异常 |
| **去首尾空白后判非空** | 一份只有空格的简历会让 AI 匹配与准备助手拿到空洞输入并产出无意义结果，属于「可预防的坏数据」 |

> **长度校验为什么必须绕过 Pydantic**：`main.py` 把 `RequestValidationError` 统一收口为 **400 `VALIDATION_ERROR`**。而 PRD §7 要求这个场景是 **422**。若用 `Field(max_length=20000)`，超长会被收口成 400，与 PRD 不符。因此长度上限放在 service 层用业务异常表达。**这是一处容易被执行者写错的地方**。

### 5.2 列表

```
list_my_resumes(db, user, limit):
1. 校验 limit <= 200 → 否则 400（由 schema 的 Field(le=200) 承担）
2. repository.list_by_creator(db, creator_id=user.id, limit)
3. 返回（按 updated_at 倒序）
```

| 要点 | 说明 |
|---|---|
| **只查本人**（`created_by = user.id`） | 隔离写在 SQL 条件里，不依赖「取回来再过滤」——后者一旦忘记过滤就会泄露他人简历 |
| 排序按 `updated_at` 倒序 | 最近编辑的最上面，贴合「继续改这份」的主用途 |
| 无简历时 | 返回空数组（不是 404）——「还没建过简历」是正常状态 |
| **不区分 admin** | 守卫是 `require_roles("candidate")`，admin 根本不通行（§4.1），因此不需要 `scope_owner_id` 那套 admin 放开逻辑 |

### 5.3 详情与更新

```
get_my_resume(db, user, resume_id):
1. resume = repository.get_by_id(db, resume_id)
2. 若 None → 404「简历不存在」
3. ensure_owner_match(user, resume.created_by, "简历")   ← auth 既有函数
4. 返回

update_resume(db, user, resume_id, data):
1. resume = get_my_resume(...)                  ← 复用上一步的校验
2. 若 data.content 非 None：校验长度上限（同 §5.1 第 4 步）
3. 对 data 中**非 None 的字段**逐个赋值（部分更新）
4. commit；返回
```

| 要点 | 说明 |
|---|---|
| **用 `ensure_owner_match` 而非 `ensure_resource_visible`** | 后者对 candidate 角色会直接抛 403（module-16 的纵深防御，见 [module-13 §4.5](./2026-09-20-module-13-practice-plan.md)），候选人连自己的简历都读不到 |
| **404 先于 403** | 与全项目一致（`position/service.py::_get_visible`）：资源不存在给 404，存在但无权给 403。**先查存在性再判权**，避免用 403/404 的差异探测他人资源是否存在——这里不构成泄露，因为简历 id 不可枚举且候选人只能看到自己的 |
| **`candidate_name` / `candidate_contact` 传 `null` 表示「清空」还是「不改」** | 采用**「不改」**：请求体字段缺省即为 `None`，`None` 一律视为「未提供」。因此**本接口无法清空这两个可选字段**。这是有意的取舍（§10）——想清空就填空串，二者在展示上等价 |

### 5.4 删除

```
delete_resume(db, user, resume_id):
1. resume = get_my_resume(...)
2. repository.delete(db, resume)
        db.delete(resume); commit()
        IntegrityError → rollback + BusinessError(409)「该简历已被面试或练习关联，无法删除」
```

| 要点 | 说明 |
|---|---|
| **不做「先数引用再决定」的预检** | 预检会引入「数完到删除之间被关联」的竞态，而数据库外键在任何时刻都是权威的。**一次捕获 `IntegrityError` 就够**，且与 `position/repository.py::delete` 完全同构 |
| **409 而非 400** | PRD §7 明确「删除已被面试或练习关联的简历 → 409（冲突）」。这是**状态冲突**（资源仍被引用），不是参数错误 |
| **不加 `ON DELETE CASCADE`** | 级联删除会静默抹掉面试的简历关联，让 HR 在不知情的情况下丢失资料。`RESTRICT` + 明确报错让候选人自己决定怎么处理 |
| 删除后 | 返回 204，前端从列表移除 |

### 5.5 简历更新与既有补题结果的关系（**跨模块一致性**）

| 事实 | 后果 |
|---|---|
| 简历被更新 | `interview.resume_id` **不变**；已补的题**不变** |
| 已补的题的题目内容与匹配理由 | 已快照在 `interview_question.content_snapshot` / `match_reason` 中，**不随简历变化** |
| 想让新简历生效 | HR 需**重新触发补题**（module-19 §5.x）；补题幂等，只会追加本场尚不存在的题 |

> **为什么不去「级联更新」已补的题**：那会让历史面试的题目随简历悄悄变化，与全项目「快照冻结历史」的取向相反（PRD §5.2 对 `answer` / `interview_question` 的一贯态度）。PRD §5.2 已写明「简历更新后不影响已补的题」。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 简历不存在 | `NOT_FOUND` | 404 | 简历不存在 |
| 简历不属于本人 | `FORBIDDEN` | 403 | 无权限访问该简历 |
| 新建 / 更新时 `title` 去空白后为空 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 新建 / 更新时 `content` 去空白后为空 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 简历正文超长 | `VALIDATION_ERROR` | **422** | 简历正文不能超过 20000 字符 |
| 删除已被面试或练习关联的简历 | `BUSINESS_ERROR` | 409 | 该简历已被面试或练习关联，无法删除 |
| 列表 `limit` 超上限 | `VALIDATION_ERROR` | 400 | `limit` 不能超过 200 |
| 守卫角色不符（hr / admin 调用） | `FORBIDDEN` | 403 | 无权限执行此操作（module-16） |
| 无 token | `UNAUTHORIZED` | 401 | 未登录或登录已过期 |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。
>
> **422 是本模块唯一的特例**：全项目的参数校验走 400 `VALIDATION_ERROR`，只有「正文超长」按 PRD §7 要求返回 **422**。执行者需注意这一处的刻意不一致（§5.1 已说明实现手法），并**在测试里显式断言 422**，防止后来者「统一」成 400。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 创建与校验

| 测试 | 断言 |
|---|---|
| `test_create_resume_persists_all_fields` | 标题 / 正文 / 姓名 / 联系方式与请求一致 |
| `test_create_resume_sets_created_by_from_token` | 请求体**不含** `created_by`；落库值为当前候选人 id |
| `test_create_resume_rejects_blank_title` | 纯空白标题 → 400 |
| `test_create_resume_rejects_blank_content` | 纯空白正文 → 400 |
| `test_create_resume_trims_whitespace` | 标题与正文两侧空白被去掉后落库 |
| `test_create_resume_content_at_limit_ok` | 正文长度 == `RESUME_CONTENT_MAX_LENGTH` → 201 |
| `test_create_resume_content_over_limit_422` | 正文长度 == 上限 + 1 → **422**（不是 400） |
| `test_create_resume_allows_duplicate_title` | 同一候选人建两份同名简历 → **都成功**（刻意不加唯一约束，§3.1） |
| `test_create_resume_optional_fields_nullable` | 不传姓名 / 联系方式 → 201，二者为 null |

### 7.2 列表

| 测试 | 断言 |
|---|---|
| `test_list_only_own_resumes` | 候选人 A 的列表**不含** B 的简历 |
| `test_list_ordered_by_updated_desc` | 先建 A 后建 B，更新 A → A 排在**最前** |
| `test_list_empty_returns_empty_array` | 无简历 → 200 且 `[]`（不是 404） |
| `test_list_limit_capped` | `limit=201` → 400，**不静默截断** |
| `test_list_response_excludes_created_by` | 响应中**不出现** `created_by` 键 |

### 7.3 详情、更新与归属

| 测试 | 断言 |
|---|---|
| `test_get_own_resume_ok` | 200，字段完整 |
| `test_get_missing_resume_404` | 不存在的 id → 404 |
| `test_get_other_candidates_resume_403` | 候选人 A 读 B 的简历 → 403 |
| `test_update_partial_title_only` | 只传 `title` → 正文**不变**，`title` 已改 |
| `test_update_partial_content_only` | 只传 `content` → 标题不变 |
| `test_update_bumps_updated_at` | 更新后 `updated_at > created_at` |
| `test_update_other_candidates_resume_403` | 403 |
| `test_update_content_over_limit_422` | 422 |
| `test_update_does_not_touch_created_by` | 请求体无法改写归属 |

### 7.4 删除与被引用保护

| 测试 | 断言 |
|---|---|
| `test_delete_unreferenced_ok` | 204，且库中已无该行 |
| `test_delete_referenced_by_interview_409` | 简历已被某面试 `resume_id` 关联 → **409**，**且行仍在** |
| `test_delete_referenced_by_practice_409` | 简历已被某练习会话 `resume_id` 关联 → 409，**且行仍在** |
| `test_delete_other_candidates_resume_403` | 403 |
| `test_delete_missing_404` | 404 |
| `test_delete_rolls_back_on_conflict` | 409 之后 session 可用（`IntegrityError` 已 rollback，不污染后续请求） |

> **「行仍在」这一条必须断言**：`IntegrityError` 若不 rollback，后续操作会在污染的事务上失败——这正是 `position/repository.py` 捕获后立刻 `db.rollback()` 的原因。

### 7.5 架构约束登记（⚠️ 容易漏）

| 测试 | 断言 |
|---|---|
| `test_nine_modules_exist`（`test_architecture.py`，**改名 + 改断言**） | `ALL_MODULES` 含 `resume`，且长度为 **9** |
| `test_five_layer_files_exist[resume]` | `models.py` / `schemas.py` / `repository.py` / `service.py` / `router.py` 齐备 |
| `test_no_reverse_dependency[resume]` | 禁止依赖 `position` / `question` / `interview` / `evaluation` / `practice` |
| `test_no_reverse_dependency[interview]`（既有，仍须通过） | `interview` 的禁止集合**不含** `resume`——因此 `interview → resume` 合法 |
| `test_no_reverse_dependency[practice]`（既有，仍须通过） | 同上，`practice → resume` 合法 |
| `test_ai_depends_on_no_business_module`（既有，仍须通过） | 未被破坏 |
| `test_repository_does_not_reach_up[resume]` / `test_models_is_pure_schema[resume]` / `test_router_goes_through_service[resume]` / `test_service_uses_repository_not_raw_sql[resume]` | 四条既有参数化用例**自动覆盖**新包（因为都 parametrize 在 `LAYERED_MODULES` 上），无需新增测试，只需确认它们出现且通过 |

> **不登记 = 不受保护**：`test_architecture.py` 用硬编码模块名列表驱动全部结构约束。`resume` 不登记时这些测试**依然全绿**，但已不再覆盖新包——这是最容易被忽视的一类失效。已记入 [module-08 §7.2](./2026-09-15-module-08-e2e-plan.md)。
>
> **`FORBIDDEN_DEPENDENCIES` 只需要新增 `resume` 一项**：`interview` / `practice` 的禁止集合里**没有** `resume`，所以两条正向依赖自动放行，无需改动。

### 7.6 鉴权与隔离

| 测试 | 断言 |
|---|---|
| `test_resume_endpoints_reject_hr` | hr 对五个端点 → 403 |
| `test_resume_endpoints_reject_admin` | admin 对五个端点 → **403**（module-09 §4.5 的精确匹配规则） |
| `test_resume_endpoints_reject_anonymous` | 无 token → 401 |
| `test_resume_endpoints_reject_hr_token_on_candidate_path` | HR token 调 `/api/candidate/resumes` → 403（**不得**被误当作合法登录放行） |

### 7.7 跨包供给契约

| 测试 | 断言 |
|---|---|
| `test_load_unchecked_returns_other_users_resume` | 传入他人简历 id → **正常返回**（证明它确实不做权限过滤，供 HR 侧使用） |
| `test_load_unchecked_missing_returns_none` | 不存在 → `None`（**不抛异常**，让调用方决定 404 语义） |
| `test_ensure_mine_ok` | 本人简历 → 返回对象 |
| `test_ensure_mine_other_user_403` | 他人简历 → 403 |
| `test_ensure_mine_missing_404` | 不存在 → 404 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-09（`require_roles`、候选人角色）、module-16（守卫）已完成。
> **本模块是 MVP-3 的第一个模块**，其余模块均依赖它，因此必须最先完成。

### Task 17.1：包骨架与架构登记

- [ ] 建 `app/resume/` 五层空文件 + `__init__.py`
- [ ] **把 `resume` 登记进 `backend/tests/test_architecture.py` 的四个列表**（含 `FORBIDDEN_DEPENDENCIES` 新增 `resume` 项）
- [ ] **`test_eight_modules_exist` 改名为 `test_nine_modules_exist`，断言改为 9**
- [ ] 运行 `pytest tests/test_architecture.py -v`，确认新参数化用例已生效（此时因缺实现而失败）
- [ ] 提交

### Task 17.2：模型与配置项

- [ ] `models.py` 定义 `resume` 表（§3.1 全字段与索引）
- [ ] `core/config.py` 新增 `RESUME_CONTENT_MAX_LENGTH`；`.env.example` 补键
- [ ] **不写迁移**（§2 说明）
- [ ] 写失败测试：`updated_at` 在更新后前进；`(created_by)` 索引存在
- [ ] 提交

### Task 17.3：repository 层

- [ ] 实现 §4.4 五个方法
- [ ] 写失败测试：`list_by_creator` 只返回指定 `created_by` 且按 `updated_at` 倒序
- [ ] 写失败测试：`delete` 遇 `IntegrityError` → `BusinessError`，且 **rollback 后 session 可用**
- [ ] 运行确认通过
- [ ] 提交

### Task 17.4：service 层（校验、归属、跨包契约）

- [ ] 写 §7.1 / §7.3 / §7.7 全部失败测试（**含「超长返回 422 而非 400」与「`load_unchecked` 对他人简历不报错」**）
- [ ] 运行确认失败
- [ ] 实现 §4.3 七个方法（含 `load_unchecked` / `ensure_mine`）
- [ ] 运行确认通过
- [ ] 提交

### Task 17.5：router 层与端点

- [ ] 写 §7.2 / §7.6 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 §4.1 五个端点；在 `main.py` 注册（**放在 interview 之前**）
- [ ] 运行确认通过
- [ ] 提交

### Task 17.6：全量回归与夹具

- [ ] `conftest.py` 新增 `resume` 夹具（供 module-19 / module-20 复用）
- [ ] 运行 `pytest tests/ -q`，**全部通过**（含架构测试的新参数化用例）
- [ ] 提交

---

## 9. 验收标准

- [ ] `resume` 成为**第九个 package**，五层文件齐备，**且已登记进 `test_architecture.py`**（含 `test_eight_…` 改名为九）
- [ ] 表 `resume` 建成，字段与 §3.1 一致，`ix_resume_created_by` 就位
- [ ] **只改模型、不写迁移、不同步 `script.sql`**（待统一收口）
- [ ] 五个端点全部 `require_roles("candidate")`，hr 与 admin **一律 403**
- [ ] 列表只返回**本人的**简历，按 `updated_at` 倒序
- [ ] 请求体**不含** `created_by`，归属恒取自 token
- [ ] 正文超长 → **422**（非 400）；纯空白标题 / 正文 → 400
- [ ] 删除被面试或练习关联的简历 → **409 且行仍在**，且事务已 rollback
- [ ] 同名简历可共存（未加唯一约束）
- [ ] `update` 为**部分更新**语义；`updated_at` 自动前进
- [ ] **`load_unchecked` 不做任何权限过滤**，`ensure_mine` 做归属校验——两个跨包口子均已实现并被测试覆盖
- [ ] `resume` 的顶层导入**只有 `core` / `auth`**，无任何业务模块
- [ ] 未新增任何错误码；既有用例零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **候选人资源归属不能用 `ensure_resource_visible`** | 用既有的 `auth.service.ensure_owner_match` | `ensure_resource_visible` 对 candidate 会直接抛 403（module-16 纵深防御），候选人连自己的简历都读不到。module-13 已就同一问题立过先例，本模块直接复用，**不新增 auth 函数** |
| **`resume` 若依赖 `interview` 就会引入循环** | 删除保护完全交给外键 `RESTRICT`，本模块零跨表查询 | 与 `position` 删除校验同构。若改为「先数引用」，既引入 `resume → interview` 的反向依赖（架构测试会红），又带来「数完到删之间被关联」的竞态 |
| **HR 读候选人简历的判据不在本模块** | 只提供 `load_unchecked`，判据由 `interview` 实现 | PRD §9 明确如此。`resume` 不感知调用方身份，才能保持单向依赖 |
| **两个跨包函数命名刻意不对称**（`load_unchecked` / `ensure_mine`） | 保留不对称命名 | 「这里没有权限检查」必须在一眼可见的位置表达，否则会被误用为安全入口 |
| **正文超长返回 422，与全项目 400 不一致** | 在 service 层抛 422 业务异常，绕过 Pydantic | PRD §7 明确 422。用 `Field(max_length=...)` 会被 `main.py` 统一收口成 400。已在测试中显式钉住 422，防止被「统一」 |
| **不加 `(created_by, title)` 唯一约束**（`position` 有） | 刻意不加 | 候选人保留同名简历无害，而唯一约束会把这种正当用法变成 409。与 `position` 的差异是有意的：岗位名是 HR 的检索键，简历标题不是 |
| **列表下发正文全文** | 下发 | 数据量是「简历数 × 一段文本」，不是「会话数 × 题目数」。轻量化在这里无收益，反而让编辑回显多一次请求。**与 `practice` 会话列表的取舍相反，原因不同** |
| **`updated_at` 是本项目首个此类字段** | 加，且用 `ON UPDATE NOW` | 简历是唯一由用户反复编辑的自有内容，且 PRD §4.13 的「改后需重新补题」需要 HR 判断手上这份是否最新。数据库保证优于应用层记得写 |
| **PUT 承载部分更新语义** | 按 PRD 走 PUT，但实现为部分更新 | PRD §8 已定 `PUT`。若改成 PATCH，前端与文档都要跟着改；在文档写明部分更新语义是成本更低的收敛方式 |
| **可选字段无法被清空** | 传 `None` = 不改；要清空就传空串 | 区分「未提供」与「显式置空」需要 `model_fields_set` 之类的额外机制（Pydantic v2 可行但增复杂度）。`None` 与空串在展示上等价，因此不值得为此加机制 |
| **不做版本历史** | 只保留最新内容 | PRD 未要求。简历是可反复覆盖的自有文本，版本化会带来存储与 UI 的双重成本 |
