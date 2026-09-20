# practice 模块执行计划书（MVP-2 刷题练习）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：practice（练习会话、逐题判分、错题本、练习统计）—— **MVP-2 新增的第八个 package**
**所属包**：`backend/app/practice/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.7（刷题练习）、§5.2（`practice_session`、`practice_item`）、§5.3 ⑤（流程）、§7（判分失败降级与限流）、§8（practice 端点）、§9（单机约束）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-01 auth](./2026-09-15-module-01-auth-plan.md)、[module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md)、[module-10 question 题型](./2026-09-20-module-10-question-plan.md)、[module-11 ai 判分](./2026-09-20-module-11-ai-plan.md)、[module-16 权限守卫](./2026-09-20-module-16-permission-guard-plan.md)
**本模块被谁依赖**：[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- 刷题**只做文本问答**，**不含编程题**（§1.3）
- 取题按**岗位 / 分类 / 维度 / 难度 / 题型**筛选（§4.7）
- 判分分工：**单选题本地规则判分（不消耗 AI）**；**简答题调 `ai.grade_practice_answer`**（§4.7）
- 无 Key 时由 Mock Provider 给出**确定性判分**（§4.7、§9）
- **参考答案与解析在提交后展示**（§4.7）
- 错题本**由判错的作答派生，不单独建表**（§4.7）
- 练习统计：累计题量、正确率、**按维度正确率**（§4.7）
- 判分失败：`practice_item` **正常落库但 `is_correct` 为空**，标记未判分，可后续重判；**不阻塞作答**（§7）
- 限流用**进程内计数**（单机约束），不引入 Redis（§2、§7）
- 数据隔离：候选人只能访问**自己的** `practice_*` 数据（§4.1、§4.6）
- 路由守卫 `require_roles("candidate")`；**admin 与 hr 在候选人侧不通行**（§4.1、[module-09 §4.5](./2026-09-20-module-09-auth-plan.md)）
- **`practice` 不依赖 `interview`**——刷题与真实面试解耦（§3.3、§9）
- 判对/判错阈值**必须**用 `ai.base.PASS_THRESHOLD`（= 6.5），不另定义（[module-11 §3.3](./2026-09-20-module-11-ai-plan.md)）
- 明确不做：收藏、笔记、排行榜、积分（§1.3、§4.7）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.7）

| 子职责 | 内容 | PRD |
|---|---|---|
| 练习会话 | 开始 / 查看 / **列出** / 结束一次练习；记录筛选条件与计数 | §4.7 |
| 取题 | 经 question 的供给契约取题并写**题目快照** | §5.3 ⑤ |
| 逐题判分 | 单选本地规则；简答调 AI；无答案则标记未判分 | §4.7 |
| 解析与参考答案 | 提交后随判分结果返回 | §4.7 |
| 错题本 | 由判错的作答**派生查询** | §4.7 |
| 练习统计 | 累计题量、正确率、按维度正确率 | §4.7 |
| 限流 | 进程内计数（单机） | §2、§7 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **取题逻辑本身** | 由 `question.service.list_practice_questions` 提供（[module-10 §4.4](./2026-09-20-module-10-question-plan.md)）。本模块只传筛选条件与 `limit` |
| **简答题的判分规则** | 由 `ai.grade_practice_answer` 提供（[module-11 §4.2](./2026-09-20-module-11-ai-plan.md)）。本模块只做分支与降级 |
| **真实面试的作答** | 属 `interview`（module-12）。**本模块不 import interview**，刷题与真实面试的数据完全分离 |
| **收藏 / 笔记 / 排行榜 / 积分 / 成就** | PRD §1.3、§4.7 明确不做 |
| **编程题判题 / 代码沙箱** | PRD §1.3 明确不做 |
| **错题本表 / 统计表** | 全部由 `practice_item` 派生，避免派生数据与源数据漂移 |
| **练习的定时器 / 倒计时 / 学习计划** | PRD 未要求 |
| **重判的历史任务 / 定时重判** | PRD §7 只说「可后续重判」。本模块提供**按题重判的入口**（§5.4），不做后台批量重判 |

### 1.3 依赖方向

```
practice.router ──→ practice.service ──→ practice.repository ──→ practice 表族
                          │
                          ├──→ question.service（list_practice_questions + PracticeQuestionOut）
                          ├──→ auth.service（ensure_owner_match）
                          └──→ ai.factory.get_provider()（grade_practice_answer / PASS_THRESHOLD）

practice ──→ core / auth / question / ai（单向）
practice ✗→ interview / position / evaluation（**无反向依赖，且与 interview 完全解耦**）
```

> **`position` 不在依赖列**：筛选用的 `position_id` 只是透传给 question 的一个原始值，本模块不需要读岗位表。取题时若岗位不存在，由 question 的取题结果为空自然反映（返回业务错误，§5.1）。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/practice/__init__.py` | 包标识 |
| `backend/app/practice/models.py` | `PracticeSession` / `PracticeItem` 模型 |
| `backend/app/practice/schemas.py` | 请求 / 响应模型、`PracticeFilters` |
| `backend/app/practice/repository.py` | 纯 CRUD 与派生查询（错题本 / 统计） |
| `backend/app/practice/service.py` | 会话编排、判分分支、降级、限流 |
| `backend/app/practice/router.py` | `/api/practice/*` **九个端点**（含重判与会话列表） |

**测试文件**：`backend/tests/test_practice.py`（service 与 repository）、`backend/tests/test_practice_router.py`（端点、鉴权、隔离）

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/app/main.py` | 注册 practice router（前缀 `/api`） | 端点生效 |
| `backend/app/auth/service.py` | **新增 `ensure_owner_match(user, owner_id, label)`** | 见 §4.5。候选人的资源归属校验**不能**用 `ensure_resource_visible`/`scope_owner_id`（对 candidate 角色会直接抛错，见 [module-16 §4](./2026-09-20-module-16-permission-guard-plan.md)） |
| `backend/alembic/versions/` | 新增迁移：两张表 + 索引 | — |
| `backend/script.sql` | 同步两张表结构与索引 | 与 Alembic 保持一致（module-00 §4） |
| `backend/tests/conftest.py` | 新增 `practice_session` 夹具（含若干题目） | 供 module-15 与 E2E 复用 |
| **`backend/tests/test_architecture.py`** | 把 `practice` 登记进 `ALL_MODULES` / `LAYERED_MODULES` / `FORBIDDEN_DEPENDENCIES` | ⚠️ 该文件的模块名列表是**硬编码**的。不登记则本包的分层与依赖方向**不受任何测试保护**（见 §7.4） |
| `backend/app/core/config.py` | 新增 `PRACTICE_SESSION_SIZE_DEFAULT` / `PRACTICE_SESSION_SIZE_MAX` / `PRACTICE_SESSION_LIST_MAX` / `PRACTICE_RATE_LIMIT_PER_MINUTE` | §3.3 |

---

## 3. 数据模型设计

### 3.1 表 `practice_session`（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 | 来源 |
|---|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 | PRD §5.2 |
| `candidate_user_id` | BIGINT | NOT NULL, FK → `user.id` **RESTRICT**, INDEX | **练习归属，数据隔离依据** | PRD §5.2 |
| `position_id` | BIGINT | NULL, FK → `position.id` **RESTRICT** | 筛选条件（未按岗位筛时为 NULL） | PRD §5.2 |
| `category` | VARCHAR(50) | NULL | 筛选条件 | PRD §5.2 |
| `dimension` | VARCHAR(50) | NULL | 筛选条件 | PRD §5.2 |
| `difficulty` | ENUM('easy','medium','hard') | NULL | 筛选条件 | PRD §5.2 |
| `question_type` | ENUM('single_choice','short_answer') | NULL | **筛选条件**（本设计补充，PRD 未列） | **本设计新增** |
| `status` | ENUM('ongoing','finished') | NOT NULL, DEFAULT `'ongoing'`, INDEX | 会话状态 | PRD §5.2 |
| `total` | INT | NOT NULL | 实际取到的题数 | PRD §5.2 |
| `answered_count` | INT | NOT NULL, DEFAULT 0 | 已作答数（**每次提交后重算**，见 §5.3） | PRD §5.2 |
| `correct_count` | INT | NOT NULL, DEFAULT 0 | 判对数（同上） | PRD §5.2 |
| `started_at` | DATETIME | NOT NULL, DEFAULT NOW | — | PRD §5.2 |
| `finished_at` | DATETIME | NULL | 结束时刻 | PRD §5.2 |

**索引**：`ix_practice_session_candidate`（`candidate_user_id`）、`ix_practice_session_status`（`status`）

> **`question_type` 是本设计的补充字段**：PRD §4.7 要求「按题型筛选取题」，筛选条件必须在会话上留痕，否则无法回答「这次练习练的是哪类题」。已记入 [module-08 §7.2](./2026-09-15-module-08-e2e-plan.md)。
>
> **`position_id` 允许 NULL**：不选岗位时是「全库随机刷题」，这是刷题的常见用法。设为 NOT NULL 会强迫候选人先选岗位。

### 3.2 表 `practice_item`（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 | 来源 |
|---|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 | PRD §5.2 |
| `session_id` | BIGINT | NOT NULL, FK → `practice_session.id` **CASCADE**, INDEX | 所属会话 | PRD §5.2 |
| `question_id` | BIGINT | NOT NULL, FK → `question.id` **RESTRICT** | 来源题目 | PRD §5.2 |
| `seq` | INT | NOT NULL | 会话内序号，**从 1 开始** | **本设计新增** |
| `content_snapshot` | TEXT | NOT NULL | 题干快照 | PRD §5.2 |
| `options_snapshot` | JSON | NOT NULL, DEFAULT `[]` | 选项快照（简答为 `[]`） | PRD §5.2 |
| `reference_answer_snapshot` | TEXT | NULL | 参考答案快照 | PRD §5.2 |
| `dimension_snapshot` | VARCHAR(50) | NOT NULL | **维度快照**（按维度统计的依据） | **本设计新增** |
| `question_type` | ENUM('single_choice','short_answer') | NOT NULL | **题型快照**（判分分支的依据） | **本设计新增** |
| `user_answer` | TEXT | NULL | 候选人作答；**NULL 表示尚未提交** | PRD §5.2 |
| `is_correct` | BOOLEAN | **NULL** | **NULL = 未判分**（无参考答案或 AI 失败） | PRD §5.2 |
| `score` | DECIMAL(3,1) | NULL | 0.0–10.0；未判分时为 NULL | PRD §5.2 |
| `explanation` | TEXT | NULL | 解析（提交后展示） | PRD §5.2 |
| `answered_at` | DATETIME | NULL | 最近一次提交时刻 | PRD §5.2 |

**索引**：`UNIQUE (session_id, seq)`、`ix_practice_item_session`（`session_id`）、`ix_practice_item_question`（`question_id`）、`ix_practice_item_correct`（`is_correct`，服务于错题本派生）

**两个补充字段的必要性**

| 字段 | 不加会怎样 |
|---|---|
| `dimension_snapshot` | 按维度统计只能联表读 `question.dimension`。题库改维度后，**历史练习的统计会跟着漂移**——与 `interview_question.dimension_snapshot` 是同一类完整性问题（module-05 §3.2） |
| `question_type` | 判分分支要按快照决定。若 HR 在会话开始后把题从简答改为单选，联表读当前值会让**已有的空 `options_snapshot`** 与「单选」分支冲突，判分直接崩 |

> **`is_correct` 用三态（TRUE / FALSE / NULL）而非两态**：`NULL` 是「未判分」这一**独立事实**，与「判错」在语义上完全不同——错题本不能把未判分的题算进去（§5.5）。加一个 `is_scored` 布尔表达同一事实会让两个字段漂移。

### 3.3 新增配置项

| 配置键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `PRACTICE_SESSION_SIZE_DEFAULT` | int | `10` | 开始练习未指定题数时的默认题量 |
| `PRACTICE_SESSION_SIZE_MAX` | int | `20` | 单次练习题量上限（硬上限，防一次拉全库） |
| `PRACTICE_RATE_LIMIT_PER_MINUTE` | int | `60` | 每用户每分钟的提交/取题上限（进程内计数） |
| `PRACTICE_SESSION_LIST_MAX` | int | `100` | 会话列表 `limit` 的硬上限（§5.9） |

---

## 4. 接口契约

### 4.1 对外 REST API（守卫 `require_roles("candidate")`）

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| GET | `/api/practice/questions` | 刷题取题（**预览用**，不含答案） | 200 |
| GET | `/api/practice/sessions` | **我的练习会话列表**（含进行中，用于继续未完成的练习） | 200 |
| POST | `/api/practice/sessions` | 开始一次练习 | 201 |
| GET | `/api/practice/sessions/{id}` | 练习详情与进度 | 200 |
| POST | `/api/practice/sessions/{id}/items` | 提交某题作答 → 即时判分 + 解析 | 200 |
| POST | `/api/practice/items/{item_id}/rescore` | **对未判分的题重新判分**（补齐 PRD §7「可后续重判」） | 200 |
| POST | `/api/practice/sessions/{id}/finish` | 结束练习，出小结 | 200 |
| GET | `/api/practice/wrong-book` | 错题本（派生） | 200 |
| GET | `/api/practice/stats` | 我的练习统计 | 200 |

> **`GET /practice/questions` 与 `POST /practice/sessions` 的关系**：前者是**无状态预览**（「有哪些题可练」），后者才创建会话并写快照。两者共用同一筛选参数与同一供给契约。预览接口存在的意义是让前端在开始前显示「符合条件的题量」。

### 4.2 请求 / 响应结构

**`PracticeQuestionOut`（候选人视图，定义在 [module-10 §4.2](./2026-09-20-module-10-question-plan.md)）** —— 取题、预览、会话详情中的题目**一律用这个视图**：

| 字段 | 下发 | 说明 |
|---|---|---|
| `id` / `position_id` | ✓ | — |
| `category` / `dimension` / `difficulty` / `tags` | ✓ | — |
| `content` | ✓ | 题干 |
| `question_type` | ✓ | 决定前端渲染单选框还是文本框 |
| `options` | ✓ | **必须下发**（否则单选框无内容） |
| `reference_answer` / `explanation` | **✗** | 提交后才由判分响应给出 |
| `source` / `created_by` / `created_at` | **✗** | 候选人无需知道 |

**GET `/api/practice/sessions`** 查询参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `status` | str \| 可选 | `ongoing` \| `finished`；缺省返回**全部** |
| `limit` | int \| 可选 | 缺省 20，上限 100 |

→ 会话列表项（**不含题目明细**，避免列表接口过重）：

| 字段 | 说明 |
|---|---|
| `session_id` | — |
| `status` | `ongoing` \| `finished` |
| `position_name` | 筛选条件摘要（未选岗位时为 `null`） |
| `category` / `dimension` / `difficulty` / `question_type` | 筛选项回显（未选的为 `null`） |
| `total` / `answered_count` / `correct_count` | 计数 |
| `started_at` / `finished_at` | — |

> **为何必须有这个端点**：没有它，候选人一旦离开某次未完成的练习就无法从 UI 回到它——只能靠 URL。`status=ongoing` 让前端能直接渲染「继续练习」入口。
>
> **列表返回的是会话而非题目**：会话的题目明细走 `GET /practice/sessions/{id}`。让列表接口带上全部题目会让「看历史」这一动作变重（20 个会话 × 20 道题）。

**POST `/api/practice/sessions`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `position_id` | int \| null | 可选 |
| 请求 | `category` | str \| null | 可选 |
| 请求 | `dimension` | str \| null | 可选 |
| 请求 | `difficulty` | str \| null | 可选，`easy`/`medium`/`hard` |
| 请求 | `question_type` | str \| null | 可选，`single_choice`/`short_answer` |
| 请求 | `size` | int \| null | 可选，缺省 `PRACTICE_SESSION_SIZE_DEFAULT`；**上限 `PRACTICE_SESSION_SIZE_MAX`** |
| 响应 | `session` | object | 会话摘要（`id` / 筛选条件 / `total` / `status` / `started_at`） |
| 响应 | `items` | array | 待答项：`item_id`、`seq`、`question`(**`PracticeQuestionOut`**)、`user_answer`(null) |

**GET `/api/practice/sessions/{id}`** → 会话摘要 + 全部 items：

| 字段（每个 item） | 说明 |
|---|---|
| `item_id` / `seq` / `question` | 同上（`question` 仍为 `PracticeQuestionOut`，**不含答案**） |
| `user_answer` | str \| null |
| `is_correct` | bool \| null（null = 未判分） |
| `score` | float \| null |
| `explanation` / `reference_answer` | **仅在该 item 已提交后才非空**（未提交时为 null） |

> **这是「提交后展示」规则的落点**：同一个响应结构，通过「已提交才填充」控制答案的可见时机。**不允许**用「前端不显示」来替代——不下发就是不下发。

**POST `/api/practice/sessions/{id}/items`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `item_id` | int | 必填，必须属于该会话 |
| 请求 | `user_answer` | str | 必填，允许空串（视为未作答 → 0 分）；≤ 5000 字符 |
| 响应 | `item_id` / `seq` | int | — |
| 响应 | `user_answer` | str | 回显 |
| 响应 | `is_correct` | bool \| null | **null = 未判分**（无参考答案或 AI 失败） |
| 响应 | `score` | float \| null | 0–10，一位小数 |
| 响应 | `correct_answer` | str \| null | 单选时为参考答案；简答为 null |
| 响应 | `reference_answer` | str \| null | 简答时为参考答案 |
| 响应 | `explanation` | str \| null | 解析 |
| 响应 | `progress` | object | `answered_count` / `correct_count` / `total` |

**POST `/api/practice/sessions/{id}/finish`** → 会话小结：

| 字段 | 说明 |
|---|---|
| `session_id` / `status` | `finished` |
| `total` / `answered_count` / `correct_count` | 计数 |
| `unscored_count` | **未判分题数**（让候选人知道有几题没判出来，而非误以为答错） |
| `accuracy` | `correct_count / answered_count`；分母为 0 时为 `null` |
| `by_dimension` | `[{dimension, answered, correct, accuracy}]` |

**GET `/api/practice/wrong-book`** 查询参数：`position_id` / `dimension` / `question_type` / `limit`（缺省 50，上限 200）

→ 数组项：

| 字段 | 说明 |
|---|---|
| `question_id` | — |
| `content` | 题干（**取最近一次练习的 `content_snapshot`**） |
| `options` | 选项快照 |
| `reference_answer` / `explanation` | 参考答案与解析 |
| `my_wrong_answer` | 最近一次的错误作答 |
| `wrong_count` | **累计判错次数** |
| `last_wrong_at` | 最近判错时间 |

> **按 `question_id` 去重**：同一道题练错多次只出现一行，并给出 `wrong_count`。逐条罗列会让错题本被同一道题刷屏，失去「该复习哪些题」的作用。

**GET `/api/practice/stats`** → ：

| 字段 | 说明 |
|---|---|
| `total_answered` | 累计已作答数（**只统计已作答的项**） |
| `scored_count` / `unscored_count` | 已判分 / 未判分数 |
| `correct_count` / `accuracy` | 正确率的分母是 `scored_count`（**未判分的题不计入正确率**） |
| `session_count` | 练习次数 |
| `by_dimension` | `[{dimension, answered, scored, correct, accuracy}]` |
| `by_type` | `[{question_type, answered, scored, correct, accuracy}]` |

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `preview_questions(db, user, filters, limit) -> list[Question]` | 题目列表 | 经 question 供给契约取题（不含答案） |
| `start_session(db, user, data: PracticeSessionCreate) -> SessionDetail` | 会话详情 | 取题 → 建会话 → 建待答项（写快照）（§5.1） |
| `get_session(db, user, session_id) -> SessionDetail` | 会话详情 | 归属校验（§4.5） |
| `submit_item(db, user, session_id, item_id, user_answer) -> ItemResult` | 判分结果 | 判分分支与降级（§5.3） |
| `finish_session(db, user, session_id) -> SessionSummary` | 小结 | 幂等（§5.6） |
| `list_wrong_book(db, user, filters, limit) -> list[WrongBookItem]` | 错题本 | 派生查询（§5.5） |
| `get_stats(db, user) -> PracticeStats` | 统计 | 派生查询（§5.7） |
| `rescore_item(db, user, item_id) -> ItemResult` | 判分结果 | **按题重判**（供未判分项补判，见 §5.4） |
| `list_my_sessions(db, user, status: str | None, limit: int) -> list[SessionListItem]` | 列表 | 仅本人的会话；按 `started_at` 倒序（§5.9） |

`PracticeFilters` 字段：`position_id: int | None`、`category: str | None`、`dimension: str | None`、`difficulty: str | None`、`question_type: str | None`。

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create_session(db, **fields) -> PracticeSession` | 会话 | — |
| `create_items(db, items: list[dict]) -> list[PracticeItem]` | 待答项 | 批量写入（含快照） |
| `get_session_by_id(db, session_id: int) -> PracticeSession \| None` | 会话 | **不带权限过滤** |
| `get_item_by_id(db, item_id: int) -> PracticeItem \| None` | 待答项 | 同上 |
| `list_items(db, session_id: int) -> list[PracticeItem]` | 列表 | **按 `seq` 升序** |
| `update_item(db, item: PracticeItem, **fields) -> PracticeItem` | 待答项 | — |
| `recount(db, session_id: int) -> tuple[int, int]` | (answered, correct) | **重算计数**（§5.3） |
| `update_session(db, session: PracticeSession, **fields) -> PracticeSession` | 会话 | — |
| `list_wrong_items(db, candidate_user_id: int, filters, limit: int) -> list[dict]` | 派生行 | 按 `question_id` 分组取最近一次 + `count(*)` |
| `aggregate_stats(db, candidate_user_id: int) -> dict` | 聚合结果 | 总量 / 已判分 / 正确数 / 按维度 / 按题型 |
| `list_by_candidate(db, candidate_user_id: int, status: str \| None, limit: int) -> list[PracticeSession]` | 列表 | **新增**：仅本人的会话，按 `started_at` 倒序；联 `position` 取 `position_name` |

> **`get_session_by_id` / `get_item_by_id` 不带权限过滤**，与既有 repository 约定一致（module-03 §4.4 的注释「不带权限过滤 —— 权限判定在 service」）。归属校验在 service 的 §4.5 完成。

### 4.5 资源归属校验（**`ensure_owner_match`，本模块对 auth 的增量请求**）

| 项 | 说明 |
|---|---|
| 需要的签名 | `auth.service.ensure_owner_match(user: User, owner_id: int, label: str) -> None` |
| 语义 | `user.role == 'admin'` → 通过；否则 `user.id == owner_id` → 通过；否则 `ForbiddenError`（403） |

**为什么不能用既有的 `ensure_resource_visible`**：

| 函数 | 对 candidate 的行为 | 能否用于 practice |
|---|---|---|
| `ensure_resource_visible` / `scope_owner_id` | **抛 `ForbiddenError`**（[module-16 §4](./2026-09-20-module-16-permission-guard-plan.md)：非 admin/hr 一律拒绝，作为纵深防御） | ✗ 候选人调用自己的练习也会被拒 |
| `ensure_owner_match` | `owner_id == user.id` → 通过 | ✓ |

> 两者的分工必须写清楚，避免后来者用错：**`scope_owner_id` 回答「HR 能看到哪些（按 `created_by`）」，`ensure_owner_match` 回答「这条记录是不是我的」**。前者是 HR 数据范围的判定函数，后者是通用的归属判定。practice 的 `candidate_user_id`、以及未来任何「非 HR 拥有的资源」都归后者管。

---

## 5. 业务流程设计

### 5.1 开始练习

```
1. 限流检查（§5.8）
2. size = min(data.size or PRACTICE_SESSION_SIZE_DEFAULT, PRACTICE_SESSION_SIZE_MAX)
3. questions = question.service.list_practice_questions(db, filters, size)
       —— 不按 created_by 过滤（module-10 §5.5 的有意放宽）
4. 若 questions 为空 → BusinessError（409）「没有符合条件的题目」
       —— 不建空会话：空会话对候选人毫无价值，且会污染练习次数统计
5. 建 practice_session：记筛选条件、total = len(questions)、status='ongoing'
6. 建 practice_item：按 questions 顺序逐个写 item（seq 从 1 开始）
       content_snapshot       ← question.content
       options_snapshot       ← question.options
       reference_answer_snapshot ← question.reference_answer（**可能为 NULL**）
       dimension_snapshot     ← question.dimension
       question_type          ← question.question_type
       user_answer = NULL，is_correct = NULL，score = NULL
7. commit；返回会话详情（题目经 PracticeQuestionOut 序列化，**不含答案**）
```

| 要点 | 说明 |
|---|---|
| **取不到题不建会话** | 空会话会让「练习次数」虚增，且前端无从解释 |
| **题数不足时按实际数量建会话** | 不补齐、不报错（与 interview 出题「AI 返回不足时按实际入库」同一态度，module-05 §5.2） |
| **快照在会话开始时写满** | 与 PRD §5.2 一致。题库后续删改不影响进行中与历史练习 |
| `reference_answer_snapshot` 允许为 NULL | 存量题目没有参考答案，或 HR 尚未补录 |

### 5.2 判分分支（**本模块的核心逻辑**）

```
submit_item(db, user, session_id, item_id, user_answer):
1. 归属校验：session 存在且属于本人 → 否则 404 / 403（§4.5）
2. 校验会话 status == 'ongoing'
       已 finished → BusinessError（409）「本次练习已结束，不可继续作答」
3. 校验 item 属于该 session → 否则 NotFoundError（404）
4. 参考答案来源（**快照优先，为空则读题库当前值并回填快照**）：
       ref = item.reference_answer_snapshot
       若 ref 为空 且 item.question_id 对应的 question.reference_answer 非空
           → ref = question.reference_answer，并**回填** item.reference_answer_snapshot
5. 分支判分：
   a) user_answer.strip() == ""          → 未作答
        is_correct = False，score = 0.0，explanation = "未作答"
   b) item.question_type == 'single_choice'
        is_correct = (user_answer.strip() == ref.strip())      ← 本地规则，不调 AI
        score = 10.0 if is_correct else 0.0
        explanation 取题库解析（可能为 NULL）
   c) item.question_type == 'short_answer' 且 ref 非空
        调 provider.grade_practice_answer('short_answer', content_snapshot, ref, user_answer)
        is_correct = result.is_correct，score = result.score，explanation = result.explanation
   d) item.question_type == 'short_answer' 且 ref 为空
        → **不调用 AI**：is_correct = NULL，score = NULL，explanation = "该题暂无参考答案，本次不判分"
6. 写 item：user_answer、is_correct、score、explanation、answered_at = now
7. 重算会话计数：answered_count / correct_count = repository.recount(session_id)
8. commit；返回判分结果
```

| 决策 | 理由 |
|---|---|
| **第 4 步「快照优先，为空回退题库当前值」** | 会话开始时 HR 可能还没补参考答案（存量题、或还没点「AI 补答案」）。若死守空快照，这些题**永远判不了分**；回填保证后续一致性，也让「HR 补录答案后重新刷同一题」能正常判分 |
| **第 5d 步不调用 AI** | `ai.grade_practice_answer` 对空参考答案会抛 `AIProviderError`（[module-11 §4.2](./2026-09-20-module-11-ai-plan.md)）。在 service 层提前判断，比让 provider 抛错再降级更清晰，也省掉一次无意义的调用 |
| **单选不调 AI** | PRD §4.7 明确要求 |
| **空作答 0 分** | 与既有约定一致（module-05 §4.2「允许空串，表示候选人未作答，评估时按 0 分处理」） |
| **`is_correct = NULL` 而非 `False`** | 「未判分」与「判错」是不同事实，错题本与正确率都必须区别对待（§5.5、§5.7） |

### 5.3 AI 判分失败的降级（PRD §7）

```
catch AIProviderError from provider.grade_practice_answer:
    不抛出给调用方；写 item：
        user_answer 正常保存
        is_correct = NULL，score = NULL
        explanation = "AI 判分暂时不可用，本题稍后可重判"
    记 warning 日志（含 session_id / item_id）
    返回 200（**不返回 5xx**）—— 作答本身已成功保存
```

| 要点 | 说明 |
|---|---|
| **不返回 502** | PRD §7 要求「刷题 AI 判分失败 → 不阻塞作答：`practice_item` 正常落库但 `is_correct` 为空」。若返回 502，前端会以为提交失败并重试，而作答其实已保存——**响应语义与事实不符是最糟的组合** |
| 与评估失败的处理**不同** | 评估失败要回退状态（`evaluating → completed`），因为评估是**有状态的流程**；刷题判分是**无状态的计算**，失败只需记为未判分 |
| 可重判 | §5.4 提供入口，把两态（有/无判分）的差异交给候选人主动弥补，而不是引入后台任务 |

### 5.4 按题重判

```
rescore_item(db, user, item_id):
1. 归属校验（经其 session 的 candidate_user_id）
2. 若 item.is_correct 非 NULL → 幂等：直接返回既有结果，不重复判分
3. 否则重走 §5.2 的第 4～7 步（重新取参考答案、重新判分、重算计数）
```

| 要点 | 说明 |
|---|---|
| **仅允许重判未判分项** | 已判分的项重判会改变正确答案与分数，等于允许「刷分」。这条限制是必要的 |
| 端点归属 | 复用 `POST /practice/sessions/{id}/items` 并在请求体加 `rescore: bool`？**否**——语义不同的动作给独立端点更清晰：`POST /api/practice/items/{item_id}/rescore`（独立端点，登记于 §4.1） |
| 计数重算 | 重判成功后同样调 `recount`，因此不需要「补偿」逻辑 |

> **`recount` 而非累加的原因**：同一题可重复提交（错题重练是刷题的正当用法）。若用 `answered_count += 1` 累加，重复提交会让计数超过 `total`。**重算永远等于事实**，累加则依赖「每次都能正确判断该不该加」这一脆弱假设：
> ```
> answered_count = count(items where user_answer is not null)
> correct_count  = count(items where is_correct is true)
> ```
> 注意 `answered_count` 用 `user_answer is not null` 判定（**含空串**——空串是「提交了但未作答」，仍占一个已作答位），与 §5.2 第 5a 步给空串判 0 分是一致的。

### 5.5 错题本（派生查询）

```
1. 取该用户的全部 practice_item，联 practice_session 限定 candidate_user_id = user.id
2. 仅保留 is_correct IS FALSE（**未判分的 NULL 不算错题**）
3. 按 question_id 分组：
     取该组最新一条（answered_at 最大）作为展示行
     wrong_count = 该组记录数
4. 按 last_wrong_at 倒序；limit 生效
```

| 要点 | 说明 |
|---|---|
| **`is_correct IS FALSE` 而非 `NOT is_correct`** | SQL 中 `NOT NULL` 的结果是 NULL（不成立），看似安全，但写成 `is_correct = false` 或 `is_correct IS FALSE` 才是显式意图。**必须显式排除 NULL**，否则未判分的题会混入错题本 |
| 展示内容取「最近一次」的快照 | 同一题在不同会话中的题干可能已被 HR 修改；展示最近一次的版本最贴合记忆 |
| 不做 `wrong_book` 表 | PRD §4.7 明确「不单独建表」。派生查询的成本由 `ix_practice_item_correct` 索引承担 |
| 已删除的题目 | `question_id` 外键为 `RESTRICT`，题目被练习引用后不可删除（与既有题目删除规则一致），因此不存在「错题指向已删题」的情形 |

### 5.6 结束练习

```
finish_session(db, user, session_id):
1. 归属校验
2. 若 status == 'finished' → **幂等**：直接返回既有小结，不报错
3. status = 'finished'，finished_at = now
4. 组装小结（§4.2 的字段）：
     total / answered_count / correct_count / unscored_count
     accuracy = correct_count / answered_count（分母 0 → null）
     by_dimension（按 dimension_snapshot 分组）
5. commit
```

| 要点 | 说明 |
|---|---|
| **允许未答完就结束** | PRD 未禁止；强行要求答完会让人无法退出 |
| **幂等** | 重复调用返回同一小结（与候选人交卷的幂等同一态度，module-12 §5.5） |
| 结束后不能再作答 | §5.2 第 2 步拦截 |
| **`by_dimension` 的必要性** | 它就是 PRD §4.7 要求的「按维度正确率」在小结里的呈现，与 `GET /stats` 的同一字段共用同一段聚合逻辑 |

### 5.7 练习统计

| 指标 | 口径 |
|---|---|
| `total_answered` | `count(user_answer IS NOT NULL)`，跨全部会话 |
| `scored_count` | `count(is_correct IS NOT NULL)` |
| `correct_count` | `count(is_correct IS TRUE)` |
| `accuracy` | `correct_count / scored_count`；`scored_count == 0` → `null` |
| `by_dimension` / `by_type` | 同上口径，按 `dimension_snapshot` / `question_type` 分组 |

> **正确率的分母是「已判分」而不是「已作答」**：未判分的题既不算对也不算错，把它放进分母会**低估**候选人的正确率，且这个低估与候选人的水平无关（只是 AI 没判出来）。分母口径必须在文档里写死，否则统计页与小结页会各算一套。

### 5.8 限流（进程内计数，PRD §2、§7）

| 项 | 设计 |
|---|---|
| 计数维度 | 按 `candidate_user_id` |
| 计数对象 | 计分动作：开始练习、提交作答、重判（读接口不计） |
| 窗口 | 滑动 60 秒，上限 `PRACTICE_RATE_LIMIT_PER_MINUTE`（默认 60） |
| 实现 | 模块级 `dict[int, deque[float]]` + 时间戳队列；**进程内**，不引入 Redis |
| 超限 | `BusinessError`（409）「操作过于频繁，请稍后再试」 |
| 清理 | 每次访问该用户的队列时顺带剔除窗口外的旧时间戳（无需后台清理线程） |

| 单机约束带来的限制（须在 README 声明） | 说明 |
|---|---|
| `--workers 1` | 多进程下计数各自独立，限流会失效（与 module-06 §5.6 的 SSE 限制同一根因） |
| 进程重启后计数清零 | 可接受：限流是防误用与防脚本刷题，不是计费 |

### 5.9 列出我的会话

```
list_my_sessions(db, user, status, limit):
1. limit 上限校验（> PRACTICE_SESSION_LIST_MAX → 400）
2. repository.list_by_candidate(db, candidate_user_id=user.id, status, limit)
3. 联 position 取岗位名；组装筛选条件摘要
4. 返回（**不含题目明细**）
```

| 要点 | 说明 |
|---|---|
| **只查本人**（`candidate_user_id = user.id`） | 隔离在 SQL 条件里，不依赖「取回来再过滤」——后者一旦忘记过滤就会泄露他人练习 |
| 排序 | 按 `started_at` **倒序**：最近练的在最上面（与「继续未完成的练习」的用途一致） |
| `status=None` 返回全部 | 前端可一次拿到「进行中 + 历史」并自行分组，减少请求 |
| **不过滤未判分项** | 与错题本不同，会话列表只关心会话本身 |
| 无会话时 | 返回空数组（不是 404）——「还没练过」是正常状态 |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 没有符合条件的题目 | `BUSINESS_ERROR` | 409 | 没有符合条件的题目，请调整筛选条件 |
| 会话不存在 | `NOT_FOUND` | 404 | 练习不存在 |
| 会话不属于本人 | `FORBIDDEN` | 403 | 无权限访问该练习 |
| item 不属于该会话 | `NOT_FOUND` | 404 | 题目不属于该练习 |
| 会话已结束仍提交 | `BUSINESS_ERROR` | 409 | 本次练习已结束，不可继续作答 |
| 重判已判分的项 | — | **200** | **不报错**：幂等返回既有结果（§5.4） |
| AI 判分失败 | — | **200** | **不报错**：`is_correct` 为空，见 §5.3 |
| 简答题无参考答案 | — | **200** | 同上：`is_correct` 为空，解析为「该题暂无参考答案，本次不判分」 |
| 题量超上限 | `VALIDATION_ERROR` | 400 | `size` 不能超过 20 |
| `user_answer` 超 5000 字符 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 限流超限 | `BUSINESS_ERROR` | 409 | 操作过于频繁，请稍后再试 |
| 守卫角色不符（hr/admin 调用） | `FORBIDDEN` | 403 | 无权限执行此操作（module-16） |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。特别注意「AI 判分失败」在这里是 **200 而非 502**，这是 PRD §7 的明确要求。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 会话与取题

| 测试 | 断言 |
|---|---|
| `test_start_session_writes_snapshots` | 每个 item 的 `content_snapshot` / `options_snapshot` / `dimension_snapshot` / `question_type` / `reference_answer_snapshot` 与题库一致 |
| `test_start_session_default_size` | 不传 `size` → `total == PRACTICE_SESSION_SIZE_DEFAULT` |
| `test_start_session_size_capped` | 传 `size=999` → 400（超上限），**不静默截断** |
| `test_start_session_insufficient_questions` | 只有 3 题符合 → `total == 3`，不报错 |
| `test_start_session_no_questions` | 无符合题 → 409，**且未创建会话记录** |
| `test_start_session_filters_applied` | 按维度 + 题型筛选 → 取到的题全部符合 |
| `test_start_session_uses_other_hrs_questions` | **hr_a 与 hr_b 各建一题** → 候选人取题两题都能拿到（module-10 §5.5 的放宽） |
| `test_start_session_creates_no_extra_session_on_failure` | §7.1 第 5 条的连带断言：`practice_session` 表无新增行 |

### 7.2 判分分支（**本模块最重要的测试组**）

| 测试 | 断言 |
|---|---|
| `test_grade_single_choice_correct` | 选对 → `is_correct=True`，`score=10.0`，**未调用 provider**（用 spy 断言） |
| `test_grade_single_choice_wrong` | 选错 → `is_correct=False`，`score=0.0` |
| `test_grade_single_choice_ignores_whitespace` | 作答两侧有空白 → 仍判对 |
| `test_grade_short_answer_calls_ai` | 简答 → 调用了 `grade_practice_answer`，参数为**原始值**（str），非 ORM 对象 |
| `test_grade_short_answer_uses_ai_result` | `is_correct` / `score` / `explanation` 取自 provider 结果 |
| `test_grade_short_answer_no_reference_is_unscored` | 简答且无参考答案 → `is_correct IS NULL`、`score IS NULL`，**未调用 provider** |
| `test_grade_empty_answer_zero` | 空串 / 纯空白 → `is_correct=False`，`score=0.0`，解析为「未作答」 |
| `test_grade_empty_answer_does_not_call_ai` | 空作答**未调用 provider**（省一次调用） |
| `test_grade_ai_failure_marks_unscored` | 注入抛 `AIProviderError` 的 provider → **200**，`user_answer` 已保存，`is_correct IS NULL`，解析提示可重判 |
| `test_grade_ai_failure_does_not_rollback_answer` | 上述场景下重新读取会话，作答**确实已持久化** |
| `test_grade_backfills_reference_from_question` | 会话建立时无参考答案 → HR 补录后提交 → 判分成功，**且快照被回填** |
| `test_grade_keeps_existing_snapshot_over_question` | 快照已有答案而题库答案后来被改 → 判分用**快照**（不被新值覆盖） |
| `test_grade_after_finish_rejected` | 会话已结束 → 409 |
| `test_grade_other_session_item_rejected` | 传别会话的 `item_id` → 404 |
| `test_grade_other_candidates_session_forbidden` | 候选人 A 提交 B 的会话 → 403 |

### 7.3 计数、错题本与统计

| 测试 | 断言 |
|---|---|
| `test_recount_after_reanswer` | 同一题提交两次（先错后对）→ `answered_count == 1`、`correct_count == 1`（**不重复累加**） |
| `test_recount_counts_blank_answers` | 提交空串 → 仍计入 `answered_count`（§5.3 的口径） |
| `test_recount_excludes_unscored_from_correct` | 有未判分项时 `correct_count` 不含它们 |
| `test_wrong_book_excludes_unscored` | 未判分（`is_correct IS NULL`）的题**不出现**在错题本 |
| `test_wrong_book_dedupes_by_question` | 同一题错 3 次 → **1 行**，`wrong_count == 3` |
| `test_wrong_book_uses_latest_snapshot` | 题干被改后再次练错 → 展示最近一次的题干 |
| `test_wrong_book_isolated_by_candidate` | 候选人 A 看不到 B 的错题 |
| `test_wrong_book_ordered_by_last_wrong_at` | 按最近判错时间倒序 |
| `test_stats_accuracy_denominator_is_scored` | 答 3 题、2 题判分、其中 1 题对 → `accuracy == 0.5`（分母 2 而非 3） |
| `test_stats_accuracy_null_when_nothing_scored` | 全部未判分 → `accuracy is None`（不出现除零错误） |
| `test_stats_by_dimension_uses_snapshot` | 题库维度改名后，统计仍按 `dimension_snapshot` 归集 |
| `test_stats_isolated_by_candidate` | 候选人 A 的统计不含 B 的数据 |

### 7.4 结束练习、重判、会话列表与限流

| 测试 | 断言 |
|---|---|
| `test_finish_sets_status_and_time` | `status='finished'`，`finished_at` 非空 |
| `test_finish_is_idempotent` | 二次结束 → 200，`finished_at` **不变** |
| `test_finish_reports_unscored_count` | 有未判分项 → `unscored_count` 正确 |
| `test_finish_allows_incomplete_session` | 只答了 1/5 题 → 允许结束 |
| `test_rescore_unscored_item` | 未判分项重判成功（provider 已恢复）→ `is_correct` 被填充，计数更新 |
| `test_rescore_scored_item_is_idempotent` | 已判分项重判 → 返回既有结果，**未再次调用 provider** |
| `test_rescore_other_candidates_item_forbidden` | 403 |
| `test_rate_limit_rejects_after_threshold` | 第 `LIMIT+1` 次计分动作 → 409 |
| `test_rate_limit_is_per_user` | 候选人 A 触发限流后，B 仍可正常提交 |
| `test_rate_limit_window_slides` | 窗口外的时间戳被剔除后，请求重新放行 |

**会话列表（§5.9）**

| 测试 | 断言 |
|---|---|
| `test_list_sessions_only_own` | 候选人 A 的列表**不含** B 的会话 |
| `test_list_sessions_includes_ongoing` | 建两个会话（一个已结束、一个进行中）→ 缺省返回**两条** |
| `test_list_sessions_filter_status` | `status=ongoing` → 只返回进行中的 |
| `test_list_sessions_ordered_by_started_desc` | 最近开始的排在最前 |
| `test_list_sessions_excludes_item_details` | 响应中**不出现**题目明细字段（`content` / `options` 等） |
| `test_list_sessions_empty_returns_empty_array` | 无会话 → 200 且 `[]`（不是 404） |
| `test_list_sessions_limit_capped` | `limit` 超上限 → 400，**不静默截断** |
| `test_list_sessions_rejects_hr` | hr / admin → 403 |

### 7.5 架构约束登记（⚠️ 容易漏）

| 测试 | 断言 |
|---|---|
| `test_eight_modules_exist`（`test_architecture.py`，**改**） | `ALL_MODULES` 含 `practice` |
| `test_five_layer_files_exist[practice]` | `models.py` / `schemas.py` / `repository.py` / `service.py` / `router.py` 齐备 |
| `test_no_reverse_dependency[practice]` | 禁止依赖 `interview` / `position` / `evaluation` |
| `test_ai_depends_on_no_business_module`（既有，仍须通过） | 未被破坏 |

> **不登记 = 不受保护**：`test_architecture.py` 用硬编码模块名列表驱动全部结构约束。`practice` 不登记时这些测试**依然全绿**，但它们已经不再覆盖新包——这是最容易被忽视的一类失效。已记入 [module-08 §7.2](./2026-09-15-module-08-e2e-plan.md)。

### 7.6 鉴权与隔离

| 测试 | 断言 |
|---|---|
| `test_practice_endpoints_reject_hr` | hr 对七个端点 → 403 |
| `test_practice_endpoints_reject_admin` | admin 对七个端点 → **403**（module-09 §4.5 的精确匹配规则） |
| `test_practice_endpoints_reject_anonymous` | 无 token → 401 |
| `test_session_detail_hides_reference_before_submit` | 会话详情中**未提交**的 item 的 `explanation` / `reference_answer` 为 null |
| `test_session_detail_reveals_after_submit` | 已提交的 item 才返回解析与参考答案 |
| `test_preview_response_has_no_answer_fields` | `PracticeQuestionOut` 序列化结果**不含** `reference_answer` / `explanation` 键 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-09（`require_roles`）、module-10（`list_practice_questions` 与 `PracticeQuestionOut`）、module-11（三个 AI 方法与 `PASS_THRESHOLD`）、module-16（守卫）已完成。

### Task 13.1：包骨架与架构登记

- [ ] 建 `app/practice/` 五层空文件 + `__init__.py`
- [ ] **把 `practice` 登记进 `backend/tests/test_architecture.py` 的三个列表**
- [ ] 运行 `pytest tests/test_architecture.py -v`，确认新参数化用例已生效（此时因缺实现而失败）
- [ ] 提交

### Task 13.2：模型与迁移

- [ ] `models.py` 定义两张表（§3.1、§3.2 全字段与索引）
- [ ] 生成迁移，同步 `backend/script.sql`
- [ ] 写失败测试：`is_correct` 可为 NULL；`UNIQUE (session_id, seq)` 生效
- [ ] `alembic upgrade head` / `downgrade` 验证
- [ ] 提交

### Task 13.3：`ensure_owner_match`（auth 增量）

- [ ] 写失败测试：admin 通过；`owner_id == user.id` 通过；候选人访问他人 → 403
- [ ] 运行确认失败
- [ ] 在 `auth/service.py` 实现
- [ ] 运行确认通过；跑 `test_auth.py` 确认零回归
- [ ] 提交

### Task 13.4：配置项

- [ ] `core/config.py` 新增三个配置项；`.env.example` 补键
- [ ] 写失败测试：默认值与上限校验生效
- [ ] 提交

### Task 13.5：repository 层与派生查询

- [ ] 实现 §4.4 全部方法（含 `recount`、`list_wrong_items`、`aggregate_stats`）
- [ ] 写失败测试：`recount` 在重复提交后不超计；`list_wrong_items` 排除未判分并按题去重
- [ ] 运行确认通过
- [ ] 提交

### Task 13.6：开始练习与取题

- [ ] 写 §7.1 全部失败测试（**含「无题不建会话」与「跨 HR 取题」**）
- [ ] 运行确认失败
- [ ] 实现 `preview_questions` / `start_session` 与两个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 13.7：判分分支与降级

- [ ] 写 §7.2 全部失败测试（**含「单选不调 AI」「空作答不调 AI」「无答案不调 AI」「AI 失败返回 200 且作答已落库」**）
- [ ] 运行确认失败
- [ ] 实现 `submit_item`（含快照回退逻辑与 §5.3 降级）
- [ ] 运行确认通过
- [ ] 提交

### Task 13.8：计数、错题本与统计

- [ ] 写 §7.3 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `recount` 的调用点、`list_wrong_book`、`get_stats` 与三个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 13.9：结束练习与重判

- [ ] 写 §7.4 中结束 / 重判的失败测试（**含两条幂等断言**）
- [ ] 运行确认失败
- [ ] 实现 `finish_session` / `rescore_item` 与两个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 13.10：会话列表

- [ ] 写 §7.4 会话列表的 8 条失败测试（**含「只查本人」与「不含题目明细」**）
- [ ] 运行确认失败
- [ ] 实现 `repository.list_by_candidate` 与 `service.list_my_sessions`，注册 `GET /practice/sessions`
- [ ] 运行确认通过
- [ ] 提交

### Task 13.11：限流

- [ ] 写 §7.4 中限流的三条失败测试
- [ ] 运行确认失败
- [ ] 实现进程内滑动窗口计数器
- [ ] 运行确认通过
- [ ] 提交

### Task 13.12：鉴权、隔离与全量回归

- [ ] 写 §7.6 全部失败测试（**含「admin 也被拒」与「提交前后答案可见性」**）
- [ ] `conftest.py` 新增 `practice_session` 夹具
- [ ] 运行 `pytest tests/ -q`，**全部通过**（含架构测试的新参数化用例）
- [ ] 提交

---

## 9. 验收标准

- [ ] `practice` 成为**第八个 package**，五层文件齐备，**且已登记进 `test_architecture.py`**
- [ ] 两张表建成，索引齐备；`practice_item.is_correct` 为**三态**（TRUE / FALSE / NULL）
- [ ] 会话开始即写满题目快照（含补充的 `dimension_snapshot` 与 `question_type`）
- [ ] 取不到题 → 409 **且不创建会话**
- [ ] 单选题判分**不调用 AI**；简答题调用 AI 并传**原始值**
- [ ] 简答无参考答案 / 空作答 → **不调用 AI**，空作答记 0 分，无答案记未判分
- [ ] AI 判分失败 → **200**，作答已持久化，`is_correct IS NULL`，可重判
- [ ] 参考答案「快照优先，为空回退题库当前值并回填」
- [ ] 会话计数用**重算**而非累加：重复提交同一题不超计
- [ ] 错题本**排除未判分**、按题去重并给出 `wrong_count`
- [ ] 统计正确率的分母是**已判分**数；全部未判分时 `accuracy` 为 `null`
- [ ] 结束练习幂等；结束后不可再作答
- [ ] 重判仅对未判分项生效；已判分项重判幂等且不重复调用 AI
- [ ] 限流为**进程内**滑动窗口，按用户独立，超限 409
- [ ] 候选人取题/提交响应**不含**参考答案与解析（未提交时）；提交后才返回
- [ ] **九个**端点对 hr 与 admin **一律 403**（含重判与会话列表）
- [ ] **（新增）** `GET /practice/sessions` 只返回**本人的**会话，含进行中的；按 `started_at` 倒序；**不含题目明细**
- [ ] `ensure_owner_match` 已加入 `auth.service`，且未破坏既有隔离行为
- [ ] 未新增任何错误码；既有用例零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **`practice` 不登记进架构测试＝结构约束失效** | Task 13.1 第一件事就是登记 | 该文件用硬编码模块名列表驱动约束；不登记则测试全绿但不再覆盖新包——静默失效最危险 |
| **候选人资源归属不能复用 `ensure_resource_visible`** | 新增 `auth.service.ensure_owner_match` | 既有函数对 candidate 角色会直接抛 403（module-16 的纵深防御），候选人连自己的练习都读不到。两个函数的分工已在 §4.5 写明 |
| **判分失败返回 200 而非 502** | 200 + `is_correct` 为空 | PRD §7 的明确要求。若返回 502，前端会认为提交失败并重试，而作答其实已保存——响应与事实不符 |
| **计数用重算而非累加** | `recount` 每次提交后重算 | 允许重复提交（错题重练是正当用法）。累加依赖「每次都能正确判断该不该加」这一脆弱假设 |
| 正确率分母用「已判分」 | 用 `scored_count` | 未判分的题与候选人水平无关（是 AI 没判出来），放进分母会系统性低估 |
| 错题本不建表、按题去重 | 派生查询 + 分组 | PRD §4.7 明确不建表；不去重会让同一题刷屏，失去「该复习哪些题」的作用 |
| `practice_item` 补充 `dimension_snapshot` / `question_type` | 补充并登记到 module-08 | 不加则统计随题库改名漂移、判分分支随题库改动崩溃 |
| 简答题参考答案为空时不调 AI | service 层提前判断 | provider 对空参考答案会抛错（module-11 §4.2）；提前判断比「抛错再降级」更清晰，也省一次调用 |
| 快照为空时回退读题库当前值并回填 | 回退 + 回填 | 否则会话建立时 HR 尚未补答案的题**永远判不了分** |
| 结束后不可再作答；重判只对未判分项 | 两条硬限制 | 前者保证小结的语义稳定；后者防止「刷分」 |
| 限流进程内实现 | 接受 + README 声明 `--workers 1` | PRD §2 禁止引入 Redis。多进程下限流失效，与 SSE 的多 worker 限制同一根因 |
| 空会话不创建 | 取不到题直接 409 | 空会话污染练习次数统计，对候选人无价值 |
| 不做后台批量重判 | 只提供按题重判入口 | 后台任务需要调度器（违反单机约束）；把补偿动作交给候选人主动触发更简单 |
| 是否支持「只练错题」模式 | **本 MVP 不做** | PRD §4.7 的筛选条件里没有它；错题本本身就是该能力的入口，候选人可据此自查。引入需新增筛选维度与跨会话取题逻辑 |
