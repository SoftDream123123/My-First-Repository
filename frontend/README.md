# AI 智能面试助手 · 前端

原生 **HTML + CSS + JavaScript**，用 **Vite** 构建。**无 UI 框架、无图表库、无状态管理库**
（PRD §2 的硬约束）。

> ⚠️ **本工程正在按模块重建中。** 2026-09-21 起，`src/` 的视觉语言整体换成
> `standalone.html` 那套「案卷工作台」（此前那套「荧光笔 + 无品牌主色 + Georgia」
> 已被否决）。页面按模块一批批搬进来，**已落地的页面见下方「当前进度」**。
> 未落地的页面不在路由表里 —— 点不到，也不会点进去报错。

---

## 运行

**只想打开看 / 演示**：双击项目根目录的 [`一键启动.bat`](../一键启动.bat)。
它会构建本目录、启动后端，并让后端托管 `dist/` —— 一个进程、一个地址
<http://127.0.0.1:8000>，不需要 `npm run dev`。详见
[如何打开项目.md](../如何打开项目.md)。

> ⚠️ `index.html` 和 `dist/index.html` **都不能双击打开**：它们是 ES 模块，
> 浏览器在 `file://` 下按 CORS 策略拒绝加载，双击是白屏。必须走 `http://`。
>
> 例外的只有 `standalone.html` —— 单文件、内嵌内存 mock，双击能开。

下面的命令是开发时用的。

**前置**：Node.js ≥ 22.12（推荐 24 LTS）、后端已在 `localhost:8000` 运行。

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Vite 把 `/api` 代理到 `http://localhost:8000`，因此前端代码一律使用相对路径，
**不需要处理 CORS**（module-07 §7）。

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器（5173） |
| `npm test` | Vitest 单测：三组纯函数（路由守卫 / SSE 分帧 / 雷达几何） |
| `npm run build` | 构建到 `dist/` |
| `npm run preview` | 预览构建产物 |

**后端启动**（另一个终端，`backend/` 目录）：

```bash
python -m uvicorn app.main:app --port 8000 --workers 1
# 首次需先建库并 seed 管理员
python scripts/seed_admin.py
```

> `--workers 1` 是硬性要求：评估的 SSE 运行注册表是进程内的，多 worker 会让
> `POST /evaluate` 与 `GET /evaluation/stream` 落在不同进程而无法衔接。

接口契约见 [`docs/apis/API接口文档.md`](../docs/apis/API接口文档.md)。

---

## 设计决策

**`standalone.html` 顶部的令牌块是设计的唯一真相**，`src/styles/tokens.css` 与它
逐字一致。改一边必须同时改另一边。四条规则：

**1. 深墨蓝的脊 + 纸白的工作区。** 脊管身份与导航，工作区管内容。

**2. 品牌靛蓝只用于「身份与操作」；分数色带只用于「评分」；灰阶用于一切结构。**
三者不混用 —— 蓝色出现的地方一定可以点，彩色出现的地方一定带信息。
分数色带的阈值 **6.5** 不是拍出来的，它取自 module-04 §4.4 对 `strengths` 的定义。

**3. 面板是纸**（白底 + 1px 边 + 8px 圆角，**无投影**）；只有真正浮起来的层
（弹窗 / toast / 下拉）才有投影。这是对「SaaS 卡片套件」的回避。

**4. 数字用衬线、右对齐、tabular。** 报表里的数字要能列对齐 —— Cambria 的活字数字
而不是 Georgia 的老式数字（3/4/7 下沉，读起来像手写）。

### 几条落到代码里的推论

- **岗位与面试详情是「列表 + 案卷」而不是表格。** JD 是成段的文字、评估维度是一组
  标签，塞进表格单元格只能靠截断与展开行 —— 左侧选，右侧读全文。
- **导航项从路由表派生。** 两份清单分开维护必然漂移；而且候选人脊上不该出现 HR 的
  入口（反之亦然），按端过滤是必须做的事。
- **候选人的状态标签只有两态上色**（待作答 / 有反馈），其余一律灰。候选人不看分数，
  分数色带也就不该出现 —— 颜色是数据的函数，不是装饰。

---

## 当前进度

`src/` 里**已经落地**的页面：

| 端 | 路由 | 页面 | 状态 |
|---|---|---|---|
| HR | `#/login` | 登录（三角色同一入口，按 `role` 分流） | ✅ |
| HR | `#/interviews` | 面试列表（表格 + 状态/进度 + 创建并同步出题）**← HR 默认落地页** | ✅ |
| HR | `#/interviews/:id` | 面试详情（题目导航 + 单题编辑 + 自动保存 + 状态机 + 邀请 + 简历只读 + 补题） | ✅ |
| HR | `#/interviews/:id/evaluation` | 评估报告：SSE 流式评分 + 雷达图 + 报告 + 导出 DOCX/PDF | ✅ |
| HR | `#/interviews/:id/prep` | 面试前准备助手：提纲（分钟刻度）+ 考察重点 + 问题预案，可编辑 / 打印 | ✅ |
| HR | `#/positions` | 岗位：列表 + 案卷 + 维度编辑器 | ✅ |
| HR | `#/questions` | 题库：六项筛选 + 题型/选项/参考答案表单 + AI 生成参考答案 | ✅ |
| HR | `#/users` | 用户管理（仅 admin） | ✅ |
| 候选人 | `#/candidate/login` | 登录 / 注册（同页切换，注册成功自动登录） | ✅ |
| 候选人 | `#/candidate/activate` | 凭邀请码激活并绑定面试（**本端唯一的 open 路由**） | ✅ |
| 候选人 | `#/candidate/interviews` | 我的面试（待你作答 / 我的记录两块）**← 候选人默认落地页** | ✅ |
| 候选人 | `#/candidate/interviews/:id` | 在线作答（逐题 + 自动保存 + 交卷） | ✅ |
| 候选人 | `#/candidate/interviews/:id/feedback` | 脱敏反馈（结论 / 优点 / 待改进） | ✅ |
| 候选人 | `#/candidate/practice` | 刷题：六项筛选 + 实时题量 + 继续/历史练习 | ✅ |
| 候选人 | `#/candidate/practice/:id` | 练习作答：整卷铺开 + 即时判分 + 重判 + 结束 | ✅ |
| 候选人 | `#/candidate/wrong-book` | 错题本（按题去重 + 错 N 次） | ✅ |
| 候选人 | `#/candidate/stats` | 练习统计（按维度 / 题型的正确率条） | ✅ |

**HR 端与候选人的「面试链路 + 刷题」都已落地。** 尚未搬进来的只剩**我的简历**
（简历增删改查、把简历关联到面试、刷题时按简历推荐及其降级提示）。

未落地的页面**没有被写进 `src/router.js` 的路由表**，因此 nav 上不会出现、
地址栏直接输也进不去（会被送去本端默认页）。这是刻意的：路由表里放一行
点进去就报错的路由，比缺一个入口更难查。

> 候选人端在 `src/` 里只剩「我的简历」没落，其余在 `standalone.html` 原型里是**全量覆盖**的。
> 两边的差集就是待搬的清单。

### 两端如何共存

同一个浏览器里**两个端可以同时登录**（`hr.*` / `candidate.*` 分开存，PRD §9）。
登录端点是三个角色共用的，因此**HR 登录页收到候选人账号会把他送到候选人端**，
反之候选人登录页收到 HR 账号会明确拒绝。

> 候选人端**没有**激活入口在导航上：激活是一次性动作，入口放在登录页与「我的面试」的空态里。

---

## 目录

```
frontend/
  index.html                  Vite 入口（只 link 四个 CSS，不开第五个）
  vite.config.js              /api 代理 + Vitest 配置
  package.json                仅 vite 与 vitest
  src/
    main.js                   入口（两行）
    app.js                    装配：页面注册表、统一 401、启动前刷新用户信息
    router.js                 路由表 + 导航守卫（守卫决策是纯函数）
    api.js                    HTTP 封装（JWT 注入 / 统一错误 / 401 / 204 / SSE / 下载）
    sse.js                    SSE 报文的纯解析（分帧、跨块缓冲、心跳注释）
    session.js                登录态存储（按端分 key：hr.* / candidate.*）
    auth.js                   登录态语义（isAdmin / logout / refreshUser）
    dom.js                    DOM 助手 —— 把 XSS 约束结构化
    components/               shell（脊 + 顶栏 + 展示件 + 状态轨 + 状态翻译 + 单选复盘）· radar · modal · toast · form
    pages/                    login · interviews · interview-detail · evaluation · interview-prep
                              · positions · questions · users
                              · candidate-login · candidate-activate · candidate-interviews
                              · candidate-interview-detail · candidate-feedback
                              · candidate-practice · candidate-practice-session
                              · candidate-wrong-book · candidate-stats
    styles/                   tokens / base / components / pages（含打印样式）
    __tests__/                router.test.js · sse.test.js · radar.test.js
                              · candidate-state.test.js · practice-grading.test.js
  standalone.html             原型单文件快照（手工维护，见下）
  mock/                       Mock 联调测试（浏览器端，见「单测」一节）
  .screenshots/               设计记录（25 张：HR 侧 12 + 候选人侧 13）
```

### 关于 `standalone.html`

它是**原型阶段的单文件快照**：数据来自内存 mock，双击即可打开，用于给别人演示设计。
**它不是本工程的构建产物，也不参与 `npm run build`**。

它是**手工维护的设计交付物**（覆盖面为 HR 侧 + 候选人侧全量），也是
**`src/` 重建时的设计依据** —— 两者的令牌与组件层逐字对齐，页面在搬进 `src/` 时
把 `mock.js` 换成真实 `/api` 调用。生成它的 `tools/build-standalone.py` 已在
`01a7d20` 中删除。

### 为什么不用 `EventSource`

它**无法设置自定义请求头**，而本项目的鉴权完全依赖 `Authorization: Bearer`。
把 JWT 放进 query string 会让令牌进入服务器访问日志、代理日志与浏览器历史 ——
这是可以避免的泄露面。SSE 用 `fetch` + `ReadableStream` 手工解析协议：
分帧与跨块缓冲在 `sse.js`（纯函数、有单测），连接循环在 `api.js` 的 `stream()`。

> ⚠️ **重连会从头重放**，这是设计特性而不是缺陷（API 文档 §9.2）。
> 评估页因此**按 `interview_question_id` 覆盖**而不是「来一条加一条」——
> 追加过一次就会看到进度翻倍（`evaluation-harness` 专门喂了一份重放报文钉住它）。

### `dom.js` 为什么存在

module-07 §6 要求「所有后端数据用 `textContent` 渲染，禁止 `innerHTML`」。
与其靠自觉，不如让代码里**根本不存在**写 HTML 的入口 —— 所有文本只经
`el(tag, { text })` 一条路径写入。全部源码里 `innerHTML` 出现 0 次。

### `session.js` 为什么单独成模块

`api.js` 需要 token 注入请求头，而 `auth.js` 需要 api 刷新用户信息 —— 两者互相依赖。
把存储键单独成模块即可打断这个环，同时保证键名只有一处定义。

### `app.js` 与 `main.js` 为什么分开

浏览器侧的 Mock 测试台要用**同一份页面注册表**启动真实路由。抄一份的代价是
「新增页面时测试台悄悄漏掉它」。`main.js` 因此只剩两行。

---

## 单测与 Mock 联调

前端能测的东西分两层，各用各的工具。

### 1. Vitest —— 纯函数（`npm test`）

| 文件 | 覆盖 |
|---|---|
| `src/__tests__/router.test.js` | 路由匹配（含段数不等不吃掉子路径）、默认落地页（adminOnly 不成为非管理员的落地页）、守卫决策（公开页 / 未登录 / 角色不符 / 改道到自己时的空转）、裸入口与未知 hash 的按端分流 |
| `src/__tests__/sse.test.js` | 分帧（`LF LF` 与 `CRLF CRLF` 两种）、**跨块缓冲**（含逐字节喂入）、多行 data、**心跳注释必须静默丢弃**、畸形 JSON 不让流崩掉 |
| `src/__tests__/radar.test.js` | 首顶点在正上方、相邻维度均分整圈、半径与分数成正比、0 分落圆心、越界夹取、**缺维度不封口**、标签按方位对齐、6.5 阈值是 `>=` |
| `src/__tests__/candidate-state.test.js` | 候选人四态翻译：进行中→待作答、已交卷→已交卷、**已评估优先于已交卷**（否则交过卷又被评估的场次拿不到反馈入口）、**未交卷但已被 HR 收口 → 已结束而不是待作答**（那是句假话）、四态取值封闭 |
| `src/__tests__/practice-grading.test.js` | 判分结果的两处读取：参考答案**按题型二选一**（单选 `correct_answer` / 简答 `reference_answer`，只读 `reference_answer` 会让单选复盘悄悄丢答案）、响应形状不对时不抛异常；正确率显示 —— **`0` 是「0%」而不是「—」**（真考了 0 分与没数据是两件事） |

**守卫决策抽成纯函数**是刻意的：它的错法都很安静 —— 少一次重定向就是白屏，
多一次就是「点了没反应」，而在浏览器里要靠手工构造登录态才能复现。
抽出来之后，这些边界就是几行断言。

不引入 jsdom / testing-library（module-07 §8.1 的既有决策）。

### 2. 浏览器端 Mock 联调（`npm run dev` 后打开）

| 测试台 | 断言 | 覆盖 |
|---|---:|---|
| `mock/auth-harness.html` | 44 | 登录分流（三角色）、会话失效 vs 凭据不符的区分、按端分 key、退出只清本端、守卫真的执行了、统一 401、注册表与路由表一一对应 |
| `mock/users-harness.html` | 47 | 列表、自身行保护、字段级校验、400/409、二次确认、加载失败 |
| `mock/positions-harness.html` | 48 | 列表 + 案卷、**模糊搜索走服务端 `keyword`**、搜到 0 条时搜索框仍在、维度编辑器校验、`PUT` 全量替换而非追加、删除保护 |
| `mock/interviews-harness.html` | 101 | **启动真实路由**，所以「点一行 → 进详情页」是真的走了一遍守卫与切页。列表：状态标签与进度、主操作按状态命名；详情：状态轨、题目导航（已答/待答、打开时定位到第一道未答）、失焦自动保存（**没改就不发请求**、提交的是 `interview_question_id`）、只读锁定、状态机给哪几个按钮、简历未关联是 404 而非报错、补题的三种结果（0 条 / 有新增 / 502）、邀请的生成与撤销 |
| `mock/prep-harness.html` | 68 | **字段名契约**（假后端按 Pydantic 的行为校验请求体：缺字段就 400 并点名，而不是来什么收什么）、`seq` 在 PUT 里重编不留空洞、分钟刻度累计、`notes` 是字符串而非数组、增删条目、本地校验拦住必然 400 的提交、重新生成的二次确认与整体覆盖、AI 失败不动旧内容、完成后冻结但阅读不受影响、导出走 `window.print()` |
| `mock/evaluation-harness.html` | 61 | **事件契约**（`question` / `dimension` / `report` / `done` / `error`，刻意把报文切到 5 字节一块以逼出跨块缓冲）、心跳注释被丢弃、**重连重放不翻倍**（按 id 覆盖而非追加）、缺维度不封口、断流不被说成失败、状态机失败后回到可重试态、导出 DOCX 的中文文件名（RFC 5987）与「改用 PDF」提示、`window.print()` |
| `mock/questions-harness.html` | 83 | 六项筛选的参数名与 AND 关系、**分类下拉在首次加载后就有值**、三种来源标签（含 `resume_match`）、题型切换改表单结构、维度跟随岗位、单选的选项/答案约束逐条、`source` 不由客户端提交、**简答必须传 `options: []` 而不是省略**、AI 生成的成功/502/409 与「失败不改动题目」、删除保护 |
| `mock/candidate-harness.html` | 94 | 候选人面试链路全量：**未登录进候选人页跳的是候选人登录页**（不是 `#/login`）、HR 账号走错入口被拒且不写候选人登录态、注册走两步（register→login）、**自助注册被关闭时翻成「凭邀请码进入」那一版**而不是弹报错、邀请激活（**未登录可进**；已登录时不重复登录）、**密码不符的 401 落在密码字段上**、激活 409 三种原因原样展示、我的面试的两块分组与状态标签、**交卷前先 flush 未保存内容且保存失败就中止交卷**、已交卷/已收口时输入框只读且不说「会自动保存」、反馈 summary 无总分而 full 有、**任何档位都没有雷达图/逐题分**、未评估 409 用空态而非报错样式、**先开 HR 页再切候选人页时请求带的是候选人 token**（时序）、退出登录只清本端 |
| `mock/practice-harness.html` | 76 | 刷题全链路：岗位下拉来自 `/candidate/positions` 且带题量、**分类/维度下拉从实际题池派生**、实时「符合条件 N 题」、**筛到 0 题时计数变警示色并禁用开始按钮**、开始练习的请求体只带选中的筛选（**不含 `resume_id`**）、409 后**筛选条件不被重置**、**题库为空时两颗「开始练习」共享同一份可用状态**（不同步就是「按了没反应」）、整卷铺开、**未判分显示为中性态而不是「答错」**且不显示分数、**单选题提交后正确答案被标出**（答案在 `correct_answer` 里）、**提交只重画被提交的那一道**（断言的是同一个节点、内容还在）、重判成功后入口消失、结束前二次确认并如实报出还差几题、小结**必须**单独报出未判分数、**错题本不渲染空的维度/题型下拉**、统计页**没有雷达图**、正确率为 `null` 时显示「—」 |

每个测试台拦截 `window.fetch` 当假后端，然后**驱动 `src/` 里的真实页面代码**，
把结果渲染到右上角面板并写进 `document.title`（`MOCK-ALL-PASS n` / `MOCK-FAIL n/m`），
因此无头浏览器也能直接抓结果：

```bash
msedge --headless=new --virtual-time-budget=30000 \
  --dump-dom http://localhost:5173/mock/auth-harness.html
```

`mock/` 不参与 `npm run build`，不会进入 `dist/`。

**每个模块都做过变异检查**（沿用后端测试报告 §6.2 的手法）：把缺陷植回去，
断言必须失败。至今二十四次：

| 模块 | 植入的缺陷 | 结果 |
|---|---|---|
| 地基 | 摘掉 `adminOnly` 守卫 | 单测 2 条红 + `auth-harness` 3 条红 ✅ |
| 地基 | `session` 不再按端分 key | `auth-harness` 4 条红（正好是与分端有关的那 4 条）✅ |
| 地基 | 岗位搜索改回本地过滤（不带 `keyword`） | `positions-harness` 4 条红 ✅ |
| 题库 | 分类下拉只在渲染开始时算一次 | `questions-harness` 1 条红（正是那一条）✅ |
| 题库 | 简答题的 `options` 传 `undefined` 而不是 `[]` | `questions-harness` 1 条红（正是那一条）✅ |
| 题库 | 条件分区改回原生 `append`（把 `null` 拼进 DOM） | `questions-harness` 1 条红（正是那一条）✅ |
| 面试 | 打开详情时不再定位到第一道未答的题 | `interviews-harness` 4 条红 ✅ |
| 面试 | 回答不再按状态锁定（已完成也能改） | `interviews-harness` 4 条红 ✅ |
| 评估 | **事件名退回原型的 `question_score`** | `evaluation-harness` 11 条红 ✅ |
| 评估 | 维度没到齐也把雷达封口 | 单测 1 条红 + `evaluation-harness` 1 条红 ✅ |
| 准备 | **PUT 提交体退回原型的字段名**（`minutes`/`points`/`focus`/`followups`） | `prep-harness` 7 条红 ✅ |
| 准备 | 只读视图也按原型的字段名读 | `prep-harness` 4 条红 ✅ |
| 候选人 | 状态翻译把「已交卷」判在「已评估」之前 | 单测 1 条红 + `candidate-harness` 2 条红 ✅ |
| 候选人 | 激活页不再标 `open`（未登录就进不去） | `candidate-harness` 3 条红 ✅ |
| 候选人 | HR 登录页把候选人账号存进 `hr.*` | `auth-harness` 4 条红 ✅ |
| 候选人 | 交卷前不再 flush 未保存的内容 | `candidate-harness` 3 条红 ✅ |
| 候选人 | 作答通道不再按状态锁定（已交卷也能改） | `candidate-harness` 6 条红 ✅ |
| 刷题 | **参考答案只读 `reference_answer`**（原型那一版，单选会丢答案） | 单测 3 条红 + `practice-harness` 1 条红 ✅ |
| 刷题 | 未判分（`null`）被当成「答错」渲染 | `practice-harness` 1 条红 ✅ |
| 刷题 | 提交后整卷重画（清掉别处写了一半的内容） | `practice-harness` 1 条红 ✅ |
| 刷题 | 改动筛选时不再刷新「符合条件 N 题」 | `practice-harness` 3 条红 ✅ |
| 刷题 | 错题本的题型判定失效（一律当简答） | `practice-harness` 2 条红 ✅ |
| 刷题 | `percent` 把 `0` 当成「没有数据」 | 单测 1 条红 ✅ |
| 刷题 | 题库为空时只禁用筛选栏那颗「开始练习」（空态那颗不同步） | `practice-harness` 1 条红 ✅ |

> 这套测试至今抓到**五个真 bug**，另有五处**原型与真实契约对不上**：
>
> 1. **岗位搜索搜到 0 条时，搜索框会跟着空态一起消失** —— 用户既看不到「为什么是空的」，
>    也没有地方把词改回去。已改成「有搜索词就保留左栏」。
> 2. **`decide()` 里 `deny` 分支的改道目标另算了一遍**，与调用方传进来的 `target`
>    不一致 —— 同一个概念在两处各算一次，迟早会漂。
> 3. **题库的「分类」下拉永远只有「全部分类」一项** —— 分类是自由文本，取值只能从
>    已加载的题目里派生，而原型在 `questions` 还是空数组时就把这份清单算完了。
>    等于这个筛选项自始至终没生效过。
> 4. **题库案卷在稀疏的题上会渲染出字面量 `null`** —— 选项 / 解析 / 标签这几个分区是
>    条件渲染的，为假时传的是 `null`，而 `dossier.append(...)` 用的是**原生** `append`，
>    它把 `null` 变成了文本节点。`dom.js` 的 `append()` 会跳过 `null`，但那一处没走它。
>    前三个是跑断言发现的，这一个**是看截图看出来的** —— 断言当时是绿的。
> 5. **评估跑完后状态轨仍停在「评估中」** —— 状态轨是回答「现在到哪了」的那一条，
>    而它在挂载时按当时的状态画好之后就不再重画。收到 `done` 时动作栏换了、
>    状态轨没换，于是它对着使用者说谎，刷新一下才对得上。
>    （`evaluation-harness` 抓到；这个是搬原型时就带着的，原型同样只挂载不重画。）
>
> ⚠️ 第 3、4 两个 bug **原型 `standalone.html` 里同样存在**，尚未修（它是设计快照）。
> 搬后续页面时留意同类写法：`questions.js` 已在搬入 `src/` 时一并修掉。
>
> **另外五处不是「bug」而是「原型的 mock 与真实后端对不上」** —— 原型当年是照
> 自己写的内存 mock 开发的，两边一起错所以自洽，但照搬进 `src/` 会直接不工作：

| 位置 | 原型写的 | 真实契约 | 照搬的后果 |
|---|---|---|---|
| 评估页的 SSE 事件名 | `stage` / `question_score` / `dimension_score` | `question` / `dimension` / `report` / `done` / `error`（API 文档 §9.2） | 一条进度都收不到，界面只表现为「一直转圈」 |
| 准备提纲的字段 | `minutes` / `points[]` / `focus` / `followups`，且 PUT 不带 `seq` | `duration_min` / `notes`（字符串）/ `point` / `follow_ups` / `seq` 必填（`app/interview/schemas.py`） | **保存必然 400，读取全是空白** |
| 激活页的流程与文案 | 先 `login` → 失败再 `register` → 再 `login`，然后才 `accept`；字段说明写「账号已存在时这个密码会被忽略」 | `accept` 是**公开端点**，账号由请求体决定，**已存在的候选账号必须密码对得上**（2026-09-21 修正，API 文档 §10.2） | ① 邀请码无效时那个先建出来的账号**会留下**（孤儿账号）；② 界面告诉用户「密码不会被校验」，而实际会——把人引向一个必然失败的提交 |
| 刷题提交作答的参考答案 | 只读 `reference_answer` | **按题型二选一**：单选在 `correct_answer`、简答在 `reference_answer`（API 文档 §13.22） | **单选题的复盘永远标不出正确答案**。不报错、不影响判分，只是那一栏空着 —— 所以它特别难被发现（已抽成 `referenceAnswerOf` 并有单测钉死） |
| 错题本条目的维度与题型 | 读 `row.dimension` / `row.question_type` 来填下拉与标签 | `WrongBookItem` **没有这两个字段**（`app/practice/schemas.py`） | 渲染出一排空标签 + 两个只有「不限」一项的下拉 |

> **前四处**已经按真实契约写上，并在测试台里钉死（评估那份把报文切到 5 字节一块、
> 准备那份让假后端按 Pydantic 的行为校验请求体、候选人那份**断言页面里不再出现
> 「会被忽略」这句话**、刷题那份**断言单选题的正确答案被标出来**）。
> **搬最后一个页面（我的简历）时先核对契约，不要直接抄原型的字段名。**

> ⚠️ **第 5 处不是「原型抄错」，是后端少给了字段。** 端点 `GET /practice/wrong-book`
> **接受** `dimension` 与 `question_type` 两个筛选参数（§12.8），却**不下发**这两个字段 ——
> 于是前端既取不到下拉的候选值，也没法在条目上标出维度与题型。
> 本轮的取舍是：**错题本不做这两个筛选**（条目本身是完整可用的），而不是塞两个
> 只有「不限」一项的下拉、或用另一种口径的数据去凑候选值（那会造出「下拉里有它、
> 选了却没结果」的矛盾）。**补上这两个字段之后**，筛选与标签都是十几行的增量。
>
> 这条属于「先改 PRD 再改计划」的那类改动，需要你决定做不做。

### 一条测试方法上的教训（与后端报告 §6.3 同一类）

候选人登录页上有**两个**写着「登录」的按钮：模式切换的分段控件，和表单的提交按钮。
测试台一开始用 `buttonIn(page(), '登录')` 取按钮 —— 它返回的是**文档顺序靠前**的
那个，也就是分段控件。于是「点一下登录」实际只是又切了一次模式，而紧跟着的
「不发请求」断言**也因为确实没发请求而通过**。两条断言全绿，但什么都没测到。

改成按 `button[type="submit"]` 取之后，同一段代码立刻开始真的提交。
现在这个取值方式被封在 `submitBtn()` 一个助手里，并写明了原因 ——
**取元素的方式本身要能被审查，否则「绿」只是「没测」的另一种说法。**

---

## 已知限制

- **仅 PC**：按 1280px+ 设计，不写媒体查询（PRD §2）
- **`src/` 尚缺**：「我的简历」（简历增删改查 + 关联到面试 + 刷题时按简历推荐及其
  降级提示）。除此之外两端页面都已落地。
- **错题本没有维度 / 题型筛选**：`WrongBookItem` 不下发这两个字段（见上一节第 5 条）。
- **评估必须单 worker 部署**：运行注册表是进程内的，多 worker 会让
  `POST /evaluate` 与 `GET /evaluation/stream` 落在不同进程（API 文档 §2.1）。
- `standalone.html` 与 `src/` 是**两套东西**：前者是手工维护的设计交付物
  （覆盖两端全量），后者是真实应用（正在按模块重建）。原型里已落地、`src/` 里
  还没搬的页面，**以原型为准**；但字段名与流程**以接口文档为准**（见上一节）。
