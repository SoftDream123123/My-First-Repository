# 候选人前端增量 执行计划书（MVP-4 简历文件上传入口）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：frontend 候选人端 **MVP-4 增量**（新建 / 编辑简历弹窗内的「上传文件」入口）
**所属工程**：`frontend/`（**同一 Vite 工程内**，不新建工程、不加依赖）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.10（简历管理：上传解析、不截断、不静默覆盖）、§7（MVP-4 错误条目）、§9（安全边界）
**前置依赖**：[module-25 resume 上传解析](./2026-09-22-module-25-resume-upload-plan.md)（端点必须已存在）、[module-22 候选人前端](./2026-09-21-module-22-candidate-frontend-plan.md)（本模块修改的文件由它建成）
**本模块被谁依赖**：[module-30 e2e](./2026-09-22-module-30-e2e-plan.md)

---

## ⚠️ 与 module-22 的冲突声明（**请先读这一节**）

module-22 的 Global Constraints 里写着：

> 简历**只支持粘贴纯文本**，前端**不提供文件上传控件**（§1.3、§4.10）

**这条约束已被 PRD 的 MVP-4 修正取代。** module-22 是 MVP-3 批次的**历史计划书**，按本项目「历史计划书不回改」的既有决定（见整体走查结论）保持冻结。

因此：

| 规则 | 处理 |
|---|---|
| module-22 该条约束 | **作废**，以 PRD §4.10（MVP-4 修订版）与本计划书为准 |
| module-22 的其余约束 | **全部继续有效**（无 UI 框架、仅 PC、`candidate.*` 键、不新增 CSS 文件、`standalone.html` 冻结、错误文案原样展示…） |
| 执行本模块时的判据 | 遇到两份文档冲突，**一律以 PRD 为准**；PRD 未覆盖处回看 module-22 |

> **同样需要作废的相邻表述**：`docs/manual/10-候选人-我的简历.md`、`docs/production/产品说明书.md`、`docs/apis/API接口文档.md` 中「不做文件上传」的段落——由 [module-30](./2026-09-22-module-30-e2e-plan.md) §3 统一回填。

---

## Global Constraints（全局约束）

- **同一 Vite 工程内的两组路由**；**不新建工程、不换框架、不加依赖**（PRD §2）
- 无 UI 框架、无图表库；原生 HTML + CSS + JS（PRD §2）
- **仅 PC 端**，不做移动端响应式（PRD §2）
- **不得新增 CSS 文件**：`index.html` 只 link `tokens/base/components/pages` 四个（module-22 继承）；新增样式只能**追加进既有文件**
- **不得新增依赖**：`package.json` 不动。文件读取用浏览器内置 `FileReader` / `FormData`，**不引 PDF.js、不引 mammoth**
- **不得静默截断**正文；**不得静默覆盖**已有正文（PRD §4.10）
- 后端错误文案**原样展示**（`error.message`），前端不重写（module-07 既有约定）
- `frontend/standalone.html` 已冻结、**不可编辑**（module-07 §1.2）
- **仍是单机 PC 端，技术栈不变**（PRD §2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| 上传入口 | 新建 / 编辑简历弹窗内加「上传文件」按钮（两种弹窗**共用同一个 `resumeModal`**，因此一次改动两处生效） | §4.10 |
| 体积预检 | `file.size` 超限则**不发请求**，直接给文案 | §9 |
| 上传请求 | `multipart/form-data` 发到 `/candidate/resumes/parse` | §8 |
| 回填 | 解析结果写入正文 textarea，**并驱动既有字数计数重算** | §4.10 |
| 不静默覆盖 | 正文非空时先 `confirmModal` 确认才替换 | §4.10 |
| 超长提示 | 回填后若超 20000 字符，计数变红禁保存**并给出可操作提示** | §4.10、§7 |
| 标题补全 | 标题为空时用文件名（去扩展名）填上；**已有内容不覆盖** | §4.10 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **拖拽上传 / 粘贴文件上传** | PRD 未要求；多一条交互路径就多一套边界（拖到正文框里怎么办、拖到弹窗外怎么办）。**一个按钮就够** |
| **上传进度条** | 单机 + 5 MB 上限，请求在百毫秒级；进度条只会闪一下。统一用「解析中…」禁用态表达 |
| **多文件批量上传** | 一份简历对应一个文件；多文件要先回答「合并还是各建一份」，PRD 未要求 |
| **本地预览原件**（在浏览器里渲染 PDF） | 会引入 PDF.js（违反「不加依赖」），且 PRD §1.3 明确不提供「回看原件」。文件在浏览器内存里存在的那几秒已经够用 |
| **前端解析文件**（绕过后端） | 同样是引依赖（PDF.js / mammoth）+ 把解析逻辑分散到两端。解析一律在后端（module-25） |
| **在「我的简历」列表页加入口** | 上传属「录入正文」的一步，必须落在编辑表单里才有确认与改写的余地 |
| **候选人面试页 / 刷题页加入口** | 同上；那两处只做「选用哪份简历」 |
| **后端与端到端验证** | 属 module-25 / module-30 |

### 1.3 交互形态（一句话）

**新建简历弹窗的「简历正文」字段上方，多一行：「上传文件」按钮 + 一行说明文字（支持的格式与体积上限）。点它选文件 → 按钮变「解析中…」→ 成功后正文框被填入文本、字数计数刷新、标题（若为空）被填上文件名，并弹一句 toast 说明解析出多少字、请确认后保存。**

---

## 2. 文件结构

**本模块需修改的文件**

| 文件 | 修改内容 |
|---|---|
| `frontend/src/api.js` | `request` 增加 `FormData` 分支；新增 `postForm(path, formData)` |
| `frontend/src/pages/candidate-resumes.js` | 新增导出常量 `RESUME_UPLOAD_MAX_BYTES` 与两个纯函数；`resumeModal` 内新增上传行 |
| `frontend/src/styles/components.css` | 追加少量上传行样式（**追加，不新建文件**） |
| `frontend/src/__tests__/resume-form.test.js` | 新增两个纯函数的用例 + 上限常量守门断言 |
| `frontend/mock/harness.js` | `JSON.parse(options.body)` 改为对 `FormData` 放行 |
| `frontend/mock/resume-harness.js` | 新增 `/candidate/resumes/parse` 的假处理器 + 走查断言 |
| `frontend/README.md` | 补「上传解析」这一段走查说明与无头跑法 |

> **`frontend/src/router.js` 不动**：本模块不加页面、不加路由。
>
> **`frontend/mock/candidate-harness.js` 不动**：它覆盖的是候选人答题链路，与简历弹窗无关。

---

## 3. 接口契约

### 3.1 `api.js` 的改动（全项目第一次发 multipart）

| 位置 | 现状 | 改后 |
|---|---|---|
| `request` 的 headers | 只要 `body !== undefined` 就无条件 `Content-Type: application/json` | `FormData` 时**不设** `Content-Type`（必须让浏览器自己带上 `multipart/form-data; boundary=…`，手工写死会丢 boundary 导致后端收不到文件） |
| `request` 的 body | 无条件 `JSON.stringify(body)` | `FormData` 时**原样传**，其余仍 `JSON.stringify` |
| 导出 | 无 | 新增 `export const postForm = (path, formData) => request('POST', path, formData);` |

> **为什么改 `request` 内部而不是另写一个上传函数**：`request` 里沉着一整套**不能复制**的逻辑——`NETWORK_ERROR` 归一化、204 处理、`ApiError` 的三字段包装、以及**401 拦截器**（会话失效判定 + `isCredentialCheck` 例外）。另写一份必然漂移。**改一处分支，等于让上传天然继承全部错误处理。**
>
> **只用 `postForm` 一个出口**：不把 `FormData` 支持扩散到 `put` / `patch`。将来真需要再开，现在多开等于给每个方法留一条无人测试的路径。

### 3.2 `candidate-resumes.js` 新增的导出

| 导出 | 签名 | 说明 |
|---|---|---|
| `RESUME_UPLOAD_MAX_BYTES` | `5242880` | 体积上限（5 MB） |
| `uploadSizeState(fileSize, maxBytes?)` | `-> { size, over }` | 体积判定 |
| `titleFromFilename(filename)` | `-> str` | 去最后一个扩展名、去首尾空白；空/异常输入返回 `''` |

> **`RESUME_UPLOAD_MAX_BYTES` 是第二处「前端镜像后端配置」**，与既有的 `RESUME_CONTENT_MAX_LENGTH`（`candidate-resumes.js:28-35`）同一处理方式：**注释写明与后端 `RESUME_UPLOAD_MAX_BYTES` 必须同步**，并用测试里的一条守门断言把它钉住——让改动成为**需要显式改测试的动作**，而不是静默漂移。
>
> **为什么必须在前端预检**：module-25 §5.1 已承认「后端的上限拦不住服务器已经收完的请求体」。前端这一道是**唯一能在请求发出前拦住大文件的地方**，因此它不是体验优化，是那条遗留项的补足手段。
>
> **`titleFromFilename` 的边界**：`"简历.docx"` → `"简历"`；`"a.b.c.pdf"` → `"a.b.c"`；`"无扩展名"` → `"无扩展名"`；`""` / `null` → `""`。**不做**文件名清洗（路径分隔符、控制字符）——浏览器 `File.name` 已是纯名称，且它只会被写进 `title` 字段（后端有 100 字符上限与去空白校验兜底）。

### 3.3 上传行的 DOM 契约

| 元素 | 用途 | 关键约定 |
|---|---|---|
| `<button class="btn btn--sm">上传文件</button>` | 触发隐藏的 file input | `type="button"`（虽然本项目弹窗不用 `<form>`，仍显式标注，避免日后再包 form 时变成隐式提交） |
| `<input type="file" accept=".docx,.pdf" hidden>` | 真正的选择器 | **`accept` 是体验不是校验**——候选人仍可选「所有文件」；真正的把关在后端（module-25 的扩展名白名单 + 魔数复核） |
| 说明文字 | 「支持 DOCX / PDF，不超过 5 MB」 | 文案里的上限**从 `RESUME_UPLOAD_MAX_BYTES` 生成**，不硬编码字符串 |
| 上传行的错误位 | 复用 HTML 原生 `alert`？**否** | 一律走 `toast.error(error.message)`——上传错误没有对应的输入框，不落 `fieldError`（与 module-25 §6 的契约一致） |

> **`id` 命名**：沿用既有 `resume-*` 前缀（`resume-title` / `resume-content`…），新增的 file input 取 `resume-file`。走查脚本按 `id` 定位，命名不一致会直接让断言失效。

---

## 4. 交互流程

### 4.1 主流程

```
点击「上传文件」
  → file input 打开系统选择框
  → 选中文件后：
      1. uploadSizeState(file.size) 判定
           over → toast「文件不能超过 5 MB」；**return，不发请求**
      2. 上传行进入忙态：按钮 disabled、文案「解析中…」
      3. postForm('/candidate/resumes/parse', FormData{file})
      4. 成功返回 { content }：
           4.1 正文框**已有内容**（去空白后非空）？
                 → confirmModal「将替换当前正文，确定吗？」
                   取消 → 保持原正文，**只有**标题补全逻辑照旧跳过
           4.2 content.value = 解析结果
           4.3 手动派发 input 事件（见 §4.2）
           4.4 标题为空 → title.value = titleFromFilename(file.name)
           4.5 超长（> 20000 字符）→ toast 说明「已解析出 N 字，超过 20000 字上限，
               请精简后再保存」（保存按钮已由字数计数禁用）
               否则 → toast.success「已从文件解析出 N 字，请确认后保存」
      5. 失败：toast.error(error.message)（文案原样来自后端）
      6. finally：忙态复位；**file input 的 value 清空**（见 §4.3）
```

### 4.2 必须手动派发 `input` 事件（**最容易漏的一步**）

字数计数 `charCount` 是**事件驱动**的：它 `addEventListener('input', paint)`（`candidate-resumes.js:69`），初始 `paint()` 一次。

**直接写 `content.value = text` 不会触发 `input`**，后果是：计数器仍显示 `0 / 20000`、保存按钮不会被超长禁用——**候选人能提交一份超长正文，然后在提交时才吃一个 422**，与「硬上限不能等提交被拒才知道」的既有设计意图（`candidate-resumes.js:58` 注释）直接矛盾。

因此：

```
content.value = parsed;
content.dispatchEvent(new Event('input', { bubbles: true }));
```

### 4.3 file input 的 `value` 必须清空

同一个文件连选两次（第一次失败后重试）时，浏览器**不会**为第二次选择触发 `change` 事件，因为 `value` 没变。这是 HTML file input 的既有行为，表现为「点了没反应」。

因此忙态复位时 `fileInput.value = ''`。

| 要点 | 说明 |
|---|---|
| **确认覆盖用 `confirmModal` 而不是直接覆盖** | PRD §4.10 明确「不静默覆盖」。候选人可能已经手打了一段再想用文件补全，直接覆盖等于吞掉他的输入 |
| **标题补全不受覆盖确认影响** | 「标题为空才填」本身就不覆盖任何东西，与正文的确认是两件独立的事 |
| **取消覆盖时仍保留忙态复位** | 取消走的是同一段 `finally`，避免按钮永久卡在「解析中…」 |
| **不在成功后再校验一次体积** | 体积在发出前已判过；后端还有一道。前端重复判只会多一条不可达分支 |

### 4.4 忙态

| 状态 | 表现 |
|---|---|
| 上传行 | 按钮 `disabled`、文案「解析中…」；正文 textarea 与保存按钮**不禁用**（候选人可以边解析边读已有内容；禁掉反而像页面卡死） |
| 失败 / 成功 / 取消 | 按钮复位为「上传文件」、`disabled=false` |

---

## 5. 走查（假后端）改动

### 5.1 `mock/harness.js`

`harness.js:56` 的 `options.body ? JSON.parse(options.body) : undefined` 对 `FormData` 会抛错（`JSON.parse` 收到 `[object FormData]`），**整个假后端会炸**。改为：

| 情形 | 记录进 `state.calls.body` 的内容 |
|---|---|
| 无 body | `undefined` |
| `FormData` | **FormData 对象本身**（断言里可 `body.get('file')`） |
| 其余 | `JSON.parse` 结果（原行为不变） |

> **判定用 `instanceof FormData`**：假后端跑在浏览器里，`FormData` 是全局构造器，直接判定即可，不需要鸭子类型。

### 5.2 `mock/resume-harness.js`

新增假处理器 `POST /candidate/resumes/parse`，并新增走查断言。**至少覆盖**：

| # | 断言 | 对应 PRD |
|---|---|---|
| 1 | 选一个正常 docx → 正文框被填上假后端返回的文本 | §4.10 |
| 2 | 填完后**字数计数文本随之更新**（不是仍显示 `0 / 20000`） | §4.10、§4.2 |
| 3 | 假后端返回超长文本 → 计数带 `is-over`、保存按钮 `disabled` | §4.10 |
| 4 | 正文预填内容后上传 → 出现确认框；**取消**后正文不变 | §4.10「不静默覆盖」 |
| 5 | 选一个超过 5 MB 的文件 → **假后端零调用**（`state.calls` 里没有 parse） | §9 |
| 6 | 标题为空时上传 → 标题被填为文件名去扩展名；标题已有内容时**不被覆盖** | §4.10 |
| 7 | 假后端返回 400 + 中文文案 → toast 展示该文案原文 | §7、module-07 §4.1 |
| 8 | 上传失败后再选同一个文件 → **仍然触发**（`value` 已清空） | §4.3 |
| 9 | 编辑已有简历的弹窗里**同样**有上传入口 | §4.10 |
| 10 | 上传成功后**没有发生任何 `POST/PUT /candidate/resumes`**（解析不落库，保存要用户点） | module-25 §5.1 |

> **第 5 条怎么造「大于 5 MB 的文件」**：不要真造 5 MB 数据。`new File([blob], name)` 的 `size` 无法伪造，但可以**构造一个 `file` 形状的对象**（`{ name, size, type }`）直接喂给页面的处理函数——前提是走查脚本能拿到该函数（导出它，见 §3.2 的纯函数设计）。**若无法从脚本触达，则用 `new File([new Uint8Array(5*1024*1024+1)], 'big.pdf')`**：5 MB 的内存分配在 Node 里毫无压力，只是别把它传进 `FormData`（预检会拦住，根本发不出去）。
>
> **第 6 条的「已有内容不覆盖」与第 4 条的区别**：第 4 条管**正文**（要确认），第 6 条管**标题**（无条件不覆盖）。两条是不同规则，**不要合并成一条断言**。

### 5.3 无头跑法

沿用既有方式：Node + 系统 Edge，**必须套 `timeout`**（否则长连接会让 Edge 永不退出）。跑法见 `frontend/README.md` 既有段落，本模块在该段落后补一行「上传解析」。

---

## 6. 测试清单

`frontend/src/__tests__/resume-form.test.js`（Vitest **纯函数**测试）

| # | 用例 | 断言 |
|---|---|---|
| 1 | `uploadSizeState(max)` | `over === false`（边界值，恰好等于上限**不算超**） |
| 2 | `uploadSizeState(max + 1)` | `over === true` |
| 3 | `uploadSizeState(0)` | `over === false` |
| 4 | `titleFromFilename('简历.docx')` | `'简历'` |
| 5 | `titleFromFilename('a.b.c.pdf')` | `'a.b.c'` |
| 6 | `titleFromFilename('无扩展名')` | `'无扩展名'` |
| 7 | `titleFromFilename('')` / `null` | `''` |
| 8 | **守门断言**：`RESUME_UPLOAD_MAX_BYTES === 5242880` | 与后端配置同步（同 `RESUME_CONTENT_MAX_LENGTH` 的既有做法） |

> **DOM 层行为不在 Vitest 覆盖范围内**——本项目的既有决定是「前端测试只测纯函数」（见该测试文件头部注释）。文件选择、确认框、toast、计数刷新全部由 §5 的假后端走查覆盖。**不要在 Vitest 里引入 jest-dom / jsdom**，那会破坏既有约定。

---

## 7. 遗留项与已知局限（交 module-30 汇总）

| # | 局限 | 性质 | 说明 |
|---|---|---|---|
| 1 | 前端 `RESUME_UPLOAD_MAX_BYTES` 与后端配置**是两份值** | 与 `RESUME_CONTENT_MAX_LENGTH` 同一既有取舍 | 靠守门断言 + 注释同步，非本模块新引入的问题 |
| 2 | 真选超大文件时**浏览器仍会读完文件内容**再交给页面 | 浏览器 file API 的固有行为 | 我们的预检在 `change` 之后，省的是网络与后端，不是本地读取 |
| 3 | 不支持拖拽、批量、进度条、原件预览 | 本模块 §1.2 的刻意边界 | PRD 未要求 |
| 4 | 分栏排版的 PDF 抽出来的文本会断行交错 | 后端 parser 的限制（module-25 §9-4） | 前端**不做任何重排**，如实展示 |
| 5 | 上传入口在弹窗里，弹出弹窗前无法上传 | 交互形态的取舍（§1.2） | 与「回填后要确认」的设计绑定，无法拆开 |

---

## 8. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | `npm test`（Vitest）全绿，含 8 条新增纯函数用例 | 本地运行 |
| 2 | 假后端走查 10 条断言全通过 | `npm run dev` + 无头 Edge（套 timeout） |
| 3 | 既有简历链路（新建 / 编辑 / 删除 / 关联）**无回归** | 既有走查断言全绿 |
| 4 | 选超 5 MB 文件时**零网络请求** | §5.2 第 5 条 |
| 5 | 回填后字数计数同步刷新 | §5.2 第 2 条 |
| 6 | `package.json` 零改动、无新增 CSS 文件 | `git status` + 人工确认 |
| 7 | 上传成功后未自动保存（仍停在弹窗，等用户点保存） | §5.2 第 10 条 |
