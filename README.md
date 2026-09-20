# AI 智能面试助手

面向 HR / 面试官的 Web 应用。AI 辅助真人面试官完成「**出题 → 记录 → 评估 → 报告**」闭环。

- **设计文档**：[docs/superpowers/mvp/](docs/superpowers/mvp/)（PRD）
- **模块计划书**：[docs/superpowers/specs/](docs/superpowers/specs/)（7 个模块的设计与验收标准）

---

## 快速开始

**只想运行 / 演示：双击根目录的 [`一键启动.bat`](一键启动.bat)。**

它会构建前端、检查数据库、启动后端，然后自动打开 <http://127.0.0.1:8000>。
登录：`admin` / `admin12345`。

失败时脚本会把原因和解决办法直接打印出来。完整的分步说明与排查表见
[如何打开项目.md](如何打开项目.md)。

> ⚠️ **不要双击 `frontend/index.html`**，也不要双击 `frontend/dist/index.html`
> —— 它们是 ES 模块，浏览器在 `file://` 下会用 CORS 策略拒绝加载，双击必然白屏。
> 必须经由 `http://` 访问（上面的一键启动做的就是这件事）。
>
> 例外的只有 `frontend/standalone.html`：它是单文件版本，双击确实能开，
> 但数据是写死的假数据、界面是 2026-09-16 的冻结快照，不再更新 ——
> 只适合给人扫一眼设计，不能用来演示真实功能。

下面的内容是给要改这个项目的人看的。

---

## 技术栈

| 项 | 选择 |
|---|---|
| 架构 | 前后端分离；开发期前端经 Vite 代理，演示期前端由后端托管（同源，无 CORS） |
| 后端 | Python 3.11+ / FastAPI |
| 前端 | Vite 8 + 原生 HTML/CSS/JS（无 UI 框架、无图表库、无状态管理库） |
| 数据库 | MySQL 8.0+ |
| 分层 | `router → service → repository → MySQL`，严格单向依赖 |
| 模块 | 八个独立 package：`core` / `auth` / `position` / `question` / `interview` / `evaluation` / `practice` / `ai` |
| AI | 抽象 Provider 接口，`mock` 与 `openai` 可配置切换 |

---

## 前置要求

| 项 | 版本 |
|---|---|
| Python | 3.11+（本机验证于 3.13） |
| MySQL | 8.0+（本机验证于 9.7；JSON 列与 ENUM 需要 8.0+） |

---

## 手动启动

> 日常运行请直接双击 [`一键启动.bat`](一键启动.bat)，本节是它背后做的事。
> **所有命令都必须在所示目录下执行** —— 在项目根目录跑 `uvicorn` 会得到
> `ModuleNotFoundError: No module named 'app'`（详见 [如何打开项目.md](如何打开项目.md)）。

### 后端

```bash
cd backend

# 1) 虚拟环境（可选但推荐）
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

# 2) 安装依赖
pip install -r requirements.txt

# 3) 配置：复制样例并填写
cp .env.example .env
#   必须填写：DATABASE_URL、JWT_SECRET
#   生成密钥：python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4) 建库（字符集必须是 utf8mb4）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS interview_dev \
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 5) 执行迁移
python -m alembic upgrade head

# 6) 创建初始管理员（幂等，重复执行不会重复创建）
python scripts/seed_admin.py

# 7) 启动
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

启动后：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

> ### ⚠️ `--workers 1` 是硬性要求
>
> 评估的 SSE 运行注册表是**进程内**的内存结构。多 worker 部署时，
> `POST /evaluate` 可能落在 worker A，而 `GET /evaluation/stream` 落在 worker B，
> B 看不到 A 的注册表，SSE 会退化为「从库合成」或直接报错。
>
> 如需多 worker，须改用 Redis pub/sub 或 Celery + 结果后端 —— 不在 MVP 范围。

> ### ⚠️ 默认管理员密码
>
> `seed_admin.py` 使用的默认密码（`admin12345`）仅供本地开发。
> **生产环境必须在 `.env` 中修改 `ADMIN_PASSWORD` 后重建账号**。

### 前端

后端启动后会**自动托管前端构建产物**（`frontend/dist` 存在时），
所以 <http://127.0.0.1:8000> 直接就是完整应用，不需要再开一个服务。

```bash
cd frontend
npm install
npm run build      # 产出 dist/，后端下次启动即可托管
```

**要频繁改前端**时用开发服务器（保存即刷新，但要多开一个进程）：

```bash
cd frontend
npm run dev        # → http://localhost:5173，/api 被代理到 8000
```

| | 一键启动 / 后端托管 | `npm run dev` |
|---|---|---|
| 地址 | <http://127.0.0.1:8000> | <http://localhost:5173> |
| 进程数 | 1 | 2（后端 + Vite） |
| 改了前端代码 | 需重新 `npm run build` | 自动刷新 |
| 适合 | 演示、给别人看 | 自己写代码 |

前端的设计决策见 [frontend/README.md](frontend/README.md)。

---

## AI Provider 切换

通过 `.env` 的 `PROVIDER_NAME` 切换，代码不写死：

| 场景 | 配置 | 说明 |
|---|---|---|
| **无 Key 演示 / 跑测试（默认）** | `PROVIDER_NAME=mock` | 规则生成**确定性**结果，无需任何 API Key |
| 真实大模型 | `PROVIDER_NAME=openai`<br>+ `OPENAI_API_KEY`<br>+ `OPENAI_BASE_URL`<br>+ `OPENAI_MODEL` | 缺任一项**启动即失败**（fail fast） |

两条重要行为：

1. **真实 Provider 调用失败时不会自动降级到 Mock**，而是返回 **502 `AI_PROVIDER_ERROR`** 并允许重试。
   静默降级会把规则模板的输出伪装成 AI 评估结果，既误导用户又掩盖故障。
2. **启动期即校验配置**：`PROVIDER_NAME` 取值非法、或选了 `openai` 却没配 Key，
   服务会直接启动失败，而不是等到第一次调用 AI 才报错。

---

## 出题数量配置

| 配置项 | 默认 | 含义 |
|---|---|---|
| `QUESTION_COUNT_FROM_BANK` | **5** | 从题库抽取的题数 **N** |
| `QUESTION_COUNT_FROM_AI` | **3** | AI 补充的题数 **M** |

**总题数恒为 N + M = 8**：题库不足时由 AI 补足差额（`need_ai = M + (N - K)`，K 为实际抽到的题库题数）。

抽取采用 round-robin（按维度轮询、组内按 id 升序），因此**相同数据状态下出题结果完全可预测**。

---

## 候选人侧配置

| 配置项 | 默认 | 含义 |
|---|---|---|
| `CANDIDATE_SELF_REGISTER` | **true** | 候选人自助注册开关 |

**默认开启是为了开箱演示** —— 无 Key 的 Mock 环境也能跑通刷题闭环。

> ⚠️ **生产部署应置为 `false`**。关闭后候选人只能凭 HR 发放的邀请码建号，
> 账号与某场真实面试或刷题行为始终有真实关联。注意该开关**不影响凭邀请码建号**
> —— 那条路径必须始终可用，否则关闭开关等于把候选人完全挡在门外。
>
> 关闭时的注册请求返回 `409 BUSINESS_ERROR`，`detail.reason` 为
> `self_register_disabled`，前端可据此提示改用邀请码。

---

## 运行测试

```bash
cd backend
python -m pytest                       # 全部（771 项）
python -m pytest tests/test_interview.py -v
```

测试**不需要网络，也不需要任何 API Key**（全部走 Mock Provider）。

测试使用独立的 MySQL 测试库（默认 `interview_test`，由 `tests/conftest.py` 自动创建），
与开发库物理隔离。可用环境变量覆盖：

```bash
DATABASE_URL="mysql+pymysql://root:pwd@127.0.0.1:3306/other_test?charset=utf8mb4" python -m pytest
```

### 端到端冒烟

对**真实运行中的服务**走通三条核心流程（登录 → 建岗位/题库 → 建面试 → 录回答 → 完成 → 流式评估 → 报告）：

```bash
# 先启动服务，再另开一个终端
python scripts/smoke_e2e.py
```

---

## API 概览

> 📖 **完整接口文档（前端对接版）**：[`docs/apis/API接口文档.md`](docs/apis/API接口文档.md)
> —— 各接口的提交方式 / URL / 参数 / 响应 / 示例，以及 SSE 与错误处理的实现代码。
> 本节只是速查表。
>
> ⚠️ 该文档目前只覆盖 HR 侧接口；候选人侧（`/api/candidate/*`、`/api/practice/*`）
> 尚未补入，以 `GET /api/openapi.json` 为准。

统一前缀 `/api`，除登录与候选人自助注册外均需 `Authorization: Bearer <token>`。

### 认证与用户

| 方法 | 路径 | 权限 |
|---|---|---|
| POST | `/auth/login` | 公开 |
| POST | `/auth/register` | 公开（候选人自助注册，可用 `CANDIDATE_SELF_REGISTER` 关闭） |
| GET | `/auth/me` | 登录 |
| POST / GET | `/users` | admin |
| PATCH | `/users/{id}` | admin |

### 岗位 / 题库

| 方法 | 路径 |
|---|---|
| POST / GET | `/positions` |
| GET / PUT / DELETE | `/positions/{id}` |
| POST / GET | `/questions` |
| GET / PUT / DELETE | `/questions/{id}` |

`GET /questions` 支持 `position_id` / `category` / `dimension` / `source` / `keyword` 筛选（AND 关系）。

### 面试

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/interviews` | 创建（含**同步出题**） |
| GET | `/interviews` | 列表（按数据隔离过滤） |
| GET | `/interviews/{id}` | 详情（含题目与回答） |
| PATCH | `/interviews/{id}` | 仅更新候选人信息 |
| POST | `/interviews/{id}/answers` | 保存 / 更新某题回答 |
| POST | `/interviews/{id}/complete` | 标记完成 |
| POST | `/interviews/{id}/rollback` | 回退到进行中 |

### 评估

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/interviews/{id}/evaluate` | 触发评估（**202**，幂等），返回 SSE 地址 |
| GET | `/interviews/{id}/evaluation/stream` | SSE 事件流 |
| GET | `/interviews/{id}/report` | 完整报告（逐题 + 多维 + 汇总） |

**SSE 事件契约**：

```
question（按 seq 升序）→ dimension → report → done 或 error
```

`done` 与 `error` 互斥且必居其一；每 15 秒有 `: ping` 心跳。

> **前端注意**：SSE 需要 `Authorization` 头，因此**不能用浏览器原生 `EventSource`**
> （它无法设置自定义请求头）。请用 `fetch` + `ReadableStream` 手动解析，
> 详见 [frontend 计划书 §4.3](docs/superpowers/specs/2026-09-15-module-07-frontend-plan.md)。

---

## 错误响应格式

所有错误响应固定为三字段：

```json
{ "code": "BUSINESS_ERROR", "message": "该岗位已被题库或面试引用，无法删除", "detail": null }
```

| code | HTTP | 场景 |
|---|---|---|
| `VALIDATION_ERROR` | 400 | 参数非法（**不是 422**） |
| `UNAUTHORIZED` | 401 | 未认证 / 凭据错误 |
| `INVALID_TOKEN` | 401 | token 过期或篡改 |
| `FORBIDDEN` | 403 | 角色不足 / 访问他人数据 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `BUSINESS_ERROR` | 409 | 业务规则冲突 / 非法状态迁移 |
| `INTERNAL_ERROR` | 500 | 未预期异常（**不泄漏堆栈**） |
| `AI_PROVIDER_ERROR` | 502 | AI 调用失败（重试后仍失败） |

---

## 项目结构

```
backend/
  app/
    main.py              # FastAPI 装配：CORS、异常处理器、路由注册、健康检查
    core/                # 配置、数据库、安全原语、异常体系、依赖注入
    auth/                # 用户、登录、JWT、角色、数据隔离基座
    position/            # 岗位与评估维度
    question/            # 题库
    ai/                  # AI Provider 抽象 + Mock + 真实实现 + 工厂
    interview/           # 面试、出题组装、回答记录、状态机、作答邀请
    evaluation/          # 流式评估、报告、候选人脱敏反馈
    practice/            # 刷题：练习会话、逐题判分、错题本、统计
  alembic/               # 数据库迁移
  scripts/
    seed_admin.py        # 创建初始管理员（幂等）
    smoke_e2e.py         # 端到端冒烟
  tests/                 # 771 项测试

frontend/
  index.html             # Vite 入口（ES 模块 —— 只能经 http:// 访问，不能双击）
  vite.config.js         # /api 代理 + Vitest 配置
  src/
    api.js               # HTTP 封装（JWT 注入 / 统一错误 / 401 / 204）
    sse.js               # SSE 客户端 + 纯函数解析器
    router.js            # hash 路由 + 导航守卫
    components/          # shell（外壳 + 状态轨）· radar · modal · toast
    pages/               # 7 个页面
    styles/              # tokens / base / components / pages
  dist/                  # 构建产物，由后端托管（gitignore）
  __tests__/             # 25 项单测：SSE 分帧解析 · 雷达图几何

一键启动.bat             # 双击这个 —— 构建前端 → 查库 → 起后端 → 开浏览器
scripts/start.ps1        # 上面那个 bat 的实际逻辑
如何打开项目.md           # 分步说明与排查表
```

### 面试状态机

```
draft → ongoing → completed → evaluating → evaluated
                     ↑            ↓            ↓
                     └────────────┴────────────┘
                        （回退 / 重新评估）
```

| from | to | 触发 |
|---|---|---|
| `draft` | `ongoing` | 出题组装完成（事务内） |
| `ongoing` | `completed` | `POST /complete` |
| `completed` | `ongoing` | `POST /rollback` |
| `completed` | `evaluating` | 触发评估 |
| `evaluating` | `evaluated` | 评估成功 |
| `evaluating` | `completed` | **评估失败回退** |
| `evaluated` | `evaluating` | 重新评估 |
| `evaluated` | `ongoing` | `POST /rollback` |

**表中未列出的迁移一律返回 409**，并在 `detail` 中给出 `{from, to}`。

### 作答邀请状态机（与面试状态解耦）

```
生成 → pending ─┬─ 候选人凭码接受 → accepted
                ├─ HR 撤销         → revoked
                └─ 超过 expires_at → expired（读取时派生，不落库）
```

| 迁移 | 触发 | 说明 |
|---|---|---|
| `pending` → `accepted` | 候选人接受 | 绑定 `candidate_user_id` |
| `pending` → `revoked` | HR 撤销 | — |
| `pending` → `expired` | `expires_at < now` | **派生**，库中 status 仍为 `pending` |
| `accepted` → `revoked` | HR 撤销 | 立即切断该候选人的访问，但 `accepted_at` / `candidate_user_id` 保留 |

> **候选人作答不进入面试状态机**：状态机描述的是 HR 侧推进流程。候选人交卷只写
> `answer.submitted_at`，面试是否完成仍由 HR 决定。

---

## 已知限制（MVP 边界）

| 限制 | 说明 |
|---|---|
| **单进程部署** | SSE 运行注册表与刷题限流计数都是进程内的，必须 `--workers 1` |
| **前端构建需手动触发** | `npm run build` 后由后端托管；未接入 CI |
| **无 JWT 刷新** | 过期后需重新登录（有效期默认 12 小时） |
| **评估不留历史版本** | 同一面试只保留最近一次评估结果 |
| **作答不留历史版本** | HR 覆盖候选人作答时只保留最新内容（`source` 仍记录最初来源） |
| **候选人不能撤回交卷** | 需补答时由 HR 回退到 `ongoing` 后重新发邀请 |
| **邀请码明文存储** | HR 需在系统内复制（PRD §1.3）；缓解手段是长码 + 短有效期 + 一次性 + 可撤销 |
| **列表不分页** | 内部系统数据量小 |
| **仅 PC 端** | 不做移动端适配 |

V1.1 规划：PDF 报告导出、报告分享。
