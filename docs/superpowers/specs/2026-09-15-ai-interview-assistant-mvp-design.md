# AI 智能面试助手 — MVP 需求文档

> 状态：已评审通过（2026-09-15）
> 定位：HR/面试官助手 —— AI 辅助真人面试官完成「出题 → 记录 → 评估 → 报告」闭环

---

## 1. 概述

### 1.1 项目定位

一个面向 HR / 面试官的 Web 应用。AI 扮演辅助角色，帮助真人面试官：

1. 根据岗位（JD + 评估维度）生成面试题
2. 在面试过程中记录候选人回答
3. 面试结束后自动评估候选人（逐题评分 + 多维评分）
4. 生成结构化面试报告

### 1.2 目标

- 打通「创建面试 → 出题 → 记录 → 评估 → 报告」完整闭环
- 提供可复用的题库，并支持 AI 按岗位现场出题
- AI 能力通过抽象接口接入，无大模型 Key 也能以 Mock 方式演示和测试

### 1.3 非目标（MVP 明确不做）

- 在线答题（候选人侧答题页）→ 规划至 V1.1
- PDF 报告导出、报告分享
- 语音 / 视频面试、录音转写、简历解析
- 多候选人横向对比
- 邮件 / 通知
- 流式出题（出题是同步的，仅评估环节流式）
- 移动端（仅 PC）

---

## 2. 技术栈与约束

| 项 | 选择 | 约束 |
|---|---|---|
| 架构 | 前后端分离 | 后端纯 API，不渲染页面 |
| 前端 | 原生 HTML + CSS + JavaScript + Vite 构建 | 无 UI 框架 |
| 后端 | Python + FastAPI | — |
| 数据库 | MySQL | — |
| 后端分层 | router → service → repository → MySQL | 严格单向依赖 |
| 模块组织 | 每个模块独立 Python package | — |
| 终端 | 仅 PC 端 | 不考虑移动端响应式 |

---

## 3. 系统架构

### 3.1 前后端分离

- 前端：`/hr` 后台（登录、岗位、题库、面试、报告），通过 REST + SSE 与后端交互
- 后端：FastAPI 提供 JSON API，JWT 鉴权，不负责页面渲染

### 3.2 后端严格分层

每个模块内部统一遵循：

```
router    → HTTP 端点：参数校验、鉴权、统一响应包装
service   → 业务逻辑：流程编排、事务、调用 AI Provider
repository → 数据访问：CRUD，对接 MySQL
```

依赖方向只允许自上而下：`router → service → repository`。service 依赖 repository 接口（依赖注入），不跨层调用、不反向依赖。

### 3.3 模块划分（每个模块独立 package）

| 包名 | 职责 | 依赖 |
|---|---|---|
| `auth` | 用户、登录、JWT、角色（admin/hr）、数据隔离 | — |
| `position` | 岗位：名称、JD、评估维度 | auth |
| `question` | 题库：题目 CRUD、分类、标签、关联岗位 | auth, position |
| `interview` | 面试：实例、候选人信息、出题组装、回答记录、状态机 | auth, position, question, ai |
| `evaluation` | 评估：逐题评分、多维评分、报告、流式评估 | auth, interview, ai |
| `ai` | AI Provider 抽象：出题/评估接口 + 真实/Mock 实现 | — |

关键依赖方向：

- `ai` 是基础设施，被 `interview`（出题）与 `evaluation`（评估）调用
- `evaluation` 读取 `interview` 的回答数据生成报告
- 各业务模块均依赖 `auth` 做鉴权与数据隔离

---

## 4. 功能需求

### 4.1 用户与鉴权（auth）

- 系统内置一个初始管理员（admin），通过迁移/配置脚本 seed
- admin 可创建 / 管理用户，并可指定角色（admin / hr）
- 普通 HR 不可自行注册
- 登录成功后签发 JWT；所有业务接口需携带 JWT
- 数据隔离：普通 HR 只能访问自己创建的数据；admin 可访问全部

### 4.2 岗位管理（position）

- 岗位字段：名称、JD（岗位描述）、评估维度列表
- 评估维度用于多维评分（如：沟通能力、专业能力、逻辑思维、文化契合）
- 支持岗位的增删改查；删除前校验是否被面试引用

### 4.3 题库管理（question）

- 题目字段：内容、所属岗位、分类、对应评估维度、难度、标签、来源（bank/ai）
- 支持题目的增删改查，支持按岗位 / 分类 / 维度筛选
- 题库中的题目可被面试抽取复用

### 4.4 面试管理（interview）

- 创建面试：选择岗位、填写候选人信息（姓名、联系方式）
- 出题组装（同步）：题库抽取 N 题（默认 5）+ AI 按 JD/维度补充 M 题（默认 3），合并成题目列表并写内容快照
- 记录回答：HR 逐题录入候选人回答，可随时编辑
- 面试状态机（见 5.1）
- 数据隔离：HR 仅见自己创建的面试

### 4.5 评估与报告（evaluation）

- 评分统一采用 **0–10 分制**（逐题分、维度分、总分均 0–10）
- 逐题评分：对每一题的回答给出分数 + 评语
- 多维评分：按岗位评估维度逐项打分 + 评语（用于雷达图）
- 汇总报告：总分、综合结论、优点、待改进
- 评估以 SSE 流式返回（见 5.3）

---

## 5. 数据模型与业务流程

### 5.1 面试状态机

```
draft（草稿）→ ongoing（进行中）→ completed（已完成）→ evaluating（评估中）→ evaluated（已评估）
```

| 迁移 | 触发 |
|---|---|
| draft → ongoing | 出题组装完成 |
| ongoing → completed | HR 标记面试完成 |
| completed → evaluating | 触发流式评估 |
| evaluating → evaluated | 评估流结束、报告落库 |
| completed → ongoing | 回退以补充/修改回答（可重新评估） |

### 5.2 数据模型（概念级）

| 实体 | 关键字段 | 所属包 |
|---|---|---|
| `user` | id, username, password_hash, role | auth |
| `position` | id, name, jd, evaluation_dimensions(JSON), created_by | position |
| `question` | id, position_id, category, dimension, content, difficulty, tags, source | question |
| `interview` | id, position_id, candidate_name, candidate_contact, status, created_by | interview |
| `interview_question` | interview_id, question_id, seq, content_snapshot | interview |
| `answer` | id, interview_id, question_id, content, recorded_at | interview |
| `question_score` | id, interview_id, question_id, score, comment | evaluation |
| `dimension_score` | id, interview_id, dimension, score, comment | evaluation |
| `report` | id, interview_id, overall_score, conclusion, strengths, weaknesses | evaluation |

> `interview_question.content_snapshot` 保存出题时的题目内容快照，之后题库删改不影响历史面试。

### 5.3 三条核心流程

**① 创建面试 + 出题（同步）**
1. HR 选岗位 + 填候选人信息
2. 系统从题库按岗位/维度抽取 N 题
3. 调 `ai` Provider 出题接口，按 JD + 评估维度补充 M 题
4. 合并生成题目列表并写内容快照，面试进入 `ongoing`

**② 面试进行（手动录入）**
1. HR 逐题录入候选人回答，回答实时保存到 `answer`
2. HR 标记完成 → 进入 `completed`

**③ 流式评估（SSE）**
1. HR 点「开始评估」→ 状态 `evaluating`，前端建立 SSE 连接
2. 后端流式推送三阶段：逐题评分 → 多维评分 → 汇总报告
3. 结束事件后状态 `evaluated`，前端渲染雷达图 + 报告

---

## 6. AI Provider 接口契约

`ai` 包对外暴露抽象接口，被 `interview` / `evaluation` 调用：

| 接口方法 | 用途 | 调用方 |
|---|---|---|
| `generate_questions(position, dims, bank_questions, count)` | 按 JD + 维度 + 已有题库题补充生成题目 | interview（出题） |
| `evaluate_answer(question, answer)` | 单题打分 + 评语 | evaluation（逐题评分） |
| `evaluate_dimensions(answers, dims)` | 综合多维打分 + 评语 | evaluation（多维评分） |
| `summarize_report(all_scores, dims)` | 汇总总分/结论/优点/待改进 | evaluation（报告） |

两个实现：

- **真实 Provider**：调用大模型 API
- **Mock Provider**：规则生成确定性结果，用于无 Key 演示与测试

通过配置项选择使用哪个 Provider，代码不写死。

---

## 7. 错误处理

- **统一响应格式**：`{code, message, detail}`，router 层集中包装
- **分层职责**：
  - router：参数校验（422/400）、鉴权（401/403）
  - service：抛业务异常（资源不存在、状态非法、越权）
  - repository：DB 异常转统一异常
- **AI 调用失败**（超时/限流/Key 无效）：重试 1 次 → 仍失败则评估任务标记失败、状态回退 `completed`，可重新触发；不阻塞其他功能
- **SSE 断连**：评估任务后台继续，前端重连后可继续拉取进度或查询最终结果

---

## 8. API 概览

统一前缀 `/api`，除登录外均需 JWT。

### auth
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/login` | 登录，返回 JWT | 公开 |
| GET | `/auth/me` | 当前用户信息 | 登录 |
| POST | `/users` | 创建用户 | admin |
| GET | `/users` | 用户列表 | admin |
| PATCH | `/users/{id}` | 改角色/禁用 | admin |

### position
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/positions` | 创建岗位 |
| GET | `/positions` | 岗位列表 |
| GET | `/positions/{id}` | 岗位详情 |
| PUT | `/positions/{id}` | 更新岗位 |
| DELETE | `/positions/{id}` | 删除岗位 |

### question
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/questions` | 创建题目 |
| GET | `/questions` | 题目列表（按岗位/分类/维度筛选） |
| GET | `/questions/{id}` | 题目详情 |
| PUT | `/questions/{id}` | 更新题目 |
| DELETE | `/questions/{id}` | 删除题目 |

### interview
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/interviews` | 创建面试（含同步出题） |
| GET | `/interviews` | 面试列表（按用户隔离） |
| GET | `/interviews/{id}` | 面试详情（含题目+回答） |
| PATCH | `/interviews/{id}` | 更新候选人信息/状态 |
| POST | `/interviews/{id}/answers` | 保存/更新某题回答 |
| POST | `/interviews/{id}/complete` | 标记完成 |
| POST | `/interviews/{id}/evaluate` | 触发评估，返回 SSE 地址 |
| GET | `/interviews/{id}/evaluation/stream` | SSE 流式评估 |

### evaluation
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/interviews/{id}/report` | 获取最终报告（逐题+多维+汇总） |

---

## 9. 非功能需求

- **数据隔离**：普通 HR 仅见自己创建的数据，admin 见全部
- **安全**：密码哈希存储（bcrypt/argon2）；JWT 过期与刷新；参数校验防注入
- **可测试性**：三层可独立测试；AI Provider 可 Mock
- **可维护性**：模块边界清晰，依赖单向，每个 package 可独立理解与修改

---

## 10. 测试策略

| 层 | 内容 |
|---|---|
| repository | 连测试库测 CRUD |
| service | 注入 mock repository / mock Provider，测业务逻辑与状态机 |
| router | TestClient 测端点（含鉴权、错误码、数据隔离） |
| 集成 | 出题组装、状态机流转、评估落库 三条主流程 |

---

## 11. 里程碑与分期

### MVP（本文档范围）
- auth / position / question / interview / evaluation / ai 六模块
- 手动录入回答 + 同步出题 + 流式评估

### V1.1（规划，不在本 MVP）
- 在线答题（候选人侧）
- PDF 报告导出
- 报告分享
