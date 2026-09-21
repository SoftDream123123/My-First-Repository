# interview 模块执行计划书（MVP-2 作答邀请与在线答题）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：interview（作答邀请、候选人在线作答、候选人侧面试接口）
**所属包**：`backend/app/interview/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.4（作答邀请管理）、§4.8（在线答题）、§5.1（面试状态机不变 + 邀请状态机）、§5.2（`interview_invitation`、`answer` 扩展）、§7（候选人侧错误语义）、§8（邀请与 candidate 端点）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-01 auth](./2026-09-15-module-01-auth-plan.md)、[module-05 interview MVP-1](./2026-09-15-module-05-interview-plan.md)、[module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md)、[module-16 权限守卫](./2026-09-20-module-16-permission-guard-plan.md)
**本模块被谁依赖**：[module-14 evaluation 反馈](./2026-09-20-module-14-evaluation-feedback-plan.md)、[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)

> **与 module-05 的关系**：module-05 是 interview 模块的 MVP-1 计划书，仍然有效。本文档是**增量**，冲突时以本文档为准。

---

## Global Constraints（全局约束，摘自 PRD）

- **面试状态机保持五态不变**；候选人作答**只是输入通道**，不是状态（§5.1）
- 作答邀请有**独立状态机** `pending → accepted / revoked / expired`，与面试状态**解耦**（§5.1）
- 两个作答通道**共用同一份作答数据**（`answer` 表）：HR 手工录入与候选人在线作答（§4.4）
- 候选人交卷后**其通道锁定**；**HR 侧不受锁影响**，仍可修订（§4.4）
- 交卷后**仍由 HR 确认面试完成**，不自动推进状态（§4.8）
- 邀请码：**有效期默认 7 天、一次性接受、不可枚举、可撤销**（§4.4、§9）
- 邀请码在**系统内展示与复制**，不发送邮件（§1.3）
- 候选人数据隔离：仅能访问**自己被邀请且已接受**的面试（§4.1、§4.6）
- **不含历史版本**：HR 覆盖候选人作答只留最新内容（§5.2）
- 候选人侧路由守卫 `require_roles("candidate")`；HR 侧 `require_roles("admin","hr")`（§4.1、§9）
- 统一响应格式 `{code, message, detail}`（§7）；**仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.4、§4.8）

| 子职责 | 内容 | PRD |
|---|---|---|
| 邀请实体 | `interview_invitation` 表的定义与迁移 | §5.2 |
| 邀请管理（HR） | 生成 / 列表 / 撤销邀请码 | §4.4 |
| 邀请接受（候选人） | 凭码激活、创建或复用账号、绑定面试 | §4.8 |
| 候选人在线作答 | 逐题作答、实时保存、交卷 | §4.8 |
| 作答通道标识 | `answer.source` / `answered_by` / `submitted_at` 的写入规则 | §5.2 |
| **候选人可见性供给契约** | 供本模块各端点与 `evaluation` 复用的「该候选人可访问该面试」判定 | §4.1、§4.6 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **候选人账号的创建逻辑** | 由 `auth.service.create_candidate_account` 实现（[module-09 §5.2](./2026-09-20-module-09-auth-plan.md)）。本模块只负责「凭码触发」，不复制账号创建规则 |
| **作答的历史版本** | PRD §5.2 明确不做。覆盖前的候选人原文不可追溯 |
| **候选人的答题时限 / 倒计时 / 防切屏** | PRD 未要求；引入会牵出计时器状态与前端轮询 |
| **邮件 / 短信发送邀请** | PRD §1.3 明确「邀请码在系统内展示与复制，不发送邮件」 |
| **候选人撤回交卷** | PRD §4.4「交卷后锁定」；需要补答时由 HR 侧回退到 `ongoing` 后重新发邀请（§5.3） |
| **定时任务把过期邀请刷成 `expired`** | 单机约束下不引入调度器；`expired` 改为**读取时派生**（§5.1） |
| 邀请的候选人姓名预填 / 一码多人 | 一条邀请绑定一个候选人账号；一码多投会破坏「作答归属」 |

### 1.3 依赖方向

```
interview.router ──→ interview.service ──→ interview.repository ──→ interview 表族
                          │
                          ├──→ auth.service（create_candidate_account / get_user_by_id）
                          ├──→ position.service / question.service / ai.get_provider()（既有）
                          └──→ core.security（邀请码随机数）

interview ──→ core / auth / position / question / ai（单向，与 MVP-1 一致）
interview ✗→ evaluation（既有约束，module-05 §1.3）
```

> **`evaluation` 如何读取候选人作答**：不需要新增依赖——`answer` 表结构变了但**供给接口不变**（`get_answers_for_evaluation` 仍按 `seq` 升序返回 `QAPair`）。评估层不感知作答来自哪条通道，这是「两条通道共用一份数据」的直接收益。

> **不调用 `auth.service.ensure_owner_match`**：候选人的资源可见性判据是**邀请**而非归属（`candidate_user_id` 在 `interview_invitation` 上，不在 `answer` 上），因此本模块用自己实现的 `get_interview_for_candidate`（§4.5）。`ensure_owner_match` 是 [practice](./2026-09-20-module-13-practice-plan.md) 的需要——它那里有 `practice_session.candidate_user_id` 这类「本人拥有」的资源。**两个函数的分工不能混**。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/interview/models.py` | **改**：新增 `InterviewInvitation` 模型；`Answer` 增三列 |
| `backend/app/interview/schemas.py` | **改**：邀请与候选人侧请求/响应模型 |
| `backend/app/interview/repository.py` | **改**：邀请 CRUD、按候选人取面试、批量补空作答 |
| `backend/app/interview/service.py` | **改**：邀请管理、接受邀请、候选人作答与交卷 |
| `backend/app/interview/candidate_router.py` | **新增**：`/api/candidate/*` 端点（与 HR 端点分文件，避免守卫混用） |

> **为何把候选人端点拆到独立文件**：两组端点的守卫不同（`candidate` vs `admin,hr`）。放在同一 router 里容易在新增端点时挂错守卫 —— 而「挂错守卫」正是 [module-16](./2026-09-20-module-16-permission-guard-plan.md) 要修的问题。按守卫分文件，让「这个文件里的端点都是同一类角色」成为可读的事实。

**测试文件**：`backend/tests/test_interview_invitation.py`（新增）、`backend/tests/test_candidate_answering.py`（新增）

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 `candidate_router`（前缀 `/api`） |
| `backend/alembic/versions/` | 新增迁移：`interview_invitation` 建表 + `answer` 加三列 |
| `backend/script.sql` | 同步上述结构与索引 |
| `backend/app/core/config.py` | 新增 `INVITATION_EXPIRE_DAYS`（默认 7） |
| `backend/.env.example` | 补 `INVITATION_EXPIRE_DAYS=7` |
| `backend/tests/conftest.py` | 新增 `accepted_invitation` 夹具（供 module-14/15 复用） |

---

## 3. 数据模型设计

### 3.1 表 `interview_invitation`（对应 PRD §5.2 的新实体）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, INDEX | 所属面试 |
| `code` | VARCHAR(64) | NOT NULL, **UNIQUE**, INDEX | 邀请码（**明文存储**，见 §3.4） |
| `candidate_user_id` | BIGINT | **NULL**, FK → `user.id` **RESTRICT**, INDEX | 接受后绑定；未接受时为 `NULL` |
| `status` | ENUM('pending','accepted','revoked') | NOT NULL, DEFAULT `'pending'`, INDEX | **只存三个取值**，`expired` 为派生态（§3.3） |
| `expires_at` | DATETIME | NOT NULL | 过期时刻 = `created_at + INVITATION_EXPIRE_DAYS` |
| `accepted_at` | DATETIME | NULL | 接受时刻 |
| `created_by` | BIGINT | NOT NULL, FK → `user.id` **RESTRICT** | 生成人（HR） |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |

**索引**

| 索引 | 字段 | 类型 | 目的 |
|---|---|---|---|
| `uq_interview_invitation_code` | (`code`) | UNIQUE | 凭码查询的唯一路径；同时兜住并发重复生成 |
| `ix_interview_invitation_interview` | (`interview_id`) | INDEX | HR 查看某面试的邀请列表 |
| `ix_interview_invitation_candidate` | (`candidate_user_id`) | INDEX | 候选人端「我参与的面试」列表 |

> **PRD §5.2 的字段列表已含全部字段**，本设计未新增业务字段，只补充了类型、约束与索引。

### 3.2 表 `answer` 的扩展（对应 PRD §5.2）

在 module-05 §3.3 的 `answer` 基础上新增三列：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `source` | ENUM('hr','candidate') | NOT NULL, DEFAULT `'hr'` | **作答最初的来源通道** |
| `answered_by` | BIGINT | **NULL**, FK → `user.id` **RESTRICT** | **最后修改者**；历史行为空（迁移前的数据无此信息） |
| `submitted_at` | DATETIME | **NULL** | **候选人交卷时刻**；HR 手工录入时为 `NULL` |

| 设计要点 | 理由 |
|---|---|
| `source` 默认 `'hr'` | 迁移前的全部作答都由 HR 录入，默认值即历史事实 |
| `answered_by` 允许为 `NULL` | 迁移前的数据无法倒推修改者。设为 NOT NULL 需要伪造一个值（假数据优于空值？否——**空值表示未知，比编造更诚实**） |
| `source` 与 `answered_by` **语义不同、不可合并** | `source` 答「最初从哪条通道进来」，`answered_by` 答「最后是谁改的」。HR 覆盖候选人作答后，`source='candidate'` 而 `answered_by=HR` —— 两个事实都需要保留（PRD §5.2 原文即为此意） |
| **不加 `answer.is_locked`** | 「候选人能否改」由 `submitted_at` 是否为空推导，无需第二个字段表达同一事实。两个字段表达同一状态必然漂移 |

### 3.3 ⚠️ `expired` 是派生态，不落库

PRD §5.1 把 `expired` 列为邀请状态机的一个状态。本设计**不把它写进 `status` 列**：

| 方案 | 问题 |
|---|---|
| 用定时任务把过期邀请刷成 `expired` | 单机约束下需要调度器或后台线程；进程不常驻时任务不执行，状态就会滞后失真 |
| **读取时派生（本设计采用）** | `status == 'pending' and expires_at < now` → 对外呈现 `expired`。`status` 列只存三个**终态**取值 |

| 要点 | 说明 |
|---|---|
| 派生发生在哪一层 | service 组装响应时计算，**repository 只存三个取值**。比较用的「当前时间」由 service 传入而非写死在 SQL，保证可测 |
| 接受邀请时的判定 | **不接受 `expires_at < now` 的邀请**（无论 `status` 是否为 `pending`），抛业务错误 |
| 派生结果是否回写 | **不回写**。写回等于用一次读操作改变状态，会产生「谁先读谁写库」的隐式副作用 |

### 3.4 ⚠️ 邀请码明文存储（需要确认的取舍）

| 方案 | 评价 |
|---|---|
| **明文存储（本设计采用）** | HR 需要**在系统内展示与复制**邀请码（PRD §1.3）。若只存哈希，生成时能显示一次，之后列表页无法再展示 —— 直接与 PRD 冲突 |
| 只存哈希 | 安全性更好，但违背 PRD 的展示要求；且 HR 体验上要「重新生成」才能再拿到码 |

**缓解措施（全部已在设计中）**：码长足够（§5.2）、有效期默认 7 天、一次性接受、可随时撤销、候选人侧接口不泄露面试是否存在（§6）。

> **该取舍已记入 §10 风险表**：数据库泄露即等同于邀请泄露，这是明文存储的代价。

---

## 4. 接口契约

### 4.1 对外 REST API

**HR 侧（守卫 `require_roles("admin","hr")`）**

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| POST | `/api/interviews/{id}/invitations` | 生成作答邀请码 | 201 |
| GET | `/api/interviews/{id}/invitations` | 邀请列表与状态 | 200 |
| DELETE | `/api/interviews/{id}/invitations/{inv_id}` | 撤销邀请 | 200 |

> **不用 204**：撤销后前端需要展示该条的最终状态（`revoked`），返回更新后的对象比空响应更有用。与既有 `DELETE /questions/{id}` 的 204 不同，此处有明确的响应内容。

**公开（无守卫）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/candidate/invitations/{code}/accept` | 凭邀请码激活并绑定面试 |

> ⚠️ **本端点是公开的，不要求 JWT**（PRD §4.1 / §8）：拿码的人往往**还没有账号**，
> 要求他先登录才能激活会让邀请链自相矛盾 —— 没有账号就拿不到 token，没有 token 就激活不了。
> 关闭自助注册（`CANDIDATE_SELF_REGISTER=false`）时它是新人的**唯一入口**，必须可用。
>
> 它虽然挂在 `/api/candidate` 前缀下，但**不属于**下面那组 `candidate` 守卫端点 ——
> 前缀是给人看的分类，守卫是逐个端点挂的。**权限扫测必须把它排除**（见
> [module-16](./2026-09-20-module-16-permission-guard-plan.md) §3.1）。

**候选人侧（守卫 `require_roles("candidate")`，前缀 `/api/candidate`）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/candidate/interviews` | 我参与的面试列表 |
| GET | `/api/candidate/interviews/{id}` | 面试详情（仅题目与我自己的作答） |
| POST | `/api/candidate/interviews/{id}/answers` | 保存 / 更新我的作答（交卷后拒绝） |
| POST | `/api/candidate/interviews/{id}/submit` | 交卷（幂等） |

> **第 6 个候选人端点 `/feedback` 属 `evaluation` 包**（读的是报告），见 [module-14](./2026-09-20-module-14-evaluation-feedback-plan.md)。它同样注册在 `/api/candidate` 前缀下，但由 `evaluation/candidate_router.py` 提供。

### 4.2 请求 / 响应结构

**POST `/api/interviews/{id}/invitations`** → 201

| 方向 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 请求 | — | — | 无请求体；`expires_at` 由配置项推导 |
| 响应 | `id` | int | — |
| 响应 | `interview_id` | int | — |
| 响应 | `code` | str | 邀请码，**明文返回**，供 HR 复制 |
| 响应 | `status` | str | `pending` \| `accepted` \| `revoked` \| **`expired`（派生）** |
| 响应 | `expires_at` | datetime | — |
| 响应 | `accepted_at` | datetime \| null | — |
| 响应 | `candidate_username` | str \| null | 已接受时联表返回，便于 HR 核对是谁接受的 |
| 响应 | `created_at` | datetime | — |

**GET `/api/interviews/{id}/invitations`** → 邀请对象数组（字段同上），按 `created_at` 倒序。

**DELETE `/api/interviews/{id}/invitations/{inv_id}`** → 200，返回更新后的邀请对象。

| 规则 | 行为 |
|---|---|
| 只能撤销 `pending` 的邀请 | 撤销 `accepted` 的 → 409「已接受的邀请不可撤销」（撤销它等于把候选人挡在面试外，应改用其他手段） |
| 撤销 `revoked` 的 | **幂等**：返回既有对象，不报错 |
| 撤销已过期的 | 允许（把 `pending` 置为 `revoked`），语义上等于「不再重发」 |

**POST `/api/candidate/invitations/{code}/accept`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `username` | str | 必填，1–50 字符（候选人**已注册**时可与既有账号同名） |
| 请求 | `password` | str | 必填，**最少 8 字符**（账号不存在时用于创建；已存在且角色为 candidate 时**忽略**，见 §5.3） |
| 响应 | `interview_id` | int | 绑定的面试 |
| 响应 | `interview` | object | 面试摘要（`id` / `position_name` / `candidate_name` / `status` / `question_count`） |
| 响应 | **不含 `token`** | — | 与注册一致：登录态由 `/auth/login` 单独获取 |

**GET `/api/candidate/interviews`** → 列表项：`id`、`position_name`、`status`、`question_count`、`answered_count`、`submitted`(bool)、`created_at`。

**GET `/api/candidate/interviews/{id}`** → 详情：

| 字段 | 说明 |
|---|---|
| `id` / `position_name` / `status` / `created_at` | 面试摘要 |
| `submitted` | 我是否已交卷（= 我的作答是否已有 `submitted_at`） |
| `submitted_at` | 交卷时刻或 `null` |
| `questions` | 题目数组：`interview_question_id`、`seq`、`content`(**取 `content_snapshot`**)、`dimension`(**取 `dimension_snapshot`**)、`my_answer`(str \| null) |
| **不含** | HR 的评语、评分、其他候选人的作答、`created_by` 等 HR 侧信息 |

> **候选人看到的是快照，不是题库当前值**：`content_snapshot` 只含题干（module-05 §3.2），因此**天然不含参考答案**。这是既有设计带来的安全收益，本模块不改变它。

**POST `/api/candidate/interviews/{id}/answers`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `interview_question_id` | int | 必填，必须属于该面试 |
| 请求 | `content` | str | 允许空串（表示未作答）；≤ 10000 字符（与 HR 通道一致） |
| 响应 | `interview_question_id` | int | — |
| 响应 | `content` | str | — |
| 响应 | `submitted_at` | datetime \| null | 已交卷时非空 |

> **候选人的作答响应里没有「作答来源」字段**：对候选人而言「谁写的」不是一个有意义的信息（只可能是他自己）。**作答来源只在 HR 侧视图出现**，且在那里命名为 **`answer_source`**——因为 HR 的题目项对象已有 `source`（题目来源快照，`bank`/`ai`），两个同名字段会被混淆。命名规则见 [module-05 §4.2](./2026-09-15-module-05-interview-plan.md)。

**POST `/api/candidate/interviews/{id}/submit`** → 200

| 方向 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 请求 | — | — | 无请求体 |
| 响应 | `interview_id` | int | — |
| 响应 | `submitted_at` | datetime | 交卷时刻（幂等：重复调用返回**首次**交卷时刻） |
| 响应 | `answered_count` | int | 实际有内容的作答数（不含交卷时补的空串） |

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_invitation(db, user, interview_id) -> InterviewInvitation` | 邀请 | 校验可见性与状态 → 生成码 → 落库 |
| `list_invitations(db, user, interview_id) -> list[InvitationView]` | 列表 | 可见性校验；**派生 `expired`** |
| `revoke_invitation(db, user, interview_id, invitation_id) -> InvitationView` | 邀请 | 含 §4.2 的三条规则 |
| `accept_invitation(db, user, code, username, password) -> InvitationAcceptResult` | 面试摘要 | 校验码 → 建/复用账号 → 绑定 → 置 `accepted` |
| `list_my_interviews(db, user) -> list[CandidateInterviewItem]` | 列表 | 仅 `accepted` 且绑定本人 |
| `get_interview_for_candidate(db, user, interview_id) -> Interview` | Interview | **候选人可见性判定的唯一入口**（§4.5） |
| `get_candidate_interview_detail(db, user, interview_id) -> CandidateInterviewDetail` | 详情 | 经上一条校验后组装 |
| `save_candidate_answer(db, user, interview_id, interview_question_id, content) -> CandidateAnswerView` | 作答 | 交卷后拒绝（§5.4） |
| `submit_interview(db, user, interview_id) -> SubmitResult` | 交卷结果 | 幂等；补齐未作答的空串（§5.5） |

沿用（不改）：`create_interview`、`list_interviews`、`get_interview`、`update_interview`、`save_answer`、`complete_interview`、`rollback_interview`、`get_answers_for_evaluation`、`get_evaluation_dimensions`、`get_position_id`、`transition_to_*`。

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create_invitation(db, **fields) -> InterviewInvitation` | 邀请 | — |
| `get_invitation_by_code(db, code: str) -> InterviewInvitation \| None` | 邀请 | 不带权限过滤（权限在 service） |
| `get_invitation_by_id(db, invitation_id: int) -> InterviewInvitation \| None` | 邀请 | 同上 |
| `list_invitations(db, interview_id: int) -> list[InterviewInvitation]` | 列表 | 按 `created_at` 倒序 |
| `list_accepted_interviews_for_candidate(db, candidate_user_id: int) -> list[tuple[Interview, InterviewInvitation]]` | 列表 | 候选人端列表；联表取 `position_name` |
| `get_accepted_invitation(db, interview_id: int, candidate_user_id: int) -> InterviewInvitation \| None` | 邀请 | **候选人可见性判定的数据源**（§4.5） |
| `update_invitation(db, invitation, **fields) -> InterviewInvitation` | 邀请 | — |
| `upsert_answer(db, interview_question_id, content, **extra) -> Answer` | Answer | **扩展现有方法**：接受 `source` / `answered_by` / `submitted_at` |
| `bulk_upsert_empty_answers(db, entry_ids: list[int], submitted_at, answered_by: int) -> None` | — | **新增**：交卷时给未作答的题补空串（§5.5） |

> **`upsert_answer` 的扩展方式**：现有实现（HR 通道）只传 `content`。扩展为接受可选的关键字参数，HR 通道**不传** `source`/`answered_by`（走模型默认 `source='hr'`），候选人通道显式传 `source='candidate'`、`answered_by=user.id`。这样 HR 通道的调用点**一行都不用改**。

### 4.5 候选人可见性供给契约（**本模块最重要的产出**）

PRD §4.1 要求候选人的隔离判据是「持有该面试的有效邀请」，而不是 `created_by`。该判据只有一处实现：

```
get_interview_for_candidate(db, user, interview_id) -> Interview
  1. 面试不存在                        → NotFoundError（404）
  2. 该用户无 accepted 邀请（或邀请已撤销） → ForbiddenError（403）
  3. 返回面试
```

| 规则 | 说明 |
|---|---|
| **所有候选人端点必须经此函数取面试** | 包括 module-14 的 `/feedback`。任何直接 `repository.get_by_id` 的写法都会绕过隔离 |
| **不接受 `pending` 邀请** | 仅 `accepted` 且 `candidate_user_id == user.id` 才算绑定 |
| 已撤销的邀请 → 403 | 撤销后候选人不能再访问该面试（即使曾 `accepted`）。**这使撤销具备实际效力**：HR 撤销已接受的邀请即可切断访问 |
| 不使用 `ensure_resource_visible` | 该函数基于 `created_by`（[module-01 §5.3](./2026-09-15-module-01-auth-plan.md)），且对 candidate 角色会直接抛错（[module-16 §4](./2026-09-20-module-16-permission-guard-plan.md)）。候选人的判据必须独立实现 |

**对 evaluation 的契约不变**：`get_answers_for_evaluation` / `get_evaluation_dimensions` / `get_position_id` / `transition_to_*` 的签名与语义**均不改动**。`answer` 加列不影响读取路径。

---

## 5. 业务流程设计

### 5.1 邀请生命周期

```
生成 → pending ─┬─ 候选人凭码接受 → accepted ── 绑定账号
                ├─ HR 撤销         → revoked
                └─ 超过 expires_at → expired（派生，不落库）
```

| 迁移 | 触发 | 副作用 |
|---|---|---|
| （新建）→ `pending` | HR 生成 | 写 `code` / `expires_at` |
| `pending` → `accepted` | 候选人接受 | 写 `candidate_user_id` / `accepted_at` |
| `pending` → `revoked` | HR 撤销 | — |
| `pending` → `expired` | **派生**：读取时 `expires_at < now` | 无数据库写入 |

**终态不可迁移**：`accepted` / `revoked` 不再变化。**例外**：`accepted` 的邀请可被撤销（用于切断访问，§4.5）；撤销后 `status` 仍为 `accepted` 但**不再计入可见性判定**。

> 这条例外必须写清楚：若把已接受的邀请改为 `revoked`，就丢失了「谁在何时接受了」这一事实（`candidate_user_id` / `accepted_at` 仍在，但状态自相矛盾）。改为：**可见性判定额外排除「存在 revoked 记录」的情形**，即同一 (`interview_id`, `candidate_user_id`) 只要有一条 `revoked` 邀请，访问即被拒绝。实现上等价于在 `get_accepted_invitation` 中加一个 `NOT EXISTS(revoked)` 条件。

### 5.2 生成邀请（HR）

```
1. 取面试并做可见性校验（复用既有 _get_visible：404 / 403）
2. 校验 status == 'ongoing'
     draft      → 409「请先完成出题」      （还没有题目，邀请无意义）
     completed 及以上 → 409「请先回退到进行中再发邀请」
3. 生成 code：secrets.token_urlsafe(16)     → 22 个 URL-safe 字符（约 128 位熵）
4. 循环查重：code 已存在则重新生成（UNIQUE 索引兜并发）
5. expires_at = now + INVITATION_EXPIRE_DAYS
6. 落库，status='pending'，created_by=HR
7. 返回明文 code（供复制）
```

| 要点 | 说明 |
|---|---|
| **同一面试允许多条邀请** | 重发、给不同候选人的场景都需要。不为「一面试一邀请」加唯一约束 |
| **邀请的有效性与面试状态绑定** | 只有 `ongoing` 能发。面试一旦 `completed`，作答通道本就不接受写入（§5.4 复用 `ongoing` 校验），此时邀请已无意义，提前拦住比让候选人白答一场更友好 |
| 码长与熵 | `token_urlsafe(16)` 给出 128 位熵，不可枚举（PRD §9 要求） |
| 不加「同一候选人只能有一条邀请」约束 | 候选人身份在生成时未知（`candidate_user_id` 为空）；接受时统一由 §5.3 的规则处理 |

### 5.3 接受邀请（候选人）

```
1. 按 code 查邀请
     不存在 / 已 revoked / 已 accepted / expires_at < now
       → BusinessError（409）「邀请码无效或已失效」   ← 四种情况同一文案，见下
2. 调 auth.service.create_candidate_account(db, username, password)
     新用户名 → 创建 role='candidate' 账号
     已有同名 candidate → **校验 password 一致**才复用；不符 → UnauthorizedError（401）
                          「用户名或密码错误」（与登录失败同一文案）
     已有同名 hr/admin → BusinessError（409）「用户名已被占用」
3. 若该候选人此前已有一条 accepted 邀请指向同一面试
       → BusinessError（409）「你已接受过该面试的邀请」
4. 写 candidate_user_id / accepted_at，status 置 'accepted'
5. commit；返回面试摘要（不含 token）
```

| 设计决策 | 说明 |
|---|---|
| **四种失效原因同一文案** | 「邀请码无效或已失效」。区分「不存在」与「已过期」等于提供一个码探测接口（PRD §7 明确「不泄露面试是否存在」）。**注意**：这不适用于「用户名已被占用」「已接受过该面试」这两条——它们发生在码校验**之后**，此时码已确定有效，泄露面为零 |
| **复用账号时必须校验密码**（2026-09-21 修正） | 原先是「忽略密码」，理由是不让「凭邀请码重置他人密码」。但它换来的是**更糟的一条**：知道对方用户名就能把自己的邀请码绑到对方账号上，进而读到对方的面试。改为「密码一致才复用」后**两个风险同时消掉**。密码不符返回 401「用户名或密码错误」（与登录失败同一文案），不新增可区分信号；残余的「用户名是否存在」可探测性只对**持有有效邀请码**的人成立，而邀请码一次性、高熵、私发，无法规模化（PRD §7） |
| **本端点为公开端点**（2026-09-21 修正） | 见 §4.1 的说明：新人没有账号就拿不到 token，要求先登录会让邀请链自相矛盾 |
| **账号创建委托给 auth** | 不在 interview 里复制「用户名唯一性 / 密码哈希 / 角色约束」规则（[module-09 §5.2](./2026-09-20-module-09-auth-plan.md)） |
| 不接受 `pending` 之外的状态 | 一次性接受：同一码第二次接受必然落在「已 accepted」分支并报错 |
| 第 3 步的必要性 | 否则同一候选人可用第二条码重复接受同一面试，产生两条绑定记录，候选人端列表出现重复项 |

### 5.4 候选人在线作答

```
save_candidate_answer(db, user, interview_id, interview_question_id, content):
1. interview = get_interview_for_candidate(db, user, interview_id)   ← 404 / 403
2. 校验 status == 'ongoing'
     否则 → BusinessError（409）「当前状态下不可作答」
3. 校验该面试尚未被该候选人交卷
     该面试下本人任一条作答的 submitted_at 非空
       → BusinessError（409）「已交卷，不可修改作答」
4. 校验 interview_question_id 属于该面试
      不属于 → NotFoundError（404）
5. repository.upsert_answer(
       interview_question_id, content,
       source='candidate', answered_by=user.id, submitted_at=None)
6. commit；返回该题的作答视图
```

| 要点 | 说明 |
|---|---|
| **复用既有的 `ongoing` 限定** | 与 HR 通道同一条规则（module-05 §5.3）。理由也相同：评估依据的数据不能在评估期间漂移 |
| **第 3 步用「本人任一条作答的 `submitted_at`」判定交卷** | 交卷时会给**全部**题写 `submitted_at`（§5.5），因此「任一条非空」等价于「本人已交卷」 |
| `submitted_at` 显式传 `None` | 交卷前作答**不应**带上交卷时间；显式传参避免依赖默认值语义 |
| 不校验答案是否为空串 | 空串是合法的「暂不作答」，与既有 `AnswerCreate` 的约定一致 |
| 候选人**不能**改 `source` | 由 service 决定，请求体不接受该字段（与 `QuestionCreate` 不接收 `source` 同一手法） |

### 5.5 交卷与锁定（⚠️ 本模块最需要想清楚的一步）

**问题**：PRD §5.2 把 `submitted_at` 放在 `answer` 行上，但「交卷」是**面试级**事实。若候选人第 5 题没作答，就没有第 5 题的 `answer` 行，交卷时间无处可存。

| 方案 | 评价 |
|---|---|
| **交卷时给未作答的题补空串作答行，并给全部行写 `submitted_at`（本设计采用）** | ① 单一事实来源，不引入冗余字段；② 交卷后**每道题都有作答行**，评估取数不必处理缺失；③ 空串在既有约定中正是「未作答，按 0 分处理」（module-05 §4.2 的 `AnswerCreate` 注释） |
| 在 `interview_invitation` 上加 `submitted_at` | 语义更贴切，但偏离 PRD §5.2 的字段位置，且与 `answer` 上的 `submitted_at` 形成两个「交卷时间」——必然漂移 |
| 只在已作答的行上写 `submitted_at` | 未作答时无处记录交卷，候选人无法交卷（或交卷后仍可改未作答的题） |

```
submit_interview(db, user, interview_id):
1. interview = get_interview_for_candidate(db, user, interview_id)   ← 404 / 403
2. 若本人已交卷（任一条 submitted_at 非空）
       → 幂等：直接返回首次交卷时刻与当前计数，不重复写入
3. 校验 status == 'ongoing' → 否则 BusinessError（409）「当前状态下不可交卷」
4. submitted_at = now
5. 取该面试的全部 interview_question
6. bulk_upsert_empty_answers(未作答的题的 id, submitted_at, answered_by=user.id)
7. 给已作答的行写 submitted_at（同一次事务）
8. commit；返回 { interview_id, submitted_at, answered_count }
```

| 要点 | 说明 |
|---|---|
| **幂等在第 2 步短路** | PRD §8 要求「交卷（幂等）」。重复调用返回**首次**时刻，而不是刷新它 |
| 幂等检查先于状态检查 | 已交卷时面试状态可能已被 HR 推进到 `completed`，此时仍应返回成功而非 409 —— 否则前端重试会看到一个自相矛盾的错误 |
| `answered_count` 不含补的空串 | 它回答的是「候选人答了几题」，不是「有几条记录」。空串行是为交卷完整性而补的 |
| **交卷不改面试状态** | PRD §5.1 的明确取舍。HR 仍需手动 `/complete` |
| 补空串的语义 | 「候选人选择不作答」。评估时按 0 分处理（既有约定），与「没记录」的区别在于：现在有明确的事实——**他确实选择了不作答** |

### 5.6 HR 覆盖候选人作答（既有端点，无需改动）

| 场景 | 行为 |
|---|---|
| HR 在 `ongoing` 下修改某题作答 | 复用既有 `save_answer`（module-05 §5.3）：更新 `content` 与 `recorded_at`，**`source` 保持 `candidate`**，`answered_by` 改为 HR 的 id，**`submitted_at` 保留** |
| 覆盖后候选人还能改吗 | **不能**。锁定判据是 `submitted_at` 非空，与谁最后修改无关 |
| HR 覆盖未作答的空串 | 同样允许；该行本就有 `submitted_at`（§5.5 补的），覆盖后仍是「已交卷」状态 |
| 需要让候选人重答 | HR 先 `/rollback` 回 `ongoing`，再撤销旧邀请、发新邀请并入 `accepted`。**这是本设计为「候选人撤回交卷」提供的唯一通道**（PRD 未要求直接撤回） |

> **`save_answer` 需不需要改**：不需要。它只写 `content` 与 `recorded_at`，不触碰新增三列，因此 `source` / `submitted_at` 自然保留。**这正是「只加列、不改语义」的收益**。

### 5.7 状态机（**不改**）

module-05 §5.4 的状态迁移表**一行不变**。本次只在其操作矩阵中新增两行（见下），不新增迁移。

| 操作 | draft | ongoing | completed | evaluating | evaluated |
|---|---|---|---|---|---|
| **候选人作答 / 交卷（MVP-2 新增行）** | ✗ | ✓ | ✗ | ✗ | ✗ |
| **生成 / 撤销邀请（MVP-2 新增行）** | ✗ | ✓（撤销任意状态下允许） | ✗ | ✗ | ✗ |

> 候选人作答与 HR 写回答共用同一条 `ongoing` 限定，这不是巧合——**两条通道写的是同一份数据**，对数据的写入约束自然应当一致。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在（候选人通道同样返回 404，由 `get_interview_for_candidate` 决定） |
| 无 accepted 邀请 / 邀请已撤销 | `FORBIDDEN` | 403 | 无权限访问该面试 |
| 邀请码无效 / 已过期 / 已撤销 / 已接受 | `BUSINESS_ERROR` | 409 | 邀请码无效或已失效（**四种同一文案**） |
| 接受邀请时用户名已被 hr/admin 占用 | `BUSINESS_ERROR` | 409 | 用户名已被占用 |
| 已接受过该面试的邀请 | `BUSINESS_ERROR` | 409 | 你已接受过该面试的邀请 |
| 非 `ongoing` 状态发邀请 | `BUSINESS_ERROR` | 409 | 当前状态下不可生成邀请，请先将面试置为进行中 |
| 撤销已接受的邀请 | `BUSINESS_ERROR` | 409 | 已接受的邀请不可撤销 |
| 非 `ongoing` 状态候选人作答 / 交卷 | `BUSINESS_ERROR` | 409 | 当前状态下不可作答 |
| 交卷后候选人再改作答 | `BUSINESS_ERROR` | 409 | 已交卷，不可修改作答 |
| `interview_question_id` 不属于该面试 | `NOT_FOUND` | 404 | 题目不属于该面试 |
| 作答超 10000 字符 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 密码不足 8 位（接受邀请时） | `VALIDATION_ERROR` | 400 | 密码长度不能少于 8 位 |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `backend/tests/test_interview_invitation.py`（新增）

**生成**

| 测试 | 断言 |
|---|---|
| `test_create_invitation_ok` | 201，`status='pending'`，`code` 长度 ≥ 22，`expires_at ≈ now + 7 天` |
| `test_create_invitation_codes_are_unique` | 连续生成 20 次，`code` 两两不同 |
| `test_create_invitation_requires_ongoing` | `draft` / `completed` / `evaluated` → 409 |
| `test_create_invitation_other_users_interview_forbidden` | 403 |
| `test_create_invitation_multiple_allowed` | 同一面试可生成多条，列表全部返回 |

**撤销**

| 测试 | 断言 |
|---|---|
| `test_revoke_pending_ok` | 200，`status='revoked'` |
| `test_revoke_accepted_rejected` | 409，message 为「已接受的邀请不可撤销」 |
| `test_revoke_revoked_is_idempotent` | 二次撤销 → 200，状态不变，不报错 |
| `test_revoked_invitation_cannot_be_accepted` | 409 |
| `test_revoke_cuts_access_of_accepted_candidate` | 先接受（可访问）→ 撤销 → 候选人再访问该面试 → **403**（§5.1 的例外规则） |

**派生过期**

| 测试 | 断言 |
|---|---|
| `test_status_pending_before_expiry` | `expires_at` 在未来 → 列表项 `status == 'pending'` |
| `test_status_expired_after_expiry` | 把 `expires_at` 手工改为过去 → 列表项 `status == 'expired'` |
| `test_expired_is_not_persisted` | 同一场景下**数据库 `status` 列仍为 `'pending'`**（派生不回写） |
| `test_accept_expired_invitation_rejected` | 409，文案与「码不存在」一致 |

**接受**

| 测试 | 断言 |
|---|---|
| `test_accept_creates_candidate_account` | 新用户名 → 账号创建为 `candidate`，邀请转 `accepted`，绑定 `candidate_user_id` |
| `test_accept_reuses_existing_candidate_account` | 已存在同名 candidate → 复用同一 id，**不新建、密码不变** |
| `test_accept_rejects_hr_username` | 同名 hr 账号 → 409「用户名已被占用」，且**邀请仍为 `pending`**（不得部分写入） |
| `test_accept_twice_same_code_rejected` | 二次接受同一码 → 409 |
| `test_accept_second_code_same_interview_rejected` | 同一候选人接受指向同一面试的第二条码 → 409 |
| `test_accept_unknown_code_message_matches_expired` | 未知码与过期码的**错误码与文案完全一致**（不泄露） |
| `test_accept_response_has_no_token` | 响应**不含** `token` |
| `test_accept_does_not_leak_interview_existence` | 上述四条失效场景的响应中**不出现**面试名、岗位名等任何面试信息 |

### 7.2 `backend/tests/test_candidate_answering.py`（新增）

**可见性**

| 测试 | 断言 |
|---|---|
| `test_candidate_lists_only_accepted_interviews` | 只返回本人 `accepted` 的面试；`pending` 的不出现 |
| `test_candidate_cannot_access_pending_invitation_interview` | 未接受 → 403 |
| `test_candidate_cannot_access_other_candidates_interview` | 候选人 A 访问 B 的面试 → 403 |
| `test_candidate_detail_hides_hr_fields` | 详情响应**不含** `created_by` / 评分 / 评语 / 其他候选人作答 |
| `test_candidate_detail_uses_snapshots` | 修改题库题干后，候选人详情仍显示 `content_snapshot` 原值 |

**作答**

| 测试 | 断言 |
|---|---|
| `test_save_candidate_answer_ok` | 200；库中该行 `source='candidate'`、`answered_by=候选人 id`、`submitted_at IS NULL` |
| `test_save_candidate_answer_only_ongoing` | `completed` 下 → 409 |
| `test_save_candidate_answer_after_submit_rejected` | 交卷后 → 409「已交卷，不可修改作答」 |
| `test_save_candidate_answer_other_question_rejected` | 传别的面试的 `interview_question_id` → 404 |
| `test_save_candidate_answer_ignores_source_in_body` | 请求体传 `source='hr'` 被忽略，库中仍为 `candidate` |
| `test_save_candidate_answer_empty_string_allowed` | 空串 → 200 |
| `test_hr_can_save_answer_after_candidate_submitted` | HR 在候选人交卷后仍可写 → 200（**关键：锁定只对候选人侧生效**） |

**交卷**

| 测试 | 断言 |
|---|---|
| `test_submit_writes_submitted_at_to_all_questions` | 3 题答了 1 题 → 交卷后**3 行**均有 `submitted_at`，未答的两行为空串 |
| `test_submit_answered_count_excludes_blank` | 答了 1 题 → `answered_count == 1`（不是 3） |
| `test_submit_is_idempotent` | 二次提交 → 200，`submitted_at` 与首次**完全相同** |
| `test_submit_after_hr_completed_returns_success` | 交卷 → HR `/complete` → 候选人再次提交 → **200 而非 409**（幂等检查先于状态检查） |
| `test_submit_does_not_change_interview_status` | 交卷后面试状态仍为 `ongoing`（PRD §5.1） |
| `test_submit_other_candidates_interview_forbidden` | 403 |
| `test_submitted_answer_is_read_by_evaluation_as_zero` | 交卷后走评估：未作答的题得 0 分（空串约定） |

**HR 覆盖**

| 测试 | 断言 |
|---|---|
| `test_hr_overwrite_keeps_source_candidate` | 覆盖后 `source` 仍为 `candidate`，`answered_by` 为 HR，`submitted_at` 保留 |
| `test_hr_overwrite_keeps_candidate_locked` | 覆盖后候选人再改 → 仍 409 |
| `test_evaluation_unchanged_by_new_columns` | 加列后 `get_answers_for_evaluation` 返回值与 MVP-1 行为一致 |

### 7.3 权限

| 测试 | 断言 |
|---|---|
| `test_invitation_endpoints_reject_candidate` | 候选人对三个 HR 邀请端点 → 403 |
| `test_candidate_endpoints_reject_hr_and_admin` | hr / admin 对 `/api/candidate/*` → 403（[module-09 §4.5](./2026-09-20-module-09-auth-plan.md) 的精确匹配规则） |
| `test_invitation_endpoints_reject_anonymous` | 无 token → 401 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-09（`require_roles`、`create_candidate_account`）、module-16（存量路由守卫）已完成。

### Task 12.1：模型与迁移

- [ ] `models.py` 新增 `InterviewInvitation`；`Answer` 增 `source` / `answered_by` / `submitted_at`
- [ ] 生成迁移（建表 + 加三列 + 索引），同步 `backend/script.sql`
- [ ] 写失败测试：`answer.source` 默认 `'hr'`；`answered_by` / `submitted_at` 可为 NULL
- [ ] `alembic upgrade head` / `downgrade` 验证
- [ ] 提交

### Task 12.2：配置项

- [ ] `core/config.py` 新增 `invitation_expire_days`（默认 7）；`.env.example` 补键
- [ ] 写失败测试：默认值 7，可由环境变量覆盖
- [ ] 提交

### Task 12.3：repository 层

- [ ] 实现 §4.4 的邀请相关方法
- [ ] 扩展 `upsert_answer` 接受可选 `source` / `answered_by` / `submitted_at`
- [ ] 新增 `bulk_upsert_empty_answers`
- [ ] 写失败测试：`get_accepted_invitation` 对 pending / revoked 返回 `None`
- [ ] 运行确认通过
- [ ] 提交

### Task 12.4：HR 邀请管理

- [ ] 写 §7.1 中生成 / 撤销 / 派生过期 / 列表的失败测试
- [ ] 运行确认失败
- [ ] 实现三个 service 方法与 `/interviews/{id}/invitations` 三端点
- [ ] 运行确认通过
- [ ] 提交

### Task 12.5：候选人可见性供给契约

- [ ] 写失败测试：`get_interview_for_candidate` 对未接受 / 已撤销 / 他人 → 403；不存在 → 404；已接受 → 返回
- [ ] 运行确认失败
- [ ] 实现 `get_interview_for_candidate`（**含「存在 revoked 即拒绝」的例外规则**）
- [ ] 运行确认通过
- [ ] 提交

### Task 12.6：接受邀请

- [ ] 写 §7.1 中接受相关的失败测试（**含四种失效同文案、拒绝 hr 同名、不泄露面试存在性**）
- [ ] 运行确认失败
- [ ] 实现 `accept_invitation` 与 `/candidate/invitations/{code}/accept`
- [ ] 创建 `candidate_router.py` 并在 `main.py` 注册
- [ ] 运行确认通过
- [ ] 提交

### Task 12.7：候选人作答与交卷

- [ ] 写 §7.2 中作答 / 交卷 / HR 覆盖的失败测试（**含幂等先于状态检查、补空串、answered_count 不含空串**）
- [ ] 运行确认失败
- [ ] 实现 `save_candidate_answer` / `submit_interview` / `list_my_interviews` / `get_candidate_interview_detail` 与四个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 12.8：夹具与全量回归

- [ ] `conftest.py` 新增 `accepted_invitation`（含候选人账号与已绑定邀请）
- [ ] 运行 `pytest tests/ -q`，**全部既有用例零回归**（重点：`test_interview.py` 62 条、`test_evaluation*.py`）
- [ ] 提交

---

## 9. 验收标准

- [ ] `interview_invitation` 表建成，`code` 唯一；`answer` 三列加好，`source` 默认 `'hr'`
- [ ] 邀请码不可枚举（≥ 128 位熵）、有效期默认 7 天且可配置
- [ ] **`expired` 不落库**：库中 `status` 只有三个取值，过期由读取派生
- [ ] 邀请只在 `ongoing` 面试上可生成；撤销已接受的邀请被拒（409）
- [ ] 已接受的邀请被撤销后，候选人**立即无法再访问**该面试（403）
- [ ] 接受邀请：新建 candidate 账号或复用既有 candidate 账号；**拒绝**同名 hr/admin（409）
- [ ] 四种邀请失效原因返回**同一**错误码与文案；响应不泄露面试任何信息
- [ ] 候选人只能看到自己被 `accepted` 的面试；详情不含 HR 字段与参考答案
- [ ] 候选人作答仅在 `ongoing` 且未交卷时允许；`source`/`answered_by` 由服务端写入，请求体不可指定
- [ ] 交卷：给全部题写 `submitted_at`（未答的补空串）；**幂等**；**不改面试状态**
- [ ] 交卷后候选人侧锁定，**HR 侧仍可覆盖**且 `source` 保留 `candidate`
- [ ] 评估读取路径（`get_answers_for_evaluation`）行为不变
- [ ] 候选人侧六端点对 hr/admin 一律 403；HR 侧三端点对 candidate 一律 403
- [ ] 未新增任何错误码；既有用例零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **`submitted_at` 放在 `answer` 行上，但交卷是面试级事实** | 交卷时给未作答的题补空串并给全部行写 `submitted_at` | 单一事实来源；空串在既有约定中正是「未作答」。代价是交卷会多写若干行（题量 ≤ 8，可忽略） |
| **邀请码明文存储** | 明文（§3.4） | PRD 要求「系统内展示与复制」，存哈希与之直接冲突。缓解：长码、短有效期、一次性、可撤销 |
| **`expired` 不落库** | 读取时派生，不回写 | 单机约束下不引入调度器；回写会让读操作产生副作用 |
| **已接受的邀请可被撤销以切断访问** | 保留 `status='accepted'`，但可见性判定额外排除存在 `revoked` 邀请的情形 | 若把状态改成 `revoked`，会丢失「谁在何时接受」的事实，且状态与 `accepted_at` 自相矛盾 |
| 交卷幂等检查**先于**状态检查 | 先判幂等 | 已交卷后 HR 可能已 `/complete`，若先判状态会返回 409，让前端重试看到自相矛盾的错误 |
| 接受邀请时的密码参数在复用账号时被忽略 | 忽略 | 否则「凭邀请码重置他人密码」成为越权路径 |
| HR 覆盖后 `source` 保留 `candidate` | 保留 | `source` 答「最初来源」，`answered_by` 答「最后修改者」，两个不同事实（PRD §5.2） |
| 候选人撤回交卷 | 不提供直接通道；走「HR 回退 → 撤销旧邀请 → 发新邀请」 | PRD 未要求；直接撤回会让「交卷」变成可逆状态，削弱锁定的意义 |
| 候选人端点拆到 `candidate_router.py` | 拆文件 | 与 HR 端点守卫不同；同文件混放易在新增端点时挂错守卫 |
| `answer.answered_by` 允许 NULL | 允许 | 迁移前的数据无法倒推修改者；空值表示未知，优于编造 |
