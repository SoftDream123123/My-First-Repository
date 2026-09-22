# AI 智能面试助手 — MVP 需求文档

> 状态：MVP-1 已评审通过（2026-09-15）；2026-09-20 追加 MVP-2「面试者（候选人）侧」需求；**2026-09-20 追加 MVP-3「简历驱动与报告导出」需求**；**2026-09-21 修正 §4.9：候选人反馈的「综合结论」不带招聘方的去留判断**；**2026-09-21 修正 §4.1 / §7 / §8：`accept` 改为公开端点，且复用已有候选人账号时必须校验密码**；**2026-09-21 修正 §4.7：错题本条目下发 `dimension` 与 `question_type`（此前该端点接受这两个筛选参数、却不下发对应字段）**；**2026-09-22 整体走查修正 §4.9 / §7：反馈条目不再内嵌维度分（否则绕过脱敏）、评估失败按「有无旧报告」决定回退目标、复用被禁用账号必须拒绝、「非空作答」统一按去除空白判定**；**2026-09-22 追加 MVP-4「简历文件上传解析」需求：候选人可上传 DOCX / PDF，由后端解析为纯文本回填正文后自行确认（不存原文件、不落盘、不改表结构）**
> 定位：单机部署的双端 Web 应用
> - **HR / 面试官端**：AI 辅助真人面试官完成「出题 → 记录 → 评估 → 报告」闭环
> - **面试者（候选人）端**：账号与权限、刷题练习题库、在线答题、查看脱敏反馈
>
> 约束：仍是**单机 PC 端**，**技术栈不做任何变更**（原生前端 + FastAPI + MySQL，不引入新框架与中间件）。MVP-3 新增依赖为 `python-docx`；MVP-4 再新增 `pypdf` 与 `python-multipart`（见 §2）

---

## 1. 概述

### 1.1 项目定位

一个面向 HR / 面试官与面试者（候选人）的 Web 应用。AI 扮演辅助角色，服务两条业务线：

**HR / 面试官端** —— 帮助真人面试官：

1. 查看候选人在线提交的简历
2. 根据岗位（JD + 评估维度）生成面试题，并可按候选人简历从题库补题
3. 在面试过程中记录候选人回答（HR 手工录入，或由候选人在线作答）
4. 面试前生成准备提纲、考察重点与问题预案
5. 面试结束后自动评估候选人（逐题评分 + 多维评分）
6. 生成结构化面试报告，并导出为 DOCX / PDF

**面试者（候选人）端** —— 服务应聘者本人：

1. 凭邀请码激活账号，或自助注册（仅刷题权限）
2. 录入自己的简历（粘贴纯文本，或上传 DOCX / PDF 由系统解析出文字后自行确认），按简历推荐练习题目
3. 用刷题题库自主练习，提交后即时判分并看参考答案与解析
4. 在线作答 HR 发起的真实面试，交卷后由 HR 侧继续推进评估
5. 面试评估完成后查看面向候选人的脱敏反馈

### 1.2 目标

- 打通「创建面试 → 出题 → 记录 → 评估 → 报告」完整闭环
- 打通「发邀请 → 在线作答 → 交卷 → 反馈」候选人闭环
- 打通「创建面试 → 发邀请 → 候选人录简历 → 按简历补题 → 准备 → 面试 → 评估 → 报告 → 导出」的简历驱动链路
- 提供可复用的题库，同时服务 HR 出题与候选人刷题
- 提供候选人刷题练习闭环：取题 → 判分 → 解析 → 错题本 → 统计
- 简历由**候选人单侧录入**，同时服务两个方向：HR 侧驱动补题，候选人侧驱动刷题推荐
- 面试前提供可编辑的准备提纲，降低 HR 临场负担
- AI 能力通过抽象接口接入，无大模型 Key 也能以 Mock 方式演示和测试

### 1.3 非目标（MVP 明确不做）

- 报告分享（导出见 4.12：PDF 走前端浏览器打印、DOCX 走后端生成）
- 语音 / 视频面试、录音转写
- **保留简历原文件**（上传仅用于解析取文字：不存原文件、不落盘、不提供「回看原件」，见 4.10）
- 多候选人横向对比
- 后端生成 PDF（脱离浏览器的批量 / 后台导出）
- 邮件 / 通知（邀请码在系统内展示与复制，不发送邮件）
- 流式出题（出题是同步的，仅评估环节流式）
- 移动端（仅 PC）
- **候选人社交能力**：排行榜、积分、成就、讨论区
- **在线编程判题**：代码沙箱执行、测试用例运行（刷题仅做文本问答）
- **候选人修改已交卷的作答**（交卷后候选人侧锁定）
- **候选人查看逐题分、维度分与雷达图**（默认脱敏，见 4.9）
- 候选人收藏题目、笔记

---

## 2. 技术栈与约束

| 项 | 选择 | 约束 |
|---|---|---|
| 架构 | 前后端分离 | 后端纯 API，不渲染页面 |
| 前端 | 原生 HTML + CSS + JavaScript + Vite 构建 | 无 UI 框架 |
| 后端 | Python + FastAPI | — |
| 数据库 | MySQL | — |
| 后端分层 | router → service → repository → MySQL | 严格单向依赖 |
| 模块组织 | 每个模块独立 Python package | — |
| 终端 | 仅 PC 端 | 不考虑移动端响应式 |
| 部署 | 单机部署（前后端同源，`127.0.0.1:8000`） | 不引入 Redis / 消息队列等外部中间件 |
| 前端入口 | HR 端与候选人端**同一 Vite 工程**内的两组路由 | 不新建工程、不换框架、不加构建产物 |

> 单机部署带来两条实现约束：前端限流类能力用**进程内计数**实现；同一 origin 下两端登录态必须**按端分 key**存储（见 9 非功能需求）。

**MVP-3 新增依赖（仅一项）**：`python-docx`（解析后实际装 `python-docx 1.2.0` + `lxml 6.1.3`，约 4.3 MB），用于后端生成 DOCX 报告（见 4.12）。一条规避路径：PDF 导出走前端浏览器打印（`window.print()` + `@media print`），因此**不引入任何 PDF 生成库**。

**MVP-4 新增依赖（两项）**：`pypdf`（PDF 读取）与 `python-multipart`（FastAPI 解析 `multipart/form-data` 的必需件；缺它则 `UploadFile` 直接报错）。用于简历文件上传解析（见 4.10）。DOCX 一路**复用已在依赖表里的 `python-docx`，不引入第二个 DOCX 库**。三个解析相关库均纯 Python、无外部中间件。**只读不写**：两者都只把上传文件抠成文本，**不生成 PDF、不落盘**。

> ⚠️ **安装必须走镜像**：本机直连 `pypi.org` / `files.pythonhosted.org` 会超时（已实测，5 次重试均 0 字节），直连索引还会把 `python-docx` 误解析到 2021 年的 `0.8.11`。可用清华镜像：
> `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple python-docx`（已实测可解析到 1.2.0 与 cp313-win_amd64 的 lxml wheel）
> MVP-4 的两个依赖同法安装：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pypdf python-multipart`
> `requirements.txt` 中照常写 `python-docx>=1.1` / `pypdf>=5.0` / `python-multipart>=0.0.9`，镜像只影响安装命令、不影响依赖声明。

---

## 3. 系统架构

### 3.1 前后端分离

- 前端：同一工程内的两组入口 —— `/hr` 后台（登录、岗位、题库、面试、报告）与 `/candidate` 端（登录/注册、刷题、我的面试、反馈），通过 REST + SSE 与后端交互
- 后端：FastAPI 提供 JSON API，JWT 鉴权，不负责页面渲染

### 3.2 后端严格分层

每个模块内部统一遵循：

```
router    → HTTP 端点：参数校验、鉴权、统一响应包装
service   → 业务逻辑：流程编排、事务、调用 AI Provider
repository → 数据访问：CRUD，对接 MySQL
```

依赖方向只允许自上而下：`router → service → repository`。service 依赖 repository 接口（依赖注入），不跨层调用、不反向依赖。

### 3.3 模块划分（每个模块独立 package）

| 包名 | 职责 | 依赖 |
|---|---|---|
| `auth` | 用户、登录、JWT、角色（admin/hr/candidate）、数据隔离、候选人注册 | — |
| `position` | 岗位：名称、JD、评估维度 | auth |
| `question` | 题库：题目 CRUD、分类、标签、关联岗位、题型与参考答案 | auth, position |
| `resume` | 简历：候选人侧纯文本增删改查、上传文件解析取文本，HR 侧经面试只读 | auth |
| `interview` | 面试：实例、候选人信息、出题组装、回答记录、状态机、作答邀请、面试前准备助手 | auth, position, question, resume, ai |
| `evaluation` | 评估：逐题评分、多维评分、报告、流式评估、候选人反馈视图、报告导出 | auth, interview, ai |
| `practice` | 刷题：练习会话、逐题作答、判分与解析、错题本、练习统计、按简历推荐 | auth, question, resume, ai |
| `ai` | AI Provider 抽象：出题 / 匹配 / 评估 / 判分 / 反馈 / 准备提纲接口 + 真实 / Mock 实现 | — |

关键依赖方向：

- `ai` 是基础设施，被 `interview`（出题 / 准备提纲）、`evaluation`（评估）、`practice`（判分 / 推荐）调用
- `evaluation` 读取 `interview` 的回答数据生成报告
- `practice` 依赖 `question` 取题、依赖 `ai` 判分与推荐、依赖 `resume` 取简历；**不依赖 `interview`**（刷题与真实面试解耦）
- `resume` 由**候选人单侧写入**，被两个方向消费：`interview`（HR 读取 + 匹配补题）与 `practice`（刷题推荐）均**单向依赖** `resume`，`resume` 不反向依赖任何业务模块——否则会把 `practice ↔ interview` 的循环依赖引进来
- 各业务模块均依赖 `auth` 做鉴权与数据隔离

---

## 4. 功能需求

### 4.1 用户与鉴权（auth）

- 角色三种：`admin` / `hr` / `candidate`
- 系统内置一个初始管理员（admin），通过迁移/配置脚本 seed
- admin 可创建 / 管理用户，并可指定角色（admin / hr）
- 普通 HR 不可自行注册
- 候选人账号两种来源：
  1. **邀请码激活**：HR 为某个面试生成作答邀请码，候选人凭码注册或激活账号，并绑定该面试
     - **该接口是公开端点**：`POST /api/candidate/invitations/{code}/accept` **不要求 JWT**。
       拿码的人往往**还没有账号**（关闭自助注册时更是唯一入口），要求他先登录才能激活，
       会让整条邀请链自相矛盾 —— 没有账号就拿不到 token，没有 token 就激活不了
     - 账号创建与复用规则（错误语义见 §7）：
       - 用户名未占用 → 按请求体里的密码创建 `candidate` 账号
       - 用户名已被 `candidate` 占用 → **必须校验密码一致**才复用。密码不符即拒绝 ——
         否则「知道对方用户名」就等价于能把他人的账号绑到自己的邀请上，进而读到对方的面试
       - 用户名已被 `hr` / `admin` 占用 → 拒绝，沿用既有「用户名已被占用」语义
     - `CANDIDATE_SELF_REGISTER` 只控制**开放注册**，**不影响凭邀请建号** ——
       关闭自助注册后，邀请码仍是候选人的唯一入口，必须可用
  2. **自助注册**：仅刷题权限，不绑定任何面试；由配置项 `CANDIDATE_SELF_REGISTER` 控制，默认开启
- 登录成功后签发 JWT；所有业务接口需携带 JWT
- 数据隔离：
  - admin 可访问全部
  - 普通 HR 只能访问自己创建的 position / question / interview
  - candidate 只能访问自己的 `practice_*` 数据，以及**自己被邀请且已接受**的面试
- **权限守卫收紧（本期必做）**：现有 HR 侧路由只校验「已登录」，加入 candidate 角色后，候选人 token 可直接调用 HR 接口。因此：
  - HR 侧路由必须显式校验角色（admin / hr 均可通过）
  - 候选人侧路由校验 candidate 角色
  - 权限校验工具需支持**多角色**判定，而非单一角色相等判断
  - 候选人数据隔离不能复用 `created_by` 判据，需新增「持有该面试的有效邀请」这一校验路径

### 4.2 岗位管理（position）

- 岗位字段：名称、JD（岗位描述）、评估维度列表
- 评估维度用于多维评分（如：沟通能力、专业能力、逻辑思维、文化契合）
- 支持岗位的增删改查；删除前校验是否被面试引用

### 4.3 题库管理（question）

- 题目字段：内容、所属岗位、分类、对应评估维度、难度、标签、来源（bank/ai）
- **新增字段（服务刷题）**：题型（单选 `single_choice` / 简答 `short_answer`）、选项列表（单选题的 `options`）、参考答案（`reference_answer`）、解析（`explanation`）
- 题型、选项、参考答案、解析可由 HR 手工录入；简答题的参考答案与解析可调 `ai` Provider 生成后由 HR 确认
- 支持题目的增删改查，支持按岗位 / 分类 / 维度 / 难度 / 题型筛选
- 题库中的题目可被面试抽取复用，也可被候选人刷题取用

### 4.4 面试管理（interview）

- 创建面试：选择岗位、填写候选人信息（姓名、联系方式）
- 出题组装（同步）：题库抽取 N 题（默认 5）+ AI 按 JD/维度补充 M 题（默认 3），合并成题目列表并写内容快照
- **简历关联（候选人侧）**：候选人凭邀请激活并绑定某场面试后，可为该场面试关联自己的一份简历（见 4.13）
- **按简历补题（HR 侧）**：候选人关联简历后，HR 可触发一次 AI 匹配，从题库追加 K 题（默认 3，见 4.14）。这是简历进入出题流程的**唯一通路**——简历由候选人提交，时间上晚于创建面试，因此匹配不发生在创建时
- 简历匹配产出的题目在 `interview_question.source_snapshot` 记为 `resume_match`，AI 给出的匹配理由写入 `match_reason`（非匹配来源的题为 `null`），供前端展示「为什么选这道题」
- 与既有约束的关系：**出题组装后不提供换题 / 删题接口**（沿用既有约束）；「按简历补题」是唯一的加题例外，且**只追加、不改动既有题目**
- 记录回答（两条通道，共用同一份作答数据）：
  - **HR 手工录入**：HR 逐题录入候选人回答，可随时编辑
  - **候选人在线作答**：候选人凭邀请码进入后逐题作答（见 4.8）
- **作答邀请管理**：生成 / 查看 / 撤销邀请码；邀请码有有效期（默认 7 天）、一次性接受、不可枚举
- 候选人交卷后，其作答通道锁定；**HR 侧不受锁影响**，仍可修订作答
- 面试状态机（见 5.1）
- 数据隔离：HR 仅见自己创建的面试

### 4.5 评估与报告（evaluation）

- 评分统一采用 **0–10 分制**（逐题分、维度分、总分均 0–10）
- 逐题评分：对每一题的回答给出分数 + 评语
- 多维评分：按岗位评估维度逐项打分 + 评语（用于雷达图）
- 汇总报告：总分、综合结论、优点、待改进
- 报告可导出为 DOCX / PDF（见 4.12）；导出的是 HR 报告全文，不含候选人脱敏视图
- 评估以 SSE 流式返回（见 5.3）
- **面向候选人的反馈视图**：在 HR 报告之外提供候选人可见的脱敏视图，仅含综合结论、优点、待改进；总分、逐题分、维度分与雷达图默认不下发，由配置项开放；**结论的口径与报告不同（不带去留判断）**，见 4.9

### 4.6 面试者账号与权限（candidate）

- 账号来源见 4.1：邀请码激活（绑定面试）或自助注册（仅刷题）
- 登录后进入候选人端 `/candidate`
- 可见范围严格限定：
  - 自己的练习会话与作答（`practice_*`）
  - 自己被邀请且已接受的面试的**题目与自己提交的作答**
  - 自己参与的、已评估完成的面试的脱敏反馈
- 不可见：其他候选人的任何数据、HR 的评语与评分明细、未接受的面试
- 不可修改已交卷的作答
- 不能访问 HR 侧任何接口（未通过角色校验一律 403）

### 4.7 刷题练习（practice）

- 取题：按岗位 / 分类 / 维度 / 难度 / 题型筛选取题，题型含单选与简答
- **按简历推荐**：开始练习时可关联一份自己的简历（`resume_id`），取题时由 AI 从符合筛选条件的题目中按简历相关度挑选排序；未关联简历时退回既有筛选取题逻辑
- **岗位筛选的可选值**：由「**有题目的岗位**」列表提供（`GET /candidate/positions`）。候选人无权访问 HR 侧的岗位接口，且刷题取题本身取全库题目，因此筛选项必须与之口径一致——否则 UI 表达不出接口支持的筛选范围。该接口只下发岗位 `id` / 名称 / 题量，**不下发 JD**
- 练习会话：开始一次练习（记录筛选条件）→ 逐题作答 → 结束；记录总题数、已答题数、正确数
- **我的练习会话列表**（`GET /practice/sessions`）：候选人可查看自己的会话（含**进行中**的），以便继续未完成的练习或回看历史
- 即时判分：
  - 单选题：本地规则判分（不消耗 AI）
  - 简答题：调 `ai.grade_practice_answer` 判分并返回解析
  - 无大模型 Key 时由 Mock Provider 给出确定性判分，保证可演示与可测试
- 参考答案与解析：提交后展示
- 错题本：由判错的作答派生查询，**不单独建表**；条目带**维度**与**题型**，与它支持的两个筛选参数一致
- 练习统计：累计题量、正确率、按维度正确率
- 明确不做：收藏、笔记、排行榜、积分、编程题判题

### 4.8 在线答题（候选人作答）

- 入口：HR 生成邀请码 → 候选人在候选人端输入邀请码（或打开邀请链接）→ 激活并绑定面试
- 作答：整卷题目下发，候选人逐题作答，作答实时保存
- 交卷：写入交卷时间，候选人侧作答通道锁定
- 交卷后仍由 HR 确认面试完成（**不自动推进面试状态**，见 5.1）
- **「已作答」的判定唯一口径**（2026-09-22 修正）：作答内容**去除首尾空白后非空**才算已作答；
  只敲空格的作答与空串一样视为未作答。该口径必须与评估入口一致 —— 评估侧本就按未作答
  送分，若计数改用「非空串」就会得出「HR 看到标着已作答的题、AI 却根本没评过分」。
  判据统一在**读取**侧，不改写入侧原文（作答可能是代码片段，需保留缩进与换行）
- 数据隔离：仅能访问自己被邀请且已接受的面试

### 4.9 面试结果与反馈

- 候选人在面试评估完成后可查看脱敏反馈
- 默认仅下发：综合结论、优点、待改进
- 默认不下发：总分、逐题分、维度分、雷达图
- 是否放开评分明细由配置项 `CANDIDATE_FEEDBACK_LEVEL` 控制（`summary` 默认 / `full`）
- **综合结论不带招聘方的去留判断**（2026-09-21 修正）：只讲这一场的表现——强在哪、弱在哪，
  不出现「建议进入下一轮 / 不建议继续推进」这类结论。报告里的那句是 HR 的决策，应由 HR
  另行沟通，而不是让当事人在自助页面上读到。**因此 `generate_candidate_feedback` 不是报告
  结论的复述，而是面向本人的重写**；优点 / 待改进的**条目**仍与 HR 报告逐条一致（便于两处
  对照），只重写结论这一项
- **优点 / 待改进的条目内不得出现分数**（2026-09-22 修正）：条目下发给候选人时是**原样**
  透传的（见上一条），因此条目本身若写着「沟通能力（7.5）」就等于从这条路径把维度分
  漏给候选人，与「默认不下发维度分」直接冲突。分数只存在于 `dimension_score` 表，
  供 HR 端雷达图使用；`summarize_report` 生成条目时只描述维度名与表现
- HR 端报告视图保持不变

### 4.10 简历管理（resume）

- 简历正文以**纯文本**存储与录入；两种录入方式最终落在同一个 `content` 字段上：
  - **粘贴纯文本**（既有）
  - **上传文件解析**（MVP-4 新增）：上传 DOCX / PDF，由后端解析为纯文本，**回填到正文框、由候选人自己确认或改完再保存**
- **上传只做「取文字」这一件事**：`POST /candidate/resumes/parse` 是**不落库、不落盘**的纯转换端点——不建简历、不改简历、服务器上不留那个文件。只有候选人随后确认保存，文本才成为简历（见 5.2）
- 因此**简历表结构完全不变**：不新增文件路径字段、不存原文件、不存解析产物
- 支持的格式：`.docx`、`.pdf`。**不支持** `.doc`（97–2003 旧二进制格式）、加密或需要密码的 PDF、以及**不含文字层的扫描件 PDF**——最后一种解析不出文字，须提示候选人改用粘贴
- 上传体积上限由配置项 `RESUME_UPLOAD_MAX_BYTES` 控制（默认 5 MB）
- 解析出的文字**不做截断**：超过 20000 字符时照样回填，由候选人按既有的字数计数自行精简（与「不静默截断」的既有约定一致）
- 解析结果**不静默覆盖**候选人已输入的正文：正文框非空时须先经候选人确认才替换
- 字段：标题、简历正文（纯文本）、候选人姓名（可选）、联系方式（可选）
- **写入方只有候选人**：候选人在 `/candidate/resumes` 自助录入与维护
- **HR 不提供简历 CRUD**：HR 只读，且只读**与某场自己名下面试关联**的简历（见 4.13 / 4.14）
- 数据隔离：
  - 候选人只能读写自己的简历（`created_by` 判据）
  - HR 只能读取与自己名下某场面试关联的简历——判据沿用 4.1 既有的「持有该面试的有效邀请」这条既有校验路径，**不引入新机制**
  - admin 见全部
- 简历**不绑定**某场面试或某次练习：同一份简历可被多场面试、多次练习复用；`interview.resume_id` 与 `practice_session.resume_id` 只记录引用
- 候选人可为不同面试关联不同简历（例如投不同岗位），关联动作见 4.13
- 简历的两种消费方式：HR 侧按简历补题（见 4.14）、候选人侧刷题推荐（见 4.7）
- 删除简历时若已被面试或练习关联 → 拒绝（409）
- 简历正文长度上限 20000 字符（避免超长文本打爆 AI 上下文）

### 4.11 面试前准备助手（interview）

- 面向 HR：在一场面试开始前，由 AI 生成三部分产出
  - **面试提纲**（`outline`）：分阶段的时间安排与要点
  - **考察重点**（`focus_points`）：按岗位评估维度给出应重点验证的能力项与理由
  - **问题预案**（`question_plan`）：建议提问及每题的考察意图、可追问方向
- 输入：岗位（JD + 评估维度）+ 候选人信息 + 简历（可选，未关联简历也能生成）+ 本场已有题目（可能为空）
- 产出**落库持久化**（`interview_prep`，一场面试一份），支持查看与编辑；重新生成会**整体覆盖**既有内容
- 状态约束：面试处于 `draft` / `ongoing` 时可生成与编辑；`completed` 及之后返回业务错误（409）
- **不进入面试状态机**：准备助手是面试的前置工作稿，与「创建 → 出题 → 记录 → 评估」主流程正交，不影响 `interview.status`（见 5.1）
- 一次生成即整批落库，不做流式

### 4.12 报告导出（evaluation / 前端）

- 导出对象**仅限 HR 侧**的面试报告（4.5）与面试前准备助手提纲（4.11）；候选人脱敏反馈不提供导出
- **DOCX（后端生成）**：`GET /interviews/{id}/report/export?format=docx`，用 `python-docx` 生成并返回文件流
  - 内容：面试基本信息（岗位 / 候选人 / 面试时间）+ 总分 + 综合结论 + 优点 + 待改进 + 逐题评分表 + 多维评分表
  - **不含雷达图**——Python 侧重画成本不划算；需要图形的场景走 PDF
- **PDF（前端浏览器打印）**：报告页与准备助手页各加「导出 PDF」按钮，触发 `window.print()`，配套 `@media print` 样式隐藏导航与操作栏
  - 雷达图直接沿用页面上已渲染的图形，所见即所得
  - 不提供后端 PDF 生成接口，因此**不支持脱离浏览器的批量 / 后台导出**
- 两条路径共用同一份数据来源，不额外落库导出记录

### 4.13 候选人关联简历到面试（interview / candidate）

- 简历由候选人提供，因此关联动作也由候选人发起：候选人凭邀请激活并绑定某场面试后，为该场面试指定一份自己的简历
- 接口：`PUT /candidate/interviews/{id}/resume`，body `{resume_id}`（传 `null` 解除关联）→ 写 `interview.resume_id`
- 约束：
  - 只能关联**属于本人**的简历（`created_by` 为本人），否则 403
  - 只能在**本人已接受邀请**的面试上操作，否则 403（沿用既有候选人隔离判据）
  - 一场面试只关联一份简历；同一份简历可被多场面试关联
  - 面试 `completed` 及之后拒绝变更关联（409）——简历是面试的输入，面试结束即冻结
- **候选人必须能看到「这场现在关联的是哪份简历」**：`GET /candidate/interviews` 与 `GET /candidate/interviews/{id}` 下发该场的 `resume_id`（未关联为 `null`）。缺了它，候选人只能盲改关联，「解除关联」也无从判断该不该给 —— 关联状态是他自己的数据，**能写就必须能读**
- **这是 HR 读取候选人简历的唯一通路**：没有这条关联，HR 看不到候选人的任何简历
- 候选人可在面试进行中随时改关联（例如换一份更贴合的简历），改后 HR 需重新触发补题才会生效（见 4.14）

### 4.14 简历匹配补题（interview）

- 目的：在既有出题结果之上，按候选人简历**追加**一批更贴合其经历的题目
- 触发：HR 在面试详情页点「按简历补题」，接口 `POST /interviews/{id}/questions/match`
- 前置条件（不满足对应报错）：
  - 面试处于 `ongoing` → 否则 409（`draft` 尚未出题，无追加对象；`completed` 及之后冻结）
  - `interview.resume_id` 非空 → 否则 409「该面试尚未关联简历」
- 行为：
  1. 取岗位（JD + 评估维度）+ 该面试关联的简历 + 目标岗位的题库候选池
  2. 调 `ai.match_questions_by_resume`，返回题目 id 与匹配理由（**只挑不生成**，见 6）
  3. 追加为新 `interview_question`：`seq` 续接本场最大值，`source_snapshot='resume_match'`，`match_reason` 写入 AI 给出的理由
- **幂等**：本场已有的 `question_id` 跳过，不重复追加。HR 连点不会产生重复题目
- 可重复触发：候选人换了简历、或 HR 想再补几题，都可再次调用；每次只追加本场尚不存在的题
- AI 调用失败 → 降级为「本次补题未生效」，不改变面试状态、不动既有题目（见 7）
- 补题完成后**不提供撤销接口**：追加的题目与既有题目一样不可删（沿用既有约束）

---

## 5. 数据模型与业务流程

### 5.1 状态机

**面试状态机（本次不变）**

```
draft（草稿）→ ongoing（进行中）→ completed（已完成）→ evaluating（评估中）→ evaluated（已评估）
```

| 迁移 | 触发 |
|---|---|
| draft → ongoing | 出题组装完成 |
| ongoing → completed | HR 标记面试完成 |
| completed → evaluating | 触发流式评估 |
| evaluating → evaluated | 评估流结束、报告落库 |
| completed → ongoing | 回退以补充/修改回答（可重新评估） |

> **设计取舍：候选人作答不进入面试状态机。** 状态机描述的是 HR 侧的面试推进流程，且已被现有实现与测试固化；把候选人作答做成状态会让 `draft` / `ongoing` / `completed` 的语义分裂（例如「HR 还没开始面」与「候选人已交卷」相互正交）。因此候选人作答只作为**输入通道**存在：通过 `answer.source`、`answer.answered_by`、`answer.submitted_at` 表达作答来源与交卷事实，面试是否完成仍由 HR 决定。

> **设计取舍：面试前准备助手不进入面试状态机。** 准备助手（4.11）是面试开始前的工作稿，其「已生成 / 已编辑」与面试推进阶段相互正交；把它做成状态会让 `draft` / `ongoing` 的语义分裂。因此只用 `interview_prep.generated_at` / `edited_at` 记录事实，面试是否可生成准备提纲由 `status` 判定（`completed` 及之后拒绝），状态本身仍由出题组装与 HR 标记驱动。

**作答邀请状态机（新增，与面试状态解耦）**

```
pending（待接受）→ accepted（已接受） / revoked（已撤销） / expired（已过期）
```

| 迁移 | 触发 |
|---|---|
| pending → accepted | 候选人凭码激活并绑定账号 |
| pending → revoked | HR 撤销邀请 |
| pending → expired | 超过有效期（默认 7 天） |

### 5.2 数据模型（概念级）

| 实体 | 关键字段 | 所属包 |
|---|---|---|
| `user`（改） | id, username, password_hash, role, is_active, created_at | auth |
| `position` | id, name, jd, evaluation_dimensions(JSON), created_by | position |
| `question`（改） | id, position_id, category, dimension, content, question_type, options(JSON), reference_answer, explanation, difficulty, tags, source, created_by | question |
| `resume`（新） | id, title, content, candidate_name, candidate_contact, created_by, created_at, updated_at | resume |
| `interview`（改） | id, position_id, **resume_id**, candidate_name, candidate_contact, status, created_by, created_at, completed_at | interview |
| `interview_question`（改） | id, interview_id, question_id, seq, content_snapshot, dimension_snapshot, source_snapshot, **match_reason** | interview |
| `interview_prep`（新） | id, interview_id, outline(JSON), focus_points(JSON), question_plan(JSON), generated_at, edited_at | interview |
| `interview_invitation`（新） | id, interview_id, code, candidate_user_id, status, expires_at, accepted_at, created_by | interview |
| `answer`（改） | id, interview_question_id, content, source(hr/candidate), answered_by, submitted_at, recorded_at | interview |
| `question_score`（改） | id, interview_id, interview_question_id, score, comment | evaluation |
| `dimension_score` | id, interview_id, dimension, score, comment | evaluation |
| `report` | id, interview_id, overall_score, conclusion, strengths, weaknesses | evaluation |
| `candidate_feedback`（新） | id, interview_id, conclusion, strengths(JSON), weaknesses(JSON), generated_at | evaluation |
| `practice_session`（新） | id, candidate_user_id, position_id, **resume_id**, category, dimension, difficulty, status, total, answered_count, correct_count, started_at, finished_at | practice |
| `practice_item`（新） | id, session_id, question_id, content_snapshot, options_snapshot(JSON), reference_answer_snapshot, user_answer, is_correct, score, explanation, answered_at | practice |

说明与取舍：

- **按实现校正两处既有文档偏差**：`answer` 的唯一键挂在 `interview_question_id`（原文写作 `interview_id + question_id`），这样才能支撑「同一道题库题在一次面试中出现两次」；`interview_question` 另含 `dimension_snapshot`（维度名快照，岗位维度改名后评估归集不错位）与 `source_snapshot`（来源快照）。快照字段保证题库删改不影响历史面试与历史评估。
- **`user.role` 增加 `candidate`**；用户不做物理删除，只置 `is_active=false`（`position` / `question` / `interview` / `practice_session` 均通过外键关联本表）。
- **作答不做历史版本**：HR 覆盖候选人作答时，只保留最新内容与最后修改者 —— `source` 表示作答最初来自哪条通道，`answered_by` 表示最后修改者，`submitted_at` 记录候选人交卷时间（HR 手工录入时为 `null`）。代价是覆盖前的候选人原文不可追溯，MVP 接受。
- **错题本不建表**，由 `practice_item.is_correct=false` 派生查询。
- **错题本条目下发 `dimension` / `question_type`**（2026-09-21 修正）：该端点一直**接受**
  这两个筛选参数（§4.7），却不下发对应字段。后果是前端既取不到下拉的候选值，也没法在
  条目上标出维度与题型——那两个筛选项成了只有「不限」一项的空壳。两个值都取自
  `practice_item` 的快照列（`dimension_snapshot` / `question_type`），与筛选读的是**同一列**，
  因此筛选结果与标注必然自洽；两列本就存在，**不需要改库**。
- **`practice_item` 带题目快照**：会话开始时即按筛选条件取题生成待答项（`user_answer` 为空），并写入 `content_snapshot` / `options_snapshot` / `reference_answer_snapshot`；题库删改不影响进行中与历史练习的复看。逐题提交只回填 `user_answer` / `is_correct` / `score` / `explanation` / `answered_at`。
- `question` 复用为刷题题源，不另建练习题库表 —— 单一题库同时服务 HR 出题与候选人刷题。
- **`resume` 只有候选人一个写入方**：`created_by` 恒为候选人用户 id。HR 的读取权限不在本表上判定，而在「该简历是否关联到自己名下的某场面试」上判定——判据复用 4.1 既有的邀请链，因此不需要 `owner_type` 之类的额外字段。
- **简历只存纯文本**：不存原文件、不存解析产物，`resume` 表结构不因上传而变动。代价是**服务器上不留原件**——上传的文件解析完即丢弃，事后无法「回看原件」（MVP-4 的明确取舍，见 1.3）
- **解析失败分支只存在于上传端点**（MVP-4）：`POST /candidate/resumes/parse` 不落库，解析失败只让那一次上传返回错误、**不产生任何简历数据**，因此 `POST/PUT /candidate/resumes` 的错误契约与既有实现完全不变
- **`interview.resume_id` 由候选人侧写入**（4.13），不是 HR 创建面试时写入。`interview.resume_id` / `practice_session.resume_id` 都只记录引用、不复制简历内容。删除简历前会校验引用（4.10），因此不存在悬空引用。**简历更新后不影响已补的题**——题目内容与匹配理由已快照在 `interview_question` 中。
- **`interview_question.match_reason` 与 `source_snapshot='resume_match'` 成对出现**：前者存 AI 给出的匹配理由，后者标记来源。非简历匹配来源的题 `match_reason` 为 `null`。
- **`interview_prep` 一场面试唯一**（`interview_id` 加唯一约束）：重新生成即覆盖，不做版本历史；三个 JSON 字段整体替换，不做字段级合并。
- **`candidate_feedback` 独立成表，而非给 `report` 加列**（MVP-2 补充）：两份文本**受众不同、可见性规则不同**。混在一张表里，`report` 的任何读取路径（含 HR 报告接口）都可能不小心把候选人字段带出去；独立成表让可见性边界落在**表**这一层——HR 报告接口**结构上读不到**候选人字段，`report` 的 schema 也完全不动，直接满足 §4.9「HR 端报告视图保持不变」。另有两处刻意缺失：**不设 `updated_at`**（反馈的输入就是报告，报告重评即整行重建，支持「更新」就必须回答「哪部分过期了」）；**不存总分**（总分属「评估结果」而非「候选人文案」，可见性层与存储层解耦后，改 `CANDIDATE_FEEDBACK_LEVEL` **不需要重新生成反馈**）。

### 5.3 五条核心流程

**① 创建面试 + 出题（同步）**
1. HR 选岗位 + 填候选人信息
2. 系统从题库按岗位/维度抽取 N 题
3. 调 `ai` Provider 出题接口，按 JD + 评估维度补充 M 题
4. 合并生成题目列表并写内容快照，面试进入 `ongoing`

**② 面试进行（HR 手动录入）**
1. HR 逐题录入候选人回答，回答实时保存到 `answer`
2. HR 标记完成 → 进入 `completed`

**③ 流式评估（SSE）**
1. HR 点「开始评估」→ 状态 `evaluating`，前端建立 SSE 连接
2. 后端流式推送三阶段：逐题评分 → 多维评分 → 汇总报告
3. 结束事件后状态 `evaluated`，前端渲染雷达图 + 报告

**④ 在线答题（HR 发邀请 → 候选人在线作答）**
1. HR 为面试生成作答邀请码（`pending`）
2. 候选人凭码激活账号并绑定该面试（`accepted`）
3. 候选人逐题作答，作答实时保存到 `answer`（`source=candidate`，`answered_by=候选人`）
4. 候选人交卷 → 写 `submitted_at`，候选人侧通道锁定；面试状态不变
5. HR 可修订作答（`source` 保留 `candidate`，仅更新 `answered_by`），随后标记 `completed`
6. 走既有流式评估（流程 ③），评估完成后候选人可查看脱敏反馈

**⑤ 刷题练习**
1. 候选人开始一次练习，选定岗位 / 分类 / 维度 / 难度（可再关联一份自己的简历）→ 生成 `practice_session`，按条件取题并生成待答项（写题目快照）；**关联了简历时，由 `ai.match_questions_by_resume` 从符合条件的候选中按简历相关度挑选排序**
2. 逐题提交：单选本地规则判分；简答调 `ai.grade_practice_answer` 判分并取解析
3. 判分结果回填 `practice_item`（`user_answer`、`is_correct`、`score`、`explanation`），并更新会话计数
4. 结束练习 → 会话置完成，展示小结；错题本与统计由 `practice_item` 派生

**⑥ 简历关联与按简历补题**
1. 走流程 ④ 的 1–2 步：HR 生成邀请码 → 候选人激活并绑定该面试
2. 候选人在候选人端录入自己的简历（`POST /candidate/resumes`），再关联到该面试（`PUT /candidate/interviews/{id}/resume`）→ 写 `interview.resume_id`
3. HR 在面试详情页看到简历，点「按简历补题」→ `POST /interviews/{id}/questions/match`
4. 后端取岗位 + 简历 + 题库候选池，调 `ai.match_questions_by_resume`（只挑不生成，返回题目 id 与理由）
5. 追加为新 `interview_question`：`seq` 续接，`source_snapshot='resume_match'`，写 `match_reason`；本场已有的 `question_id` 跳过
6. 前端在题目上展示匹配理由
7. AI 失败 → 本次补题不生效，不动既有题目、不改面试状态（见 7）

**⑦ 面试前准备（HR 侧）**
1. HR 在面试详情页点「生成准备提纲」
2. 后端取岗位（JD + 维度）+ 候选人信息 + 简历（若有）+ 本场题目，调 `ai.generate_interview_prep`
3. 产出的提纲 / 考察重点 / 问题预案整体落库到 `interview_prep`（已存在则覆盖）
4. HR 可编辑并保存（`PUT`），可随时重新生成
5. 面试 `completed` 及之后拒绝生成与编辑（409）

---

## 6. AI Provider 接口契约

`ai` 包对外暴露抽象接口，被 `interview` / `evaluation` / `practice` 调用：

| 接口方法 | 用途 | 调用方 |
|---|---|---|
| `generate_questions(position, dims, bank_questions, count)` | 按 JD + 维度 + 已有题库题补充生成题目 | interview（出题） |
| `evaluate_answer(question, answer)` | 单题打分 + 评语 | evaluation（逐题评分） |
| `evaluate_dimensions(answers, dims)` | 综合多维打分 + 评语 | evaluation（多维评分） |
| `summarize_report(all_scores, dims)` | 汇总总分/结论/优点/待改进 | evaluation（报告） |
| `generate_reference_answer(question)` | 为缺参考答案的题目生成参考答案与解析 | question / practice |
| `grade_practice_answer(question, user_answer)` | 刷题作答判分 + 解析（简答题） | practice |
| `generate_candidate_feedback(report, level)` | 由报告**重写**出面向候选人的脱敏反馈：结论只讲本场表现、不带去留判断（§4.9）；优点 / 待改进的条目与报告逐条一致 | evaluation |
| `match_questions_by_resume(resume_text, position, dims, bank_questions, count)` | 按简历从题库候选中挑选并排序相关题目，返回题目 id 与匹配理由（**只挑不生成**） | interview（简历匹配出题）/ practice（按简历推荐） |
| `generate_interview_prep(position, dims, candidate, resume_text, questions)` | 生成面试提纲、考察重点与问题预案 | interview（准备助手） |

两个实现：

- **真实 Provider**：调用大模型 API
- **Mock Provider**：规则生成确定性结果，用于无 Key 演示与测试

通过配置项选择使用哪个 Provider，代码不写死。刷题判分在 AI 不可用时降级（见 7）。

两条 MVP-3 接口的约束：

- `match_questions_by_resume` **只从传入的题库候选中挑选，不生成新题**。这样保证匹配到的题目都有参考答案与解析，且不引入新题质量风险。调用方（`interview` / `practice`）负责先按岗位或筛选条件取出候选题目池再传入。
- `resume_text` 在两个方法中均为**可选**：未关联简历时 `match_questions_by_resume` 整体不参与（出题少一路、推荐走原筛选逻辑），`generate_interview_prep` 仍可仅凭岗位与候选人信息生成。

`generate_candidate_feedback` 另有一条口径约束（2026-09-21 修正）：**结论是面向本人的重写，不是报告结论的复述**，不得出现「建议进入下一轮 / 不建议继续推进」这类去留判断（§4.9）；`strengths` / `weaknesses` 的条目仍按原样下发，便于 HR 与候选人逐条对照。这条约束与 level 无关 —— 放开总分（`full`）也不放开去留判断。

---

## 7. 错误处理

- **统一响应格式**：`{code, message, detail}`，router 层集中包装
- **分层职责**：
  - router：参数校验（422/400）、鉴权（401/403）
  - service：抛业务异常（资源不存在、状态非法、越权）
  - repository：DB 异常转统一异常
- **AI 调用失败**（超时/限流/Key 无效）：重试 1 次 → 仍失败则评估任务标记失败、状态回退、可重新触发；不阻塞其他功能
  - **回退目标按库里有无旧报告判定**（2026-09-22 修正）：
    - 无报告（首次评估就失败）→ 回退 `completed`
    - 有报告（**重新评估**失败）→ 回退 `evaluated`。旧报告、逐题分、维度分与候选人反馈都仍在库里；
      一律退到 `completed` 会让 `GET /report`、导出与候选人反馈全部 409「评估尚未完成」——
      报告没丢却像丢了，与本条「失败也不损失既有数据」自相矛盾
  - 进程重启遗留的孤儿评估（状态卡在 `evaluating` 且运行注册表为空）按同一规则自愈
- **SSE 断连**：评估任务后台继续，前端重连后可继续拉取进度或查询最终结果
- **候选人侧补充**：
  - 邀请码无效 / 已过期 / 已撤销 → 业务错误，不泄露面试是否存在
  - **凭邀请码激活（`accept`，公开端点）的账号错误**（见 §4.1）：
    - 用户名已被 `hr` / `admin` 占用 → **409**，文案与自助注册一致（不区分占用者角色）
    - 用户名已被 `candidate` 占用但**密码不符** → **401 `UNAUTHORIZED`**，文案与登录失败一致
      （`用户名或密码错误`）。不新增可区分的信号 —— 代价是「该用户名是否存在」对
      **持有有效邀请码的人**可被探测；但邀请码一次性、高熵、私发，探测无法规模化
    - 用户名已被 `candidate` 占用但**该账号已被禁用** → **401**，文案与登录一致
      （`账号已禁用，请联系管理员`）。**不得复用绑定**（2026-09-22 修正）：绑定会消耗掉
      一次性邀请码，而该账号此后 `login` 与 `get_current_user` 都拒绝它 —— 候选人永远
      打不开这场面试，HR 也无法重新发码
  - 重复接受同一邀请 → 业务错误（冲突）。**并发接受也只能产生一条绑定**（2026-09-22 修正）：
    仅靠「先查后写」在并发下会双双通过，候选人列表里同一场面试出现两次。实现上以
    **面试行锁**（`SELECT … FOR UPDATE`）串行化同一场面试的接受，并在锁内以当前读复查
    （快照读会读不到并发事务刚提交的那一行）；判定条件不变
  - 候选人修改已交卷作答 → 业务错误（冲突）
  - 越权访问（非本人面试、非本人练习）→ **403**，沿用现有 `ensure_resource_visible` 的语义：资源存在但无权访问
  - 角色不符（候选人调 HR 接口、HR 调候选人接口）→ 403
  - 刷题 AI 判分失败 → 不阻塞作答：`practice_item` 正常落库但 `is_correct` 为空，标记为未判分，可后续重判
  - 刷题限流（进程内计数，单机规模）→ 超限返回业务错误
- **MVP-3 新增**：
  - 简历不存在 / 非本人所有 → 404 / 403（沿用现有 `ensure_resource_visible` 语义：资源存在但无权访问）
  - 候选人把非本人的简历关联到面试 → 403
  - 候选人在未接受邀请的面试上关联简历 → 403
  - 删除已被面试或练习关联的简历 → 409（冲突）
  - 简历正文超长（> 20000 字符）→ 422
  - **面试未关联简历时触发补题 → 409**（「该面试尚未关联简历」，前端据此隐藏或禁用「按简历补题」按钮）
  - **面试非 `ongoing` 时触发补题 → 409**（`draft` 无追加对象、`completed` 及之后冻结）
  - **补题时 AI 调用失败 → 降级**：本次补题不生效，**不动既有题目、不改面试状态**，返回业务错误由 HR 重试；不阻塞面试的任何其他操作
  - 面试 `completed` 及之后候选人变更简历关联 → 409
  - 候选人刷题按简历推荐时 AI 失败 → 降级为原筛选取题，不阻塞开始练习
  - 面试状态为 `completed` 及之后调用准备助手生成 / 编辑 → 409
  - 准备助手尚未生成时读取 → 404（前端据此显示「生成准备提纲」按钮）
  - DOCX 生成失败 → 业务错误，前端提示可改用「导出 PDF」（浏览器打印路径不依赖后端，仍可用）
- **MVP-4 新增（简历文件上传解析）**：
  - 文件类型不在 `.docx` / `.pdf` 白名单内（含 `.doc` 旧格式、`.txt`、图片等）→ 400，文案点名受支持的两种格式
  - 文件超过 `RESUME_UPLOAD_MAX_BYTES` → 400，文案给出实际上限。**不新增 413**：§7 既有分层只用 400/422 表达「参数不合法」，单独引一个状态码会让前端多出一种没有对应处理的分支
  - 文件损坏 / 加密 / 需要密码 → 400「无法解析该文件」，提示改用粘贴
  - 解析成功但**未提取到文字**（典型是扫描件 PDF、纯图片 DOCX），或提取结果只有空白 → 400，文案点明「这可能是扫描件」并提示改用粘贴
  - 以上四类**都只影响这一次上传**：不创建简历、不落库、不改动任何既有数据

---

## 8. API 概览

统一前缀 `/api`，除登录与候选人自助注册外均需 JWT。

### auth
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/login` | 登录，返回 JWT | 公开 |
| POST | `/auth/register` | 候选人自助注册（仅刷题；配置可关） | 公开 |
| GET | `/auth/me` | 当前用户信息 | 登录 |
| POST | `/users` | 创建用户 | admin |
| GET | `/users` | 用户列表 | admin |
| PATCH | `/users/{id}` | 改角色/禁用 | admin |

### position
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/positions` | 创建岗位 | admin, hr |
| GET | `/positions` | 岗位列表 | admin, hr |
| GET | `/positions/{id}` | 岗位详情 | admin, hr |
| PUT | `/positions/{id}` | 更新岗位 | admin, hr |
| DELETE | `/positions/{id}` | 删除岗位 | admin, hr |

### question
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/questions` | 创建题目 | admin, hr |
| GET | `/questions` | 题目列表（按岗位/分类/维度/难度/题型筛选） | admin, hr |
| GET | `/questions/{id}` | 题目详情 | admin, hr |
| PUT | `/questions/{id}` | 更新题目（含题型、参考答案、解析） | admin, hr |
| DELETE | `/questions/{id}` | 删除题目 | admin, hr |
| POST | `/questions/{id}/reference-answer` | 调 AI 生成参考答案与解析并落库（补齐 §4.3「可由 AI 生成后由 HR 确认」） | admin, hr |

### interview
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/interviews` | 创建面试（含同步出题；**不接受 `resume_id`**，简历由候选人事后关联，见 4.13） | admin, hr |
| GET | `/interviews` | 面试列表（按用户隔离） | admin, hr |
| GET | `/interviews/{id}` | 面试详情（含题目+回答） | admin, hr |
| PATCH | `/interviews/{id}` | 更新候选人信息（**不含状态**，状态走动词端点） | admin, hr |
| POST | `/interviews/{id}/answers` | 保存/更新某题回答（含覆盖候选人作答） | admin, hr |
| POST | `/interviews/{id}/complete` | 标记完成 | admin, hr |
| POST | `/interviews/{id}/rollback` | 回退到进行中（补齐 §5.1 的 `completed → ongoing` 迁移） | admin, hr |
| POST | `/interviews/{id}/evaluate` | 触发评估，返回 SSE 地址 | admin, hr |
| GET | `/interviews/{id}/evaluation/stream` | SSE 流式评估 | admin, hr |
| POST | `/interviews/{id}/invitations` | 生成作答邀请码 | admin, hr |
| GET | `/interviews/{id}/invitations` | 邀请列表与状态 | admin, hr |
| DELETE | `/interviews/{id}/invitations/{inv_id}` | 撤销邀请 | admin, hr |
| POST | `/interviews/{id}/prep` | 生成 / 重新生成面试前准备提纲（整体覆盖） | admin, hr |
| GET | `/interviews/{id}/prep` | 查看准备提纲（未生成则 404） | admin, hr |
| PUT | `/interviews/{id}/prep` | 编辑准备提纲（整体覆盖 outline / focus_points / question_plan） | admin, hr |
| GET | `/interviews/{id}/resume` | 读取该面试关联的候选人简历（未关联则 404） | admin, hr |
| POST | `/interviews/{id}/questions/match` | 按简历从题库补题（追加、幂等；前置条件见 4.14） | admin, hr |

### evaluation
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/interviews/{id}/report` | 获取最终报告（逐题+多维+汇总） | admin, hr |
| GET | `/interviews/{id}/report/export` | 导出报告为 DOCX（`?format=docx`），返回文件流 | admin, hr |

### candidate（候选人侧）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/candidate/positions` | 刷题岗位筛选项（**有题目的岗位**：id / 名称 / 题量；不含 JD） |
| POST | `/candidate/invitations/{code}/accept` | 凭邀请码激活并绑定面试 |
| GET | `/candidate/interviews` | 我参与的面试列表（**含每场已关联的 `resume_id`**，未关联为 `null`） |
| GET | `/candidate/interviews/{id}` | 面试详情（仅题目与我自己的作答，**同样含 `resume_id`**） |
| POST | `/candidate/interviews/{id}/answers` | 保存/更新我的作答（交卷后拒绝） |
| POST | `/candidate/interviews/{id}/submit` | 交卷（幂等） |
| GET | `/candidate/interviews/{id}/feedback` | 查看面向候选人的脱敏反馈 |
| PUT | `/candidate/interviews/{id}/resume` | 为本人已接受的面试关联 / 解除关联我的一份简历（`{resume_id}`，传 `null` 解除） |
| POST | `/candidate/resumes` | 新建我的简历（正文为纯文本） |
| GET | `/candidate/resumes` | 我的简历列表 |
| GET | `/candidate/resumes/{id}` | 简历详情（仅本人） |
| PUT | `/candidate/resumes/{id}` | 更新我的简历 |
| DELETE | `/candidate/resumes/{id}` | 删除我的简历（被面试或练习关联则 409） |
| POST | `/candidate/resumes/parse` | 上传 DOCX / PDF 解析为纯文本（**不落库、不落盘**，只返回文字，见 4.10 / 5.2） |

### practice（候选人侧）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/practice/questions` | 刷题取题（按岗位/分类/难度/题型筛选） |
| GET | `/practice/sessions` | 我的练习会话列表（含进行中，用于继续未完成的练习） |
| POST | `/practice/sessions` | 开始一次练习（请求体可选 `resume_id` 触发按简历推荐取题） |
| GET | `/practice/sessions/{id}` | 练习详情与进度 |
| POST | `/practice/sessions/{id}/items` | 提交某题作答 → 即时判分 + 解析 |
| POST | `/practice/items/{item_id}/rescore` | 对**未判分**的题重新判分（补齐 §7「可后续重判」） |
| POST | `/practice/sessions/{id}/finish` | 结束练习，出小结 |
| GET | `/practice/wrong-book` | 错题本（由 practice_item 派生） |
| GET | `/practice/stats` | 我的练习统计（题量/正确率/按维度） |

> candidate 与 practice 两组接口权限均为 `candidate`，数据隔离为「仅本人数据（含本人简历）+ 本人已接受的邀请所对应面试」。
>
> **唯一例外是 `accept`**：`POST /candidate/invitations/{code}/accept` 是**公开端点**，
> 不要求 JWT —— 拿码的人可能还没有账号（见 §4.1）。它是全项目第三个公开端点
> （另外两个是 `/auth/login` 与 `/auth/register`）。
>
> **`resume` 在 API 层只有候选人侧一组 CRUD**（`/candidate/resumes`）。HR 侧不提供简历 CRUD：HR 通过 `GET /interviews/{id}/resume` 只读候选人关联的简历，读取权限的判据是「该简历关联到自己名下的某场面试」，复用 4.1 既有的邀请链校验路径，而非 `created_by`。

---

## 9. 非功能需求

- **数据隔离（三端）**：admin 见全部；普通 HR 仅见自己创建的数据，外加**与自己名下某场面试关联的候选人简历**（只读）；candidate 仅见自己的练习数据、自己的简历，以及自己已接受的邀请所对应面试的题目与自己的作答
- **权限守卫**：HR 侧全部接口显式校验角色（admin/hr），候选人侧接口校验 candidate；权限工具支持多角色判定。这是本期新增强制项，不是可选项
- **候选人可见性**：反馈默认脱敏（仅综合结论/优点/待改进）；逐题分、维度分、雷达图默认不下发，由配置项 `CANDIDATE_FEEDBACK_LEVEL` 控制
- **单机约束适配**：
  - 前端同一 origin 下两端登录态**按端分 key 存储**（`hr.*` / `candidate.*`），保证单浏览器可同时保持 HR 与候选人登录
  - 限流类能力用进程内计数实现，不引入 Redis 等中间件
- **安全**：密码哈希存储（bcrypt/argon2）；JWT 过期与刷新；参数校验防注入；邀请码具备足够熵、不可枚举、有效期默认 7 天、一次性接受、可撤销
- **可测试性**：三层可独立测试；AI Provider 可 Mock（刷题判分同样可在无 Key 下确定性复现）
- **可维护性**：模块边界清晰，依赖单向，每个 package 可独立理解与修改；`practice` 不依赖 `interview`，刷题与真实面试解耦
- **简历的跨端流不破坏分层（MVP-3）**：`resume` 由候选人单侧写入、不依赖任何业务模块，`interview` 与 `practice` 各自单向依赖它；**不得让 `resume` 反向引用面试或练习**，否则会把 `practice ↔ interview` 的循环依赖引进来。HR 读取候选人简历的判据（邀请链）由 `interview` 实现，`resume` 只提供纯数据读取，不感知调用方身份
- **新增依赖受控（MVP-3 / MVP-4）**：MVP-3 仅新增 `python-docx`；MVP-4 再新增 `pypdf` 与 `python-multipart`（见 §2）。PDF 导出仍以「浏览器打印」实现，从而**不引入任何 PDF 生成库**。新增任何依赖都需先更新本节与 §2
- **上传解析的安全边界（MVP-4）**：
  - 文件**在内存中处理、不落盘**（与 DOCX 报告导出同一取舍），因此不存在「上传目录被当静态资源对外暴露」这一类风险
  - 体积上限既是体验护栏也是资源护栏：防一次请求把内存撑爆
  - **扩展名白名单之外还要按文件头魔数复核**（PDF 以 `%PDF` 开头、DOCX 是 ZIP 容器以 `PK` 开头），避免改名绕过
  - 解析库须以**安全配置**打开文件：关闭 XML 外部实体解析与 DTD（防 XXE），并对解压后的展开体积设限（防 ZIP bomb，DOCX 本质是 ZIP）
  - 解析失败的文案**不回显文件内部结构、路径或原始异常**，避免把内部信息透给上传方

---

## 10. 测试策略

| 层 | 内容 |
|---|---|
| repository | 连测试库测 CRUD |
| service | 注入 mock repository / mock Provider，测业务逻辑与状态机 |
| practice service | 注入 mock repository / mock Provider，测判分分支（单选规则判分、简答 AI 判分、AI 失败降级）与错题本 / 统计的派生 |
| router | TestClient 测端点（含鉴权、错误码、数据隔离） |
| 权限 | 候选人 token 调 HR 接口 → 403；HR 调候选人接口 → 403；候选人 A 访问候选人 B 的面试 / 练习 → 403；访问未被邀请或未接受的面试 → 403 |
| 流程 | 邀请生命周期（pending → accepted / revoked / expired）、交卷锁定与 HR 覆盖、候选人重复交卷幂等 |
| 集成 | 出题组装、状态机流转、评估落库 三条主流程；在线答题、刷题练习 两条新增主流程；简历匹配出题、面试前准备 两条 MVP-3 主流程 |
| resume（MVP-3） | 候选人 `created_by` 隔离（A 看不到 B 的简历）；HR 只能经 `GET /interviews/{id}/resume` 读到关联到自己名下某场的简历，读他人面试的简历 → 403；删除被关联的简历 → 409；正文超长 → 422 |
| 简历上传解析（MVP-4） | 类型白名单（`.docx` / `.pdf` 通过；`.doc` / `.txt` / 图片 → 400）；超 `RESUME_UPLOAD_MAX_BYTES` → 400；损坏 / 加密文件 → 400；扫描件 PDF（无文字层）→ 400；改名伪装的非 PDF / DOCX → 400（魔数复核）；正常 DOCX / PDF → 返回纯文本且**不产生任何简历记录**（断言库内简历数不变）；DOCX **表格内文字也被提取**；HR token 调该端点 → 403 |
| 简历关联（MVP-3） | 候选人关联非本人简历 → 403；在未接受邀请的面试上关联 → 403；面试 `completed` 后变更 → 409；传 `null` 解除关联 |
| 简历补题（MVP-3） | 未关联简历 → 409；非 `ongoing` → 409；正常补题 → 追加且 `source_snapshot='resume_match'`、`match_reason` 非空、`seq` 续接；重复调用 → 已有 `question_id` 跳过（幂等）；AI 失败 → 不动既有题目、不改状态；候选人换简历后再次补题 → 只追加新增的题 |
| 准备助手（MVP-3） | 生成 / 重新生成覆盖 / 编辑；`completed` 状态生成或编辑 → 409；未生成时读取 → 404；`draft` 且本场无题目时仍可生成 |
| 导出（MVP-3） | DOCX 端点的鉴权与数据隔离、生成失败返回业务错误；PDF 为前端浏览器行为，后端无对应端点（不在后端测试范围） |
| 候选人反馈（MVP-2） | 白名单序列化：响应里**结构上**不含逐题分 / 维度分 / 雷达图；`summary` 档 `overall_score` 为 null、`full` 档为 0–10；**结论不含「建议进入下一轮 / 不建议继续推进」这类去留判断**，且 `strengths` / `weaknesses` 条目与报告逐条一致；未评估 → 409 |

---

## 11. 里程碑与分期

### MVP-1 HR / 面试官侧（已完成）
- auth / position / question / interview / evaluation / ai 六模块
- 手动录入回答 + 同步出题 + 流式评估
- 后端契约已由 461 条用例验证（见 [API 接口测试报告](../../tests/2026-09-17-API接口测试报告.md)）

### MVP-2 面试者（候选人）侧（2026-09-20 追加，本文档范围）
- `auth`：新增 candidate 角色、候选人注册、权限守卫收紧（多角色判定）
- `interview`：作答邀请（生成/接受/撤销/过期）、候选人在线作答通道与交卷锁定
- `question`：题型、选项、参考答案、解析字段
- `evaluation`：面向候选人的脱敏反馈视图
- `practice`：新模块 —— 练习会话、逐题判分与解析、错题本、练习统计
- 前端：同一 Vite 工程内新增候选人路由与页面；登录态按端分 key

### MVP-3 简历驱动与报告导出（2026-09-20 追加，本文档范围）
- `resume`：新模块 —— 候选人侧纯文本 CRUD；HR 侧经面试只读（判据复用邀请链）
- `interview`：候选人关联简历到面试（4.13）；HR 按简历补题（4.14，写 `source_snapshot='resume_match'` 与 `match_reason`）；面试前准备助手（生成 / 查看 / 编辑，落库 `interview_prep`）
- `practice`：开始练习时可按简历推荐题目
- `evaluation`：报告 DOCX 导出（`python-docx`，唯一新增依赖；安装需走镜像，见 §2）
- 前端：候选人侧简历管理页、HR 侧面试详情内的简历只读区与「按简历补题」按钮、报告与准备助手的打印导出样式（`@media print`）
- ⚠️ **迁移说明**：本批次新增 / 变更的表结构（`resume`、`interview_prep`、`interview.resume_id`、`interview_question.match_reason`、`practice_session.resume_id`）与 MVP-2 一致，**只改模型、不写迁移**，待统一收口

### MVP-4 简历文件上传解析（2026-09-22 追加，本文档范围）
- `resume`：新增 `POST /candidate/resumes/parse` —— 上传 DOCX / PDF 解析为纯文本，**不落库、不落盘**（4.10、5.2）
- `core`：新增配置项 `RESUME_UPLOAD_MAX_BYTES`（默认 5 MB）
- 新增依赖 `pypdf` 与 `python-multipart`（安装需走镜像，见 §2）；DOCX 一路**复用既有 `python-docx`**
- 前端：候选人「新建 / 编辑简历」弹窗内新增「上传文件」入口，解析结果回填正文框、由候选人确认后再保存
- **不改任何表结构**：`resume` 表字段与 `script.sql` 均不变，无迁移动作
- 本批次把原列在 V1.1 的「简历文件解析与上传」**收窄实现**后提前落地：只做「取文字」，不做「存原件」

### V1.1（规划，不在本次范围）
- 报告分享
- 语音 / 视频面试、录音转写
- **保留简历原文件与「回看原件」**（MVP-4 只解析取文字，不存原文件，见 4.10）
- 多候选人横向对比
- 后端 PDF 生成（脱离浏览器的批量 / 后台导出）
- 候选人端导出自己的脱敏反馈
