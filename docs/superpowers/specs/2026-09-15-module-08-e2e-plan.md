# e2e 端到端验证与收尾 执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：e2e（端到端验证、交付收尾、需求追溯）
**所属范围**：`backend/`、`frontend/`、`README.md`、`.env.example`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§5.3（三条核心流程）、§9（非功能需求）、§10（测试策略）、§11（里程碑）
**前置依赖**：全部模块（[00](./2026-09-15-module-00-core-plan.md) ～ [07](./2026-09-15-module-07-frontend-plan.md)）

---

## Global Constraints（全局约束，摘自 PRD）

- 后端分层：**router → service → repository → MySQL，严格单向依赖**（§2、§3.2）
- 每个模块独立 Python package（§2、§3.3）
- AI 通过抽象接口接入，**真实与 Mock 可配置切换**（§6）
- 评分统一 **0–10 分制**（§4.5）
- **出题同步、评估流式（SSE）**（§5.3）
- 统一前缀 `/api`，除登录外均需 JWT（§8）
- **数据隔离：普通 HR 仅见自己创建的数据，admin 见全部**（§4.1）
- **仅 PC 端**（§2）

---

## 1. 模块职责与边界

### 1.1 职责

本模块**不产生新功能**，负责把前面七个模块收口成一个可交付、可启动、可验收的整体：

| 子职责 | 内容 |
|---|---|
| 环境与启动 | 依赖安装、数据库准备、迁移执行、seed admin、前后端启动说明 |
| 配置交付 | `.env.example` 完整、README 写清切换 Mock / 真实 Provider |
| **端到端验证** | 走通 PRD §5.3 的三条核心流程 |
| **非功能验证** | 逐条验证 PRD §9 的四项非功能需求 |
| **需求追溯** | 建立「PRD 需求 → 模块文档 → 任务」的覆盖矩阵（§6） |
| 遗留问题交接 | 汇总所有对 PRD 的修正与待确认项（§7） |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **新增功能** | 本模块只验证与收尾 |
| **CI/CD 流水线** | 不在 PRD 范围 |
| **容器化（Docker）** | 不在 PRD 范围 |
| **生产部署与运维** | 不在 PRD 范围 |
| **性能压测** | PRD §9 未提出性能指标 |
| **V1.1 功能** | PRD §11 明确分期（在线答题、PDF 导出、报告分享） |

---

## 2. 交付物清单

| 交付物 | 位置 | 说明 |
|---|---|---|
| 后端工程 | `backend/` | FastAPI + 七个 package |
| 前端工程 | `frontend/` | Vite + 原生 JS |
| 依赖清单 | `backend/requirements.txt` | 完整且可安装 |
| 配置样例 | `backend/.env.example` | **全部键，无真实密钥** |
| 迁移脚本 | `backend/alembic/versions/` | 覆盖全部业务表 |
| seed 脚本 | `backend/scripts/seed_admin.py` | 幂等创建初始 admin |
| **启动文档** | `README.md` | §3 的完整内容 |
| 前端依赖 | `frontend/package.json` | 仅 vite / vitest |

---

## 3. 环境准备与启动文档（`README.md` 内容清单）

README **必须**覆盖以下内容，缺一不可——否则交付物无法被他人独立启动。

### 3.1 前置要求

| 项 | 版本要求 | 出自 |
|---|---|---|
| Python | 3.11+ | §2 |
| MySQL | 8.0+ | §2（JSON 列与 ENUM 需要） |
| Node.js | 18+ | §2（Vite 要求） |

### 3.2 后端启动步骤（按序）

| 步骤 | 内容 |
|---|---|
| 1 | 创建 Python 虚拟环境并激活 |
| 2 | `pip install -r backend/requirements.txt` |
| 3 | 复制 `.env.example` 为 `.env`，**填写 `DATABASE_URL` 与 `JWT_SECRET`** |
| 4 | 创建数据库（给出建库 SQL，注明字符集 **`utf8mb4`**） |
| 5 | `alembic upgrade head` |
| 6 | `python scripts/seed_admin.py`（创建初始 admin；说明**默认账号密码**及**生产必须修改**） |
| 7 | 启动：**`uvicorn app.main:app --workers 1`** |

> **`--workers 1` 是硬性要求**，须在 README 中**显著标注**：评估的 SSE 运行注册表是进程内的，多 worker 会导致 `POST /evaluate` 与 `GET /stream` 落在不同进程而无法衔接（见 evaluation §5.6）。

### 3.3 前端启动步骤

| 步骤 | 内容 |
|---|---|
| 1 | `cd frontend && npm install` |
| 2 | `npm run dev`（默认 5173 端口） |
| 3 | 打开 `http://localhost:5173` |
| 4 | 说明：Vite 已配置 `/api` 代理到 `http://localhost:8000`，**无需额外配置 CORS** |

### 3.4 Provider 切换说明（PRD §6）

| 场景 | 配置 | 说明 |
|---|---|---|
| **无 Key 演示 / 跑测试（默认）** | `PROVIDER_NAME=mock` | 规则生成确定性结果，**无需任何 API Key** |
| 真实大模型 | `PROVIDER_NAME=openai` + `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL` | 缺 Key 时**启动即报错**（fail fast） |

> README 中须注明：真实 Provider 调用失败时**不会自动降级到 Mock**，而是报 502 并允许重试（ai §5.5、evaluation §5.4.1）。

### 3.5 出题数量配置说明（PRD §4.4）

| 配置项 | 默认 | 说明 |
|---|---|---|
| `QUESTION_COUNT_FROM_BANK` | **5** | 从题库抽取的题数 **N** |
| `QUESTION_COUNT_FROM_AI` | **3** | AI 补充的题数 **M** |

> 说明**总题数恒为 N + M = 8**；题库不足时由 AI 补足差额（interview §5.2）。

### 3.6 测试运行说明

| 命令 | 覆盖 |
|---|---|
| `pytest` | 后端全部测试 |
| `pytest backend/tests/test_interview.py -v` | 单模块 |
| `cd frontend && npm test` | 前端单测（SSE 解析 + 雷达图几何） |

---

## 4. 端到端验证（PRD §5.3 三条核心流程）

**验证环境**：`PROVIDER_NAME=mock`、admin 账号、另一个 hr 账号。

### 4.1 流程① 创建面试 + 出题（同步，PRD §5.3 ①）

| # | 操作 | 预期 | 依据 |
|---|---|---|---|
| 1 | 创建岗位「后端工程师」，JD 填完整描述，维度填 4 个 | 201，列表可见 | §4.2 |
| 2 | 为该岗位建 **3 道题**（分属不同维度） | 列表可见，来源「手工」 | §4.3 |
| 3 | 创建面试（选该岗位 + 候选人信息） | **同步出题**，加载态结束后跳详情页 | §5.3 ① |
| 4 | 检查题目列表 | **共 8 题**，前三道为手工题、后五道为 AI 题，`seq` 从 1 连续 | §4.4 |
| 5 | 检查题库 | **新增 5 道 `source='ai'` 的题目** | §5.2、§5.3 ① |
| 6 | 修改题库中某道题的题干 | **面试详情仍显示出题时的快照** | §5.2 注释 |
| 7 | 岗位维度改 1 个 / 删 1 个 | **历史面试不受影响** | position §5.4 |

### 4.2 流程② 面试进行（手动录入，PRD §5.3 ②）

| # | 操作 | 预期 | 依据 |
|---|---|---|---|
| 1 | 逐题录入回答（含**一题留空**） | 每题显示「已保存」 | §5.3 ② |
| 2 | 修改已录入的回答 | 保存成功，**只有一条记录**（更新而非新增） | interview §5.3 |
| 3 | 点「标记完成」 | 状态 →「已完成」，`completed_at` 非空 | §5.1 |
| 4 | 尝试修改回答 | **文本框只读** | interview §5.3 |
| 5 | 点「回退到进行中」，修改回答，再「标记完成」 | 状态正确流转，`completed_at` 被清空后重新设置 | §5.1 |

### 4.3 流程③ 流式评估（PRD §5.3 ③）

| # | 操作 | 预期 | 依据 |
|---|---|---|---|
| 1 | 点「开始评估」 | 状态 →「评估中」，跳评估页并建立 SSE | §5.3 ③ |
| 2 | 观察进度 | **逐题分数逐条出现**（每题含分数 + 评语） | §4.5 |
| 3 | 观察雷达图 | **逐维度生长**，未到达的维度灰显 | §4.5 |
| 4 | 观察汇总 | 出现**总分、综合结论、优点、待改进** | §4.5 |
| 5 | 检查分数 | 逐题分、维度分、总分**均在 0–10**，保留 1 位小数 | §4.5 |
| 6 | 评估结束 | 状态 →「已评估」 | §5.1、§5.3 ③ |
| 7 | **刷新页面** | 仍能完整看到报告与雷达图 | §7 |
| 8 | 点「重新评估」 | 进度重走；逐题条数**不翻倍**；`updated_at` 更新 | §5.1 |
| 9 | 评估中途**断开网络**，再恢复 | 显示「连接已断开」+「重新连接」；重连后**从头重放并继续** | **§7** |
| 10 | 评估进行中**关闭浏览器标签**，稍后重开该页面 | 评估已完成，可看到完整报告 | **§7** |

### 4.4 异常路径验证（PRD §7）

| # | 操作 | 预期 | 依据 |
|---|---|---|---|
| 1 | 配置一个**必然失败的 Provider**（或用无效 Key 走真实 Provider）→ 创建面试 | **502 `AI_PROVIDER_ERROR`**；**面试与 AI 题目均无残留**（整体回滚）；可重试 | §7 |
| 2 | 同上，触发**评估** | 收到 `error` 事件；状态**回到「已完成」**（非卡在「评估中」）；数据库**无残留**；可重新触发 | **§7** |
| 3 | 把面试状态手工改为 `evaluating` 后重启后端 | 再次触发评估可成功（**孤儿自愈**） | evaluation §5.7 |
| 4 | 删除被面试引用的岗位 | 409「该岗位已被题库或面试引用，无法删除」 | §4.2 |
| 5 | 删除被面试引用的题目 | 409「该题目已被面试引用，无法删除」 | §4.3 |

---

## 5. 非功能需求验证（PRD §9）

### 5.1 数据隔离（PRD §4.1）

| # | 验证 | 预期 |
|---|---|---|
| 1 | 用 hr_A 账号创建岗位 / 题目 / 面试 | 均成功 |
| 2 | 登录 hr_B | **看不到 hr_A 的任何数据**（岗位 / 题目 / 面试三个列表均为空） |
| 3 | hr_B 直接请求 hr_A 资源详情（手工改 URL 的 id） | **403 `FORBIDDEN`** |
| 4 | hr_B 尝试修改 / 删除 hr_A 的资源 | **403** |
| 5 | 登录 admin | **可见全部数据**（三个列表均含 hr_A 的数据） |
| 6 | hr_B 创建面试时，岗位下拉 | **只列出 hr_B 自己的岗位** |

### 5.2 安全（PRD §9）

| # | 验证 | 预期 |
|---|---|---|
| 1 | 查看数据库 `user.password_hash` | 为 bcrypt 哈希串，**不等于明文**，且以 `$2b$` 开头 |
| 2 | 任何用户相关 API 响应 | **不含 `password_hash` 字段** |
| 3 | 不带 token 访问业务接口 | **401 `UNAUTHORIZED`** |
| 4 | 携带过期 / 篡改的 token | **401 `INVALID_TOKEN`** |
| 5 | 用错误密码与不存在的用户名分别登录 | **返回完全相同的错误码与文案**（防用户名枚举） |
| 6 | 禁用某 hr 账号后，该账号的**旧 token** 再请求 | **401**（角色 / 状态不缓存于 JWT） |
| 7 | 提交超长 / 类型错误的参数 | **400 `VALIDATION_ERROR`**，`detail` 含字段级错误 |
| 8 | 触发未预期异常 | 500 `INTERNAL_ERROR`，**响应体不含堆栈** |
| 9 | 前端界面检查 | 所有后端数据用 `textContent` 渲染，**无 `innerHTML` 注入点** |

### 5.3 可测试性（PRD §9、§10）

| # | 验证 | 预期 |
|---|---|---|
| 1 | `pytest` 全量运行 | **全部通过**，且**不需要网络**、不需要真实 API Key |
| 2 | 统计各模块测试文件 | auth / position / question / interview / evaluation / ai 六个模块**均有对应测试文件**（对应 PRD §10 的四层） |
| 3 | ai 模块测试 | **不依赖数据库**（纯函数测试） |
| 4 | `cd frontend && npm test` | 全部通过 |
| 5 | 检查 `ai` 模块源码 | **不存在对任何业务模块的 import** |
| 6 | 检查 `core` 模块源码 | 除 `get_current_user` 内的延迟导入外，**不存在对业务模块的顶层 import** |

### 5.4 可维护性（PRD §9）

| # | 验证 | 预期 |
|---|---|---|
| 1 | 检查 `backend/app/` 目录结构 | **七个独立 package**：`core` / `auth` / `position` / `question` / `interview` / `evaluation` / `ai`（对应 PRD §3.3 的六个 + core） |
| 2 | 检查每个模块内部文件 | 均有 `models.py` / `schemas.py` / `repository.py` / `service.py` / `router.py` 分层（`ai` 除外，它无 router/models） |
| 3 | 检查依赖方向 | 无**反向依赖**（如 position 不 import interview） |
| 4 | 检查 router 层 | **只做**参数校验、鉴权、响应包装，**不含业务逻辑** |
| 5 | 检查 service 层 | **只调 repository**，不直接写 SQL、不直接操作 Session 的 `execute` |
| 6 | 检查 repository 层 | **只做数据操作**，不含业务判断（如「密码是否正确」） |

---

## 6. 需求追溯矩阵（PRD 需求 → 模块文档）

> 本表用于确认**没有 PRD 要求被遗漏**。逐行核对。

### 6.1 功能需求（PRD §4）

| PRD 需求 | 章节 | 落地模块 | 具体位置 |
|---|---|---|---|
| 内置初始 admin，通过脚本 seed | §4.1 | auth | auth §5.4 |
| admin 可创建 / 管理用户，指定角色 | §4.1 | auth | auth §4.1、§5.2 |
| 普通 HR 不可自行注册 | §4.1 | auth | auth §1.2 |
| 登录签发 JWT，业务接口需携带 | §4.1 | core + auth | core §5、auth §5.1 |
| 数据隔离（HR 见自己，admin 见全部） | §4.1 | auth + 各业务模块 | auth §5.3（统一约定） |
| 岗位字段：名称、JD、评估维度列表 | §4.2 | position | position §3.1 |
| 岗位增删改查 | §4.2 | position | position §4.1 |
| **删除前校验是否被引用** | §4.2 | position | position §5.3 |
| 题目字段：内容、岗位、分类、维度、难度、标签、来源 | §4.3 | question | question §3.1 |
| 题目增删改查 | §4.3 | question | question §4.1 |
| **按岗位 / 分类 / 维度筛选** | §4.3 | question | question §4.2 |
| **题库可被面试抽取复用** | §4.3 | question → interview | question §5.6、interview §5.2 |
| 创建面试：选岗位 + 候选人信息 | §4.4 | interview | interview §4.1 |
| **出题组装（同步）：抽 N 题 + AI 补 M 题，写快照** | §4.4 | interview + ai + question | interview §5.2 |
| 记录回答，可随时编辑 | §4.4 | interview | interview §5.3 |
| 面试状态机 | §4.4 | interview | interview §5.4 |
| 评分 0–10 分制 | §4.5 | ai + evaluation | ai §3.1、evaluation §3 |
| 逐题评分（分数 + 评语） | §4.5 | evaluation + ai | evaluation §5.2、ai §3.2 |
| 多维评分（用于雷达图） | §4.5 | evaluation + ai + frontend | evaluation §3.2、frontend §4.4 |
| 汇总报告：总分 / 结论 / 优点 / 待改进 | §4.5 | evaluation + ai | evaluation §3.3、ai §4.4 |
| **评估以 SSE 流式返回** | §4.5 | evaluation + frontend | evaluation §4.3、frontend §4.3 |

### 6.2 架构约束（PRD §2、§3）

| PRD 需求 | 章节 | 落地 |
|---|---|---|
| 前后端分离，后端纯 API | §3.1 | core §8（后端不渲染页面）、frontend §1 |
| 前端原生 HTML+CSS+JS + Vite | §2 | frontend §1.2、§7 |
| 后端 Python + FastAPI | §2 | core §8 |
| 数据库 MySQL | §2 | core §4 |
| **严格分层 router→service→repository→MySQL** | §2、§3.2 | core §1.1；各模块文件结构均按此分层 |
| **每个模块独立 package** | §2、§3.3 | core §0（建立七个 package） |
| 仅 PC 端 | §2 | frontend §3.4、§6 |

### 6.3 AI 契约（PRD §6）

| PRD 需求 | 章节 | 落地 |
|---|---|---|
| 四个接口方法 | §6 | ai §3.2 |
| **两个实现（真实 / Mock）** | §6 | ai §4（Mock）、§5（真实） |
| **Mock 规则生成确定性结果** | §6 | ai §4 |
| **通过配置项选择，代码不写死** | §6 | ai §3.5、core §3（`PROVIDER_NAME`） |

### 6.4 错误处理与流程（PRD §5.1、§5.3、§7）

| PRD 需求 | 章节 | 落地 |
|---|---|---|
| 状态机五态与五条迁移 | §5.1 | interview §5.4.1 |
| 流程① 创建面试 + 出题 | §5.3 ① | interview §5.1、§5.2 |
| 流程② 面试进行（手动录入） | §5.3 ② | interview §5.3 |
| 流程③ 流式评估三阶段 | §5.3 ③ | evaluation §5.1、§5.2、§4.3 |
| 统一响应格式 `{code, message, detail}` | §7 | core §6.2、§6.3 |
| 分层错误职责 | §7 | core §6.4 |
| **AI 失败：重试 1 次 → 标记失败 → 状态回退 completed → 可重新触发** | §7 | ai §5.4（重试）、evaluation §5.4.1（回退）、interview §5.4（迁移） |
| **AI 失败不阻塞其他功能** | §7 | ai §5.6 |
| **SSE 断连：任务后台继续，重连可继续拉取进度或查最终结果** | §7 | evaluation §5.5 |

### 6.5 API 清单（PRD §8）

| PRD §8 端点 | 落地 | 备注 |
|---|---|---|
| `POST /auth/login` | auth §4.1 | — |
| `GET /auth/me` | auth §4.1 | — |
| `POST /users`、`GET /users`、`PATCH /users/{id}` | auth §4.1 | — |
| `POST/GET /positions`、`GET/PUT/DELETE /positions/{id}` | position §4.1 | — |
| `POST/GET /questions`、`GET/PUT/DELETE /questions/{id}` | question §4.1 | — |
| `POST/GET /interviews`、`GET /interviews/{id}` | interview §4.1 | — |
| `PATCH /interviews/{id}` | interview §4.1 | **范围收窄**：只改候选人信息（见 §7.1） |
| `POST /interviews/{id}/answers` | interview §4.1 | — |
| `POST /interviews/{id}/complete` | interview §4.1 | — |
| `POST /interviews/{id}/evaluate` | evaluation §4.1 | — |
| `GET /interviews/{id}/evaluation/stream` | evaluation §4.1 | — |
| `GET /interviews/{id}/report` | evaluation §4.1 | — |
| **（新增）** `POST /interviews/{id}/rollback` | interview §4.1 | 补齐 §5.1 的回退迁移入口 |

### 6.6 非功能与分期（PRD §9、§10、§11）

| PRD 需求 | 章节 | 落地 |
|---|---|---|
| 数据隔离 | §9 | auth §5.3、§5.1 |
| 密码哈希 / JWT / 参数校验 | §9 | core §5、auth §5.1 |
| 三层可独立测试、Provider 可 Mock | §9、§10 | 各模块测试设计；ai §7.1 |
| 模块边界清晰、依赖单向 | §9 | core §0、各模块 §1.3 |
| 测试策略四层 | §10 | core §9、各模块 §7 |
| **MVP 六模块 + 手动录入 + 同步出题 + 流式评估** | §11 | 全部覆盖 |
| V1.1：在线答题 / PDF 导出 / 报告分享 | §11 | **明确不在本次范围**（frontend §1.2、evaluation §1.2） |

---

## 7. 遗留问题与待确认项（**交接清单**）

以下条目是各模块文档中**对 PRD 的修正或补充**，需在验收时一并确认。

### 7.1 对 PRD 的修正（改变了 PRD 的原始设计）

| # | 修正 | 出处 | 原 PRD | 修正后 | 理由 |
|---|---|---|---|---|---|
| 1 | **`answer` 的标识键** | interview §3.3 | `(interview_id, question_id)` | `interview_question_id` | 唯一性语义更准；与快照对齐；不阻碍扩展；消除冗余 |
| 2 | **`question_score` 的标识键** | evaluation §3.1 | `question_id` | `interview_question_id` | 同上（与 #1 保持一致） |
| 3 | **`PATCH /interviews/{id}` 不再改状态** | interview §4.1 | 「更新候选人信息/状态」 | 仅改候选人信息；状态走动词端点 | 状态迁移有前置条件与副作用，作为字段更新易被绕过；同时消除 PRD §8 中 PATCH 与 `/complete` 的重叠 |
| 4 | **评估结果「先推后写」** | evaluation §5.3 | 「SSE 边推边写库」 | 三阶段实时推送 + 末尾一次性落库 | 避免失败时新旧结果混杂；避免丢失上一次完好报告；**让 §7 的「状态回退」语义干净** |
| 5 | **SSE 客户端不用 `EventSource`** | evaluation §4.3 | 未指定 | `fetch` + `ReadableStream` | `EventSource` 无法设置 `Authorization` 头；JWT 放 query string 会泄露 |
| 6 | **PRD §7 的「422/400」收口为 400** | core §6.3 | 「参数校验（422/400）」 | 统一 400 `VALIDATION_ERROR` | 使全项目错误码收敛为一张表 |

### 7.2 对 PRD 的补充（PRD 未定义，为使其可落地而补齐）

| # | 补充 | 出处 | 为何必要 |
|---|---|---|---|
| 1 | **`core` 作为第七个 package** | core §0 | PRD §3.3 只列了六个业务包，但 §7/§9 的横切要求（统一错误格式、分层底座、JWT、DB 连接）必须有唯一落点 |
| 2 | **`user.is_active`** | auth §3.1 | PRD §8 的 `PATCH /users/{id}` 要求「禁用」，无此字段无法实现 |
| 3 | **`question.created_by`** | question §3.1 | PRD §4.1 的数据隔离要求必须有归属字段才能落地 |
| 4 | **`interview_question.dimension_snapshot` / `source_snapshot`** | interview §3.2 | 与 PRD 已有的 `content_snapshot` 是同一类完整性需求；缺任一项历史面试无法自洽 |
| 5 | **`interview.completed_at`** | interview §3.1 | 标记完成的审计信息 |
| 6 | **`POST /interviews/{id}/rollback`** | interview §4.1 | PRD §5.1 要求 `completed → ongoing` 回退，但 §8 未给端点 |
| 7 | **状态迁移 `evaluating → completed`** | interview §5.4.1 | **PRD §7「AI 失败回退 completed」的必要条件** |
| 8 | **状态迁移 `evaluated → evaluating` / `evaluated → ongoing`** | interview §5.4.1 | 落实 PRD §5.1 的「可重新评估」 |
| 9 | **`question` 的 `source` / `keyword` 筛选** | question §4.2 | `source` 是 PRD 定义的字段；不能筛选则无法分辨与清理 AI 题目 |
| 10 | **`pages/users.js`（前端用户管理页）** | frontend §11 | PRD §4.1/§8 定义了 `/users`，但 §3.1 前端清单未列。**没有它 admin 无法创建 HR 账号** |
| 11 | **`src/sse.js`** | frontend §2 | 修正 #5 的直接后果 |
| 12 | **孤儿评估自愈** | evaluation §5.7 | PRD 未覆盖「评估中进程重启」，否则面试永久卡在 `evaluating` |
| 13 | **运行注册表单进程限制声明** | evaluation §5.6 | 进程内实现须明确部署约束（`--workers 1`） |
| 14 | **前端 Vitest 单测（SSE 解析 + 雷达图几何）** | frontend §8.1 | 两者是无界面反馈的纯逻辑，出错表现隐蔽。**可裁剪** |
| 15 | **各类字段的边界值**（长度、数量上限、枚举取值） | 各模块 §3 | PRD 只定义字段名，未定义边界 |

### 7.3 **需要你拍板的待确认项**

| # | 待确认 | 出处 | 选项 |
|---|---|---|---|
| 1 | **PRD §9「JWT 过期与刷新」如何落地** | core §5.3 | **A. 过期后重新登录（当前默认）** / B. 滑动续期 / C. Refresh Token（新增表与端点，属范围扩大） |
| 2 | 测试库选 MySQL 还是 SQLite | core §9.1 | **MySQL（当前推荐，与生产同构）** / SQLite（快，但 JSON 列行为有差异） |
| 3 | 前端 Vitest 单测是否保留 | frontend §8.1 | **保留（当前设计）** / 裁剪以压缩 MVP 范围 |
| 4 | `question` 是否自动收录 AI 题目 | question §5.4 | **自动收录（当前设计）** / 不收录（则 `source='ai'` 无从产生） |
| 5 | 数据隔离越权返回 403 还是 404 | auth §5.3 | **403（当前设计，语义明确）** / 404（不暴露资源存在性） |

---

## 8. 任务分解（步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 8.1：后端启动收尾

- [ ] 核对 `requirements.txt` 完整且可 `pip install` 成功
- [ ] 核对 `.env.example` 覆盖 core §3 的**全部键**，且**无真实密钥**
- [ ] 验证：全新环境按 README 步骤 1–7 可启动后端
- [ ] 验证 `GET /api/health` 返回 200
- [ ] 提交

### Task 8.2：前端启动收尾

- [ ] 核对 `package.json` 仅依赖 vite / vitest
- [ ] 核对 `vite.config.js` 的 `/api` 代理指向 `http://localhost:8000`
- [ ] 验证：全新环境 `npm install && npm run dev` 可启动
- [ ] 验证：`npm run build` 可产出 `dist/`
- [ ] 提交

### Task 8.3：编写 README

- [ ] 按 §3 的六个小节编写完整启动文档
- [ ] **显著标注 `--workers 1` 的硬性要求**（§3.2）
- [ ] 写明 Provider 切换方式与「不自动降级」的行为（§3.4）
- [ ] 写明出题数量配置与「总数恒为 N+M」（§3.5）
- [ ] 写明测试运行命令（§3.6）
- [ ] 提交

### Task 8.4：端到端主流程验证（PRD §5.3）

- [ ] 走查 §4.1 流程①（创建面试 + 出题）全部 7 项
- [ ] 走查 §4.2 流程②（手动录入）全部 5 项
- [ ] 走查 §4.3 流程③（流式评估）全部 10 项
- [ ] 记录并修复发现的问题
- [ ] 提交

### Task 8.5：异常路径验证（PRD §7）

- [ ] 走查 §4.4 全部 5 项（AI 失败回滚、评估失败回退、孤儿自愈、两个 409）
- [ ] 记录并修复发现的问题
- [ ] 提交

### Task 8.6：非功能验证（PRD §9）

- [ ] 走查 §5.1 数据隔离 6 项
- [ ] 走查 §5.2 安全 9 项
- [ ] 走查 §5.3 可测试性 6 项
- [ ] 走查 §5.4 可维护性 6 项
- [ ] 记录并修复发现的问题
- [ ] 提交

### Task 8.7：全量回归

- [ ] `pytest` 后端全量通过
- [ ] `cd frontend && npm test` 前端全量通过
- [ ] 确认测试**不依赖网络与真实 API Key**
- [ ] 提交

### Task 8.8：需求追溯核对

- [ ] 逐行核对 §6 的追溯矩阵，确认**无 PRD 要求被遗漏**
- [ ] 核对 §7.1 的 6 项修正、§7.2 的 15 项补充
- [ ] 把 §7.3 的 5 个待确认项提交给项目负责人决策
- [ ] 提交

---

## 9. 验收标准

### 9.1 可启动性

- [ ] 全新环境按 README 可**独立启动**前后端
- [ ] README 覆盖 §3 的六个小节，无缺失
- [ ] `.env.example` 包含全部配置键且无真实密钥
- [ ] README **显著标注** `--workers 1` 的硬性要求

### 9.2 功能完整性（PRD §5.3）

- [ ] 三条核心流程（创建+出题 / 手动录入 / 流式评估）**全部走通**
- [ ] 出题总数为 **N + M = 8**，题库不足时由 AI 补足
- [ ] 题库中题目修改后，历史面试**仍显示快照**
- [ ] SSE 三阶段事件**按序**到达，界面**逐条**渲染
- [ ] 评估完成后**刷新页面仍可看到完整报告**（PRD §7）
- [ ] **断线重连可继续拉取进度**（PRD §7）

### 9.3 异常健壮性（PRD §7）

- [ ] AI 出题失败 → **502 且无残留数据**
- [ ] AI 评估失败 → **状态回到 `completed`、无残留、可重新触发**
- [ ] 进程重启不导致面试**卡在 `evaluating`**
- [ ] 删除被引用的岗位 / 题目返回 **409**

### 9.4 非功能（PRD §9）

- [ ] **数据隔离**：hr 之间完全不可见（列表与详情两条路径均验证）；admin 可见全部
- [ ] **安全**：密码为哈希；响应无 `password_hash`；401/403 正确；无堆栈泄漏；无 `innerHTML` 注入
- [ ] **可测试性**：`pytest` 与 `npm test` 全通过，**不依赖网络与 Key**
- [ ] **可维护性**：七个独立 package；三层职责清晰；**无反向依赖**；`ai` 不 import 任何业务模块

### 9.5 需求覆盖（PRD §4、§6、§8）

- [ ] §6 追溯矩阵**逐行**核对通过，无遗漏
- [ ] PRD §8 的**全部端点**均已实现（含新增的 `/rollback`）
- [ ] PRD §6 的四个 AI 接口、两个实现、配置切换均已实现
- [ ] PRD §11 的 V1.1 项目**确实未实现**（无范围蔓延）

### 9.6 交接

- [ ] §7.1 的 6 项修正已向负责人说明
- [ ] §7.2 的 15 项补充已向负责人说明
- [ ] §7.3 的 5 个待确认项**已获决策**

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| 是否新增功能来「补齐」验收时发现的缺口 | **不新增** | 本模块只验证与收尾；发现的缺口记入 §7 交接清单，由负责人决定 |
| README 的详细程度 | **写到「新人可独立启动」** | 交付物的可启动性决定其价值；一步缺失会导致整条链路不可用 |
| `--workers 1` 限制是否在文档中弱化 | **显著标注，不弱化** | 多 worker 下 SSE 会失效（evaluation §5.6）；隐瞒限制会导致部署后才发现问题 |
| 前端是否补 DOM 自动化测试 | **不补**，用 §4.3 的手工清单 | 投入产出比低；关键纯逻辑已由 Vitest 覆盖 |
| 验收是否阻塞在待确认项 | **不阻塞** | §7.3 的 5 项均有默认方案，可先按默认推进，决策后再调整；仅第 1 项（JWT 刷新）若选 C 会触发范围扩大，需优先确认 |
| 性能压测 | **不做** | PRD §9 未提出任何性能指标 |
