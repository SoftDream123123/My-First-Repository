# evaluation 模块执行计划书（MVP-2 候选人脱敏反馈）

> **文档状态**：⚠️ **待编写** —— 编号与文件名已预留，本轮（2026-09-20）**未产出内容**。
> 本文档不是可执行的计划书，请勿据此实施。已完成的部分见文末「已由其他文档固定的契约」。

**模块**：evaluation（候选人可见的脱敏反馈视图）
**所属包**：`backend/app/evaluation/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.5（面向候选人的反馈视图）、§4.9（面试结果与反馈）、§8（`GET /candidate/interviews/{id}/feedback`）、§9（候选人可见性为强制项）

---

## 待编写的章节（沿用 module-00～16 的统一模板）

1. 模块职责与边界（HR 报告视图**不变**；反馈视图是**新增的第二条读取路径**）
2. 文件结构（含需修改的上游文件：`evaluation/router.py` 增加候选人端点、`core/config.py` 增加档位配置）
3. 数据模型设计（**是否新增表？** 待定：可复用 `report`，也可能需要缓存脱敏文本——本文件需给出决策与理由）
4. 接口契约：`GET /candidate/interviews/{id}/feedback` 的请求/响应结构；service 与 repository 签名
5. 业务流程：评估完成后生成/读取候选人反馈；`summary` 与 `full` 两档的差异
6. 错误处理（未评估 → 什么状态码？不属于本人 → 403；AI 生成失败 → 502 且不影响 HR 侧报告）
7. 测试设计（**脱敏断言：响应中不得出现逐题分、维度分、雷达图数据**；两档对比；越权）
8. 任务分解（TDD 步骤，无代码）
9. 验收标准
10. 风险与设计权衡

---

## 已由其他文档固定的契约（编写本文件时**必须遵守，不得另立**）

| 契约 | 出处 |
|---|---|
| 默认档位 `summary`：**仅**下发综合结论、优点、待改进；**不下发**总分、逐题分、维度分、雷达图 | PRD §4.9 |
| `full` 档位额外含总分；**逐题分、维度分与雷达图在任何档位下都不下发给候选人** | PRD §4.9、§1.3；[module-08 §3.7](./2026-09-15-module-08-e2e-plan.md) |
| 档位由配置项 `CANDIDATE_FEEDBACK_LEVEL` 控制（`summary` 默认 / `full`） | PRD §4.9 |
| 生成反馈调用 `ai.generate_candidate_feedback(level, conclusion, strengths, weaknesses, overall_score)`；**只传原始值** | [module-11 §3.2、§5.2](./2026-09-20-module-11-ai-plan.md) |
| `level='summary'` 时 provider 返回的 `overall_score` 为 `None`；未知 level 退化为 `summary` 并记 warning | [module-11 §4.3](./2026-09-20-module-11-ai-plan.md) |
| 候选人只能看**自己已接受的邀请所对应面试**的反馈；守卫 `require_roles("candidate")` | [module-12（待编写）§5](./2026-09-20-module-12-interview-invitation-plan.md)；[module-16 §3.1](./2026-09-20-module-16-permission-guard-plan.md) |
| HR 侧报告视图与 `GET /interviews/{id}/report` **完全不变** | PRD §4.9；[module-06 §4.1](./2026-09-15-module-06-evaluation-plan.md) |
| 反馈生成失败**不影响** HR 侧报告；不得阻塞评估流程 | PRD §7；[module-11 §5.5](./2026-09-20-module-11-ai-plan.md) |
| 候选人可见性（脱敏）是 PRD §9 的**强制项**，不是可选项 | PRD §9 |

**依赖本文件的模块**：[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)；E2E 走查清单见 [module-08 §4.5 流程④ 第 7～8 步](./2026-09-15-module-08-e2e-plan.md)。
