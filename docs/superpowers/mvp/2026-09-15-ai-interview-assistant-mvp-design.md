# AI 智能面试助手 — MVP 需求文档

> 状态：MVP-1 已评审通过（2026-09-15）；**2026-09-20 追加 MVP-2「面试者（候选人）侧」需求**
> 定位：单机部署的双端 Web 应用
> - **HR / 面试官端**：AI 辅助真人面试官完成「出题 → 记录 → 评估 → 报告」闭环
> - **面试者（候选人）端**：账号与权限、刷题练习题库、在线答题、查看脱敏反馈
>
> 约束：仍是**单机 PC 端**，**技术栈不做任何变更**（原生前端 + FastAPI + MySQL，不引入新框架与中间件）

---

## 1. 概述

### 1.1 项目定位

一个面向 HR / 面试官与面试者（候选人）的 Web 应用。AI 扮演辅助角色，服务两条业务线：

**HR / 面试官端** —— 帮助真人面试官：

1. 根据岗位（JD + 评估维度）生成面试题
2. 在面试过程中记录候选人回答（HR 手工录入，或由候选人在线作答）
3. 面试结束后自动评估候选人（逐题评分 + 多维评分）
4. 生成结构化面试报告

**面试者（候选人）端** —— 服务应聘者本人：

1. 凭邀请码激活账号，或自助注册（仅刷题权限）
2. 用刷题题库自主练习，提交后即时判分并看参考答案与解析
3. 在线作答 HR 发起的真实面试，交卷后由 HR 侧继续推进评估
4. 面试评估完成后查看面向候选人的脱敏反馈

### 1.2 目标

- 打通「创建面试 → 出题 → 记录 → 评估 → 报告」完整闭环
- 打通「发邀请 → 在线作答 → 交卷 → 反馈」候选人闭环
- 提供可复用的题库，同时服务 HR 出题与候选人刷题
- 提供候选人刷题练习闭环：取题 → 判分 → 解析 → 错题本 → 统计
- AI 能力通过抽象接口接入，无大模型 Key 也能以 Mock 方式演示和测试

### 1.3 非目标（MVP 明确不做）

- PDF 报告导出、报告分享
- 语音 / 视频面试、录音转写、简历解析、简历上传
- 多候选人横向对比
- 邮件 / 通知（邀请码在系统内展示与复制，不发送邮件）
- 流式出题（出题是同步的，仅评估环节流式）
- 移动端（仅 PC）
- **候选人社交能力**：排行榜、积分、成就、讨论区
- **在线编程判题**：代码沙箱执行、测试用例运行（刷题仅做文本问答）
- **候选人修改已交卷的作答**（交卷后候选人侧锁定）
- **候选人查看逐题分、维度分与雷达图**（默认脱敏，见 4.9）
- 候选人收藏题目、笔记

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
| 部署 | 单机部署（前后端同源，`127.0.0.1:8000`） | 不引入 Redis / 消息队列等外部中间件 |
| 前端入口 | HR 端与候选人端**同一 Vite 工程**内的两组路由 | 不新建工程、不换框架、不加构建产物 |

> 单机部署带来两条实现约束：前端限流类能力用**进程内计数**实现；同一 origin 下两端登录态必须**按端分 key**存储（见 9 非功能需求）。

---

## 3. 系统架构

### 3.1 前后端分离

- 前端：同一工程内的两组入口 —— `/hr` 后台（登录、岗位、题库、面试、报告）与 `/candidate` 端（登录/注册、刷题、我的面试、反馈），通过 REST + SSE 与后端交互
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
| `auth` | 用户、登录、JWT、角色（admin/hr/candidate）、数据隔离、候选人注册 | — |
| `position` | 岗位：名称、JD、评估维度 | auth |
| `question` | 题库：题目 CRUD、分类、标签、关联岗位、题型与参考答案 | auth, position |
| `interview` | 面试：实例、候选人信息、出题组装、回答记录、状态机、作答邀请 | auth, position, question, ai |
| `evaluation` | 评估：逐题评分、多维评分、报告、流式评估、候选人反馈视图 | auth, interview, ai |
| `practice` | 刷题：练习会话、逐题作答、判分与解析、错题本、练习统计 | auth, question, ai |
| `ai` | AI Provider 抽象：出题 / 评估 / 判分 / 反馈接口 + 真实 / Mock 实现 | — |

关键依赖方向：

- `ai` 是基础设施，被 `interview`（出题）、`evaluation`（评估）、`practice`（判分）调用
- `evaluation` 读取 `interview` 的回答数据生成报告
- `practice` 依赖 `question` 取题、依赖 `ai` 判分；**不依赖 `interview`**（刷题与真实面试解耦）
- 各业务模块均依赖 `auth` 做鉴权与数据隔离

---

## 4. 功能需求

### 4.1 用户与鉴权（auth）

- 角色三种：`admin` / `hr` / `candidate`
- 系统内置一个初始管理员（admin），通过迁移/配置脚本 seed
- admin 可创建 / 管理用户，并可指定角色（admin / hr）
- 普通 HR 不可自行注册
- 候选人账号两种来源：
  1. **邀请码激活**：HR 为某个面试生成作答邀请码，候选人凭码注册或激活账号，并绑定该面试
  2. **自助注册**：仅刷题权限，不绑定任何面试；由配置项 `CANDIDATE_SELF_REGISTER` 控制，默认开启
- 登录成功后签发 JWT；所有业务接口需携带 JWT
- 数据隔离：
  - admin 可访问全部
  - 普通 HR 只能访问自己创建的 position / question / interview
  - candidate 只能访问自己的 `practice_*` 数据，以及**自己被邀请且已接受**的面试
- **权限守卫收紧（本期必做）**：现有 HR 侧路由只校验「已登录」，加入 candidate 角色后，候选人 token 可直接调用 HR 接口。因此：
  - HR 侧路由必须显式校验角色（admin / hr 均可通过）
  - 候选人侧路由校验 candidate 角色
  - 权限校验工具需支持**多角色**判定，而非单一角色相等判断
  - 候选人数据隔离不能复用 `created_by` 判据，需新增「持有该面试的有效邀请」这一校验路径

### 4.2 岗位管理（position）

- 岗位字段：名称、JD（岗位描述）、评估维度列表
- 评估维度用于多维评分（如：沟通能力、专业能力、逻辑思维、文化契合）
- 支持岗位的增删改查；删除前校验是否被面试引用

### 4.3 题库管理（question）

- 题目字段：内容、所属岗位、分类、对应评估维度、难度、标签、来源（bank/ai）
- **新增字段（服务刷题）**：题型（单选 `single_choice` / 简答 `short_answer`）、选项列表（单选题的 `options`）、参考答案（`reference_answer`）、解析（`explanation`）
- 题型、选项、参考答案、解析可由 HR 手工录入；简答题的参考答案与解析可调 `ai` Provider 生成后由 HR 确认
- 支持题目的增删改查，支持按岗位 / 分类 / 维度 / 难度 / 题型筛选
- 题库中的题目可被面试抽取复用，也可被候选人刷题取用

### 4.4 面试管理（interview）

- 创建面试：选择岗位、填写候选人信息（姓名、联系方式）
- 出题组装（同步）：题库抽取 N 题（默认 5）+ AI 按 JD/维度补充 M 题（默认 3），合并成题目列表并写内容快照
- 记录回答（两条通道，共用同一份作答数据）：
  - **HR 手工录入**：HR 逐题录入候选人回答，可随时编辑
  - **候选人在线作答**：候选人凭邀请码进入后逐题作答（见 4.8）
- **作答邀请管理**：生成 / 查看 / 撤销邀请码；邀请码有有效期（默认 7 天）、一次性接受、不可枚举
- 候选人交卷后，其作答通道锁定；**HR 侧不受锁影响**，仍可修订作答
- 面试状态机（见 5.1）
- 数据隔离：HR 仅见自己创建的面试

### 4.5 评估与报告（evaluation）

- 评分统一采用 **0–10 分制**（逐题分、维度分、总分均 0–10）
- 逐题评分：对每一题的回答给出分数 + 评语
- 多维评分：按岗位评估维度逐项打分 + 评语（用于雷达图）
- 汇总报告：总分、综合结论、优点、待改进
- 评估以 SSE 流式返回（见 5.3）
- **面向候选人的反馈视图**：在 HR 报告之外提供候选人可见的脱敏视图，仅含综合结论、优点、待改进；总分、逐题分、维度分与雷达图默认不下发，由配置项开放（见 4.9）

### 4.6 面试者账号与权限（candidate）

- 账号来源见 4.1：邀请码激活（绑定面试）或自助注册（仅刷题）
- 登录后进入候选人端 `/candidate`
- 可见范围严格限定：
  - 自己的练习会话与作答（`practice_*`）
  - 自己被邀请且已接受的面试的**题目与自己提交的作答**
  - 自己参与的、已评估完成的面试的脱敏反馈
- 不可见：其他候选人的任何数据、HR 的评语与评分明细、未接受的面试
- 不可修改已交卷的作答
- 不能访问 HR 侧任何接口（未通过角色校验一律 403）

### 4.7 刷题练习（practice）

- 取题：按岗位 / 分类 / 维度 / 难度 / 题型筛选取题，题型含单选与简答
- 练习会话：开始一次练习（记录筛选条件）→ 逐题作答 → 结束；记录总题数、已答题数、正确数
- 即时判分：
  - 单选题：本地规则判分（不消耗 AI）
  - 简答题：调 `ai.grade_practice_answer` 判分并返回解析
  - 无大模型 Key 时由 Mock Provider 给出确定性判分，保证可演示与可测试
- 参考答案与解析：提交后展示
- 错题本：由判错的作答派生查询，**不单独建表**
- 练习统计：累计题量、正确率、按维度正确率
- 明确不做：收藏、笔记、排行榜、积分、编程题判题

### 4.8 在线答题（候选人作答）

- 入口：HR 生成邀请码 → 候选人在候选人端输入邀请码（或打开邀请链接）→ 激活并绑定面试
- 作答：整卷题目下发，候选人逐题作答，作答实时保存
- 交卷：写入交卷时间，候选人侧作答通道锁定
- 交卷后仍由 HR 确认面试完成（**不自动推进面试状态**，见 5.1）
- 数据隔离：仅能访问自己被邀请且已接受的面试

### 4.9 面试结果与反馈

- 候选人在面试评估完成后可查看脱敏反馈
- 默认仅下发：综合结论、优点、待改进
- 默认不下发：总分、逐题分、维度分、雷达图
- 是否放开评分明细由配置项 `CANDIDATE_FEEDBACK_LEVEL` 控制（`summary` 默认 / `full`）
- HR 端报告视图保持不变

---

## 5. 数据模型与业务流程

### 5.1 状态机

**面试状态机（本次不变）**

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

> **设计取舍：候选人作答不进入面试状态机。** 状态机描述的是 HR 侧的面试推进流程，且已被现有实现与测试固化；把候选人作答做成状态会让 `draft` / `ongoing` / `completed` 的语义分裂（例如「HR 还没开始面」与「候选人已交卷」相互正交）。因此候选人作答只作为**输入通道**存在：通过 `answer.source`、`answer.answered_by`、`answer.submitted_at` 表达作答来源与交卷事实，面试是否完成仍由 HR 决定。

**作答邀请状态机（新增，与面试状态解耦）**

```
pending（待接受）→ accepted（已接受） / revoked（已撤销） / expired（已过期）
```

| 迁移 | 触发 |
|---|---|
| pending → accepted | 候选人凭码激活并绑定账号 |
| pending → revoked | HR 撤销邀请 |
| pending → expired | 超过有效期（默认 7 天） |

### 5.2 数据模型（概念级）

| 实体 | 关键字段 | 所属包 |
|---|---|---|
| `user`（改） | id, username, password_hash, role, is_active, created_at | auth |
| `position` | id, name, jd, evaluation_dimensions(JSON), created_by | position |
| `question`（改） | id, position_id, category, dimension, content, question_type, options(JSON), reference_answer, explanation, difficulty, tags, source, created_by | question |
| `interview` | id, position_id, candidate_name, candidate_contact, status, created_by, created_at, completed_at | interview |
| `interview_question`（改） | id, interview_id, question_id, seq, content_snapshot, dimension_snapshot, source_snapshot | interview |
| `interview_invitation`（新） | id, interview_id, code, candidate_user_id, status, expires_at, accepted_at, created_by | interview |
| `answer`（改） | id, interview_question_id, content, source(hr/candidate), answered_by, submitted_at, recorded_at | interview |
| `question_score`（改） | id, interview_id, interview_question_id, score, comment | evaluation |
| `dimension_score` | id, interview_id, dimension, score, comment | evaluation |
| `report` | id, interview_id, overall_score, conclusion, strengths, weaknesses | evaluation |
| `practice_session`（新） | id, candidate_user_id, position_id, category, dimension, difficulty, status, total, answered_count, correct_count, started_at, finished_at | practice |
| `practice_item`（新） | id, session_id, question_id, content_snapshot, options_snapshot(JSON), reference_answer_snapshot, user_answer, is_correct, score, explanation, answered_at | practice |

说明与取舍：

- **按实现校正两处既有文档偏差**：`answer` 的唯一键挂在 `interview_question_id`（原文写作 `interview_id + question_id`），这样才能支撑「同一道题库题在一次面试中出现两次」；`interview_question` 另含 `dimension_snapshot`（维度名快照，岗位维度改名后评估归集不错位）与 `source_snapshot`（来源快照）。快照字段保证题库删改不影响历史面试与历史评估。
- **`user.role` 增加 `candidate`**；用户不做物理删除，只置 `is_active=false`（`position` / `question` / `interview` / `practice_session` 均通过外键关联本表）。
- **作答不做历史版本**：HR 覆盖候选人作答时，只保留最新内容与最后修改者 —— `source` 表示作答最初来自哪条通道，`answered_by` 表示最后修改者，`submitted_at` 记录候选人交卷时间（HR 手工录入时为 `null`）。代价是覆盖前的候选人原文不可追溯，MVP 接受。
- **错题本不建表**，由 `practice_item.is_correct=false` 派生查询。
- **`practice_item` 带题目快照**：会话开始时即按筛选条件取题生成待答项（`user_answer` 为空），并写入 `content_snapshot` / `options_snapshot` / `reference_answer_snapshot`；题库删改不影响进行中与历史练习的复看。逐题提交只回填 `user_answer` / `is_correct` / `score` / `explanation` / `answered_at`。
- `question` 复用为刷题题源，不另建练习题库表 —— 单一题库同时服务 HR 出题与候选人刷题。

### 5.3 五条核心流程

**① 创建面试 + 出题（同步）**
1. HR 选岗位 + 填候选人信息
2. 系统从题库按岗位/维度抽取 N 题
3. 调 `ai` Provider 出题接口，按 JD + 评估维度补充 M 题
4. 合并生成题目列表并写内容快照，面试进入 `ongoing`

**② 面试进行（HR 手动录入）**
1. HR 逐题录入候选人回答，回答实时保存到 `answer`
2. HR 标记完成 → 进入 `completed`

**③ 流式评估（SSE）**
1. HR 点「开始评估」→ 状态 `evaluating`，前端建立 SSE 连接
2. 后端流式推送三阶段：逐题评分 → 多维评分 → 汇总报告
3. 结束事件后状态 `evaluated`，前端渲染雷达图 + 报告

**④ 在线答题（HR 发邀请 → 候选人在线作答）**
1. HR 为面试生成作答邀请码（`pending`）
2. 候选人凭码激活账号并绑定该面试（`accepted`）
3. 候选人逐题作答，作答实时保存到 `answer`（`source=candidate`，`answered_by=候选人`）
4. 候选人交卷 → 写 `submitted_at`，候选人侧通道锁定；面试状态不变
5. HR 可修订作答（`source` 保留 `candidate`，仅更新 `answered_by`），随后标记 `completed`
6. 走既有流式评估（流程 ③），评估完成后候选人可查看脱敏反馈

**⑤ 刷题练习**
1. 候选人开始一次练习，选定岗位 / 分类 / 维度 / 难度 → 生成 `practice_session`，按条件取题并生成待答项（写题目快照）
2. 逐题提交：单选本地规则判分；简答调 `ai.grade_practice_answer` 判分并取解析
3. 判分结果回填 `practice_item`（`user_answer`、`is_correct`、`score`、`explanation`），并更新会话计数
4. 结束练习 → 会话置完成，展示小结；错题本与统计由 `practice_item` 派生

---

## 6. AI Provider 接口契约

`ai` 包对外暴露抽象接口，被 `interview` / `evaluation` / `practice` 调用：

| 接口方法 | 用途 | 调用方 |
|---|---|---|
| `generate_questions(position, dims, bank_questions, count)` | 按 JD + 维度 + 已有题库题补充生成题目 | interview（出题） |
| `evaluate_answer(question, answer)` | 单题打分 + 评语 | evaluation（逐题评分） |
| `evaluate_dimensions(answers, dims)` | 综合多维打分 + 评语 | evaluation（多维评分） |
| `summarize_report(all_scores, dims)` | 汇总总分/结论/优点/待改进 | evaluation（报告） |
| `generate_reference_answer(question)` | 为缺参考答案的题目生成参考答案与解析 | question / practice |
| `grade_practice_answer(question, user_answer)` | 刷题作答判分 + 解析（简答题） | practice |
| `generate_candidate_feedback(report, level)` | 由报告生成面向候选人的脱敏反馈 | evaluation |

两个实现：

- **真实 Provider**：调用大模型 API
- **Mock Provider**：规则生成确定性结果，用于无 Key 演示与测试

通过配置项选择使用哪个 Provider，代码不写死。刷题判分在 AI 不可用时降级（见 7）。

---

## 7. 错误处理

- **统一响应格式**：`{code, message, detail}`，router 层集中包装
- **分层职责**：
  - router：参数校验（422/400）、鉴权（401/403）
  - service：抛业务异常（资源不存在、状态非法、越权）
  - repository：DB 异常转统一异常
- **AI 调用失败**（超时/限流/Key 无效）：重试 1 次 → 仍失败则评估任务标记失败、状态回退 `completed`，可重新触发；不阻塞其他功能
- **SSE 断连**：评估任务后台继续，前端重连后可继续拉取进度或查询最终结果
- **候选人侧补充**：
  - 邀请码无效 / 已过期 / 已撤销 → 业务错误，不泄露面试是否存在
  - 重复接受同一邀请 → 业务错误（冲突）
  - 候选人修改已交卷作答 → 业务错误（冲突）
  - 越权访问（非本人面试、非本人练习）→ **403**，沿用现有 `ensure_resource_visible` 的语义：资源存在但无权访问
  - 角色不符（候选人调 HR 接口、HR 调候选人接口）→ 403
  - 刷题 AI 判分失败 → 不阻塞作答：`practice_item` 正常落库但 `is_correct` 为空，标记为未判分，可后续重判
  - 刷题限流（进程内计数，单机规模）→ 超限返回业务错误

---

## 8. API 概览

统一前缀 `/api`，除登录与候选人自助注册外均需 JWT。

### auth
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/login` | 登录，返回 JWT | 公开 |
| POST | `/auth/register` | 候选人自助注册（仅刷题；配置可关） | 公开 |
| GET | `/auth/me` | 当前用户信息 | 登录 |
| POST | `/users` | 创建用户 | admin |
| GET | `/users` | 用户列表 | admin |
| PATCH | `/users/{id}` | 改角色/禁用 | admin |

### position
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/positions` | 创建岗位 | admin, hr |
| GET | `/positions` | 岗位列表 | admin, hr |
| GET | `/positions/{id}` | 岗位详情 | admin, hr |
| PUT | `/positions/{id}` | 更新岗位 | admin, hr |
| DELETE | `/positions/{id}` | 删除岗位 | admin, hr |

### question
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/questions` | 创建题目 | admin, hr |
| GET | `/questions` | 题目列表（按岗位/分类/维度/难度/题型筛选） | admin, hr |
| GET | `/questions/{id}` | 题目详情 | admin, hr |
| PUT | `/questions/{id}` | 更新题目（含题型、参考答案、解析） | admin, hr |
| DELETE | `/questions/{id}` | 删除题目 | admin, hr |

### interview
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/interviews` | 创建面试（含同步出题） | admin, hr |
| GET | `/interviews` | 面试列表（按用户隔离） | admin, hr |
| GET | `/interviews/{id}` | 面试详情（含题目+回答） | admin, hr |
| PATCH | `/interviews/{id}` | 更新候选人信息/状态 | admin, hr |
| POST | `/interviews/{id}/answers` | 保存/更新某题回答（含覆盖候选人作答） | admin, hr |
| POST | `/interviews/{id}/complete` | 标记完成 | admin, hr |
| POST | `/interviews/{id}/evaluate` | 触发评估，返回 SSE 地址 | admin, hr |
| GET | `/interviews/{id}/evaluation/stream` | SSE 流式评估 | admin, hr |
| POST | `/interviews/{id}/invitations` | 生成作答邀请码 | admin, hr |
| GET | `/interviews/{id}/invitations` | 邀请列表与状态 | admin, hr |
| DELETE | `/interviews/{id}/invitations/{inv_id}` | 撤销邀请 | admin, hr |

### evaluation
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/interviews/{id}/report` | 获取最终报告（逐题+多维+汇总） | admin, hr |

### candidate（候选人侧）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/candidate/invitations/{code}/accept` | 凭邀请码激活并绑定面试 |
| GET | `/candidate/interviews` | 我参与的面试列表 |
| GET | `/candidate/interviews/{id}` | 面试详情（仅题目与我自己的作答） |
| POST | `/candidate/interviews/{id}/answers` | 保存/更新我的作答（交卷后拒绝） |
| POST | `/candidate/interviews/{id}/submit` | 交卷（幂等） |
| GET | `/candidate/interviews/{id}/feedback` | 查看面向候选人的脱敏反馈 |

### practice（候选人侧）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/practice/questions` | 刷题取题（按岗位/分类/难度/题型筛选） |
| POST | `/practice/sessions` | 开始一次练习 |
| GET | `/practice/sessions/{id}` | 练习详情与进度 |
| POST | `/practice/sessions/{id}/items` | 提交某题作答 → 即时判分 + 解析 |
| POST | `/practice/sessions/{id}/finish` | 结束练习，出小结 |
| GET | `/practice/wrong-book` | 错题本（由 practice_item 派生） |
| GET | `/practice/stats` | 我的练习统计（题量/正确率/按维度） |

> candidate 与 practice 两组接口权限均为 `candidate`，数据隔离为「仅本人数据 + 本人已接受的邀请所对应面试」。

---

## 9. 非功能需求

- **数据隔离（三端）**：admin 见全部；普通 HR 仅见自己创建的数据；candidate 仅见自己的练习数据与自己已接受的邀请所对应面试的题目与自己的作答
- **权限守卫**：HR 侧全部接口显式校验角色（admin/hr），候选人侧接口校验 candidate；权限工具支持多角色判定。这是本期新增强制项，不是可选项
- **候选人可见性**：反馈默认脱敏（仅综合结论/优点/待改进）；逐题分、维度分、雷达图默认不下发，由配置项 `CANDIDATE_FEEDBACK_LEVEL` 控制
- **单机约束适配**：
  - 前端同一 origin 下两端登录态**按端分 key 存储**（`hr.*` / `candidate.*`），保证单浏览器可同时保持 HR 与候选人登录
  - 限流类能力用进程内计数实现，不引入 Redis 等中间件
- **安全**：密码哈希存储（bcrypt/argon2）；JWT 过期与刷新；参数校验防注入；邀请码具备足够熵、不可枚举、有效期默认 7 天、一次性接受、可撤销
- **可测试性**：三层可独立测试；AI Provider 可 Mock（刷题判分同样可在无 Key 下确定性复现）
- **可维护性**：模块边界清晰，依赖单向，每个 package 可独立理解与修改；`practice` 不依赖 `interview`，刷题与真实面试解耦

---

## 10. 测试策略

| 层 | 内容 |
|---|---|
| repository | 连测试库测 CRUD |
| service | 注入 mock repository / mock Provider，测业务逻辑与状态机 |
| practice service | 注入 mock repository / mock Provider，测判分分支（单选规则判分、简答 AI 判分、AI 失败降级）与错题本 / 统计的派生 |
| router | TestClient 测端点（含鉴权、错误码、数据隔离） |
| 权限 | 候选人 token 调 HR 接口 → 403；HR 调候选人接口 → 403；候选人 A 访问候选人 B 的面试 / 练习 → 403；访问未被邀请或未接受的面试 → 403 |
| 流程 | 邀请生命周期（pending → accepted / revoked / expired）、交卷锁定与 HR 覆盖、候选人重复交卷幂等 |
| 集成 | 出题组装、状态机流转、评估落库 三条主流程；在线答题、刷题练习 两条新增主流程 |

---

## 11. 里程碑与分期

### MVP-1 HR / 面试官侧（已完成）
- auth / position / question / interview / evaluation / ai 六模块
- 手动录入回答 + 同步出题 + 流式评估
- 后端契约已由 461 条用例验证（见 [API 接口测试报告](../../tests/2026-09-17-API接口测试报告.md)）

### MVP-2 面试者（候选人）侧（2026-09-20 追加，本文档范围）
- `auth`：新增 candidate 角色、候选人注册、权限守卫收紧（多角色判定）
- `interview`：作答邀请（生成/接受/撤销/过期）、候选人在线作答通道与交卷锁定
- `question`：题型、选项、参考答案、解析字段
- `evaluation`：面向候选人的脱敏反馈视图
- `practice`：新模块 —— 练习会话、逐题判分与解析、错题本、练习统计
- 前端：同一 Vite 工程内新增候选人路由与页面；登录态按端分 key

### V1.1（规划，不在本 MVP）
- PDF 报告导出
- 报告分享
- 语音 / 视频面试、简历解析
- 多候选人横向对比
