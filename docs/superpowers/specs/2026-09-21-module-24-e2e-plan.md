# e2e 端到端验证与收尾 执行计划书（MVP-3 简历驱动与报告导出）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：e2e —— MVP-3 的端到端验证、需求追溯、**DDL 统一收口清单**、遗留问题交接
**所属**：跨模块（无独立 package）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.7、§4.10、§4.11、§4.12、§4.13、§4.14、§5.2、§5.3 ⑥⑦、§7、§8、§9、§11
**前置依赖**：[module-17 resume](./2026-09-21-module-17-resume-plan.md)、[module-18 ai](./2026-09-21-module-18-ai-plan.md)、[module-19 interview](./2026-09-21-module-19-interview-plan.md)、[module-20 practice](./2026-09-21-module-20-practice-plan.md)、[module-21 evaluation 导出](./2026-09-21-module-21-evaluation-export-plan.md)、[module-22 候选人前端](./2026-09-21-module-22-candidate-frontend-plan.md)、[module-23 HR 前端](./2026-09-21-module-23-hr-frontend-plan.md)
**前序收尾**：[module-08 e2e（MVP-1/2）](./2026-09-15-module-08-e2e-plan.md)——**本模块是它的续篇，不重复其内容**

---

## Global Constraints（全局约束，摘自 PRD）

- **只验证与收尾，不就地改代码**：需要改实现时**回到对应模块计划书**（module-08 §1.2 的既有约定）
- 验证必须覆盖 PRD §5.3 的**全部七条核心流程**（前五条由 module-08 覆盖，⑥⑦ 由本模块覆盖）
- **三条导出/交付路径必须区分清楚**：DOCX（后端生成）、PDF（浏览器打印）、候选人脱敏反馈（**不导出**）
- 前端仍**不得新增依赖**；后端新增依赖**仅 `python-docx`**（§2）
- **不写 alembic 迁移**：DDL 由你统一收口（§11）——**本模块的职责是把清单备齐**（§7）
- **无数据库变更、无新增错误码**（module-08 §6 的八个错误码不变）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | 出处 |
|---|---|---|
| 端到端验证 | PRD §5.3 流程 ⑥⑦ 与报告导出的完整走通 | §4 |
| 异常路径验证 | 补题失败、提纲未生成、导出失败等降级与报错 | §4.4 |
| 非功能验证 | 数据隔离（HR 读候选人简历）、架构约束、新增依赖、打印 | §5 |
| 需求追溯 | MVP-3 的每条 PRD 需求 → 落地模块 | §6 |
| **DDL 统一收口清单** | **MVP-2 + MVP-3 全部待建表/待改列，含一处 `MODIFY COLUMN`** | §7 |
| 遗留问题交接 | 已知局限与待你拍板项 | §8 |
| README 增量 | 镜像安装、新配置项、演示步骤 | §3 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **重复 module-08 的验证内容** | 前五条流程、MVP-1/2 的非功能项已在 module-08。本模块**只写增量** |
| **就地修实现** | 发现问题回对应模块计划书改（module-08 §1.2 既有约定） |
| **写 alembic 迁移 / 同步 `script.sql`** | DDL 由你统一收口（§11）。本模块**产出清单**，不产出迁移 |
| **生产部署与运维** | 不在 PRD 范围 |
| **性能压测** | PRD §9 未提出性能指标 |
| **V1.1 功能**（报告分享、语音视频面试、简历文件解析、多候选人对比、后端 PDF、候选人导出反馈） | PRD §11 明确分期 |
| **补做候选人前端**（module-15） | 它是**独立前置模块**。本模块只**如实记录**它未执行（§8） |

---

## 2. 交付物清单

| # | 交付物 | 形式 | 章节 |
|---|---|---|---|
| 1 | README 增量 | 文档修改 | §3 |
| 2 | MVP-3 端到端验证记录 | 执行记录 | §4 |
| 3 | 非功能验证记录 | 执行记录 | §5 |
| 4 | MVP-3 需求追溯矩阵 | 文档 | §6 |
| 5 | **DDL 统一收口清单** | 文档（**给你执行建表用**） | §7 |
| 6 | 遗留问题清单 | 文档 | §8 |
| 7 | **对 module-08 §5.4 的陈旧表述修正** | 文档修改 | §5.2 |

---

## 3. README 与启动文档的增量

在 module-08 §3 的既有 README 内容清单上**追加**：

### 3.1 新增依赖与镜像（**必写**）

| 内容 | 说明 |
|---|---|
| `python-docx` 是 MVP-3 唯一新增依赖 | 用于后端生成报告 DOCX |
| **安装必须走镜像** | `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt` |
| **直连的后果（写清具体症状）** | 在 `files.pythonhosted.org` 上超时（5 次重试、0 字节）；索引取不全时会把 `python-docx` 解析到 2021 年的 `0.8.11` |

> **这不是「顺带一提」的环境说明**：它是**会让下一个人卡住的坑**，而且症状（超时 + 版本诡异）与「网络不好」难以区分。已实测（PRD §2）。

### 3.2 新增配置项

| 配置键 | 默认 | 说明 |
|---|---|---|
| `resume_match_count` | `3` | 按简历补题的默认追加题数（PRD §4.14 的「默认 3」） |

> 其余 MVP-3 旋钮（池因子 4、池上限 100、准备助手预案上限 4）是**实现内部常量，不进配置**（module-20 §5.2、module-18 §4.2 已说明理由）。

### 3.3 MVP-3 演示路径（**按实际可演示的顺序写**）

```
前置：HR 与候选人各一个账号（候选人可自助注册或凭邀请激活）
      ⚠️ 候选人前端目前不存在的部分见 §8 第 1 条

① 简历录入        [候选人侧 UI]
② 关联到面试      [候选人侧 UI]  → PUT /candidate/interviews/{id}/resume
③ HR 读简历       [HR 侧 UI]     → 面试详情页「候选人简历」面板
④ 按简历补题      [HR 侧 UI]     → 按钮 → 提示「本次新增 N 题，本场共 M 题」
⑤ 面试准备        [HR 侧 UI]     → #/interviews/{id}/prep 生成 / 编辑
⑥ 评估            [HR 侧 UI]     → 既有 SSE 流式评估
⑦ 导出 DOCX       [HR 侧 UI]     → 报告页下载 .docx
⑧ 导出 PDF        [HR 侧 UI]     → 报告页 / 准备助手页 window.print()
```

> **①②⑤ 若无候选人前端则只能走接口**（`curl` / API 文档）。README 必须**如实写明这一点**，不能让读文档的人以为是环境搭错了。

---

## 4. 端到端验证（PRD §5.3 新增流程）

### 4.1 流程⑥ 简历关联与按简历补题（PRD §5.3 ⑥）

| 步 | 动作 | 预期 |
|---|---|---|
| 1 | 候选人建简历 | 201；`GET /candidate/resumes` 可见 |
| 2 | 候选人把简历关联到已接受的面试 | 200；`interview.resume_id` 写入 |
| 3 | 候选人重复关联另一份 | 200；`resume_id` 被替换 |
| 4 | HR 读面试详情 | `resume_id` 非空 |
| 5 | HR 读 `GET /interviews/{id}/resume` | 200；含 `title` / `content` / `updated_at`；**不含 `created_by`** |
| 6 | HR 触发补题 | 200；`added_count > 0`；`total_questions` = 原题数 + 新增数 |
| 7 | HR 读面试详情 | 新增题的 `source === 'resume_match'`、`match_reason` 非空；**既有题目三个快照字段与 `match_reason`（应为 null）全未变** |
| 8 | 新增题的 `seq` | 续接既有最大值，**无重号无空洞** |
| 9 | HR 再次触发补题 | 200；**新增的 `question_id` 与上一次无交集**；`total_questions` 继续递增 |
| 10 | 反复触发至题库耗尽 | 409「题库中没有可补充的题目」 |
| 11 | 候选人在面试 `completed` 后尝试换关联 | 409 |
| 12 | HR 在面试 `completed` 后尝试补题 | 409 |
| 13 | 撤销该面试的全部邀请后再读简历 | 403（HR 侧不受影响）/ 候选人侧 403 |

> **第 9 与第 11 条是流程⑥ 的关键**：前者证明「幂等的准确含义是不产生重复题目、但会累加」（module-19 §5.3 的核心提醒），后者证明「白名单式状态判定覆盖了 `completed`/`evaluating`/`evaluated`」。

### 4.2 流程⑦ 面试前准备（PRD §5.3 ⑦）

| 步 | 动作 | 预期 |
|---|---|---|
| 1 | `draft` 面试（本场无题目）生成提纲 | 200；三部分非空 |
| 2 | 有关联简历时生成 | 200；`focus_points` 含「简历核对」条目 |
| 3 | 无关联简历时生成 | 200；**不含**「简历核对」条目 |
| 4 | 编辑三部分并保存 | 200；`edited_at` 非空、`generated_at` **不变** |
| 5 | 重新生成 | 200；**`interview_prep` 仍只有一行**；`edited_at` **回到 null** |
| 6 | 只提交两部分（缺 `question_plan`） | 400 |
| 7 | 未生成时读取 | 404 |
| 8 | 未生成时编辑 | 404，**且未创建行** |
| 9 | `completed` / `evaluating` / `evaluated` 时生成或编辑 | 409 |
| 10 | 切到会抛错的 Provider 后生成（已有提纲） | 502；**旧提纲三部分与 `generated_at` 不变** |
| 11 | 首次生成时 AI 失败 | 502；**`interview_prep` 无新行** |

> **第 5、10 两条是流程⑦ 的关键**：前者证明「整体覆盖 + 编辑标记同步清除」，后者证明「AI 调用先于写入，因此失败时数据库零改动」。

### 4.3 报告导出（PRD §4.12）

| 步 | 动作 | 预期 |
|---|---|---|
| 1 | 未评估完成时 `GET /report/export` | 409「评估尚未完成」 |
| 2 | 评估完成后导出 | 200；`content-type` 为 DOCX MIME |
| 3 | 检查 `Content-Disposition` | 含 `attachment`；含 ASCII 回退名；含 `filename*=UTF-8''` |
| 4 | 用 `unquote` 解码 `filename*` | 得到含岗位名与候选人姓名的中文名 |
| 5 | **打开下载的 DOCX** | 八个区块齐备；**中文正常**；**无图片**；**逐题回答不截断** |
| 6 | 把候选人姓名改成含 `"` 与换行的值后导出 | 头部无 `"` / CR / LF；文件名可解码 |
| 7 | 导出前后查表 | `report` / `question_score` 等**行数不变**（不落库导出记录） |
| 8 | 候选人 token 调导出端点 | 403 |
| 9 | 他人 HR 的面试 | 403 |
| 10 | 前端「导出 DOCX」 | 下载到中文名的 `.docx`（**不是未解码的百分号串**） |
| 11 | 前端「导出 PDF」（报告页） | 另存 PDF：**颜色仍在**、无侧边栏/顶栏/按钮、雷达图未断页 |
| 12 | 前端「导出 PDF」（准备助手页） | 同上；三块内容完整 |
| 13 | 后端停掉后点「导出 PDF」 | **仍可打印**（不依赖后端） |
| 14 | 后端停掉后点「导出 DOCX」 | 提示「可改用导出 PDF」 |

> **第 5 与第 11 条必须实际执行、不得只看屏幕**：DOCX 要看**打开后的文档**（中文是否退化、有无图片）；PDF 要看**另存后的文件**（`print-color-adjust` 缺失的症状恰恰是屏幕正常、PDF 掉色）。

### 4.4 异常路径（PRD §7）

| 场景 | 预期 |
|---|---|
| 补题时 AI 失败 | **502**；本场题目数与内容**完全不变** |
| 补题时 AI 返回空 | **200**，`added_count == 0`，题目数不变 |
| 补题时 AI 返回池外 id | 该条被丢弃；其余正常入库（`ai` 层与本模块各挡一次） |
| 补题时未关联简历 | 409 |
| 刷题按简历推荐 AI 失败 | **201 正常建会话**；`resume_match_applied === false`；题目与「不传 `resume_id`」**逐条相同** |
| 刷题关联非本人简历 | 403 |
| 简历删除（被面试关联） | 409，**且行仍在** |
| 简历删除（被练习关联） | 409 |
| 简历正文超长 | **422**（不是 400） |
| 删除简历后重试同一请求 | 能正常执行（`IntegrityError` 已 rollback，事务未被污染） |
| 生成提纲 AI 失败 | 502；旧值保留 |
| 准备助手未生成时读取 | 404（**前端应显示空态而非错误**） |
| 导出 DOCX 失败 | 前端提示可改用 PDF |

> **「降级」与「失败」必须能被区分**（本批次反复出现的一条原则）：
> - 补题 AI 失败 → **502**（用户要知道没生效）
> - 补题 AI 返回空 → **200 + `added_count=0`**（「没有」是正当结论）
> - 刷题推荐失败 → **201 + `resume_match_applied=false`**（不阻塞开练，但要留痕）
> - 生成提纲失败 → **502 且旧值不变**（「重新生成失败」应表现为「什么都没发生」）

---

## 5. 非功能验证（PRD §9）

### 5.1 数据隔离（新增项的验证）

| # | 验证 | 预期 |
|---|---|---|
| 1 | 候选人 A 读候选人 B 的简历 | 403 |
| 2 | 候选人 A 把 B 的简历关联到自己的面试 | 403，且 `resume_id` 未变 |
| 3 | HR 读**自己**面试关联的简历 | 200 |
| 4 | HR 读**他人**面试关联的简历 | 403 |
| 5 | HR 直接读任意 `resume_id`（不经面试） | **不存在这样的端点**（HR 侧无简历 CRUD，PRD §4.10） |
| 6 | 未关联简历时 HR 读 | 404（**不是 403**） |
| 7 | 候选人读自己被接受面试的详情 | `match_reason` **键不存在**（PRD §4.6） |
| 8 | 补题后候选人再读面试详情 | 新增题**仍不含** `match_reason` |
| 9 | 候选人读他人的练习会话 / 统计 / 错题本 | 403（既有，回归） |
| 10 | hr / admin 调候选人侧任一端点 | 403（既有，回归） |

> **第 3–6 条验证的是本批次最容易做错的隔离**：HR 能读候选人简历，**判据是「面试属于我」而非「简历属于我」**（module-19 §5.2）。若实现错了这一处，症状是「HR 永远读不到」或「HR 能读到任意简历」，前者立刻可见、后者是严重越权。

### 5.2 架构约束清单（**含对 module-08 §5.4 的修正**）

| # | 验证 | 预期 |
|---|---|---|
| 1 | `backend/app/` 的独立 package 数 | **九个**：`core` / `auth` / `position` / `question` / `resume` / `interview` / `evaluation` / `ai` / `practice` |
| 2 | 每个业务模块的分层文件 | 均有 `models.py` / `schemas.py` / `repository.py` / `service.py` / `router.py`（`ai` 除外：无 router/models） |
| 3 | 依赖方向 | 无反向依赖。**特别确认 `resume` 不依赖任何业务模块** |
| 4 | `test_architecture.py` | `test_nine_modules_exist` 通过；`FORBIDDEN_DEPENDENCIES` 含 `resume` 一项 |
| 5 | `resume` 的跨端供给 | `interview` / `practice` 顶层只 import `resume.service`，**不 import `resume.repository`**（有静态断言） |
| 6 | `practice` 未新增 position 依赖 | 有静态断言（module-20 §7.5） |
| 7 | `ai` 不依赖业务模块 | `test_ai_depends_on_no_business_module` 覆盖**改动后的三个文件**且通过 |
| 8 | `AIProvider` 抽象方法数 | **九个**（`test_mock_provider_implements_all_nine_methods` 断言 `== 9`） |

> ⚠️ **必须修正 module-08 §5.4 第 1 条**：现写「**七个独立 package**」（那是 MVP-1 的 6 + core）。**practice（MVP-2）当时未同步更新**，现在 resume（MVP-3）又加一个。正确值是**九个**。
>
> **这是「文档陈旧」的典型样本**：module-08 的这条清单是**人工维护的硬编码文本**，加模块时没人会想起它。**本模块的职责之一就是把它改对**，并在 README/计划书里保留「加 package 时必须同步此处」的提醒。

### 5.3 新增依赖与镜像（PRD §2）

| # | 验证 | 预期 |
|---|---|---|
| 1 | `requirements.txt` | 含 `python-docx>=1.1`，且**仅此一项新增** |
| 2 | 镜像安装 | `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple python-docx` 成功 |
| 3 | 实际装入版本 | `python-docx 1.2.0` + `lxml 6.1.3`（cp313 win_amd64 二进制 wheel） |
| 4 | `import docx` | 成功 |
| 5 | 前端依赖 | `package.json` **零新增**；无 PDF / DOCX 前端库 |
| 6 | 无 PDF 生成库 | 后端 dependencies 中**无** reportlab / weasyprint / fpdf 等 |
| 7 | README | 已写明镜像安装命令与直连的两个具体症状（§3.1） |

### 5.4 打印导出

| # | 验证 | 预期 |
|---|---|---|
| 1 | 报告页打印 | 颜色保留；无导航 / 按钮 / toast；雷达图未断页 |
| 2 | 准备助手页打印 | 三块内容完整；无操作控件 |
| 3 | `@media print` 不影响屏幕 | 正常浏览布局与改动前一致 |
| 4 | 雷达图的打印方式 | **已核实（2026-09-21）：`components/radar.js` 是 Canvas 实现**（`getContext('2d')` + DPR 缩放）。结论：能打印出图、**颜色不丢**（像素不受 `print-color-adjust` 影响）、尺寸不会被拉伸（CSS 尺寸显式钉死）；代价是**位图略糊**（dpr=1）。详见 module-23 §5.4 |
| 5 | `print-color-adjust` 的实际作用范围 | 保护的是**分数色块 / 标签底色 / 面板底色等 CSS 背景**，**不是**雷达图。走查时须确认这些元素在另存的 PDF 里**仍有色** |

> ⚠️ **第 4 条已核实并给出结论**（不再待验证）：`radar.js` 是 canvas，**能打印、颜色不丢**。
>
> **由此得出一条反直觉的推论，走查时必须按它调整注意力**：雷达图**不是**颜色丢失的风险点，**真正的风险点是那些 CSS 背景**（分数色块、来源 / 维度标签底色、优劣势列表着色）。**别因为「雷达图能打印」就跳过对 `print-color-adjust` 的核查**。

---

## 6. 需求追溯矩阵（MVP-3）

### 6.1 功能需求（PRD §4）

| PRD 需求 | 章节 | 落地模块 | 具体位置 |
|---|---|---|---|
| 候选人录入简历（纯文本） | §4.10 | resume + 前端候选人 | resume §4.1、candidate-frontend §5.1 |
| 简历字段：标题 / 正文 / 姓名 / 联系方式 | §4.10 | resume | resume §3.1 |
| HR **不提供**简历 CRUD，只读 | §4.10 | resume + interview | resume §1.2、interview §5.2 |
| 简历正文上限 20000 字符 | §4.10 | resume + 前端候选人 | resume §3.3、§5.1；candidate-frontend §5.1 |
| 删除被关联的简历 → 409 | §4.10 | resume | resume §5.4 |
| 候选人**关联简历到面试** | §4.13 | interview + 前端候选人 | interview §5.1、candidate-frontend §5.2 |
| 关联仅限本人简历 / 本人已接受面试 | §4.13 | interview | interview §5.1、§7.1 |
| 关联仅 `ongoing` 可变更 | §4.13 | interview | interview §5.1、§7.1 |
| HR **按简历补题** | §4.14 | interview + ai + question | interview §5.3、ai §4.1 |
| 补题写 `source_snapshot='resume_match'` 与 `match_reason` | §4.4、§5.2 | interview | interview §3.2 |
| 补题**只追加、不改动既有题目** | §4.14 | interview | interview §5.3、§7.3 |
| 补题**不产生重复题目** | §4.14 | interview | interview §5.3、§7.3 |
| 补题前置：`ongoing` 且已关联简历 → 否则 409 | §4.14 | interview | interview §5.3、§7.3 |
| 补题**无撤销接口** | §4.14 | interview | interview §1.2 |
| 匹配**只挑不生成** | §6 | ai | ai §3.3、§5.5 |
| 面试前准备助手（提纲 / 重点 / 预案） | §4.11 | interview + ai | interview §5.4、ai §4.2 |
| 准备助手**落库、可编辑、整体覆盖** | §4.11、§5.2 | interview | interview §3.3、§5.5 |
| 准备助手仅 `draft`/`ongoing` 可生成编辑 | §4.11 | interview | interview §5.4、§7.4 |
| 准备助手**不进入状态机** | §5.1 | interview | interview §3.3、§1.2 |
| 准备助手输入可无简历 / 无题目 | §4.11 | interview + ai | interview §5.4、ai §4.2 |
| 刷题**按简历推荐** | §4.7 | practice + ai | practice §5.2 |
| 刷题推荐 AI 失败**降级不阻塞** | §7 | practice | practice §5.2、§7.3 |
| 报告导出 **DOCX** | §4.12 | evaluation | evaluation-export §3.1 |
| 报告导出 **PDF（浏览器打印）** | §4.12 | 前端 HR | hr-frontend §3.3、§5.3 |
| 导出**仅 HR 侧**，不含候选人反馈 | §4.12 | evaluation + 前端 HR | evaluation-export §1.2 |
| DOCX **不含雷达图** | §4.12 | evaluation | evaluation-export §3.1 |
| **不落库导出记录** | §4.12 | evaluation | evaluation-export §5.1、§7.2 |

### 6.2 AI 契约（PRD §6）

| 接口 | 落地 | 位置 |
|---|---|---|
| `match_questions_by_resume` | ai | ai §3.2、§4.1、§5.2 |
| `generate_interview_prep` | ai | ai §3.2、§4.2、§5.2 |
| 两者 Mock 确定性 | ai | ai §7.1、§7.2 |
| 两者真实实现容错 | ai | ai §5.3、§7.3 |

### 6.3 数据模型（PRD §5.2）

| 实体 | 落地模块 | 位置 |
|---|---|---|
| `resume`（新） | resume | resume §3.1 |
| `interview.resume_id`（改） | interview | interview §3.1 |
| `interview_question.match_reason`（改） | interview | interview §3.2 |
| `interview_question.source_snapshot` **枚举加值** | interview | interview §3.2 |
| `interview_prep`（新） | interview | interview §3.3 |
| `practice_session.resume_id` / `.resume_match_applied`（改） | practice | practice §3.1 |

### 6.4 API 清单（PRD §8）

| 端点 | 落地 | 位置 |
|---|---|---|
| `POST /candidate/resumes` | resume | resume §4.1 |
| `GET /candidate/resumes` | resume | resume §4.1 |
| `GET /candidate/resumes/{id}` | resume | resume §4.1 |
| `PUT /candidate/resumes/{id}` | resume | resume §4.1、§4.2 |
| `DELETE /candidate/resumes/{id}` | resume | resume §4.1、§5.4 |
| `PUT /candidate/interviews/{id}/resume` | interview | interview §4.1、§5.1 |
| `GET /interviews/{id}/resume` | interview | interview §4.1、§5.2 |
| `POST /interviews/{id}/questions/match` | interview | interview §4.1、§5.3 |
| `POST /interviews/{id}/prep` | interview | interview §4.1、§5.4 |
| `GET /interviews/{id}/prep` | interview | interview §4.1、§5.5 |
| `PUT /interviews/{id}/prep` | interview | interview §4.1、§5.5 |
| `GET /interviews/{id}/report/export` | evaluation | evaluation-export §4.1 |

### 6.5 非功能（PRD §9）与分期（§11）

| PRD 项 | 章节 | 落地 | 位置 |
|---|---|---|---|
| 数据隔离（含 HR 读候选人简历） | §9 | 各模块 | interview §5.2；见 §5.1 |
| 简历的跨端流不破坏分层 | §9 | resume / interview / practice | resume §1.3；见 §5.2 |
| 新增依赖受控 | §9 | evaluation | evaluation-export §3.4 |
| MVP-3 里程碑与迁移说明 | §11 | — | **§7 的 DDL 清单** |

---

## 7. DDL 统一收口清单（**本模块最重要的交付物**）

> **用途**：你要用单独的方式统一建表/改表。**本表就是那次操作的输入**。
>
> 本清单**汇总 MVP-2 与 MVP-3 两批**——因为 MVP-2 的 DDL 当时也刻意没写（同样的约定），两批必须一起收口，否则无论先做哪一批，应用都起不来。

### 7.1 待建表

| # | 批次 | 表 | 关键约束 | 特别说明 |
|---|---|---|---|---|
| 1 | MVP-2 | `interview_invitation` | `code` **唯一**；FK → `interview.id` | — |
| 2 | MVP-2 | `practice_session` | FK `candidate_user_id` → `user.id` **RESTRICT**；`position_id` NULL 允许 | MVP-3 追加两列（见 §7.2） |
| 3 | MVP-2 | `practice_item` | `UNIQUE (session_id, seq)`；`is_correct` **必须可空**（三态：TRUE/FALSE/**NULL**） | `is_correct` 若加成 NOT NULL，「未判分」这一状态就没了（module-13 §3.2） |
| 4 | MVP-2 | `candidate_feedback` | FK → `interview.id` **CASCADE**；`interview_id` **唯一** | ✅ 已于 2026-09-21 **补进 PRD §5.2**（此前 PRD 未列此表，见 §8.2 第 8 条） |
| 5 | MVP-3 | `resume` | FK `created_by` → `user.id` **RESTRICT**；索引 `ix_resume_created_by` | `updated_at` 是本项目**首个 `ON UPDATE CURRENT_TIMESTAMP`** 列（module-17 §3.1） |
| 6 | MVP-3 | `interview_prep` | `interview_id` **UNIQUE**；FK → `interview.id` **CASCADE**；三个 JSON 列 NOT NULL | ⚠️ **MySQL 的 JSON 列不支持 DEFAULT**——默认值只能在模型层给，写入时必须显式供值（module-19 §3.3） |

### 7.2 待加列 / 待改列

| # | 批次 | 表 | 变更 | 类型 | 特别说明 |
|---|---|---|---|---|---|
| 7 | MVP-2 | `question` | `+question_type`, `+options`, `+reference_answer`, `+explanation` | ADD COLUMN | ⚠️ **`options` 是 JSON NOT NULL，必须分三步**：① 先加可空列 → ② `UPDATE ... SET options = JSON_ARRAY()` → ③ 改成 NOT NULL。**一步到位会因既有行为 NULL 而失败** |
| 8 | MVP-2 | `answer` | `+source`, `+answered_by`, `+submitted_at` | ADD COLUMN | `answered_by` FK → `user.id` |
| 9 | MVP-3 | `interview` | `+resume_id` | ADD COLUMN | NULL 允许；FK → `resume.id` **RESTRICT** |
| 10 | MVP-3 | `interview_question` | `+match_reason` | ADD COLUMN | TEXT NULL |
| 11 | MVP-3 | `interview_question` | **`source_snapshot` 枚举加取值 `'resume_match'`** | ⚠️⚠️ **MODIFY COLUMN，不是 ADD COLUMN** | 见 §7.3 |
| 12 | MVP-3 | `practice_session` | `+resume_id`, `+resume_match_applied` | ADD COLUMN | `resume_id` NULL + FK `RESTRICT`；`resume_match_applied` BOOLEAN **NOT NULL DEFAULT false** |

> **`user.role` 的 `candidate` 枚举值已做**（迁移 `b7f1c2a4d8e6`，且已升到 dev 库），**不在本次清单内**。

### 7.3 ⚠️ 第 11 项必须单独强调（**最容易漏的一条**）

**现状**（`backend/app/interview/models.py:121-123`）：

```
source_snapshot: Mapped[str] = mapped_column(
    Enum(SOURCE_BANK, SOURCE_AI, name="interview_question_source"), nullable=False
)
```

| 项 | 内容 |
|---|---|
| 目标 | `Enum(SOURCE_BANK, SOURCE_AI, SOURCE_RESUME_MATCH, name="interview_question_source")` |
| SQL 性质 | `ALTER TABLE interview_question MODIFY COLUMN source_snapshot ENUM('bank','ai','resume_match') NOT NULL` |
| 漏掉的后果 | 补题写入 `resume_match` 时抛 `DataError: Data truncated for column 'source_snapshot'`——**功能直接不可用** |
| **为什么容易漏** | 它是**改既有列的取值域**，不是「新增了哪些列/表」。若按后者收集 DDL，**这一条必然不在名单上**。它是 MVP-3 里**唯一一处**此类变更 |

| 备选方案 | 评价 |
|---|---|
| 改成 `VARCHAR` | ❌ 会让「来源」失去取值约束；为加一个取值而放松整体约束，代价大于一次 `MODIFY COLUMN`（module-19 §3.2） |

### 7.4 建表顺序（外键依赖）

```
user（已存在）
  └─ resume                        ← 必须先于 interview 的新外键
  └─ interview_invitation
  └─ interview（已完成；本次加 resume_id → 需 resume 先建）
       └─ interview_question（CASCADE）
            └─ answer（CASCADE）
       └─ interview_prep（CASCADE）
       └─ candidate_feedback
  └─ practice_session → practice_item（CASCADE）
```

> **`resume` 必须早于 `interview.resume_id` 的外键**；`interview_prep` 必须晚于 `interview`。

### 7.5 收口后的验证

| # | 验证 |
|---|---|
| 1 | `alembic upgrade head` 成功；`alembic downgrade -1` 再 `upgrade` 各一次均成功 |
| 2 | `backend/script.sql` 与迁移结果**一致** |
| 3 | 应用在 dev 库上**能启动**（收口前会因缺列直接报错） |
| 4 | 全量 `pytest tests/ -q` 通过 |
| 5 | 补题功能在 dev 库上**实际能写入 `resume_match`**（第 11 项的落地验证） |
| 6 | `source_snapshot` 的列定义确认为 `enum('bank','ai','resume_match')` |

---

## 8. 遗留问题与已知局限（**交接清单**）

### 8.1 未完成的既存工作（**不是 MVP-3 引入的**）

| # | 项 | 影响 | 处置 |
|---|---|---|---|
| 1 | **候选人前端（module-15）整体未实现** | MVP-3 的简历录入 / 关联 / 刷题入口**没有 UI 闭环**，只能用接口演示 | **计划书已存在且完整（569 行），待执行**。**执行顺序已定**：module-15 → module-22；与 module-23 无依赖，可并行。**后端 17～21 均不依赖它，可先行**。README 与演示文档必须如实写明（§3.3） |
| 2 | **dev 库缺列**（DDL 未收口） | 应用**跑在 dev 库上会直接报错**（测试不受影响，conftest 从模型重建） | 见 §7 的清单 |

### 8.2 MVP-3 的已知局限（**有意接受**）

| # | 局限 | 原因 | 出处 |
|---|---|---|---|
| 3 | **补题会累加**：每次调用追加一批新题 | PRD §4.14 明确「可重复触发；每次只追加本场尚不存在的题」。「幂等」只指**不产生重复题目**，不指「重复调用无效果」 | module-19 §5.3 |
| 4 | **刷题推荐的候选池按 `id` 取前 N 条**（N = `min(size*4, 100)`） | 池子必须放大 AI 才能**改选**（否则只是重排）；而取池复用既有 SQL（按 id 排序）。后果：符合条件的题目超过池上限时，**排在后面的题永远进不了推荐** | module-20 §5.2 |
| 5 | **准备助手不做 DOCX** | 它是 HR 的现场工作稿，打印 PDF 足够；DOCX 的消费者是留档/转发，那是报告的用途 | module-23 §3.4 |
| 6 | **刷题推荐时 `jd` 传空串** | 刷题不绑定岗位，且 `list_practice_positions` 的契约**刻意不下发 JD**（PRD §4.7）。真实 Provider 的 prompt 中该行为空，属措辞质量损失，不影响选排逻辑 | module-20 §4.4 |
| 7 | **无后端 PDF**：不能脱离浏览器批量 / 后台导出 | PRD §4.12 明确 PDF 走浏览器打印，且不引入 PDF 库 | module-21 §1.2 |
| 8 | ~~`candidate_feedback` 表不在 PRD §5.2~~ | — | ✅ **已补进 PRD §5.2**（2026-09-21，含一行实体 + 一条设计说明）。不再是缺口 |
| 9 | **雷达图是位图，打印略糊** | Canvas 绘制（dpr=1 时），打印分辨率低于矢量 | **接受为已知限制**。它能出图、颜色不丢、尺寸不失真（module-23 §5.4 已核实）。改渲染方式属 module-07 的改动，不在本批次 |
| 9 | **准备助手不流式** | PRD §4.11 明确「一次生成即整批落库」。流式会引入 SSE 复杂度（既有 SSE 已有 `--workers 1` 限制） | module-19 §1.2 |
| 10 | **候选人看不到补题理由** | PRD §4.6 限定候选人可见范围；`match_reason` 描述的是 HR 的评估思路 | module-19 §4.2 |
| 11 | **补题无撤销** | PRD §4.14 明确「不提供撤销接口」，与既有题目同样不可删 | module-19 §1.2 |
| 12 | **单机约束**：SSE 与刷题限流需 `--workers 1` | PRD §2 禁止引入 Redis / 消息队列；多进程下限流各自独立、评估任务跨进程不可见 | module-06 §5.6、module-13 §5.8 |

### 8.3 设计决策定稿（原「待拍板项」，**已全部决出**）

| # | 议题 | **结论** | 理由 |
|---|---|---|---|
| 13 | 雷达图的渲染方式与打印表现 | **已核实为 Canvas**。能打印出图、颜色不丢、尺寸不拉伸；代价是位图略糊 | 见 §5.4 与 module-23 §5.4。**反直觉的一点**：canvas 的颜色是像素，**不受 `print-color-adjust` 影响**，在「颜色保留」上比 CSS 背景更稳——**因此真正的风险点是分数色块与标签底色，不是雷达图** |
| 14 | 候选人前端（module-15）何时执行 | **排在本批次执行队列第一位**。顺序：`module-15 → module-22`；`module-23` 与二者无依赖，可并行；**后端 `17～21` 完全不依赖它，可先行** | module-22 的简历页 / 关联 UI / 刷题入口都建立在 module-15 的基座上（module-22 开头已声明该前提）。后端五个模块自成闭环，不被前端阻塞——**先做后端可以让功能①②③的接口侧尽早可验证** |
| 15 | 补题累加是否要加上限 | **不加新机制** | **它已天然有界**：单次 `count ≤ 20`（module-19 §3.4），且候选池耗尽后返回 409。真正需要的是**前端的连点防护 + 「本场共 M 题」提示**——两者 module-23 §5.2b 都已设计。加「已补过」标记需要新的状态字段，**PRD 未定义该概念**，属凭空扩大模型 |
| 16 | `candidate_feedback` 是否补进 PRD §5.2 | **已补** | PRD 是权威契约；代码里存在的表而 PRD 没有，就是**追溯断点**（module-24 §6 的矩阵会因此指不到位置）。module-14 当时只在模型 docstring 里备注了这件事，收尾时应把它落到 PRD。**补一行成本极低** |
| 17 | 准备助手是否需要 DOCX 导出 | **不需要**（维持原设计） | 它是 HR 的**现场对照工作稿**，打印 PDF 足够；DOCX 的消费者是「留档 / 转发 / 二次编辑」，那是**报告**的用途。做它意味着在 `interview` 与 `evaluation` **各写一份文档装配代码**，成本高于收益（module-23 §3.4） |

---

## 9. 任务分解

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-17～23 **全部执行完毕**。

### Task 24.1：README 增量与可启动性检查

- [ ] README 增补 §3.1 镜像安装、§3.2 新配置项、§3.3 MVP-3 演示路径
- [ ] 打开首页确认应用能起、登录可用（若 dev 库未收口则会失败——**记录该现象**）
- [ ] 提交

### Task 24.2：流程⑥ 端到端验证

- [ ] 执行 §4.1 全部 13 步，逐条记录实际结果
- [ ] 提交验证记录

### Task 24.3：流程⑦ 端到端验证

- [ ] 执行 §4.2 全部 11 步
- [ ] 提交验证记录

### Task 24.4：报告导出验证

- [ ] 执行 §4.3 全部 14 步（**含实际打开 DOCX 与实际另存 PDF**）
- [ ] 提交验证记录

### Task 24.5：异常路径验证

- [ ] 执行 §4.4 全部 13 项（含把 Provider 切到会抛错的实现来构造 AI 失败）
- [ ] 提交验证记录

### Task 24.6：非功能验证

- [ ] 执行 §5.1（隔离 10 项）、§5.2（架构 8 项）、§5.3（依赖 7 项）、§5.4（打印 4 项）
- [ ] **修正 module-08 §5.4 第 1 条的「七个独立 package」→「九个」**（§5.2 的提醒）
- [ ] 提交

### Task 24.7：需求追溯与代价核对

- [ ] 逐条核对 §6 的追溯矩阵，确认每条 PRD 需求都能指到模块位置
- [ ] 提交

### Task 24.8：DDL 清单定稿

- [ ] 逐条核对 §7，确认与各模块计划书**逐字一致**（尤其 §7.3 的 `MODIFY COLUMN`）
- [ ] 把清单单独导出/摘出，作为「统一收口」的输入
- [ ] 提交

### Task 24.9：全量回归与交接

- [ ] `pytest tests/ -q` 全绿
- [ ] `npm test` / `npm run build` 全绿
- [ ] 确认 `standalone.html` 未被修改
- [ ] 整理 §8 的遗留清单与已决决策（§8.3 已定稿，核对是否与实际一致）
- [ ] 提交

---

## 10. 验收标准

- [ ] README 含**镜像安装命令**与**直连的两个具体症状**（超时 / 误解析到 0.8.11）
- [ ] README 含新配置项 `resume_match_count`
- [ ] README 的演示路径**如实标注**「候选人前端未实现」的部分需走接口
- [ ] 流程⑥ 的 13 步、流程⑦ 的 11 步、导出的 14 步、异常路径的 13 项**全部执行并有记录**
- [ ] **DOCX 实际打开验证过**：八区块齐备、中文正常、无图片、回答不截断
- [ ] **PDF 实际另存验证过**：颜色保留、无控件、雷达图未断页
- [ ] 导出文件名是**解码后的中文**，不是百分号串
- [ ] 「补题会累加但不重复」「刷题推荐降级后与不传 `resume_id` 逐条相同」**两条已实测**
- [ ] 隔离验证 10 项通过，**含 `match_reason` 不下发候选人的两条**
- [ ] 架构验证确认 **9 个 package**、`AIProvider` **9 个抽象方法**
- [ ] **module-08 §5.4 第 1 条已从「七个」改为「九个」**
- [ ] 依赖验证确认**仅 `python-docx` 一项新增**，前端零新增
- [ ] **雷达图的 SVG/canvas 结论已给出并记录**（不假定）
- [ ] §6 追溯矩阵逐条可指到模块位置
- [ ] **§7 的 DDL 清单与各模块计划书逐字一致**，且**第 11 项明确标注为 `MODIFY COLUMN`**
- [ ] §8 的遗留清单包含**候选人前端未实现**与 **dev 库缺列**两条既存问题
- [ ] **§8.3 的五条决策已定稿**（雷达图 canvas / module-15 优先 / 补题不加限 / `candidate_feedback` 已补 PRD / 准备助手不做 DOCX）
- [ ] `pytest tests/ -q` / `npm test` / `npm run build` 全绿
- [ ] `standalone.html` 未被修改

---

## 11. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **DDL 清单若只按「新增了哪些列/表」收集，必漏 `MODIFY COLUMN`** | §7.3 **单独一节**强调第 11 项 | 它是 MVP-3 唯一一处「改既有列取值域」的变更。漏掉的后果是补题直接抛 `Data truncated`——**功能不可用，且报错信息与 DDL 无关，排查成本高** |
| **MVP-2 与 MVP-3 的 DDL 必须一起收口** | §7 汇总两批 | 两批当时都刻意没写。**先做哪一批应用都起不来**，所以不能分两次 |
| **`question.options` 加 JSON NOT NULL 必须三步** | §7.2 第 7 条写明 | 一步到位会因既有行为 NULL 而失败。这是 MySQL JSON 列的既有坑，MVP-2 时就已记录 |
| **MySQL JSON 列不能有 DEFAULT** | §7.1 第 6 条写明 | 默认值只能在模型层给。若在 DDL 里写 DEFAULT 会直接语法报错 |
| **module-08 §5.4 的「七个独立 package」已陈旧** | Task 24.6 显式修正为九个 | 它是**人工维护的硬编码文本**，加模块（practice、resume）时没人会想起它。**文档陈旧不会让任何测试变红**，只能靠收尾模块抓 |
| **候选人前端未实现会让简历功能无法 UI 演示** | §3.3 与 §8.1 **如实写明** | 掩盖这一点会让后来者以为环境搭错了。**如实记录 + 给出接口演示路径**是唯一诚实的处置 |
| **雷达图的打印表现若靠「假定」就会翻车** | **已核实**：它是 canvas，能打印、颜色不丢、不拉伸（§5.4） | 而且结论**与直觉相反**——canvas 的颜色是像素、不受 `print-color-adjust` 影响。**由此把走查注意力从雷达图转移到真正会掉色的地方：CSS 背景（分数色块、标签底色）** |
| **降级与失败必须可区分** | §4.4 末尾汇成一张对照 | 本批次反复出现：补题失败 502 vs 补题无结果 200、生成失败 502 vs 未生成 404、推荐失败 201+留痕。**混在一起会让「没有」被当成「坏了」，或反过来** |
| **只验证与收尾，不就地改代码** | 沿用 module-08 §1.2 | 就地改会让改动脱离对应模块的契约与测试，也让「哪份计划书是权威」变得含糊 |
| **不写迁移** | §1.2 明确 | 你已明确要统一收口。本模块的职责是**把清单备齐并标明陷阱**，不是产出迁移 |
| **本模块不重复 module-08 的内容** | §1.2 明确 | 前五条流程与 MVP-1/2 的非功能项已在 module-08。重复会让两份文档对同一批验证各有一套说法 |
