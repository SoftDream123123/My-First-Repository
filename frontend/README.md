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
| `npm test` | Vitest 单测：路由守卫的纯函数 |
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
| HR | `#/positions` | 岗位：列表 + 案卷 + 维度编辑器 | ✅ |
| HR | `#/users` | 用户管理（仅 admin） | ✅ |

**尚未搬进来**：题库、面试列表、面试详情、评估报告、准备助手；
候选人端整体（登录/激活/刷题/我的面试/在线答题/反馈/错题本/统计/简历）。

未落地的页面**没有被写进 `src/router.js` 的路由表**，因此 nav 上不会出现、
地址栏直接输也进不去（会被送去本端默认页）。这是刻意的：路由表里放一行
点进去就报错的路由，比缺一个入口更难查。

> 候选人端在 `src/` 里整体不存在，但在 `standalone.html` 原型里是**全量覆盖**的。
> 两边的差集就是待搬的清单。

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
    api.js                    HTTP 封装（JWT 注入 / 统一错误 / 401 / 204）
    session.js                登录态存储（按端分 key：hr.* / candidate.*）
    auth.js                   登录态语义（isAdmin / logout / refreshUser）
    dom.js                    DOM 助手 —— 把 XSS 约束结构化
    components/               shell（脊 + 顶栏）· modal · toast · form（字段级报错）
    pages/                    login · positions · users
    styles/                   tokens / base / components / pages
    __tests__/router.test.js  路由守卫纯函数单测
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
这是可以避免的泄露面。SSE 用 `fetch` + `ReadableStream` 手工解析协议，
在评估模块落地时随 `api.js` 一起补上。

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

**守卫决策抽成纯函数**是刻意的：它的错法都很安静 —— 少一次重定向就是白屏，
多一次就是「点了没反应」，而在浏览器里要靠手工构造登录态才能复现。
抽出来之后，这些边界就是几行断言。

不引入 jsdom / testing-library（module-07 §8.1 的既有决策）。

### 2. 浏览器端 Mock 联调（`npm run dev` 后打开）

| 测试台 | 断言 | 覆盖 |
|---|---:|---|
| `mock/auth-harness.html` | 42 | 登录分流（三角色）、会话失效 vs 凭据不符的区分、按端分 key、退出只清本端、守卫真的执行了、统一 401、注册表与路由表一一对应 |
| `mock/users-harness.html` | 47 | 列表、自身行保护、字段级校验、400/409、二次确认、加载失败 |
| `mock/positions-harness.html` | 48 | 列表 + 案卷、**模糊搜索走服务端 `keyword`**、搜到 0 条时搜索框仍在、维度编辑器校验、`PUT` 全量替换而非追加、删除保护 |

每个测试台拦截 `window.fetch` 当假后端，然后**驱动 `src/` 里的真实页面代码**，
把结果渲染到右上角面板并写进 `document.title`（`MOCK-ALL-PASS n` / `MOCK-FAIL n/m`），
因此无头浏览器也能直接抓结果：

```bash
msedge --headless=new --virtual-time-budget=30000 \
  --dump-dom http://localhost:5173/mock/auth-harness.html
```

`mock/` 不参与 `npm run build`，不会进入 `dist/`。

**每个模块都做过变异检查**（沿用后端测试报告 §6.2 的手法）：把缺陷植回去，
断言必须失败。本轮三次：

| 植入的缺陷 | 结果 |
|---|---|
| 摘掉 `adminOnly` 守卫 | 单测 2 条红 + `auth-harness` 3 条红 ✅ |
| `session` 不再按端分 key | `auth-harness` 4 条红（正好是与分端有关的那 4 条）✅ |
| 岗位搜索改回本地过滤（不带 `keyword`） | `positions-harness` 4 条红 ✅ |

> 这套测试当轮就抓到两个真 bug：
>
> 1. **岗位搜索搜到 0 条时，搜索框会跟着空态一起消失** —— 用户既看不到「为什么是空的」，
>    也没有地方把词改回去。改为「有搜索词就保留左栏」。
> 2. **`decide()` 里 `deny` 分支的改道目标另算了一遍**，与调用方传进来的 `target`
>    不一致 —— 同一个概念在两处各算一次，迟早会漂。

---

## 已知限制

- **仅 PC**：按 1280px+ 设计，不写媒体查询（PRD §2）
- **`src/` 尚缺**：题库 / 面试 / 评估 / 准备助手 / 候选人端整体（见「当前进度」）
- **候选人账号不能在 HR 登录页登录**：会明确告知「这是 HR 工作台」并拒绝，
  不写登录态 —— 候选人端页面尚未落地，存下 token 也无处可去。
  候选人端搬进来时这一条要改成跳 `#/candidate/*`。
- `standalone.html` 与 `src/` 是**两套东西**：前者是手工维护的设计交付物
  （覆盖两端全量），后者是真实应用（正在按模块重建）。原型里已落地、`src/` 里
  还没搬的页面，**以原型为准**。
