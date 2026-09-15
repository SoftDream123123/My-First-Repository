# frontend 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：frontend（HR 后台前端）
**所属目录**：`frontend/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§2（技术栈约束）、§3.1（前后端分离）、§4（各功能界面）、§5.3 ③（流式评估的前端侧）、§7（SSE 断连重连）
**前置依赖**：全部后端模块（core / auth / position / question / interview / evaluation）

---

## Global Constraints（全局约束，摘自 PRD）

- **前端使用原生 HTML + CSS + JavaScript + Vite 构建，无 UI 框架**（§2）
- **仅 PC 端，不考虑移动端响应式**（§2、§1.3）
- 前后端**分离**：后端纯 API，前端通过 **REST + SSE** 与后端交互（§3.1）
- **在线答题（候选人侧）属于 V1.1，不在 MVP**（§1.3）
- 统一错误响应格式 `{code, message, detail}` —— 前端据此统一展示错误（§7）
- **评估以 SSE 流式呈现**（§4.5、§5.3 ③）
- **SSE 断连后前端重连可继续拉取进度或查询最终结果**（§7）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §3.1 的「`/hr` 后台」）

PRD §3.1 定义前端为「`/hr` 后台（**登录、岗位、题库、面试、报告**）」。据此拆分为：

| 子职责 | 内容 | PRD |
|---|---|---|
| 认证界面 | 登录页、token 存取、登录态判断、401 自动登出 | §4.1、§3.1 |
| 岗位管理 | 岗位列表、创建、编辑、删除（含**评估维度编辑**） | §4.2 |
| 题库管理 | 题目列表（多维筛选）、创建、编辑、删除 | §4.3 |
| 面试管理 | 面试列表、创建面试（**同步出题**）、详情、逐题录入回答、完成 / 回退 | §4.4、§5.3 ①② |
| **评估与报告** | 触发评估、**SSE 实时进度**、雷达图、完整报告渲染 | §4.5、§5.3 ③ |
| 用户管理 | admin 创建 / 列出 / 修改 HR 账号 | §4.1、§8 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **候选人侧答题页** | PRD §1.3 明确列为 V1.1 |
| **任何 UI 框架 / 组件库** | PRD §2 明确「无 UI 框架」 |
| **图表库** | 雷达图用 Canvas 2D 手写（不引入 ECharts 等数百 KB 依赖） |
| **前端权威权限校验** | 前端只隐藏入口，权限由后端强制（PRD §4.1） |
| **状态管理库** | 页面级数据获取 + 重新渲染即可 |
| **移动端适配 / 响应式断点** | PRD §2 明确「仅 PC 端」 |
| **国际化** | 界面文案为简体中文，硬编码 |
| **PDF 导出 / 报告分享** | PRD §1.3 / §11 明确列为 V1.1 |

### 1.3 依赖方向

```
frontend ──→ 后端 REST API（/api/*）
frontend ──→ 后端 SSE 端点（/api/interviews/{id}/evaluation/stream，经 fetch + ReadableStream）

模块内部：
  pages/* ──→ components/*（渲染复用）
  pages/* ──→ api.js（HTTP 与错误处理）
  pages/* ──→ auth.js（登录态）
  pages/* ──→ router.js（跳转）
  evaluation 页 ──→ sse.js（流式）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `frontend/package.json` | 依赖（仅 vite 与 vitest）与脚本 |
| `frontend/vite.config.js` | Vite 配置 + `/api` 代理到后端 |
| `frontend/index.html` | 唯一 HTML 入口，含 `#app` 挂载点 |
| `frontend/src/main.js` | 应用启动：初始化路由、注入 401 处理器、挂载默认页 |
| `frontend/src/api.js` | `fetch` 封装：注入 JWT、统一错误、401 处理 |
| `frontend/src/sse.js` | **SSE 客户端**：`fetch` + `ReadableStream` 手动解析（见 §4.3） |
| `frontend/src/auth.js` | token 存取、登录态判断、当前用户信息 |
| `frontend/src/router.js` | hash 路由：注册表、参数解析、导航守卫 |
| `frontend/src/pages/login.js` | 登录页 |
| `frontend/src/pages/interviews.js` | 面试列表 + 创建弹窗 |
| `frontend/src/pages/interview-detail.js` | 面试详情：题目、录入回答、完成 / 回退 |
| `frontend/src/pages/evaluation.js` | 评估页：SSE 进度、雷达图、报告 |
| `frontend/src/pages/positions.js` | 岗位管理 |
| `frontend/src/pages/questions.js` | 题库管理 |
| `frontend/src/pages/users.js` | 用户管理（admin） |
| `frontend/src/components/sidebar.js` | 侧边导航（按角色过滤入口） |
| `frontend/src/components/table.js` | 表格渲染与空态 |
| `frontend/src/components/modal.js` | 弹窗（表单容器） |
| `frontend/src/components/radar.js` | Canvas 雷达图 |
| `frontend/src/components/toast.js` | 成功 / 失败消息提示 |
| `frontend/src/styles/main.css` | 全部样式（CSS 变量主题） |

**测试文件**：`frontend/src/__tests__/sse.test.js`、`frontend/src/__tests__/radar.test.js`

---

## 3. 页面与路由设计

### 3.1 路由表

| hash 路由 | 页面模块 | 权限 | PRD |
|---|---|---|---|
| `#/login` | `login.js` | 公开 | §4.1 |
| `#/interviews` | `interviews.js` | 登录 | §4.4 |
| `#/interviews/:id` | `interview-detail.js` | 登录 | §4.4 |
| `#/interviews/:id/evaluation` | `evaluation.js` | 登录 | §4.5 |
| `#/positions` | `positions.js` | 登录 | §4.2 |
| `#/questions` | `questions.js` | 登录 | §4.3 |
| `#/users` | `users.js` | **admin** | §4.1、§8 |

- **默认落地页**：`#/interviews`
- **未知路由** → 重定向到 `#/interviews`

### 3.2 页面模块契约

每个 page 模块**必须**导出：

| 导出 | 签名 | 说明 |
|---|---|---|
| `render` | `(container: HTMLElement, params: object) => void \| Promise<void>` | 渲染页面到容器 |
| `destroy` | `() => void` | **可选**。离开页面时清理（关闭 SSE 连接、移除全局监听、清定时器） |

> **`destroy` 是本设计的关键约定**：评估页持有长连接，若不清理会导致**连接泄漏**、后台仍在推送、甚至重复渲染。路由器在切换页面前**必须**调用上一页的 `destroy`（若存在）。

### 3.3 导航守卫

```
router.beforeEach：
  1. 若 hash == '#/login'
       已登录 → 跳 '#/interviews'
       否则放行
  2. 若未登录（无 token）
       → 跳 '#/login'
  3. 若目标页要求 admin 且当前用户非 admin（PRD §4.1）
       → 跳 '#/interviews' + toast「无权限访问该页面」
  4. 放行
```

> token 过期由 `api.js` 在收到 401 时统一处理（§4.1），守卫只做「有没有 token」的快速判断。

### 3.4 布局（PRD §2「仅 PC 端」）

```
┌────────────────────────────────────────────┐
│  顶栏：应用名 · 当前用户 · 退出             │
├──────────┬─────────────────────────────────┤
│          │                                 │
│  侧边栏   │        内容区（页面渲染于此）     │
│  导航     │                                 │
│          │                                 │
└──────────┴─────────────────────────────────┘
```

- 侧边栏宽度固定（如 200px），内容区自适应。
- 侧边栏入口按角色过滤：`users.js` 入口仅 admin 可见（**仅体验优化，权限由后端强制**）。
- 登录页**不套用**该布局。

---

## 4. 核心工具设计

### 4.1 `api.js` —— HTTP 封装

| 导出 | 签名 | 说明 |
|---|---|---|
| `request` | `(method: string, path: string, body?: object) => Promise<any>` | 统一请求入口 |
| `get` / `post` / `put` / `patch` / `del` | 语义化快捷方法 | 内部调 `request` |
| `ApiError` | `class`，字段 `code: string`、`message: string`、`detail: object \| null`、`status: number` | 业务错误 |
| `setUnauthorizedHandler` | `(fn: () => void) => void` | 注册 401 回调（由 `main.js` 注入「清 token + 跳登录」） |

**行为约定**

| 情况 | 行为 |
|---|---|
| 有 token | 自动注入 `Authorization: Bearer <token>`（PRD §8） |
| 请求体 | 自动 `JSON.stringify` 并设 `Content-Type: application/json` |
| 2xx | 返回解析后的 JSON；**204 返回 `null`**（删除接口，见 position / question 模块的 204 约定） |
| 非 2xx 且响应体是三字段格式 | 抛 `ApiError`，字段取自响应体（**PRD §7**） |
| 非 2xx 且响应体不是预期格式 | 抛 `ApiError`，`code = "UNKNOWN"`，`message` 用 HTTP 状态文案兜底 |
| **401** | 清除 token → 调用 `setUnauthorizedHandler` 注册的回调 → 同时抛出 `ApiError` |
| 网络错误 | 抛 `ApiError`，`code = "NETWORK_ERROR"`，`message`「网络连接失败，请检查后端服务」 |

> **统一错误展示**：页面只需 `try/catch` 并调 `toast.error(err.message)`。错误文案来自后端的 `message` 字段，**前端不重新编造**（PRD §7 要求统一响应格式的目的正在于此）。

### 4.2 `auth.js` —— 登录态

| 导出 | 签名 | 说明 |
|---|---|---|
| `saveToken` | `(token: string, user: object) => void` | 写入存储 |
| `getToken` | `() => string \| null` | — |
| `getUser` | `() => object \| null` | 缓存的用户信息（`id` / `username` / `role`） |
| `isLoggedIn` | `() => boolean` | 有 token 即视为已登录（过期由 401 兜底） |
| `isAdmin` | `() => boolean` | `getUser()?.role === 'admin'`（PRD §4.1） |
| `logout` | `() => void` | 清除存储并跳登录页 |
| `refreshUser` | `() => Promise<void>` | 调 `GET /api/auth/me` 刷新用户信息（页面加载时调用，保证角色是最新的） |

**存储方案与权衡**

| 方案 | 决策 |
|---|---|
| **`localStorage`（本设计采用）** | 刷新与跨标签页保持登录态，实现最简单 |
| `sessionStorage` | 关标签即登出，多标签协作体验差 |
| `httpOnly` Cookie | 安全性最好（JS 读不到，天然免疫 XSS 窃取），但需后端改为 Cookie 鉴权并处理 CSRF |

**已声明的风险**：`localStorage` 中的 token 可被 XSS 读取。MVP 为内网 HR 系统、且界面**无用户生成的 HTML 内容注入点**（题干、回答均以文本节点渲染，不用 `innerHTML`），风险可接受。如未来面向公网，应迁移到 `httpOnly` Cookie + CSRF 防护。

### 4.3 `sse.js` —— SSE 客户端（**关键设计**）

**为何不能用 `EventSource`**

浏览器的 `EventSource` **无法设置自定义请求头**，而本项目的鉴权完全依赖 `Authorization: Bearer`（PRD §8）。若把 JWT 放进 query string，令牌会进入服务器访问日志、反向代理日志与浏览器历史记录——这是可以避免的泄露面。因此必须用 `fetch` + `ReadableStream` 自行解析 SSE 协议。

| 导出 | 签名 | 说明 |
|---|---|---|
| `sseConnect` | `(path: string, handlers: SseHandlers) => SseConnection` | 建立连接 |
| `SseHandlers` | `{ onEvent?: (name: string, data: object) => void, onError?: (err: Error) => void, onClose?: () => void }` | 回调集合 |
| `SseConnection` | `{ close: () => void, isOpen: () => boolean }` | 连接句柄 |

**实现要点**

| 要点 | 说明 |
|---|---|
| 请求 | `fetch(path, { headers: { Authorization, Accept: 'text/event-stream' }, signal })` |
| 中断 | 用 `AbortController`，`close()` 即 `abort()` |
| 读取 | `response.body.getReader()` + `TextDecoder('utf-8')` 流式解码 |
| 分帧 | 按**空行对**（`\n\n` 或 `\r\n\r\n`）切分事件块 |
| **跨块缓冲** | **必须保留未闭合的尾部**，与下一个 chunk 拼接后再分帧（**这是最容易写错的地方**，见 §8.2 单测） |
| 字段解析 | `event:` 取事件名（缺省 `message`）、`data:` 拼接多行、**忽略 `:` 开头的注释行**（心跳） |
| 结束 | 流结束时调用 `onClose` |
| 致命错误 | 非 2xx 响应、网络中断 → 调 `onError`，**不自动重连**（重连由页面显式控制，避免无限重试风暴） |
| 认证失败 | 响应 401 → 交回 `api.js` 的统一 401 处理（清 token 跳登录） |

> 本工具是 **evaluation §4.3 对前端提出的强约束**的落地实现。

### 4.4 `radar.js` —— 雷达图（PRD §4.5「用于雷达图」）

| 导出 | 签名 | 说明 |
|---|---|---|
| `drawRadar` | `(canvas: HTMLCanvasElement, data: {dimension: string, score: number}[], options?: object) => void` | 绘制 |
| `computePoints` | `(values: number[], center: {x, y}, radius: number, maxValue: number) => {x, y}[]` | **纯函数**，输出顶点坐标（供单测） |

**绘制要素**

| 要素 | 设计 |
|---|---|
| 坐标映射 | 顶点角度均分：第 `i` 个维度角度为 `-90° + i * 360°/N`（**从正上方开始**） |
| 半径映射 | `r = radius * (score / maxValue)`，`maxValue` **固定为 10**（与后端 0–10 分制一致，PRD §4.5） |
| 网格 | 4 圈同心多边形（2.5 / 5 / 7.5 / 10 分），浅灰描边 |
| 轴线 | 从中心到每个顶点的直线 |
| 数据多边形 | 半透明填充 + 实线描边 |
| 顶点 | 每个顶点画圆点；旁标分数（**保留 1 位小数**，PRD §4.5） |
| 维度标签 | 在顶点外侧沿轴向偏移绘制；根据角度调整 `textAlign` 避免出界 |
| 尺寸 | 画布正方形，`radius = min(w, h) / 2 - padding`，`padding` 预留标签空间（如 60px） |
| **边界** | `N < 3` → **不绘制**，改显示「维度不足，无法绘制雷达图」文本 |
| 高分屏 | 按 `devicePixelRatio` 缩放画布，避免模糊 |

> **不引入图表库**：雷达图几何简单，手写约 80 行且完全可控；引入 ECharts 等会带来数百 KB 依赖，与 PRD §2「原生 JS + 无 UI 框架」的约束相悖。

---

## 5. 各页面设计

### 5.1 登录页 `login.js`（PRD §4.1）

| 交互 | 行为 |
|---|---|
| 表单 | 用户名、密码；提交按钮；回车提交 |
| 提交 | `POST /api/auth/login` → `saveToken(token, user)` → 跳 `#/interviews` |
| 失败 | `toast.error(err.message)`（后端已统一为「用户名或密码错误」，见 auth §6） |
| 加载态 | 提交期间按钮禁用 + 文案「登录中…」 |

### 5.2 面试列表 `interviews.js`（默认落地页，PRD §4.4）

| 区块 | 内容 |
|---|---|
| 列表 | 调 `GET /api/interviews`；列：候选人、岗位、状态、题目数、已回答数、创建时间、操作 |
| 状态展示 | `ongoing` → 「进行中」、`completed` → 「已完成」、`evaluating` → 「评估中」、`evaluated` → 「已评估」（不同颜色标签，对应 PRD §5.1 的状态） |
| 操作 | 「查看」→ `#/interviews/:id`；`evaluated` 时额外显示「查看报告」 |
| 创建按钮 | 打开创建弹窗 |
| **空态** | 「暂无面试，点击右上角创建」 |

**创建弹窗**（PRD §4.4「选择岗位、填写候选人信息」）

| 字段 | 控件 | 约束 |
|---|---|---|
| 岗位 | 下拉选择（调 `GET /api/positions`） | 必填 |
| 候选人姓名 | 文本 | 必填，1–100 字符 |
| 候选人联系方式 | 文本 | 可选，0–200 字符 |

**提交行为（关键）**：`POST /api/interviews` 是**同步出题**（PRD §5.3 ①），可能耗时数秒。

| 项 | 设计 |
|---|---|
| 加载态 | 按钮禁用 + 文案「正在生成面试题…」，**弹窗不可关闭**，避免重复提交 |
| 成功 | 关闭弹窗 → 跳 `#/interviews/:id` |
| 失败（**502 `AI_PROVIDER_ERROR`**） | 弹窗保持打开，`toast.error('AI 出题失败，请稍后重试')`，按钮恢复可用（**后端已整体回滚，可安全重试**，见 interview §5.1） |
| 无可选岗位 | 岗位下拉为空时提示「请先创建岗位」并禁止提交 |

### 5.3 面试详情 `interview-detail.js`（PRD §4.4、§5.3 ②）

| 区块 | 内容 |
|---|---|
| 头部 | 候选人、岗位、状态标签、创建时间 |
| 操作区 | 按状态渲染（见下表） |
| 题目列表 | 逐题展示：序号、题干、**维度标签**、**来源标签**、回答输入框、保存状态 |

**操作区按钮矩阵**（与 interview §5.4.3 对齐）

| 状态 | 可用操作 |
|---|---|
| `ongoing` | 「标记完成」 |
| `completed` | 「回退到进行中」、「开始评估」 |
| `evaluating` | 「查看评估进度」（跳评估页） |
| `evaluated` | 「查看报告」、「回退到进行中」、「重新评估」 |

**回答录入**（PRD §5.3 ②「HR 逐题录入候选人回答，可随时编辑」）

| 项 | 设计 |
|---|---|
| 控件 | 每题一个多行文本框 |
| 保存 | **失焦自动保存** + 手动「保存」按钮；调 `POST /api/interviews/{id}/answers` |
| 保存状态 | 每题右上角显示「未修改 / 保存中… / 已保存 / 保存失败」 |
| 防抖 | 失焦保存即可，**不做输入防抖**（避免高频请求） |
| 非 `ongoing` 状态 | 文本框**只读**并提示「需先回退到进行中才能修改回答」 |
| 空回答 | 允许保存空串（表示候选人**未作答**，评估将按 0 分处理） |

> **不做未保存离开拦截**：MVP 采用显式保存按钮 + 失焦自动保存，已能覆盖主要场景；`beforeunload` 拦截会在路由切换时误触发，收益不抵复杂度。

### 5.4 评估页 `evaluation.js`（**最复杂页面**，PRD §4.5、§5.3 ③、§7）

**两个入口状态**

| 入口 | 行为 |
|---|---|
| 从「开始评估 / 重新评估」进入 | 调 `POST /api/interviews/{id}/evaluate` → 拿到 `stream_url` → 建立 SSE |
| 从「查看报告 / 查看评估进度」进入 | **直接**建立 SSE（不重复触发）。若已完成，服务端会合成完整事件序列推送（evaluation §5.5） |

> 页面**不区分**这两种情况：一律先建立 SSE，由服务端决定是「重放进行中的运行」「从库合成历史」还是「推 error」。这避免了前端与后端的状态判断分歧。

**实时进度渲染**

| 阶段 | 界面 |
|---|---|
| 连接中 | 「正在连接评估服务…」 |
| `question` 事件 | 题目列表**逐一出现**评分与评语，当前题高亮；顶部进度条 `index / total` |
| `dimension` 事件 | 雷达图**逐维度「生长」**（每次收到事件重绘，未到达的维度按 0 处理并灰显） |
| `report` 事件 | 渲染总分、结论、优点、待改进（PRD §4.5 的四项输出） |
| `done` 事件 | 隐藏进度条，展示完整报告 + 「查看面试详情」「返回列表」按钮 |
| `error` 事件 | 显示错误文案（取 `data.message`）+ 「重新评估」按钮；**提示后端已回滚到 `completed`，可安全重试**（PRD §7） |

**断线处理（PRD §7）**

| 情况 | 行为 |
|---|---|
| `onError`（网络中断） | 显示「连接已断开」+ 「重新连接」按钮（**不自动重连**，避免重试风暴） |
| 用户点「重新连接」 | 再次 `sseConnect` 同一 `stream_url`；服务端会**重放已推事件**，界面从头重建（PRD §7「重连后可继续拉取进度」） |
| 离开页面 | `destroy()` 中调 `connection.close()`（**必须**） |

**报告区结构**（对应 PRD §4.5 的四项 + 明细）

| 区块 | 内容 |
|---|---|
| 总分 | `overall_score`，大字展示（保留 1 位小数） |
| 结论 | `conclusion` 段落 |
| **雷达图** | 由 `dimension_scores` 绘制（PRD §4.5「用于雷达图」） |
| 维度明细 | 每个维度：名称、分数、评语 |
| 优势 / 待改进 | `strengths` / `weaknesses` 列表 |
| 逐题明细 | `question_scores`：序号、题干、回答、分数、评语（**按 `seq` 升序**） |

> **`done` 后不重新拉取报告**：SSE 的 `report` 事件 + 逐题/维度事件已含全部数据，重新调 `GET /report` 会增加一次请求且可能因时序产生闪烁。仅在**直接进入已完成报告的页面**时（无 SSE 数据）才可能走 `GET /report` 兜底。

### 5.5 岗位管理 `positions.js`（PRD §4.2）

| 项 | 设计 |
|---|---|
| 列表 | `GET /api/positions`；列：岗位名、JD 摘要、维度数、创建时间、操作 |
| 关键字搜索 | 输入框 → `GET /api/positions?keyword=` |
| 创建 / 编辑 | 弹窗表单：名称（必填）、JD（多行文本，必填）、**评估维度** |
| **维度编辑器** | 动态列表：输入框 + 「添加」按钮；每项右侧「删除」；前端即时校验（**非空、≤10 项、去重、单项 ≤50 字符**，与 position §3.3 对齐），错误在字段下方红字提示 |
| 删除 | 二次确认弹窗；后端返回 **409** 时展示「该岗位已被题库或面试引用，无法删除」（PRD §4.2） |
| 详情 | 展开行显示完整 JD |

### 5.6 题库管理 `questions.js`（PRD §4.3）

| 项 | 设计 |
|---|---|
| 列表 | `GET /api/questions`；列：题干摘要、岗位、分类、维度、难度、**来源**、标签、操作 |
| **筛选栏** | 岗位下拉、分类输入、**维度输入**、来源下拉（全部/手工/AI）、关键字输入；任一变化即重新请求（**AND 关系**）——对应 PRD §4.3「按岗位 / 分类 / 维度筛选」 |
| 创建 / 编辑 | 弹窗表单：岗位（下拉）、分类、维度、题干（多行）、难度（下拉）、标签（动态列表） |
| **维度联动** | 选择岗位后，**维度字段改为下拉**，选项为该岗位的 `evaluation_dimensions`（**避免提交必然失败的维度**，对应 question §3.3 的校验） |
| 来源标识 | `bank` → 「手工」、`ai` → 「AI」（不同颜色标签）——PRD §5.2 的 `source` 字段 |
| 删除 | 二次确认；409 时提示「该题目已被面试引用，无法删除」 |

### 5.7 用户管理 `users.js`（admin，PRD §4.1、§8）

| 项 | 设计 |
|---|---|
| 入口 | 侧边栏仅 admin 可见 |
| 列表 | `GET /api/users`；列：用户名、角色、状态、创建时间、操作 |
| 创建 | 弹窗：用户名、密码（**≥8 字符**）、角色（下拉）——对应 PRD §4.1「admin 可创建用户，并可指定角色」 |
| 修改 | 行内改角色 / 启用禁用；调 `PATCH /api/users/{id}`（PRD §8） |
| 自身保护 | 当前登录用户所在行的操作按钮**置灰**（后端也会拒绝，前端提前避免误操作） |
| 错误 | 409 时展示后端 message（如「用户名已存在」） |

---

## 6. 样式设计（`main.css`）

| 项 | 设计 |
|---|---|
| 主题变量 | `:root` 定义主色、文字色、边框色、背景色、危险色、成功色、警告色 |
| 布局 | 顶栏固定高度、侧边栏固定宽度、内容区 `flex: 1` + 内边距 |
| 表格 | 统一 `.table` 类：表头浅底、行 hover 高亮、单元格垂直居中、超长文本省略号 + `title` 提示 |
| 状态标签 | `.tag` 基类 + `.tag--ongoing` / `.tag--completed` / `.tag--evaluating` / `.tag--evaluated` 等修饰类（对应 PRD §5.1 的五个状态） |
| 弹窗 | 遮罩层 + 居中面板；`Esc` 关闭；**提交中禁用关闭** |
| 消息 | `toast` 固定右上角，自动消失（成功 3 秒、失败 5 秒） |
| 加载 | 统一 `.spinner` 与 `.loading-block` 占位 |
| 空态 | 统一 `.empty` 提示 |
| **视口** | 按 `min-width: 1280px` 设计；**不写媒体查询**（PRD §2 仅 PC 端） |
| 字体 | 系统字体栈（`-apple-system, "Segoe UI", "Microsoft YaHei", sans-serif`） |
| **XSS 防护** | 所有来自后端的数据（题干、回答、评语、结论）**一律用 `textContent` 渲染，禁止 `innerHTML`** |

---

## 7. Vite 配置（PRD §2「Vite 构建」）

| 项 | 设计 |
|---|---|
| 开发端口 | 5173（Vite 默认） |
| **代理** | `/api` → `http://localhost:8000` |
| 入口 | `index.html` |
| 构建输出 | `dist/` |
| 脚本 | `dev`（vite）、`build`（vite build）、`preview`（vite preview）、`test`（vitest run） |

**为何用代理而非跨域**：开发期通过 Vite 代理把 `/api` 转发到后端，前端代码中**一律使用相对路径 `/api/...`**，无需处理 CORS，构建产物部署到同域后也无需改动。后端 CORS 配置（`CORS_ORIGINS`，见 core §3）仍保留，作为不经代理时的兜底。

---

## 8. 测试设计

### 8.1 测试范围声明

前端 MVP **不引入 DOM 测试框架**（jsdom / Testing Library）——页面逻辑以「调 API + 重渲染」为主，DOM 测试的投入产出比低，改为**手工联调清单**（§8.4）覆盖。

仅对两个**几何 / 协议类的纯函数模块**做单测——它们手写且易错，是缺陷高发区。工具：**Vitest**（与 Vite 同源，零额外配置）。

> **对 PRD 的补充说明**：PRD §10 的测试策略只覆盖后端三层。本设计增加前端 Vitest 与两个测试文件，理由：SSE 分帧与雷达图坐标是**无界面反馈的纯逻辑**，出错时表现为「进度条卡住」或「图形画歪」，靠手工联调定位成本高。**若希望进一步压缩 MVP 范围，可裁剪 Task 7.9 / 7.10 中的单测部分，其余任务不受影响。**

### 8.2 `sse.test.js`（SSE 解析）

> 测试目标是把「字节流 → 事件」的解析逻辑抽为**纯函数**（`parseChunk` / `parseEventBlock`），使测试无需真实的 `ReadableStream`。

| 测试 | 断言 |
|---|---|
| `test_parse_single_event` | `event: question\ndata: {"a":1}\n\n` → 1 个事件，名 `question`，data 解析正确 |
| `test_parse_multiple_events_one_chunk` | 一个 chunk 含 2 个事件 → 解析出 2 个 |
| **`test_split_across_chunks`** | 事件被切成两个 chunk → **拼接后**正确解析（覆盖跨块缓冲） |
| **`test_incomplete_tail_buffered`** | chunk 结尾不完整 → 不产出事件，尾部被保留 |
| `test_data_without_event_name` | 只有 `data:` 行 → 事件名缺省为 `message` |
| `test_multiline_data_joined` | 多个 `data:` 行 → 按换行拼接后解析 |
| `test_comment_lines_ignored` | 以 `:` 开头的行（**心跳**）→ 不产出事件 |
| `test_crlf_line_endings` | `\r\n\r\n` 分帧同样正确 |
| `test_malformed_json_does_not_throw` | `data: not-json` → 不抛异常，跳过或按原文处理 |
| `test_empty_chunk_ignored` | 空 chunk → 无事件产出 |

### 8.3 `radar.test.js`（雷达图几何）

| 测试 | 断言 |
|---|---|
| `test_first_vertex_at_top` | `N=4`、满分时第一个顶点在**正上方**（`x == center.x`，`y < center.y`） |
| `test_vertices_evenly_spaced` | `N=4` → 相邻顶点角度差为 90° |
| `test_radius_proportional_to_score` | 分数 5 与 10 时顶点到中心距离比约为 **1:2** |
| `test_zero_score_at_center` | 分数 0 → 顶点与中心重合 |
| `test_max_value_is_ten` | 满分 10 时顶点落在 `radius` 处（与后端 0–10 分制对齐，PRD §4.5） |
| `test_n_less_than_three` | `N=2` → `computePoints` 返回空数组（由调用方显示降级文案） |

### 8.4 手工联调清单（覆盖主要路径）

**准备**：`PROVIDER_NAME=mock`（PRD §6）、admin 账号、另一个 hr 账号。

| # | 步骤 | 预期 | PRD |
|---|---|---|---|
| 1 | 未登录访问任意 hash | 跳到 `#/login` | §8 |
| 2 | 错误密码登录 | 提示「用户名或密码错误」，停留登录页 | §4.1 |
| 3 | 正确登录 | 跳 `#/interviews` | §4.1 |
| 4 | 岗位管理：建岗位（含 4 个维度） | 列表出现该岗位 | §4.2 |
| 5 | 岗位维度校验：提交空维度 / 11 个维度 / 重复维度 | 字段下方红字提示，无法提交 | §4.2 |
| 6 | 题库管理：为岗位建 3 道题 | 列表出现，来源标签为「手工」 | §4.3 |
| 7 | 题库筛选：按岗位 / 维度 / 来源筛选 | 结果符合预期 | §4.3 |
| 8 | 创建面试（选该岗位） | 出题中显示加载态；完成后跳详情页，题目列表共 **8 题（3 手工 + 5 AI）** | §5.3 ① |
| 9 | 检查题库 | 新增 5 道来源为「AI」的题目 | §5.2 |
| 10 | 详情页录回答：失焦保存 | 每题显示「已保存」 | §5.3 ② |
| 11 | 未答完即点「标记完成」 | 允许（PRD 未要求答完）；状态变「已完成」 | §5.1 |
| 12 | 非「进行中」状态下编辑回答 | 文本框只读 + 提示 | §5.1 |
| 13 | 「回退到进行中」→ 补充回答 → 再「标记完成」 | 状态正确流转 | §5.1 |
| 14 | 「开始评估」 | 跳评估页；逐题分数**逐条**出现；雷达图逐维度生长；最后出报告与总分 | §5.3 ③ |
| 15 | 评估完成后刷新页面 | 重新连接后**仍能完整看到进度与报告** | §7 |
| 16 | 评估中途手动断网再恢复 | 显示「连接已断开」+「重新连接」；重连后**从头重放并继续** | §7 |
| 17 | 「重新评估」 | 进度重新走一遍；报告 `updated_at` 更新；逐题条数**不翻倍** | §5.1 |
| 18 | 「查看报告」入口 | **不重复触发评估**，直接看到完整报告 | §4.5 |
| 19 | 删除被面试引用的岗位 | 提示「该岗位已被题库或面试引用，无法删除」 | §4.2 |
| 20 | 删除被面试引用的题目 | 提示「该题目已被面试引用，无法删除」 | §4.3 |
| 21 | 用 hr 账号登录 | 侧边栏**无**「用户管理」入口；手动输入 `#/users` 被拦回 `#/interviews` | §4.1 |
| 22 | hr 账号看面试列表 | **只见自己创建的**面试 | §4.1、§4.4 |
| 23 | hr 账号直接请求他人面试详情（手工改 URL 的 id） | 提示无权限（后端 403） | §4.1 |
| 24 | admin 登录 | 可见「用户管理」，可创建 hr 账号；自己那行操作按钮置灰 | §4.1 |
| 25 | 点击「退出」 | 清 token 并回登录页 | §4.1 |
| 26 | 手工把 localStorage 的 token 改成非法值后请求 | 收到 401 → **自动清 token 并跳登录页** | §7 |
| 27 | 关闭后端后操作 | 提示「网络连接失败，请检查后端服务」 | §7 |
| 28 | 视口缩到 1280px 以下 | 布局不塌陷（**不要求响应式**，但不能错位到不可用） | §2 |

---

## 9. 任务分解（步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 7.1：工程初始化与登录

- [ ] 建 `frontend/`，用 Vite 原生模板初始化（`package.json`、`vite.config.js`、`index.html`、`src/main.js`）
- [ ] 配置 `/api` 代理到 `http://localhost:8000`（§7）
- [ ] 实现 `api.js`（§4.1：JWT 注入、统一错误、401 回调、**204 处理**）
- [ ] 实现 `auth.js`（§4.2）
- [ ] 实现 `login.js` 页面
- [ ] 手工验证：错误密码 / 正确密码 / 网络错误三种情况的提示
- [ ] 提交

### Task 7.2：路由与整体布局

- [ ] 实现 `router.js`（hash 路由、参数解析、导航守卫 §3.3）
- [ ] 实现 `components/sidebar.js`（**按角色过滤入口**）与 `components/toast.js`
- [ ] 实现 `main.js`：注册路由、注入 401 处理器、启动
- [ ] 实现 `styles/main.css` 的布局与基础主题变量（§6）
- [ ] 手工验证：未登录跳转、未知路由重定向、侧边栏角色过滤
- [ ] 提交

### Task 7.3：通用组件

- [ ] 实现 `components/table.js`（渲染 + 空态 + 加载态）
- [ ] 实现 `components/modal.js`（打开 / 关闭 / Esc / **提交中禁用关闭** / 二次确认模式）
- [ ] 手工验证：弹窗交互与表格空态
- [ ] 提交

### Task 7.4：岗位管理页

- [ ] 实现 `pages/positions.js`：列表、关键字搜索、创建 / 编辑弹窗
- [ ] 实现**维度编辑器**（动态增删 + 前端校验 §5.5）
- [ ] 实现删除（二次确认 + **409 提示**）
- [ ] 手工验证：联调清单 #4、#5、#19
- [ ] 提交

### Task 7.5：题库管理页

- [ ] 实现 `pages/questions.js`：列表、**筛选栏**（§5.6）、创建 / 编辑弹窗
- [ ] 实现「**选岗位后维度变下拉**」的联动
- [ ] 实现来源标签与删除（含 409 提示）
- [ ] 手工验证：联调清单 #6、#7、#20
- [ ] 提交

### Task 7.6：用户管理页

- [ ] 实现 `pages/users.js`：列表、创建、改角色、启用禁用、**自身行禁用操作**
- [ ] 手工验证：联调清单 #21、#24
- [ ] 提交

### Task 7.7：面试列表与创建

- [ ] 实现 `pages/interviews.js`：列表、状态标签、创建弹窗
- [ ] 实现**同步出题的加载态**与 **502 失败提示**（§5.2）
- [ ] 手工验证：联调清单 #8、#9、#22、#23
- [ ] 提交

### Task 7.8：面试详情与回答录入

- [ ] 实现 `pages/interview-detail.js`：头部、操作区按钮矩阵（§5.3）、题目列表
- [ ] 实现回答录入（**失焦保存** + 手动保存 + 每题保存状态 + 非 ongoing 只读）
- [ ] 实现「标记完成」「回退到进行中」与跳转评估页
- [ ] 手工验证：联调清单 #10–#13
- [ ] 提交

### Task 7.9：SSE 客户端与单测

- [ ] 把解析逻辑抽为**纯函数**（`parseChunk` / `parseEventBlock`）
- [ ] 实现 `sse.js` 的 `sseConnect`（§4.3：AbortController、流式解码、**跨块缓冲**、心跳忽略、不自动重连）
- [ ] 写 §8.2 全部单测（Vitest）
- [ ] 运行 `npm test`，全部通过
- [ ] 提交

### Task 7.10：雷达图与单测

- [ ] 实现 `radar.js` 的 `computePoints`（纯函数）与 `drawRadar`（§4.4）
- [ ] 实现高分屏缩放与维度标签边界处理
- [ ] 写 §8.3 全部单测（Vitest）
- [ ] 运行 `npm test`，全部通过
- [ ] 提交

### Task 7.11：评估页

- [ ] 实现 `pages/evaluation.js`：SSE 连接、三阶段实时渲染、报告区（§5.4）
- [ ] 实现断线提示与「重新连接」（**PRD §7**）
- [ ] 实现 `destroy()` 关闭连接并在路由器中确保被调用
- [ ] 手工验证：联调清单 #14–#18
- [ ] 提交

### Task 7.12：端到端手工联调

- [ ] 按 §8.4 清单**逐条**走查（admin 与 hr 两个账号）
- [ ] 修复发现的问题
- [ ] 运行 `npm test`，确认单测未回归
- [ ] 提交

---

## 10. 验收标准

- [ ] **无 UI 框架、无图表库**（PRD §2）
- [ ] 未登录访问任何页面均跳转登录页；登录成功后落地 `#/interviews`
- [ ] 登录失败展示后端返回的 `message`，**不自行编造文案**（PRD §7）
- [ ] 收到 401 自动清 token 并跳登录页（PRD §9）
- [ ] 网络故障展示「网络连接失败，请检查后端服务」
- [ ] 侧边栏按角色过滤：非 admin 无「用户管理」；手工访问 `#/users` 被拦回（PRD §4.1）
- [ ] 岗位页维度编辑器在前端拦截空 / 超 10 项 / 重复 / 超长
- [ ] 题库页选中岗位后，维度字段变为该岗位维度的**下拉**；筛选栏支持**岗位 / 分类 / 维度**及来源、关键字（PRD §4.3）
- [ ] 创建面试时展示「正在生成面试题…」加载态；AI 失败（**502**）时弹窗保持打开且**可重试**
- [ ] 回答录入支持失焦自动保存与手动保存，每题显示保存状态；非 `ongoing` 状态只读
- [ ] 评估页逐题分数**逐条**实时出现，雷达图逐维度生长（PRD §5.3 ③）
- [ ] **评估完成后刷新页面仍可完整看到进度与报告**（PRD §7）
- [ ] **断线后展示「连接已断开」+「重新连接」，重连后从头重放**（PRD §7）
- [ ] 离开评估页时 **SSE 连接被关闭**（`destroy` 被调用），无连接泄漏
- [ ] `done` 后**不重复请求** `GET /report` 造成闪烁
- [ ] 雷达图：维度 < 3 时不绘制并显示降级文案；分数与半径成比例（满分 10）；标签不出界
- [ ] 删除被引用的岗位 / 题目时展示后端 **409** 文案（PRD §4.2、§4.3）
- [ ] 界面在 **1280px 及以上**视口下布局正常；**无移动端适配代码**（PRD §2）
- [ ] 所有后端数据用 `textContent` 渲染，**无 `innerHTML` 注入**（XSS 防护）
- [ ] `npm test` 全部通过（SSE 解析 + 雷达图几何）

---

## 11. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| SSE 客户端选型 | **`fetch` + `ReadableStream`**，不用 `EventSource` | `EventSource` 无法设置 `Authorization` 头（PRD §8）；JWT 放 query string 会泄露到日志与历史。**该约束来自 evaluation §4.3** |
| token 存储位置 | `localStorage` | 实现最简单、刷新与跨标签保持登录；XSS 风险经「界面无 HTML 注入点 + 全部用 `textContent`」缓解；公网场景应迁 `httpOnly` Cookie |
| 断线是否自动重连 | **不自动**，由用户点「重新连接」 | 避免后端长时间不可用时的重试风暴；评估任务在服务端继续（PRD §7），用户重连即重放 |
| 是否引入 DOM 测试框架 | **不引入**，改为手工联调清单 | 页面以「调 API + 重渲染」为主，DOM 测试投入产出比低 |
| 是否引入 Vitest | **引入**，仅测 SSE 解析与雷达图几何 | 两者是无界面反馈的纯逻辑，出错表现隐蔽，定位成本高。**可裁剪** |
| 是否引入图表库 | **不引入**，Canvas 手写 | 雷达图几何简单（约 80 行）；图表库体积与 PRD §2「原生 JS」约束相悖 |
| 是否引入状态管理库 | **不引入** | 页面级获取 + 重渲染足够；MVP 无跨页共享状态 |
| 回答保存是否防抖 | **不防抖**，失焦保存 | 避免高频请求；失焦已能覆盖主要场景 |
| 是否拦截未保存离开 | **不拦截** | 已有显式保存 + 失焦保存；`beforeunload` 在路由切换时误触发，得不偿失 |
| `done` 后是否重新拉取报告 | **不拉取** | SSE 已含全部数据；重复请求会增加往返并可能闪烁 |
| 前后端跨域处理 | **Vite 代理 + 相对路径 `/api`** | 开发与部署路径一致；后端 CORS 配置保留作兜底 |
| 前端是否做权限判定 | **只隐藏入口，不做权威判定** | 权限由后端强制（PRD §4.1）；前端控制仅为体验优化 |
| 移动端 | **不写媒体查询** | PRD §2 明确仅 PC 端 |
| **PRD §3.1 未列出用户管理页** | **新增 `pages/users.js`** | PRD §4.1 与 §8 定义了 `/users` 端点。**若前端没有对应页面，admin 将无任何途径创建 HR 账号**（初始 admin 只能由脚本 seed），该功能实际不可用。属补齐 |
