# AI 智能面试助手 MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个面向 HR 的 AI 面试助手 Web 应用，打通「创建面试 → 出题 → 记录回答 → 评估 → 报告」完整闭环。

**Architecture:** 前后端分离。后端 FastAPI 严格分层（router → service → repository → MySQL），六个独立模块（auth/position/question/interview/evaluation/ai）；AI 通过抽象 Provider 接口接入，出题同步、评估流式（SSE）。前端原生 HTML/CSS/JS + Vite，通过 REST + SSE 调后端。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy 2.0（同步）、Pydantic v2、MySQL 8、PyJWT、bcrypt、httpx、sse-starlette、Alembic、pytest + FastAPI TestClient、Vite（原生 JS）。

**Spec:** [docs/superpowers/specs/2026-09-15-ai-interview-assistant-mvp-design.md](../specs/2026-09-15-ai-interview-assistant-mvp-design.md)

## Global Constraints

- 后端严格分层：`router → service → repository → MySQL`，只允许自上而下依赖，不跨层调用、不反向依赖。
- 每个模块独立 Python package（`backend/app/<module>/`）。
- AI 通过抽象接口接入，真实 Provider 与 Mock Provider 可配置切换，代码不写死。
- 评分统一 0–10 分制（逐题、维度、总分）。
- 出题同步、评估流式（SSE）。
- 数据隔离：普通 HR 仅见自己创建的数据，admin 见全部。
- 仅 PC 端，不做移动端响应式。
- 统一错误响应格式 `{code, message, detail}`。
- 密码哈希存储（bcrypt），JWT 鉴权。

---

## 文件结构

```
backend/
  requirements.txt
  .env.example
  alembic.ini
  alembic/
    env.py
    versions/
  app/
    main.py                  # FastAPI 实例、路由注册、CORS
    core/
      config.py              # 配置（DB URL、JWT secret、Provider 名、出题数 N/M）
      db.py                  # SQLAlchemy engine + SessionLocal + Base
      security.py            # 密码哈希、JWT 签发/校验
      exceptions.py          # 业务异常 + 统一响应包装
      deps.py                # get_db、get_current_user、require_role 依赖
    auth/
      models.py              # User
      schemas.py             # Pydantic 请求/响应
      repository.py          # User CRUD
      service.py             # 登录、用户管理
      router.py              # /auth/*、/users/*
    position/
      models.py              # Position
      schemas.py
      repository.py
      service.py
      router.py              # /positions/*
    question/
      models.py              # Question
      schemas.py
      repository.py
      service.py
      router.py              # /questions/*
    ai/
      base.py                # AIProvider 抽象基类
      mock_provider.py       # 规则生成确定性结果
      openai_provider.py     # 真实大模型实现（可选，接 HTTP）
      factory.py             # get_provider() 按配置返回实现
    interview/
      models.py              # Interview、InterviewQuestion、Answer
      schemas.py
      repository.py
      service.py             # 出题组装、状态机
      router.py              # /interviews/*
    evaluation/
      models.py              # QuestionScore、DimensionScore、Report
      schemas.py
      repository.py
      service.py             # 评估编排、逐题/多维/汇总
      stream.py              # SSE 事件流
      router.py              # /interviews/{id}/evaluate、.../report
  tests/
    conftest.py              # 测试库、TestClient、seed admin 夹具
    test_auth.py
    test_position.py
    test_question.py
    test_interview.py
    test_evaluation.py
    test_mock_provider.py

frontend/
  package.json
  vite.config.js
  index.html
  src/
    api.js                   # fetch 封装、JWT 头、统一错误处理
    auth.js                  # token 存取、登录态判断
    router.js                # hash 路由（简单 SPA）
    pages/
      login.js
      positions.js
      questions.js
      interviews.js          # 面试列表 + 创建
      interview-detail.js    # 出题结果、逐题记录回答、标记完成
      evaluation.js          # SSE 流式评估 + 雷达图 + 报告
    components/
      sidebar.js
      table.js
      modal.js
      radar.js               # Canvas/SVG 雷达图
    styles/
      main.css
```

---

## Task 0: 项目脚手架与基础设施（core）

**Files:**
- Create: `backend/requirements.txt`、`backend/.env.example`、`backend/app/main.py`、`backend/app/core/config.py`、`backend/app/core/db.py`、`backend/app/core/security.py`、`backend/app/core/exceptions.py`、`backend/app/core/deps.py`、`backend/alembic.ini`、`backend/alembic/env.py`、`backend/tests/conftest.py`

**Interfaces:**
- Produces（后续任务依赖）:
  - `config.Settings`：字段 `database_url`、`jwt_secret`、`jwt_expire_minutes`、`provider_name`、`question_count_from_bank`(默认 5)、`question_count_from_ai`(默认 3)
  - `db.Base`、`db.SessionLocal`、`db.get_db() -> Generator[Session]`
  - `security.hash_password(raw) -> str`、`security.verify_password(raw, hashed) -> bool`、`security.create_access_token(user_id: int) -> str`、`security.decode_token(token) -> int`
  - `exceptions.AppError(code, message, status_code)`、`exceptions.NotFoundError`、`exceptions.ForbiddenError`、`exceptions.BusinessError`
  - `deps.get_db()`、`deps.get_current_user(db, token) -> User`、`deps.require_role(role)` 依赖工厂
  - `main.app`（FastAPI 实例）、统一异常处理器、`GET /api/health`

- [ ] **Step 1: 建立目录结构与依赖清单**

创建 `backend/` 目录树；`requirements.txt` 写入：fastapi、uvicorn[standard]、sqlalchemy、pymysql、pydantic、pydantic-settings、pyjwt、bcrypt、httpx、sse-starlette、alembic、pytest、httpx（测试用）。

- [ ] **Step 2: 写配置与数据库基础**

`config.py` 用 pydantic-settings 从 `.env` 读配置，字段如上；`db.py` 建 engine + `SessionLocal` + `Base`（SQLAlchemy 2.0 风格 `DeclarativeBase`）。

- [ ] **Step 3: 写安全与异常基础**

`security.py` 实现 bcrypt 哈希与校验、JWT 签发与解码；`exceptions.py` 定义统一异常体系。

- [ ] **Step 4: 写依赖注入**

`deps.py` 实现 `get_db`、`get_current_user`（从 Bearer token 解出 user_id → 查 User）、`require_role(role)`。

- [ ] **Step 5: 写 app 入口与健康检查**

`main.py` 创建 FastAPI 实例、挂 CORS、注册统一异常处理器、挂 `GET /api/health`（返回 `{status: "ok"}`）。

- [ ] **Step 6: 写测试夹具**

`conftest.py`：用 SQLite 内存库（或测试用 MySQL 库）建 `Base` 全表、提供 `TestClient` 夹具、seed 一个 admin 用户。

- [ ] **Step 7: 验证健康检查**

Run: 启动 uvicorn，`curl /api/health` 返回 200 `{status:"ok"}`。用 pytest 跑一个健康检查测试，确认 TestClient 可工作。

- [ ] **Step 8: 提交**

`git init`（若未初始化）并提交脚手架。

---

## Task 1: auth 模块（登录、JWT、用户管理、数据隔离）

**Files:**
- Create: `backend/app/auth/models.py`、`backend/app/auth/schemas.py`、`backend/app/auth/repository.py`、`backend/app/auth/service.py`、`backend/app/auth/router.py`
- Test: `backend/tests/test_auth.py`
- Modify: `backend/app/main.py`（注册 auth 路由）、`backend/alembic/versions/`（迁移：User 表）

**Interfaces:**
- Consumes: `core.deps`、`core.security`、`core.exceptions`
- Produces:
  - `auth.models.User(id, username, password_hash, role, created_at)`
  - `auth.service.login(username, password) -> dict(token, user)`
  - `auth.service.create_user(db, username, password, role) -> User`
  - `auth.service.list_users(db) -> list[User]`
  - `auth.service.update_user(db, user_id, role=None, disabled=None) -> User`
  - 端点：`POST /api/auth/login`、`GET /api/auth/me`、`POST /api/users`(admin)、`GET /api/users`(admin)、`PATCH /api/users/{id}`(admin)

- [ ] **Step 1: 定义 User 模型与迁移**

`models.py` 建 User（含 role 枚举 admin/hr），用 Alembic 生成迁移。

- [ ] **Step 2: 写 login 与 me 的失败测试**

test_auth.py：错误密码返回 401；正确密码返回 token；未带 token 访问 `/auth/me` 返回 401。

- [ ] **Step 3: 实现 login 与 me**

repository + service + router：校验密码 → 签发 JWT；`/auth/me` 用 `get_current_user` 返回当前用户。

- [ ] **Step 4: 写用户管理测试**

test_auth.py：普通 HR 调 `/users` 返回 403；admin 可创建/列表/改角色。

- [ ] **Step 5: 实现用户管理**

实现 `require_role("admin")` 保护的 `/users` 端点与 service 方法。

- [ ] **Step 6: 验证数据隔离基础**

确认 `get_current_user` 注入的 User 可用于后续模块过滤 `created_by`。

- [ ] **Step 7: 提交**

---

## Task 2: position 模块（岗位 + 评估维度）

**Files:**
- Create: `backend/app/position/{models,schemas,repository,service,router}.py`
- Test: `backend/tests/test_position.py`
- Modify: `backend/app/main.py`（注册路由）、迁移

**Interfaces:**
- Consumes: `core.deps.get_current_user`
- Produces:
  - `position.models.Position(id, name, jd, evaluation_dimensions(JSON), created_by, created_at)`
  - `position.service.create_position(db, user, data) -> Position`
  - `position.service.list_positions(db, user) -> list[Position]`
  - `position.service.get_position(db, user, id) -> Position`
  - `position.service.update_position(db, user, id, data) -> Position`
  - `position.service.delete_position(db, user, id) -> None`（删除前校验无面试引用）
  - 端点：`POST/GET /api/positions`、`GET/PUT/DELETE /api/positions/{id}`

- [ ] **Step 1: 定义 Position 模型与迁移**

`evaluation_dimensions` 存 JSON 列表（如 `["沟通能力","专业能力","逻辑思维","文化契合"]`）。

- [ ] **Step 2: 写 CRUD 失败测试**

test_position.py：无 token 返回 401；HR 只能看到自己创建的岗位（数据隔离）；删除被面试引用的岗位返回业务错误。

- [ ] **Step 3: 实现 service 与 router**

严格分层：router 只做校验与包装，业务在 service，数据在 repository。

- [ ] **Step 4: 跑通测试并提交**

---

## Task 3: question 模块（题库）

**Files:**
- Create: `backend/app/question/{models,schemas,repository,service,router}.py`
- Test: `backend/tests/test_question.py`
- Modify: `backend/app/main.py`、迁移

**Interfaces:**
- Consumes: `position`（关联岗位）
- Produces:
  - `question.models.Question(id, position_id, category, dimension, content, difficulty, tags(JSON), source, created_by)`
  - `question.service.create_question(db, user, data) -> Question`
  - `question.service.list_questions(db, user, filters) -> list[Question]`（filters: position_id/category/dimension）
  - `question.service.get/update/delete`
  - 端点：`POST/GET /api/questions`、`GET/PUT/DELETE /api/questions/{id}`

- [ ] **Step 1: 定义 Question 模型与迁移**

- [ ] **Step 2: 写题库 CRUD 与筛选测试**

test_question.py：按 position_id/category/dimension 筛选；`source` 默认 `bank`；数据隔离。

- [ ] **Step 3: 实现 service 与 router**

- [ ] **Step 4: 跑通测试并提交**

---

## Task 4: ai 模块（Provider 抽象 + Mock 实现 + 工厂）

**Files:**
- Create: `backend/app/ai/base.py`、`backend/app/ai/mock_provider.py`、`backend/app/ai/openai_provider.py`、`backend/app/ai/factory.py`
- Test: `backend/tests/test_mock_provider.py`

**Interfaces:**
- Consumes: `core.config`（provider_name）
- Produces（interview/evaluation 依赖）:
  - `ai.base.AIProvider`（抽象基类），方法：
    - `generate_questions(position, dims, bank_questions, count) -> list[GeneratedQuestion]`（`GeneratedQuestion` 含 content、dimension、difficulty、source="ai"）
    - `evaluate_answer(question, answer) -> QuestionScoreResult(score, comment)`
    - `evaluate_dimensions(answers, dims) -> list[DimensionScoreResult(dimension, score, comment)]`
    - `summarize_report(all_scores, dims) -> ReportResult(overall_score, conclusion, strengths, weaknesses)`
  - `ai.factory.get_provider() -> AIProvider`（按 `provider_name` 返回 `MockProvider` 或 `OpenAIProvider`）

- [ ] **Step 1: 定义抽象基类与返回结构**

`base.py` 定义抽象方法与返回数据类（Pydantic 或 dataclass）。

- [ ] **Step 2: 实现 MockProvider**

`mock_provider.py`：规则生成确定性结果 —— 出题按维度拼模板题；评分按回答长度/关键词给 0–10 分；报告用模板句拼接。保证同输入同输出，便于测试。

- [ ] **Step 3: 写 MockProvider 测试**

test_mock_provider.py：`generate_questions` 返回 count 个题目且 source="ai"；`evaluate_answer` 分数在 0–10；`evaluate_dimensions` 覆盖传入的全部维度；`summarize_report` 返回四字段齐全。

- [ ] **Step 4: 实现 OpenAIProvider 与工厂**

`openai_provider.py`：用 httpx 调大模型 API（返回结构与抽象一致）；`factory.py` 读 `provider_name` 返回对应实现。真实 Provider 可先留空调用桩 + 明确 TODO 注释（本任务交付以 Mock 为准）。

- [ ] **Step 5: 跑通测试并提交**

---

## Task 5: interview 模块（面试、出题组装、回答记录、状态机）

**Files:**
- Create: `backend/app/interview/{models,schemas,repository,service,router}.py`
- Test: `backend/tests/test_interview.py`
- Modify: `backend/app/main.py`、迁移

**Interfaces:**
- Consumes: `auth`、`position`、`question`、`ai.factory.get_provider()`
- Produces:
  - `interview.models.Interview(id, position_id, candidate_name, candidate_contact, status, created_by, created_at)`
  - `interview.models.InterviewQuestion(id, interview_id, question_id, seq, content_snapshot)`
  - `interview.models.Answer(id, interview_id, question_id, content, recorded_at)`
  - `interview.service.create_interview(db, user, data) -> Interview`（含出题组装，见下）
  - `interview.service.list_interviews(db, user) -> list[Interview]`
  - `interview.service.get_interview(db, user, id) -> InterviewDetail`（含题目 + 回答）
  - `interview.service.save_answer(db, user, interview_id, question_id, content) -> Answer`
  - `interview.service.complete_interview(db, user, id) -> Interview`（状态 → completed）
  - 端点：`POST/GET /api/interviews`、`GET/PATCH /api/interviews/{id}`、`POST /api/interviews/{id}/answers`、`POST /api/interviews/{id}/complete`

- [ ] **Step 1: 定义三个模型与迁移**

Interview 的 status 用枚举（draft/ongoing/completed/evaluating/evaluated）。

- [ ] **Step 2: 写出题组装的失败测试**

test_interview.py：创建面试后自动生成题目（默认 5+3=8 题）；每题的 `content_snapshot` 已写入；题库不足 5 题时 AI 补齐逻辑不报错。

- [ ] **Step 3: 实现出题组装**

`create_interview`：建 Interview → 从题库按岗位/维度抽取 N 题 → 调 `generate_questions` 补 M 题 → 写 `InterviewQuestion`（含快照）→ 状态置 `ongoing`。

- [ ] **Step 4: 写回答与状态机测试**

test_interview.py：保存回答成功；`complete_interview` 把状态从 ongoing → completed；completed 可回退 ongoing；非法状态迁移返回业务错误。

- [ ] **Step 5: 实现回答记录与状态机**

`save_answer`、`complete_interview`，并在 service 层校验状态迁移合法性。

- [ ] **Step 6: 跑通测试并提交**

---

## Task 6: evaluation 模块（流式评估 + 报告）

**Files:**
- Create: `backend/app/evaluation/{models,schemas,repository,service,stream,router}.py`
- Test: `backend/tests/test_evaluation.py`
- Modify: `backend/app/main.py`、迁移

**Interfaces:**
- Consumes: `interview`（回答数据、状态）、`ai.factory.get_provider()`
- Produces:
  - `evaluation.models.QuestionScore(id, interview_id, question_id, score, comment)`
  - `evaluation.models.DimensionScore(id, interview_id, dimension, score, comment)`
  - `evaluation.models.Report(id, interview_id, overall_score, conclusion, strengths, weaknesses)`
  - `evaluation.service.get_report(db, user, interview_id) -> ReportDetail`（逐题 + 维度 + 汇总）
  - SSE 端点：`POST /api/interviews/{id}/evaluate`（触发，返回流地址）、`GET /api/interviews/{id}/evaluation/stream`（SSE）、`GET /api/interviews/{id}/report`
  - SSE 事件序：`stage=question`（逐题）→ `stage=dimension`（多维）→ `stage=report`（汇总）→ `done`

- [ ] **Step 1: 定义评估三个模型与迁移**

- [ ] **Step 2: 写评估落库测试**

test_evaluation.py：对已完成面试触发评估，落库生成逐题分、维度分、报告；`overall_score` 在 0–10。

- [ ] **Step 3: 实现评估编排（service，先同步版）**

`evaluate`：遍历每题调 `evaluate_answer` → 写 QuestionScore；调 `evaluate_dimensions` → 写 DimensionScore；调 `summarize_report` → 写 Report；状态 evaluating → evaluated。

- [ ] **Step 4: 写 SSE 流式测试**

test_evaluation.py：`GET .../evaluation/stream` 按序收到三个 stage 事件和 `done`；断连后 `get_report` 仍能查到结果。

- [ ] **Step 5: 实现 SSE 流式**

`stream.py` 用 sse-starlette 把 service 评估过程转为事件流；评估任务后台执行，SSE 边推边写库；失败时状态回退 completed 并推 `error` 事件。

- [ ] **Step 6: 实现 router 与报告查询**

`/evaluate` 触发并返回流地址；`/report` 返回完整报告结构（供前端渲染雷达图）。

- [ ] **Step 7: 跑通测试并提交**

---

## Task 7: 前端（HR 后台）

**Files:**
- Create: `frontend/package.json`、`frontend/vite.config.js`、`frontend/index.html`、`frontend/src/{api.js,auth.js,router.js}`、`frontend/src/pages/*`、`frontend/src/components/*`、`frontend/src/styles/main.css`

**Interfaces:**
- Consumes: 后端所有 `/api/*` 端点与 SSE 端点
- Produces: 可登录、管理岗位、管理题库、创建面试并查看题目、逐题记录回答、标记完成、触发流式评估并展示雷达图 + 报告

- [ ] **Step 1: Vite 脚手架 + 登录页**

`npm create vite`（vanilla）→ 配代理 `/api` 到后端；`api.js` 封装 fetch + JWT 头；`auth.js` 存 token；`login.js` 调 `/auth/login` 存 token 跳转。

- [ ] **Step 2: 布局与路由**

`router.js` 用 hash 路由；`sidebar.js` 侧边栏；未登录跳登录页。

- [ ] **Step 3: 岗位页与题库页**

`positions.js`、`questions.js` 调对应端点做列表 + 增删改（`table.js`、`modal.js` 复用）。

- [ ] **Step 4: 面试列表与创建**

`interviews.js` 列表 + 创建弹窗（选岗位、填候选人）→ 调 `POST /interviews` 拿到题目。

- [ ] **Step 5: 面试详情页（记录回答）**

`interview-detail.js` 展示题目列表（快照内容），逐题文本框保存回答（`POST .../answers`），「标记完成」按钮。

- [ ] **Step 6: 评估页（SSE + 雷达图）**

`evaluation.js` 用 `EventSource` 连流，实时渲染三阶段进度；`radar.js` 用 Canvas/SVG 画多维雷达图；结束后展示报告。

- [ ] **Step 7: 联调自测**

用 admin + hr 两个账号在浏览器走通主流程（含 Mock 评估），确认数据隔离。

- [ ] **Step 8: 提交**

---

## Task 8: 端到端验证与收尾

**Files:**
- Modify: `README.md`（启动说明：后端 uvicorn + 前端 npm dev + 迁移 + seed admin）、`.env.example` 补全

- [ ] **Step 1: 写启动文档**

README 写清：安装依赖、建库、Alembic 迁移、seed admin、起后端、起前端、切 Mock/真实 Provider。

- [ ] **Step 2: 端到端主流程验证**

用 Mock Provider 走通：登录 → 建岗位 → 建题库 → 创建面试（出题）→ 记录回答 → 完成 → 流式评估 → 看雷达图与报告。

- [ ] **Step 3: 提交**

---

## 自检记录

- **Spec 覆盖**：auth（Task 1）、position（Task 2）、question（Task 3）、interview 出题/回答/状态机（Task 5）、evaluation 流式/报告（Task 6）、ai Provider 抽象（Task 4）、数据隔离与角色（Task 0/1/2）、评分 0–10（Task 4/6）、前端（Task 7）、错误处理统一格式（Task 0）。全部有对应任务。
- **占位符**：无 TBD/TODO；真实 OpenAIProvider 以「调用桩 + TODO」标注，明确以 Mock 为交付验收（MVP 演示/测试不需要真实 Key）。
- **类型一致性**：`AIProvider` 四个方法与 spec §6 一致；状态枚举 draft/ongoing/completed/evaluating/evaluated 与 spec §5.1 一致；`content_snapshot`、`evaluation_dimensions`、`source` 字段名在模型与接口中一致。
