# evaluation 模块执行计划书（MVP-2 候选人脱敏反馈）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：evaluation（候选人可见的脱敏反馈视图）
**所属包**：`backend/app/evaluation/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§1.3（非目标：候选人看不到逐题分与雷达图）、§4.5（面向候选人的反馈视图）、§4.9（面试结果与反馈）、§7（AI 失败不阻塞其他功能）、§8（`/candidate/interviews/{id}/feedback`）、§9（候选人可见性为**强制项**）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-06 evaluation MVP-1](./2026-09-15-module-06-evaluation-plan.md)、[module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md)、[module-11 ai 判分与反馈](./2026-09-20-module-11-ai-plan.md)、[module-12 interview 邀请](./2026-09-20-module-12-interview-invitation-plan.md)
**本模块被谁依赖**：[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)

> **与 module-06 的关系**：module-06 是 evaluation 模块的 MVP-1 计划书，仍然有效。本文档是**增量**，冲突时以本文档为准。

---

## Global Constraints（全局约束，摘自 PRD）

- **候选人可见性（脱敏）是强制项，不是可选项**（§9）
- 默认档位 `summary` **仅**下发：综合结论、优点、待改进（§4.9）
- 默认档位**不下发**：总分、逐题分、维度分、雷达图（§4.9）
- **逐题分、维度分与雷达图在任何档位下都不下发给候选人**（§1.3、§4.9）
- 档位由配置项 `CANDIDATE_FEEDBACK_LEVEL` 控制（`summary` 默认 / `full`）（§4.9）
- **HR 端报告视图保持不变**（§4.9）
- 反馈由 `ai.generate_candidate_feedback(level, ...)` 生成（§6）
- 反馈生成失败**不影响** HR 侧报告，也不阻塞评估（§7）
- 候选人只能查看**自己已接受的邀请所对应面试**的反馈（§4.6）
- 候选人侧路由守卫 `require_roles("candidate")`；**admin 与 hr 不通行**（§4.1）
- 统一响应格式 `{code, message, detail}`（§7）；**仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.5、§4.9）

| 子职责 | 内容 | PRD |
|---|---|---|
| 候选人反馈实体 | `candidate_feedback` 表的定义与迁移 | §4.5 |
| 反馈生成 | 由报告结论生成面向候选人的脱敏文案（懒生成 + 缓存） | §4.9 |
| 档位裁剪 | 按 `CANDIDATE_FEEDBACK_LEVEL` 决定响应是否含总分 | §4.9 |
| 反馈读取端点 | `GET /api/candidate/interviews/{id}/feedback` | §8 |
| 缓存失效 | 重新评估后使旧反馈失效 | §5.3 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **改动 HR 侧报告的任何行为** | PRD §4.9 明确「HR 端报告视图保持不变」。`GET /interviews/{id}/report`、SSE 流、三张评估表的读写**一律不动** |
| **候选人查看逐题分 / 维度分 / 雷达图** | PRD §1.3、§4.9 明确不下发。**注意**：这不是「前端不显示」，而是**后端不下发**（§4.2 的白名单响应结构） |
| **候选人反馈的编辑 / 审批流** | PRD 未要求。HR 若不同意反馈措辞，应通过重新评估来改变（反馈由报告派生） |
| **录用建议 / 通过与否的结论** | PRD §1.3 未要求；此类表述有合规风险，且属 HR 的判断，不应由系统代答 |
| **反馈的邮件 / 通知推送** | PRD §1.3 明确不做通知 |
| **候选人反馈的历史版本** | 重评即重建（§5.3）。保留多版本需要版本选择 UI（YAGNI，与 module-06 §5.4「不做版本留存」同一态度） |
| **在评估流程内同步生成反馈** | 会让评估的失败面变大（§5.2 的取舍） |

### 1.3 依赖方向

```
evaluation.router        ──→ evaluation.service ──→ evaluation.repository ──→ 四张表
evaluation.candidate_router ─┘
                                  │
                                  ├──→ interview.service.get_interview_for_candidate（候选人可见性）
                                  ├──→ ai.factory.get_provider()（generate_candidate_feedback）
                                  └──→ core.config（CANDIDATE_FEEDBACK_LEVEL）

evaluation ──→ core / auth / interview / ai（单向，与 MVP-1 一致）
evaluation ✗→ position / question（既有约束，module-06 §1.3）
evaluation ✗→ practice
```

> **候选人可见性复用 interview 的供给契约**：`get_interview_for_candidate`（[module-12 §4.5](./2026-09-20-module-12-interview-invitation-plan.md)）是候选人能否访问某面试的**唯一判据**。本模块不重复实现它——否则「邀请撤销后是否仍可看反馈」会出现两套答案。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/evaluation/models.py` | **改**：新增 `CandidateFeedback` 模型 |
| `backend/app/evaluation/schemas.py` | **改**：新增 `CandidateFeedbackOut`（白名单结构） |
| `backend/app/evaluation/repository.py` | **改**：`candidate_feedback` 的 CRUD |
| `backend/app/evaluation/service.py` | **改**：`get_candidate_feedback`（懒生成 + 档位裁剪） |
| `backend/app/evaluation/candidate_router.py` | **新增**：`/api/candidate/interviews/{id}/feedback`（守卫与 HR 端点不同，故分文件） |
| `backend/app/evaluation/stream.py` | **不改** |
| `backend/app/evaluation/router.py` | **不改**（HR 视图保持原样） |

**测试文件**：`backend/tests/test_candidate_feedback.py`（新增）

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 `candidate_router`（前缀 `/api`） |
| `backend/alembic/versions/` | 新增迁移：`candidate_feedback` 建表 |
| `backend/script.sql` | 同步建表语句 |
| `backend/app/core/config.py` | 新增 `candidate_feedback_level`（默认 `summary`，取值白名单校验） |
| `backend/.env.example` | 补 `CANDIDATE_FEEDBACK_LEVEL=summary` |
| **`backend/app/evaluation/service.py`** | **在评估落库的同一事务内**删除该面试的候选人反馈（§5.3） |

---

## 3. 数据模型设计

### 3.1 表 `candidate_feedback`（**PRD 未列出，本设计新增**）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `interview_id` | BIGINT | NOT NULL, FK → `interview.id` **CASCADE**, **UNIQUE** | 一次面试一份候选人反馈 |
| `conclusion` | TEXT | NOT NULL | 面向候选人的综合结论 |
| `strengths` | JSON | NOT NULL | 优点条目数组 |
| `weaknesses` | JSON | NOT NULL | 待改进条目数组 |
| `generated_at` | DATETIME | NOT NULL, DEFAULT NOW | 生成时刻 |

**索引**：`uq_candidate_feedback_interview`（`interview_id`，唯一）

**为何新增一张表而非在 `report` 上加列**

| 方案 | 评价 |
|---|---|
| 在 `report` 上加 `candidate_conclusion` 等三列 | 会把两份**受众不同、可见性规则不同**的文本混在一张表里。`report` 的任何读取路径（含 HR 报告接口）都可能不小心把候选人字段带出去 |
| **独立表（本设计采用）** | ① 可见性边界落在**表**这一层，HR 报告接口**结构上读不到**候选人字段；② `report` 的 schema 完全不动，直接满足 PRD §4.9「HR 端报告视图保持不变」 |

### 3.2 为何没有 `updated_at`

| 设计 | 理由 |
|---|---|
| 只有 `generated_at`，重评时**整行删除重建** | 反馈的输入是报告，报告重评即整体替换（module-06 §5.4 的「先删后插」）。反馈若支持「更新」就必须回答「哪一部分过期了」；整行重建把这个问题消掉 |

### 3.3 新增配置项

| 配置键 | 类型 | 默认 | 取值 | 说明 |
|---|---|---|---|---|
| `CANDIDATE_FEEDBACK_LEVEL` | str | `summary` | `summary` \| `full` | 候选人可见的反馈档位 |

**两层校验（必须都做，职责不同）**

| 层 | 行为 | 理由 |
|---|---|---|
| **启动期（`core/config.py`）** | 取值不在白名单 → **fail fast，拒绝启动** | 它是**部署配置**。写错了应该立刻发现，而不是静默降级后让运维以为配置生效了（与既有 `validate_provider_config` 同一态度，module-00 §8） |
| **Provider 层（`ai`）** | 收到未知 `level` → 按 `summary` 处理并记 warning（[module-11 §4.3](./2026-09-20-module-11-ai-plan.md)） | 纵深防御。调用方本不该传出非法值，但 provider 不该因调用方失误而泄露分数 |

---

## 4. 接口契约

### 4.1 对外 REST API

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| GET | `/api/candidate/interviews/{id}/feedback` | **新增**：候选人查看脱敏反馈 | **candidate** | 200 |

> **HR 侧三个端点完全不变**（`POST /interviews/{id}/evaluate`、`GET /interviews/{id}/evaluation/stream`、`GET /interviews/{id}/report`），其权限仍为 admin/hr（守卫补全见 [module-16 §3](./2026-09-20-module-16-permission-guard-plan.md)）。
>
> **端点路径归属 `/candidate` 前缀但由 evaluation 包提供**：路径表达的是「谁在访问」，包归属表达的是「数据属于谁」。这与 [module-12 §4.1](./2026-09-20-module-12-interview-invitation-plan.md) 的说明一致。

### 4.2 请求 / 响应结构

**`CandidateFeedbackOut`（白名单结构，**本模块最重要的安全设计**）**

| 字段 | 类型 | `summary` 档 | `full` 档 | 说明 |
|---|---|---|---|---|
| `interview_id` | int | ✓ | ✓ | — |
| `level` | str | ✓ | ✓ | 回显当前档位，便于前端与排查 |
| `conclusion` | str | ✓ | ✓ | 综合结论 |
| `strengths` | list[str] | ✓ | ✓ | 优点 |
| `weaknesses` | list[str] | ✓ | ✓ | 待改进 |
| `overall_score` | float \| null | **`null`** | ✓（0–10） | 总分 |
| `generated_at` | datetime | ✓ | ✓ | 生成时刻 |

**结构上不存在**的字段（不可下发，且**不在 schema 中定义**）：

| 不下发 | 依据 |
|---|---|
| `question_scores` / 逐题评语 | §1.3、§4.9 |
| `dimension_scores` / 维度评语 | §1.3、§4.9 |
| 雷达图数据 | §1.3、§4.9 |
| `created_by` / HR 侧任何字段 | §4.6 |

> **安全规则的落点是 schema，不是前端**：`CandidateFeedbackOut` 是 Pydantic 白名单模型，未定义的字段**不可能**出现在响应里。靠「前端不渲染」实现脱敏，等于把答案发给了浏览器再要求它别看——一个开发者工具就能看到。
>
> **这与 `PracticeQuestionOut` 剥离参考答案是同一手法**（[module-10 §4.2](./2026-09-20-module-10-question-plan.md)）：把安全边界放在序列化结构上，让它可被代码评审、可被测试断言、且不可能被前端疏忽绕过。

**请求参数**：无（档位来自服务端配置，**不接受客户端指定**——否则候选人可以传 `level=full` 拿到自己的分数）。

**错误**

| 场景 | code | HTTP | message |
|---|---|---|---|
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在 |
| 无 accepted 邀请 / 邀请已撤销 | `FORBIDDEN` | 403 | 无权限访问该面试 |
| 面试状态非 `evaluated` | `BUSINESS_ERROR` | 409 | 评估尚未完成 |
| 反馈生成时 AI 失败 | `AI_PROVIDER_ERROR` | 502 | AI 服务调用失败，请稍后重试 |

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `get_candidate_feedback(db, user: User, interview_id: int) -> CandidateFeedbackOut` | 反馈视图 | 可见性 → 状态检查 → 取缓存或生成 → 档位裁剪（§5.1） |

沿用（不改）：`evaluate_interview`、`get_report`、`list_question_scores`、`list_dimension_scores`。

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `get_candidate_feedback(db, interview_id: int) -> CandidateFeedback \| None` | 反馈或 `None` | 缓存读取 |
| `upsert_candidate_feedback(db, interview_id: int, data: dict) -> CandidateFeedback` | 反馈 | 懒生成后落库 |
| `delete_candidate_feedback(db, interview_id: int) -> None` | — | **缓存失效**（§5.3） |

### 4.5 对 `ai` 的调用点

| 调用 | 方法 | 说明 |
|---|---|---|
| 生成反馈 | `provider.generate_candidate_feedback(level, conclusion, strengths, weaknesses, overall_score)` | **只传原始值**；`level` 同时决定返回的 `overall_score` 是否为 `None`（[module-11 §4.3](./2026-09-20-module-11-ai-plan.md)） |

---

## 5. 业务流程设计

### 5.1 读取反馈（懒生成 + 缓存）

```
get_candidate_feedback(db, user, interview_id):
1. interview = interview.service.get_interview_for_candidate(db, user, interview_id)
       ← 404（不存在） / 403（无 accepted 邀请或已撤销）
2. 校验 interview.status == 'evaluated'
       否则 → BusinessError（409）「评估尚未完成」
3. 读缓存 repository.get_candidate_feedback(db, interview_id)
4. 缓存命中 → 跳到第 7 步
5. 缓存未命中 → 读取 report（repository.get_report）
       report 为 None → BusinessError（409）「评估尚未完成」
       ← 防御：状态为 evaluated 但报告缺失（理论不可达）
6. 调 provider.generate_candidate_feedback(level, report.conclusion,
                                          report.strengths, report.weaknesses,
                                          float(report.overall_score))
   失败 → AIProviderError（502），**不落库**，下次可重试
   成功 → repository.upsert_candidate_feedback(...) 落库
7. 组装 CandidateFeedbackOut：
       conclusion / strengths / weaknesses ← 落库的候选人文案
       overall_score ← **仅当 level == 'full'**，取 report.overall_score；否则 None
8. 返回（**不提交任何写操作，除非第 6 步刚生成**）
```

| 要点 | 说明 |
|---|---|
| **懒生成而非在评估流程内生成** | 见 §5.2 的取舍 |
| **第 7 步的总分从 `report` 读，而非存进反馈表** | 反馈表刻意不存总分：它属于「评估结果」，不属于「候选人文案」。存储层与可见性层解耦后，改变档位配置**不需要重新生成反馈** |
| 档位不影响缓存内容 | 缓存的是**中性文案**（不含总分）。因此 `summary` 与 `full` 共用同一份缓存，切换配置立即生效、无需失效 |
| 第 8 步「不提交」 | 只读路径不应产生写操作。缓存落库发生在第 6 步，由 service 显式 commit |

### 5.2 ⚠️ 为何是「懒生成」而非「评估落库时生成」（本模块的核心取舍）

| 方案 | 问题 |
|---|---|
| 在评估落库的阶段 4 里生成反馈 | ① 评估事务会多一次 AI 调用，**评估的成功率被第二个 AI 调用拖累**；② PRD §7 要求「AI 失败不阻塞其他功能」——把反馈塞进评估事务直接违反该要求；③ 无人查看反馈时白花一次 AI 调用 |
| **懒生成 + 落库缓存（本设计采用）** | ① 评估流程**完全不变**（满足 module-06 §5.2 的既有设计）；② 生成失败只影响「这一次读取」，不影响已完成的评估；③ 只在有人看时生成；④ 落库后同一次面试不再重复生成，**同一份反馈文案稳定**——候选人多次刷新看到的是同一份内容 |

| 懒生成的代价 | 应对 |
|---|---|
| 首次读取慢（一次 AI 调用） | 可接受：只在评估完成后首次查看时发生 |
| 缓存与报告可能不一致 | 重评时**删除**缓存（§5.3），下次读取重新生成 |
| 并发首次读取可能重复生成 | `interview_id` 唯一索引兜底：并发插入时后者捕获 `IntegrityError` 并读取前者写入的行（而不是报错） |

### 5.3 缓存失效（⚠️ 容易漏掉的一步）

重新评估会整体替换报告（module-06 §5.4 的 `replace_*` + `upsert_report`）。若缓存不失效，候选人会看到**上一轮**的反馈。

| 时机 | 动作 |
|---|---|
| 评估成功落库（module-06 §5.2 阶段 4 的同一事务） | `repository.delete_candidate_feedback(db, interview_id)` |
| 评估失败 | **不删除**：报告未被替换，缓存仍然有效（这也是懒生成的一个好处——失败不损失已有反馈） |

```
阶段 4 · 落库（单事务）—— module-06 §5.2 的清单新增一行
  repository.replace_question_scores(...)
  repository.replace_dimension_scores(...)
  repository.upsert_report(...)
  repository.delete_candidate_feedback(db, interview_id)      ← 新增
  interview.service.transition_to_evaluated(...)
  commit
```

| 要点 | 说明 |
|---|---|
| **在既有事务内删除，不额外开事务** | 与报告替换同生共死：要么都生效，要么都回滚。开第二个事务会留下「报告已换、反馈还是旧的」的窗口 |
| 删除是**本地 DB 操作**，不调 AI | 因此不会违反 PRD §7「AI 失败不阻塞其他功能」 |
| 删除后候选人访问 → 重新生成 | 候选人可能看到措辞略有不同的新反馈，但**内容与最新报告一致**——这是期望行为 |

### 5.4 与候选人在线答题的关系（`answer` 加列的影响）

| 项 | 影响 |
|---|---|
| `get_answers_for_evaluation` | **无影响**（module-12 §4.3 已确认签名与语义不变） |
| 候选人交卷时补写的空串作答 | 会被评估按 0 分处理（既有约定），进而影响报告与候选人反馈的措辞——这是**正确**的：未作答就是一件事实，反馈里提到它是合理的（framework 生成时由 AI 措辞把握） |
| 候选人是否可能提前看到反馈 | **不会**：第 2 步要求 `status == 'evaluated'`，而状态由 HR 触发评估推进 |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在（由 `get_interview_for_candidate` 抛出） |
| 无 accepted 邀请 / 邀请已撤销 | `FORBIDDEN` | 403 | 无权限访问该面试 |
| 评估尚未完成（含报告缺失） | `BUSINESS_ERROR` | 409 | 评估尚未完成 |
| 反馈生成 AI 失败 | `AI_PROVIDER_ERROR` | 502 | AI 服务调用失败，请稍后重试（**不落库，可重试**） |
| 并发首次生成撞唯一索引 | — | 200 | **不报错**：捕获 `IntegrityError` 后读取已写入的行返回（§5.2） |
| hr / admin 调用该端点 | `FORBIDDEN` | 403 | 无权限执行此操作（module-16） |
| 客户端传 `level` 参数 | — | 200 | **参数被忽略**：档位只来自服务端配置（§4.2） |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 脱敏（**本模块最重要的测试组**）

| 测试 | 断言 |
|---|---|
| `test_summary_response_keys_exactly_match_whitelist` | 响应的键集合**精确等于** `{interview_id, level, conclusion, strengths, weaknesses, overall_score, generated_at}` |
| `test_summary_has_no_overall_score` | `summary` 档 → `overall_score is None` |
| `test_response_never_contains_question_scores` | 响应体（原始 JSON 文本）中**不出现** `question_scores` / `score`（逐题）等键 |
| `test_response_never_contains_dimension_scores` | 同样不出现 `dimension_scores` / `dimensions` |
| `test_response_never_contains_radar_payload` | 不出现任何雷达图数据结构 |
| `test_full_has_overall_score_but_still_no_detail` | `full` 档 → `overall_score` 非空，**但逐题分与维度分仍然不出现** |
| `test_client_cannot_escalate_level` | 请求带 `?level=full` → 响应 `level` 仍为服务端配置值，`overall_score` 仍受配置决定 |

> **第一条与后三条的组合是刻意的**：只断言「`overall_score` 为 None」无法发现「逐题分被顺手带出去了」。键集合的**精确**比对（而非包含比对）才能拦住新增字段时的意外泄露。

### 7.2 可见性与状态

| 测试 | 断言 |
|---|---|
| `test_feedback_requires_accepted_invitation` | 未接受邀请 → 403 |
| `test_feedback_after_invitation_revoked_forbidden` | 接受后被撤销 → 403（复用 module-12 §5.1 的例外规则） |
| `test_feedback_other_candidates_interview_forbidden` | 候选人 A 访问 B 的面试反馈 → 403 |
| `test_feedback_before_evaluation_conflict` | 状态 `ongoing` / `completed` / `evaluating` → 409「评估尚未完成」 |
| `test_feedback_only_after_evaluated` | `evaluated` → 200 |
| `test_feedback_rejects_hr_and_admin` | hr / admin → 403（module-09 §4.5 的精确匹配） |
| `test_feedback_rejects_anonymous` | 无 token → 401 |

### 7.3 生成、缓存与失效

| 测试 | 断言 |
|---|---|
| `test_first_read_generates_and_caches` | 首次读取调用 provider **一次**，库中出现 `candidate_feedback` 行 |
| `test_second_read_uses_cache` | 二次读取**不再调用** provider（用 spy 断言），内容与首次一致 |
| `test_cache_content_is_level_independent` | `summary` 档生成后把配置改为 `full` → 再次读取**不重新生成**，仅 `overall_score` 变为非空 |
| `test_reevaluation_invalidates_cache` | 评估 → 读反馈（有缓存）→ 重新评估 → **缓存行被删除** |
| `test_feedback_after_reevaluation_is_regenerated` | 上述场景下再读 → 调用了 provider 且内容为本轮报告所生成 |
| `test_failed_evaluation_keeps_cache` | 评估失败（状态回退 `completed`）→ 缓存行**仍在**（报告未变，反馈仍有效） |
| `test_generation_failure_returns_502` | 注入失败的 provider → 502，**库中无反馈行** |
| `test_generation_failure_is_retryable` | 上述场景后恢复正常 provider → 再次读取 → 200 且落库 |
| `test_generation_does_not_break_hr_report` | 生成失败后再调 `GET /interviews/{id}/report` → **仍 200 且内容完整** |
| `test_concurrent_first_read_does_not_error` | 两次并发首次读取 → 都返回 200，库中**只有一行** |
| `test_ai_receives_raw_values` | spy 断言 provider 收到的是 str / list[str]，**不是 ORM 对象**（module-04 §3.4） |

### 7.4 HR 侧零回归（**必须验证**）

| 测试 | 断言 |
|---|---|
| `test_hr_report_unchanged` | `GET /interviews/{id}/report` 的响应字段与 MVP-1 完全一致（**不因新表而增减**） |
| `test_hr_report_never_contains_candidate_fields` | HR 报告响应中**不出现** `candidate_feedback` 相关键 |
| `test_evaluation_pipeline_unchanged` | `test_evaluation.py` 既有 29 条与 `test_evaluation_stream.py` 既有 34 条全部通过 |
| `test_reevaluation_still_works` | 重评流程（`replace_*` + `upsert_report`）行为不变，仅多一次缓存删除 |

### 7.5 配置校验

| 测试 | 断言 |
|---|---|
| `test_default_level_is_summary` | 不设环境变量 → `summary` |
| `test_invalid_level_fails_fast` | `CANDIDATE_FEEDBACK_LEVEL=detailed` → **启动期报错**（不在白名单） |
| `test_valid_levels_accepted` | `summary` / `full` 均可正常加载 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-11（`generate_candidate_feedback`）、module-12（`get_interview_for_candidate`）、module-16（守卫）已完成。

### Task 14.1：配置项与启动校验

- [ ] `core/config.py` 新增 `candidate_feedback_level`（默认 `summary` + 白名单校验）；`.env.example` 补键
- [ ] 写 §7.5 三条失败测试
- [ ] 运行确认通过
- [ ] 提交

### Task 14.2：模型与迁移

- [ ] `models.py` 新增 `CandidateFeedback`（§3.1 全字段 + 唯一索引）
- [ ] 生成迁移，同步 `backend/script.sql`
- [ ] 写失败测试：`interview_id` 唯一约束生效
- [ ] `alembic upgrade head` / `downgrade` 验证
- [ ] 提交

### Task 14.3：schema 白名单

- [ ] 定义 `CandidateFeedbackOut`（§4.2 的七个字段，**不含任何明细字段**）
- [ ] 写 §7.1 的键集合精确比对测试（此时因 service 未实现而失败）
- [ ] 提交

### Task 14.4：repository 层

- [ ] 实现 §4.4 三个方法
- [ ] 写失败测试：`delete_candidate_feedback` 对不存在的行不报错
- [ ] 运行确认通过
- [ ] 提交

### Task 14.5：读取与懒生成

- [ ] 写 §7.2 与 §7.3 中生成 / 缓存相关测试（**含「二次读取不调 provider」「并发不报错」**）
- [ ] 运行确认失败
- [ ] 实现 `service.get_candidate_feedback` 与 `candidate_router.py`，在 `main.py` 注册
- [ ] 运行确认通过
- [ ] 提交

### Task 14.6：缓存失效

- [ ] 写 §7.3 的 `test_reevaluation_invalidates_cache` 与 `test_failed_evaluation_keeps_cache`
- [ ] 运行确认失败
- [ ] 在 module-06 §5.2 阶段 4 的落库清单中插入 `delete_candidate_feedback`
- [ ] 运行确认通过
- [ ] 提交

### Task 14.7：脱敏与可见性收尾

- [ ] 写 §7.1 剩余测试（**含「客户端不能提权」与「full 档仍无明细」**）
- [ ] 写 §7.2 全部可见性测试
- [ ] 运行确认通过
- [ ] 提交

### Task 14.8：HR 侧零回归

- [ ] 写 §7.4 四条测试
- [ ] 运行 `pytest tests/ -q`，**全部通过**
- [ ] 提交

---

## 9. 验收标准

- [ ] `candidate_feedback` 表建成，`interview_id` 唯一；**`report` 表结构未改动**
- [ ] `GET /api/candidate/interviews/{id}/feedback` 对 `evaluated` 面试返回 200
- [ ] 响应键集合**精确等于**白名单七项；**任何档位**下都不含逐题分、维度分、雷达图数据
- [ ] `summary` 档 `overall_score` 为 `None`；`full` 档非空且仍无明细
- [ ] 档位**只来自服务端配置**，客户端传参被忽略
- [ ] 非法档位值导致**启动失败**（fail fast）
- [ ] 首次读取生成并落库；二次读取**不再调用 AI**
- [ ] 切换档位**不触发重新生成**（缓存与档位解耦）
- [ ] 重新评估后缓存**被删除**并在下次读取时重新生成；评估失败时缓存**保留**
- [ ] 生成失败返回 502 且**不落库**，可重试；且**不影响 HR 报告**
- [ ] 未接受邀请 / 邀请已撤销 / 他人面试 → 403；非 `evaluated` → 409
- [ ] hr 与 admin 调用该端点 → 403
- [ ] 对 `ai` 的调用**只传原始值**
- [ ] `GET /interviews/{id}/report` 行为与 MVP-1 **完全一致**
- [ ] 未新增任何错误码；`test_evaluation.py` 29 条与 `test_evaluation_stream.py` 34 条零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **脱敏靠前端还是后端** | 后端白名单 schema（`CandidateFeedbackOut`） | 靠前端「不渲染」等于把答案发给浏览器再要求它别看。白名单可被评审、可被测试断言，且结构上不可能绕过 |
| **反馈何时生成** | 懒生成 + 落库缓存（§5.2） | 塞进评估事务会：拖累评估成功率、违反 PRD §7「AI 失败不阻塞其他功能」、无人看时白花调用 |
| **重评后缓存必须失效** | 在既有落库事务内删除（§5.3） | 不删则候选人看到上一轮的反馈。放同一事务避免「报告已换、反馈还是旧的」窗口 |
| **总分不进反馈表** | 总分从 `report` 读取，按档位决定是否下发 | 存储层与可见性层解耦：改档位配置**不需要重新生成**反馈 |
| **新增独立表而非给 `report` 加列** | 独立表 | 让可见性边界落在表这一层；`report` schema 完全不动，直接满足 PRD §4.9 |
| 无 `updated_at`，重评整行重建 | 单字段 `generated_at` | 支持「更新」就必须回答「哪部分过期」，整行重建把问题消掉 |
| 生成失败返回 502（与刷题判分返回 200 不同） | 502 + 不落库 | 反馈是**读接口**：读不到就是读不到，报错并允许重试是正确的。刷题判分不同——那里作答已成功保存，报错会与事实不符（module-13 §5.3） |
| 档位校验放两层 | 启动期 fail fast + provider 层防御性降级 | 启动期拦住配置错误；provider 不该因调用方失误而泄露分数 |
| 并发首次读取 | 唯一索引 + 捕获 `IntegrityError` 后返回既有行 | 不报错，因为对候选人而言「拿到反馈」这一目标已达成 |
| HR 是否能看候选人反馈的措辞 | **不在端点范围内** | PRD 未要求；HR 需要的是报告，不是候选人版的措辞。若将来需要，应作为 HR 端点单独评审 |
| 反馈是否含「是否通过」的结论 | **不含** | 录用判断属 HR 职责，系统代答有合规风险（§1.2） |
