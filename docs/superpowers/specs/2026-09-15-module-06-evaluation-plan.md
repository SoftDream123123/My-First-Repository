# evaluation 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：evaluation（流式评估与报告）
**所属包**：`backend/app/evaluation/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.5（评估与报告）、§5.2（三个实体）、§5.3 ③（流式评估）、§7（AI 失败与 SSE 断连）、§8（evaluation API）
**前置依赖**：core（[00](./2026-09-15-module-00-core-plan.md)）、auth（[01](./2026-09-15-module-01-auth-plan.md)）、ai（[04](./2026-09-15-module-04-ai-plan.md)）、interview（[05](./2026-09-15-module-05-interview-plan.md)）

> **MVP-2 增量（2026-09-20）**：新增**面向候选人的脱敏反馈**（`candidate_feedback` 表 + `GET /api/candidate/interviews/{id}/feedback`），并在评估落库的**同一事务**内删除旧的候选人反馈缓存以使其失效。**HR 侧报告视图与三张评估表完全不变**。本文档的 Global Constraints、§1.1、§4.1、§5.2、§7.1、§10 已同步修正；**增量部分的完整契约以 [module-14 候选人脱敏反馈](./2026-09-20-module-14-evaluation-feedback-plan.md) 为准**。

---

## Global Constraints（全局约束，摘自 PRD）

- 后端分层：**router → service → repository → MySQL，严格单向依赖**（§2、§3.2）
- 每个模块独立 Python package（§2、§3.3）
- **评估以 SSE 流式返回**（§4.5、§5.3 ③）
- **评分统一 0–10 分制（逐题分、维度分、总分均 0–10）**（§4.5）
- 统一响应格式：**`{code, message, detail}`**（§7）
- **AI 调用失败**：重试 1 次 → 仍失败则**评估任务标记失败、状态回退 `completed`，可重新触发**；不阻塞其他功能（§7）
- **SSE 断连**：**评估任务后台继续，前端重连后可继续拉取进度或查询最终结果**（§7）
- **数据隔离（三端，MVP-2 起）**：admin 可访问全部；普通 HR 只能访问自己创建的面试的报告；**candidate 不拥有评估数据，只能读自己被邀请且已接受的面试的脱敏反馈**（§4.1、§4.6、§4.9）
- 仅 PC 端（§2）
- **（MVP-2）HR 侧端点必须显式校验角色（admin/hr）**；候选人侧端点校验 candidate，且 **admin 在候选人侧不通行**（§4.1、§9）
- **（MVP-2）候选人可见性为强制项**：反馈默认只下发综合结论/优点/待改进；**逐题分、维度分、雷达图在任何档位下都不下发**（§1.3、§4.9、§9）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.5）

| 子职责 | 内容 | PRD |
|---|---|---|
| 评估实体 | `question_score` / `dimension_score` / `report` 三张表的定义与迁移 | §5.2 |
| 评估编排 | 逐题评分 → 多维评分 → 汇总报告，三阶段顺序执行与结果落库 | §5.3 ③ |
| 流式推送 | 以 SSE 实时推送三阶段进度，支持断线重连与重放 | §4.5、§5.3 ③、§7 |
| 报告查询 | 提供结构化的完整报告（逐题 + 维度 + 汇总），供前端渲染雷达图 | §4.5、§8 |
| **候选人反馈视图（MVP-2）** | `candidate_feedback` 表；按档位下发**脱敏**反馈；重评时使缓存失效。**结论为面向本人的重写，不含去留判断**（2026-09-21 修正，PRD §4.9） | §4.5、§4.9 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **定义状态机** | 状态迁移合法性由 interview 模块的 `transition_*` 接口校验（PRD §5.1 将状态机列为 interview 职责）；evaluation 只**调用**，不自行判定 |
| **AI 调用细节** | 只调 `ai.factory.get_provider()`（PRD §6） |
| **读取回答数据的细节** | 通过 `interview.service.get_answers_for_evaluation` 获取 `QAPair`，**不直接查 interview 的表**（PRD §3.2 分层） |
| **PDF 导出 / 报告分享** | PRD §1.3 / §11 明确列入 V1.1 |
| **多候选人横向对比** | PRD §1.3 明确列入非目标 |
| **分布式任务队列** | MVP 采用**进程内**运行注册表（**限制声明见 §5.6**） |
| **评估历史版本留存** | 同一面试只保留**最近一次**评估结果（见 §5.4） |

### 1.3 依赖方向（对应 PRD §3.3）

```
evaluation.router ──→ evaluation.stream ──→ evaluation.service ──→ evaluation.repository ──→ evaluation 三张表
                            │                      │
                            │                      ├──→ ai.factory.get_provider()
                            │                      └──→ interview.service（QAPair / 维度 / 状态迁移）
                            └──→ auth.service.scope_owner_id

evaluation ──→ core, auth, ai, interview（单向）
evaluation ✗→ position / question（不需要）
interview ✗→ evaluation
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/evaluation/__init__.py` | 包标识 |
| `backend/app/evaluation/models.py` | `QuestionScore`、`DimensionScore`、`Report` 三个模型 |
| `backend/app/evaluation/schemas.py` | 事件结构与报告响应的 Pydantic 模型 |
| `backend/app/evaluation/repository.py` | 三张表的数据访问（读写、整批替换） |
| `backend/app/evaluation/service.py` | **同步**评估编排：三阶段执行 + 落库（**不含任何 SSE 逻辑**） |
| `backend/app/evaluation/stream.py` | 运行注册表、事件队列、SSE 事件生成与响应、重连重放、孤儿自愈 |
| `backend/app/evaluation/router.py` | `/api/interviews/{id}/evaluate`、`/evaluation/stream`、`/report` |
| `backend/app/evaluation/candidate_router.py` | **MVP-2 新增**：`/api/candidate/interviews/{id}/feedback`（守卫为 `candidate`，与 HR 端点分开文件） |

**测试文件**：`backend/tests/test_evaluation.py`、`backend/tests/test_evaluation_stream.py`；**MVP-2 新增** `backend/tests/test_candidate_feedback.py`

**本模块需修改的上游文件（MVP-2）**

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 另注册 `candidate_router`（前缀 `/api`） |
| `backend/alembic/versions/` | 新增 `candidate_feedback` 建表迁移 |
| `backend/script.sql` | 同步建表语句 |
| `backend/app/core/config.py` | 新增 `candidate_feedback_level`（默认 `summary`，**白名单校验 + 启动期 fail fast**） |
| `backend/.env.example` | 补 `CANDIDATE_FEEDBACK_LEVEL=summary` |

> **`service.py` 与 `stream.py` 的切分是本模块最关键的设计**：评估的**业务编排**（调 AI、写库、迁移状态）全部在 `service.py` 中，以**同步、回调式**的方式实现——它可以在**完全不涉及 SSE、不涉及异步**的情况下被单测。`stream.py` 只负责「把回调变成队列推送」「管理运行注册表」「生成 SSE 文本」，是一层薄薄的传输适配。
>
> 这样最复杂的业务逻辑获得了最简单的测试路径，契合 PRD §9/§10 对可测试性的要求。

---

## 3. 数据模型设计

### 3.1 表 `question_score`（逐题分）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, INDEX | 所属面试 |
| `interview_question_id` | BIGINT | NOT NULL, FK → `interview_question.id` **CASCADE** | 该题在面试中的唯一标识 |
| `score` | DECIMAL(3,1) | NOT NULL | **0.0–10.0**（PRD §4.5） |
| `comment` | TEXT | NOT NULL | 评语（PRD §4.5） |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |

**索引**：`UNIQUE (interview_id, interview_question_id)`

> **对 PRD §5.2 的修正**：PRD 中 `question_score` 以 `question_id` 标识，本设计改为 **`interview_question_id`**，与 interview §3.3 对 `answer` 的修正**保持一致**（同一面试内一题一条评分；库题可复用；消除 `(interview_id, question_id)` 组合的歧义）。

### 3.2 表 `dimension_score`（多维分，对应 PRD §4.5「用于雷达图」）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, INDEX | 所属面试 |
| `dimension` | VARCHAR(50) | NOT NULL | 维度名 |
| `score` | DECIMAL(3,1) | NOT NULL | 0.0–10.0 |
| `comment` | TEXT | NOT NULL | 评语 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |

**索引**：`UNIQUE (interview_id, dimension)`

> `dimension` 存**字符串**而非 ID，与 `position.evaluation_dimensions` 及 `question.dimension` 保持同一命名空间，评估打分时可直接按维度名归集，**无需联表**（PRD §5.2 的 `dimension_score` 字段设计）。

### 3.3 表 `report`（汇总报告，对应 PRD §5.2 与 §4.5）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, **UNIQUE** | 一次面试一份报告 |
| `overall_score` | DECIMAL(3,1) | NOT NULL | **总分**，0.0–10.0（PRD §4.5） |
| `conclusion` | TEXT | NOT NULL | **综合结论**（PRD §4.5） |
| `strengths` | JSON | NOT NULL | **优点**条目数组（PRD §4.5） |
| `weaknesses` | JSON | NOT NULL | **待改进**条目数组（PRD §4.5） |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 首次生成时刻 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT NOW, ON UPDATE NOW | 重新评估时更新 |

> `strengths` / `weaknesses` 用 JSON 数组列，与 ai §3.1 的 `ReportResult` 契约一致。

### 3.4 设计要点

| 要点 | 理由 |
|---|---|
| **`score` 用 `DECIMAL(3,1)` 而非浮点** | 评分保留 1 位小数；定点类型避免浮点误差累积到 `overall_score` 的平均计算中 |
| **全部外键 CASCADE** | 面试被删除时，评分与报告一并清除，无孤儿数据 |
| **`question_score` 冗余 `interview_id`** | 与 `interview_question_id` 存在传递依赖，但**保留是刻意的**——「清空某面试的全部评分」与「按面试查询」是最高频操作，冗余这一列让这两个操作免于联表。写入时由 service 从同一来源填充，不会不一致 |
| **三张表都不设 `evaluation_run_id`** | 同一面试只保留最近一次结果（§5.4），不做版本留存 |

---

## 4. 接口契约

### 4.1 对外 REST API（对应 PRD §8）

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/interviews/{id}/evaluate` | 触发评估，返回 SSE 流地址 | **admin, hr** + 可见 | **202** |
| GET | `/api/interviews/{id}/evaluation/stream` | SSE 事件流（PRD §5.3 ③） | **admin, hr** + 可见 | 200 |
| GET | `/api/interviews/{id}/report` | 获取完整报告 | **admin, hr** + 可见 | 200 |
| GET | `/api/candidate/interviews/{id}/feedback` | **MVP-2 新增**：候选人查看脱敏反馈 | **candidate** | 200 |

> **（MVP-2）「权限」列的变动**：原文写作「登录 + 可见」。引入 `candidate` 角色后「已登录」不再充分——候选人 token 同样满足它。自 MVP-2 起 HR 侧三个端点显式校验角色（`require_roles("admin","hr")`），守卫补全见 [module-16](./2026-09-20-module-16-permission-guard-plan.md)，**须与 module-09 同批发布**。
>
> **（MVP-2）第 4 个端点由独立文件提供**：`evaluation/candidate_router.py`（守卫为 `candidate`，与 HR 端点分开文件）。它的响应结构是**白名单** `CandidateFeedbackOut`（结构上不含逐题分、维度分与雷达图数据），完整契约见 [module-14 §4.2](./2026-09-20-module-14-evaluation-feedback-plan.md)。
>
> **HR 侧三个端点的响应结构与行为完全不变**（PRD §4.9）——`candidate_feedback` 是独立表，HR 报告接口**结构上读不到**候选人字段。

> **`POST /evaluate` 返回 202 Accepted**（而非 200）：语义是「已接受并开始后台处理」，与同步完成的 200 区分开。

### 4.2 请求 / 响应结构

**POST `/api/interviews/{id}/evaluate`**

| 方向 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 请求 | 无请求体 | — | — |
| 响应 | `interview_id` | int | — |
| 响应 | `status` | str | `"evaluating"`（PRD §5.1） |
| 响应 | `stream_url` | str | `/api/interviews/{id}/evaluation/stream` |

**幂等语义**：若该面试已有正在运行的评估，**不重复触发**，直接返回既有运行的 `stream_url`（仍为 202）。

**GET `/api/interviews/{id}/report`**（对应 PRD §4.5 的四项输出）

| 方向 | 字段 | 类型 | PRD §4.5 对应 |
|---|---|---|---|
| 响应 | `interview_id` | int | — |
| 响应 | `candidate_name` | str | — |
| 响应 | `position_name` | str | — |
| 响应 | `overall_score` | float | **总分** |
| 响应 | `conclusion` | str | **综合结论** |
| 响应 | `strengths` | list[str] | **优点** |
| 响应 | `weaknesses` | list[str] | **待改进** |
| 响应 | `evaluated_at` | datetime | 报告最后更新时间 |
| 响应 | `dimension_scores` | list[DimensionScoreItem] | **供雷达图**（PRD §4.5） |
| 响应 | `question_scores` | list[QuestionScoreItem] | **供逐题明细**（PRD §4.5） |

**DimensionScoreItem**：`dimension: str`、`score: float`、`comment: str`

**QuestionScoreItem**：`interview_question_id: int`、`seq: int`、`content: str`、`dimension: str`、`answer: str | null`、`score: float`、`comment: str`

> `content` / `dimension` / `answer` 取自面试的**快照与回答**（通过 interview §5.5 的供给接口），使报告页可独立渲染，**无需二次请求面试详情**。

### 4.3 SSE 事件契约（对应 PRD §5.3 ③）

**传输层设计**

| 项 | 设计 |
|---|---|
| 响应头 | `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no` |
| 认证 | **`Authorization: Bearer <token>` 请求头** |
| 客户端 | **必须用 `fetch` + `ReadableStream` 手动解析 SSE**，**不能使用 `EventSource`** |
| 心跳 | 每 **15 秒**推送一次 `event: ping`，防止代理 / 网关因空闲断开 |
| 重连 | 客户端断线后重新发起同一 GET 请求；服务端按 §5.5 重放（PRD §7） |

> **为何不能用 `EventSource`**：浏览器原生 `EventSource` **无法设置自定义请求头**，而本项目的鉴权完全依赖 `Authorization` 头（PRD §8「除登录外均需 JWT」）。把 JWT 放进 query string 会让令牌进入服务器访问日志、代理日志与浏览器历史——这是**可避免的泄露面**。因此前端需自建一个约 30 行的 SSE 解析工具（见 frontend 模块计划书）。

**事件类型与载荷**（对应 PRD §5.3 ③ 的三阶段）

| 事件名 | 触发时机 | `data` 字段 |
|---|---|---|
| `question` | 每完成一道题的评分 | `interview_question_id: int`、`seq: int`、`index: int`（第几题，从 1 起）、`total: int`（总题数）、`dimension: str`、`score: float`、`comment: str` |
| `dimension` | 每完成一个维度的评分 | `dimension: str`、`index: int`、`total: int`、`score: float`、`comment: str` |
| `report` | 汇总报告生成完成 | `overall_score: float`、`conclusion: str`、`strengths: list[str]`、`weaknesses: list[str]` |
| `done` | 全部完成、结果已落库、状态已置 `evaluated` | `status: "evaluated"` |
| `error` | 评估失败、状态已回退 | `code: str`、`message: str` |

**事件顺序保证**（PRD §5.3 ③）：

```
question（0..N 条，按 seq 升序）→ dimension（0..M 条，按维度顺序）→ report（恰好 1 条）→ done 或 error
```

`done` 与 `error` **互斥且必居其一**。

### 4.4 service 层方法签名（**同步、无 SSE**）

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `evaluate_interview(db: Session, interview_id: int, on_event: Callable[[EvaluationEvent], None]) -> None` | — | 三阶段编排；每完成一题/一维度/汇总各调用一次 `on_event`；成功后整批落库并迁移状态 |
| `get_report(db, user: User, interview_id: int) -> ReportDetail` | 报告详情 | 不存在/不可见 → 404/403；状态非 `evaluated` → 409 |
| `list_question_scores(db, interview_id: int) -> list[QuestionScore]` | 列表 | 按 `seq` 升序 |
| `list_dimension_scores(db, interview_id: int) -> list[DimensionScore]` | 列表 | 按写入顺序 |

`EvaluationEvent` 字段：`name: str`（`question` / `dimension` / `report`）、`payload: dict`。

> **`on_event` 回调的意义**：service 不需要知道事件要发到哪里（SSE 队列、日志、测试间谍）。这使得**三阶段编排可以在没有任何异步/网络设施的情况下被完整单测**。

### 4.5 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `replace_question_scores(db, interview_id: int, items: list[dict]) -> None` | — | **事务内**：删除该面试全部逐题分后批量插入 |
| `replace_dimension_scores(db, interview_id: int, items: list[dict]) -> None` | — | 同上 |
| `upsert_report(db, interview_id: int, data: dict) -> Report` | Report | 存在则更新，不存在则创建 |
| `list_question_scores(db, interview_id: int) -> list[QuestionScore]` | 列表 | 联 `interview_question` 取 `seq` |
| `list_dimension_scores(db, interview_id: int) -> list[DimensionScore]` | 列表 | — |
| `get_report(db, interview_id: int) -> Report \| None` | Report | — |
| `delete_all_for_interview(db, interview_id: int) -> None` | — | 清空三张表中该面试的全部数据（供失败清理，见 §5.4） |

> **（MVP-2）新增的表与方法不列在本节**：`candidate_feedback` 表与 `get_candidate_feedback` / `upsert_candidate_feedback` / `delete_candidate_feedback` 三个 repository 方法见 [module-14 §4.4](./2026-09-20-module-14-evaluation-feedback-plan.md)。上表 7 个方法的**签名与语义均不变**。

---

## 5. 业务流程设计

### 5.1 触发评估（PRD §5.3 ③ 第 1 步）

```
1. 校验面试存在与可见（interview.service.get_interview）
2. 若运行注册表中已有该面试的运行中任务
      → 幂等：直接返回既有 stream_url，不重复触发
3. 若状态为 'evaluating' 但注册表中无运行记录
      → 判定为孤儿评估（进程重启遗留）→ 调 transition_back_to_completed 自愈（§5.7）
4. 调 interview.service.transition_to_evaluating(db, interview_id)
      → 非 'completed' / 'evaluated' 时抛 BusinessError（409）
5. 在运行注册表中创建 EvaluationRun，以 asyncio 任务启动后台评估
6. 返回 202 + stream_url
```

### 5.2 评估编排（`service.evaluate_interview`，同步）

```
输入：interview_id、on_event 回调

阶段 0 · 取数
  1. qa_pairs = interview.service.get_answers_for_evaluation(db, interview_id)
  2. dims     = interview.service.get_evaluation_dimensions(db, interview_id)
  3. provider = ai.factory.get_provider()

阶段 1 · 逐题评分（PRD §4.5「对每一题的回答给出分数 + 评语」）
  for idx, pair in enumerate(qa_pairs, start=1):
      result = provider.evaluate_answer(pair.dimension, pair.question, pair.answer)
      on_event(EvaluationEvent("question", {...seq, index=idx, total=len(qa_pairs), score, comment...}))
  结果累积在内存列表 question_results

阶段 2 · 多维评分（PRD §4.5「按岗位评估维度逐项打分 + 评语」）
  results = provider.evaluate_dimensions(dims, qa_pairs)
  for idx, r in enumerate(results, start=1):
      on_event(EvaluationEvent("dimension", {...}))
  结果累积在内存列表 dimension_results

阶段 3 · 汇总（PRD §4.5「总分、综合结论、优点、待改进」）
  report = provider.summarize_report(dims, dimension_results, question_results)
  on_event(EvaluationEvent("report", {...}))

阶段 4 · 落库（单事务）
  repository.replace_question_scores(db, interview_id, question_results)
  repository.replace_dimension_scores(db, interview_id, dimension_results)
  repository.upsert_report(db, interview_id, report)
  repository.delete_candidate_feedback(db, interview_id)      ← MVP-2 新增（缓存失效）
  interview.service.transition_to_evaluated(db, interview_id)
  commit
```

> **（MVP-2）为何在这条事务里加一行删除**：候选人的反馈由报告派生（[module-14 §5.2](./2026-09-20-module-14-evaluation-feedback-plan.md) 采用懒生成 + 落库缓存）。重新评估会整体替换报告，**若不删缓存，候选人会看到上一轮的反馈**。放在同一事务里是必须的——开第二个事务会留下「报告已换、反馈还是旧的」的窗口；同生共死则要么都生效、要么都回滚。
>
> 该操作是**本地 DB 删除、不调 AI**，因此不违反 PRD §7「AI 失败不阻塞其他功能」。评估失败时**不删除**（报告未变，缓存仍然有效）。

**异常传播**：任一阶段抛出的 `AIProviderError` 或其它异常向外传播，由 `stream.py` 的运行器捕获并执行 §5.4 的失败处理。

### 5.3 「先推后写」的设计决策（**对 PRD §7 的修正**）

PRD §7 描述为「评估任务后台执行，SSE 边推边写库」。本设计**不采用边推边写**，改为**三阶段进度实时推送 + 结果在最后一次性落库**。

| 方案 | 问题 |
|---|---|
| 边推边写库 | ① 失败时会留下**部分新结果与部分旧结果混杂**的数据；② 若先清空旧结果再逐步写入，失败时会让用户**丢失之前那份完好的报告**；③ 重新评估场景下问题最突出 |
| **先推后写（本设计采用）** | 数据库要么是「上一次的完整结果」，要么是「这一次的完整结果」，**永不存在混合态**；失败不损失任何既有数据 |

**这与 PRD §7 的要求是否冲突**：不冲突，且更严格。PRD §7 要求「失败则评估任务标记失败、状态回退 `completed`，可重新触发」——**先推后写正是让「回退」变得干净的前提**：回退后数据库里仍是上一次的完整结果或空，而不是半成品。

**代价与应对**

| 代价 | 应对 |
|---|---|
| 评估进行中时，数据库中尚无可读结果 | 报告接口要求状态为 `evaluated`，此期间本来就不应可读（§4.4） |
| 进程重启会丢失进行中的进度 | 状态为 `evaluating` 但无运行记录时自动自愈回 `completed`（§5.7），用户重新触发即可 |
| 前端断线重连时需重放已推事件 | 运行注册表保存已推事件的完整历史，重连时先重放（§5.5）——**满足 PRD §7「前端重连后可继续拉取进度」** |

### 5.4 结果替换、重新评估与失败回退

| 场景 | 行为 |
|---|---|
| 首次评估 | 三张表原本为空，直接写入 |
| **重新评估**（`evaluated` → `evaluating`） | 阶段 4 的 `replace_*` **先删后插**，旧的逐题分、维度分被整体替换，`report` 被 upsert 更新（`updated_at` 变化） |
| **评估中途失败** | 阶段 4 之前就抛错，**数据库未做任何修改**，上一次结果完整保留；随后执行 §5.4.1 的失败处理 |
| 阶段 4 自身失败（如 DB 异常） | 事务回滚，数据库回到评估前状态 |

#### 5.4.1 失败处理（**PRD §7 的落地**）

```
catch 任何异常 as e:
    1. 不落库（或回滚事务）
    2. interview.service.transition_back_to_completed(db, interview_id)   ← PRD §7「状态回退 completed」
    3. 推 error 事件（code / message）
    4. run.status = 'failed'
    5. 记录完整堆栈到服务端日志
```

**PRD §7 的四个要求逐条对应**

| PRD §7 原文 | 落地方式 |
|---|---|
| 「重试 1 次」 | 由 `ai` 模块内部完成（ai §5.4，`AI_MAX_RETRIES=1`） |
| 「评估任务标记失败」 | `run.status = 'failed'`（§5.5） |
| 「状态回退 `completed`」 | `transition_back_to_completed`（§5.4.1 第 2 步） |
| 「可重新触发」 | 状态回到 `completed` 后即可再次 `POST /evaluate`（§5.1） |
| 「不阻塞其他功能」 | 失败影响面限于该次评估；其它面试的评估与所有 CRUD 不受影响 |

**不做版本留存**：同一面试只保留最近一次评估结果。理由：MVP 无「对比两次评估」的需求（PRD §1.3 已将「多候选人横向对比」列为非目标），留存版本会引入版本选择 UI 与额外的查询条件（YAGNI）。

### 5.5 运行注册表与重连重放（`stream.py`，**PRD §7 的落地**）

**`EvaluationRun` 数据结构**

| 字段 | 类型 | 说明 |
|---|---|---|
| `interview_id` | int | — |
| `status` | str | `running` \| `done` \| `failed` |
| `events` | list[EvaluationEvent] | **已推送事件的完整历史**，供重连重放 |
| `subscribers` | list[Queue] | 当前订阅者的队列 |
| `started_at` | datetime | 用于孤儿判定（§5.7） |
| `task` | asyncio.Task | 后台任务句柄 |

**注册表操作**

| 操作 | 说明 |
|---|---|
| `create_run(interview_id) -> EvaluationRun` | 创建并登记 |
| `get_run(interview_id) -> EvaluationRun \| None` | — |
| `remove_run(interview_id) -> None` | 完成后延时移除（保留短暂窗口以便重连重放） |
| `publish(run, event)` | 追加到 `events`，并向所有订阅者队列投递 |

**SSE 连接生命周期**

```
1. 校验面试存在与可见
2. run = get_run(interview_id)
3. 若 run 为 None：
      - 状态为 evaluated → 从数据库**合成**一轮完整事件（逐题分→维度分→报告→done）推送后关闭
      - 状态非 evaluated → 推送 error 事件后关闭
4. 若 run 存在：
      a. 先重放 run.events 中已产生的事件        ← PRD §7「重连后可继续拉取进度」
      b. 若 run.status 已是 done/failed → 推送终结事件后关闭
      c. 否则订阅队列，持续转发新事件
5. 订阅期间每 15 秒推送一次 ping 心跳
6. 客户端断开 → 从 subscribers 移除该队列；**后台任务继续运行**
```

**关键性质**（PRD §7「SSE 断连：评估任务后台继续」）

| 性质 | 说明 |
|---|---|
| 断线**不影响**后台评估任务 | 订阅者只是旁观者；后台任务独立运行至完成 |
| 重连可拿到**完整历史** | `run.events` 保存全部已推事件，重连从头重放，界面状态可完整重建 |
| **评估完成后**重连仍可用 | 若注册表已清理，则从数据库**合成**事件序列（第 3 步）——即 PRD §7 的「**或查询最终结果**」 |

### 5.6 部署限制声明（**重要**）

**MVP 采用进程内运行注册表，要求后端以单进程（单 worker）方式运行。**

| 项 | 说明 |
|---|---|
| 为何 | 运行注册表是进程内的内存结构；多 worker 下 `POST /evaluate` 可能落在 worker A，而 `GET /stream` 落在 worker B，B 看不到 A 的注册表 |
| 多 worker 下的表现 | SSE 连接会走到 §5.5 第 3 步（run 为 None），若有 `evaluated` 结果则能合成推送，否则报错 |
| 缓解 | 启动脚本固定 `--workers 1`；README 中明确说明 |
| 未来方案 | 引入 Redis pub/sub 或 Celery + 结果后端；不在 MVP 范围 |

### 5.7 孤儿评估自愈

**问题**：评估进行中时进程重启，面试状态永久停留在 `evaluating`——用户既无法重新触发（状态机不允许 `evaluating → evaluating`），也无法读取报告（状态非 `evaluated`）。**PRD 未覆盖该场景**。

**方案**：在 `POST /evaluate` 与 `GET /stream` 的入口处判定：

```
若 interview.status == 'evaluating'
   且 运行注册表中无对应 run
   → 视为孤儿评估
   → 调 interview.service.transition_back_to_completed(db, interview_id)
   → 继续按 'completed' 状态处理
```

**判定依据**：进程内的运行注册表是「评估是否真的在跑」的**唯一事实来源**。注册表里没有，就说明那个任务随着进程消失了。

### 5.8 报告读取

```
1. 校验面试存在与可见
2. 若 status != 'evaluated' → BusinessError(409)「评估尚未完成」
3. 读 report / dimension_scores / question_scores
4. 联 interview 的供给接口补齐 question_scores 的 seq / content / dimension / answer
5. 组装 ReportDetail 返回
```

> **（MVP-2）候选人反馈的读取是一条独立路径，不在本节**：它**不读** `question_score` / `dimension_score`，可见性判据也不同（经 `interview.service.get_interview_for_candidate` 而非 `created_by`）。完整流程见 [module-14 §5.1](./2026-09-20-module-14-evaluation-feedback-plan.md)。本节 5 步**一行不改**——这是 PRD §4.9「HR 端报告视图保持不变」在读取路径上的落实。

---

## 6. 错误处理（对应 PRD §7）

### 6.1 HTTP 错误

| 场景 | code | HTTP | message |
|---|---|---|---|
| 未带 / 无效 token | `UNAUTHORIZED` / `INVALID_TOKEN` | 401 | — |
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在 |
| 访问他人面试 | `FORBIDDEN` | 403 | 无权限访问该面试 |
| 面试状态不允许触发评估 | `BUSINESS_ERROR` | 409 | 当前状态不可开始评估（`detail` 含 from/to） |
| 报告尚未生成（状态非 `evaluated`） | `BUSINESS_ERROR` | 409 | 评估尚未完成 |
| 评估已在进行中 | — | **202** | **不报错**，幂等返回既有 `stream_url` |

### 6.2 评估执行中的失败（推 `error` 事件）

| 失败点 | 处理 |
|---|---|
| AI 调用失败（`AIProviderError`） | 不落库；调 `transition_back_to_completed`；推 `error` 事件（`code=AI_PROVIDER_ERROR`）；run 状态置 `failed` |
| 阶段 4 落库异常 | 事务回滚；调 `transition_back_to_completed`；推 `error` 事件（`code=INTERNAL_ERROR`） |
| 状态迁移失败（如并发修改） | 推 `error` 事件；run 状态置 `failed` |
| 任何未预期异常 | 同上，日志记录完整堆栈，**对外只给通用文案** |

**统一保证**：失败后面试状态**必回到 `completed`**，用户可立即重新触发（PRD §7）；数据库不残留本次评估的任何写入。

### 6.3 部分成功的情形

`evaluate_dimensions` 可能返回少于 `dims` 的条目（真实 Provider 的容错行为，见 ai §5.3）。处理：**按实际返回写入**，不补齐、不报错。报告中的雷达图按实际维度数渲染。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `backend/tests/test_evaluation.py`（service 层，**同步、无 SSE**）

> 直接调用 `evaluate_interview`，传入一个记录事件的间谍回调。**不涉及异步、不涉及 HTTP、不涉及 SSE**——这是 §2 切分设计带来的收益。

| 测试 | 断言 |
|---|---|
| `test_evaluate_writes_question_scores` | 8 道题 → 落库 8 条 `question_score` |
| `test_evaluate_writes_dimension_scores` | 落库条目数等于岗位维度数 |
| `test_evaluate_writes_report` | `report` 一行，**四字段齐全**（PRD §4.5） |
| `test_overall_score_in_range` | `0.0 <= overall_score <= 10.0`（PRD §4.5） |
| `test_all_scores_in_range` | 逐题分、维度分、总分**均**落在 [0, 10]（PRD §4.5） |
| `test_scores_have_one_decimal` | 逐题分、维度分均保留 1 位小数 |
| `test_events_order` | 事件序列为 8×`question` → N×`dimension` → 1×`report`（PRD §5.3 ③） |
| `test_question_events_ordered_by_seq` | `question` 事件的 `seq` 严格递增 |
| `test_event_payload_fields` | 每类事件载荷字段完整（§4.3） |
| `test_status_becomes_evaluated` | 结束后状态为 `evaluated`（PRD §5.3 ③ 第 3 步） |
| `test_evaluate_from_completed_ok` | `completed` 状态可触发 |
| `test_evaluate_from_ongoing_rejected` | `ongoing` → 409 |
| `test_reevaluate_replaces_scores` | 重新评估后 `question_score` 条数**不翻倍**（替换而非追加） |
| `test_reevaluate_updates_report_updated_at` | `updated_at` 变化 |
| `test_ai_failure_leaves_db_unchanged` | 注入抛 `AIProviderError` 的 provider → 抛异常，且三张表**无任何新增行** |
| `test_ai_failure_preserves_previous_report` | 先成功评估一次，再注入失败重评 → **旧的逐题分/维度分/报告完好无损** |
| `test_dimension_scores_fewer_than_dims_ok` | provider 返回少于维度数 → 按实际写入，不报错 |

### 7.2 `backend/tests/test_evaluation_stream.py`（SSE 层）

| 测试 | 断言 |
|---|---|
| `test_stream_events_sequence` | 依次收到 `question` … `dimension` … `report` … `done`（PRD §5.3 ③） |
| `test_stream_ends_with_done` | 最后一个事件为 `done`，`status == "evaluated"` |
| `test_stream_content_type` | 响应头 `Content-Type` 为 `text/event-stream` |
| `test_stream_requires_auth` | 无 `Authorization` → 401（PRD §8） |
| `test_stream_other_users_interview_forbidden` | 403 |
| `test_stream_nonexistent_interview` | 404 |
| `test_reconnect_replays_events` | 断开后重连 → 收到**已推事件的历史**（从头重放）——PRD §7 |
| `test_reconnect_after_done_gets_full_replay` | 完成后重连 → 仍能收到完整事件序列并以 `done` 结束 |
| `test_stream_after_evaluated_synthesizes_from_db` | 注册表已清理但状态为 `evaluated` → 从库中**合成**完整事件序列（PRD §7「或查询最终结果」） |
| `test_stream_when_not_evaluated_pushes_error` | 状态为 `ongoing` → 推 `error` 事件后关闭 |
| `test_ai_failure_pushes_error_event` | 注入失败的 provider → 收到 `error` 事件 |
| `test_ai_failure_rolls_back_status_to_completed` | 失败后状态回到 **`completed`**（PRD §7） |
| `test_ai_failure_does_not_leave_stuck_evaluating` | 失败后状态**不是** `evaluating` |
| `test_evaluate_idempotent_when_running` | 运行中再次 POST → 202，返回同一 `stream_url`，且**不产生第二组事件** |
| `test_disconnect_does_not_stop_task` | 断开连接后，后台任务仍跑到完成；随后 `GET /report` 可读到结果（PRD §7） |
| `test_orphan_evaluation_self_heals` | 手工把状态置为 `evaluating` 但清空注册表 → POST `/evaluate` 能成功触发（**状态先自愈到 `completed`**） |

### 7.3 报告接口

| 测试 | 断言 |
|---|---|
| `test_report_ok` | 200，含 `overall_score` / `conclusion` / `strengths` / `weaknesses`（PRD §4.5） |
| `test_report_includes_all_dimensions` | `dimension_scores` 覆盖岗位全部维度（**供雷达图**，PRD §4.5） |
| `test_report_includes_question_details` | `question_scores` 含 `seq` / `content` / `dimension` / `answer` / `score` / `comment` |
| `test_report_question_scores_ordered_by_seq` | 按 `seq` 升序 |
| `test_report_all_scores_in_range` | 所有分数落在 [0, 10]（PRD §4.5） |
| `test_report_before_evaluation_returns_409` | 状态为 `completed` → 409 |
| `test_report_when_ongoing_returns_409` | 409 |
| `test_report_other_users_interview_forbidden` | 403 |
| `test_report_nonexistent_interview` | 404 |
| `test_report_uses_snapshot_content` | **修改题库题目后，报告中的 `content` 仍是出题时的快照** |
| **`test_report_rejects_candidate`**（MVP-2） | 候选人 token 对三个 HR 端点 → **一律 403** |
| **`test_report_rejects_anonymous`**（MVP-2） | 无 token → 401 |
| **`test_report_unchanged_by_candidate_feedback`**（MVP-2） | `candidate_feedback` 表有数据时，`GET /report` 的响应字段与 MVP-1 **完全一致**，**不出现任何候选人字段** |

> MVP-2 的越权矩阵以**表驱动**形式集中实现于 `backend/tests/test_permissions.py`（[module-16 §7.1](./2026-09-20-module-16-permission-guard-plan.md)）。候选人反馈的脱敏、缓存、失效等测试**不在本模块重复编写**，见 [module-14 §7](./2026-09-20-module-14-evaluation-feedback-plan.md)——但上表第三条（HR 报告零污染）必须留在本模块，它是「HR 视图不变」这条 PRD 要求的直接断言。

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

> **（MVP-2）Task 6.x 为 MVP-1 已完成的任务清单，保持不变。** MVP-2 的增量任务（`candidate_feedback` 建表、白名单 schema、懒生成与缓存、落库事务内删除缓存、配置项等共 8 个 Task）见 [module-14 §8](./2026-09-20-module-14-evaluation-feedback-plan.md)。**唯一需要改动既有代码的是 Task 14.6**：在 §5.2 阶段 4 的落库清单中插入 `delete_candidate_feedback`。

### Task 6.1：三张模型与迁移

- [ ] 定义 `QuestionScore`、`DimensionScore`、`Report`（§3 全字段）
- [ ] 建立外键（全部 CASCADE）与唯一约束
- [ ] 生成迁移、`alembic upgrade head`、验证约束
- [ ] 提交

### Task 6.2：schema 与事件结构

- [ ] 定义 `EvaluationEvent`、`DimensionScoreItem`、`QuestionScoreItem`、`ReportDetail`、`EvaluateTriggerResponse`
- [ ] 写失败测试：`ReportDetail` 字段完整性（对齐 PRD §4.5 的四项输出）
- [ ] 运行确认失败 → 实现 → 通过
- [ ] 提交

### Task 6.3：repository 层

- [ ] 写失败测试：`replace_*` 二次调用后**行数不变**（替换语义）；`upsert_report` 二次调用更新而非新增
- [ ] 运行确认失败
- [ ] 实现 §4.5 全部方法
- [ ] 运行确认通过
- [ ] 提交

### Task 6.4：评估编排（service，同步）

- [ ] 写 §7.1 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `evaluate_interview`：三阶段 + `on_event` 回调 + **阶段 4 单事务落库** + 状态迁移
- [ ] 运行确认通过
- [ ] 提交

### Task 6.5：报告组装与读取

- [ ] 写 §7.3 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `get_report`（含**状态守卫**与快照内容补齐）与 `GET /report` 端点
- [ ] 在 `main.py` 注册 router
- [ ] 运行确认通过
- [ ] 提交

### Task 6.6：运行注册表与事件队列

- [ ] 定义 `EvaluationRun` 与注册表操作（§5.5）
- [ ] 实现 `publish` 与订阅者投递
- [ ] 写失败测试：同一 run 的多个订阅者都能收到同一事件；`events` 历史完整累积
- [ ] 运行确认通过
- [ ] 提交

### Task 6.7：SSE 事件流

- [ ] 实现 SSE 响应生成（响应头、事件格式化、**15 秒 ping 心跳**）
- [ ] 实现 §5.5 的连接生命周期（重放 → 订阅 → 终结 → 从库合成）
- [ ] 写 §7.2 中流式相关的失败测试
- [ ] 运行确认通过
- [ ] 提交

### Task 6.8：触发端点与孤儿自愈

- [ ] 实现 `POST /evaluate`（**幂等**、`transition_to_evaluating`、启动后台任务、返回 202）
- [ ] 实现 §5.7 的孤儿评估自愈
- [ ] 写 §7.2 中触发与自愈相关的失败测试
- [ ] 运行确认通过
- [ ] 提交

### Task 6.9：失败处理与状态回退

- [ ] 实现后台运行器的异常捕获：**不落库** + `transition_back_to_completed` + 推 `error` 事件（§5.4.1，**PRD §7**）
- [ ] 写失败测试：AI 失败后状态回到 `completed`、数据库无残留、收到 `error` 事件
- [ ] 运行确认通过
- [ ] 提交

### Task 6.10：全量回归

- [ ] 运行 evaluation 全部测试
- [ ] 运行 core / auth / position / question / ai / interview 测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] `POST /evaluate` 返回 **202** 与 `stream_url`；重复触发**幂等**（202 + 同一 URL，不产生第二组事件）
- [ ] SSE 事件顺序为 `question`（按 `seq` 升序）→ `dimension` → `report` → `done`（PRD §5.3 ③）
- [ ] `done` 与 `error` **互斥且必居其一**
- [ ] SSE 响应头含 `text/event-stream`，且每 15 秒有 ping 心跳
- [ ] SSE 需要 `Authorization` 头鉴权（PRD §8），可用 `fetch` + `ReadableStream` 正常消费
- [ ] **断线重连可收到已推事件的完整重放**；评估完成后重连仍可收到完整序列（PRD §7）
- [ ] **断开连接不影响后台评估任务继续进行**（PRD §7）
- [ ] 评估结束后 `GET /report` 返回逐题分 + 维度分 + 汇总，维度覆盖岗位全部维度（PRD §4.5）
- [ ] 非 `evaluated` 状态下 `GET /report` 返回 409
- [ ] 逐题分、维度分、总分**均为 0–10** 且保留 1 位小数（PRD §4.5）
- [ ] 重新评估为**替换**语义：`question_score` 行数不翻倍，`report.updated_at` 更新
- [ ] **AI 失败时**：三张表无任何新增行，上一次的完整结果**完好保留**，状态回到 `completed`，客户端收到 `error` 事件（PRD §7）
- [ ] `evaluating` 状态的面试在进程重启后可自愈（`POST /evaluate` 与 `GET /stream` 均不卡死）
- [ ] 报告中的 `content` / `dimension` 取自**出题快照**，修改题库后不变
- [ ] 全部 evaluation 测试通过
- [ ] **（MVP-2）** `candidate_feedback` 表建成；**`question_score` / `dimension_score` / `report` 三张表结构未改动**
- [ ] **（MVP-2）** `GET /interviews/{id}/report` 响应字段与 MVP-1 完全一致，且**不含任何候选人反馈字段**
- [ ] **（MVP-2）** 重新评估后候选人反馈缓存被删除（同一事务内）
- [ ] **（MVP-2）** 三个 HR 端点对候选人 token 一律 403
- [ ] **（MVP-2）** 候选人侧验收见 [module-14 §9](./2026-09-20-module-14-evaluation-feedback-plan.md)

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| 是否「边推边写库」 | **先推后写**，最后一次性落库 | 避免失败时新旧结果混杂；避免丢失上一次完好的报告；**且让 PRD §7 的「状态回退」语义干净** |
| 重新评估是否留存历史版本 | **不留存**，只保留最近一次 | MVP 无版本对比需求（PRD §1.3 已将「多候选人横向对比」列为非目标）；留存会引入版本选择 UI 与额外查询条件 |
| 后台任务用进程内注册表 | 采用（**单进程部署**） | MVP 无分布式诉求；引入 Redis/Celery 属过度设计。**已明确声明单 worker 限制** |
| 进程重启导致卡在 `evaluating` | **孤儿评估自愈** | PRD 未覆盖该场景；注册表是「是否真的在跑」的唯一事实来源 |
| SSE 客户端能否用 `EventSource` | **不能，须用 fetch + ReadableStream** | `EventSource` 无法设置 `Authorization` 头；把 JWT 放 query string 会泄露到日志与历史 |
| 断线重连如何续上进度 | 运行注册表保存事件历史并重放 | 实现简单、语义明确，**直接满足 PRD §7 的「重连后可继续拉取进度」**；代价是内存中临时保留事件列表（评估规模小，可接受） |
| `question_score` 是否冗余 `interview_id` | **冗余** | 「清空某面试全部评分」与「按面试查询」是最高频操作，冗余列免去联表；写入来源单一，无不一致风险 |
| `score` 用 DECIMAL 还是 FLOAT | **`DECIMAL(3,1)`** | 定点类型避免浮点误差影响平均值计算 |
| 维度分数量少于岗位维度数 | 按实际写入，不补齐不报错 | 真实 Provider 的容错行为（ai §5.3）；强行补齐会伪造数据 |
| 评估期间面试数据是否可改 | **不可**（interview §5.4.3 全锁） | 避免评估读到一半数据被修改导致报告不自洽 |
| **（MVP-2）候选人反馈与报告是否共用一张表** | **不共用**，新增 `candidate_feedback` | 两者受众与可见性规则不同。分开后 HR 报告接口**结构上读不到**候选人字段，直接满足 PRD §4.9「HR 端报告视图保持不变」 |
| **（MVP-2）候选人反馈何时生成** | **懒生成 + 落库缓存**（module-14 §5.2） | 塞进评估事务会：拖累评估成功率、违反 PRD §7「AI 失败不阻塞其他功能」、无人看时白花一次 AI 调用 |
| **（MVP-2）重评后旧反馈怎么办** | 在本次落库的**同一事务**内删除（§5.2 阶段 4） | 不删则候选人看到上一轮的反馈；同事务保证与报告替换同生共死 |
| **（MVP-2）HR 是否能看到候选人反馈的措辞** | **不提供**（不在端点范围内） | PRD 未要求。若将来需要，应作为 HR 端点单独评审，而不是复用候选人端点 |
