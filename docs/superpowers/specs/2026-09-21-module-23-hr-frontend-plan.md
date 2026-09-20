# HR 前端增量执行计划书（MVP-3 简历、准备助手、报告导出）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：frontend HR 端 **MVP-3 增量**（简历只读区、按简历补题、面试前准备助手页、报告导出 DOCX / PDF）
**所属工程**：`frontend/`（**同一 Vite 工程内**，不新建工程）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.4（补题理由展示）、§4.10（HR 只读候选人简历）、§4.11（准备助手）、§4.12（报告导出）、§2（不新增依赖）
**前置依赖**：[module-07 HR 前端](./2026-09-15-module-07-frontend-plan.md)、[module-19 interview](./2026-09-21-module-19-interview-plan.md)、[module-21 evaluation 导出](./2026-09-21-module-21-evaluation-export-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **同一 Vite 工程内**；**不新建工程、不换框架、不加构建产物**（§2、§3.1）
- 无 UI 框架、无图表库；原生 HTML + CSS + JS（§2）
- **仅 PC 端**，不做移动端响应式（§2）
- **不得新增 CSS 文件**：`index.html` 只 link `tokens/base/components/pages` 四个
- **不得新增任何依赖**（尤其：**不引入 PDF 生成库、不引入 DOCX 前端库**）——PDF 走浏览器打印（§4.12、§2）
- HR 端**不得出现**候选人侧入口；候选人端**不得出现** HR 侧入口（§4.6）
- 报告导出**仅 HR 侧**；候选人脱敏反馈**不导出**（§4.12）
- 准备助手**不进入状态机**；`completed` 及之后不可生成与编辑（§4.11、§5.1）
- 后端错误文案**原样展示**（`error.message`），前端不重写（module-07 §4.1 既有约定）
- `frontend/standalone.html` 已冻结、**不可编辑**（module-07 §1.2）
- **仍是单机 PC 端，技术栈不变**（§2）

> **本模块是 MVP-3 前端改动面最大的一份**，但它仍然**只加一个页面**，其余是在既有页面上做增量。

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| 候选人简历只读区 | 面试详情页展示该面试关联的候选人简历 | §4.10 |
| 按简历补题 | 触发补题、展示本次新增题数与本场总数 | §4.4、§4.14 |
| 匹配理由展示 | 匹配来源的题目显示 `match_reason` | §4.4 |
| 准备助手页 | `#/interviews/:id/prep`：生成 / 查看 / 编辑三部分 | §4.11 |
| 导出 DOCX | 报告页下载 `.docx`（带鉴权头的二进制下载） | §4.12 |
| 导出 PDF | 报告页与准备助手页的浏览器打印 | §4.12 |
| 打印样式 | 全工程**首次**引入 `@media print` | §4.12 |
| 来源标签补全 | `sourceTag` 支持 `resume_match` | §4.4（延伸） |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **准备助手并入面试详情页** | 见 §5.1 的取舍：它内容多、要编辑、要单独打印，独立成页最干净 |
| **后端 PDF 接口** | PRD §4.12 明确 PDF 走浏览器打印。**前端不得调用任何 PDF 相关端点** |
| **DOCX 在前端生成** | 后端已提供（module-21）。前端只负责**下载**，不引入 `docx` 之类的 JS 库 |
| **候选人侧任何文件** | 属 module-22 |
| **简历的编辑 / 删除** | HR **只读**（PRD §4.10）。HR 端**不得出现**任何简历写操作控件 |
| **补题的撤销 / 换题 / 删题** | PRD §4.14 明确不提供撤销；既有系统本就没有删题接口 |
| **匹配理由的历史记录 / 对比** | 只展示当前值 |
| **印刷级排版**（页眉页脚页码、分页控制到小节） | PRD 未要求。打印样式只解决「打印出来别带上导航栏与按钮、图表别被拆页、颜色别被浏览器吃掉」 |
| **导出进度条 / 后台导出** | 单份报告秒级完成 |
| **改动 `standalone.html` / `vite.config.js` / `index.html` / `package.json`** | 无需改动；`standalone.html` 冻结 |

### 1.3 改动面总览

```
新增：  src/pages/interview-prep.js          ← 唯一新增页
        src/__tests__/download.test.js       ← 纯函数单测

修改：  src/api.js               ＋ download() 与 parseContentDisposition()
        src/router.js             ＋ #/interviews/:id/prep
        src/main.js               ＋ 注册 interviewPrep
        src/components/shell.js   ✎ SOURCE_LABELS 加 resume_match；sourceTag 的 title 改三分支
        src/pages/interview-detail.js
                                  ✎ 简历只读区 ＋ 按简历补题 ＋ match_reason ＋ 准备助手入口
        src/pages/evaluation.js   ✎ 导出 DOCX ＋ 导出 PDF
        src/styles/components.css ✎ 打印样式 ＋ 新区块样式
        src/styles/pages.css      ✎ 准备助手页样式

不动：  src/pages/{interviews,positions,questions,users,login}.js
        src/components/{form,modal,toast,radar}.js、dom.js、sse.js、auth.js、session.js
        standalone.html、vite.config.js、index.html、package.json
```

> **`session.js` / `auth.js` 不在改动列**：按端分 key 是 module-15 的职责（候选人端）。本轮 HR 侧不需要它们变化——`hr.*` 键保持不变。

---

## 2. 文件结构

### 2.1 新增文件（**仅 2 个**）

| 文件 | 单一职责 |
|---|---|
| `frontend/src/pages/interview-prep.js` | 面试前准备助手：生成 / 查看 / 编辑 / 打印 |
| `frontend/src/__tests__/download.test.js` | `parseContentDisposition` 的纯函数单测 |

### 2.2 修改的既有文件

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `frontend/src/api.js` | 新增 `download(path)` 与纯函数 `parseContentDisposition(header)` | ⚠️ 既有的 `request()` **只解析 JSON**（`api.js:60-64`），无法处理二进制响应。导出 DOCX 必须另开一条下载通道，且要复用同一套错误形状与 401 处理 |
| `frontend/src/router.js` | HR 路由组加 `#/interviews/:id/prep` | 准备助手页的入口 |
| `frontend/src/main.js` | 注册 `interviewPrep` | 页面注册表是静态的，不注册则路由找不到页面 |
| `frontend/src/components/shell.js` | **`SOURCE_LABELS` 加 `resume_match`；`sourceTag` 的 `title` 改为三分支** | ⚠️ 见 §3.1——不改会把英文枚举值直接显示给用户，并给出**错误的提示文案** |
| `frontend/src/pages/interview-detail.js` | 简历只读区、按简历补题、`match_reason`、准备助手入口 | §4.4、§4.10、§4.11 |
| `frontend/src/pages/evaluation.js` | 导出 DOCX、导出 PDF | §4.12 |
| `frontend/src/styles/components.css` | **`@media print` 全套** + 新区块样式 | 全工程首次引入打印样式（§3.3） |
| `frontend/src/styles/pages.css` | 准备助手页样式 | 沿用既有「页面布局写在 pages.css」的分工 |

**测试文件**

| 文件 | 改动 |
|---|---|
| `frontend/src/__tests__/download.test.js` | **新增**（纯函数） |
| `frontend/mock/evaluation-harness.html` / `.js` | **改**：补导出的手工走查台（沿用 module-07 §8.4 的方式） |

> **前端测试的现实边界**：本工程只测纯函数（`vite.config.js` 的注释明确「只测纯函数 —— 无需 DOM 环境」）。**不得为页面交互引入 jsdom / testing-library**——那是新增依赖（§2）。页面交互走 `mock/*-harness.html` 手工走查。

---

## 3. 关键设计

### 3.1 `sourceTag` 的补全（**最容易漏、且会直接显示给用户**）

**现状**（`shell.js:146-160`）：

```
const SOURCE_LABELS = { bank: '手工', ai: 'AI' };
export function sourceTag(source) {
  return el('span', {
    class: `tag tag--${source}`,
    text: SOURCE_LABELS[source] || source,               ← 兜底是「原样显示 source」
    title: source === 'ai' ? '由 AI 生成并收录进题库' : '手工录入题库',   ← 二分支
  });
}
```

**加入 `resume_match` 后的两个缺陷**

| 缺陷 | 后果 | 修法 |
|---|---|---|
| `SOURCE_LABELS` 命中不到 | 标签上**直接显示英文 `resume_match`**——这是用户可见的界面缺陷，不是内部问题 | 加 `resume_match: '简历匹配'` |
| `title` 只有二分支 | `resume_match` 会走 `else` 分支，提示「**手工录入题库**」——**文案与事实相反** | 改为三分支（用映射表而非三元表达式） |
| `class` 为 `tag--resume_match` | 需要一条对应样式，否则标签无配色（退化为无底色） | 在 `components.css` 补 `.tag--resume_match`（与既有 `tag--bank` / `tag--ai` 同构） |

> ⚠️ **`sourceTag` 是共享组件**（`interview-detail.js:295` 与 `questions.js:320` 都在用）。改动必须**只增不改**既有 `bank` / `ai` 的表现，否则 `questions.js` 会跟着变——`questions.js` 展示的是题库题目的 `source`（只可能是 `bank` / `ai`），因此**新分支对它是不可达的**，无回归风险。
>
> **这条被漏掉的概率很高**：`shell.js` 不在「HR 页面」的直觉范围内，但它是本项目**唯一集中定义来源标签文案**的地方。

### 3.2 二进制下载通道（`api.js` 的增量）

**为什么必须新增**：既有 `request()` 在 2xx 时执行 `await response.json()`（`api.js:60-64`）。对 DOCX 的二进制响应，`response.json()` 会抛错，被 `catch` 吞掉后 `payload = null`，最终返回 `null`——**表现为「导出成功但拿到 null」**，是本模块最容易踩的坑。

**新增导出**

| 导出 | 签名 | 职责 |
|---|---|---|
| `download(path)` | `async (path: string) => { blob: Blob, filename: string }` | 带 token 请求 → 2xx 取 Blob 并解析文件名；非 2xx **复用 `request()` 的错误形状**；401 走同一套清理与回调 |
| `parseContentDisposition(header)` | `(header: string \| null) => string` | **纯函数**，供单测。优先 `filename*=UTF-8''<pct>`，回退 `filename="..."`，都无则返回缺省名 |

`parseContentDisposition` 的行为契约：

| 输入 | 输出 |
|---|---|
| `attachment; filename="report.docx"; filename*=UTF-8''%E9%9D%A2%E8%AF%95...docx` | 解码后的中文名（**优先 `filename*`**） |
| `attachment; filename="report.docx"` | `report.docx` |
| `null` / `""` | 缺省名（如 `report.docx`） |
| `filename*=UTF-8''` 后为空串 / 百分号编码非法 | 缺省名（**不抛异常**） |

> **为什么要抽成纯函数**：`decodeURIComponent` 对非法百分号序列**会抛 `URIError`**。这条路径在前端自动化测试里够不着（无 DOM），但**纯函数可以被测**，所以把它抽出来。这是本工程「判定逻辑必须抽成纯函数才可能被覆盖」的一贯做法（module-22 §5.1 同理）。

**页面侧的下载收尾（必须写对）**

```
const { blob, filename } = await api.download(path);
const url = URL.createObjectURL(blob);
const link = document.createElement('a');
link.href = url; link.download = filename;
link.click();
URL.revokeObjectURL(url);        ← ⚠️ 不调用会按次数泄漏内存
```

> ⚠️ **`URL.revokeObjectURL` 不能省**：漏掉时每次导出都留一份文档在内存里，长会话下会持续增长。`link.click()` 后立刻 revoke 在主流浏览器是安全的（下载已开始）。

**不能用 `<a href="/api/...">` 直接下载的原因**：导出端点需要 `Authorization` 头（PRD §8：除登录与候选人自助注册外均需 JWT），而 `<a>` 无法带头。**因此必须走 fetch + Blob。**

### 3.3 打印样式（**全工程首次引入 `@media print`**）

**现状**：`grep "@media print" src/` **零命中**。本模块要建立第一套。

**要解决的四个问题**

| 问题 | 处理 |
|---|---|
| 打印时带上侧边栏 / 顶栏 / 按钮 / toast | `.sidebar`、`.topbar`、`.page-head-actions`、`.btn`、`.toast-stack` → `display: none` |
| 侧边栏隐藏后 `.shell` 仍是两列网格，正文被挤在右侧 | 打印时把 `.shell` 改为单列、`.workspace` 去掉偏移 |
| 浏览器**默认不打印背景色**，报告的分数色块、来源 / 维度标签底色、面板底色、优劣势列表着色都会丢失 | 相关元素加 `print-color-adjust: exact; -webkit-print-color-adjust: exact;`。**注意范围**：雷达图是 canvas，它的颜色是像素、**不在**这条的正射程内（见 §5.4）——被这条救的是**其余所有 CSS 背景** |
| 面板被分页切开（雷达图与结论分到两页） | 面板加 `break-inside: avoid`；必要时用 `break-before` 控制大题块 |

**另需 `@page { margin: ... }`** 给纸张留边距——`@page` 与普通 `@media print` 是两回事，**两者都要写**。

**打印范围的控制**：打印时**只打印主内容区**（`.main`），且页面上的操作控件全部隐藏。这样报告页打印出来就是一份报告，不含任何交互痕迹。

> ⚠️ **`print-color-adjust` 是最容易漏的一条**：漏掉时**屏幕上一切正常，只有打印/另存为 PDF 后颜色消失**——而这正是本功能的交付形态（PRD §4.12 的 PDF 就是靠打印产出）。**没有它，PDF 导出在视觉上等于报废。**
>
> **雷达图是例外而非风险源**：它是 canvas，颜色是像素、会照常打印（§5.4）。**别因为「雷达图能打印」就以为不需要 `print-color-adjust`**——需要它的是分数色块与各类标签底色。
>
> **本工程没有自动化测试能覆盖打印样式**，因此 §7.2 的手工走查里必须包含「**实际执行一次打印预览**」这一项，且要看的是**另存的 PDF**，不是屏幕。

### 3.4 准备助手页的形态选择

| 方案 | 评价 |
|---|---|
| **A. 独立页 `#/interviews/:id/prep`** | ✅ 选中。内容多（四阶段提纲 + N 条重点 + 4 条预案）、需要编辑态、需要单独打印 |
| B. 面试详情页内的折叠面板 | ❌ 详情页已 379 行且承担题目导航 + 作答编辑；再塞三块可编辑结构会让它失控。且**打印时无法只打印面板**（需要给 `body` 加状态类来切换打印范围，脆弱） |
| C. 弹窗 | ❌ 三块结构在弹窗里无法舒适编辑；弹窗也不便打印 |

> **PRD §4.11 说「在面试详情页点『生成准备提纲』」**：本设计在详情页放一个**入口按钮**，点击**跳转到准备助手页**——满足「在详情页点」的字面要求，同时拿到独立页的全部好处。**API 层面的 `POST/GET/PUT` 与 PRD §8 完全一致。**

---

## 4. 接口契约（页面 ↔ 后端）

### 4.1 本模块消费的端点

| 用途 | 端点 | 来源 |
|---|---|---|
| 读候选人简历 | `GET /interviews/{id}/resume`（未关联 404） | module-19 §4.1 |
| 按简历补题 | `POST /interviews/{id}/questions/match`，body `{count?}` | module-19 §4.1 |
| 生成准备提纲 | `POST /interviews/{id}/prep` | module-19 §4.1 |
| 查看准备提纲 | `GET /interviews/{id}/prep`（未生成 404） | module-19 §4.1 |
| 编辑准备提纲 | `PUT /interviews/{id}/prep`，**三部分全必填** | module-19 §4.1 |
| 面试详情（含 `resume_id`、题目 `match_reason`） | `GET /interviews/{id}` | module-19 §4.2 |
| 报告（含 `resume_id`） | `GET /interviews/{id}/report` | module-06 既有 |
| 导出 DOCX | `GET /interviews/{id}/report/export?format=docx` | module-21 §4.1 |

**本模块只消费端点，不新增端点。**

### 4.2 关键字段

**`InterviewDetail` 新增**（module-19 §4.2）

| 字段 | 前端用途 |
|---|---|
| `resume_id` | 判断是否已关联简历（决定「按简历补题」是否可用） |

**`QuestionItem` 新增**（module-19 §4.2）

| 字段 | 前端用途 |
|---|---|
| `match_reason` | `source === 'resume_match'` 时展示「为什么选这道题」；其余为 null |

**`MatchResult`**（module-19 §4.2）

| 字段 | 前端用途 |
|---|---|
| `added_count` | 提示「本次新增 N 题」 |
| `total_questions` | 提示「本场共 M 题」（**必须有**，见 §5.4） |
| `added[]` | 追加项的 `match_reason` |

**`PrepOut` / `PrepUpdate`**（module-19 §4.2）

| 字段 | 前端处理 |
|---|---|
| `outline[]` | `{seq, phase, duration_min, notes}` |
| `focus_points[]` | `{dimension, point, reason}` |
| `question_plan[]` | `{question, intent, follow_ups[]}` |
| `generated_at` / `edited_at` | 页头显示来源与时间；`edited_at` 非空表示已被手工编辑 |

**`ResumeOut`（HR 只读视图）**（module-17 §4.2 / module-19 §4.2）

| 字段 | 前端用途 |
|---|---|
| `title` / `content` | 展示；`content` 用**保留换行**的文本块呈现 |
| `candidate_name` / `candidate_contact` | 可空 |
| `updated_at` | 显示「最后更新」，**提示 HR 手上这份是否最新** |

---

## 5. 页面设计

### 5.1 `interview-prep.js`（`#/interviews/:id/prep`）—— 唯一新增页

**页头**：面包屑/返回（回 `#/interviews/{id}`）、标题「面试准备」、右侧两个按钮：

| 按钮 | 行为 |
|---|---|
| 生成 / 重新生成 | `POST /interviews/{id}/prep`。已存在时**二次确认**（会覆盖手工编辑，§5.5） |
| 导出 PDF | `window.print()` |

**三块内容**（`outline` / `focus_points` / `question_plan`），每块一个面板：

| 块 | 只读态 | 编辑态 |
|---|---|---|
| 面试提纲 | 有序列表：阶段名 · 时长 · 要点 | 每行三个输入（阶段名 `<input>`、时长 `<input type=number min=1>`、要点 `<textarea>`）+ 删除行；底部「添加阶段」 |
| 考察重点 | 每行：维度标签 · 重点 · 理由 | 每行（维度 `<input>`、重点、理由）+ 删除行；底部「添加」 |
| 问题预案 | 每行：问题 · 考察意图 · 追问（列表） | 每行（问题 `<textarea>`、意图 `<input>`、**追问一个 `<textarea>` 每行一条**）+ 删除行；底部「添加」 |

**保存**：`PUT /interviews/{id}/prep`，**三部分整体提交**（§4.2 明确要求）。

| 细节 | 处理 |
|---|---|
| `seq` | **保存时按当前顺序重算为 1..n**（用户可能删行 / 调序）。前端重算避免「删了中间一行后 seq 出现空洞」 |
| `follow_ups` | 用 `<textarea>` 承载，**按行拆分 / 按行合并**（`split('\n').map(trim).filter(Boolean)`）。这是纯文本 ↔ 字符串数组最简单的双向映射，不引入任何富文本控件 |
| `duration_min` | `<input type="number" min="1">`；后端对非正整数会回落 5（module-18 §5.3），**前端仍要做本地校验**，避免用户以为填的 0 生效了 |

**状态与只读**

| 面试状态 | 行为 |
|---|---|
| `draft` / `ongoing` | 可生成、可编辑（显示「编辑」按钮） |
| `completed` / `evaluating` / `evaluated` | **只读**：隐藏生成与编辑按钮，仅可查看与打印 |

**未生成时**（`GET` 返回 404）：展示空态 + 「生成准备提纲」按钮，**不把 404 当错误弹 toast**。

> ⚠️ **404 是正常状态而非错误**：PRD §4.11 与 module-19 §5.5 明确「未生成时读取 → 404，前端据此显示生成按钮」。因此**必须把 404 识别出来走空态分支**，而不是走通用错误提示。识别方式：`error.status === 404`。

**无关联简历时**：仍可生成（PRD §4.11「未关联简历也能生成」）。页面上给一句轻提示「该面试尚未关联简历，提纲将不含简历针对性内容」。

### 5.2 `interview-detail.js` 的增量（四处）

**（a）候选人简历只读区**

| 状态 | 展示 |
|---|---|
| 已关联 | 面板「候选人简历」：标题 · 姓名 / 联系方式 · 最后更新 · 正文（保留换行，可折叠） |
| 未关联（404） | 面板显示一行说明：「候选人尚未提交简历。候选人可在其端内录入并关联，之后可据此补充面试题。」**不显示错误** |
| 读取失败（非 404） | 面板显示错误文案（原样） |

> **404 与真错误必须分开**：前者是「还没做这件事」，后者是「出问题了」。混在一起会让 HR 以为系统坏了。这与 §5.1 的处理同理。

**（b）按简历补题**

| 项 | 设计 |
|---|---|
| 启用条件 | `detail.status === 'ongoing'` **且** `detail.resume_id != null` |
| 不满足时的提示 | 未关联简历 → 按钮 disabled + `title`「该面试尚未关联简历」；非 `ongoing` → 按钮 disabled + `title`「当前状态不可补题」 |
| 点击 | `POST /interviews/{id}/questions/match`（不带 `count`，用后端默认） |
| 进行中 | 按钮进入 busy（禁用 + 文案「匹配中…」），**防止连点**（连点会累加题数，见下） |
| 成功后 | `toast.success('本次新增 N 题，本场共 M 题')`；**重新拉取面试详情**以显示新题与理由 |
| `added_count === 0` | `toast.info('未匹配到新的题目')`——**这不是错误**（200） |

> ⚠️ **必须显示「本场共 M 题」**：module-19 §5.3 已写明「重复补题会**累加**新题」。若只提示「本次新增 3 题」，HR 不清楚总量、连点几次后会以为界面在重复加同一批题。**`total_questions` 字段存在的全部意义就是这个提示。**
>
> ⚠️ **必须做 busy 防护**：补题按钮**不是幂等的**（module-19 §5.3 的「幂等」只指「不产生重复题目」，不指「重复调用无效果」）。不做防护时连点 5 次会调 5 次 AI 并追加 5 批题。

**（c）`match_reason` 展示**

| 位置 | 展示 |
|---|---|
| 题目编辑区头部（`editor-head` 附近） | 当 `question.source === 'resume_match'` 且 `match_reason` 非空时，显示一条引用样式的说明：「为什么选这道题：{match_reason}」 |
| 左侧题目导航 | 不改（保持紧凑） |

**（d）准备助手入口**

页头操作区（`page-head-actions`）加一个按钮「面试准备」→ `navigate('/interviews/{id}/prep')`。

**不改动**：题目导航、作答编辑与自动保存、状态轨、既有的完成 / 回退 / 邀请等按钮。

### 5.3 `evaluation.js` 的增量（两个导出按钮）

**位置**：报告态页头操作区（`page-head-actions`，`evaluation.js:125-135`）。

| 按钮 | 行为 |
|---|---|
| 导出 DOCX | `api.download('/interviews/{id}/report/export?format=docx')` → Blob 下载（§3.2）；busy 期间禁用；**失败时提示「导出 DOCX 失败，可改用『导出 PDF』」**（module-21 §6 的契约） |
| 导出 PDF | `window.print()`。**无网络请求，因此后端故障时仍可用** |

**按钮可见性**：仅在报告渲染完成后显示（`evaluated` 且有报告），与既有报告态一致。

> ⚠️ **两个导出按钮在打印时必须被隐藏**：否则打印出来的 PDF 里会印着「导出 DOCX / 导出 PDF」两个按钮。这条已由 §3.3 的 `.btn { display: none }` 覆盖，但**走查时必须实际看一眼另存的 PDF**（§7.2）。

### 5.4 打印时的页面差异

| 页面 | 打印内容 |
|---|---|
| 报告页（`evaluation`） | 报告英雄区（总分 / 结论）+ 雷达图 + 维度得分 + 优势 / 待改进 + 逐题明细。**含雷达图** |
| 准备助手页（`interview-prep`） | 三块内容（提纲 / 重点 / 预案）。**无图** |

**雷达图的打印表现（**已核实，非推测**）**

`components/radar.js` 是 **Canvas 实现**（`getContext('2d')` + DPR 缩放，文件头注释明确写「Canvas 雷达图」）。因此：

| 项 | 结论 |
|---|---|
| 能否打印出图 | **能**。canvas 是 DOM 的一部分，打印时会被浏览器栅格化 |
| 颜色会不会丢 | **不会**。canvas 的颜色是**像素**，不是 CSS 背景，因此**不受 `print-color-adjust` 影响**——这一点上它反而比 CSS 背景更稳 |
| `print-color-adjust` 还需要吗 | **仍然必需**，但保护的是**别的东西**：分数色块、来源/维度标签底色、面板底色、优劣势列表的着色，这些是 **CSS 背景**，浏览器默认不打印 |
| 清晰度 | **是位图不是矢量**：打印分辨率取决于绘制时的 dpr。Windows 普通屏 dpr=1，打印会略糊但可读。**属可接受的已知限制** |
| 尺寸 | 不会被拉伸。`drawRadar` 会把 `canvas.style.width/height` 显式钉成 px，不依赖父容器宽度，因此打印时隐藏侧边栏导致的布局变化**不会改变画布尺寸** |
| 本模块是否改渲染方式 | **不改**。雷达图是 module-07 的产物，改渲染属另一件事（且会动到既有单测 `radar.test.js`） |

### 5.5 重新生成的覆盖风险

`POST /prep` 会**整体覆盖**既有内容（module-19 §5.4），且**把 `edited_at` 置回 null**。因此：

| 场景 | 前端行为 |
|---|---|
| 尚未生成（404） | 直接生成，不确认 |
| 已生成、`edited_at` 为 null（未被手工编辑） | 二次确认文案：「重新生成将覆盖当前提纲，确定继续？」 |
| 已生成、`edited_at` 非 null（**已被手工编辑**） | 二次确认文案**加重**：「当前提纲已手工编辑过，重新生成会**丢失这些修改**且不可撤销。确定继续？」 |

> **本模块不做「保存草稿再重生成」的折中**：PRD §5.2 明确「一场面试唯一、重新生成即覆盖、不做版本历史」。**用确认文案把不可逆性说清楚，比提供一个 PRD 没有的机制更诚实。**

---

## 6. 错误处理

| 场景 | 前端行为 |
|---|---|
| `GET /interviews/{id}/resume` → **404** | 视为「尚未关联」，显示引导说明，**不弹错误**（§5.2a） |
| `GET /interviews/{id}/prep` → **404** | 视为「尚未生成」，显示空态 + 生成按钮，**不弹错误**（§5.1） |
| 补题 → **409** | 原样展示后端文案（「该面试尚未关联简历」/「当前状态下不可按简历补题」），并**重新拉取详情**刷新可用态 |
| 补题 → **502**（AI 失败） | 原样展示后端文案；**提示可稍后重试**；**题目列表不变**（后端保证数据库无改动，module-19 §5.3） |
| 生成准备提纲 → **502** | 原样展示；若已有提纲，**确认旧内容仍在页面上**（后端保证未写库） |
| 生成准备提纲 → **409** | 原样展示；刷新页面状态为只读 |
| 编辑准备提纲 → **400** | 走 `fieldErrors.fromServer`；三部分任一为空时**前端本就应阻止提交**（本地校验），400 是兜底 |
| 导出 DOCX → **502 / 500** | 提示「导出 DOCX 失败，可改用『导出 PDF』」 |
| 导出 DOCX → **409**（评估尚未完成） | 原样展示后端文案（按钮本不该出现在未评估状态） |
| 导出 DOCX → **404** | 原样展示 |
| 下载通道收到非 `application/...docx` 的内容类型 | 仍按 Blob 保存（后端 200 即为成功），但**记一条 console.warn**，便于排查反向代理改写响应的情况 |
| 401 | 走既有统一处理器（`api.js` 的按端处理） |

> **全部沿用既有约定**：错误文案来自后端、前端不重写（module-07 §4.1）。**本模块不新增任何错误处理机制。**

---

## 7. 测试设计

### 7.1 纯函数单测（`src/__tests__/download.test.js`，**新增**）

| 测试 | 断言 |
|---|---|
| `test_parse_prefers_rfc5987_filename` | 同时有 `filename` 与 `filename*` → 取 `filename*` |
| `test_parse_decodes_utf8_chinese` | `UTF-8''` 编码的中文名被正确 `decodeURIComponent` 还原 |
| `test_parse_falls_back_to_plain_filename` | 只有 `filename="a.docx"` → `a.docx` |
| `test_parse_handles_missing_header` | `null` / `""` → 返回缺省名 |
| `test_parse_handles_malformed_percent_encoding` | `filename*=UTF-8''%E0%A4%A` → **返回缺省名，不抛 `URIError`** |
| `test_parse_handles_empty_rfc5987_value` | `filename*=UTF-8''` → 缺省名 |
| `test_parse_is_case_insensitive_on_prefix` | `filename*` 的大小写变体仍被识别 |
| `test_parse_strips_quotes` | `filename="a.docx"` → `a.docx`（不含引号） |
| `test_default_filename_is_ascii` | 缺省名本身是 ASCII（老客户端也不会乱码） |

> **`test_parse_handles_malformed_percent_encoding` 是最重要的一条**：`decodeURIComponent` 对非法序列**直接抛异常**，而这条路径在页面上表现为「点了导出没反应」。抽成纯函数就是为了让它能被测到（§3.2）。

### 7.2 手工走查（`mock/evaluation-harness.html` 增补 + 浏览器实操）

**简历只读区**

| 走查项 | 期望 |
|---|---|
| 未关联 | 显示引导说明，**无错误提示** |
| 已关联 | 显示标题 / 姓名 / 最后更新 / 正文；正文换行保留 |
| 后端不可达 | 面板显示错误文案（与 404 的表现**明显不同**） |

**按简历补题**

| 走查项 | 期望 |
|---|---|
| 未关联简历 | 按钮 disabled，`title` 说明原因 |
| 非 `ongoing` | 按钮 disabled，`title` 说明原因 |
| `ongoing` 且已关联 | 可点击；点击后 busy；成功后提示「本次新增 N 题，本场共 M 题」 |
| **连点 5 次** | **只发出 1 次请求**（busy 防护生效） |
| 重复补题 | 第二次仍能追加，且**提示里的总数递增**（体现「累加」语义，§5.2b） |
| AI 失败 | 显示后端文案；**题目列表不变** |
| `added_count == 0` | 显示「未匹配到新的题目」，**不是错误样式** |
| `match_reason` | 匹配来的题显示「为什么选这道题」；其余题不显示该区块 |
| 来源标签 | 匹配来的题标签显示 **「简历匹配」**，且 `title` 不再是「手工录入题库」（§3.1） |

**准备助手**

| 走查项 | 期望 |
|---|---|
| 未生成 | 空态 + 生成按钮，**无错误提示** |
| 生成成功 | 三块内容正确渲染 |
| 编辑并保存 | 改动落库；页头 `edited_at` 出现 |
| 删行后保存 | `seq` 无空洞（重算为 1..n） |
| 追问多行 → 保存 → 重新打开 | 追问条目保持 |
| 重新生成（未编辑过） | 二次确认文案为普通版 |
| 重新生成（已编辑过） | 二次确认文案**明确提示会丢失修改且不可撤销** |
| 非 `draft`/`ongoing` | 只读，无生成 / 编辑按钮 |
| 无关联简历 | 可以生成，页面有轻提示 |
| 生成失败 | 后端文案；已有内容**仍在页面上** |

**导出**（**必须实际执行打印，不只看屏幕**）

| 走查项 | 期望 |
|---|---|
| 导出 DOCX | 下载到 `.docx`，文件名是**中文**且可正常打开（§3.2 的 `filename*` 路径） |
| 文件名解码 | 不出现 `%E9%9D%A2...` 这类未解码的乱码名 |
| 导出 DOCX（后端关闭） | 提示「导出 DOCX 失败，可改用『导出 PDF』」 |
| **导出 PDF（报告页）** | `window.print()` → **另存为 PDF** → **颜色仍在**（分数色块、雷达图配色）、**无侧边栏 / 顶栏 / 按钮 / toast**、雷达图**未被分页切开** |
| **导出 PDF（准备助手页）** | 同上；三块内容完整，无操作控件 |
| 连续导出 3 次 DOCX | 无异常；页面无卡顿（`revokeObjectURL` 生效的间接观察） |

> ⚠️ **打印走查必须看「另存的 PDF」，不是屏幕，也不是打印预览的缩略图**：`print-color-adjust` 缺失的症状恰恰是「屏幕上完全正常、PDF 里颜色没了」。**只看屏幕等于没测。**

### 7.3 回归

| 项 | 断言 |
|---|---|
| `npm test` | 新增 `download.test.js` + 既有 `radar.test.js` / `sse.test.js` **全绿** |
| `npm run build` | 构建通过 |
| **`questions.js` 的 `sourceTag` 表现不变** | 手工看题库页的来源标签仍为「手工」/「AI」 |
| **既有 HR 页面零回归** | 面试列表 / 面试详情（题目导航、作答自动保存、状态轨、邀请）/ 岗位 / 题库 / 用户 / 登录逐一走查 |
| `standalone.html` | **未被修改**（`git status` 无该文件） |
| 打印样式不污染屏幕 | 正常浏览（非打印）时布局与改动前一致 |
| 后端 | `pytest tests/ -q` 全绿（本模块不改后端） |

---

## 8. 任务分解

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-07（HR 前端基座）、module-19（三个端点与两个字段）、module-21（导出端点）已完成。

### Task 23.1：`sourceTag` 补全（**先做，最小且用户可见**）

- [ ] `shell.js` 的 `SOURCE_LABELS` 加 `resume_match: '简历匹配'`
- [ ] `sourceTag` 的 `title` 从三元表达式改为三分支映射
- [ ] `components.css` 补 `.tag--resume_match` 样式（与 `tag--bank` / `tag--ai` 同构）
- [ ] 手工确认题库页的「手工」/「AI」标签**表现不变**
- [ ] 提交

### Task 23.2：下载通道

- [ ] `api.js` 新增并导出 `parseContentDisposition`（纯函数）与 `download(path)`
- [ ] 写 §7.1 全部失败测试（**含非法百分号编码不抛错、优先 `filename*`**）
- [ ] `npm test` 确认通过
- [ ] 提交

### Task 23.3：报告导出按钮

- [ ] `evaluation.js` 页头加「导出 DOCX」「导出 PDF」（§5.3）
- [ ] DOCX 走 `api.download` + Blob + **`URL.revokeObjectURL`**（§3.2）
- [ ] 失败提示「可改用导出 PDF」
- [ ] 手工走查 §7.2「导出」组的 DOCX 部分
- [ ] 提交

### Task 23.4：打印样式

- [ ] `components.css` 加 `@page` 与 `@media print` 全套（§3.3 的四个问题逐条处理）
- [ ] 含 `print-color-adjust: exact`
- [ ] **实际执行**报告页与准备助手页的打印 → 另存 PDF → 核对颜色 / 无控件 / 无分页断裂
- [ ] 提交

### Task 23.5：面试详情页 —— 简历只读区与匹配理由

- [ ] 简历只读区（**404 走引导态，不弹错误**）
- [ ] 题目区展示 `match_reason`（仅 `resume_match` 来源）
- [ ] 手工走查 §7.2 的「简历只读区」与「`match_reason`」两组
- [ ] 提交

### Task 23.6：面试详情页 —— 按简历补题

- [ ] 按钮 + 启用条件 + `title` 说明 + **busy 防护**
- [ ] 成功后提示「本次新增 N 题，本场共 M 题」并刷新详情
- [ ] `added_count == 0` 走 info 提示
- [ ] 手工走查 §7.2 的「按简历补题」全组（**含连点 5 次只发 1 次请求**）
- [ ] 提交

### Task 23.7：准备助手页

- [ ] 新建 `src/pages/interview-prep.js`（空态 / 只读 / 编辑三态）
- [ ] `router.js` 加 `#/interviews/:id/prep`；`main.js` 注册
- [ ] 面试详情页页头加「面试准备」入口
- [ ] `pages.css` 追加样式
- [ ] 手工走查 §7.2 的「准备助手」全组（**含两种二次确认文案、`seq` 重算、追问多行往返**）
- [ ] 提交

### Task 23.8：全量走查与回归

- [ ] 跑完 §7.2 **全部**走查项（**打印必须看另存的 PDF**）
- [ ] 跑 §7.3 全部回归项（既有 HR 页面逐一走查）
- [ ] `npm test` / `npm run build` 全绿
- [ ] 确认 `standalone.html`、`vite.config.js`、`index.html`、`package.json` **零改动**
- [ ] 提交

---

## 9. 验收标准

- [ ] 新增 **2 个**文件（`interview-prep.js`、`download.test.js`）；**未新增**任何依赖、组件或 CSS 文件
- [ ] 路由 `#/interviews/:id/prep` 注册且可从面试详情页进入
- [ ] **`sourceTag` 支持 `resume_match`**：标签显示「简历匹配」，`title` 文案正确（不再是「手工录入题库」）；既有「手工」/「AI」表现不变
- [ ] `api.js` 新增 `download()` 与纯函数 `parseContentDisposition()`；**非法百分号编码不抛异常**
- [ ] 报告页可导出 DOCX；**文件名是解码后的中文**；下载后 `URL.revokeObjectURL` 已调用
- [ ] 导出 DOCX 失败时提示「可改用『导出 PDF』」
- [ ] 报告页与准备助手页均可 `window.print()` 导出 PDF
- [ ] **打印样式中含 `print-color-adjust: exact`**，且**实际另存的 PDF 里颜色仍在**
- [ ] **打印产物不含**侧边栏 / 顶栏 / 按钮 / toast；雷达图未被分页切开
- [ ] 面试详情页：简历只读区在 **404 时显示引导而非错误**；正文换行保留
- [ ] 面试详情页：`match_reason` 仅对 `resume_match` 来源的题展示
- [ ] 按简历补题：启用条件正确；**连点只发一次请求**；成功提示**含本场总数**
- [ ] `added_count == 0` 提示为 info「未匹配到新的题目」，非错误样式
- [ ] 准备助手：未生成时**空态 + 生成按钮**（404 不当错误）；`draft`/`ongoing` 可编辑，其余只读
- [ ] 准备助手：保存时 `seq` **重算为 1..n**；`follow_ups` 多行往返正确
- [ ] 准备助手：重新生成有二次确认；**已手工编辑过的文案明确提示不可撤销的丢失**
- [ ] 准备助手：无关联简历时仍可生成，并有轻提示
- [ ] 全部错误文案**原样来自后端**
- [ ] `npm test` / `npm run build` 通过；既有前端用例零回归
- [ ] 既有 HR 页面（面试列表 / 详情 / 岗位 / 题库 / 用户 / 登录）功能不变
- [ ] `standalone.html` 未被修改；后端零改动

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **`sourceTag` 会直接显示英文 `resume_match`** | §3.1 显式补全标签与 `title` | `SOURCE_LABELS[source] \|\| source` 的兜底是「原样显示」，用户会看到英文枚举值；`title` 的二分支还会给出**与事实相反**的提示。`shell.js` 不在「HR 页面」的直觉范围内，漏掉的概率很高 |
| **`request()` 只解析 JSON，无法下载二进制** | 新增 `download()` 通道 | 对 DOCX 响应执行 `response.json()` 会抛错并被吞掉，表现为「导出成功但拿到 null」。**这是本模块最容易踩的坑** |
| **`parseContentDisposition` 必须能处理非法编码** | 抽成纯函数并单测 | `decodeURIComponent` 对非法序列抛 `URIError`，页面上表现为「点了没反应」。抽出来才可能被覆盖（本工程只测纯函数） |
| **必须 `URL.revokeObjectURL`** | 下载后立即 revoke | 漏掉会按导出次数泄漏内存 |
| **打印样式必须带 `print-color-adjust`** | 显式加上 | 缺失时**屏幕正常、PDF 里颜色全丢**——而 PDF 正是要靠打印产出的交付形态。**光看屏幕等于没测** |
| **打印必须实际另存 PDF 走查** | §7.2 明确要求 | 打印样式是本工程首次引入，且没有自动化测试能覆盖；「看屏幕」无法暴露颜色与分页问题 |
| **雷达图是 canvas 而非 SVG** | **已核实**：能打印、颜色不丢（像素不受 `print-color-adjust` 影响）、尺寸不会被拉伸；**代价是位图略糊**（dpr=1 时） | 与直觉相反，canvas 在「颜色保留」上比 CSS 背景更稳。**真正的风险不在雷达图，而在那些 CSS 背景**（分数色块、标签底色、面板底色）——它们仍然需要 `print-color-adjust: exact`。**本模块不改渲染方式**（那是 module-07 的产物） |
| **准备助手独立成页而非详情页内嵌** | 独立页 `#/interviews/:id/prep` | 内嵌方案下「只打印准备助手」需要给 `body` 加状态类切换打印范围，脆弱；且详情页已 379 行。PRD 只要求「在详情页点」，入口按钮即满足 |
| **404 是正常状态，不是错误** | 简历未关联、提纲未生成都走引导态 | 它们是「还没做这件事」，不是「出问题了」。混在一起会让 HR 以为系统坏了 |
| **补题按钮必须做 busy 防护** | 点击期间禁用 | 补题**会累加**新题（module-19 §5.3）。不防护时连点 5 次会调 5 次 AI 并追加 5 批题 |
| **补题成功提示必须含本场总数** | 显示「本次新增 N 题，本场共 M 题」 | 只报增量时 HR 不清楚总量，连点后会以为界面在重复加同一批题。**`total_questions` 字段存在的全部意义就在这条提示** |
| **重新生成必须区分「是否已手工编辑」** | 两种二次确认文案 | 重新生成**整体覆盖且不可撤销**（module-19 §5.4）。已编辑过的场景必须把后果说重。**不做「存草稿再重生成」的折中**——PRD §5.2 明确不做版本历史 |
| **不引入任何前端 PDF / DOCX 库** | 打印 + 后端 DOCX | PRD §2 技术栈不变。前端生成 PDF 需要 pdf-lib 之类（新增依赖）；DOCX 已有后端实现 |
| **`<a href>` 不能用于下载** | 走 fetch + Blob | 导出端点需 `Authorization` 头，`<a>` 无法带头 |
| **`follow_ups` 用多行 textarea** | 按行拆分 / 合并 | 纯文本 ↔ 字符串数组最简单的双向映射，不引入富文本或 tag 输入控件。代价是**追问内容里不能含换行**——这对「追问方向」这类短句是合理的限制 |
| **编辑保存时前端重算 `seq`** | 重算为 1..n | 用户可删行 / 调序；重算避免「删了中间一行后 seq 出现空洞」 |
| **准备助手的编辑只提交整三块** | 整体 PUT | module-19 §4.2 明确「三字段全必填、整体替换」。部分提交需要回答「未提交部分保留还是清空」，答案依场景而变 |
| **不做保存草稿 / 自动保存** | 显式「保存」按钮 | 三块结构是可编辑列表，自动保存会在增删行过程中产生大量中间态请求。显式保存让提交时机确定、失败可重试 |
| **打印样式写在 `components.css` 而非新建文件** | 追加到既有文件 | `index.html` 只 link 四个 CSS 文件，**不得新增**（module-15 §2.2 的既有约束） |
