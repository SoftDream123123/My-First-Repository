# interview 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：interview（面试实例、出题组装、回答记录、状态机）
**所属包**：`backend/app/interview/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp.md](../plans/2026-09-15-ai-interview-assistant-mvp.md)
**设计规格**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 任务**：Task 5
**前置依赖**：core（[00](./2026-09-15-module-00-core-plan.md)）、auth（[01](./2026-09-15-module-01-auth-plan.md)）、position（[02](./2026-09-15-module-02-position-plan.md)）、question（[03](./2026-09-15-module-03-question-plan.md)）、ai（[04](./2026-09-15-module-04-ai-plan.md)）

---

## Global Constraints（全局约束）

- 后端严格分层：`router → service → repository → MySQL`，只允许自上而下依赖，不跨层调用、不反向依赖。
- 每个模块独立 Python package（`backend/app/<module>/`）。
- 出题同步、评估流式（SSE）。
- 数据隔离：普通 HR 仅见自己创建的数据，admin 见全部。
- 统一错误响应格式 `{code, message, detail}`。

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 |
|---|---|
| 面试实体 | Interview / InterviewQuestion / Answer 三张表的定义与迁移 |
| 出题组装 | 从题库按维度均衡抽取 N 题 + 调用 AI 补充 M 题，合并、编号、写快照 |
| 回答记录 | 逐题录入候选人回答，支持修改 |
| 状态机 | 面试生命周期状态的唯一权威，校验并执行状态迁移 |

### 1.2 边界（明确不做）

- **不做评分与报告**：属于 evaluation 模块。interview 只保证「回答数据齐备、状态已到 `completed`」。
- **不做 AI 调用细节**：只调用 `ai.factory.get_provider()` 暴露的接口，不关心真实还是 Mock。
- **不做题目字段校验**：题目的创建校验属于 question 模块。
- **不做在线答题（候选人侧）**：MVP 仅 HR 手动录入；V1.1 才引入候选人侧。
- **不反向依赖 evaluation**：interview 不知道评估的存在；状态迁移中涉及 `evaluating` / `evaluated` 的迁移由 evaluation 模块**调用 interview 的状态机接口**完成（见 §5.4）。

### 1.3 依赖方向

```
interview.router ──→ interview.service ──→ interview.repository ──→ interview 表
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
| `backend/app/interview/models.py` | `Interview`、`InterviewQuestion`、`Answer` 三个模型 |
| `backend/app/interview/schemas.py` | 请求 / 响应 Pydantic 模型 |
| `backend/app/interview/repository.py` | 三张表的数据访问（含 `owner_id` 过滤） |
| `backend/app/interview/service.py` | 出题组装、回答记录、状态机 |
| `backend/app/interview/router.py` | `/api/interviews/*` 端点 |

**测试文件**：`backend/tests/test_interview.py`

**本模块需修改的上游文件**：

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 interview router |
| `backend/alembic/versions/` | 新增三张表迁移 |

---

## 3. 数据模型设计

### 3.1 表 `interview`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `position_id` | BIGINT | NOT NULL, FK → `position.id` RESTRICT, INDEX | 面试岗位 |
| `candidate_name` | VARCHAR(100) | NOT NULL | 候选人姓名 |
| `candidate_contact` | VARCHAR(200) | NULL | 联系方式（邮箱 / 电话），可选 |
| `status` | ENUM('draft','ongoing','completed','evaluating','evaluated') | NOT NULL, DEFAULT `'draft'`, INDEX | 状态机当前态 |
| `created_by` | BIGINT | NOT NULL, FK → `user.id`, INDEX | 创建人，数据隔离依据 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |
| `completed_at` | DATETIME | NULL | 标记完成的时刻 |

### 3.2 表 `interview_question`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, INDEX | 所属面试 |
| `question_id` | BIGINT | NOT NULL, FK → `question.id` RESTRICT | 来源题目 |
| `seq` | INT | NOT NULL | 面试内序号，**从 1 开始** |
| `content_snapshot` | TEXT | NOT NULL | 出题时的题干快照 |
| `dimension_snapshot` | VARCHAR(50) | NOT NULL | 出题时的考察维度快照 |
| `source_snapshot` | ENUM('bank','ai') | NOT NULL | 出题时的来源快照 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |

**索引**：`UNIQUE (interview_id, seq)`、`INDEX (interview_id)`、`INDEX (question_id)`

**快照设计的必要性**：

| 快照字段 | 不加会怎样 |
|---|---|
| `content_snapshot` | 题库题目被编辑后，历史面试的题干会跟着变，评估报告与当时实际问的问题对不上 |
| `dimension_snapshot` | 岗位维度改名后，evaluation 按 `dimension_score.dimension` 归集会错位 |
| `source_snapshot` | 题库题目被删除或来源变更后，无法还原当时题目的出处 |

> **对 PRD §5.2 的补充说明**：PRD 中 `interview_question` 字段列表仅列出 `content_snapshot`。本设计增加 `dimension_snapshot` 与 `source_snapshot`，理由如上表——它们与 `content_snapshot` 是**同一类完整性需求**，缺任一项都会让历史面试无法自洽。此为必要补充。

### 3.3 表 `answer`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_question_id` | BIGINT | NOT NULL, FK → `interview_question.id` **CASCADE**, **UNIQUE** | 一道面试题对应一条回答 |
| `content` | TEXT | NOT NULL | 候选人回答（HR 录入） |
| `recorded_at` | DATETIME | NOT NULL, DEFAULT NOW, ON UPDATE NOW | 最后记录时刻 |

> **对 PRD §5.2 的修正（重要）**：PRD 中 `answer` 以 `(interview_id, question_id)` 标识，本设计改为以 **`interview_question_id`** 标识。理由：
> 1. **唯一性语义更准**：要保证「一道面试题一条回答」，正确的唯一键是 `interview_question.id`。
> 2. **与快照对齐**：回答属于「这次面试的这一题」，而 `interview_question` 正是这个身份。
> 3. **不阻碍扩展**：若未来允许同一道题库题在一次面试中出现两次，按 `question_id` 建唯一键会直接撞车。
> 4. **消除冗余**：`interview_id` 可通过 `interview_question` 关联得到，不再在 `answer` 上冗余存储，避免不一致。

### 3.4 设计要点

- **`interview_question.interview_id` 用 CASCADE**：面试删除时，其题目与回答一并清除。
- **`question_id` 用 RESTRICT**：题库题目被面试引用时不可删除（question §5.3）。
- **`position_id` 用 RESTRICT**：岗位被面试引用时不可删除（position §5.3）。
- **`answer` 与 `interview_question` 之间 CASCADE**：删面试题连带删回答。
- **不设 `answer.is_deleted`**：回答只有「有」和「无」两态；清空回答通过写入空串（评分为 0）而非删除记录。

---

## 4. 接口契约

### 4.1 对外 REST API

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/interviews` | 创建面试（含同步出题组装） | 登录 + 岗位可见 | 201 |
| GET | `/api/interviews` | 面试列表（按数据隔离过滤） | 登录 | 200 |
| GET | `/api/interviews/{id}` | 面试详情（含题目与回答） | 登录 + 可见 | 200 |
| PATCH | `/api/interviews/{id}` | 更新候选人信息 | 登录 + 可见 | 200 |
| POST | `/api/interviews/{id}/answers` | 保存 / 更新某题回答 | 登录 + 可见 | 200 |
| POST | `/api/interviews/{id}/complete` | 标记面试完成 | 登录 + 可见 | 200 |
| POST | `/api/interviews/{id}/rollback` | 回退到进行中 | 登录 + 可见 | 200 |

> **对 PRD §8 API 概览的修正**：PRD 中 `PATCH /interviews/{id}` 描述为「更新候选人信息/状态」，同时又单独列出 `POST /interviews/{id}/complete`。二者在「改状态」上重叠。本设计**二选一，采纳显式命令端点**：
> - `PATCH` 只改候选人信息；
> - 状态迁移一律走 `/complete`、`/rollback` 等**动词端点**，由状态机统一校验。
>
> 理由：状态迁移有前置条件与副作用（如设置 `completed_at`），作为「字段更新」容易被绕过校验；动词端点也让 API 语义自解释。新增 `/rollback` 是因为 PRD §5.1 明确要求 `completed → ongoing` 的回退能力，但 PRD §8 未给出对应端点——此为补齐，非扩展。

### 4.2 请求 / 响应结构

**Interview 列表项**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | — |
| `position_id` | int | — |
| `position_name` | str | 岗位名（联表读取，供列表展示） |
| `candidate_name` | str | — |
| `candidate_contact` | str \| null | — |
| `status` | str | 状态机当前态 |
| `created_at` | datetime | — |
| `completed_at` | datetime \| null | — |
| `question_count` | int | 题目总数 |
| `answered_count` | int | 已回答题数 |

**Interview 详情**（在列表项基础上追加）

| 字段 | 类型 | 说明 |
|---|---|---|
| `jd` | str | 岗位 JD（供展示，非快照） |
| `evaluation_dimensions` | list[str] | 岗位当前维度（供展示） |
| `questions` | list[QuestionItem] | 见下 |

**QuestionItem**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_question_id` | int | 该题在此面试中的唯一标识（**回答接口用它**） |
| `seq` | int | 序号，从 1 开始 |
| `content` | str | 题干（取自 `content_snapshot`） |
| `dimension` | str | 维度（取自 `dimension_snapshot`） |
| `source` | str | 来源（取自 `source_snapshot`） |
| `answer` | str \| null | 已回答内容；未回答为 `null` |
| `recorded_at` | datetime \| null | — |

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
| 请求 | `interview_question_id` | int | 必填，须属于该面试 |
| 请求 | `content` | str | 必填，**允许空串**（表示「候选人未作答」），0–10000 字符 |
| 响应 | 该 QuestionItem | — | 含更新后的 `answer` 与 `recorded_at` |

**POST `/api/interviews/{id}/complete`** → 响应完整 Interview 详情，`status == "completed"`，`completed_at` 非空。

**POST `/api/interviews/{id}/rollback`** → 响应完整 Interview 详情，`status == "ongoing"`，`completed_at` 置空。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_interview(db, user: User, data: InterviewCreate) -> InterviewDetail` | 详情 | 建面试 + 出题组装 + 置 `ongoing`，**单事务** |
| `list_interviews(db, user: User) -> list[InterviewListItem]` | 列表 | `scope_owner_id` 过滤 |
| `get_interview(db, user: User, interview_id: int) -> InterviewDetail` | 详情 | 不存在 → 404；不可见 → 403 |
| `update_candidate(db, user: User, interview_id: int, data: InterviewPatch) -> InterviewDetail` | 详情 | 按状态限制 |
| `save_answer(db, user: User, interview_id: int, interview_question_id: int, content: str) -> QuestionItem` | 题目项 | 仅 `ongoing` 允许 |
| `complete_interview(db, user: User, interview_id: int) -> InterviewDetail` | 详情 | `ongoing` → `completed` |
| `rollback_interview(db, user: User, interview_id: int) -> InterviewDetail` | 详情 | `completed` / `evaluated` → `ongoing` |
| `get_answers_for_evaluation(db, interview_id: int) -> list[QAPair]` | QAPair 列表 | **供 evaluation 使用**：组装维度 + 题干（快照）+ 回答 |
| `get_position_id(db, interview_id: int) -> int` | int | **供 evaluation 使用** |
| `get_evaluation_dimensions(db, interview_id: int) -> list[str]` | 维度列表 | **供 evaluation 使用**：取岗位当前维度 |
| `transition_to_evaluating(db, interview_id: int) -> None` | — | **供 evaluation 使用**：`completed` / `evaluated` → `evaluating` |
| `transition_to_evaluated(db, interview_id: int) -> None` | — | **供 evaluation 使用**：`evaluating` → `evaluated` |
| `transition_back_to_completed(db, interview_id: int) -> None` | — | **供 evaluation 使用**：评估失败时 `evaluating` → `completed` |

> **为何 evaluation 的迁移要走 interview 的方法**：状态机的唯一权威在 interview 模块。evaluation 不得直接改 `interview.status` 字段，必须调用上表的迁移方法，以保证迁移合法性校验集中在一处。

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create_interview(db, position_id: int, candidate_name: str, contact: str \| None, created_by: int) -> Interview` | Interview | 初始 `status='draft'` |
| `list_by_owner(db, owner_id: int \| None) -> list[Interview]` | 列表 | 联表取 `position_name`；`owner_id=None` 表示不过滤 |
| `get_by_id(db, interview_id: int) -> Interview \| None` | Interview | **不带权限过滤** |
| `update_interview(db, interview: Interview, **fields) -> Interview` | Interview | — |
| `create_questions(db, items: list[dict]) -> list[InterviewQuestion]` | 列表 | 批量写入面试题（含快照） |
| `list_questions(db, interview_id: int) -> list[InterviewQuestion]` | 列表 | 按 `seq` 升序 |
| `get_question_entry(db, entry_id: int) -> InterviewQuestion \| None` | InterviewQuestion | — |
| `upsert_answer(db, interview_question_id: int, content: str) -> Answer` | Answer | 存在则更新 `content` + `recorded_at`，不存在则创建 |
| `list_answers(db, interview_id: int) -> list[Answer]` | 列表 | 联 `interview_question` 取 `interview_id` |
| `count_questions(db, interview_id: int) -> int` | int | — |
| `count_answers(db, interview_id: int) -> int` | int | — |

---

## 5. 业务流程设计

### 5.1 创建面试 + 出题组装（**单事务**）

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

| 方案 | 评价 |
|---|---|
| **整体回滚（本设计采用）** | 语义清晰——要么面试创建成功且题目齐备，要么什么都没发生；无需引入 `draft` 的持久化分支与「重新出题」端点 |
| 保留 `draft` + 重试端点 | 输入仅 3 个字段（岗位、姓名、联系方式），重填成本极低，为此引入新状态分支与新端点不划算（YAGNI） |

失败时事务回滚，**AI 题目也不会入库**（`bulk_create_from_ai` 在同一事务内），客户端收到 502 `AI_PROVIDER_ERROR` 并可重试。

> **`draft` 状态说明**：`draft` 是模型默认值与**事务内的瞬态值**，MVP 中不会出现在已提交的数据里。保留该枚举值的两个理由：① 作为模型默认值最安全；② 为 V1.1 的「草稿面试 / 在线答题」预留。

### 5.2 出题组装算法（确定性）

**输入**：`position`（含 `jd`、`evaluation_dimensions`）、`N = QUESTION_COUNT_FROM_BANK`（默认 5）、`M = QUESTION_COUNT_FROM_AI`（默认 3）

| 步骤 | 规则 |
|---|---|
| 1. 取候选 | `question.list_candidates_for_position(db, owner_id=user.id, position_id)` |
| 2. 过滤 | 剔除 `dimension` 不在 `position.evaluation_dimensions` 中的题目（见 question §5.5） |
| 3. 分组 | 按 `dimension` 分组；每组按 `id` **升序**（保证确定性） |
| 4. 轮询抽取 | 按 `evaluation_dimensions` 的顺序，每轮从各组取 1 题，直至取满 `N` 或所有组耗尽。记录实际抽得数 `K` |
| 5. 计算 AI 需求 | `need_ai = M + (N - K)` —— **保证总题数恒为 `N + M`** |
| 6. 调 AI | `provider.generate_questions(position_name, jd, dims, existing_contents=已抽题干列表, count=need_ai)` |
| 7. AI 题入库 | `question.bulk_create_from_ai(db, user, position_id, ai_items)` → 题库中 `source='ai'` |
| 8. 合并与编号 | 题库题在前（按抽取顺序）、AI 题在后；`seq` 从 1 连续编号 |
| 9. 写快照 | 每题写 `content_snapshot` / `dimension_snapshot` / `source_snapshot` |

**关键性质**

| 性质 | 说明 |
|---|---|
| 总题数恒定 | 只要 `dims` 非空且 AI 可用，总题数恒为 `N + M = 8`——题库不足时由 AI 补足差额 |
| 确定性 | 轮询顺序固定、组内按 `id` 升序、Mock Provider 确定性 → 同一数据状态下出题结果完全可预测，便于断言 |
| 维度均衡 | round-robin 保证各维度题目数尽量平均，而非某一维度被抽空 |
| 题库不足不报错 | `K < N` 时只是把差额转给 AI，PRD 明确要求「不报错」 |

**边界情况**

| 情况 | 行为 |
|---|---|
| `position.evaluation_dimensions` 为空 | 被 position 校验阻止，理论上不可达；若发生 → 抛 `BusinessError` |
| 题库为空 | `K = 0`，`need_ai = M + N = 8`，全部由 AI 生成 |
| `need_ai = 0` | 跳过 AI 调用（例如题库题量充足但 `M=0` 的配置） |
| AI 返回数量少于 `need_ai` | 按实际返回数量入库，不报错；总题数可能少于 8，响应中如实反映 |

### 5.3 回答记录

```
1. 按 §4.3 get_interview 校验存在与可见
2. 校验状态 == 'ongoing'
      否则 → BusinessError「当前状态下不可修改回答，请先回退到进行中」
3. 校验 interview_question_id 属于该面试
      不属于 → NotFoundError
4. repository.upsert_answer（存在则更新 content 与 recorded_at）
5. commit
```

**唯一允许写回答的状态是 `ongoing`**——一条规则覆盖所有情况，保证「评估所依据的回答」在评估期间与评估后不被篡改。

### 5.4 状态机（**本模块的核心**）

#### 5.4.1 状态迁移表

| from | to | 触发端点 / 调用方 | 副作用 |
|---|---|---|---|
| `draft` | `ongoing` | 出题组装完成（事务内） | — |
| `ongoing` | `completed` | `POST /complete` | 设 `completed_at` |
| `completed` | `ongoing` | `POST /rollback` | 清 `completed_at` |
| `completed` | `evaluating` | evaluation 触发 | — |
| `evaluating` | `evaluated` | evaluation 成功 | — |
| `evaluating` | `completed` | evaluation 失败 | — |
| `evaluated` | `evaluating` | evaluation 重新评估 | — |
| `evaluated` | `ongoing` | `POST /rollback` | 清 `completed_at` |

**表中未列出的迁移一律拒绝**，返回 `BUSINESS_ERROR`（409），`detail` 携带 `{from, to}`。

#### 5.4.2 状态机实现位置

```
interview/service.py
  └── _assert_transition(current: str, target: str) -> None
        非法 → BusinessError(code=BUSINESS_ERROR, detail={"from": current, "to": target})
```

所有状态变更（含 evaluation 触发的）都经过这一个断言函数，不允许任何地方直接赋值 `interview.status`。

#### 5.4.3 各状态下允许的操作矩阵

| 操作 | draft | ongoing | completed | evaluating | evaluated |
|---|---|---|---|---|---|
| 查看面试 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 改候选人信息 | ✗ | ✓ | ✓ | ✗ | ✗ |
| 写 / 改回答 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 标记完成 | ✗ | ✓ | ✗ | ✗ | ✗ |
| 回退到进行中 | ✗ | — | ✓ | ✗ | ✓ |
| 触发评估 | ✗ | ✗ | ✓ | ✗ | ✓ |

> `evaluated` 下的「触发评估」即**重新评估**：会用当前回答覆盖旧的逐题分、维度分与报告（见 evaluation §5.4）。

### 5.5 对 evaluation 的供给契约

evaluation 只通过以下接口读取面试数据，**不直接查 interview 的表**：

| 接口 | 返回 |
|---|---|
| `get_answers_for_evaluation(db, interview_id)` | `list[QAPair]`（`dimension` 取 `dimension_snapshot`、`question` 取 `content_snapshot`、`answer` 取回答内容或 `None`），按 `seq` 升序 |
| `get_evaluation_dimensions(db, interview_id)` | 岗位**当前**的 `evaluation_dimensions` |
| `get_position_id(db, interview_id)` | 岗位 id |
| `transition_to_evaluating` / `transition_to_evaluated` / `transition_back_to_completed` | 状态迁移 |

> **维度取「岗位当前值」而非快照的原因**：维度集合的权威定义在岗位。若岗位维度被修改，重新评估应按新维度出分。题目与回答的快照保护的是「问了什么、答了什么」，维度则是「按什么标准评」——后者跟随岗位定义。此设计已与 position §5.4 的约定对齐。

---

## 6. 错误处理

| 场景 | code | HTTP | message 示例 |
|---|---|---|---|
| 未带 / 无效 token | `UNAUTHORIZED` / `INVALID_TOKEN` | 401 | — |
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在 |
| 访问他人面试 | `FORBIDDEN` | 403 | 无权限访问该面试 |
| 岗位不存在 / 不可见 | `NOT_FOUND` / `FORBIDDEN` | 404 / 403 | — |
| `interview_question_id` 不属于该面试 | `NOT_FOUND` | 404 | 题目不属于该面试 |
| 非 `ongoing` 状态写回答 | `BUSINESS_ERROR` | 409 | 当前状态下不可修改回答，请先回退到进行中 |
| 非 `ongoing` 状态标记完成 | `BUSINESS_ERROR` | 409 | 当前状态下不可标记完成 |
| 非法状态迁移 | `BUSINESS_ERROR` | 409 | 不允许从「已完成」迁移到「评估中」（`detail` 含 from/to） |
| `evaluating` / `evaluated` 下改候选人信息 | `BUSINESS_ERROR` | 409 | 评估中或已评估的面试不可修改候选人信息 |
| AI 出题失败 | `AI_PROVIDER_ERROR` | 502 | AI 出题失败，请稍后重试（事务已回滚，无残留数据） |
| `candidate_name` 为空或超长 | `VALIDATION_ERROR` | 400 | — |
| 回答内容超 10000 字符 | `VALIDATION_ERROR` | 400 | — |

---

## 7. 测试设计

`backend/tests/test_interview.py`

> 全部测试使用 **Mock Provider**，保证确定性与无外部依赖。

### 7.1 鉴权与数据隔离

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

### 7.2 出题组装

| 测试 | 断言 |
|---|---|
| `test_create_generates_n_plus_m_questions` | 题库充足时共 8 题（5 + 3） |
| `test_question_seq_starts_at_one_and_is_contiguous` | `seq` 为 1..8 |
| `test_bank_questions_come_first` | 前 5 题 `source == "bank"`，后 3 题 `source == "ai"` |
| `test_snapshots_written` | 每题 `content` / `dimension` / `source` 三个快照非空 |
| `test_dimension_snapshot_matches_bank_question` | 题库题的快照维度等于该题原维度 |
| `test_insufficient_bank_pads_with_ai` | 题库仅 2 题 → 仍共 8 题（2 题库 + 6 AI），**不报错** |
| `test_empty_bank_all_ai` | 题库为空 → 8 题全部 `source == "ai"` |
| `test_dimension_round_robin` | 两个维度各有充足题目 → 抽取结果在两维度间交替 |
| `test_questions_with_stale_dimension_skipped` | 题库含 `dimension` 不在岗位维度中的题 → 该题**不被抽取** |
| `test_ai_questions_saved_to_bank` | 出题后题库中新增 `source == "ai"` 的题目，`created_by` 为面试创建人 |
| `test_ai_failure_rolls_back_everything` | 注入会抛 `AIProviderError` 的 provider → 502，且**面试与 AI 题目均未入库** |
| `test_create_with_invisible_position` | 用他人岗位 → 403 |
| `test_create_with_nonexistent_position` | 404 |
| `test_generation_is_deterministic` | 相同数据状态下创建两次（不同面试）→ 题目序列完全一致 |

### 7.3 回答记录

| 测试 | 断言 |
|---|---|
| `test_save_answer_ok` | 200，`answer` 与 `recorded_at` 正确 |
| `test_save_answer_updates_existing` | 二次保存 → 只有一条记录，`content` 被更新，`recorded_at` 变化 |
| `test_save_empty_answer_allowed` | `content=""` → 200，`answer == ""` |
| `test_save_answer_wrong_interview` | 传其他面试的 `interview_question_id` → 404 |
| `test_save_answer_content_too_long` | 10001 字符 → 400 |
| `test_save_answer_not_ongoing` | `completed` 状态下 → 409 |
| `test_save_answer_when_evaluating` | 409 |

### 7.4 状态机

| 测试 | 断言 |
|---|---|
| `test_complete_from_ongoing` | 200，`status == "completed"`，`completed_at` 非空 |
| `test_complete_twice_rejected` | 第二次 409 |
| `test_complete_from_evaluated_rejected` | 409 |
| `test_rollback_from_completed` | 200，`status == "ongoing"`，`completed_at` 为 `None` |
| `test_rollback_from_evaluated` | 200，`status == "ongoing"` |
| `test_rollback_from_ongoing_rejected` | 409 |
| `test_rollback_from_evaluating_rejected` | 409 |
| `test_transition_to_evaluating_from_ongoing_rejected` | 直接调用迁移方法 → 409 |
| `test_transition_to_evaluated_requires_evaluating` | 从 `completed` 直接调 `transition_to_evaluated` → 409 |
| `test_transition_back_to_completed_from_evaluating` | 成功，`status == "completed"` |
| `test_error_detail_contains_from_and_to` | 非法迁移的 `detail` 含 `from` 与 `to` |

### 7.5 候选人信息更新

| 测试 | 断言 |
|---|---|
| `test_update_candidate_when_ongoing` | 200 |
| `test_update_candidate_when_completed` | 200 |
| `test_update_candidate_when_evaluating` | 409 |
| `test_update_candidate_when_evaluated` | 409 |
| `test_update_candidate_does_not_change_status` | 状态不变（验证 PATCH 不含状态字段） |
| `test_update_candidate_name_too_long` | 400 |

### 7.6 详情与列表

| 测试 | 断言 |
|---|---|
| `test_detail_includes_questions_with_answers` | 题目按 `seq` 升序，回答正确挂载 |
| `test_detail_unanswered_question_answer_is_null` | 未回答题 `answer` 为 `null` |
| `test_list_includes_position_name` | 列表项含 `position_name` |
| `test_list_includes_counts` | `question_count == 8`，`answered_count` 正确 |
| `test_detail_uses_snapshot_not_live_question` | 修改题库题目内容后，详情仍显示出题时的快照 |

### 7.7 对 evaluation 的供给契约

| 测试 | 断言 |
|---|---|
| `test_get_answers_for_evaluation_shape` | 返回 `QAPair` 列表，`dimension` 来自快照，`question` 来自快照 |
| `test_get_answers_for_evaluation_order` | 按 `seq` 升序 |
| `test_get_answers_unanswered_is_none` | 未回答的 `answer` 为 `None`（不是空串） |
| `test_get_evaluation_dimensions_from_position` | 返回岗位当前维度（非快照） |

---

## 8. 任务分解（TDD 步骤，无代码）

### Task 5.1：三张模型与迁移

- [ ] 定义 `Interview`（§3.1）、`InterviewQuestion`（§3.2）、`Answer`（§3.3）
- [ ] 建立全部外键（CASCADE / RESTRICT 按 §3.4）与索引
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
- [ ] 实现 `_assert_transition` 与三个供 evaluation 使用的迁移方法
- [ ] 运行确认通过
- [ ] 提交

### Task 5.5：出题组装

- [ ] 写 §7.2 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 §5.2 算法（过滤 → 分组 → round-robin → 计算 `need_ai` → 调 AI → 入库 → 合并编号 → 写快照）
- [ ] 实现 `create_interview` 单事务与 AI 失败整体回滚
- [ ] 实现 `POST /api/interviews`，在 `main.py` 注册 router
- [ ] 运行确认通过
- [ ] 提交

### Task 5.6：列表与详情

- [ ] 写 §7.6 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `list_interviews`、`get_interview`（含快照读取、回答挂载、计数）与两个 GET 端点
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

- [ ] 创建面试返回 201，题库充足时共 8 题（5 题库 + 3 AI），`seq` 从 1 连续
- [ ] 题库不足时由 AI 补齐至总数 8，且**不报错**
- [ ] 题库为空时 8 题全部来自 AI
- [ ] 题库中 `dimension` 已不在岗位维度内的题目**不被抽取**
- [ ] 每题写全 `content_snapshot` / `dimension_snapshot` / `source_snapshot`
- [ ] AI 生成的题目写入题库且 `source == "ai"`
- [ ] AI 出题失败 → 502 且**面试与 AI 题目均无残留**（整体回滚）
- [ ] 相同数据状态下出题结果完全确定
- [ ] 回答保存仅允许在 `ongoing`；二次保存为更新而非新增（唯一约束生效）
- [ ] `completed_at` 在标记完成时被设置、回退时被清空
- [ ] 状态机：§5.4.1 表中未列出的迁移一律返回 409，`detail` 含 `from` / `to`
- [ ] §5.4.3 操作矩阵逐格生效
- [ ] 修改题库题目后，面试详情仍显示出题时的快照
- [ ] `get_answers_for_evaluation` 的 `dimension` / `question` 来自快照，未回答项 `answer` 为 `None`
- [ ] `get_evaluation_dimensions` 返回岗位**当前**维度
- [ ] 全部 interview 测试通过

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| AI 出题失败是否保留面试草稿 | **整体回滚** | 输入仅 3 个字段，重填成本低；避免新状态分支与新端点；语义最清晰 |
| `draft` 状态是否可达 | 事务内瞬态，不持久化 | 保留为模型默认值与 V1.1 预留；如强行让它可达需引入重试端点，YAGNI |
| 出题是否随机化 | **不确定随机，round-robin + id 升序** | 可测试性优先；每次出题结果可预测，避免测试不稳定。实际多样性由题库内容与 AI 提供 |
| `answer` 的标识键 | `interview_question_id` 而非 `(interview_id, question_id)` | 唯一性语义更准、与快照对齐、不阻碍扩展、消除冗余字段 |
| 快照字段是否需要三个 | 需要（content / dimension / source） | 缺任一都会让历史面试无法自洽（§3.2） |
| 状态迁移走 PATCH 还是动词端点 | **动词端点** | 状态迁移有前置条件与副作用，作为字段更新易被绕过；同时消除 PRD 中二者的重叠 |
| 候选人信息可否在 `evaluated` 后修改 | 不可 | 报告依据的对象不应事后变更 |
| 写回答是否允许在 `completed` 状态 | 不允许，须先回退 | 一条规则覆盖所有情况，保证评估依据不被篡改 |
| 评估期间面试数据是否可改 | 不可（`evaluating` / `evaluated` 全锁） | 避免「评估读到一半数据被改」导致报告不自洽 |
| 是否软删除面试 | 不软删除 | MVP YAGNI；本模块无被其他模块引用的场景（evaluation 通过接口读取） |
| 维度取岗位当前值还是快照 | **岗位当前值** | 维度是「按什么标准评」，权威定义在岗位；题目与回答的快照保护的是「问了什么、答了什么」 |
