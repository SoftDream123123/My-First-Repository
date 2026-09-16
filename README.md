# AI 智能面试助手

面向 HR / 面试官的 Web 应用。AI 辅助真人面试官完成「**出题 → 记录 → 评估 → 报告**」闭环。

- **设计文档**：[docs/superpowers/mvp/](docs/superpowers/mvp/)（PRD）
- **模块计划书**：[docs/superpowers/specs/](docs/superpowers/specs/)（7 个模块的设计与验收标准）

> **当前实现范围**：**后端**（FastAPI + MySQL）。前端（Vite + 原生 JS）尚未实现，
> 详见 [docs/superpowers/specs/2026-09-15-module-07-frontend-plan.md](docs/superpowers/specs/2026-09-15-module-07-frontend-plan.md)。

---

## 技术栈

| 项 | 选择 |
|---|---|
| 架构 | 前后端分离，后端纯 API（不渲染页面） |
| 后端 | Python 3.11+ / FastAPI |
| 数据库 | MySQL 8.0+ |
| 分层 | `router → service → repository → MySQL`，严格单向依赖 |
| 模块 | 七个独立 package：`core` / `auth` / `position` / `question` / `interview` / `evaluation` / `ai` |
| AI | 抽象 Provider 接口，`mock` 与 `openai` 可配置切换 |

---

## 前置要求

| 项 | 版本 |
|---|---|
| Python | 3.11+（本机验证于 3.13） |
| MySQL | 8.0+（本机验证于 9.7；JSON 列与 ENUM 需要 8.0+） |

---

## 后端启动

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

## 运行测试

```bash
cd backend
python -m pytest                       # 全部（344 项）
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

统一前缀 `/api`，除登录外均需 `Authorization: Bearer <token>`。

### 认证与用户

| 方法 | 路径 | 权限 |
|---|---|---|
| POST | `/auth/login` | 公开 |
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
    interview/           # 面试、出题组装、回答记录、状态机
    evaluation/          # 流式评估、报告
  alembic/               # 数据库迁移
  scripts/
    seed_admin.py        # 创建初始管理员（幂等）
    smoke_e2e.py         # 端到端冒烟
  tests/                 # 344 项测试
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

---

## 已知限制（MVP 边界）

| 限制 | 说明 |
|---|---|
| **单进程部署** | SSE 运行注册表是进程内的，必须 `--workers 1` |
| **无前端** | 本次仅实现后端；前端计划书已就绪（V1.1 交付） |
| **无 JWT 刷新** | 过期后需重新登录（有效期默认 12 小时） |
| **评估不留历史版本** | 同一面试只保留最近一次评估结果 |
| **列表不分页** | 内部系统数据量小 |
| **仅 PC 端** | 不做移动端适配 |

V1.1 规划：在线答题（候选人侧）、PDF 报告导出、报告分享。
