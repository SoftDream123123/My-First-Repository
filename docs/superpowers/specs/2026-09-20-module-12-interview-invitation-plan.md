# interview 模块执行计划书（MVP-2 作答邀请与在线答题）

> **文档状态**：⚠️ **待编写** —— 编号与文件名已预留，本轮（2026-09-20）**未产出内容**。
> 本文档不是可执行的计划书，请勿据此实施。已完成的部分见文末「已由其他文档固定的契约」。

**模块**：interview（作答邀请、候选人在线作答、候选人侧面试接口）
**所属包**：`backend/app/interview/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.4（作答邀请管理）、§4.8（在线答题）、§5.1（面试状态机不变 + 邀请状态机）、§5.2（`interview_invitation`、`answer` 扩展）、§8（candidate 与邀请端点）

---

## 待编写的章节（沿用 module-00～16 的统一模板）

1. 模块职责与边界（含「候选人隔离判据」的落点声明）
2. 文件结构（含需修改的上游文件：`answer` 与 `interview_invitation` 的迁移、`script.sql`）
3. 数据模型设计：`interview_invitation` 全字段与索引；`answer` 新增 `source` / `answered_by` / `submitted_at`
4. 接口契约：邀请三端点、candidate 六端点、service 与 repository 签名
5. 业务流程：邀请生命周期、激活绑定、逐题作答、交卷锁定、HR 覆盖
6. 错误处理（邀请失效不泄露面试是否存在、重复接受、改已交卷 → 冲突）
7. 测试设计（邀请状态机、交卷锁定与 HR 覆盖、候选人隔离与越权）
8. 任务分解（TDD 步骤，无代码）
9. 验收标准
10. 风险与设计权衡

---

## 已由其他文档固定的契约（编写本文件时**必须遵守，不得另立**）

| 契约 | 出处 |
|---|---|
| 面试状态机**五态不变**；候选人作答只是输入通道（`answer.source` / `answered_by` / `submitted_at` 表达） | PRD §5.1；[module-08 §6.4](./2026-09-15-module-08-e2e-plan.md) |
| 邀请状态机 `pending → accepted / revoked / expired` | PRD §5.1 |
| 凭邀请建号**必须调用** `auth.service.create_candidate_account`；同名 hr/admin 账号必须**拒绝**（不得绑定到邀请） | [module-09 §5.2](./2026-09-20-module-09-auth-plan.md) |
| 候选人隔离判据**不能复用 `created_by`**，需按「持有该面试的有效邀请」实现 | PRD §4.1；[module-01 §5.3](./2026-09-15-module-01-auth-plan.md) |
| 候选人侧路由守卫 `require_roles("candidate")`；**admin 在候选人侧不通行** | [module-09 §4.5](./2026-09-20-module-09-auth-plan.md) |
| 候选人在线答题看到的题干来自 `interview_question.content_snapshot`，**天然不含参考答案** | [module-09 §3.2](./2026-09-20-module-09-auth-plan.md)；[module-10 §3.2](./2026-09-20-module-10-question-plan.md) |
| 交卷后**候选人锁死、HR 可覆盖**；`source` 保留最初来源通道 | PRD §5.2、§4.8 |
| 候选人作答**不做**历史版本（覆盖前的原文不可追溯，已在 PRD §5.2 显式记录） | PRD §5.2 |
| 邀请码：不可枚举、有效期默认 7 天、一次性接受、可撤销 | PRD §4.4、§9 |
| E2E 走查清单（流程④ 9 项 + 越权 4 项）已写好，实现后须逐项通过 | [module-08 §4.5](./2026-09-15-module-08-e2e-plan.md) |

**依赖本文件的模块**：[module-14 evaluation 反馈](./2026-09-20-module-14-evaluation-feedback-plan.md)、[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)、[module-16 §3.1 的守卫规则](./2026-09-20-module-16-permission-guard-plan.md)。
