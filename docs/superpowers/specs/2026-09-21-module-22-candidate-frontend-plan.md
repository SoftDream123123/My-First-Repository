# 候选人前端增量执行计划书（MVP-3 简历）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：frontend 候选人端 **MVP-3 增量**（简历管理页、关联简历到面试、刷题按简历推荐入口）
**所属工程**：`frontend/`（**同一 Vite 工程内**，不新建工程）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.7（刷题按简历推荐）、§4.10（简历管理）、§4.13（候选人关联简历）、§4.6（候选人可见范围）、§9（按端分 key）
**前置依赖**：[module-15 候选人前端](./2026-09-20-module-15-candidate-frontend-plan.md)（**已写好计划书，但尚未执行**）、[module-17 resume](./2026-09-21-module-17-resume-plan.md)、[module-19 interview](./2026-09-21-module-19-interview-plan.md)、[module-20 practice](./2026-09-21-module-20-practice-plan.md)

---

## ⚠️ 执行前提（**请先读这一节**）

**候选人前端目前整体不存在。** 现状核实（2026-09-21）：

| 事实 | 证据 |
|---|---|
| `src/pages/` 只有 7 个页面，**全是 HR 侧** | `login` / `interviews` / `interview-detail` / `evaluation` / `positions` / `questions` / `users` |
| 会话只存 HR 一侧 | `session.js:9-10` 固定 `hr.token` / `hr.user`，**无 `candidate.*`** |
| `src/styles/` 中 `candidate` 零命中 | 无候选人端样式 |
| 路由表无候选人路由 | `router.js:20-28` 的 `routes` 全是 HR 路由 |

因此 **module-15（候选人前端全套，11 个页面 + `src/side.js` + 按端分 key 改造）必须先执行完毕**，本模块才有可改的基座。

**本模块不重复 module-15 的任何内容**——它只写 MVP-3 的**增量**。本模块修改的若干文件（`candidate-practice.js` / `candidate-shell.js` 等）**由 module-15 创建**，本模块在其上做扩展。（`candidate-interview-detail.js` **不在改动之列** —— 关联入口在「我的简历」页，见 §1.1 的注。）

> **不要因为「候选人前端不存在」就在本模块里重建它。** 那会让两个计划书对同一批文件各有一套描述，必然漂移。执行顺序是：**先 module-15，再本模块。**

---

## Global Constraints（全局约束，摘自 PRD）

- **同一 Vite 工程内的两组路由**；**不新建工程、不换框架、不加构建产物**（§2、§3.1）
- 无 UI 框架、无图表库；原生 HTML + CSS + JS（§2）
- **仅 PC 端**，不做移动端响应式（§2）
- 候选人侧登录态用 **`candidate.*`** 键，与 HR 侧互不影响（§9）
- 候选人**只能读写自己的简历**；只能把**自己的**简历关联到**自己已接受**的面试（§4.6、§4.13）
- 简历**只支持粘贴纯文本**，前端**不提供文件上传控件**（§1.3、§4.10）
- 简历正文上限 **20000 字符**；前端**不得静默截断**（§4.10、§7）
- 候选人**看不到** `match_reason`（PRD §4.6）；前端**不得**假设该字段存在（module-19 §7.5）
- 后端错误文案**原样展示**（`error.message`），前端不重写（module-07 §4.1 既有约定）
- `frontend/standalone.html` 已冻结、**不可编辑**（module-07 §1.2）
- **不得新增 CSS 文件**：`index.html` 只 link `tokens/base/components/pages` 四个（module-15 §2.2）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| 简历管理页 | 列表 / 新建 / 编辑 / 删除（纯文本 + 字数计数） | §4.10 |
| 关联简历到面试 | 在**「我的简历」页**勾选「这份简历用在哪些面试上」，可解除（见下方注） | §4.13 |
| 刷题关联入口 | 开始练习时可选一份简历触发按简历推荐 | §4.7 |
| 降级提示 | 显示「按简历推荐暂不可用，已按筛选条件取题」 | §7（module-20 的 `resume_match_applied`） |
| 导航入口 | 候选人侧边栏加「我的简历」 | §4.10 |

> **⚠️ 关联入口的位置是 2026-09-21 定的，与本文档早期版本不同。** 早期版本把它放在**面试详情页**
> （`candidate-interview-detail.js`），那也正好是 PRD §4.13 的流程落点（激活后跳到该场面试）。
> 后来改为放在「我的简历」页，理由有两条：① 「这份简历用在哪几场面试上」是**这一份简历的属性**，
> 与它的增删改查放一处才好理解；② 关联动作是「一份简历 → 多场面试」，放在简历侧一次就能看完，
> 放在面试侧则要逐场翻。**执行时不要按早期版本改回面试详情页**；代价是列表接口要下发每场的
> `resume_id`（§2.3）。

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **候选人前端基座**（登录 / 注册 / 激活 / 刷题 / 我的面试 / 待答 / 反馈 / 错题本 / 统计 / `src/side.js` / 按端分 key 改造） | 全部属 **module-15**，**必须先执行**。本模块只在其上扩展 |
| **文件上传控件** | PRD §1.3 明确不做简历文件上传解析。**不得**出现 `<input type="file">` |
| **简历预览 / 富文本渲染** | 简历是纯文本，用 `<textarea>` 编辑、用保留换行的文本块展示。引入 Markdown / 富文本渲染器等于引依赖 |
| **简历的岗位定向 / 多版本分支管理** | PRD §4.10 未要求。简历就是一段可复用的文本 |
| **在候选人侧展示 `match_reason`** | PRD §4.6 只允许候选人看到题目与自己提交的作答 |
| **候选人侧导出 / 打印** | PRD §4.12 明确导出仅限 HR 侧 |
| **HR 侧任何页面** | 属 module-23 |
| **打印样式（`@media print`）** | 属 module-23（报告页与准备助手页都在 HR 侧） |
| **改动 `standalone.html` / `vite.config.js` / `index.html` / `package.json`** | 无需改动；`standalone.html` 冻结 |

### 1.3 依赖方向（前端不存在包依赖，此节说明**改动面**）

```
module-15 已建：  side.js / session.js / api.js / auth.js / router.js / main.js
                  candidate-shell.js / 11 个候选人页面 / 候选人样式
                              │
                              ↓  本模块在其上「加一个页 + 改三处入口」
本模块改动：      ＋ candidate-resumes.js（唯一新增页）
                  ✎ candidate-practice.js（加简历下拉）
                  ✎ candidate-practice-session.js（加降级提示）
                  ✎ candidate-shell.js（导航加入口）
                  ✎ router.js / main.js（注册新页）
                  ✎ styles/pages.css（追加样式）

后端侧（本模块声明的上游改动，见 §2.3）：
                  ✎ interview/schemas.py：候选人两个响应模型加 resume_id
```

> **本模块**不新增任何前端基础设施文件**（除一个页面文件）**：不加新的组件、不加新的工具模块、不加新的 CSS 文件。这是「增量」的实质含义。

---

## 2. 文件结构

### 2.1 新增文件（**仅 1 个**）

| 文件 | 单一职责 |
|---|---|
| `frontend/src/pages/candidate-resumes.js` | 我的简历：列表 + 新建 / 编辑 / 删除 |

### 2.2 修改的既有文件（**均由 module-15 创建**）

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `frontend/src/router.js` | 候选人路由组加 `#/candidate/resumes` | 新页面的可访问入口 |
| `frontend/src/main.js` | 注册 `candidateResumes` | 页面注册表是**静态**的，不注册则路由找不到页面 |
| `frontend/src/components/candidate-shell.js` | 侧边导航加「我的简历」 | 候选人需有可达入口 |
| `frontend/src/pages/candidate-practice.js` | 开始练习表单加「使用我的简历」下拉 | §4.7 的 UI |
| `frontend/src/pages/candidate-practice-session.js` | 显示「按简历推荐未生效」提示 | 消费 module-20 的 `resume_match_applied` |
| `frontend/src/styles/pages.css` | 追加简历页与新增区块的样式 | **不得新建 CSS 文件**（module-15 §2.2） |

### 2.3 声明的后端上游改动（**按 module-13 的既有惯例，由消费方声明**）

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/app/interview/schemas.py` | **候选人两个响应模型都加 `resume_id: int \| None = None`** —— `CandidateInterviewItem`（列表）与 `CandidateInterviewDetail`（详情） | ⚠️ 候选人端需要知道「这场面试当前关联了哪份简历」。**两个都要**：关联入口在「我的简历」页（§5.2），那一页要一次列出「我每一场用的是哪一份」，只用详情页的字段就得逐场发请求；而 `null` 与「字段缺失」在展示上无从区分，前端也没法自己补 |

> **为什么这一条写在本模块而不是回头改 module-19**：本仓库已有先例——module-13 的 `auth/service.py` 增量就是由**消费方** module-13 声明并实现的（module-13 §2 的「本模块需修改的上游文件」）。**改动跟着需要它的模块走**，避免在已提交的计划书里来回改。
>
> **⚠️ 该改动会触达既有用例**：给既有响应模型加字段可能影响断言响应键集合的既有测试（同 module-19 §4.2 对 `InterviewDetail` 的提醒）。执行时须先跑 `test_candidate_answering.py` / `test_interview.py`。

**测试文件**

| 文件 | 本次改动 |
|---|---|
| `frontend/src/__tests__/resume-form.test.js` | **新增**：简历表单的纯函数校验（字数上限判定、可否提交） |
| `frontend/mock/candidate-harness.html` / `.js` | **改**（若 module-15 已建）：补简历相关的手工走查台 |

> **前端测试的现实边界**：本工程的既有前端测试**只测纯函数**（`src/__tests__/` 下仅 `radar.test.js` 与 `sse.test.js`，`vite.config.js` 的注释明确「只测纯函数 —— 无需 DOM 环境」）。因此本模块**不为页面交互写自动化测试**，而是：
> - 纯函数（字数判定、选项组装）进 `src/__tests__/`；
> - 页面交互走 `mock/candidate-harness.html` 的**手工走查**（module-07 §8.4 的既有方式）。
>
> **不得为此引入 DOM 测试环境（jsdom / @testing-library）**——那是新增依赖（§2）。

---

## 3. 路由与导航

### 3.1 新增路由（追加到 module-15 的候选人路由组）

| hash | 页面 | 端 | 门禁 |
|---|---|---|---|
| `#/candidate/resumes` | `candidateResumes` | candidate | candidate |

> 路径与 module-15 的候选人路由组风格一致（`#/candidate/*`）。**不加子路由**：简历的详情 / 编辑走**弹窗**，与 `positions` / `questions` 页面一致（那两个页面都用 modal 编辑），不引入新的页面层级。

### 3.2 导航

| 位置 | 内容 |
|---|---|
| `candidate-shell.js` 的候选人侧边导航 | 新增「我的简历」，指向 `#/candidate/resumes` |

**排序**：排在「刷题」之后、「我的面试」之前——候选人先录简历，才能用它推荐题目与投给面试。**确切插入位置由 module-15 最终实现的导航顺序决定**，本模块只要求「在刷题与我的面试之间」。

> ⚠️ **候选人端不得出现任何 HR 侧入口**（module-15 的既有约束）。本模块只加一个候选人页面入口，不新增任何跨端链接。

---

## 4. 接口契约（页面 ↔ 后端）

### 4.1 本模块消费的端点

| 用途 | 端点 | 来源 |
|---|---|---|
| 简历列表 / 详情 | `GET /candidate/resumes` | module-17 §4.1 |
| 新建简历 | `POST /candidate/resumes` | module-17 §4.1 |
| 更新简历 | `PUT /candidate/resumes/{id}` | module-17 §4.1 |
| 删除简历 | `DELETE /candidate/resumes/{id}` | module-17 §4.1 |
| 关联 / 解除 | `PUT /candidate/interviews/{id}/resume`，body `{resume_id}` | module-19 §4.1 |
| 面试列表 / 详情（取当前关联） | `GET /candidate/interviews`、`GET /candidate/interviews/{id}` | module-12（**本次两者都加 `resume_id`**，见 §2.3） |
| 开始练习（带简历） | `POST /practice/sessions`，body 加 `resume_id` | module-20 §4.1 |
| 会话详情（读降级标记） | `GET /practice/sessions/{id}` | module-20 §4.2 |

**本模块只消费端点，不新增端点。**

### 4.2 关键字段

**`PUT /candidate/resumes/{id}` —— 部分更新语义**

| 方向 | 字段 | 说明 |
|---|---|---|
| 请求 | `title` / `candidate_name` / `candidate_contact` | 可选 |
| 请求 | `content` | 可选 |
| 响应 | `ResumeOut` | 见 module-17 §4.2 |

> ⚠️ **后端是 PUT 但语义为部分更新**（module-17 §4.2 已写明）。因此前端**只提交用户改动的字段**即可；但**本模块采用「整体提交四个字段」的简化做法**——编辑弹窗里四个字段全部可编辑且全部有值，整体提交的语义更直白，也避免「哪些字段是脏的」这一状态管理。
>
> **例外**：`candidate_name` / `candidate_contact` 传 `null` 表示**不改**（module-17 §5.3）。因此这两个字段**空输入时应提交空串 `""` 而非 `null`**，否则用户清空它们不会生效。

**`PUT /candidate/interviews/{id}/resume`**

| 方向 | 字段 | 说明 |
|---|---|---|
| 请求 | `resume_id` | **必填**（字段必须在请求体里）；`int` 关联，`null` 解除 |

> ⚠️ **字段必填、不能省略**：后端区分不了「没传」与「传 null」以外的情况，而 module-19 明确要求「传 `null` = 解除」。因此**解除关联时必须显式提交 `{"resume_id": null}`**。

**`POST /practice/sessions`** 新增的可选字段

| 字段 | 说明 |
|---|---|
| `resume_id` | 不传 / `null` → 走既有筛选取题；传值 → 触发按简历推荐 |

**`GET /practice/sessions/{id}`** 新增的两个字段（module-20 §4.2）

| 字段 | 前端用途 |
|---|---|
| `resume_id` | 显示「本次练习使用了简历：X」 |
| `resume_match_applied` | **false 且 `resume_id` 非空** → 显示降级提示（§5.4） |

### 4.3 `match_reason` **不在候选人的契约里**

| 事实 | 前端约束 |
|---|---|
| `CandidateQuestionItem` **不含** `match_reason`（module-19 §7.5 有测试断言） | 前端**不得**读取或渲染它；不得因缺失而报错 |

> ⚠️ **不要「顺手」在候选人侧显示「为什么给你这道题」**：那看似是加分功能，实则把 HR 的评估思路泄露给候选人，且 PRD §4.6 明确限定候选人可见范围。**后端不下发，前端就不该想要。**

---

## 5. 页面设计

### 5.1 `candidate-resumes.js`（`#/candidate/resumes`）—— 唯一新增页

**布局**

| 区块 | 内容 |
|---|---|
| 页头 | 标题「我的简历」+ 右侧「新建简历」按钮 |
| 列表 | 每行：标题 · 候选人姓名 · 最后更新 `updated_at` · 正文摘要（前若干字） · 「编辑」/「删除」 |
| 空态 | 「还没有简历。录入一份后，可在刷题时按它推荐题目，也可投给你参与面试的岗位。」+ 新建按钮 |
| 编辑 / 新建 | **弹窗**（`openModal`），四字段 + 字数计数 + 取消 / 保存 |

**弹窗字段**

| 字段 | 控件 | 约束 |
|---|---|---|
| 标题 | `<input>` | 必填；`maxlength=100`（与后端 `String(100)` 一致） |
| 简历正文 | `<textarea rows≈18>` | 必填；**不加 `maxlength`**（见下）；配字数计数 |
| 候选人姓名 | `<input>` | 可选；`maxlength=100` |
| 联系方式 | `<input>` | 可选；`maxlength=200` |

**⚠️ 正文字段的关键设计：不加 `maxlength`，改用「计数 + 禁用提交」**

| 做法 | 后果 |
|---|---|
| **`<textarea maxlength="20000">`** | ❌ **粘贴超长文本会被浏览器静默截断**。候选人以为整份简历存进去了，实际尾部已丢——**这是最糟的一类数据丢失：无提示、不可察觉** |
| **计数 + 超限禁用保存**（本设计） | ✅ 不截断、不丢数据、不发无谓请求。计数显示 `当前/20000`，超限时变红并把「保存」按钮置为 disabled |

> **阈值必须与后端同源**：前端的 20000 是硬编码常量（前端无法 import 后端配置）。**在代码注释里写明「与 `RESUME_CONTENT_MAX_LENGTH` 保持一致，改一处必须改另一处」**——与既有的 `PASS_THRESHOLD = 6.5`（前后端各写一份）同一处理方式，那是本项目已有的先例。

**删除**：`confirmModal` 二次确认。后端返回 **409**（简历已被面试或练习关联）时**原样展示后端文案**，不自定义。

**纯函数（可测部分）**：把「能否提交」的判定抽成纯函数导出，供 `src/__tests__/resume-form.test.js` 测试：

| 纯函数 | 语义 |
|---|---|
| `canSubmitResume({ title, content, maxLength })` | 标题去空白非空 **且** 正文去空白非空 **且** 正文长度 `<= maxLength` |
| `contentLengthState(content, maxLength)` | 返回 `{ length, over: boolean }`，供计数着色 |

> **抽成纯函数不是为了「架构好看」**：本工程的前端测试**只能测纯函数**（无 DOM 环境，§2.3）。把判定逻辑留在 `render()` 里就等于**它永远不会被测到**。

### 5.2 `candidate-resumes.js` 的增量（「用于面试」关联区块）

**位置**：右栏案卷的操作区，与「编辑」「删除」并排 —— 它回答的是「**这一份**简历用在哪」。

**内容**：弹窗里列出**我已接受的面试**（`GET /candidate/interviews`，§2.3 的 `resume_id` 在这里被消费），每行一个复选框：

| 该场当前关联 | 行内说明 | 复选框 |
|---|---|---|
| 就是这一份 | 「本场现在用的就是这份简历」 | 勾上 |
| 另一份 | 「本场现在用的是《X》」 | 未勾（勾上 = 改用这一份） |
| 没有 | 「本场还没有关联简历」 | 未勾 |
| 面试已结束 | 「本场面试已结束，关联已冻结」 | 未勾且**禁用** |

**交互**：勾上 = 本场用这一份；取消勾 = 本场不用简历 —— **只在该场当前用的确实是这一份时**才给取消（用着另一份时，改由那一份的「用于面试」去换，否则会误把别人的关联解除掉）。

**提交**：一场面试只挂一份简历，因此逐场 `PUT /candidate/interviews/{id}/resume`，body `{resume_id}` 或 `{resume_id: null}`（**解除必须显式传 null**，§4.2）。

> **⚠️ 中途失败会留下「部分成功」**：关掉弹窗 + 重载列表，让界面与事实一致 —— 比留着勾选状态更不容易让人误判「已经生效」。

**状态相关的禁用**

| 面试状态 | 行为 |
|---|---|
| `ongoing` | 可勾 / 可取消 |
| 其他（`completed` / `evaluating` / `evaluated`） | **该行只读并禁用**，且说明原因 |

> **前端只做「禁用」的体验优化，不作为安全边界**：后端对非 `ongoing` 一律 409（module-19 §5.1），前端不禁用也不会造成数据问题。**但禁用能避免候选人点了才吃一个错**。
>
> **`draft` 态候选人不可能看到**（邀请只在 `ongoing` 可生成），因此无需单独处理。

**弹窗里那句解释**：「关联之后，招聘方才能按这份简历补题」—— 它解释了**为什么值得做这件事**。刻意不做成 `toast.success('已关联简历，HR 可据此补充面试题')`：解除关联时同一句话就成了错话。保存提示只用中性的「已更新关联」。

### 5.3 `candidate-practice.js` 的增量（按简历推荐入口）

**位置**：既有筛选表单内，最后一个筛选项之后。

**内容**

| 控件 | 说明 |
|---|---|
| 下拉「使用我的简历（可选）」 | 首项「不使用」；其余选项来自 `GET /candidate/resumes`，显示 `title` |
| 无简历时 | 该下拉**只显示「不使用」并禁用**，旁边给一句「录入简历后可按简历推荐题目」+ 链接 |

**提交**：`POST /practice/sessions` 的 body 里，选择了简历时带 `resume_id`，否则**不带该字段**（与后端「不传 / null 都走筛选」等价，但省略更干净）。

**为什么不做「记住上次选择」**：module-20 §1.2 已明确不做服务端记忆；前端也**不做 `localStorage` 记忆**——隐式状态会让「为什么这次推荐的题不一样」无从解释。

### 5.4 `candidate-practice-session.js` 的增量（降级提示）

**触发条件**：`detail.resume_id != null` **且** `detail.resume_match_applied === false`。

**展示**：题目列表上方一条**信息条**（非错误）：

> 「按简历推荐暂不可用，本次已按你的筛选条件取题。」

| 决策 | 理由 |
|---|---|
| **用信息条而非 toast** | 它是**页面的持久状态**（这件事在整个练习期间都为真），toast 几秒后就没了，候选人回头看不到 |
| **不用错误样式** | 练习是可用的，只是推荐没生效。用红色错误条会让候选人以为练习坏了 |
| **必须显示** | 这正是 module-20 增加 `resume_match_applied` 列的目的（module-20 §3.1）：**降级必须可观测**，否则候选人以为功能坏了却没有任何线索 |
| **不显示时不要占位** | 未关联简历（`resume_id == null`）时**不显示任何提示**——那是正常选择，不是降级 |

---

## 6. 错误处理

| 场景 | 前端行为 |
|---|---|
| 简历标题 / 正文为空（本地校验） | 在对应字段下方显示字段级错误，**不发请求**（复用 `fieldErrors` 的节点映射机制，module-07 §12.1） |
| 正文超限（本地校验） | 计数变红 + 保存按钮 disabled，**不发请求** |
| 后端 400 `VALIDATION_ERROR`（含 `detail.fields`） | 走 `fieldErrors.fromServer(error)` 落到字段 |
| 后端 **422**（正文超长，跑到了服务端） | `detail.fields` 可能不存在 → `fromServer` 返回 false → **通用 toast 原样展示后端文案**。**这是本地校验失效时的兜底，不是主防线** |
| 删除简历 → 409（被关联） | 原样展示后端文案（如「该简历已被面试或练习关联，无法删除」），**不自定义** |
| 关联非本人简历 → 403 | 理论上不可达（下拉只列自己的简历）；若发生，原样展示 |
| 关联时面试已结束 → 409 | 原样展示；并**重新拉取面试详情**刷新状态，让区块转为只读 |
| `GET /candidate/resumes` 返回空数组 | **不是错误**：渲染空态与引导文案 |
| 401 | 走既有统一处理器（module-15 的按端 401 处理） |

> **全部沿用既有约定**：错误文案来自后端、前端不重写（module-07 §4.1）；字段级错误与 400 走同一出口（`components/form.js`）。**本模块不新增任何错误处理机制。**

---

## 7. 测试设计

### 7.1 纯函数单测（`src/__tests__/resume-form.test.js`，**新增**）

| 测试 | 断言 |
|---|---|
| `test_can_submit_requires_title` | 标题为空白 → false |
| `test_can_submit_requires_content` | 正文为空白 → false |
| `test_can_submit_trims_before_check` | 标题 / 正文前后空白不影响判定 |
| `test_can_submit_at_limit_ok` | 正文长度 == 上限 → **true** |
| `test_can_submit_over_limit_false` | 正文长度 == 上限 + 1 → **false** |
| `test_can_submit_empty_optional_fields_ok` | 姓名 / 联系方式为空 → 仍 true |
| `test_content_length_state_counts_chars` | `length` 等于 `content.length`（**不做去空白**，因为计数要反映用户实际看到的长度） |
| `test_content_length_state_over_flag` | 超限时 `over === true` |
| `test_max_length_constant_is_20000` | 导出的常量等于 `20000`（**与后端 `RESUME_CONTENT_MAX_LENGTH` 对齐的守门断言**，改了这里会红） |

> **最后一条是刻意的**：前端无法 import 后端配置，只能各写一份常量。用一条断言把「值是 20000」钉住，至少让改动成为一个**需要显式修改测试的动作**，而不是静默漂移。

### 7.2 手工走查（`mock/candidate-harness.html`，沿用 module-07 §8.4 的方式）

| 走查项 | 期望 |
|---|---|
| 空态 | 无简历时列表显示引导文案，新建按钮可用 |
| 新建 | 填四字段 → 保存 → 列表出现该条，`updated_at` 为当前 |
| 校验 | 标题留空 → 字段下出现错误、不发请求 |
| 超长 | 粘贴 25000 字 → 计数变红、保存禁用、**文本框内容仍是 25000 字（未被截断）** |
| 编辑 | 改标题 → 保存 → 列表标题更新 |
| 删除（未被引用） | 确认后 204，列表移除 |
| 删除（被引用） | 409，**显示后端原文**，列表不变 |
| 关联 | 面试详情页选一份 → 关联 → 显示「当前使用简历」 |
| 更换 / 解除 | 换一份 → 显示更新；解除 → 回到未关联态 |
| 面试已结束 | 区块只读，无按钮 |
| 刷题 | 开始练习选简历 → 进入会话；正常时无提示条 |
| 降级提示 | 构造 AI 失败（后端切到会抛错的 Provider）→ 会话页出现信息条；未关联简历时**不出现** |
| 候选人看不到 `match_reason` | 面试详情页的任何位置都不出现匹配理由 |

### 7.3 回归

| 项 | 断言 |
|---|---|
| `npm test` | 新增纯函数用例 + 既有 `radar.test.js` / `sse.test.js` **全绿** |
| `npm run build` | 构建通过 |
| HR 侧零回归 | 7 个 HR 页面功能不变（本模块不碰任何 HR 文件） |
| `standalone.html` | **未被修改**（`git status` 无该文件） |
| 后端回归 | 跑 `pytest tests/ -q` 确认候选人两个响应模型加字段未破坏既有用例（§2.3） |

---

## 8. 任务分解

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置（硬性）**：**module-15 已执行完毕**（候选人前端基座存在）。未执行前，本模块的任何任务都无法开始。

### Task 22.1：后端上游改动（候选人两个响应模型加 `resume_id`）

- [ ] `interview/schemas.py` 的 `CandidateInterviewItem` 与 `CandidateInterviewDetail` **都**加 `resume_id: int | None = None`，并让 `list_my_interviews` / `get_candidate_interview_detail` 填上它
- [ ] `get_candidate_interview_detail` 填入该值
- [ ] **先跑** `pytest tests/test_candidate_answering.py tests/test_interview.py -q` 确认既有断言（§2.3 的回归风险）
- [ ] 补一条测试：详情响应含 `resume_id`，未关联时为 null
- [ ] 提交

### Task 22.2：简历表单纯函数与常量

- [ ] 导出 `RESUME_CONTENT_MAX_LENGTH = 20000`（**注释写明与后端配置对齐**）
- [ ] 实现并导出 `canSubmitResume` / `contentLengthState`
- [ ] 写 §7.1 全部失败测试（**含「超限不截断」相关的长度判定与常量守门**）
- [ ] `npm test` 确认通过
- [ ] 提交

### Task 22.3：简历管理页

- [ ] 新建 `src/pages/candidate-resumes.js`（列表 + 空态 + 新建 / 编辑弹窗 + 删除确认）
- [ ] **textarea 不加 `maxlength`**，配字数计数与超限禁用
- [ ] `styles/pages.css` 追加样式
- [ ] `router.js` 加 `#/candidate/resumes`；`main.js` 注册页面
- [ ] 手工走查 §7.2 的前七项
- [ ] 提交

### Task 22.4：导航入口

- [ ] `candidate-shell.js` 侧边导航加「我的简历」（排在刷题与我的面试之间）
- [ ] 手工走查：候选人侧边栏出现入口、HR 侧不受影响
- [ ] 提交

### Task 22.5：面试详情关联简历

- [ ] `candidate-resumes.js` 加「用于面试」区块（逐场复选框 / 解除 / 已结束只读）
- [ ] **解除时显式提交 `{"resume_id": null}`**（§4.2）
- [ ] 无简历时给出引导链接
- [ ] 手工走查 §7.2 的关联四项
- [ ] 提交

### Task 22.6：刷题入口与降级提示

- [ ] `candidate-practice.js` 加「使用我的简历」下拉（无简历时禁用并给提示）
- [ ] `candidate-practice-session.js` 加降级信息条（**仅当 `resume_id` 非空且 `resume_match_applied === false`**）
- [ ] 手工走查 §7.2 的刷题与降级两项（**降级需后端切到会抛错的 Provider 来构造**）
- [ ] 提交

### Task 22.7：回归与走查收尾

- [ ] 跑完 §7.2 全部走查项
- [ ] `npm test` / `npm run build` 全绿
- [ ] 确认 `standalone.html`、HR 侧文件、`vite.config.js`、`index.html`、`package.json` **零改动**
- [ ] 跑 `pytest tests/ -q` 确认后端零回归
- [ ] 提交

---

## 9. 验收标准

- [ ] **module-15 已执行**（候选人前端基座存在于仓库中）
- [ ] 候选人两个响应模型都含 `resume_id`（列表 + 详情），「用于面试」弹窗能逐场回显当前关联
- [ ] 新增 **1 个**页面文件 `candidate-resumes.js`；**未新增**任何组件 / 工具 / CSS 文件
- [ ] 路由 `#/candidate/resumes` 注册且可访问；侧边导航出现「我的简历」
- [ ] 简历列表：新建 / 编辑 / 删除可用；空态有引导文案
- [ ] 简历弹窗：四字段齐备；标题与姓名 / 联系方式有 `maxlength`；**正文没有 `maxlength`**
- [ ] 正文超限时：计数变红、保存禁用、**文本内容不被截断**、不发请求
- [ ] 正文上限常量 == **20000**，且有守门断言；代码注释写明与后端对齐
- [ ] 删除被关联的简历 → **原样展示后端 409 文案**
- [ ] 面试详情页：可关联 / 更换 / 解除；**解除时显式提交 `{"resume_id": null}`**
- [ ] 面试非 `ongoing` 时关联区块**只读**
- [ ] 无简历时，关联下拉与刷题下拉都有引导文案与 `#/candidate/resumes` 链接
- [ ] 刷题可选用简历；不选时不提交 `resume_id`
- [ ] 会话页在 `resume_id` 非空且 `resume_match_applied === false` 时显示**信息条**（非错误样式）；未关联简历时**不显示**
- [ ] 候选人侧**任何位置都不出现 `match_reason`**，且不因字段缺失报错
- [ ] 全部错误文案**原样来自后端**，前端未重写
- [ ] `npm test` / `npm run build` 通过；既有前端用例零回归
- [ ] HR 侧 7 个页面功能不变；`standalone.html` 未被修改
- [ ] 后端 `pytest tests/ -q` 全绿

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **候选人前端整体不存在，本模块无基座** | 计划书**开头即声明**执行前提是 module-15 已完成 | 若不声明，执行者会面对「要改的文件根本不存在」，进而就地重建候选人前端——那会让两份计划书对同一批文件各有一套描述，必然漂移 |
| **不重复 module-15 的内容** | 只写增量 | 重复的代价是「两份文档描述同一批文件」，改一处必漏一处。执行顺序明确为「先 15，后本模块」 |
| **候选人的面试响应缺 `resume_id`** | 由**本模块**声明并实现该后端改动（§2.3），**列表与详情两个模型都要** | 没有它，关联选择器无法回显当前值（打开永远显示「未选择」），解除关联也无从判断。关联入口在简历页 ⇒ 要跨面试看，故列表也需要。按 module-13 的既有惯例，**改动跟着需要它的模块走** |
| **正文字段绝不能加 `maxlength`** | 用「计数 + 超限禁用提交」 | `maxlength` 会让浏览器**静默截断粘贴**——候选人以为整份存好了，尾部已丢。**无提示的数据丢失是最糟的一类故障** |
| **20000 常量前后端各写一份** | 各写一份 + 守门断言 + 注释指明对齐 | 前端无法 import 后端配置。与既有 `PASS_THRESHOLD = 6.5` 前后端各一份同一处理方式，是本项目已有的先例 |
| **编辑弹窗整体提交四字段（而非只交脏字段）** | 整体提交 | 四个字段在弹窗里全部可编辑且都有值，整体提交语义更直白，省掉「哪些字段是脏的」状态管理。**唯一例外**：可选字段空输入提交空串（不是 null，否则等于「不改」） |
| **解除关联必须显式提交 `null`** | 前端固定发 `{"resume_id": null}` | 后端要区分「传 null = 解除」（module-19 §4.2）。**不能靠省略字段表达解除** |
| **不做「记住上次用的简历」** | 不做前端记忆 | module-20 §1.2 已明确不做服务端记忆；前端再加 `localStorage` 记忆会让「为什么这次推荐不一样」无从解释 |
| **降级提示用信息条而非 toast / 错误样式** | 信息条 | 它在整个练习期间都为真（持久状态），toast 转瞬即逝；练习本身可用，红色错误条会让人以为坏了 |
| **未关联简历时不显示任何提示** | 不显示 | 那是候选人的正常选择，不是降级。显示提示会把「正常」说成「异常」 |
| **不显示 `match_reason` 给候选人** | 不显示，且不因缺失报错 | 它是 HR 的评估思路，PRD §4.6 限定候选人可见范围。后端不下发，前端就不该想要 |
| **前端测试只覆盖纯函数** | 判定逻辑抽成纯函数 + 其余走手工走查 | 本工程无 DOM 测试环境（`vite.config.js` 明确「只测纯函数」）。不引入 jsdom 等依赖（§2）。**把判定留在 `render()` 里 = 永远不会被测到** |
| **只加一个页面 / 不改 HR 侧任何文件** | 严格增量 | HR 侧零回归是硬要求；改 HR 文件会引入与 module-23 的交叉，两份计划书互相踩 |
| **关联区块的只读态只是体验优化** | 不做安全边界 | 后端对非 `ongoing` 一律 409（module-19 §5.1）。前端禁用只是避免「点了才吃错」 |
