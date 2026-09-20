# interview 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：interview（面试实例、出题组装、回答记录、状态机）
**所属包**：`backend/app/interview/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.4（面试管理）、§5.1（状态机）、§5.2（三个实体）、§5.3 ①②（创建+出题、手动录入）、§8（interview API）
**前置依赖**：core（[00](./2026-09-15-module-00-core-plan.md)）、auth（[01](./2026-09-15-module-01-auth-plan.md)）、position（[02](./2026-09-15-module-02-position-plan.md)）、question（[03](./2026-09-15-module-03-question-plan.md)）、ai（[04](./2026-09-15-module-04-ai-plan.md)）

> **MVP-2 增量（2026-09-20）**：新增**作答邀请**实体与三个 HR 端点、**候选人在线作答**通道与交卷锁定；`answer` 表新增 `source` / `answered_by` / `submitted_at` 三列。**面试状态机五态不变**（候选人作答只是输入通道）。本文档的 Global Constraints、§1.1、§1.2、§3.3、§4.1、§4.2、§5.3、§5.4.3、§7.1、§10 已同步修正；**增量部分的完整契约以 [module-12 作答邀请与在线答题](./2026-09-20-module-12-interview-invitation-plan.md) 为准**。

---

## Global Constraints（全局约束，摘自 PRD）

- 后端分层：**router → service → repository → MySQL，严格单向依赖**（§2、§3.2）
- 每个模块独立 Python package（§2、§3.3）
- **出题同步、评估流式（SSE）**（§1.3、§5.3）
- 统一响应格式：**`{code, message, detail}`**（§7）
- 统一前缀 `/api`，**除登录与候选人自助注册外均需 JWT**（§8；MVP-2 起多一个公开端点）
- **数据隔离（三端，MVP-2 起）**：admin 可访问全部；普通 HR 只能访问自己创建的 position / question / interview；**candidate 只能访问自己被邀请且已接受的面试**（§4.1、§4.4、§4.6）
- **AI 调用失败**：重试 1 次 → 仍失败则标记失败、可重新触发；**不阻塞其他功能**（§7）
- **（MVP-2）HR 侧端点必须显式校验角色（admin/hr）**；候选人侧端点校验 candidate，且 **admin 在候选人侧不通行**（§4.1、§9）
- 仅 PC 端（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.4）

| 子职责 | 内容 | PRD |
|---|---|---|
| 面试实体 | `interview` / `interview_question` / `answer` 三张表的定义与迁移 | §5.2 |
| 出题组装 | 题库抽 N 题 + AI 补 M 题，合并、编号、**写内容快照** | §5.3 ① |
| 回答记录 | 逐题录入候选人回答，**可随时编辑** | §5.3 ② |
| **状态机** | 面试生命周期状态的**唯一权威**，校验并执行状态迁移 | §5.1 |
| **作答邀请（MVP-2）** | `interview_invitation` 表；生成 / 列表 / 撤销邀请码；凭码激活绑定 | §4.4、§4.8 |
| **候选人在线作答（MVP-2）** | 候选人逐题作答与交卷锁定；HR 仍可覆盖 | §4.4、§4.8 |
| **候选人可见性供给契约（MVP-2）** | `get_interview_for_candidate`：候选人能否访问某面试的**唯一判据** | §4.1、§4.6 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **评分与报告** | 属于 evaluation 模块。interview 只保证「回答数据齐备、状态已到 `completed`」（PRD §4.5） |
| **AI 调用细节** | 只调 `ai.factory.get_provider()` 暴露的接口，不关心真实还是 Mock（PRD §6） |
| **题目字段校验** | 题目的创建校验属于 question 模块 |
| ~~**在线答题（候选人侧）**~~ | ⚠️ **MVP-2 起已在范围内**（PRD §4.8）：候选人凭邀请码逐题作答、交卷锁定。实现见 [module-12](./2026-09-20-module-12-interview-invitation-plan.md) |
| **候选人的答题时限 / 倒计时 / 防切屏（MVP-2）** | PRD 未要求；引入会牵出计时器状态与前端轮询 |
| **候选人撤回交卷（MVP-2）** | 交卷后锁定（§4.4）；需补答时由 HR 回退到 `ongoing` 后重发邀请 |
| **候选人账号的创建逻辑（MVP-2）** | 委托 `auth.service.create_candidate_account`（[module-09 §5.2](./2026-09-20-module-09-auth-plan.md)），不在本模块复制账号规则 |
| **作答的历史版本（MVP-2）** | PRD §5.2 明确不做（覆盖前的候选人原文不可追溯） |
| **反向依赖 evaluation** | interview 不知道评估的存在；涉及 `evaluating` / `evaluated` 的迁移由 evaluation **调用 interview 的状态机接口**完成（§5.4） |

### 1.3 依赖方向（对应 PRD §3.3）

```
interview.router ──→ interview.service ──→ interview.repository ──→ interview 三张表
                          │
                          ├──→ position.service（取 JD 与维度）
                          ├──→ question.service（取候选题目、写入 AI 题）
                          ├──→ ai.factory.get_provider()（出题）
                          ├──→ auth.service.scope_owner_id
                          └──→ core.deps.get_current_user

evaluation ──→ interview（读取回答与快照；调用状态机迁移接口）
interview ✗→ evaluation（不反向依赖）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/interview/__init__.py` | 包标识 |
| `backend/app/interview/models.py` | `Interview`、`InterviewQuestion`、`Answer` 三个模型（**MVP-2 起加 `InterviewInvitation`**） |
| `backend/app/interview/schemas.py` | 请求 / 响应 Pydantic 模型 |
| `backend/app/interview/repository.py` | 三张表的数据访问（含 `owner_id` 过滤） |
| `backend/app/interview/service.py` | 出题组装、回答记录、**状态机**（**MVP-2 起加邀请与候选人作答**） |
| `backend/app/interview/router.py` | `/api/interviews/*` 端点（**HR 侧**） |
| `backend/app/interview/candidate_router.py` | **MVP-2 新增**：`/api/candidate/interviews/*` 端点（守卫为 `candidate`，与 HR 端点分开文件） |

**测试文件**：`backend/tests/test_interview.py`；**MVP-2 新增** `test_interview_invitation.py`、`test_candidate_answering.py`

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 interview router；**MVP-2 起另注册 `candidate_router`** |
| `backend/alembic/versions/` | 新增三张表迁移；**MVP-2 起另加 `interview_invitation` 建表与 `answer` 加三列** |
| `backend/script.sql` | **MVP-2 起需同步**上述结构与索引（module-00 §4 的一致性要求） |
| `backend/app/core/config.py` | **MVP-2 起新增** `INVITATION_EXPIRE_DAYS`（默认 7） |
| `backend/tests/conftest.py` | **MVP-2 起新增** `accepted_invitation` 夹具（供 module-14/15 复用） |

---

## 3. 数据模型设计

### 3.1 表 `interview`（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 | 来源 |
|---|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 | PRD §5.2 |
| `position_id` | BIGINT | NOT NULL, FK → `position.id` **RESTRICT**, INDEX | 面试岗位 | PRD §5.2 |
| `candidate_name` | VARCHAR(100) | NOT NULL | 候选人姓名 | PRD §5.2 |
| `candidate_contact` | VARCHAR(200) | NULL | 联系方式，可选 | PRD §5.2 |
| `status` | ENUM('draft','ongoing','completed','evaluating','evaluated') | NOT NULL, DEFAULT `'draft'`, INDEX | 状态机当前态 | PRD §5.1 |
| `created_by` | BIGINT | NOT NULL, FK → `user.id`, INDEX | **创建人，数据隔离依据** | PRD §5.2 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — | **本设计新增** |
| `completed_at` | DATETIME | NULL | 标记完成的时刻 | **本设计新增** |

### 3.2 表 `interview_question`（对应 PRD §5.2）

PRD §5.2 列出 `interview_id, question_id, seq, content_snapshot`。本设计补充两个快照字段：

| 字段 | 类型 | 约束 | 说明 | 来源 |
|---|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 | 本设计新增（见 §3.5） |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, INDEX | 所属面试 | PRD §5.2 |
| `question_id` | BIGINT | NOT NULL, FK → `question.id` RESTRICT | 来源题目 | PRD §5.2 |
| `seq` | INT | NOT NULL | 面试内序号，**从 1 开始** | PRD §5.2 |
| `content_snapshot` | TEXT | NOT NULL | 出题时的题干快照 | PRD §5.2 |
| `dimension_snapshot` | VARCHAR(50) | NOT NULL | 出题时的考察维度快照 | **本设计新增** |
| `source_snapshot` | ENUM('bank','ai') | NOT NULL | 出题时的来源快照 | **本设计新增** |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — | **本设计新增** |

**索引**：`UNIQUE (interview_id, seq)`、`INDEX (interview_id)`、`INDEX (question_id)`

**为何必须补充快照字段**（与 PRD §5.2 的注释「之后题库删改不影响历史面试」同一动机）

| 快照字段 | 不加会怎样 |
|---|---|
| `content_snapshot`（PRD 已有） | 题库题目被编辑后，历史面试的题干会跟着变，评估报告与当时实际问的问题对不上 |
| `dimension_snapshot` | 岗位维度改名后，evaluation 按 `dimension_score.dimension` 归集会**错位** |
| `source_snapshot` | 题库题目被删除或来源变更后，**无法还原当时题目的出处** |

> 三者是**同一类完整性需求**，缺任一项都会让历史面试无法自洽。PRD 只显式列出 `content_snapshot`，另外两个是按其同一逻辑补齐。

### 3.3 表 `answer`（**对 PRD §5.2 的修正**）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_question_id` | BIGINT | NOT NULL, FK → `interview_question.id` **CASCADE**, **UNIQUE** | 一道面试题对应一条回答 |
| `content` | TEXT | NOT NULL | 候选人回答（HR 录入或候选人自答） |
| `recorded_at` | DATETIME | NOT NULL, DEFAULT NOW, ON UPDATE NOW | 最后记录时刻 |
| `source`（**MVP-2**） | ENUM('hr','candidate') | NOT NULL, DEFAULT `'hr'` | **作答最初的来源通道**；历史数据默认 `hr` |
| `answered_by`（**MVP-2**） | BIGINT | **NULL**, FK → `user.id` **RESTRICT** | **最后修改者**；迁移前的数据无法倒推，故允许 NULL |
| `submitted_at`（**MVP-2**） | DATETIME | **NULL** | **候选人交卷时刻**；HR 手工录入时为 NULL |

> **（MVP-2）三列的分工与不可合并性**：`source` 答「最初从哪条通道进来」，`answered_by` 答「最后是谁改的」，`submitted_at` 答「候选人是否已交卷」。HR 覆盖候选人作答后会出现 `source='candidate'` 而 `answered_by=HR` —— **两个事实都需要保留**（PRD §5.2）。
>
> **不加 `is_locked` 列**：「候选人能否改」由 `submitted_at` 是否为空推导。用第二个字段表达同一状态必然漂移。
>
> **交卷是面试级事实，但 `submitted_at` 落在作答行上**：候选人交卷时会给**全部题**写 `submitted_at`（未作答的题补空串作答行），从而保住单一事实来源。完整理由与替代方案见 [module-12 §5.5](./2026-09-20-module-12-interview-invitation-plan.md)。

**PRD §5.2 原为**：`answer(id, interview_id, question_id, content, recorded_at)`。本设计改为以 **`interview_question_id`** 标识。理由：

| 论点 | 说明 |
|---|---|
| **唯一性语义更准** | 要保证「一道面试题一条回答」，正确的唯一键是 `interview_question.id`；用 `(interview_id, question_id)` 是绕道实现同一约束 |
| **与快照对齐** | 回答属于「**这次面试的这一题**」，而 `interview_question` 正是这个身份 |
| **不阻碍扩展** | 若未来允许同一道题库题在一次面试中出现两次，按 `question_id` 建唯一键会直接撞车 |
| **消除冗余** | `interview_id` 可通过 `interview_question` 关联得到，不再在 `answer` 上冗余存储，避免不一致 |

> 该修正的连带影响：evaluation 的 `question_score` 同样以 `interview_question_id` 标识（见 evaluation 模块）。

### 3.4 设计要点

| 要点 | 理由 |
|---|---|
| `interview_question.interview_id` 用 **CASCADE** | 面试删除时，其题目与回答一并清除，无孤儿数据 |
| `question_id` 用 **RESTRICT** | 题库题目被面试引用时不可删除（question §5.3） |
| `position_id` 用 **RESTRICT** | 岗位被面试引用时不可删除（position §5.3） |
| `answer` 与 `interview_question` 之间 **CASCADE** | 删面试题连带删回答 |
| **不设 `answer.is_deleted`** | 回答只有「有」和「无」两态；清空回答通过写入空串（评分为 0）而非删除记录 |
| `UNIQUE (interview_id, seq)` | 防止并发出题导致序号重复 |

### 3.5 为何给 `interview_question` 与 `answer` 补 `id` 主键

PRD §5.2 的关键字段列表未列出这两张表的主键。但：

- `answer` **必须**有稳定的唯一标识才能被「保存回答」接口幂等地定位（§4.2 的 `interview_question_id` 即指向 `interview_question.id`）。
- 代理主键比复合主键在 ORM 映射、级联删除、未来扩展上更简单。

---

## 4. 接口契约

### 4.1 对外 REST API（对应 PRD §8）

| 方法 | 路径 | 说明 | 权限 | 成功码 | PRD §8 |
|---|---|---|---|---|---|
| POST | `/api/interviews` | 创建面试（含**同步出题组装**） | **admin, hr** + 岗位可见 | 201 | ✓ |
| GET | `/api/interviews` | 面试列表（按数据隔离过滤） | **admin, hr** | 200 | ✓ |
| GET | `/api/interviews/{id}` | 面试详情（含题目与回答） | **admin, hr** + 可见 | 200 | ✓ |
| PATCH | `/api/interviews/{id}` | **仅更新候选人信息** | **admin, hr** + 可见 | 200 | ✓（范围收窄，见下） |
| POST | `/api/interviews/{id}/answers` | 保存 / 更新某题回答（**含覆盖候选人作答**） | **admin, hr** + 可见 | 200 | ✓ |
| POST | `/api/interviews/{id}/complete` | 标记面试完成 | **admin, hr** + 可见 | 200 | ✓ |
| POST | `/api/interviews/{id}/rollback` | 回退到进行中 | **admin, hr** + 可见 | 200 | **本设计新增** |
| POST | `/api/interviews/{id}/invitations` | **MVP-2**：生成作答邀请码 | **admin, hr** + 可见 | 201 | ✓ |
| GET | `/api/interviews/{id}/invitations` | **MVP-2**：邀请列表与状态 | **admin, hr** + 可见 | 200 | ✓ |
| DELETE | `/api/interviews/{id}/invitations/{inv_id}` | **MVP-2**：撤销邀请 | **admin, hr** + 可见 | 200 | ✓ |

> **（MVP-2）「权限」列的变动**：原文写作「登录」「登录 + 可见」。引入 `candidate` 角色后「已登录」不再充分——候选人 token 同样满足它。自 MVP-2 起本表全部端点显式校验角色（`require_roles("admin","hr")`），再由 service 做可见性判定（§5.3）。守卫补全见 [module-16](./2026-09-20-module-16-permission-guard-plan.md)，**须与 module-09 同批发布**。
>
> **（MVP-2）候选人侧六个端点不在本表**：它们注册在 `/api/candidate/*` 下、守卫为 `require_roles("candidate")`，**实现在独立文件 `interview/candidate_router.py`**（按守卫分文件，避免同文件里挂错守卫）。端点和契约见 [module-12 §4.1、§4.2](./2026-09-20-module-12-interview-invitation-plan.md)；其中 `/feedback` 由 `evaluation` 包提供（[module-14](./2026-09-20-module-14-evaluation-feedback-plan.md)）。

> **对 PRD §8 的修正：`PATCH` 不再承担状态变更**
>
> PRD §8 中 `PATCH /interviews/{id}` 描述为「更新候选人信息/**状态**」，同时又单独列出 `POST /interviews/{id}/complete`。二者在「改状态」上**重叠**。本设计二选一，采纳**显式命令端点**：
> - `PATCH` 只改候选人信息；
> - 状态迁移一律走 `/complete`、`/rollback` 等**动词端点**，由状态机统一校验。
>
> 理由：状态迁移有**前置条件与副作用**（如设置 `completed_at`），作为「字段更新」容易被绕过校验；动词端点也让 API 语义自解释。
>
> **新增 `/rollback` 的依据**：PRD §5.1 明确要求 `completed → ongoing` 的回退能力（"回退以补充/修改回答"），但 PRD §8 **未给出对应端点**——此为补齐该状态机迁移的入口，**非功能扩展**。

### 4.2 请求 / 响应结构

**Interview 列表项**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | — |
| `position_id` | int | — |
| `position_name` | str | 岗位名（联表读取，供列表展示） |
| `candidate_name` | str | — |
| `candidate_contact` | str \| null | — |
| `status` | str | 状态机当前态（PRD §5.1） |
| `created_at` | datetime | — |
| `completed_at` | datetime \| null | — |
| `question_count` | int | 题目总数 |
| `answered_count` | int | 已回答题数 |

**Interview 详情**（在列表项基础上追加）

| 字段 | 类型 | 说明 |
|---|---|---|
| `jd` | str | 岗位 JD（供展示） |
| `evaluation_dimensions` | list[str] | 岗位当前维度（供展示） |
| `questions` | list[QuestionItem] | 见下 |

**QuestionItem**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | int | **该题在此面试中的唯一标识（回答接口用它）** |
| `seq` | int | 序号，从 1 开始 |
| `content` | str | 题干（取自 `content_snapshot`） |
| `dimension` | str | 维度（取自 `dimension_snapshot`） |
| `source` | str | **题目来源**（取自 `source_snapshot`）⚠️ 与 `answer_source` 含义不同，见下 |
| `answer` | str \| null | 已回答内容；**未回答为 `null`** |
| `recorded_at` | datetime \| null | — |
| `answer_source`（**MVP-2**） | str \| null | **作答来源**：`hr` \| `candidate`；无作答记录时为 `null` |
| `answered_by`（**MVP-2**） | int \| null | **作答最后修改者的 user id** |
| `submitted_at`（**MVP-2**） | datetime \| null | **候选人交卷时刻**；HR 手工录入的作答恒为 `null` |

> ⚠️ **命名冲突的显式处理（MVP-2）**：本对象已有一个 `source`，含义是**题目来源快照**。作答的 `answer.source` 是**另一件事**（哪条通道写的回答）。因此在新字段前加 `answer_` 前缀，命名为 **`answer_source`**。
>
> **绝不可**把作答来源也叫 `source` —— 同一个对象里出现两个同名不同义的字段，是排查成本最高的那类 bug（前端会把题目的「手工/AI」标签错当成作答通道）。HR 详情页需要这两个信息分别展示：题目来自题库还是 AI（`source`），以及这一题是候选人自己答的还是 HR 代录的（`answer_source`）。

**POST `/api/interviews`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `position_id` | int | 必填，岗位须存在且可见 |
| 请求 | `candidate_name` | str | 必填，1–100 字符 |
| 请求 | `candidate_contact` | str \| 可选 | 0–200 字符 |
| 响应 | 完整的 Interview 详情 | — | 含已生成的 `questions` |

**PATCH `/api/interviews/{id}`**

| 请求字段 | 类型 | 约束 |
|---|---|---|
| `candidate_name` | str \| 可选 | 1–100 字符 |
| `candidate_contact` | str \| null \| 可选 | 0–200 字符 |

> 仅当状态为 `ongoing` 或 `completed` 时允许修改候选人信息；`evaluating` / `evaluated` 下拒绝（避免报告所依据的对象发生变化）。

**POST `/api/interviews/{id}/answers`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `interview_question_id` | int | 必填，**须属于该面试** |
| 请求 | `content` | str | 必填，**允许空串**（表示「候选人未作答」），0–10000 字符 |
| 响应 | 该 QuestionItem | — | 含更新后的 `answer` 与 `recorded_at` |

**POST `/api/interviews/{id}/complete`** → 响应完整 Interview 详情，`status == "completed"`，`completed_at` 非空。

**POST `/api/interviews/{id}/rollback`** → 响应完整 Interview 详情，`status == "ongoing"`，`completed_at` 置空。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_interview(db, user: User, data: InterviewCreate) -> InterviewDetail` | 详情 | 建面试 + 出题组装 + 置 `ongoing`，**单事务**（PRD §5.3 ①） |
| `list_interviews(db, user: User) -> list[InterviewListItem]` | 列表 | `scope_owner_id` 过滤（PRD §4.4） |
| `get_interview(db, user: User, interview_id: int) -> InterviewDetail` | 详情 | 不存在 → 404；不可见 → 403 |
| `update_candidate(db, user: User, interview_id: int, data: InterviewPatch) -> InterviewDetail` | 详情 | 按状态限制 |
| `save_answer(db, user: User, interview_id: int, interview_question_id: int, content: str) -> QuestionItem` | 题目项 | 仅 `ongoing` 允许（PRD §5.3 ②「可随时编辑」）。**MVP-2**：本方法即为 **HR 通道**，候选人交卷后仍可覆盖其作答（锁定只对候选人侧生效） |
| `complete_interview(db, user: User, interview_id: int) -> InterviewDetail` | 详情 | `ongoing` → `completed`（PRD §5.1） |
| `rollback_interview(db, user: User, interview_id: int) -> InterviewDetail` | 详情 | `completed` / `evaluated` → `ongoing`（PRD §5.1） |

**供 evaluation 使用的接口**（§5.5）

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `get_answers_for_evaluation(db, interview_id: int) -> list[QAPair]` | QAPair 列表 | 组装维度（快照）+ 题干（快照）+ 回答 |
| `get_position_id(db, interview_id: int) -> int` | int | — |
| `get_evaluation_dimensions(db, interview_id: int) -> list[str]` | 维度列表 | 取**岗位当前**维度 |
| `transition_to_evaluating(db, interview_id: int) -> None` | — | `completed` / `evaluated` → `evaluating` |
| `transition_to_evaluated(db, interview_id: int) -> None` | — | `evaluating` → `evaluated` |
| `transition_back_to_completed(db, interview_id: int) -> None` | — | 评估失败时 `evaluating` → `completed` |

> **（MVP-2）新增的 service 方法不列在本节**：邀请管理（`create_invitation` / `list_invitations` / `revoke_invitation` / `accept_invitation`）与候选人侧（`get_interview_for_candidate` / `get_candidate_interview_detail` / `save_candidate_answer` / `submit_interview` / `list_my_interviews`）共 9 个方法的完整签名见 [module-12 §4.3](./2026-09-20-module-12-interview-invitation-plan.md)。上表 6 个「供 evaluation 使用的接口」**签名与语义均不变**。

> **为何 evaluation 的迁移必须走 interview 的方法**：状态机的**唯一权威在 interview 模块**（PRD §5.1 将状态机列为 interview 的职责）。evaluation **不得**直接改 `interview.status` 字段，必须调用上表的迁移方法，以保证迁移合法性校验集中在一处。

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create_interview(db, position_id: int, candidate_name: str, contact: str \| None, created_by: int) -> Interview` | Interview | 初始 `status='draft'` |
| `list_by_owner(db, owner_id: int \| None) -> list[Interview]` | 列表 | 联表取 `position_name`；`owner_id=None` 表示不过滤 |
| `get_by_id(db, interview_id: int) -> Interview \| None` | Interview | **不带权限过滤** |
| `update_interview(db, interview: Interview, **fields) -> Interview` | Interview | — |
| `create_questions(db, items: list[dict]) -> list[InterviewQuestion]` | 列表 | 批量写入面试题（含快照） |
| `list_questions(db, interview_id: int) -> list[InterviewQuestion]` | 列表 | **按 `seq` 升序** |
| `get_question_entry(db, entry_id: int) -> InterviewQuestion \| None` | InterviewQuestion | — |
| `upsert_answer(db, interview_question_id: int, content: str) -> Answer` | Answer | 存在则更新 `content` + `recorded_at`，不存在则创建。**MVP-2**：扩展为接受可选关键字参数 `source` / `answered_by` / `submitted_at`；HR 通道调用点**一行都不用改**（走模型默认） |
| `list_answers(db, interview_id: int) -> list[Answer]` | 列表 | 联 `interview_question` 取 `interview_id` |
| `count_questions(db, interview_id: int) -> int` | int | — |
| `count_answers(db, interview_id: int) -> int` | int | — |

---

## 5. 业务流程设计

### 5.1 创建面试 + 出题组装（PRD §5.3 ①，**单事务**）

```
1. schemas 校验（candidate_name 长度等）
2. position.service.get_position(db, user, position_id)
      → 不存在 404；不可见 403
3. repository.create_interview(status='draft', created_by=user.id)
4. 执行出题组装（§5.2）
5. repository.create_questions(所有题目与快照)
6. status → 'ongoing'，commit
```

**AI 失败时的策略：整体回滚**

PRD §7 规定 AI 失败「重试 1 次 → 仍失败则标记失败、可重新触发；**不阻塞其他功能**」。据此：

| 方案 | 评价 |
|---|---|
| **整体回滚（本设计采用）** | 语义清晰——要么面试创建成功且题目齐备，要么什么都没发生；无需引入 `draft` 的持久化分支与「重新出题」端点；**符合 PRD §7 的「可重新触发」** |
| 保留 `draft` + 重试端点 | 输入仅 3 个字段（岗位、姓名、联系方式），重填成本极低，为此引入新状态分支与新端点不划算（YAGNI） |

失败时事务回滚，**AI 题目也不入库**（`bulk_create_from_ai` 在同一事务内），客户端收到 **502 `AI_PROVIDER_ERROR`** 并可重试。

> **`draft` 状态说明**：PRD §5.1 定义了 `draft`，但本设计中 `POST /interviews` 是**单事务**完成「建面试 + 出题 + 置 ongoing」，因此 `draft` 是**事务内的瞬态值**，不会出现在已提交的数据里。保留该枚举值的两个理由：① 作为模型默认值最安全；② 保留 PRD §5.1 已定义的完整状态集，便于未来引入「先建面试、后出题」的分步流程。
>
> ⚠️ **MVP-2 修正**：原文把「为 V1.1 在线答题预留草稿态」列为理由之一。该理由**已作废且方向相反**——在线答题自 MVP-2 起已在范围内（PRD §4.8），而 PRD §5.1 明确要求**候选人作答不进入面试状态机**（作答的进行状态由 `answer.submitted_at` 表达，不是面试状态）。因此**不得**为候选人答题再引入任何状态。

### 5.2 出题组装算法（PRD §5.3 ①）

**输入**：`position`（含 `jd`、`evaluation_dimensions`）、**N** = `QUESTION_COUNT_FROM_BANK`（默认 **5**）、**M** = `QUESTION_COUNT_FROM_AI`（默认 **3**）

| 步骤 | 规则 |
|---|---|
| 1. 取候选 | `question.list_candidates_for_position(db, owner_id=user.id, position_id)` |
| 2. 过滤 | 剔除 `dimension` 不在 `position.evaluation_dimensions` 中的题目（见 question §5.5） |
| 3. 分组 | 按 `dimension` 分组；每组按 `id` **升序**（保证确定性） |
| 4. 轮询抽取 | 按 `evaluation_dimensions` 的顺序，每轮从各组取 1 题，直至取满 `N` 或所有组耗尽。记录实际抽得数 **K** |
| 5. 计算 AI 需求 | `need_ai = M + (N - K)` —— **保证总题数恒为 `N + M`** |
| 6. 调 AI | `provider.generate_questions(position_name, jd, dims, existing_contents=已抽题干列表, count=need_ai)` |
| 7. AI 题入库 | `question.bulk_create_from_ai(db, user, position_id, ai_items)` → 题库中 `source='ai'`（见 question §5.4） |
| 8. 合并与编号 | 题库题在前（按抽取顺序）、AI 题在后；**`seq` 从 1 连续编号** |
| 9. 写快照 | 每题写 `content_snapshot` / `dimension_snapshot` / `source_snapshot` |

**关键性质**

| 性质 | 说明 |
|---|---|
| **总题数恒定** | 只要 `dims` 非空且 AI 可用，总题数恒为 `N + M = 8`——题库不足时由 AI 补足差额 |
| **确定性** | 轮询顺序固定、组内按 `id` 升序、Mock Provider 确定性 → **同一数据状态下出题结果完全可预测**，便于测试断言 |
| **维度均衡** | round-robin 保证各维度题目数尽量平均，而非某一维度被抽空 |
| **题库不足不报错** | `K < N` 时只是把差额转给 AI（PRD §4.4 未要求报错，且 AI 补充本就是设计意图） |

**边界情况**

| 情况 | 行为 |
|---|---|
| `position.evaluation_dimensions` 为空 | 被 position §3.3 校验阻止，理论上不可达；若发生 → 抛 `BusinessError` |
| 题库为空 | `K = 0`，`need_ai = M + N = 8`，全部由 AI 生成 |
| `need_ai = 0` | 跳过 AI 调用（例如题库题量充足且 `M=0` 的配置） |
| AI 返回数量少于 `need_ai` | **按实际返回数量入库，不报错**；总题数可能少于 8，响应中如实反映 |

### 5.3 回答记录（PRD §5.3 ②「可随时编辑」的边界）

PRD §5.3 ② 说回答「**可随时编辑**」。本设计将其限定为**仅在 `ongoing` 状态**：

```
1. 校验面试存在与可见
2. 校验状态 == 'ongoing'
      否则 → BusinessError「当前状态下不可修改回答，请先回退到进行中」
3. 校验 interview_question_id 属于该面试
      不属于 → NotFoundError
4. repository.upsert_answer（存在则更新 content 与 recorded_at）
5. commit
```

**（MVP-2）两条作答通道**

| 通道 | 入口 | 额外校验 | 写入的字段 |
|---|---|---|---|
| **HR 手工录入** | `POST /api/interviews/{id}/answers` | 与上述流程完全一致（**无新增校验**） | `content` / `recorded_at`；`source` 走默认 `hr` |
| **候选人自答** | `POST /api/candidate/interviews/{id}/answers`（[module-12 §5.4](./2026-09-20-module-12-interview-invitation-plan.md)） | 先经 `get_interview_for_candidate`（404/403），再加**一条**：本人未交卷 | `content` / `source='candidate'` / `answered_by=候选人` / `submitted_at=None` |

| 要点 | 说明 |
|---|---|
| **两条通道共用同一条 `ongoing` 限定** | 不是巧合：他们写的是**同一份数据**，写入约束自然应当一致 |
| **锁定只对候选人侧生效** | HR 通道**不检查** `submitted_at` —— 这是 PRD §4.4「HR 侧不受锁影响」的落点。因此在实现上，「锁定」是候选人端点内的一条校验，**不是** `save_answer` 里的通用规则 |
| 覆盖后 `source` 保留 `candidate` | `save_answer` 只写 `content` 与 `recorded_at`，不触碰新增三列 —— 这正是「只加列、不改语义」的收益（module-12 §5.6） |

| 论点 | 说明 |
|---|---|
| 为何限定 `ongoing` | 「随时编辑」的目的是让 HR 能补充/修正记录，而不是让评估**依据的数据在评估期间或评估后漂移** |
| 与 PRD §5.1 的一致性 | PRD §5.1 已给出 `completed → ongoing` 的**回退迁移**，正是为「编辑已完成面试的回答」准备的通道。若允许在 `completed` 直接改回答，这条回退迁移就没有存在意义 |
| 一条规则覆盖所有情况 | 无需为每个状态单独定义「能不能改」，降低状态爆炸 |

### 5.4 状态机（PRD §5.1，**本模块的核心**）

#### 5.4.1 状态迁移表（PRD §5.1 + 评估失败回退）

| from | to | 触发 | 副作用 | 来源 |
|---|---|---|---|---|
| `draft` | `ongoing` | 出题组装完成（事务内） | — | PRD §5.1 |
| `ongoing` | `completed` | `POST /complete` | 设 `completed_at` | PRD §5.1 |
| `completed` | `evaluating` | evaluation 触发 | — | PRD §5.1 |
| `evaluating` | `evaluated` | evaluation 成功 | — | PRD §5.1 |
| `completed` | `ongoing` | `POST /rollback` | 清 `completed_at` | PRD §5.1 |
| **`evaluating`** | **`completed`** | evaluation 失败 | — | **PRD §7「失败则状态回退 `completed`」** |
| **`evaluated`** | **`evaluating`** | 重新评估 | — | **本设计新增**（见下） |
| **`evaluated`** | **`ongoing`** | `POST /rollback` | 清 `completed_at` | **本设计新增**（见下） |

**表中未列出的迁移一律拒绝**，返回 `BUSINESS_ERROR`（409），`detail` 携带 `{from, to}`。

**两处新增迁移的依据**

| 迁移 | 依据 |
|---|---|
| `evaluating → completed` | PRD §7 明确要求 AI 失败时「状态回退 `completed`，可重新触发」。**没有这条迁移，PRD §7 无法实现** |
| `evaluated → evaluating` | PRD §5.1 的注释「回退以补充/修改回答（**可重新评估**）」蕴含重新评估的意图。若不支持，HR 想换标准重评只能走 `evaluated → ongoing → completed → evaluating` 四步，语义更绕 |
| `evaluated → ongoing` | 与 `completed → ongoing` 同源：PRD §5.1 允许回退修改回答；`evaluated` 的面试同样应允许（修改后需重新评估） |

#### 5.4.2 状态机实现位置

```
interview/service.py
  └── _assert_transition(current: str, target: str) -> None
        非法 → BusinessError(code=BUSINESS_ERROR, detail={"from": current, "to": target})
```

**所有状态变更（含 evaluation 触发的）都经过这一个断言函数**，不允许任何地方直接赋值 `interview.status`。

#### 5.4.3 各状态下允许的操作矩阵

| 操作 | draft | ongoing | completed | evaluating | evaluated |
|---|---|---|---|---|---|
| 查看面试 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 改候选人信息 | ✗ | ✓ | ✓ | ✗ | ✗ |
| 写 / 改回答 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 标记完成 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 回退到进行中 | ✗ | — | ✓ | ✗ | ✓ |
| 触发评估 | ✗ | ✗ | ✓ | ✗ | ✓ |
| **候选人作答 / 交卷**（MVP-2） | ✗ | ✓ | ✗ | ✗ | ✗ |
| **生成 / 撤销邀请**（MVP-2） | ✗ | ✓ | ✗ | ✗ | ✗ |

> **（MVP-2）新增两行的说明**
>
> - **候选人作答与 HR 写回答共用同一条 `ongoing` 限定**：两条通道写的是同一份数据，「写 / 改回答」这一行的状态约束对二者相同。区别不在状态，而在两条通道各自的额外校验（HR 侧无；候选人侧需「本人未交卷」，见 §5.3）。
> - **撤销邀请在任何状态下都允许**（表中按生成口径记为 `ongoing`）：撤销是**收紧**访问而非放宽，已接受的邀请被撤销后候选人立即失去访问权（module-12 §5.1）。因此它不需要状态前置条件，但生成邀请仍限定 `ongoing`。
> - **状态迁移表（§5.4.1）一行不变** —— 候选人作答不进状态机，这是 PRD §5.1 的明确取舍。

> `evaluated` 下的「触发评估」即**重新评估**，会用当前回答覆盖旧的逐题分、维度分与报告（见 evaluation 模块）。
>
> **评估期间（`evaluating`）面试数据全锁**：避免「评估读到一半数据被修改」导致报告不自洽。

### 5.5 对 evaluation 的供给契约

evaluation 只通过以下接口读取面试数据，**不直接查 interview 的表**：

| 接口 | 返回 |
|---|---|
| `get_answers_for_evaluation(db, interview_id)` | `list[QAPair]`：`dimension` 取 `dimension_snapshot`、`question` 取 `content_snapshot`、`answer` 取回答内容或 **`None`**，按 `seq` 升序 |
| `get_evaluation_dimensions(db, interview_id)` | 岗位**当前**的 `evaluation_dimensions` |
| `get_position_id(db, interview_id)` | 岗位 id |
| `transition_to_evaluating` / `transition_to_evaluated` / `transition_back_to_completed` | 状态迁移 |

> **维度取「岗位当前值」而非快照的原因**：维度集合的权威定义在岗位（PRD §4.2）。若岗位维度被修改，重新评估应按**新维度**出分。题目与回答的快照保护的是「**问了什么、答了什么**」；维度则是「**按什么标准评**」——后者跟随岗位定义。此设计已与 position §5.4 的约定对齐。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 未带 / 无效 token | `UNAUTHORIZED` / `INVALID_TOKEN` | 401 | — |
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在 |
| 访问他人面试 | `FORBIDDEN` | 403 | 无权限访问该面试 |
| 岗位不存在 / 不可见 | `NOT_FOUND` / `FORBIDDEN` | 404 / 403 | — |
| `interview_question_id` 不属于该面试 | `NOT_FOUND` | 404 | 题目不属于该面试 |
| 非 `ongoing` 状态写回答 | `BUSINESS_ERROR` | 409 | 当前状态下不可修改回答，请先回退到进行中 |
| 非 `ongoing` 状态标记完成 | `BUSINESS_ERROR` | 409 | 当前状态下不可标记完成 |
| 非法状态迁移 | `BUSINESS_ERROR` | 409 | 不允许从「已完成」迁移到「评估中」（**`detail` 含 `from` / `to`**） |
| `evaluating` / `evaluated` 下改候选人信息 | `BUSINESS_ERROR` | 409 | 评估中或已评估的面试不可修改候选人信息 |
| **AI 出题失败** | `AI_PROVIDER_ERROR` | **502** | AI 出题失败，请稍后重试（**事务已回滚，无残留数据**） |
| `candidate_name` 为空或超长 | `VALIDATION_ERROR` | 400 | — |
| 回答内容超 10000 字符 | `VALIDATION_ERROR` | 400 | — |
| **（MVP-2）角色不符**（候选人调 HR 端点 / HR 调候选人端点） | `FORBIDDEN` | 403 | 无权限执行此操作 |
| **（MVP-2）候选人访问非本人面试** | `FORBIDDEN` | 403 | 无权限访问该面试 |

> **（MVP-2）候选人侧的错误语义不列在本表**：邀请码失效、重复接受、交卷后修改、未交卷/非 `ongoing` 作答等共 12 条见 [module-12 §6](./2026-09-20-module-12-interview-invitation-plan.md)。本表只补「角色」与「跨端访问」两类通用错误。

---

## 7. 测试设计（对应 PRD §10）

> 全部测试使用 **Mock Provider**，保证确定性与无外部依赖（PRD §10 的「service 层注入 mock Provider」）。

### 7.1 鉴权与数据隔离（PRD §4.1、§4.4）

| 测试 | 断言 |
|---|---|
| `test_create_without_token` | 401 |
| `test_create_ok` | 201，返回详情含题目 |
| `test_list_only_own_interviews` | 另一 hr 看不到 |
| `test_admin_sees_all_interviews` | admin 可见全部 |
| `test_get_other_users_interview_forbidden` | 403 |
| `test_get_nonexistent_interview` | 404 |
| `test_save_answer_other_users_interview_forbidden` | 403 |
| `test_complete_other_users_interview_forbidden` | 403 |
| **`test_candidate_cannot_access_hr_interview_endpoints`**（MVP-2） | 候选人 token 对 HR 侧全部端点 → **一律 403** |
| **`test_hr_cannot_access_candidate_endpoints`**（MVP-2） | hr / admin 对 `/api/candidate/interviews*` → 403 |
| **`test_interview_endpoints_reject_anonymous`**（MVP-2） | 无 token → 401 |

> MVP-2 的越权矩阵以**表驱动**形式集中实现于 `backend/tests/test_permissions.py`（[module-16 §7.1](./2026-09-20-module-16-permission-guard-plan.md)）。候选人侧的行为测试（作答、交卷、锁定、可见性）见 [module-12 §7](./2026-09-20-module-12-interview-invitation-plan.md)——**不在本模块重复编写**。

### 7.2 出题组装（PRD §5.3 ①）

| 测试 | 断言 |
|---|---|
| `test_create_generates_n_plus_m_questions` | 题库充足时共 **8 题（5 + 3）** |
| `test_question_seq_starts_at_one_and_is_contiguous` | `seq` 为 1..8 |
| `test_bank_questions_come_first` | 前 5 题 `source == "bank"`，后 3 题 `source == "ai"` |
| `test_snapshots_written` | 每题 **三个快照**（`content` / `dimension` / `source`）非空 |
| `test_dimension_snapshot_matches_bank_question` | 题库题的快照维度等于该题原维度 |
| `test_insufficient_bank_pads_with_ai` | 题库仅 2 题 → **仍共 8 题**（2 题库 + 6 AI），**不报错** |
| `test_empty_bank_all_ai` | 题库为空 → 8 题全部 `source == "ai"` |
| `test_dimension_round_robin` | 两个维度各有充足题目 → 抽取结果在两维度间交替 |
| `test_questions_with_stale_dimension_skipped` | 题库含 `dimension` 不在岗位维度中的题 → **该题不被抽取** |
| `test_ai_questions_saved_to_bank` | 出题后题库中新增 `source == "ai"` 的题目，`created_by` 为面试创建人 |
| `test_ai_failure_rolls_back_everything` | 注入会抛 `AIProviderError` 的 provider → **502**，且**面试与 AI 题目均未入库** |
| `test_create_with_invisible_position` | 用他人岗位 → 403 |
| `test_create_with_nonexistent_position` | 404 |
| `test_generation_is_deterministic` | 相同数据状态下创建两个面试 → **题目序列完全一致** |

### 7.3 回答记录（PRD §5.3 ②）

| 测试 | 断言 |
|---|---|
| `test_save_answer_ok` | 200，`answer` 与 `recorded_at` 正确 |
| `test_save_answer_updates_existing` | 二次保存 → **只有一条记录**，`content` 被更新，`recorded_at` 变化 |
| `test_save_empty_answer_allowed` | `content=""` → 200，`answer == ""` |
| `test_save_answer_wrong_interview` | 传其他面试的 `interview_question_id` → 404 |
| `test_save_answer_content_too_long` | 10001 字符 → 400 |
| `test_save_answer_not_ongoing` | `completed` 状态下 → 409 |
| `test_save_answer_when_evaluating` | 409 |

### 7.4 状态机（PRD §5.1、§7）

| 测试 | 断言 |
|---|---|
| `test_complete_from_ongoing` | 200，`status == "completed"`，**`completed_at` 非空** |
| `test_complete_twice_rejected` | 第二次 409 |
| `test_complete_from_evaluated_rejected` | 409 |
| `test_rollback_from_completed` | 200，`status == "ongoing"`，**`completed_at` 为 `None`** |
| `test_rollback_from_evaluated` | 200，`status == "ongoing"` |
| `test_rollback_from_ongoing_rejected` | 409 |
| `test_rollback_from_evaluating_rejected` | 409 |
| `test_transition_to_evaluating_from_ongoing_rejected` | 直接调用迁移方法 → 409 |
| `test_transition_to_evaluated_requires_evaluating` | 从 `completed` 直接调 `transition_to_evaluated` → 409 |
| `test_transition_back_to_completed_from_evaluating` | 成功，`status == "completed"`（**PRD §7 的失败回退**） |
| `test_reevaluate_from_evaluated` | `evaluated` → `evaluating` 成功 |
| `test_error_detail_contains_from_and_to` | 非法迁移的 `detail` 含 `from` 与 `to` |
| `test_no_direct_status_assignment` | 校验迁移方法之外的路径无法改状态（通过操作矩阵逐格验证） |

### 7.5 候选人信息更新

| 测试 | 断言 |
|---|---|
| `test_update_candidate_when_ongoing` | 200 |
| `test_update_candidate_when_completed` | 200 |
| `test_update_candidate_when_evaluating` | 409 |
| `test_update_candidate_when_evaluated` | 409 |
| `test_update_candidate_does_not_change_status` | **状态不变**（验证 PATCH 不含状态字段） |
| `test_update_candidate_name_too_long` | 400 |

### 7.6 详情与列表

| 测试 | 断言 |
|---|---|
| `test_detail_includes_questions_with_answers` | 题目**按 `seq` 升序**，回答正确挂载 |
| `test_detail_unanswered_question_answer_is_null` | 未回答题 `answer` 为 `null` |
| `test_list_includes_position_name` | 列表项含 `position_name` |
| `test_list_includes_counts` | `question_count == 8`，`answered_count` 正确 |
| `test_detail_uses_snapshot_not_live_question` | **修改题库题目内容后，详情仍显示出题时的快照** |

### 7.7 对 evaluation 的供给契约（§5.5）

| 测试 | 断言 |
|---|---|
| `test_get_answers_for_evaluation_shape` | 返回 `QAPair` 列表，`dimension` 来自**快照**，`question` 来自**快照** |
| `test_get_answers_for_evaluation_order` | 按 `seq` 升序 |
| `test_get_answers_unanswered_is_none` | 未回答的 `answer` 为 **`None`**（不是空串） |
| `test_get_evaluation_dimensions_from_position` | 返回岗位**当前**维度（非快照） |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

> **（MVP-2）Task 5.x 为 MVP-1 已完成的任务清单，保持不变。** MVP-2 的增量任务（`answer` 加三列、`interview_invitation` 建表、`candidate_router.py`、候选人作答复用 `ongoing` 校验等共 8 个 Task）见 [module-12 §8](./2026-09-20-module-12-interview-invitation-plan.md)。**不要在本模块重复实现**。

### Task 5.1：三张模型与迁移

- [ ] 定义 `Interview`（§3.1）、`InterviewQuestion`（§3.2）、`Answer`（§3.3）
- [ ] 建立全部外键（CASCADE / RESTRICT 按 §3.4）与索引、`UNIQUE (interview_id, seq)`
- [ ] 生成迁移、`alembic upgrade head`、验证约束
- [ ] 提交

### Task 5.2：schema 定义

- [ ] 定义 `InterviewCreate`、`InterviewPatch`、`AnswerCreate`、`InterviewListItem`、`InterviewDetail`、`QuestionItem`
- [ ] 写字段校验失败测试（`candidate_name` 长度、回答长度上限）
- [ ] 运行确认失败 → 实现 → 通过
- [ ] 提交

### Task 5.3：repository 层

- [ ] 写失败测试：`list_by_owner(None)` 返回全部；`upsert_answer` 幂等（二次调用只更新不新增）
- [ ] 运行确认失败
- [ ] 实现 §4.4 全部方法
- [ ] 运行确认通过
- [ ] 提交

### Task 5.4：状态机断言

- [ ] 写 §7.4 中迁移方法相关的失败测试（含 `detail` 含 `from`/`to`）
- [ ] 运行确认失败
- [ ] 实现 `_assert_transition`（§5.4.1 全表）与三个供 evaluation 使用的迁移方法
- [ ] 运行确认通过
- [ ] 提交

### Task 5.5：出题组装

- [ ] 写 §7.2 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 §5.2 算法（过滤 → 分组 → round-robin → 计算 `need_ai` → 调 AI → 入库 → 合并编号 → 写快照）
- [ ] 实现 `create_interview` **单事务**与 AI 失败**整体回滚**
- [ ] 实现 `POST /api/interviews`，在 `main.py` 注册 router
- [ ] 运行确认通过
- [ ] 提交

### Task 5.6：列表与详情

- [ ] 写 §7.6 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `list_interviews`、`get_interview`（含**快照读取**、回答挂载、计数）与两个 GET 端点
- [ ] 运行确认通过
- [ ] 提交

### Task 5.7：回答记录

- [ ] 写 §7.3 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `save_answer`（含 `ongoing` 状态限制与题目归属校验）与 `POST /answers` 端点
- [ ] 运行确认通过
- [ ] 提交

### Task 5.8：完成 / 回退 / 候选人信息

- [ ] 写 §7.5 与 §7.4 中端点相关的失败测试
- [ ] 运行确认失败
- [ ] 实现 `complete_interview`、`rollback_interview`、`update_candidate` 与三个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 5.9：对 evaluation 的供给接口

- [ ] 写 §7.7 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `get_answers_for_evaluation`、`get_evaluation_dimensions`、`get_position_id`
- [ ] 运行确认通过
- [ ] 提交

### Task 5.10：全量回归

- [ ] 运行 interview 全部测试
- [ ] 运行 core / auth / position / question / ai 测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] 创建面试返回 201，题库充足时共 **8 题（5 题库 + 3 AI）**，`seq` 从 1 连续（PRD §4.4）
- [ ] 题库不足时由 AI 补齐至总数 8，且**不报错**
- [ ] 题库为空时 8 题全部来自 AI
- [ ] 题库中 `dimension` 已不在岗位维度内的题目**不被抽取**
- [ ] 每题写全 **三个快照**（`content_snapshot` / `dimension_snapshot` / `source_snapshot`）
- [ ] AI 生成的题目写入题库且 `source == "ai"`（PRD §5.2 的 `source` 取值）
- [ ] **AI 出题失败 → 502 且面试与 AI 题目均无残留**（整体回滚，PRD §7）
- [ ] 相同数据状态下出题结果**完全确定**
- [ ] 回答保存仅允许在 `ongoing`；二次保存为**更新而非新增**（唯一约束生效）
- [ ] `completed_at` 在标记完成时被设置、回退时被清空
- [ ] 状态机：§5.4.1 表中未列出的迁移**一律返回 409**，`detail` 含 `from` / `to`（PRD §5.1）
- [ ] PRD §7 的「AI 失败 → 状态回退 `completed`」可通过 `transition_back_to_completed` 实现
- [ ] §5.4.3 操作矩阵**逐格**生效
- [ ] 修改题库题目后，面试详情仍显示出题时的**快照**
- [ ] `get_answers_for_evaluation` 的 `dimension` / `question` 来自**快照**，未回答项 `answer` 为 **`None`**
- [ ] `get_evaluation_dimensions` 返回岗位**当前**维度
- [ ] 全部 interview 测试通过
- [ ] **（MVP-2）** 面试状态机**五态与迁移表一行不变**（候选人作答未引入任何状态）
- [ ] **（MVP-2）** `answer` 三列落地；候选人交卷后 HR 仍可覆盖且 `source` 保留 `candidate`
- [ ] **（MVP-2）** HR 侧端点对候选人一律 403；候选人端点对 hr/admin 一律 403
- [ ] **（MVP-2）** 候选人侧验收见 [module-12 §9](./2026-09-20-module-12-interview-invitation-plan.md)

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| AI 出题失败是否保留面试草稿 | **整体回滚** | 输入仅 3 个字段，重填成本低；避免新状态分支与新端点；符合 PRD §7「可重新触发」 |
| `draft` 状态是否可达 | **事务内瞬态，不持久化** | 保留为模型默认值并保持 PRD §5.1 定义的状态集完整。⚠️ **MVP-2 修正**：原文「为 V1.1 在线答题预留」的理由已作废——在线答题已在范围内，且 PRD §5.1 明确候选人作答**不进状态机**；不得再为它引入状态 |
| **（MVP-2）候选人作答是否需要新状态** | **不需要** | PRD §5.1 的明确取舍：作答是**输入通道**，交付/交卷事实由 `answer.source` / `answered_by` / `submitted_at` 表达。把它做成状态会让 `ongoing` / `completed` 的语义分裂（「HR 还没面」与「候选人已交卷」相互正交） |
| **（MVP-2）作答来源的同名字段冲突** | 作答来源命名为 `answer_source` | 响应对象里已有 `source`（题目来源快照）。两个同名不同义的字段是排查成本最高的 bug 类型 |
| **（MVP-2）交卷时的未作答题目** | 交卷时补空串作答行并写 `submitted_at` | `submitted_at` 在 `answer` 行上（PRD §5.2），但「交卷」是面试级事实；不补行则未作答的题无处记录交卷。理由见 module-12 §5.5 |
| 出题是否随机化 | **不确定随机，round-robin + id 升序** | 可测试性优先；每次出题结果可预测，避免测试不稳定。实际多样性由题库内容与 AI 提供 |
| `answer` 的标识键 | **`interview_question_id`** 而非 PRD 的 `(interview_id, question_id)` | 唯一性语义更准、与快照对齐、不阻碍扩展、消除冗余字段 |
| 快照字段是否需要三个 | **需要**（content / dimension / source） | 缺任一都会让历史面试无法自洽（§3.2） |
| 状态迁移走 PATCH 还是动词端点 | **动词端点** | 状态迁移有前置条件与副作用，作为字段更新易被绕过；同时消除 PRD §8 中二者的重叠 |
| 新增 `/rollback` 端点 | 新增 | PRD §5.1 要求 `completed → ongoing` 回退，但 §8 未给端点——**补齐状态机入口，非扩展** |
| 新增 `evaluating → completed` 与 `evaluated → evaluating` 迁移 | 新增 | 前者是 PRD §7「失败回退」的**必要条件**；后者落实 PRD §5.1 的「可重新评估」 |
| 是否允许在 `completed` 直接改回答 | **不允许**，须先回退 | 一条规则覆盖所有情况，保证评估依据不被篡改；否则 PRD §5.1 的回退迁移失去意义 |
| 评估期间面试数据是否可改 | **不可**（`evaluating` / `evaluated` 全锁） | 避免「评估读到一半数据被改」导致报告不自洽 |
| 维度取岗位当前值还是快照 | **岗位当前值** | 维度是「按什么标准评」，权威定义在岗位；快照保护的是「问了什么、答了什么」 |
| 是否软删除面试 | **不软删除** | MVP YAGNI；本模块无被其他模块引用的场景（evaluation 通过接口读取） |
