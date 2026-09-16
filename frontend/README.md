# 前端 UI 原型

AI 智能面试助手 · HR 后台的**高保真静态原型**。

> **这是什么**：视觉与交互的设计验证件，不是生产前端。
> 生产前端按 [module-07 计划书](../docs/superpowers/specs/2026-09-15-module-07-frontend-plan.md) 用 Vite 构建，
> 本目录的**页面代码、DOM 助手、SSE 解析器与雷达图可以直接复用**（见下）。

---

## 怎么看

### 方式一：双击（推荐）

双击 **`standalone.html`** —— 单文件版本，不需要任何服务器，浏览器直接打开即可。

### 方式二：本地服务器

```bash
cd frontend
python -m http.server 5173
# 打开 http://127.0.0.1:5173
```

### 为什么会有两个入口

`index.html` 用的是 **ES 模块**，而浏览器在 `file://` 协议下会用 CORS 策略拒绝加载它们 ——
直接双击 `index.html` 只会看到一片空白。这是浏览器行为，不是代码问题。

| 文件 | 用途 |
|---|---|
| `standalone.html` | 单文件构建产物。不含 import，因此**双击可用**，也方便发给别人看 |
| `index.html` + `src/` | 真正的源码（模块化）。开发时走 HTTP 服务器；接入 Vite 时用这套 |

`index.html` 内置了一段普通脚本（非模块，因此在 `file://` 下也能执行）：
如果你直接双击它，会看到一句明确的指引，而不是空白页。

> **改了源码后**要重新生成单文件版本：
> ```bash
> python tools/build-standalone.py
> ```

演示账号：`admin` / `admin12345`（任意 ≥4 位的密码都能登录，原型不做真实校验）

### 接真实后端

原型默认走内存 mock。要连本地 FastAPI：

```bash
# 1. 起后端（backend 目录）
python -m uvicorn app.main:app --port 8000 --workers 1

# 2. 浏览器控制台执行，然后刷新
localStorage.setItem('prototype.live', '1')
#  或访问 http://127.0.0.1:5173/?live=1
```

注意：直连时没有 Vite 代理，需要后端 CORS 放开 5173 —— `.env` 里的
`CORS_ORIGINS` 默认已包含它。

> 单文件版同样支持这个开关，但 `standalone.html` 在 `file://` 下发不出跨域请求，
> 直连后端请用方式二的 HTTP 服务器。

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

**6.5 这个阈值不是我拍的** —— 它取自 module-04 §4.4 对 `strengths` 的定义。
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
  standalone.html              单文件构建产物 —— 双击可用（生成物，勿直接编辑）
  index.html                   模块化入口 —— 开发时经 HTTP 服务器访问
  tools/
    build-standalone.py        极小打包器：生成上面的单文件版本
  src/
    main.js                    启动 + 页面静态注册 + 401 统一处理
    router.js                  hash 路由 + 导航守卫 + 页面 destroy 约定
    api.js                     HTTP 封装 + 内存 mock 后端
    auth.js                    登录态（localStorage）
    sse.js                     SSE 客户端（fetch + ReadableStream）
    dom.js                     DOM 助手 —— 把 XSS 约束结构化
    mock.js                    模拟数据（字段与后端响应一一对应）
    components/
      shell.js                 外壳 + 状态轨 + 共享展示件
      radar.js                 Canvas 雷达图
      modal.js                 弹窗 + 二次确认
      toast.js                 消息提示
    pages/                     7 个页面
    styles/                    tokens / base / components / pages
  .screenshots/                设计记录（8 张）
```

### 关于 `tools/build-standalone.py`

本机没有 Node，所以打包器是自己写的（约 150 行 Python）：把
`import { a } from './x.js'` 改写成 `__require('./x.js')`、把 `export function f`
改写为 `function f` + `exports.f = f`，再把每个模块包进独立作用域 ——
最后一点是必须的，因为 7 个页面都导出同名的 `render`，扁平拼接会互相覆盖。

它内置两道自检：模块体里若残留任何 import/export 写法、或导出赋值数量异常，
构建会直接失败，而不是产出一个运行时才报错的坏文件。

### 为什么不用 `EventSource`

它**无法设置自定义请求头**，而本项目的鉴权完全依赖 `Authorization: Bearer`。
把 JWT 放进 query string 会让令牌进入服务器访问日志、代理日志与浏览器历史 ——
这是可以避免的泄露面。所以 `sse.js` 用 `fetch` + `ReadableStream` 自己解析协议。

### `dom.js` 为什么存在

module-07 §6 要求「所有后端数据用 `textContent` 渲染，禁止 `innerHTML`」。
与其靠自觉，不如让代码里**根本不存在**写 HTML 的入口 —— 所有文本只经
`el(tag, { text })` 一条路径写入。

---

## 自审发现并修复的问题

原型是用 Edge 无头截图逐页校验过的。以下问题**只有真正渲染出来才会暴露**：

| # | 问题 | 成因 |
|---|---|---|
| 1 | 页面白屏 | `mock.js` 的 `interviewQuestions` 未导出，`api.js` 读到 undefined |
| 2 | 雷达图左右两侧标签被裁（「文化契合」显示成「化契合」） | 按文档用固定 60px 留白，装不下 4 个汉字 + 26px 偏移。改为**先量文字宽度再定留白** |
| 3 | 岗位表格渲染成 `[object HTMLTableRowElement]` | `buildRow` 返回数组，而原生 `append` 会把数组字符串化。改用 `dom.js` 的 `append`（会 flat 展开） |
| 4 | 岗位描述列撑满整表，评估维度被挤成一字一行 | `.truncate` 的 `max-width` 用在了 `<span>` 上 —— **`max-width` 对行内元素无效** |
| 5 | 「进行中」与「已完成」标签几乎分不出来 | 都是灰底。改为「描边 = 还没落定 / 实底 = 已经落定」 |
| 6 | AI 来源标签用了蓝紫色 | 我自己违反了规则 1 —— 往调色板里塞了第四个色系。改用与状态标签同一套手法 |

另有两处**文案问题**：`张书宁 · 后端工程师 · 8 题` 这类中点分隔的元信息串是
典型的模板化痕迹，已改为分行/自然语序；详情页与报告页顶部的状态标签与状态轨
**信息重复**，已删除。

### 打包器自己的 bug

单文件版本上线前也踩了两个坑，都是**先静态检查、再靠 `file://` 实跑**抓出来的：

| 问题 | 成因 |
|---|---|
| `const * as mock = __require(...)` 语法错误 | `import * as ns` 不能简单套用 `const {clause} =` 模板，命名空间导入要生成 `const ns =` |
| 页面白屏，报 `undefined` | `export async function` 没被导出正则覆盖，模块导出为空 |
| 所有导出为空 | `tail`（`exports.X = X`）算出来了却忘了拼回模块体 —— 这类 bug 不报语法错，只在运行时表现为 undefined |

后两个现在都有构建期自检拦截。

---

## 可复用的部分

以下文件与原型形态无关，接到正式 Vite 工程时**可以原样搬过去**：

- `src/dom.js` —— XSS 安全的 DOM 构造
- `src/sse.js` —— SSE 客户端，含跨块缓冲解析（`splitBlocks` / `parseEventBlock` 是纯函数，可直接单测）
- `src/components/radar.js` —— Canvas 雷达图（`computePoints` 是纯函数，符合 module-07 §4.4 的几何规格）
- `src/router.js` —— 路由与 `destroy()` 契约
- `src/styles/` —— 设计令牌与全部样式

需要重写的是 `api.js`（去掉 mock 分支）与 `mock.js`（删除）。

---

## 已知限制

- **仅 PC**：按 1280px+ 设计，不写媒体查询（PRD §2）
- **无测试**：module-07 §8.1 的 Vitest 单测尚未落地（`splitBlocks` 与 `computePoints` 是首选的被测对象）
- **mock 数据在内存里**：刷新后新增/修改会丢失
- **未做**：在线答题（V1.1）、PDF 导出、报告分享（均为 PRD §11 的 V1.1 范围）
