# AI 智能面试助手 · HR 工作台前端

原生 **HTML + CSS + JavaScript**，用 **Vite** 构建。**无 UI 框架、无图表库、无状态管理库**
（PRD §2 的硬约束）。

---

## 运行

**只想打开看 / 演示**：双击项目根目录的 [`一键启动.bat`](../一键启动.bat)。
它会构建本目录、启动后端，并让后端托管 `dist/` —— 一个进程、一个地址
<http://127.0.0.1:8000>，不需要 `npm run dev`。详见
[如何打开项目.md](../如何打开项目.md)。

> ⚠️ `index.html` 和 `dist/index.html` **都不能双击打开**：它们是 ES 模块，
> 浏览器在 `file://` 下按 CORS 策略拒绝加载，双击是白屏。必须走 `http://`。

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
| `npm test` | Vitest 单测：SSE 分帧解析 + 雷达图几何 |
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

接口契约见 [`docs/apis/API接口文档.md`](../docs/apis/API接口文档.md)（含每个接口的
提交方式 / URL / 参数 / 响应 / 示例，以及前端 SSE 与错误处理的完整实现）。

---

## 设计决策

### 三条贯穿全站的规则

**1. 颜色只出现在有分数的地方。**
全站没有品牌主色 —— 主按钮就是墨色 `#16202B`。唯一的彩色是三种，且都**编码信息**：

| 令牌 | 值 | 含义 |
|---|---|---|
| `--marker` | `#F2C744` | 荧光笔：**你在哪里**（当前状态、当前题目、焦点） |
| `--pass` | `#0E6B5C` | 分数 ≥ 6.5 |
| `--watch` | `#9A6B12` | 分数 < 6.5 |

**6.5 这个阈值不是拍出来的** —— 它取自 module-04 §4.4 对 `strengths` 的定义。
颜色因此成了数据的函数，而不是装饰。

**2. 衬线体只说数字。**
分数与总分用 Georgia，中文一律无衬线。Georgia 的老式数字（3、4、7、0 会下沉）
在仪表盘里罕见，给分数一种被"写下"而不是被"打印"的质感。中文若用宋体，
在大字号下会显得单薄 —— 这条规则同时解决了风格与可读性。

**3. 内容块之间只用发丝线分隔，不用投影。**
投影只给真正浮起来的层（弹窗、toast）。这是对"SaaS 卡片套件"的直接回避。

### 结构：状态轨

产品本身有真实的状态机（module-05 §5.4），面试就是一个有顺序的过程。
所以横向状态轨放在每个面试页顶部，回答 HR 每时每刻的问题：**现在到哪了、下一步是什么**。

"当前"那一段用荧光笔划过标签 —— 这是全站唯一的大胆手势，其余一切保持安静。

### 布局：面试详情是两栏

真实面试是**一题一题走的**，长滚动列表是错的。左侧是题目导航（定位"问到第几题"），
右侧只放当前一题。序号在这里是真实顺序（`seq` 1..8），不是装饰性编号。

---

## 目录

```
frontend/
  index.html                  Vite 入口
  vite.config.js              /api 代理 + Vitest 配置
  package.json                仅 vite 与 vitest
  src/
    main.js                   启动、页面静态注册、401 统一处理、启动前刷新用户信息
    router.js                 hash 路由 + 导航守卫 + 页面 destroy 约定
    api.js                    HTTP 封装（JWT 注入 / 统一错误 / 401 / 204）
    session.js                登录态存储（token 与用户信息的唯一读写处）
    auth.js                   登录态语义（isAdmin / logout / refreshUser）
    sse.js                    SSE 客户端 + 纯函数解析器（splitBlocks / parseEventBlock / parseChunk）
    dom.js                    DOM 助手 —— 把 XSS 约束结构化
    components/               shell（外壳 + 状态轨）· radar · modal · toast · form（字段级报错）
    pages/                    7 个页面
    styles/                   tokens / base / components / pages
    __tests__/                sse.test.js · radar.test.js
  standalone.html             原型单文件快照（手工维护，见下）
  mock/                       Mock 联调测试（浏览器端，见「单测」一节）
  .screenshots/               设计记录（12 张，拍自 standalone.html）
```

### 关于 `standalone.html`

它是**原型阶段的单文件快照**：数据来自内存 mock，双击即可打开，用于给别人演示设计。
**它不是本工程的构建产物，也不参与 `npm run build`** —— 真实应用走
[`一键启动.bat`](../一键启动.bat)（后端托管 `dist/`）或 `npm run dev`。

它现在是**手工维护**的设计交付物（覆盖面为 HR 侧 + 候选人侧全量），不再是构建产物 ——
生成它的 `tools/build-standalone.py` 已在 `01a7d20` 中删除。

> ⚠️ **原型与 `src/` 目前是两套视觉语言。** 下面「设计决策」三条规则描述的是
> `src/`（荧光笔 + Georgia + 无品牌主色）。原型自 2026-09-21 起改用另一套
> 「案卷工作台」语言：深墨蓝脊 + 纸白工作区 + 单一品牌靛蓝（只管身份与操作）
> + 分数色带（只管评分）+ 灰阶（管结构），数字用 Cambria 衬线右对齐。
> **原型的令牌以 `standalone.html` 顶部注释为唯一真相。** 两套是否收敛，另行决定。

### 为什么不用 `EventSource`

它**无法设置自定义请求头**，而本项目的鉴权完全依赖 `Authorization: Bearer`。
把 JWT 放进 query string 会让令牌进入服务器访问日志、代理日志与浏览器历史 ——
这是可以避免的泄露面。所以 `sse.js` 用 `fetch` + `ReadableStream` 自己解析协议。

### `dom.js` 为什么存在

module-07 §6 要求「所有后端数据用 `textContent` 渲染，禁止 `innerHTML`」。
与其靠自觉，不如让代码里**根本不存在**写 HTML 的入口 —— 所有文本只经
`el(tag, { text })` 一条路径写入。全部源码里 `innerHTML` 出现 0 次。

### `session.js` 为什么单独成模块

`api.js` 需要 token 注入请求头，而 `auth.js` 需要 api 刷新用户信息 —— 两者互相依赖。
把存储键单独成模块即可打断这个环，同时保证键名只有一处定义。

---

## 单测

`npm test` 覆盖两个**几何 / 协议类的纯函数模块** —— 它们手写且易错，
出错时表现为"进度条卡住"或"图形画歪"，靠肉眼定位成本高（module-07 §8.1）。

| 文件 | 覆盖 |
|---|---|
| `src/__tests__/sse.test.js` | 分帧、**跨块缓冲**、多行 data、心跳注释、畸形 JSON、逐字节喂入 |
| `src/__tests__/radar.test.js` | 首顶点在正上方、顶点均分、半径与分数成正比、0 分落圆心、满分对齐 radius、维度 < 3 降级、越界夹取 |

页面逻辑（"调 API + 重渲染"）不引入 DOM 测试框架，改用下面的 Mock 联调测试
覆盖（module-07 §8.4 的手工联调清单仍是最后一道关）。

### Mock 联调测试（浏览器端）

```bash
npm run dev
# 然后打开其中之一：
#   http://localhost:5173/mock/users-harness.html        用户管理
#   http://localhost:5173/mock/evaluation-harness.html   评估页（SSE）
#   http://localhost:5173/mock/forms-harness.html        五个页面的表单
```

每个 harness 拦截 `window.fetch` 当假后端，然后**驱动页面里的真实代码**，
把每条断言的结果渲染到右上角面板，并写进 `document.title`
（`MOCK-ALL-PASS n` / `MOCK-FAIL n/m`），因此 headless 浏览器也能直接抓结果：

```bash
msedge --headless=new --virtual-time-budget=30000 \
  --dump-dom http://localhost:5173/mock/evaluation-harness.html
```

| harness | 断言 | 覆盖 |
|---|---:|---|
| `users-harness` | 45 | 列表、自身行保护、字段级校验、400/409、二次确认 |
| `evaluation-harness` | 29 | SSE 分帧**真跑**（真 `ReadableStream`）、断线重连、雷达图生长、报告 |
| `forms-harness` | 45 | 登录 / 岗位 / 题库 / 面试 / 面试详情：内联报错、maxlength、清空确认 |

为什么不用 jsdom：module-07 §8.1 明确不引入 DOM 测试框架，而这些断言的价值恰恰在
DOM 行为（二次确认、字段级报错、按钮禁用）。这个做法不新增依赖，又比手工点一遍可靠。

`mock/` 不参与 `npm run build`，不会进入 `dist/`。

**每个修复都做过变异检查**（沿用后端测试报告 §5.2 的手法）：把缺陷植回去，
断言必须失败。例如把 `modal.js` 的 `busy` 守卫改回来 → `MOCK-FAIL 5/45`；
还原 → `MOCK-ALL-PASS 45`。

> 这套测试抓到的前两个真 bug：
>
> 1. **不在任何模块里，而在 `components/modal.js`** —— `close()` 在 `busy` 时直接
>    return，而没有任何地方把 `busy` 复位，于是**四个页面的创建/编辑弹窗在提交成功后
>    都关不掉**（按钮还被禁用了，只能刷新）。
> 2. **评估页重连时事件重复累加** —— 点「重新连接」没有清空 `state.questions`，
>    服务端从头重放后逐题行翻倍、进度显示 16/8（API 文档 §9.2 专门警告过这一点）。
>
> 两者都不靠"看一眼"能发现 —— 第一个要提交成功后才显形，第二个要先断线再重连。

---

## 已知限制

- **仅 PC**：按 1280px+ 设计，不写媒体查询（PRD §2）
- **未做**：在线答题（V1.1）、PDF 导出、报告分享（均为 PRD §11 的 V1.1 范围）
- `standalone.html` 是冻结快照，与 `src/` 不再同步
