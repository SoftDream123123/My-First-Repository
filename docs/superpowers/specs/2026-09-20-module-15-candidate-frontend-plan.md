# 候选人前端执行计划书（MVP-2 面试者端）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：frontend 候选人端（路由、页面、会话按端分离）
**所属工程**：`frontend/`（**同一 Vite 工程内**，不新建工程）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§1.3（候选人侧非目标）、§2（技术栈与单机约束）、§3.1（`/candidate` 端）、§4.6（候选人可见范围）、§4.7（刷题）、§4.8（在线答题）、§4.9（反馈）、§9（会话按端分 key）
**前置依赖**：[module-07 frontend MVP-1](./2026-09-15-module-07-frontend-plan.md)、[module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md)、[module-12 interview 邀请](./2026-09-20-module-12-interview-invitation-plan.md)、[module-13 practice](./2026-09-20-module-13-practice-plan.md)、[module-14 evaluation 反馈](./2026-09-20-module-14-evaluation-feedback-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- HR 端与候选人端是**同一 Vite 工程内的两组路由**；**不新建工程、不换框架、不加构建产物**（§2、§3.1）
- 无 UI 框架、无图表库；仍用原生 HTML + CSS + JS（§2、module-07 §1.2）
- **仅 PC 端**，不做移动端响应式（§2）
- 同一 origin 下两端登录态必须**按端分 key 存储**（`hr.*` / `candidate.*`），保证单浏览器可同时保持两端登录（§9）
- 候选人可见范围严格限定：自己的练习数据、自己已接受的邀请所对应面试、其脱敏反馈（§4.6）
- 候选人端**不得出现** HR 侧入口；HR 端**不得出现**候选人侧入口（§4.6）
- 候选人**看不到**逐题分、维度分与雷达图；举报页面**不得**渲染这些内容（§1.3、§4.9）
- 刷题取题响应本身就**不含**参考答案与解析——前端不得假设其存在（[module-10 §4.2](./2026-09-20-module-10-question-plan.md)）
- 后端错误文案**原样展示**（`error.message`），前端不重写（module-07 §4.1 既有约定）
- `frontend/standalone.html` 已冻结、**不可编辑**（module-07 §1.2）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §3.1、§4.6）

| 子职责 | 内容 | PRD |
|---|---|---|
| 候选人路由 | `#/candidate/*` 路由组与角色门禁 | §3.1 |
| 候选人页面 | 登录/注册、邀请激活、刷题、我的面试、答题、反馈 | §4.6 |
| **会话按端分离** | `session.js` 改为按端分 key；`api.js` 按当前端取 token | §9 |
| 候选人外壳 | 候选人导向航与顶层布局 | §4.6 |
| 角色守卫扩展 | 从「仅 `adminOnly`」扩展为**两端各自的角色门禁** | §4.1、§4.6 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **HR 页面因 MVP-2 产生的新增表单字段与邀请管理 UI** | 题型/选项/参考答案/解析的表单、面试详情页的邀请生成与复制，属 **HR 端**的增量，归 [module-07 的 MVP-2 增量](./2026-09-15-module-07-frontend-plan.md)（同步修正清单中列出）。本文档只负责候选人端与**两端共用的基础设施改造** |
| **新建第二个 Vite 工程 / 第二个 HTML 入口 / 新构建产物** | PRD §2 明确禁止 |
| 候选人端的雷达图、逐题分展示 | PRD §1.3、§4.9 明确不下发（后端也不下发，见 module-14 §4.2） |
| 候选人社交能力（排行榜、积分、成就、讨论区） | PRD §1.3 |
| 移动端响应式 | PRD §2 |
| 编辑 `standalone.html` | 已冻结、生成脚本已删除，改它等于制造第二份真相 |
| 引入 DOM 测试框架（jsdom / testing-library） | module-07 §8.1 的既有决策：Vitest 只测纯函数，页面靠 `mock/*.html` 手工走查。本次**不改变**该决策 |
| 候选人改密码 / 找回密码 | PRD 未要求 |

### 1.3 依赖方向

```
pages/candidate-*.js ──→ components/candidate-shell.js
        │                        │
        ├──→ api.js ──→ session.js（按端取 token）
        ├──→ router.js（路由与守卫）
        └──→ dom.js / components/{form,modal,toast}.js

候选人页面 ✗→ HR 页面（两组路由互不 import，避免入口耦合）
api.js 仍不感知 SSE —— SSE 只在 HR 评估页使用（module-07 §4.3）
```

> **候选人端不使用 `sse.js`**：PRD 的流式能力只在评估环节（§1.3「仅评估环节流式」），候选人的刷题判分与反馈读取都是普通请求。

---

## 2. 文件结构

### 2.1 新增文件

| 文件 | 单一职责 |
|---|---|
| `frontend/src/side.js` | **端的解析与活动端标记**（`resolveSide` / `getActiveSide` / `setActiveSide`） |
| `frontend/src/components/candidate-shell.js` | 候选人外壳：品牌区、候选人导向航、顶栏 |
| `frontend/src/pages/candidate-login.js` | 登录 / 注册（同页切换） |
| `frontend/src/pages/candidate-activate.js` | 邀请码激活 |
| `frontend/src/pages/candidate-practice.js` | 刷题：筛选 + 开始练习 |
| `frontend/src/pages/candidate-practice-session.js` | 练习进行：逐题作答与即时判分 |
| `frontend/src/pages/candidate-wrong-book.js` | 错题本 |
| `frontend/src/pages/candidate-stats.js` | 练习统计 |
| `frontend/src/pages/candidate-interviews.js` | 我的面试 |
| `frontend/src/pages/candidate-interview-detail.js` | 面试作答与交卷 |
| `frontend/src/pages/candidate-feedback.js` | 候选人反馈 |
| `frontend/src/__tests__/side.test.js` | `resolveSide` 与守卫决策的纯函数单测 |
| `frontend/mock/candidate-harness.html` | 浏览器侧联调台（沿用 module-07 §8.4 的手工走查方式） |

### 2.2 修改的既有文件（**改动面必须最小**）

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `frontend/src/session.js` | 存储键加端命名空间：`hr.token` / `candidate.token` 等；所有导出函数加 `side` 参数 | ⚠️ 现状是**固定的 `hr.token` / `hr.user`**（`session.js` 第 9-10 行）。同源下两端会互相顶号——这是 PRD §9 的直接要求 |
| `frontend/src/api.js` | 取 token 时用当前端（`side.getActiveSide()`）；401 处理回调带上是哪一端 | 否则候选人请求会带上 HR 的 token（或反之） |
| `frontend/src/auth.js` | 导出函数加端参数；`isAdmin` 保持 HR 语义；新增候选人端判断 | `main.js` 的 `refreshUser` 需按端调用 |
| `frontend/src/router.js` | 路由表加 `side` 字段；`guard()` 改为**按端的角色门禁**；`DEFAULT_ROUTE` 按端区分；守卫决策抽成**纯函数** | 现有守卫只有 `adminOnly` 一种门禁，无法表达「HR 端 vs 候选人端」 |
| `frontend/src/main.js` | 注册 11 个候选人页面；`boot()` 与 401 处理器改为**按端** | 页面注册表与启动流程 |
| `frontend/src/styles/pages.css`、`components.css` | 追加候选人端样式规则 | `index.html` 只 link 四个 CSS 文件（tokens/base/components/pages），**不新增 CSS 文件** |

**不改动**：`frontend/src/components/shell.js`（HR 外壳原样保留，候选人外壳另开文件 → HR 端零回归）、`dom.js`、`sse.js`、`components/{form,modal,toast,radar}.js`、`vite.config.js`、`index.html`、`package.json`、`standalone.html`。

---

## 3. 路由与会话设计（**本模块的核心**）

### 3.1 路由表

| hash 路由 | 页面模块 | 端 | 权限 |
|---|---|---|---|
| `#/login` | `login.js` | hr | 公开 |
| `#/interviews` | `interviews.js` | hr | hr / admin |
| `#/interviews/:id` | `interview-detail.js` | hr | hr / admin |
| `#/interviews/:id/evaluation` | `evaluation.js` | hr | hr / admin |
| `#/positions` | `positions.js` | hr | hr / admin |
| `#/questions` | `questions.js` | hr | hr / admin |
| `#/users` | `users.js` | hr | **admin** |
| `#/candidate/login` | `candidate-login.js` | candidate | 公开 |
| `#/candidate/activate` | `candidate-activate.js` | candidate | candidate |
| `#/candidate/practice` | `candidate-practice.js` | candidate | candidate |
| `#/candidate/practice/:id` | `candidate-practice-session.js` | candidate | candidate |
| `#/candidate/wrong-book` | `candidate-wrong-book.js` | candidate | candidate |
| `#/candidate/stats` | `candidate-stats.js` | candidate | candidate |
| `#/candidate/interviews` | `candidate-interviews.js` | candidate | candidate |
| `#/candidate/interviews/:id` | `candidate-interview-detail.js` | candidate | candidate |
| `#/candidate/interviews/:id/feedback` | `candidate-feedback.js` | candidate | candidate |

**默认落地页（按端）**

| 端 | 默认页 | 说明 |
|---|---|---|
| `hr` | `#/interviews` | 与现状一致 |
| `candidate` | `#/candidate/interviews` | **我的面试**是候选人最关心的（有无待答面试），随后可自行去刷题 |

> **未知路由的兜底按端决定**：`#/candidate/xxx` → 候选人默认页；其余 → `#/interviews`。这要求在解析未知路由时**也先判断前缀**，不能一律跳 HR 默认页（否则候选人输错地址会被弹到 HR 登录页）。

### 3.2 端的解析（`side.js`）

| 导出 | 签名 | 说明 |
|---|---|---|
| `resolveSide(hash)` | `(hash: string) => 'hr' \| 'candidate'` | **纯函数**：`hash.startsWith('#/candidate')` → `'candidate'`，否则 `'hr'`。可被 Vitest 直接单测 |
| `getActiveSide()` | `() => 'hr' \| 'candidate'` | 当前活动端（`session.js` 与 `api.js` 用它取存储键） |
| `setActiveSide(side)` | `(side) => void` | 由 `router.js` 在每次渲染前设置 |

**设置时机的顺序约束（容易出错，必须按此实现）**

```
start(app):
  1. hex = location.hash || DEFAULT_ROUTE[resolveSide(location.hash)]
  2. setActiveSide(resolveSide(hex))          ← 必须在任何 render 之前
  3. render()

render():
  1. resolved = resolve(hex)  → 得到 route（含 side）
  2. setActiveSide(resolved.route.side)       ← 匹配成功后以路由声明为准
  3. guard 决策 → 放行 / 重定向
  4. 页面 render：此时 api.js 取到的 token 必定是正确端的
```

> **为何在第 1 步就先设一次**：`render()` 之前可能有请求（例如 `boot()` 里的 `refreshUser()`）。若那时活动端尚未确定，会读到 `hr` 的默认值并带上错误的 token。这一处顺序错误在「先打开候选人页面」时不会暴露，在「先打开 HR 页面再切到候选人页面」时才出现 —— 属于典型的环境相关 bug，必须用顺序约束提前钉死。

### 3.3 会话按端分离（`session.js`）

| 函数 | 现状签名 | 新签名 |
|---|---|---|
| `save` | `(token, user)` | `(token, user, side)` |
| `clear` | `()` | `(side)` |
| `getToken` | `()` | `(side)` |
| `getUser` | `()` | `(side)` |
| `setUser` | `(user)` | `(user, side)` |

**存储键**：

| 端 | token 键 | user 键 |
|---|---|---|
| `hr` | `hr.token` | `hr.user` |
| `candidate` | `candidate.token` | `candidate.user` |

| 设计要点 | 说明 |
|---|---|
| **`side` 由调用方显式传入，不在 `session.js` 内部读活动端** | 让模块保持无状态、纯函数式（除 localStorage 读写）。若内部读活动端，测试与排查都必须先设置全局状态 |
| **键名由 `side` 拼出**：`` `${side}.token` `` | 新增端只需加一个取值，不需要再加一对常量 |
| HR 端键名**不变**（仍是 `hr.token` / `hr.user`） | 现有 HR 用户升级后登录态**不丢失** |
| `clear(side)` 只清该端 | 退出候选人端不应把 HR 登录态也清掉（这正是「同时登录」的前提） |

### 3.4 导航守卫（改为**纯决策函数 + 执行**）

现状 `guard()` 直接改 `location`，无法单测。改为：

| 导出 | 签名 | 说明 |
|---|---|---|
| `decideGuard(route, ctx)` | `(route, {hasToken: bool, role: string \| null}) => {action: 'allow' \| 'redirect', to?: string, toast?: string}` | **纯函数**，可单测 |
| `guard(route)`（内部） | — | 调 `decideGuard` 并执行跳转 / toast |

**`decideGuard` 的规则表**

| 条件 | 结果 |
|---|---|
| route 为公开 且 该端已登录 | redirect → 该端默认页 |
| route 为公开 且 未登录 | allow |
| 未登录（该端无 token） | redirect → 该端登录页 |
| route 要求 `admin` 且 role ≠ `admin` | redirect → HR 默认页 + toast「无权限访问该页面」 |
| route 属 HR 端 且 role === `candidate` | redirect → 候选人默认页（**跨端串号**：候选人 token 不能进 HR 页） |
| route 属候选人端 且 role ∈ {`admin`, `hr`} | redirect → HR 默认页 |
| 其余 | allow |
| **解析不到 route（未知路径）** | redirect → **按 hash 前缀决定**的该端默认页 |

| 要点 | 说明 |
|---|---|
| **门禁只做「体验」，不做「安全」** | 真正的强制在**后端**（[module-16](./2026-09-20-module-16-permission-guard-plan.md)）。前端守卫拦不住手工改 hash 的用户，但能避免让人看到一堆 403 报错 |
| 跨端串号必须拦截 | 候选人 token 进 HR 页面会得到满屏 403；HR token 进候选人页会看到空数据。提前重定向体验更好，也让「两端互不干扰」在 UI 上成立 |
| `role` 来自 `session.getUser(side)` 缓存 | 角色不缓存在 JWT 里，`boot()` 会刷新一次（module-07 §4.2） |

### 3.5 `api.js` 的改造

| 改动点 | 说明 |
|---|---|
| token 来源 | `session.getToken(side.getActiveSide())` 取代 `getToken()` |
| 401 处理 | `unauthorizedHandler(side)` —— 由 `main.js` 注入的回调按端跳对应登录页 |
| 其余行为**全部不变** | 204 → `null`、`{code,message,detail}` 透传、网络错误码 `NETWORK_ERROR`、`/auth/login` 的 401 不触发清 token（登录页自己提示）—— 这些既有细节一个都不能动 |

> **`api.js` 是 HR 与候选人共用的关键路径**：本模块对它只做「token 从哪来」与「401 跳哪去」两处改动，其余逻辑保持原样，以降低 HR 端回归风险。

### 3.6 `auth.js` 的改造

| 导出 | 变化 |
|---|---|
| `saveToken(token, user, side)` | 加 `side` |
| `getToken(side)` / `getUser(side)` | 加 `side` |
| `isLoggedIn(side)` | 加 `side` |
| `isAdmin(side = 'hr')` | 保持 HR 语义；候选人端不用它 |
| `isCandidate(side = 'candidate')` | **新增**：`getUser(side)?.role === 'candidate'` |
| `logout(side)` | 只清该端并跳该端登录页 |
| `refreshUser(side)` | 按端调 `/auth/me`（端点相同，token 不同） |
| `register(username, password)` | **新增**：调 `POST /auth/register`；成功后**自动调 login**（[module-09 §5.1](./2026-09-20-module-09-auth-plan.md) 规定注册不返回 token） |

---

## 4. 候选人页面设计

> 所有页面沿用既有页面契约（module-07 §3.2）：`export async function render(container, params)`，可选 `destroy()`；加载态用 `loadingBlock`，失败态用 `emptyState` + 重试按钮，模态用 `openModal` / `confirmModal`，表单错误用 `fieldErrors`（**键名必须等于后端 `detail.fields[].field`**）。

### 4.1 `candidate-login.js`（`#/candidate/login`）

| 项 | 设计 |
|---|---|
| 布局 | 单列窄卡片（复用登录页样式），品牌区写「面试助手 · 候选人端」 |
| 两种模式 | 「登录」/「注册」切换（同一页面内切换，不新增路由） |
| 登录 | `POST /auth/login` → `auth.saveToken(token, user, 'candidate')` → 跳 `#/candidate/interviews` |
| 注册 | `POST /auth/register` → 成功后**自动** `POST /auth/login` → 同样落登录态 → 跳 `#/candidate/interviews` |
| 注册关闭时的处理 | 后端返回 409 且 `detail.reason === 'self_register_disabled'` → 在注册表单上提示「自助注册已关闭，请使用邀请码激活」并给出跳 `#/candidate/activate` 的按钮 |
| 入口提示 | 卡片底部给「已有邀请码？去激活」链接 |
| **不做** | 不显示 HR 侧任何入口；不提供「记住我」 |

> **注册后自动登录的两步请求必须都成功才算完成**：若登录失败（例如刚注册的账号被管理员禁用），提示「注册成功，但自动登录失败，请手动登录」，**不要**把用户留在半登录状态。

### 4.2 `candidate-activate.js`（`#/candidate/activate`）

| 项 | 设计 |
|---|---|
| 表单 | 邀请码、用户名、密码（≥ 8 位，前端先校验一次，后端仍会校验） |
| 提交 | `POST /candidate/invitations/{code}/accept` |
| 成功后 | 提示「已绑定面试：{position_name}」→ **自动调 `POST /auth/login`** → 跳 `#/candidate/interviews/{id}` |
| 失败提示 | 直接展示后端文案（「邀请码无效或已失效」「用户名已被占用」「你已接受过该面试的邀请」）；**不得**自行推断原因（后端刻意不区分失效原因，见 module-12 §5.3） |
| 字段错误 | 用 `fieldErrors` 映射 `detail.fields`（如 `password` / `username`） |
| **不做** | 不在前端预校验邀请码格式（格式规则属后端，前端猜错会拦掉合法码） |

### 4.3 `candidate-practice.js`（`#/candidate/practice`）

| 项 | 设计 |
|---|---|
| 筛选栏 | 岗位下拉、分类、维度、难度、题型、题量 |
| **岗位下拉的数据来源** | `GET /candidate/positions`（**有题目的岗位**：`id` / `name` / `question_count`）。首项固定为「不限岗位」。该端点与取题同为「全库」口径，因此**筛选项与取得到的题必然自洽**（[module-10 §5.6](./2026-09-20-module-10-question-plan.md)） |
| 岗位下拉的展示 | 选项文案用 `` `${name}（${question_count} 题）` `` —— 让候选人一眼看出哪些岗位有题可练 |
| 开始按钮 | `POST /practice/sessions` → 跳 `#/candidate/practice/{id}` |
| 空结果 | 取不到题时后端返回 409，页面提示「没有符合条件的题目，请调整筛选条件」并**保留筛选条件不重置** |
| **进行中的练习** | 页面下方列出 `GET /practice/sessions?status=ongoing` 的会话，每行显示岗位/分类摘要与进度（`answered_count / total`），点击「继续」→ `#/candidate/practice/{id}`。**这是候选人中途离开后唯一的返回入口** |
| **历史练习** | 同一次请求取全部会话（`status` 缺省），前端按 `status` 分成「继续练习」与「历史记录」两组，**避免两次请求** |
| 空态 | 「还没有练习记录。选好条件，开始第一次练习」 |
| **不做** | 不做「只练错题」入口（需后端支持跨会话取题，见 [module-13 §10](./2026-09-20-module-13-practice-plan.md)）；不做练习时长统计 |

> **候选人的岗位候选值为什么不能取自「已参与的面试」**：那会**漏掉候选人从未面过的岗位**，而它们恰恰是他最需要练的。`GET /candidate/positions` 的收录范围是「至少有一道题的岗位」，与刷题取题口径一致——两个口径若不同，会出现「下拉里有 A 岗位，选了却取不到题」的矛盾。

### 4.4 `candidate-practice-session.js`（`#/candidate/practice/:id`）

| 项 | 设计 |
|---|---|
| 加载 | `GET /practice/sessions/{id}` |
| 题目渲染 | **按 `question_type` 分支**：`single_choice` → 单选按钮组（用 `options`）；`short_answer` → `textarea` |
| 逐题提交 | `POST /practice/sessions/{id}/items`，`{item_id, user_answer}` |
| 判分展示 | 提交后在该题下方就地展示：`is_correct`（对/错/未判分）、`score`、`reference_answer`、`explanation` |
| **未判分态的展示** | `is_correct === null` → 显示中性提示「本题暂未判分」+「重判」按钮（调 `POST /practice/items/{item_id}/rescore`）。**不得**显示为「错误」 |
| 进度 | 顶部显示 `answered_count / total`（取自响应中的 `progress`） |
| 结束 | `confirmModal` 确认后 `POST /practice/sessions/{id}/finish` → 展示小结（`total` / `answered_count` / `correct_count` / `unscored_count` / `accuracy` / `by_dimension`） |
| 未判分题数 | 小结中**必须**显示 `unscored_count`（否则候选人会把「未判分」误读成「答错」） |
| **不做** | 不做倒计时、不做切屏检测、不做自动保存草稿（提交即保存） |

### 4.5 `candidate-wrong-book.js`（`#/candidate/wrong-book`）

| 项 | 设计 |
|---|---|
| 数据 | `GET /practice/wrong-book`（支持 `dimension` / `question_type` / `limit`） |
| 展示 | 每题一行：题干摘要、我的错误作答、参考答案、解析、`wrong_count`（错误次数徽标）、最近判错时间 |
| 空态 | 「还没有错题。去刷题」+ 跳刷题的按钮 |
| **不做** | 不做「只练这些错题」的入口（串到练习创建需要后端支持，本 MVP 不做，见 module-13 §10） |

### 4.6 `candidate-stats.js`（`#/candidate/stats`）

| 项 | 设计 |
|---|---|
| 数据 | `GET /practice/stats` |
| 展示 | 总量卡片（已作答 / 已判分 / 正确率 / 练习次数）+ **按维度的正确率表** + 按题型的正确率表 |
| **未判分的呈现** | 单独显示 `unscored_count` 并注明「未判分的题不计入正确率」 |
| **不做** | **不画雷达图**（PRD §1.3 明确候选人看不到雷达图）。维度统计用**条形进度**而非雷达图 —— 既满足 §4.7 的「按维度正确率」，又不触碰 §1.3 的禁令 |
| 正确率为 `null` | 显示「—」并提示「还没有已判分的作答」 |

### 4.7 `candidate-interviews.js`（`#/candidate/interviews`）

| 项 | 设计 |
|---|---|
| 数据 | `GET /candidate/interviews` |
| 展示 | 列表：岗位名、状态标签、题目数 / 已答数、**是否已交卷**、创建时间；操作：「查看」/「查看反馈」（`status === 'evaluated'` 时） |
| 空态 | 「还没有面试。如果你有邀请码，去激活」+ 跳激活页按钮（把最可能的下一步直接给出） |
| **不做** | 不显示 HR 的评语与评分（后端也不返回） |

### 4.8 `candidate-interview-detail.js`（`#/candidate/interviews/:id`）

| 项 | 设计 |
|---|---|
| 数据 | `GET /candidate/interviews/{id}` |
| 展示 | 面试摘要（岗位、状态）+ 题目列表（`seq`、`content`、维度标签）+ 每题文本框 |
| 作答 | `POST /candidate/interviews/{id}/answers`（`{interview_question_id, content}`）。**失焦即保存**（与 HR 详情页的逐题保存同一手法，module-07 §5.3） |
| 交卷 | `confirmModal` 强提醒（「交卷后你不能再修改作答」）→ `POST /candidate/interviews/{id}/submit` |
| **已交卷态** | 后端返回 `submitted === true` → 全部输入框**只读** + 顶部横幅「你已交卷，如有疑问请联系招聘方」。**不得**只在提交时拦截而让输入框看起来可编辑 |
| 提示 | 未交卷时提示「交卷前可随时修改」；交卷后不再显示 |
| **不做** | 不显示参考答案（面试题本就没有）、不显示评分与反馈（反馈在独立页面） |

### 4.9 `candidate-feedback.js`（`#/candidate/interviews/:id/feedback`）

| 项 | 设计 |
|---|---|
| 数据 | `GET /candidate/interviews/{id}/feedback` |
| 展示 | 综合结论（长文本）+ 优点列表 + 待改进列表；`level === 'full'` 且 `overall_score` 非空时，额外显示总分 |
| **绝对不展示** | 逐题分、维度分、**雷达图**。响应里本就没有这些数据；页面**不得**尝试从别处拼凑 |
| 未评估 | 后端 409 → 页面提示「评估尚未完成，请稍后再来」，并给返回列表的按钮（**不是**错误样式，这是正常状态） |
| 生成失败 | 后端 502 → 提示「反馈生成失败，请稍后重试」+ 重试按钮（后端未落库，重试会重新生成，见 module-14 §5.3） |
| **不做** | 不做下载 / 分享 / 打印（PRD §1.3 明确不做报告导出与分享） |

### 4.10 候选人外壳 `components/candidate-shell.js`

| 项 | 设计 |
|---|---|
| 品牌区 | 「面试助手」+ 副标题「候选人端」（HR 侧是「HR 工作台」） |
| 导航 | `我的面试`（`/candidate/interviews`）、`刷题`（`/candidate/practice`）、`错题本`（`/candidate/wrong-book`）、`练习统计`（`/candidate/stats`） |
| 顶栏 | 用户名 + 「退出」（按候选人端登出） |
| 激活入口 | 导航**不含**激活项（激活是一次性动作）；入口放在「我的面试」页的空态与登录页 |
| 结构 | `createCandidateShell(contextNodes)` → `{ root, main }`，与 `createShell` 同构，便于页面写法一致 |
| **不修改 `shell.js`** | HR 外壳保持原样 → HR 端零回归 |

> 抽一个 `createShell` 的公共基建（如传入品牌文案与 NAV）会让两个页面组共享一个函数。**本 MVP 不抽**：`shell.js` 是 HR 端已稳定运行的代码，为候选人端重构成参数化外壳会把回归风险带入 HR 端，收益仅是少十几行重复。§10 记录该取舍。

---

## 5. 样式设计

| 项 | 设计 |
|---|---|
| CSS 文件 | **不新增**。候选人规则追加到既有的 `styles/components.css`（外壳类）与 `styles/pages.css`（页面类） |
| 前缀 | 候选人特有类名统一加 `candidate-` 前缀（如 `.candidate-brand`），避免与 HR 端规则相互污染 |
| 复用 | 布局与控件**复用既有 class**：`.panel` / `.page-head` / `.table` / `.filterbar` / `.field` / `.input` / `.select` / `.textarea` / `.btn btn--*` / `.tag` / `.empty` / `.spinner` / `.meta` / `.cell-actions` |
| 令牌 | 只用 `styles/tokens.css` 的既有变量（颜色、字号、间距、圆角），**不新增令牌** |
| 正确率展示 | 用既有 `--pass` / `--watch` 与 `scoreClass` 同源的判断（阈值 **6.5**）—— 若展示分数，必须与后端 `PASS_THRESHOLD` 一致（module-11 §3.3） |
| 仅 PC | 固定 `min-width: 1280px` 的既有约定（module-07 §3.4），候选人端同样不做响应式 |

---

## 6. 测试设计（对应 PRD §10）

> 沿用 module-07 §8.1 的决策：Vitest **只测纯函数**（无 jsdom）；页面行为靠 `mock/candidate-harness.html` 手工走查。

### 6.1 `frontend/src/__tests__/side.test.js`（新增）

**`resolveSide`**

| 测试 | 断言 |
|---|---|
| `test_resolve_candidate_prefix` | `#/candidate/login`、`#/candidate`、`#/candidate/interviews/3/feedback` → `'candidate'` |
| `test_resolve_hr_default` | `#/interviews`、`#/login`、`''`（空 hash） → `'hr'` |
| `test_resolve_is_prefix_not_substring` | `#/x-candidate/y` → `'hr'`（**不能用 `includes`** —— 前缀判定必须严格） |
| `test_resolve_case_sensitivity` | `#/Candidate/x` → `'hr'`（路由大小写敏感，与既有 `resolve()` 一致） |

**`decideGuard`**

| 测试 | 断言 |
|---|---|
| `test_public_route_allows_when_logged_out` | 未登录进该端登录页 → `allow` |
| `test_public_route_redirects_when_logged_in` | 已登录进登录页 → `redirect` 到该端默认页 |
| `test_protected_route_redirects_when_logged_out` | 未登录进受保护页 → `redirect` 到**该端**登录页 |
| `test_admin_route_rejects_hr` | `adminOnly` 且 role=`hr` → `redirect` + toast |
| `test_hr_route_rejects_candidate` | HR 端路由 + role=`candidate` → `redirect` 到候选人默认页 |
| `test_candidate_route_rejects_hr` | 候选人路由 + role=`hr` → `redirect` 到 HR 默认页 |
| `test_candidate_route_rejects_admin` | 同上（role=`admin`）→ 同样重定向 |
| `test_candidate_route_allows_candidate` | 候选人路由 + role=`candidate` + 有 token → `allow` |
| `test_hr_route_allows_admin_and_hr` | role 为 `admin` / `hr` → `allow` |
| `test_unknown_route_redirects_within_side` | 未知的候选人路径 → 候选人默认页（**不是** HR 默认页） |
| `test_decide_is_pure` | 同输入两次调用结果相等，且**不抛异常**（不访问 `location`） |

> **`decideGuard` 必须是纯函数**：这是本次唯一改动既有守卫逻辑的地方，抽成纯函数后可以用表格驱动覆盖 11 条规则。若留着 `location` 副作用，这些规则只能靠手工点击验证。

### 6.2 既有测试零回归

| 项 | 要求 |
|---|---|
| `frontend/src/__tests__/sse.test.js`、`radar.test.js` | 全部通过（本次不改 `sse.js` / `radar.js`） |
| `npm test` | 全绿 |
| `npm run build` | 成功（**未新增构建产物与入口**） |

### 6.3 手工联调（`frontend/mock/candidate-harness.html`）

沿用 module-07 §8.4 的方式：stub `window.fetch` 驱动真实页面代码。覆盖：

| 场景 | 期望 |
|---|---|
| 注册成功 → 自动登录 | 两步请求发出，落候选人登录态，进入「我的面试」 |
| 自助注册已关闭 | 409 + `detail.reason` → 表单提示并给出跳激活页的按钮 |
| 邀请激活成功 | 显示绑定的岗位名，进入面试页 |
| 邀请码无效（四种原因） | **四种都显示同一文案**（不泄露原因） |
| 刷题：单选判对 / 判错 / 未判分 | 三种状态各自正确渲染（未判分**不显示为错误**） |
| 刷题：简答题提交 | 显示分数与解析 |
| 刷题：岗位下拉 | 选项来自 `GET /candidate/positions`，文案含题量；选一个岗位后取题结果与之一致 |
| 刷题：离开未完成的练习后再回刷题页 | 「继续练习」区域列出该会话，点击可回到它 |
| 结束练习 | 小结含 `unscored_count` |
| 错题本 | 未判分的题**不出现** |
| 统计页 | 无雷达图；未判分单独计数；无已判分时正确率显示「—」 |
| 在线答题 → 交卷 | 交卷后输入框只读 + 横幅提示 |
| 反馈页（`summary`） | 只有结论 / 优点 / 待改进，**无总分** |
| 反馈页（`full`） | 多一个总分卡片，**仍无逐题分与雷达图** |
| 反馈未评估 | 409 → 正常提示而非错误样式 |

### 6.4 两端共存（**单机约束的关键验证**）

| # | 操作 | 期望 |
|---|---|---|
| 1 | 同一浏览器标签 A 登录 HR，标签 B 登录候选人 | **两者都保持登录**（互不顶号） |
| 2 | 在标签 A 退出登录 | 标签 B 的候选人登录态**不受影响** |
| 3 | 在标签 B 手工把 hash 改成 `#/positions` | 被重定向到候选人默认页（跨端串号拦截） |
| 4 | 在标签 A 手工把 hash 改成 `#/candidate/practice` | 被重定向到 HR 默认页 |
| 5 | 直接打开 `#/candidate/interviews`（未登录） | 跳 `#/candidate/login`（**不是** `#/login`） |
| 6 | 先打开 HR 首页，再切到候选人页并操作 | 请求带上的是**候选人** token（验证 §3.2 的时序约束） |

> 第 6 条是**最容易漏测**的一条：它检验 `setActiveSide` 是否在请求之前执行。只在「先开候选人页」的路径上测试不会暴露时序错误。

---

## 7. 任务分解（步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-09（注册）、module-12（邀请与作答端点）、module-13（刷题端点）、module-14（反馈端点）已完成。

### Task 15.1：端的解析与会话分离（基础设施）

- [ ] 新建 `src/side.js`（`resolveSide` / `getActiveSide` / `setActiveSide`）
- [ ] `session.js` 加端命名空间（§3.3）
- [ ] 写 `side.test.js` 的 `resolveSide` 四条测试
- [ ] 运行 `npm test` 确认通过
- [ ] 提交

### Task 15.2：守卫决策纯函数

- [ ] 从 `router.js` 抽出 `decideGuard(route, ctx)`，路由表加 `side` 与按端的 `DEFAULT_ROUTE`
- [ ] 写 `decideGuard` 的 11 条测试
- [ ] 运行确认通过
- [ ] **回归检查**：HR 端七个页面逐一走查，行为与改动前一致
- [ ] 提交

### Task 15.3：api / auth / main 按端改造

- [ ] `api.js` 按活动端取 token；401 回调带 `side`
- [ ] `auth.js` 加端参数、`isCandidate`、`register`
- [ ] `main.js`：注册候选人页面、`boot()` 按端刷新、401 按端跳登录
- [ ] 按 §6.4 的 1~2、5 条做手工验证（两端共存与按端跳转）
- [ ] 提交

### Task 15.4：候选人外壳与样式

- [ ] 新建 `components/candidate-shell.js`
- [ ] 在 `components.css` / `pages.css` 追加候选人规则（`candidate-` 前缀）
- [ ] 提交

### Task 15.5：登录 / 注册 / 激活

- [ ] 实现 `candidate-login.js`（登录 + 注册切换 + 注册后自动登录 + 注册关闭提示）
- [ ] 实现 `candidate-activate.js`
- [ ] 按 §6.3 前三条走查
- [ ] 提交

### Task 15.6：刷题三页

- [ ] 实现 `candidate-practice.js`、`candidate-practice-session.js`、`candidate-wrong-book.js`、`candidate-stats.js`
- [ ] 按 §6.3 的刷题 / 结束 / 错题本 / 统计六条走查（**重点：未判分不显示为错误；统计页无雷达图**）
- [ ] 提交

### Task 15.7：我的面试 / 作答 / 反馈

- [ ] 实现 `candidate-interviews.js`、`candidate-interview-detail.js`、`candidate-feedback.js`
- [ ] 按 §6.3 的在线答题 / 反馈三条走查（**重点：已交卷只读；summary 无总分**）
- [ ] 提交

### Task 15.8：联调台与两端共存验证

- [ ] 新建 `mock/candidate-harness.html`，覆盖 §6.3 全表
- [ ] 按 §6.4 全表走查（**含第 6 条的时序验证**）
- [ ] 提交

### Task 15.9：全量回归与文档

- [ ] `npm test` 全绿；`npm run build` 成功
- [ ] HR 端七个页面完整走一遍（**零回归**）
- [ ] 更新 `frontend/README.md`（两端入口、演示步骤、候选人端说明）
- [ ] 更新 `docs/apis/API接口文档.md`（13 个新端点）
- [ ] 提交

---

## 8. 验收标准

- [ ] 候选人端与 HR 端在**同一 Vite 工程**内，未新增工程、HTML 入口或构建产物
- [ ] `npm run build` 成功，产物结构与 MVP-1 一致
- [ ] 会话按端分 key：**同一浏览器可同时登录两端且互不顶号**；退出任一端不影响另一端
- [ ] HR 端键名仍为 `hr.*`（既有登录态不丢失）
- [ ] `resolveSide` 与 `decideGuard` 为**纯函数**且有单测覆盖（含「前缀而非子串」「未知路径按端兜底」）
- [ ] 跨端串号被拦截：候选人 token 进 HR 页面、HR token 进候选人页面，均重定向到本端默认页
- [ ] 未登录访问 `#/candidate/*` 跳 `#/candidate/login`（不是 `#/login`）
- [ ] **先开 HR 页再切候选人页**时，请求带的是候选人 token（时序正确）
- [ ] 注册成功后自动登录；自助注册关闭时给出跳激活页的引导
- [ ] 邀请激活失败的**四种原因显示同一文案**，前端不自行推断
- [ ] 刷题页按 `question_type` 渲染单选/文本框；提交后就地显示判分与解析
- [ ] **未判分（`is_correct === null`）显示为中性状态，不显示为「错误」**；提供重判入口
- [ ] 统计页**不出现雷达图**；未判分数单独呈现且不计入正确率；无已判分时正确率显示「—」
- [ ] 错题本不含未判分题；显示 `wrong_count`
- [ ] 交卷后输入框**只读**并有横幅提示；未交卷时可随时修改
- [ ] 反馈页在 `summary` 档**无总分**、在 `full` 档有总分，**两档都无逐题分与雷达图**
- [ ] 候选人端**无任何 HR 侧入口**；HR 端无候选人入口
- [ ] 刷题页的**岗位下拉来自 `GET /candidate/positions`**（有题目的岗位，文案含题量），且与取题口径一致
- [ ] 刷题页列出**进行中的练习**（`GET /practice/sessions?status=ongoing`）并可「继续」回到该会话
- [ ] 本地 `PASS_THRESHOLD` 相关的分数展示与后端一致（阈值 6.5，见 module-11 §3.3）
- [ ] `shell.js` / `sse.js` / `radar.js` / `dom.js` / `vite.config.js` / `index.html` / `standalone.html` **未被修改**
- [ ] `npm test`（含既有 sse / radar 单测）全绿；HR 端七页零回归
- [ ] `frontend/README.md` 与 `docs/apis/API接口文档.md` 已更新

---

## 9. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **同源下单浏览器两端互相顶号** | `session.js` 按端分 key（§3.3） | 现状是固定 `hr.token` / `hr.user`。不改则 PRD §9 的演示路径（同一浏览器跑通 HR 发邀请 → 候选人答题）**根本走不通** |
| **`setActiveSide` 的时序** | 在 `start()` 与每次 `render()` 开头各设一次（§3.2） | 漏掉会表现为「换端后请求带错 token」。该 bug 只在特定操作顺序下出现，必须用顺序约束 + §6.4 第 6 条钉死 |
| **候选人没有可用的岗位列表接口** | **已补进 PRD**：新增 `GET /candidate/positions`，注册在 `question` 包（口径 =「有题目的岗位」，与取题一致） | 初版曾拟用「已参与面试的岗位」凑筛选项，但那会**漏掉候选人从未面过的岗位**——恰恰是他最需要练的。补端点后筛选项与取题口径自洽。为何放 `question` 包见 [module-10 §2](./2026-09-20-module-10-question-plan.md) |
| **PRD 没有「列出我的练习会话」端点** | **已补进 PRD**：新增 `GET /practice/sessions`（含 `status` 筛选） | 初版「不做该列表」的代价是：候选人一旦离开未完成的练习，**只能靠 URL 回到它**。补端点后刷题页可直接渲染「继续练习」入口（[module-13 §5.9](./2026-09-20-module-13-practice-plan.md)） |
| **不重构 `shell.js` 为参数化外壳** | 候选人外壳另开文件 | `shell.js` 是 HR 端稳定运行的代码；参数化改造的收益（少十几行重复）远小于把回归风险带入 HR 端的代价 |
| **统计页不画雷达图** | 用条形进度替代 | PRD §1.3 明确候选人看不到雷达图。用柱状呈现「按维度正确率」既满足 §4.7 又不越界 |
| **未判分不能显示为「错误」** | 三态渲染（对 / 错 / 未判分） | 后端刻意用 `NULL` 表达「未判分」（module-13 §3.2）。若前端把 `null` 当成 `false` 渲染，候选人会以为答错了，而事实是 AI 没判出来 |
| 邀请失效四种原因同一文案 | 前端直接展示后端文案，不推断 | 后端刻意不区分（module-12 §5.3）。前端若自行加提示（如「邀请码可能已过期」）就泄露了原因 |
| `api.js` 是两端共用路径 | 只改 token 来源与 401 跳转，其余不动 | 它是 HR 端的关键路径。逐行审查改动面是控制回归的唯一办法 |
| 不引入 DOM 测试框架 | 沿用 Vitest 纯函数 + `mock/*.html` | module-07 §8.1 的既有决策，本次不推翻。代价是页面行为依赖手工走查（§6.3 给出了完整清单） |
| 候选人端是否要显示分数 | 刷题判分**显示**分数（0–10）；面试反馈默认**不显示**总分 | 刷题是自我练习，分数是反馈的核心价值；面试评估结果受 PRD §4.9 的脱敏约束。两者规则不同，必须在文档中分别写明，避免实现时统一处理 |
