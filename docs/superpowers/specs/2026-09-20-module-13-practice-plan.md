# practice 模块执行计划书（MVP-2 刷题练习）

> **文档状态**：⚠️ **待编写** —— 编号与文件名已预留，本轮（2026-09-20）**未产出内容**。
> 本文档不是可执行的计划书，请勿据此实施。已完成的部分见文末「已由其他文档固定的契约」。

**模块**：practice（练习会话、逐题判分、错题本、练习统计）—— **MVP-2 新增的第八个 package**
**所属包**：`backend/app/practice/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.7（刷题练习）、§5.3 ⑤（流程）、§5.2（`practice_session`、`practice_item`）、§7（判分失败降级）、§8（practice 端点）

---

## 待编写的章节（沿用 module-00～16 的统一模板）

1. 模块职责与边界（**不依赖 `interview`**；不做收藏、笔记、排行榜、编程判题）
2. 文件结构（含需修改的上游文件：迁移、`script.sql`、**`tests/test_architecture.py`**）
3. 数据模型设计：`practice_session`、`practice_item`（含三个题目快照字段）
4. 接口契约：七个端点、service 与 repository 签名、`PracticeQuestionOut` 的使用方式
5. 业务流程：开始会话（生成待答项）→ 逐题提交与判分 → 结束出小结 → 错题本 / 统计派生
6. 错误处理（判分失败降级、重复提交幂等、进程内限流超限）
7. 测试设计（判分分支、错题本与统计派生、候选人隔离、限流）
8. 任务分解（TDD 步骤，无代码）
9. 验收标准
10. 风险与设计权衡

---

## 已由其他文档固定的契约（编写本文件时**必须遵守，不得另立**）

| 契约 | 出处 |
|---|---|
| 取题调用 `question.service.list_practice_questions(db, filters, limit)`；**不按 `created_by` 过滤**（有意放宽），按 `id` 升序，`limit` 必须有上限（建议 20） | [module-10 §5.5、§4.4](./2026-09-20-module-10-question-plan.md) |
| 取题与展示用 `PracticeQuestionOut`：**不含** `reference_answer` / `explanation` / `source` / `created_by` / `created_at`；**必须含** `options` | [module-10 §4.2](./2026-09-20-module-10-question-plan.md) |
| **单选题由 practice 本地规则判分**（strip 后与 `reference_answer` 精确比较，**不消耗 AI**）；简答题调 `ai.grade_practice_answer` | PRD §4.7；[module-10 §5.4](./2026-09-20-module-10-question-plan.md) |
| 简答题无参考答案时**直接标记未判分**（`is_correct` 为空），**不调用 provider**（provider 对空参考答案抛 `AIProviderError`） | [module-11 §4.2](./2026-09-20-module-11-ai-plan.md) |
| 判分失败时 `practice_item` **正常落库**但 `is_correct` 为空，可后续重判（不作废作答） | PRD §7；[module-11 §5.5](./2026-09-20-module-11-ai-plan.md) |
| 判对/判错阈值**必须**用 `ai.base.PASS_THRESHOLD`（= 6.5），**不得另定义阈值** | [module-11 §3.3](./2026-09-20-module-11-ai-plan.md) |
| 会话开始时即生成待答项并写题目快照；逐题提交只回填 `user_answer` / `is_correct` / `score` / `explanation` / `answered_at` | PRD §5.2；[module-08 §7.2-16 相关说明](./2026-09-15-module-08-e2e-plan.md) |
| 错题本**不建表**，由 `practice_item.is_correct = false` 派生；未判分项**不入**错题本 | PRD §4.7 |
| 限流用**进程内计数**（单机约束），不引入 Redis；超限返回业务错误 | PRD §2、§7、§9 |
| 路由守卫 `require_roles("candidate")` | [module-16 §3.1](./2026-09-20-module-16-permission-guard-plan.md) |
| **必须**把 `practice` 登记进 `backend/tests/test_architecture.py` 的 `ALL_MODULES`、`LAYERED_MODULES`、`FORBIDDEN_DEPENDENCIES` | [module-08 §7.2-21](./2026-09-15-module-08-e2e-plan.md)；[module-16 §7.3](./2026-09-20-module-16-permission-guard-plan.md) |

**依赖本文件的模块**：[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)；E2E 走查清单见 [module-08 §4.5 流程⑤](./2026-09-15-module-08-e2e-plan.md)。
