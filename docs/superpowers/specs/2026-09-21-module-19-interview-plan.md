# interview 模块执行计划书（MVP-3 简历关联、按简历补题、面试前准备助手）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：interview（在既有出题 / 记录 / 状态机 / 邀请之上，新增简历关联、按简历补题、面试前准备助手）
**所属包**：`backend/app/interview/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.4（出题组装的延伸）、§4.11（面试前准备助手）、§4.13（候选人关联简历）、§4.14（简历匹配补题）、§5.2（三处表结构变更）、§5.3 ⑥⑦、§7（错误）、§8（端点）、§9（分层）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-05 interview](./2026-09-15-module-05-interview-plan.md)、[module-12 interview 邀请](./2026-09-20-module-12-interview-invitation-plan.md)、[module-16 权限守卫](./2026-09-20-module-16-permission-guard-plan.md)、[module-17 resume](./2026-09-21-module-17-resume-plan.md)、[module-18 ai](./2026-09-21-module-18-ai-plan.md)
**本模块被谁依赖**：[module-23 HR 前端](./2026-09-21-module-23-hr-frontend-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **简历由候选人提供**，因此关联动作由**候选人**发起，**不是** HR 创建面试时指定（§4.13）
- **简历进入出题流程的唯一通路**是按简历补题；匹配**不发生在创建面试时**（§4.4、§4.14）
- 按简历补题**只追加、不改动既有题目**；`source_snapshot='resume_match'`，理由写入 `match_reason`（§4.4、§4.14）
- **出题组装后不提供换题 / 删题接口**（沿用既有约束）；**补题是唯一的加题例外**，且**不提供撤销**（§4.4、§4.14）
- 补题前置：面试 `ongoing` **且** `resume_id` 非空，否则 **409**（§4.14、§7）
- 准备助手**不进入面试状态机**；只在 `draft` / `ongoing` 可生成与编辑，`completed` 及之后 **409**（§4.11、§5.1）
- 准备助手产出**三部分整体返回、整体覆盖**，**不做字段级合并、不做版本历史、不做流式**（§4.11、§5.2）
- 候选人只能在**本人已接受邀请**的面试上操作；**只有 `ongoing` 允许变更简历关联**（§4.13、§4.6）
- HR 读取候选人简历的判据是**「该面试属于自己」**（`created_by`），复用既有 `_get_visible`，**不引入新机制**（§4.10、§9）
- `source_snapshot` 是 **Enum 列**，新增取值需 **`ALTER TABLE ... MODIFY COLUMN`**（§5.2）
- **仍是单机 PC 端，技术栈不变、不引入新依赖**（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| 候选人关联简历 | `PUT /candidate/interviews/{id}/resume`，写 `interview.resume_id`（可传 `null` 解除） | §4.13 |
| HR 读取关联简历 | `GET /interviews/{id}/resume`，只读、含 `updated_at` | §4.10 |
| 按简历补题 | `POST /interviews/{id}/questions/match`，AI 从题库挑选并**追加** | §4.14 |
| 匹配理由回传 | 补题的 `match_reason` 写入并在 HR 题目视图下发 | §4.4 |
| 准备助手生成 | `POST /interviews/{id}/prep`，调 AI 生成三部分并落库（覆盖） | §4.11 |
| 准备助手查看 / 编辑 | `GET` / `PUT /interviews/{id}/prep` | §4.11 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **简历的增删改查** | 属 `resume`（module-17）。本模块只调它的两个契约方法，**不直接读简历表** |
| **AI 匹配与准备提纲的生成规则** | 属 `ai`（module-18）。本模块只负责取候选池、传参、落库 |
| **候选池的取法** | 复用 `question_service.list_candidates_for_position`（module-10 既有供给），**不新增取题逻辑** |
| **候选人侧看到匹配理由** | PRD §4.6 只允许候选人看到「题目与自己提交的作答」。`match_reason` **不下发**给候选人 |
| **补题的撤销 / 批量删除** | PRD §4.14 明确「不提供撤销接口」 |
| **准备助手的版本历史 / 差异对比** | PRD §5.2 明确「一场面试唯一，重新生成即覆盖」 |
| **准备助手的流式生成** | PRD §4.11 明确「一次生成即整批落库，不做流式」 |
| **把准备助手纳入状态机** | PRD §5.1 的明确取舍 |
| **`interview_question` 的换题 / 删题** | 沿用既有约束，补题只追加 |
| **简历的自动关联**（如凭邀请自动挑一份） | PRD §4.13 要求候选人**显式**指定；自动挑会在候选人有多个简历时产生意外 |

### 1.3 依赖方向

```
                       ┌──→ question.service（list_candidates_for_position）
interview.router ──→ interview.service ──→ interview.repository ──→ interview 表族
                       ├──→ resume.service（load_unchecked / ensure_mine）      ← 新增依赖边
                       ├──→ position.service（get_position）
                       ├──→ auth.service（ensure_resource_visible / scope_owner_id）
                       └──→ ai.factory.get_provider()

interview ──→ core / auth / position / question / resume / ai（单向）
interview ✗→ evaluation / practice（既有禁止不变）
```

> **本次只新增一条依赖边 `interview → resume`**，且 `resume` 不反向依赖任何业务模块（module-17 §1.3），因此**不会形成循环**。架构测试的 `FORBIDDEN_DEPENDENCIES["interview"]` 是 `{evaluation, practice}`，**本来就不含 `resume`**，故无需改动该集合。

---

## 2. 文件结构

| 文件 | 单一职责 | 本次改动 |
|---|---|---|
| `backend/app/interview/models.py` | 表结构 + 状态 / 来源常量 | **改**：`Interview` 加 `resume_id`；`InterviewQuestion` 加 `match_reason`、**Enum 加取值**；新增 `InterviewPrep` 表；新增 `SOURCE_RESUME_MATCH` 常量 |
| `backend/app/interview/schemas.py` | 请求 / 响应模型 | **改**：新增 **10 个模型**（清单见 §4.2 末）；`QuestionItem` 加 `match_reason`；`InterviewDetail` 加 `resume_id` |
| `backend/app/interview/repository.py` | 纯 CRUD | **改**：新增 6 个方法 |
| `backend/app/interview/service.py` | 业务编排 | **改**：新增 6 个方法 + 2 个内部辅助 |
| `backend/app/interview/router.py` | HR 侧端点 | **改**：新增 **5 个端点** |
| `backend/app/interview/candidate_router.py` | 候选人侧端点 | **改**：新增 **1 个端点** |

**测试文件**

| 文件 | 本次改动 |
|---|---|
| `backend/tests/test_interview.py` | **改**：新增简历关联 / 补题 / 准备助手三组用例 |
| `backend/tests/test_e2e_flows.py` | **改**：新增流程 ⑥⑦ 的端到端用例 |
| `backend/tests/conftest.py` | **改**：新增 `interview_prep` 相关夹具 |

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/app/core/config.py` | 新增 `resume_match_count` | §3.3 |
| `backend/app/question/service.py` | **无改动**（复用既有 `list_candidates_for_position`） | — |

> **不写 alembic 迁移、不同步 `backend/script.sql`**（PRD §11）。但 ⚠️ **本模块的 DDL 变更里有一条不是「加列」而是「改 Enum 类型」**，见 §3.2——它在统一收口时最容易被漏掉。

---

## 3. 数据模型设计

### 3.1 `interview` 表：新增 `resume_id`（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `resume_id` | BIGINT | **NULL**, FK → `resume.id` **RESTRICT** | 该面试关联的候选人简历；NULL = 尚未关联 |

| 决策 | 理由 |
|---|---|
| **`RESTRICT` 而非 `SET NULL`** | `SET NULL` 会让「简历被删 → 面试静默失去简历」而不报错。`RESTRICT` 让删除方（候选人）收到 409，自己决定怎么处理（module-17 §5.4） |
| **NULL 允许** | 关联是可选动作。未关联时补题报 409、准备助手走无简历分支，都是有定义的路径 |
| **写入方是候选人**（不是 HR） | PRD §4.13。因此 HR 创建面试的请求体**不接受** `resume_id`（module-17 §4.1 与 PRD §8 均已写明） |

> **`interview.resume_id` 存在 `interview` 包、`resume.created_by` 指向候选人**：这两个事实共同构成「HR 能读到候选人简历」的路径，而 HR 的读取判据落在**面试的归属**上（§1.3、§5.2），不在简历的归属上。

### 3.2 `interview_question` 表：新增 `match_reason` + **Enum 加取值**（对应 PRD §5.2）

**（a）新增列**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `match_reason` | TEXT | NULL | AI 给出的匹配理由；**非 `resume_match` 来源的题为 NULL** |

**（b）⚠️ 已有 `source_snapshot` 是 Enum 列，需改类型**

```python
# 现状（models.py:121-123）
source_snapshot: Mapped[str] = mapped_column(
    Enum(SOURCE_BANK, SOURCE_AI, name="interview_question_source"), nullable=False
)
```

| 项 | 内容 |
|---|---|
| 目标 | `Enum(SOURCE_BANK, SOURCE_AI, SOURCE_RESUME_MATCH, name="interview_question_source")` |
| 新增常量 | `SOURCE_RESUME_MATCH = "resume_match"`（加在 `models.py` 的 `SOURCE_BANK` / `SOURCE_AI` **旁边**——它们已经定义在那里，见 `models.py:36-37`） |
| **DDL 性质** | **不是 ADD COLUMN，而是 `ALTER TABLE interview_question MODIFY COLUMN source_snapshot ENUM('bank','ai','resume_match') NOT NULL`** |

> ⚠️ **这是 MVP-3 里唯一一处「改既有列的取值域」，而不是「加列」。** 统一收口建表时若只按「新增了哪些列/表」来收集 DDL，**必然会漏掉它**，后果是补题时写入 `resume_match` 直接抛 `DataError: Data truncated for column`。
>
> **为什么用 Enum 而不是改成 VARCHAR**：改成 VARCHAR 会让「来源」失去取值约束，历史上 Enum 挡住的那类脏数据将不再被数据库拒绝。**为加一个取值而放松整体约束，代价大于一次 `MODIFY COLUMN`。**

> **`match_reason` 与 `source_snapshot='resume_match'` 成对出现**（PRD §5.2）：前者存理由，后者标来源。非匹配来源的题 `match_reason` 为 NULL——因此「有没有理由」与「是不是匹配来的」两个事实不会漂移。

### 3.3 新增表 `interview_prep`（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | — |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, **UNIQUE** | **一场面试唯一** |
| `outline` | JSON | NOT NULL | 面试提纲：`[{seq, phase, duration_min, notes}]` |
| `focus_points` | JSON | NOT NULL | 考察重点：`[{dimension, point, reason}]` |
| `question_plan` | JSON | NOT NULL | 问题预案：`[{question, intent, follow_ups: []}]` |
| `generated_at` | DATETIME | NOT NULL | **最近一次 AI 生成**时刻 |
| `edited_at` | DATETIME | NULL | HR **最近一次手工编辑**时刻；重新生成时置回 NULL |

| 决策 | 理由 |
|---|---|
| **`interview_id` 加 UNIQUE** | PRD §5.2「一场面试唯一」。用唯一约束而不是「查询时取最新」，让「不可能有两条」成为数据库事实 |
| **FK 用 `CASCADE`** | 面试删除时其准备提纲一并消失。与 `interview_question` / `answer` 的 `CASCADE` 一致（`models.py:108`、`:196`） |
| **三个 JSON 列 NOT NULL** | 三部分**要么都有要么都没有**（module-18 §5.3 的「三部分任一为空即整批失败」）。允许 NULL 会引入「有记录但某部分缺失」这一无意义状态 |
| **三个 JSON 列在模型层给 `default=list`，但表上无 DEFAULT** | MySQL 的 JSON 列**不支持字面量 DEFAULT**。因此默认值只能在 Python 侧给（用于裸构造），实际写入永远显式供值 |
| **`edited_at` 在重新生成时置回 NULL** | 「AI 重新生成」意味着 HR 之前的编辑**已被整体覆盖**。留着旧的 `edited_at` 会让前端显示「已手工编辑」，而实际内容已是 AI 的 |
| **不放 `created_by`** | 能读写它的只有面试的拥有者（§5.5），而面试本身已有 `created_by`。再加一列会引入「两个 created_by 不一致怎么办」的伪问题 |

### 3.4 新增配置项

| 配置键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `resume_match_count` | int | `3` | 按简历补题的默认追加题数（PRD §4.14 的「默认 3」）；请求体可覆盖，上限 20 |

> **为什么是配置而 `count` 上限不是**：默认题数是**产品可调**的量（题太少展示不出效果、太多让面试过长）；上限 20 是接口卫生，由 schema 的 `Field(le=20)` 固定即可。

---

## 4. 接口契约

### 4.1 对外 REST API

**HR 侧**（守卫 `require_roles(admin, hr)`，沿用既有 `_hr_guard`）

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| GET | `/api/interviews/{id}/resume` | 读取该面试关联的候选人简历（未关联则 404） | 200 |
| POST | `/api/interviews/{id}/questions/match` | 按简历从题库补题（追加） | 200 |
| POST | `/api/interviews/{id}/prep` | 生成 / 重新生成准备提纲（整体覆盖） | 200 |
| GET | `/api/interviews/{id}/prep` | 查看准备提纲（未生成则 404） | 200 |
| PUT | `/api/interviews/{id}/prep` | 编辑准备提纲（整体覆盖三部分） | 200 |

> 共 **5 个** HR 端点（PRD §8 表中 prep 三个、resume 一个、match 一个）。

**候选人侧**（守卫 `require_roles("candidate")`，沿用既有 `_candidate_guard`）

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| PUT | `/api/candidate/interviews/{id}/resume` | 为本人已接受的面试关联 / 解除关联我的一份简历 | 200 |

**补题为什么是 POST 而不是 PUT**：它会**追加**数据（每次调用都改变结果），不是幂等替换。用 PUT 会让调用方以为重复调用无副作用。

### 4.2 请求 / 响应结构

**`InterviewResumeOut`（HR 只读视图）**

| 字段 | 下发 | 说明 |
|---|---|---|
| `resume_id` | ✓ | — |
| `title` / `content` | ✓ | 正文全文（HR 需要看内容才能判断匹配） |
| `candidate_name` / `candidate_contact` | ✓ | 可能为 null |
| `updated_at` | ✓ | **HR 据此判断手上这份是否最新**（module-17 §3.1 的用途） |
| `created_by` / `created_at` | **✗** | HR 不需要知道候选人的 user id |

**`POST /api/interviews/{id}/questions/match`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `count` | int \| 可选 | 缺省 `resume_match_count`；`Field(ge=1, le=20)` |
| 响应 | `added_count` | int | 本次实际追加的题数（可能为 0） |
| 响应 | `added` | array | 追加项：`interview_question_id` / `seq` / `content` / `dimension` / `match_reason` |
| 响应 | `total_questions` | int | 追加后本场题目总数（供前端提示） |

> **`added_count == 0` 是正常结果**（200），不是错误：AI 认为候选池里没有更相关的题了。前端提示「未匹配到新题目」。

**`PrepOut`（查看 / 生成 / 编辑的统一响应）**

| 字段 | 说明 |
|---|---|
| `interview_id` | — |
| `outline` | `[{seq, phase, duration_min, notes}]` |
| `focus_points` | `[{dimension, point, reason}]` |
| `question_plan` | `[{question, intent, follow_ups}]` |
| `generated_at` / `edited_at` | `edited_at` 为 null 表示当前内容是 AI 原样产出 |

**`PUT /api/interviews/{id}/prep`** 请求体：`outline` / `focus_points` / `question_plan` **三个字段全部必填**。

> **为什么编辑必须整体提交三部分**：PRD §5.2 明确「三个 JSON 字段整体替换，不做字段级合并」。允许部分提交就需要回答「没提交的那部分保留还是清空」，而这个问题的答案在不同场景下不同。**整体替换让语义唯一。**

**`PUT /api/candidate/interviews/{id}/resume`** 请求体：`resume_id: int | null`（`null` = 解除关联）。

**`QuestionItem` 的改动**

| 字段 | 变化 | 说明 |
|---|---|---|
| `match_reason` | **新增**，`str \| None = None` | 仅 HR 侧视图。非匹配来源的题为 null |

**`CandidateQuestionItem` 的改动**

| 变化 | 说明 |
|---|---|
| **无变化** | `match_reason` **不下发给候选人**（PRD §4.6 只允许候选人看到题目与自己提交的作答） |

> ⚠️ **这一条必须显式断言**：`match_reason` 会描述「候选人简历的哪段经历对应这道题」，属于 HR 的评估思路。若图省事复用了 HR 的 schema，就会把它泄露给候选人。**测试里必须有一条「候选人详情响应不含 match_reason 键」。**

**`InterviewDetail` 的改动**：新增 `resume_id: int | None = None`（供 HR 界面判断是否已关联）。

> ⚠️ **回归风险**：给既有响应模型加字段可能影响断言「响应键集合」的既有用例。执行时须先跑 `test_interview.py` 确认，若有断言精确键集的用例，按新增字段更新。

**本次新增的 10 个 schema（`interview/schemas.py`，供 §2 与 Task 19.2 对照）**

| # | 名称 | 用途 |
|---|---|---|
| 1 | `InterviewResumeOut` | HR 读简历的响应（§5.2） |
| 2 | `ResumeLinkRequest` | 候选人关联请求体：`{resume_id: int \| null}`（§5.1） |
| 3 | `MatchRequest` | 补题请求体：`{count: int \| null}`（§5.3） |
| 4 | `MatchAddedItem` | 补题响应中的单条追加项（§4.2） |
| 5 | `MatchResult` | 补题响应：`added_count` / `added: list[MatchAddedItem]` / `total_questions` |
| 6 | `PrepOutlineStageOut` | 提纲阶段（§3.3 的 JSON 元素） |
| 7 | `PrepFocusPointOut` | 考察重点项 |
| 8 | `PrepQuestionItemOut` | 问题预案项（含 `follow_ups`） |
| 9 | `PrepOut` | 准备助手查看 / 生成 / 编辑的统一响应 |
| 10 | `PrepUpdate` | 准备助手编辑请求体（三部分全必填） |

> `MatchResult.added` 直接内联 `list[MatchAddedItem]`，**不另建列表包装类型**——多一个无人使用的模型只会增加维护面。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 侧 | 职责 |
|---|---|---|---|
| `link_resume(db, user, interview_id: int, resume_id: int \| None) -> InterviewResumeOut \| None` | 简历视图 / None | 候选人 | 关联或解除（§5.1） |
| `get_interview_resume(db, user, interview_id: int) -> InterviewResumeOut` | 简历视图 | HR | 只读，含 `updated_at`（§5.2） |
| `match_questions_by_resume(db, user, interview_id: int, count: int) -> MatchResult` | 补题结果 | HR | 取池 → 调 AI → 追加（§5.3） |
| `generate_prep(db, user, interview_id: int) -> PrepOut` | 准备提纲 | HR | 调 AI → 落库（覆盖）（§5.4） |
| `get_prep(db, user, interview_id: int) -> PrepOut` | 准备提纲 | HR | 未生成 → 404（§5.5） |
| `update_prep(db, user, interview_id: int, data: PrepUpdate) -> PrepOut` | 准备提纲 | HR | 整体覆盖三部分（§5.5） |

**新增内部辅助**

| 签名 | 说明 |
|---|---|
| `_briefs(questions) -> list[QuestionBrief]` | ORM `Question` → `ai.QuestionBrief`（**`ai` 只收原始值的适配点**，§4.6） |
| `_prep_view(prep: InterviewPrep) -> PrepOut` | ORM → 响应模型 |

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `list_question_ids(db, interview_id: int) -> set[int]` | 本场已有的 `question_id` 集合 | **补题幂等的依据** |
| `max_seq(db, interview_id: int) -> int` | 本场最大 `seq`（无题时为 0） | 追加时续接 |
| `get_prep_by_interview(db, interview_id: int) -> InterviewPrep \| None` | 准备提纲 | **不带权限过滤**（与既有约定一致） |
| `create_prep(db, **fields) -> InterviewPrep` | 准备提纲 | — |
| `update_prep(db, prep: InterviewPrep, **fields) -> InterviewPrep` | 准备提纲 | — |
| `get_resume_id_of_interview(db, interview_id: int) -> int \| None` | `interview.resume_id` | 集中一处读该列 |

> **为什么 `get_resume_id_of_interview` 单列一个方法**：`interview.resume_id` 会被「HR 读简历」「补题」「准备助手」三处读取。散着写 `interview.resume_id` 没问题，但**没有集中的地方可以加「未关联时统一如何表现」的注释**。集中一处便于后续统一行为。

### 4.5 跨包契约

**本模块消费 `resume`（module-17 §4.5）**

| 调用 | 用在哪 | 为什么是它 |
|---|---|---|
| `resume.service.load_unchecked(db, resume_id)` | HR 读简历、补题取文本、准备助手取文本 | HR 读的是**候选人的**简历，`ensure_owner_match` 必然失败 |
| `resume.service.ensure_mine(db, user, resume_id)` | 候选人关联简历时校验归属 | 候选人只能关联**自己的**简历 |

> ⚠️ **禁止 `interview` 直接 import `resume.repository`**。架构测试的 `test_router_goes_through_service` 用的是 `_own_module_refs(path, module)`，**只统计同模块内的引用**——跨模块跳层**不会被任何测试拦住**（module-17 §4.5 已详述）。这是本模块最需要靠评审守住的一条。

**本模块消费 `question`（既有）**

| 调用 | 用途 |
|---|---|
| `question_service.list_candidates_for_position(db, user.id, position.id)` | 补题的候选池。**与既有出题组装用同一个供给**，因此「题库题能不能被选中」的口径完全一致 |

### 4.6 `ai` 适配点（`ai` 只收原始值）

```python
def _briefs(questions) -> list[QuestionBrief]:
    return [QuestionBrief(question_id=q.id, content=q.content,
                          dimension=q.dimension, category=q.category)
            for q in questions]
```

> **这是 `interview → ai` 之间的唯一转换点**。`ai` 层的 6 个新 dataclass（module-18 §3.1）不能接收 ORM 对象，因此每次调用 `match_questions_by_resume` / `generate_interview_prep` 前必须经此转换。
>
> **例外**：`match` 的 `resume_text` 取 `resume.content`（**已是 str**），不需要转换——它不经过 `_briefs`。

---

## 5. 业务流程设计

### 5.1 候选人关联简历到面试（PRD §4.13）

```
link_resume(db, user, interview_id, resume_id):
1. interview = get_interview_for_candidate(db, user, interview_id)
       ← 复用既有的「持有效邀请」判定（service.py:623），不另写判据
2. 若 interview.status != STATUS_ONGOING → BusinessError(409)
       「面试已结束，不可变更简历关联」
3. 若 resume_id is None:
       interview.resume_id = None; commit; return None
4. resume = resume_service.ensure_mine(db, user, resume_id)     ← 404 / 403 由它抛
5. interview.resume_id = resume.id
6. commit；返回 InterviewResumeOut(resume)
```

| 决策 | 理由 |
|---|---|
| **只看 `ongoing`，不用黑名单** | 用「非 ongoing 一律拒绝」的白名单，而不是「completed 及之后拒绝」。`draft` 对候选人本就不可达（`create_invitation` 与 `accept_invitation` 都要求 `ongoing`），但 `evaluating` / `evaluated` 是可达的（HR 可先 complete 再评估）。黑名单写法容易漏 `evaluating` 这一态，白名单不会 |
| **`resume_id=None` 是解除，不是「不修改」** | 请求体是 `int \| null` 且字段必填，因此 `null` 只能是显式的「解除关联」。若允许缺省，就无法区分「没传」和「要清空」——这与 module-17 §5.3 对可选字段的处理相反，因为在这里**清空是有意义的动作** |
| **不改面试状态** | 关联简历是准备动作，不推进状态机（PRD §5.1） |
| **不校验简历「是否适合这个岗位」** | 系统没有这个判据，也不该猜 |

### 5.2 HR 读取关联简历（PRD §4.10）

```
get_interview_resume(db, user, interview_id):
1. interview = _get_visible(db, user, interview_id)
       ← HR 归属校验（created_by），**这就是全部权限判据**
2. resume_id = repository.get_resume_id_of_interview(db, interview_id)
3. 若为 None → NotFoundError(404)「该面试尚未关联简历」
       ← 前端据此显示「候选人尚未提交简历」，不是「无权限」
4. resume = resume_service.load_unchecked(db, resume_id)
5. 防御：若 None → NotFoundError(404)
6. 返回 InterviewResumeOut(resume)
```

| 决策 | 理由 |
|---|---|
| **权限判据只有「面试属于我」** | 简历是通过 `interview.resume_id` 关联进来的，而候选人只能关联**自己被邀请的**面试、HR 只能读**自己创建的**面试。两条链叠加即构成完整隔离，**不需要新增 auth 函数** |
| **第 5 步的防御是必要的（虽然理论上不可达）** | `interview.resume_id` 的外键是 `RESTRICT`，被引用的简历删不掉，因此 `load_unchecked` 不该返回 None。但**依赖「外键不会失效」来保证非空，是一个跨三层的隐式假设**；一行防御换来「即使假设失效也只是 404 而不是 500」 |
| **未关联返回 404 而非空对象** | 前端需要区分「没关联」与「关联了但内容为空（不可能，`content` NOT NULL）」 |

### 5.3 按简历补题（PRD §4.14）—— **本模块的核心流程**

```
match_questions_by_resume(db, user, interview_id, count):
 1. interview = _get_visible(db, user, interview_id)
 2. 若 interview.status != STATUS_ONGOING → BusinessError(409)
       「当前状态下不可按简历补题」
 3. resume_id = repository.get_resume_id_of_interview(db, interview_id)
    若为 None → BusinessError(409)「该面试尚未关联简历」
 4. resume = resume_service.load_unchecked(db, resume_id)
    防御：None → BusinessError(409)「该简历已不可用」
 5. position = repository.get_position(db, interview.position_id)
    dims = list(position.evaluation_dimensions)
    若为空 → BusinessError(409)「岗位未定义评估维度，无法补题」
 6. existing_ids = repository.list_question_ids(db, interview_id)
 7. candidates = question_service.list_candidates_for_position(db, user.id, position.id)
    candidates = _filter_valid_candidates(candidates, dims)          ← 复用既有
    candidates = [q for q in candidates if q.id not in existing_ids] ← 幂等依据
    若为空 → BusinessError(409)「题库中没有可补充的题目」
 8. matched = get_provider().match_questions_by_resume(
        resume_text=resume.content,
        position_name=position.name,
        jd=position.jd,
        dims=dims,
        candidates=_briefs(candidates),
        count=count,
    )
 9. 若 matched 为空 → 返回 MatchResult(added=[], added_count=0,
                                    total_questions=len(existing_ids))   ← 200，不是错误
10. by_id = {q.id: q for q in candidates}          ← 只认候选池内的 id
    seq = repository.max_seq(db, interview_id)
    items = []
    for m in matched:                              ← 顺序即相关度顺序
        q = by_id.get(m.question_id)
        if q is None: continue                     ← 双保险（ai 层已过滤，此处不信任）
        seq += 1
        items.append({interview_id, question_id=q.id, seq=seq,
                      content_snapshot=q.content,
                      dimension_snapshot=q.dimension,
                      source_snapshot=SOURCE_RESUME_MATCH,
                      match_reason=m.reason})
    created = repository.create_questions(db, items)
11. commit；返回 MatchResult(added=_added_view(created), added_count=len(created),
                            total_questions=len(existing_ids) + len(created))
```

**⚠️ 「幂等」的准确含义（最容易被误解的一处）**

| 说法 | 对不对 |
|---|---|
| 「重复调用不会产生重复题目」 | ✅ **对**。第 7 步把本场已有题从候选池里剔除，AI 不可能再挑到它们 |
| 「重复调用不会有任何效果」 | ❌ **错**。候选池变小了，AI 会挑**下一批**尚不存在的题，因此**每次调用都会再加 `count` 题**，直到池子耗尽 |

> **这是 PRD §4.14「可重复触发：候选人换了简历、或 HR 想再补几题，都可再次调用」的直接后果**——PRD 有意允许累加。
>
> **对前端的含义**：按钮点击**会产生累加**，因此界面必须显示「本场共 N 题」，并在响应里回 `added_count` 让前端提示「本次新增 3 题」。**不显示总数的话，HR 连点几次会以为界面卡了。**
>
> **若将来认为累加不可接受**，正确的修法是引入「已补过」标记（需要新的状态字段），而不是把候选池过滤去掉——后者会破坏幂等。PRD 目前未定义该标记。

| 决策 | 理由 |
|---|---|
| **第 7 步用 `list_candidates_for_position`（同出题组装）** | 出题与补题必须口径一致，否则会出现「同一个岗位，出题时能抽到的题、补题时抽不到」这种无法解释的差异 |
| **第 7 步的 `_filter_valid_candidates` 复用既有的** | 岗位维度改过之后的历史题应被剔除——这个判断在出题组装里已有，不该有第二份实现 |
| **第 10 步再查一次 `by_id`** | `ai` 层已保证 id 来自池内（module-18 §5.3）。此处**再挡一次**是刻意的冗余：`ai` 是抽象接口，将来换实现（新 Provider、或 Mock 被改）时不能假定它守约 |
| **`seq` 续接而非重排** | 既有题目已有作答挂在 `interview_question.id` 上，重排 `seq` 会打乱 HR 已录入的作答顺序。且 `uq_interview_question_seq` 唯一约束不允许重号 |
| **不新建题库题目** | 匹配**只挑不生成**（PRD §6）。因此**不调用** `question_service.bulk_create_from_ai` |
| **`added_count == 0` 返回 200** | AI 认为没有更相关的题是**正当结论**，不是故障。「没有」与「坏了」必须可区分（module-18 §5.3 同一原则） |
| **候选池为空 → 409** | 与 `added_count == 0` 不同：这里根本没东西可挑，属于**前置条件不满足**（通常意味着该岗位题库太小或本场已把题用尽），报错比返回 0 更有信息量 |
| **AI 失败原样抛 `AIProviderError`** | PRD §7「本次补题不生效，不动既有题目、不改面试状态」。因为**第 10-11 步在任何写入之前**，所以抛错时数据库无任何改动——**不需要额外回滚逻辑** |

### 5.4 准备助手生成（PRD §4.11）

```
generate_prep(db, user, interview_id):
1. interview = _get_visible(db, user, interview_id)
2. 若 interview.status not in (STATUS_DRAFT, STATUS_ONGOING) → BusinessError(409)
       「面试已进入评估或已完成，不可再生成准备提纲」
3. position = repository.get_position(db, interview.position_id)
   dims = list(position.evaluation_dimensions)
   若为空 → BusinessError(409)「岗位未定义评估维度，无法生成准备提纲」
4. resume_text = None
   resume_id = repository.get_resume_id_of_interview(db, interview_id)
   若 resume_id 非空:
       resume = resume_service.load_unchecked(db, resume_id)
       resume_text = resume.content if resume else None
5. questions = _briefs(repository.list_questions(db, interview_id))   ← 可能为空
6. result = get_provider().generate_interview_prep(
        position_name=position.name, jd=position.jd, dims=dims,
        candidate_name=interview.candidate_name,
        resume_text=resume_text, questions=questions)
7. prep = repository.get_prep_by_interview(db, interview_id)
   若 prep is None:
       repository.create_prep(db, interview_id=..., outline=[...], focus_points=[...],
                              question_plan=[...], generated_at=_now(), edited_at=None)
   否则:
       repository.update_prep(db, prep, outline=..., focus_points=..., question_plan=...,
                              generated_at=_now(), edited_at=None)   ← 覆盖，且抹掉编辑标记
8. commit；返回
```

| 决策 | 理由 |
|---|---|
| **`draft` 也允许生成** | PRD §4.11 明确「`draft` / `ongoing` 时可生成与编辑」。`draft` 只在出题组装失败时短暂出现，但**允许**比「拒绝」少一个特例分支 |
| **第 6 步在任何写入之前** | AI 失败时数据库无改动，因此**准备助手不需要「生成失败则回滚/保留旧值」的补偿逻辑**——旧值自然还在（第 7 步没执行） |
| **第 7 步 `edited_at=None`** | 重新生成覆盖了 HR 的编辑，标记必须同步清除。否则界面会显示「已手工编辑」而内容其实是 AI 的（§3.3） |
| **`questions` 允许为空** | PRD §4.11「本场已有题目（可能为空）」。module-18 §4.2 的 Mock 会按维度补足 |
| **不落 `resume_text` 快照** | 准备提纲里已含从简历提取的内容。再存一份简历原文会让「简历更新后提纲是否要变」成为新问题——PRD 未定义，故不引入 |

### 5.5 准备助手查看与编辑

```
get_prep(db, user, interview_id):
1. _get_visible(db, user, interview_id)
2. prep = repository.get_prep_by_interview(db, interview_id)
3. 若 None → NotFoundError(404)「尚未生成准备提纲」   ← 前端据此显示「生成」按钮
4. 返回 _prep_view(prep)

update_prep(db, user, interview_id, data):
1. interview = _get_visible(db, user, interview_id)
2. 若 interview.status not in (STATUS_DRAFT, STATUS_ONGOING) → BusinessError(409)
3. prep = repository.get_prep_by_interview(db, interview_id)
   若 None → NotFoundError(404)                 ← 编辑一份不存在的提纲是错误用法
4. repository.update_prep(db, prep, outline=data.outline,
                          focus_points=data.focus_points,
                          question_plan=data.question_plan,
                          edited_at=_now())     ← generated_at **不变**
5. commit；返回
```

| 决策 | 理由 |
|---|---|
| **404 而不是「自动创建」** | 若编辑时不存在就自动建，则「生成」与「编辑」会产生同一条记录的两条路径，且 `generated_at` 无从取值。**先 `POST` 生成、再 `PUT` 编辑**是显式且唯一的顺序 |
| **`generated_at` 不被编辑改动** | 它回答「这份提纲是哪次 AI 生成的」，编辑不改这个问题 |
| **`edited_at` 每次编辑刷新** | 它回答「HR 最后一次动它是什么时候」 |
| **编辑也受状态限制** | PRD §4.11 明确「`completed` 及之后拒绝生成与编辑」 |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在 |
| 面试不属于当前 HR | `FORBIDDEN` | 403 | 无权限访问该面试（既有 `ensure_resource_visible`） |
| 候选人未持有该面试的有效邀请 | `FORBIDDEN` | 403 | 无权限访问该面试（既有 `get_interview_for_candidate`） |
| 关联非本人的简历 | `FORBIDDEN` | 403 | 无权限访问该简历（`ensure_mine` 抛） |
| 关联不存在的简历 | `NOT_FOUND` | 404 | 简历不存在（`ensure_mine` 抛） |
| 面试非 `ongoing` 时变更简历关联 | `BUSINESS_ERROR` | 409 | 面试已结束，不可变更简历关联 |
| 面试未关联简历时读取简历 | `NOT_FOUND` | 404 | 该面试尚未关联简历 |
| 面试未关联简历时补题 | `BUSINESS_ERROR` | 409 | 该面试尚未关联简历 |
| 面试非 `ongoing` 时补题 | `BUSINESS_ERROR` | 409 | 当前状态下不可按简历补题 |
| 岗位未定义评估维度（补题 / 生成提纲） | `BUSINESS_ERROR` | 409 | 岗位未定义评估维度，无法… |
| 候选池为空（补题） | `BUSINESS_ERROR` | 409 | 题库中没有可补充的题目 |
| 补题时 AI 失败 | `AI_PROVIDER_ERROR` | **502** | AI 服务调用失败（既有错误码）。**数据库无改动** |
| 准备助手未生成时读取 / 编辑 | `NOT_FOUND` | 404 | 尚未生成准备提纲 |
| 面试非 `draft`/`ongoing` 时生成或编辑准备提纲 | `BUSINESS_ERROR` | 409 | 面试已进入评估或已完成，不可再生成准备提纲 |
| 生成提纲时 AI 失败 | `AI_PROVIDER_ERROR` | **502** | AI 服务调用失败。**旧提纲保留不变** |
| 编辑时三部分任一缺失 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 补题 `count` 越界（<1 或 >20） | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 守卫角色不符 | `FORBIDDEN` | 403 | 无权限执行此操作（module-16） |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。
>
> **两个 502 的语义差别（必须在测试中区分）**：
> - 补题 AI 失败 → 502，**本场题目数不变**
> - 生成提纲 AI 失败 → 502，**已有提纲内容不变**（若是首次生成则仍不存在）

---

## 7. 测试设计（对应 PRD §10）

### 7.1 候选人关联简历（§5.1）

| 测试 | 断言 |
|---|---|
| `test_link_resume_ok` | 写库后 `interview.resume_id == resume.id` |
| `test_link_resume_null_unlinks` | 先关联再传 `null` → `resume_id` 为 None |
| `test_link_resume_other_candidates_resume_403` | 候选人 A 关联 B 的简历 → 403，**且 `resume_id` 未变** |
| `test_link_resume_missing_resume_404` | 不存在的 `resume_id` → 404 |
| `test_link_resume_without_invitation_403` | 未被邀请的面试 → 403 |
| `test_link_resume_after_completed_409` | 面试 `completed` → 409 |
| `test_link_resume_during_evaluating_409` | 面试 `evaluating` → 409（**白名单写法的关键覆盖**） |
| `test_link_resume_during_evaluated_409` | 面试 `evaluated` → 409 |
| `test_link_resume_does_not_change_interview_status` | 关联后 `status` 不变 |
| `test_link_resume_replaces_previous` | 先后关联两份简历 → `resume_id` 为后者 |

### 7.2 HR 读取关联简历（§5.2）

| 测试 | 断言 |
|---|---|
| `test_get_interview_resume_ok` | HR 读到自己面试关联的简历，字段完整 |
| `test_get_interview_resume_unlinked_404` | 未关联 → 404（**不是 403**） |
| `test_get_interview_resume_other_hrs_interview_403` | hr_b 读 hr_a 面试的简历 → 403 |
| `test_get_interview_resume_excludes_created_by` | 响应**不含** `created_by` 键 |
| `test_get_interview_resume_has_updated_at` | 响应含 `updated_at` |
| `test_get_interview_resume_rejects_candidate` | 候选人 token → 403 |

### 7.3 按简历补题（§5.3）—— **本模块最重要的测试组**

| 测试 | 断言 |
|---|---|
| `test_match_appends_questions` | 追加后本场题目数 == 原数 + `added_count` |
| `test_match_sets_source_and_reason` | 追加项的 `source_snapshot == 'resume_match'`，`match_reason` 非空 |
| `test_match_seq_continues` | 追加项 `seq` 从既有最大值 +1 起，连续无重号 |
| `test_match_does_not_touch_existing_questions` | 既有题目的 `content_snapshot` / `source_snapshot` / `match_reason`（应仍为 NULL）**全不变** |
| `test_match_without_resume_409` | `resume_id` 为空 → 409「该面试尚未关联简历」 |
| `test_match_non_ongoing_409` | `completed` / `evaluating` / `evaluated` / `draft` → 409 |
| `test_match_excludes_questions_already_in_interview` | 构造「本场已有题恰是 AI 最相关的题」→ 它**不出现在**追加结果中 |
| `test_match_repeated_call_adds_new_questions_only` | 连调两次 → 两次追加的 `question_id` **无交集**；总数为 原 + n1 + n2 |
| `test_match_repeated_call_never_duplicates` | 连调三次后，本场 `question_id` **无重复**（幂等的核心断言） |
| `test_match_exhausts_pool_then_409` | 候选池被补尽后再调 → 409「题库中没有可补充的题目」 |
| `test_match_ai_returns_empty_gives_200` | Mock 返回空 → 200，`added_count == 0`，**题目数不变** |
| `test_match_ai_failure_leaves_interview_unchanged` | 注入抛错的 Provider → 502，**题目数与内容完全不变** |
| `test_match_ai_failure_does_not_commit` | 上述场景下重新读取面试，题目数仍为原值（证明无半写） |
| `test_match_drops_ids_outside_pool` | 注入返回池外 id 的 Provider → 该条被丢弃，其余正常入库 |
| `test_match_count_default_from_config` | 不传 `count` → 追加数 `<= resume_match_count` |
| `test_match_count_capped` | `count=21` → 400 |
| `test_match_uses_question_supply` | 断言候选池取自 `list_candidates_for_position`（与出题组装同源） |
| `test_match_filters_invalid_dimensions` | 维度已不在岗位的题目**不被选中** |
| `test_match_other_hrs_interview_403` | hr_b 补 hr_a 的面试 → 403 |
| `test_match_response_includes_reason_for_ui` | 响应 `added[*].match_reason` 非空 |

### 7.4 准备助手（§5.4、§5.5）

| 测试 | 断言 |
|---|---|
| `test_generate_prep_persists_three_sections` | `outline` / `focus_points` / `question_plan` 三列均非空且结构正确 |
| `test_generate_prep_sets_generated_at` | `generated_at` 非空，`edited_at` 为 None |
| `test_generate_prep_regenerate_overwrites` | 二次生成 → **仍只有一行**（UNIQUE 生效），内容为新值 |
| `test_generate_prep_regenerate_clears_edited_at` | 先编辑（`edited_at` 非空）再重新生成 → `edited_at` 回到 **None** |
| `test_generate_prep_without_resume_ok` | 未关联简历 → 正常生成（走无简历分支） |
| `test_generate_prep_without_questions_ok` | 本场无题目（`draft`）→ 正常生成 |
| `test_generate_prep_in_draft_allowed` | `draft` 状态 → 允许 |
| `test_generate_prep_after_completed_409` | `completed` / `evaluating` / `evaluated` → 409 |
| `test_generate_prep_ai_failure_leaves_existing_intact` | 已有提纲 + AI 失败 → 502，**旧提纲内容与 `generated_at` 不变** |
| `test_generate_prep_ai_failure_first_time_no_row` | 首次生成时 AI 失败 → 502，`interview_prep` **无新行** |
| `test_generate_prep_empty_dims_409` | 岗位无维度 → 409 |
| `test_get_prep_not_generated_404` | 未生成 → 404 |
| `test_get_prep_ok` | 三部分与落库一致 |
| `test_update_prep_overwrites_three_sections` | 整体覆盖；`edited_at` 非空，`generated_at` **不变** |
| `test_update_prep_missing_section_400` | 缺 `question_plan` → 400（三部分全必填） |
| `test_update_prep_not_generated_404` | 未生成就编辑 → 404，**且未创建行** |
| `test_update_prep_after_completed_409` | `completed` → 409 |
| `test_prep_isolated_by_hr` | hr_b 读 hr_a 面试的提纲 → 403 |

### 7.5 契约与隔离（**容易漏**）

| 测试 | 断言 |
|---|---|
| `test_candidate_question_item_has_no_match_reason` | `GET /candidate/interviews/{id}` 的题目项**不含** `match_reason` 键 |
| `test_candidate_detail_has_no_match_reason_after_match` | 补题**之后**再读候选人详情，追加的题仍**不含** `match_reason` |
| `test_question_item_exposes_match_reason_to_hr` | HR 的 `GET /interviews/{id}` 中，匹配来的题有 `match_reason`，其余题为 null |
| `test_interview_detail_has_resume_id` | `InterviewDetail` 含 `resume_id`，未关联时为 null |
| `test_briefs_converts_orm_to_raw_values` | `_briefs` 输出为 `QuestionBrief`，**不含任何 ORM 属性访问**（喂给 `ai` 的必须是原始值） |
| `test_interview_does_not_import_resume_repository` | **静态断言**：`interview/` 下任一文件**顶层**不出现 `from app.resume import repository`（守住 §4.5 的禁止项） |
| 既有 `test_interview.py` / `test_e2e_flows.py` 全部用例 | **零回归**（含 `InterviewDetail` 新增字段带来的键集断言） |

> **`test_interview_does_not_import_resume_repository` 是本节唯一「补上测试空白」的一条**：架构测试的层校验只覆盖同模块内引用，跨模块跳层无人监管（module-17 §4.5）。用一条 AST/文本断言补上这个洞，比依赖评审可靠。

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-17（`resume` 包与两个契约方法）、module-18（两个 AI 方法）已完成。

### Task 19.1：模型与常量

- [ ] `Interview` 加 `resume_id`（§3.1）
- [ ] `InterviewQuestion` 加 `match_reason`；`source_snapshot` 的 **Enum 加入 `SOURCE_RESUME_MATCH`**（§3.2）
- [ ] `models.py` 新增 `SOURCE_RESUME_MATCH = "resume_match"` 常量（放在 `SOURCE_BANK` / `SOURCE_AI` 旁边）
- [ ] 新增 `InterviewPrep` 表（§3.3，含 `interview_id` UNIQUE 与 `CASCADE`）
- [ ] **不写迁移**，但**在提交说明里记下「`source_snapshot` 需 `MODIFY COLUMN`，不是 ADD COLUMN」**
- [ ] 写失败测试：`match_reason` 可为 NULL；`interview_prep.interview_id` 唯一约束生效
- [ ] 提交

### Task 19.2：配置项与 schema

- [ ] `core/config.py` 新增 `resume_match_count`；`.env.example` 补键
- [ ] `schemas.py` 新增 **10 个模型**（§4.2 末的清单）；`QuestionItem` 加 `match_reason`；`InterviewDetail` 加 `resume_id`
- [ ] 写失败测试：`count` 越界 → 400；`PrepUpdate` 缺字段 → 400
- [ ] **跑 `test_interview.py` 确认 `InterviewDetail` 加字段未破坏既有断言**
- [ ] 提交

### Task 19.3：repository 层

- [ ] 实现 §4.4 六个方法
- [ ] 写失败测试：`list_question_ids` 返回集合；`max_seq` 在无题时返回 0
- [ ] 运行确认通过
- [ ] 提交

### Task 19.4：候选人关联简历 + HR 读简历

- [ ] 写 §7.1 / §7.2 全部失败测试（**含 `evaluating` / `evaluated` 也 409 的白名单覆盖，与「未关联返回 404 而非 403」**）
- [ ] 运行确认失败
- [ ] 实现 `link_resume` / `get_interview_resume` 与两个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 19.5：按简历补题

- [ ] 写 §7.3 全部失败测试（**含「连调不重复」「连调会累加」「AI 失败题目数不变」「池外 id 被丢」「候选池耗尽 409」「空结果 200」**）
- [ ] 运行确认失败
- [ ] 实现 `match_questions_by_resume`、`_briefs` 与端点
- [ ] 运行确认通过
- [ ] 提交

### Task 19.6：面试前准备助手

- [ ] 写 §7.4 全部失败测试（**含「重新生成清空 `edited_at`」「AI 失败旧提纲不变」「未生成就编辑 404 且不建行」**）
- [ ] 运行确认失败
- [ ] 实现 `generate_prep` / `get_prep` / `update_prep`、`_prep_view` 与三个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 19.7：契约、隔离与全量回归

- [ ] 写 §7.5 全部测试（**含「候选人响应不含 `match_reason`」「interview 顶层不 import resume.repository」**）
- [ ] `conftest.py` 新增准备助手相关夹具
- [ ] 运行 `pytest tests/ -q`，**全部通过**（含既有 interview / e2e 用例零回归）
- [ ] 提交

---

## 9. 验收标准

- [ ] `interview.resume_id` 为 **NULL 允许**、外键 `RESTRICT`
- [ ] `interview_question.match_reason` 为 TEXT NULL；非匹配来源的题恒为 NULL
- [ ] **`source_snapshot` 的 Enum 已加入 `resume_match`**；`models.py` 中有 `SOURCE_RESUME_MATCH` 常量
- [ ] **提交/交付说明中明确记录「此项需 `ALTER TABLE ... MODIFY COLUMN`，不是 ADD COLUMN」**
- [ ] `interview_prep` 表建成，`interview_id` **UNIQUE** + `CASCADE`，三个 JSON 列 NOT NULL
- [ ] `resume_match_count` 默认 3，可被请求体覆盖，上限 20
- [ ] 关联简历：仅 `ongoing` 允许；`draft` / `completed` / `evaluating` / `evaluated` **一律 409**
- [ ] 关联简历只能用自己的简历（403）、未受邀面试不可关联（403）
- [ ] HR 读简历：判据只有「面试属于我」；未关联 **404**、他人面试 **403**；响应含 `updated_at`、不含 `created_by`
- [ ] 补题：写入 `source_snapshot='resume_match'` 与非空 `match_reason`；`seq` 续接无重号
- [ ] 补题**不改动任何既有题目**；**不新建题库题目**
- [ ] 补题候选池与出题组装**同源**（`list_candidates_for_position`），且剔除本场已有题
- [ ] **重复补题永不产生重复题目**（幂等），但**会累加**新题；池耗尽后 409
- [ ] 补题 AI 失败 → 502 且**数据库零改动**；AI 返回空 → **200 且 `added_count == 0`**
- [ ] 池外 id 被丢弃（本模块一层，`ai` 层另有一层）
- [ ] 准备助手：`draft`/`ongoing` 可生成与编辑，`completed` 及之后 409
- [ ] 准备助手三部分**整体覆盖**；重新生成把 `edited_at` 置回 **NULL**；编辑不改 `generated_at`
- [ ] 未生成的提纲读取 / 编辑 → **404 且不自动创建行**
- [ ] 生成失败 → 502 且**已有提纲（含 `generated_at`）不变**；首次生成失败则**无新行**
- [ ] **`match_reason` 从不下发给候选人**（补题后仍不下发）
- [ ] `interview` **未新增依赖** `evaluation` / `practice`；新增的 `resume` 依赖为**顶层 import service**，无 `resume.repository`
- [ ] 未新增错误码；既有用例零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **`source_snapshot` 是 Enum，加取值要 `MODIFY COLUMN`** | 显式写进计划书与交付说明 | 统一收口建表时若按「新增了哪些列 / 表」收集 DDL，**必然漏掉它**，后果是补题时 `Data truncated for column`。这是 MVP-3 唯一一处「改既有列取值域」 |
| **「幂等」被误读成「重复调用无效果」** | 文档用表格写清：不重复 ✅ / 不累加 ❌ | 候选池剔除了本场已有题，AI 会换一批。若实现成「第二次直接返回空」，就违背 PRD §4.14「HR 想再补几题」的意图 |
| **连点会累加题数** | 响应回 `added_count` 与 `total_questions`，要求前端显示总数 | 不显示总数的话，HR 连点几次会以为界面卡了。**不引入「已补过」标记**（PRD 未定义该概念，凭空加状态字段会带来新问题） |
| **`match_reason` 泄露给候选人的风险** | 候选人 schema **不加**该字段，并加测试断言 | 它描述「候选人简历的哪段经历对应这道题」，是 HR 的评估思路。复用 HR schema 是最容易发生的泄露 |
| **跨模块跳层无人监管** | 新增 `test_interview_does_not_import_resume_repository` 静态断言 | 架构测试的层校验用 `_own_module_refs`，**只看同模块内引用**。`interview` 顶层 import `resume.repository` 在测试眼里只是「合法依赖」 |
| **给 `InterviewDetail` 加字段可能破坏既有断言** | Task 19.2 显式要求先跑 `test_interview.py` | 若既有用例断言响应键集合，加字段会让它失败——这是**有益的失败**，但必须被执行者看见而不是被忽略 |
| **补题 AI 失败不需要补偿逻辑** | 第 6-7 步在任何写入之前 | 顺序本身就是保证。若把 AI 调用放在写库之后，就需要「回滚已写入部分」这类易错的补偿代码 |
| **生成提纲 AI 失败时旧值保留** | 同样因为 AI 调用（第 6 步）先于写入（第 7 步） | 「重新生成失败」应表现为「什么都没发生」，而不是「旧提纲被清空」 |
| **准备助手编辑要求先 `POST` 生成** | 未生成时 `PUT` → 404，**不自动创建** | 自动创建会让 `generated_at` 无从取值，且「生成」与「编辑」产生两条创建路径 |
| **编辑必须整体提交三部分** | 三字段全必填 | PRD §5.2「整体替换，不做字段级合并」。部分提交需要回答「未提交部分保留还是清空」，答案依场景而变，语义无法唯一 |
| **简历关联只允许 `ongoing`（白名单）** | 不用「completed 及之后拒绝」的黑名单 | `evaluating` / `evaluated` 对候选人是可达的（HR 可先 complete 再评估），黑名单极易漏掉它们 |
| **`load_unchecked` 后仍做 None 防御** | 保留（理论上不可达） | 依赖「外键 RESTRICT 保证不悬空」是跨三层的隐式假设。一行防御换来「假设失效时是 404 而非 500」 |
| **不落 `resume_text` 快照到 `interview_prep`** | 不存 | 存了就要回答「简历更新后提纲是否重生成」——PRD 未定义，不引入该问题 |
| **`interview_prep` 不放 `created_by`** | 不放 | 能读写它的只有面试拥有者，而面试已有 `created_by`。再加一列会引入「两个 created_by 不一致」的伪问题 |
| **准备助手不允许流式** | 一次性返回 | PRD §4.11 明确。流式会引入 SSE 的复杂度（既有 SSE 已有 `--workers 1` 限制，见 module-06 §5.6），收益不成比例 |
