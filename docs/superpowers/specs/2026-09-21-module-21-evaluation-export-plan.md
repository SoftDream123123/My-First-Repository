# evaluation 模块执行计划书（MVP-3 报告 DOCX 导出）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：evaluation（在既有评分 / 报告 / SSE 流 / 候选人反馈之上，新增报告 DOCX 导出）
**所属包**：`backend/app/evaluation/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.12（报告导出）、§4.5（报告内容）、§2（`python-docx` 依赖与镜像安装）、§7（导出失败）、§8（端点）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-06 evaluation](./2026-09-15-module-06-evaluation-plan.md)、[module-14 evaluation 反馈](./2026-09-20-module-14-evaluation-feedback-plan.md)
**本模块被谁依赖**：[module-23 HR 前端](./2026-09-21-module-23-hr-frontend-plan.md)

**⚠️ 本模块是 MVP-3 唯一引入新依赖的模块**：`python-docx`（安装**必须走镜像**，见 §3.4 与 PRD §2）。

---

## Global Constraints（全局约束，摘自 PRD）

- 导出**仅限 HR 侧**的面试报告；**候选人脱敏反馈不提供导出**（§4.12）
- 导出内容 = **HR 报告全文**，不含候选人脱敏视图（§4.5、§4.12）
- **DOCX 里不放雷达图**——Python 侧重画成本不划算（§4.12）
- **PDF 不走后端**：由前端浏览器打印实现，**本模块不提供任何 PDF 接口**（§4.12）
- 两条路径**共用同一份数据来源**（`ReportDetail`），**不额外落库导出记录**（§4.12）
- 必须复用既有 `evaluation` 的可见性与状态校验：**未评估完成不可导出**（§4.5、§7）
- 新增依赖**仅 `python-docx`**；`requirements.txt` 中写 `python-docx>=1.1`（§2）
- **安装必须走镜像**（本机直连 PyPI 超时，且会误解析到 2021 年的 `0.8.11`）（§2）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.12）

| 子职责 | 内容 | PRD |
|---|---|---|
| 导出端点 | `GET /interviews/{id}/report/export?format=docx`，返回文件流 | §4.12 |
| 文档装配 | 由 `ReportDetail` 生成 DOCX 字节流 | §4.12 |
| 中文可读性 | 显式设置**东亚字体**，避免中文在某些查看器中变形 | §4.12（「中文完美」是选型的理由之一） |
| 文件名安全 | 文件名含岗位名与候选人姓名，须**消毒**防头部注入 | §4.12（延伸） |
| 权限与状态 | 复用既有可见性校验与「仅 `evaluated` 可读」 | §4.5 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **后端生成 PDF** | PRD §4.12 明确 PDF 走**前端浏览器打印**，后端**不提供** PDF 接口，也**不引入任何 PDF 库** |
| **雷达图** | PRD §4.12 明确「DOCX 里不放雷达图」。需要图形走打印 PDF |
| **导出准备助手提纲** | 准备助手是 HR 的工作稿，走**前端打印 PDF**（PRD §4.12 只把 DOCX 给了报告）。见 §10 的说明 |
| **导出候选人脱敏反馈** | PRD §4.12 明确不在范围内 |
| **导出记录落库 / 下载历史 / 下载计数** | PRD §4.12 明确「不额外落库导出记录」 |
| **异步导出 / 批量导出 / 导出队列** | 单份报告在秒级完成，且单机部署不引入任务队列（§2） |
| **模板文件（`.docx` 模板）与样式可配置** | 项目无模板管理机制；样式内置在装配函数里，与既有「prompt 内置」同理 |
| **报告内容本身的计算** | 全部来自既有 `service.get_report`。本模块**不重算任何分数** |

### 1.3 依赖方向

```
evaluation.router ──→ evaluation.service ──→ evaluation.repository
                          │
                          ├──→ evaluation.export（纯装配，无 DB、无 FastAPI）   ← 新增文件
                          └──→ interview.service（读快照与回答，既有）

evaluation ──→ core / auth / interview / ai（**依赖集合不变**）
evaluation ✗→ position / question / practice（禁止集合不变）
```

> **本次不新增任何模块间依赖边**：`export.py` 只吃 `ReportDetail`（本模块自己的 schema），不读数据库、不调 AI。因此 `FORBIDDEN_DEPENDENCIES` **无需改动**，架构测试自动覆盖新文件。

---

## 2. 文件结构

| 文件 | 单一职责 | 本次改动 |
|---|---|---|
| `backend/app/evaluation/export.py` | **新增**。`ReportDetail` → DOCX 字节流。纯函数，无 DB、无 FastAPI、无 IO | **新增** |
| `backend/app/evaluation/service.py` | 业务编排 | **改**：新增 `export_report` 与 `ReportExport` dataclass |
| `backend/app/evaluation/router.py` | 端点 | **改**：新增 1 个端点 |
| `backend/app/evaluation/schemas.py` | 请求 / 响应模型 | **无改动**（导出返回二进制流，无响应模型） |
| `backend/app/evaluation/repository.py` | 数据访问 | **无改动** |
| `backend/requirements.txt` | 依赖声明 | **改**：新增 `python-docx>=1.1` |

**`export.py` 为什么单独成文件**

| 理由 | 说明 |
|---|---|
| **它是纯函数** | 输入 `ReportDetail`、输出 `bytes`，**不碰数据库、不碰 FastAPI**，因此可以用最便宜的方式单测（构造一个 `ReportDetail` 即可） |
| **与 `stream.py` 同理** | `stream.py` 已是「同模块内的非分层文件」（SSE 事件生成）。`export.py` 是同一形态：一个专注的技术细节，不属 router/service/repository 任何一层 |
| **不让 `service.py` 继续膨胀** | `service.py` 已 320 行且承担评估编排；把 100+ 行的文档装配塞进去会让「评估流程」与「文档排版」两个无关关注点混在一处 |

**测试文件**

| 文件 | 本次改动 |
|---|---|
| `backend/tests/test_evaluation_export.py` | **新增**：`export.py` 的装配单测（round-trip） |
| `backend/tests/test_evaluation.py` | **改**：新增导出端点的鉴权 / 状态 / 头信息用例 |
| `backend/tests/conftest.py` | **无改动**（复用既有 `evaluated` 面试夹具） |

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/requirements.txt` | 新增 `python-docx>=1.1` | 唯一新增依赖 |
| `backend/README.md` | 补一条「安装须走镜像」的说明 | ⚠️ 本机直连 PyPI 不通（PRD §2 已实测）。**不写进 README，下一个人装依赖会卡几分钟后失败** |

> **不写 alembic 迁移、不同步 `backend/script.sql`**（PRD §11）——**本模块无任何数据库变更**。
>
> **不新增配置项**：导出没有需要运维调整的旋钮（格式只有一种、内容固定）。

---

## 3. 文档结构设计（**本模块无数据模型变更**）

### 3.1 文档骨架（对应 PRD §4.12 的内容清单）

| # | 区块 | 内容来源 | Word 元素 |
|---|---|---|---|
| 1 | 标题 | 固定文案「面试评估报告」 | 一级标题 |
| 2 | 基本信息表 | 岗位名 / 候选人姓名 / 评估时间 | 2 列 × 3 行表格 |
| 3 | 总分 | `overall_score`（0–10，1 位小数） | 二级标题 + 段落 |
| 4 | 综合结论 | `conclusion` | 二级标题 + 段落 |
| 5 | 优点 | `strengths`（逐条） | 二级标题 + 无序列表 |
| 6 | 待改进 | `weaknesses`（逐条） | 二级标题 + 无序列表 |
| 7 | 逐题评分 | `question_scores` 全字段 | 二级标题 + 6 列表格 |
| 8 | 多维评分 | `dimension_scores` 全字段 | 二级标题 + 3 列表格 |

**区块 2 与 7、8 的列定义**

| 区块 | 列 |
|---|---|
| 基本信息 | 岗位 / 候选人 / 评估时间 |
| 逐题评分（6 列） | 序号（`seq`） / 考察维度（`dimension`） / 题目（`content`） / 回答（`answer`） / 得分（`score`） / 评语（`comment`） |
| 多维评分（3 列） | 维度（`dimension`） / 得分（`score`） / 评语（`comment`） |

| 决策 | 理由 |
|---|---|
| **逐题表包含「回答」原文、不截断** | 回答是分数的**证据**。截断会让报告失去「HR 复核当初为什么给这个分」的用途，而 DOCX 正是留档交付物。代价是回答长时文档会很长——**Word 会自动换行，这是可接受的排版代价** |
| **`answer` 为 null 时写「（未作答）」** | 与既有 `evaluate_answer` 的 prompt 措辞一致（`openai_provider.py:227`），保持同一套表达 |
| **分数统一 `f"{score:.1f}"`** | 与既有报告页 / 雷达图 / `summarize_report` 的格式化一致，避免同一个分数在两个地方显示成 `7` 与 `7.0` |
| **维度顺序沿用 `dimension_scores` 的既有顺序** | 该顺序由评估流程按岗位维度列表产生，**本模块不重排**——重排会引入第二套维度顺序口径 |
| **逐题顺序按 `seq`** | `get_report` 已排序（`service.py:195` 的 `sort(key=lambda q: q.seq)`），本模块**不再排序** |
| **空列表时的表现形式** | `strengths` / `weaknesses` 为空 → 写「（无）」；`question_scores` / `dimension_scores` 为空 → 仍输出表头（空表比整块消失更易察觉异常） |
| **不放雷达图、不放任何图片** | PRD §4.12 明确 |
| **不落页码 / 页眉页脚** | PRD 未要求；页眉页脚需要额外的 XML 操作（python-docx 无高层 API），收益不成比例 |

### 3.2 中文可读性（**最容易做错的一处**）

`python-docx` 的默认样式基于 `Calibri`。**中文不会因此「看不见」，但在部分查看器（尤其 WPS 与 LibreOffice 的默认渲染）下会退化到不可控的替代字体，甚至出现方框。**

| 做法 | 说明 |
|---|---|
| 设置文档默认样式的中文字体 | 需要把 `w:rFonts` 的 **`w:eastAsia`** 属性设成一个中文字体（如 `宋体` / `微软雅黑`），**只设 `w:ascii` 不够**——中文字符走的是 `eastAsia` 分支 |
| 与西文字体并存 | `w:ascii` 保持一个西文字体（数字与英文），`w:eastAsia` 设中文字体，两者**不是二选一** |
| 实现位置 | 统一在 `export.py` 的一个 `_set_default_font(document)` 辅助里做一次，**不要在每个 `add_paragraph` 处重复设置** |

> ⚠️ **`python-docx` 没有「设置中文字体」的高层 API**：`style.font.name = "宋体"` **只改 `w:ascii`**，中文仍走 `eastAsia`。必须拿到 `style.element.rPr.rFonts` 并显式 `set(qn("w:eastAsia"), "宋体")`（必要时还要 `get_or_add_rPr()` / `get_or_add_rFonts()`）。
>
> **这是本模块最容易被漏掉的一处**：漏掉时**在一部分查看器里看起来完全正常**，只在另一些里出问题——属于「本地看着没问题」的典型故障。因此 §7 必须有一条断言「文档默认样式的 `eastAsia` 字体已设置」。

| 决策 | 理由 |
|---|---|
| **选「宋体」（`SimSun`）作为默认中文正文字体** | 它是 Windows 简体中文环境的**默认衬线字体**，本项目的目标终端就是 **Windows 单机 PC**（PRD §2），因此无需打包字体、无需回退链。选「微软雅黑」亦可，但它是无衬线，用于文档正文不如宋体常见 |
| **不内嵌字体** | python-docx 不支持字体嵌入；即使支持也会让文档体积暴涨。目标终端是 Windows，字体必然存在 |
| **不做字体缺失的运行时检测** | 单机 Windows 部署下无法触发；检测逻辑在 Linux CI 上会永远报「缺字体」，反而变成噪声 |

### 3.3 文件名设计（**含一处安全考虑**）

**命名规则**：`面试评估报告-{position_name}-{candidate_name}.docx`

| 风险 | 处置 |
|---|---|
| **HTTP 头部注入**：`candidate_name` / `position_name` 是**用户输入**（HR 创建面试时填的），若含 `"`、CR、LF，会破坏 `Content-Disposition` 头或注入额外头部 | **消毒**：剔除 `"`、`\`、CR、LF、`/`、`\`、以及 ASCII 控制字符；再限长（建议 60 字符内）；消毒后为空则退化为「候选段」缺省值 |
| **文件名含中文，不能直接放进 `filename=`** | 用 **RFC 5987** 双写：`filename="report.docx"; filename*=UTF-8''<percent-encoded>`。ASCII 回退名保证老客户端也能存下文件 |
| **`candidate_name` 很长** | 限长，避免超长头部被中间件截断 |

**消毒的落点**：消毒发生在 `service.export_report` 里（它已持有 `ReportDetail`），`export.py` **只负责文档内容、不管文件名**——保持「文档装配」与「HTTP 语义」分离。

### 3.4 依赖与安装（对应 PRD §2）

| 项 | 内容 |
|---|---|
| 声明 | `requirements.txt` 新增 `python-docx>=1.1` |
| 实测解析结果 | `python-docx 1.2.0`（纯 Python wheel）+ `lxml 6.1.3`（`cp313-cp313-win_amd64` 二进制 wheel），共约 4.3 MB |
| **安装命令（必须带镜像）** | `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple python-docx` |
| 直连的后果 | 超时（5 次重试均 0 字节），且索引取不全时会把包解析到 2021 年的 `0.8.11` |

> ⚠️ **必须把「走镜像」写进 `backend/README.md`**：这是**环境事实**，不是代码事实。不写下来，下一个人（或下一次部署）会重新踩一遍——先在 `files.pythonhosted.org` 上卡几分钟，再拿到一个把 `python-docx` 解析成 `0.8.11` 的诡异结果。

---

## 4. 接口契约

### 4.1 对外 REST API（守卫 `require_roles(admin, hr)`，复用既有 `_hr_guard`）

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| GET | `/api/interviews/{id}/report/export` | 导出报告为 DOCX，返回**文件流** | 200 |

**查询参数**

| 参数 | 类型 | 默认 | 约束 |
|---|---|---|---|
| `format` | str | `docx` | **当前仅支持 `docx`**；其他取值 → 400 |

> **为什么只有一个取值还要留这个参数**：PRD §8 的端点表已把它写成 `?format=docx`。保留参数让**将来加格式不必改路径**（改路径会同时破坏前端与已发出的文档链接）。**不支持的值报 400 而不是静默当 docx**——静默回退会让调用方以为拿到了别的格式。

**响应头**

| 头 | 值 |
|---|---|
| `Content-Type` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `Content-Disposition` | `attachment; filename="report.docx"; filename*=UTF-8''<消毒并百分号编码的文件名>` |

> **用 `Content-Disposition: attachment` 而不是 `inline`**：`inline` 会让浏览器尝试在标签页里预览，而 DOCX 无法预览，结果是下载一个临时文件或弹出无从选择的行为。`attachment` 语义明确。

### 4.2 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `export_report(db, user, interview_id: int, fmt: str) -> ReportExport` | 导出结果 | 校验格式 → 取报告 → 装配 → 组装文件名（§5） |

**新增 dataclass**

| dataclass | 字段 | 说明 |
|---|---|---|
| `ReportExport` | `content: bytes`、`filename: str`、`media_type: str` | `service` 与 `router` 之间的载体。**不用 `tuple`**：三个同类型 `str` 里两个是字符串，元组会让 `(content, filename)` 与 `(filename, content)` 的笔误无声通过 |

> **`ReportExport` 定义在 `service.py`**（与既有 `EvaluationItem` 同处），而不是 `schemas.py`：`schemas.py` 承载的是**HTTP 请求 / 响应模型**，而 `ReportExport` 是**内部传递结构**（含 `bytes`，无法作为 Pydantic 响应模型）。

### 4.3 `export.py` 的契约（**纯函数，无副作用**）

| 签名 | 返回 | 说明 |
|---|---|---|
| `build_report_docx(report: ReportDetail) -> bytes` | DOCX 文件字节流 | **唯一对外函数** |

| 约束 | 说明 |
|---|---|
| **不接收 `Session`** | 它不读数据库。数据全部来自入参 `ReportDetail` |
| **不接收 `User`** | 它不做权限判断。权限在 `service`/`router` |
| **不写磁盘** | 全程在内存（`io.BytesIO`）。单机部署下写临时文件会引入清理与并发问题 |
| **不打印 / 不记日志** | 纯函数，不产生副作用 |
| **不做 IO 之外的失败兜底** | 失败即抛，由 `service` 决定对外表现（§6） |

**内部辅助（私有，不对外）**

| 辅助 | 职责 |
|---|---|
| `_set_default_font(document) -> None` | 设置 `w:ascii` 与 **`w:eastAsia`**（§3.2） |
| `_add_info_table(document, report) -> None` | 区块 2 |
| `_add_bullets(document, items) -> None` | 区块 5 / 6，空时写「（无）」 |
| `_add_question_table(document, report) -> None` | 区块 7 |
| `_add_dimension_table(document, report) -> None` | 区块 8 |

### 4.4 与既有能力的关系

| 既有 | 本次 |
|---|---|
| `service.get_report(db, user, interview_id)` | **直接复用**。因此自动继承：面试不存在 → 404；非本人 → 403；状态非 `evaluated` → **409「评估尚未完成」**；报告行缺失 → 404「报告不存在」 |
| `service.ensure_visible` | 不需要单独调用（`get_report` 内部已调 `interview_service.get_interview`） |
| `ReportDetail` schema | **不改动一个字段**。本模块是纯消费者 |
| `stream.py` 的 SSE | 与导出无关，零交互 |
| `evaluation/candidate_router.py` | **零改动**（候选人无导出） |

---

## 5. 业务流程设计

### 5.1 导出流程

```
export_report(db, user, interview_id, fmt):
1. 若 fmt != "docx" → ValidationError(400)「不支持的导出格式」
       ← 在取报告**之前**校验：格式错了就不该白读一次库
2. report = get_report(db, user, interview_id)
       ← 复用既有：404 / 403 / 409（评估尚未完成）/ 404（报告不存在）全在此
3. content = export.build_report_docx(report)
4. filename = _build_filename(report)          ← §5.2
5. return ReportExport(content=content, filename=filename,
                        media_type=_DOCX_MEDIA_TYPE)
```

```
router.export_report(interview_id, format, db, user):
1. result = service.export_report(db, user, interview_id, format)
2. return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": _content_disposition(result.filename)},
   )
```

| 决策 | 理由 |
|---|---|
| **第 1 步先校验格式** | 格式非法时读库毫无意义；且 400 与 404/409 的优先级应当是「参数错先于资源错」，与 `main.py` 的全局校验收口方向一致 |
| **用 `Response` 而不是 `StreamingResponse`** | 内容已在内存中完整生成（一份报告通常几十 KB，回答很长时最多几 MB）。`StreamingResponse` 适合「边读边发」的场景（如既有 SSE），**这里没有流可流**，用它反而多一层包装 |
| **不设 `Content-Length`** | Starlette 对 `bytes` 内容会自动设置。手写容易算错 |
| **一次导出全程在内存** | 单机 + 单份 + 几十 KB～几 MB，无需落盘。**不写临时文件**，避免清理与并发问题 |

### 5.2 文件名组装与消毒

```
_build_filename(report) -> str:
  raw = f"面试评估报告-{report.position_name}-{report.candidate_name}.docx"
  return _sanitize_filename(raw)

_sanitize_filename(name) -> str:
  1. 剔除：`"`  `\`  `/`  CR  LF  TAB  及所有 ASCII 控制字符（< 0x20）
  2. 剔除后若只剩扩展名（即中段全空）→ 退化为 "report.docx"
  3. 中段限长 60 字符（超出截断）
  4. 保持 UTF-8 字符串返回（百分号编码在 router 层做）
```

**router 层的百分号编码**

```
_content_disposition(filename) -> str:
  ascii_fallback = "report.docx"                       ← 与真实名字无关的固定 ASCII 名
  encoded = urllib.parse.quote(filename, safe="")
  return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'
```

| 决策 | 理由 |
|---|---|
| **消毒放在 `service`，编码放在 `router`** | 消毒是**业务规则**（文件名该长什么样）；百分号编码是**HTTP 协议细节**。混在一起会让 `export.py` 或 `service` 承担协议知识 |
| **ASCII 回退名用固定的 `report.docx`，不用拼音化** | 把中文转拼音需要额外映射表，收益只是「老客户端里文件名好看一点」。现代浏览器都认 `filename*`，**不做无谓的复杂度** |
| **`safe=""`** | 让 `urllib.parse.quote` 编码包括 `/` 在内的所有字符，避免文件名里的路径分隔符被当成路径 |
| **⭐ 必须测试注入** | `candidate_name = 'A"; DROP'`、含 `\r\n` 的值、含 `/` 的值 → 断言最终头部**不含**这些字符，且 `filename*` 可被 `unquote` 还原 |

> ⚠️ **这一条不是理论风险**：`candidate_name` 是 HR 在创建面试时自由填写的字段（`InterviewCreate`），没有任何字符限制。**报告导出是本项目第一处把用户输入放进 HTTP 头部的地方**——既有代码从未把用户输入写入头部（`Content-Disposition` 此前不存在）。

### 5.3 与前端打印 PDF 的分工（明确不重叠）

| 交付形态 | 实现位置 | 覆盖内容 | 本模块是否参与 |
|---|---|---|---|
| **DOCX** | **本模块**（后端生成） | HR 报告全文（文字 + 表格） | ✅ |
| **PDF** | **前端**（`window.print()` + `@media print`） | 报告页 + 准备助手页，**含雷达图** | ❌ 零参与 |
| 准备助手提纲的 DOCX | **不做** | — | ❌ |

> **为何准备助手不做 DOCX**：它是 HR 现场的对照工作稿，打印 PDF 足够；而 DOCX 的消费者是「需要留档 / 转发 / 二次编辑」的场景，那是**报告**的用途。让两个模块各写一份文档装配代码，成本高于收益。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| `format` 非 `docx` | `VALIDATION_ERROR` | 400 | 不支持的导出格式（`detail.fields`） |
| 面试不存在 | `NOT_FOUND` | 404 | 面试不存在（**既有**，经 `get_report`） |
| 面试不属于当前 HR | `FORBIDDEN` | 403 | 无权限访问该面试（**既有**） |
| 评估尚未完成（非 `evaluated`） | `BUSINESS_ERROR` | 409 | 评估尚未完成（**既有**） |
| `evaluated` 但报告行缺失 | `NOT_FOUND` | 404 | 报告不存在（**既有**） |
| **DOCX 装配失败** | `INTERNAL_ERROR` | 500 | 服务器内部错误 |
| 守卫角色不符（candidate 调用） | `FORBIDDEN` | 403 | 无权限执行此操作（module-16） |
| 无 token | `UNAUTHORIZED` | 401 | 未登录或登录已过期 |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。
>
> **装配失败**：本模块**不为它新增错误码，也不把它转成业务错误**。`export.py` 是纯函数、输入已校验过，失败只可能是编程错误或依赖异常——这类失败应当是 **500 + 服务端完整堆栈**（`main.py` 的 `handle_unexpected_error` 已覆盖），而不是伪装成「业务上不能导出」。
>
> **前端对 500 的处置**（写进 §4.1 的契约，由 module-23 实现）：提示「导出 DOCX 失败，可改用『导出 PDF』」——浏览器打印路径**不依赖后端**，因此在后端挂了的情况下仍然可用。**这是「两条导出路径」在设计上的实际价值**，不只是格式偏好。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `export.py` 装配（`test_evaluation_export.py`，**新增**）

**测试手法**：**round-trip**——把 `build_report_docx` 的输出用 `python-docx` 重新打开，再断言段落与表格内容。比按字节断言可读、可维护，且真正验证了「文件能被 Word 打开」。

| 测试 | 断言 |
|---|---|
| `test_returns_bytes_starting_with_zip_magic` | 返回 `bytes`，以 `PK` 开头（DOCX 是 zip 容器） |
| `test_output_opens_as_document` | `Document(BytesIO(content))` **不抛异常** |
| `test_contains_all_eight_sections` | 八个区块的标题文字均出现 |
| `test_info_table_rows` | 基本信息表含岗位名与候选人姓名 |
| `test_overall_score_formatted_one_decimal` | 总分出现且为 1 位小数（如 `7.5`） |
| `test_conclusion_present` | 综合结论全文出现 |
| `test_strengths_and_weaknesses_bulleted` | 每条优点 / 待改进各出现一次 |
| `test_empty_strengths_renders_placeholder` | `strengths=[]` → 出现「（无）」 |
| `test_question_table_has_header_and_rows` | 表头 6 列；行数 == `len(question_scores)` |
| `test_question_table_keeps_full_answer` | **长回答不被截断**（构造 5000 字回答，断言文档里能取到全文） |
| `test_null_answer_renders_placeholder` | `answer=None` → 出现「（未作答）」 |
| `test_question_rows_ordered_by_seq` | 行序与入参 `seq` 一致（**本模块不重排**） |
| `test_dimension_table_has_header_and_rows` | 表头 3 列；行数 == `len(dimension_scores)` |
| `test_dimension_order_preserved` | 行序 == 入参顺序（**不重排**） |
| `test_no_images` | **`document.inline_shapes` 为空**（证明没有雷达图 / 任何图片） |
| **`test_default_font_sets_east_asia`** | **文档默认样式的 `rPr.rFonts` 的 `w:eastAsia` 已设置**（§3.2 的关键断言） |
| `test_boundary_scores` | `0.0` 与 `10.0` 正常渲染 |
| `test_empty_tables_still_render_headers` | 两个明细表为空时**仍有表头** |
| `test_pure_function_no_side_effects` | 同一份 `ReportDetail` 调用两次 → 两次输出**都能被打开**（不依赖全局状态） |

> **`test_default_font_sets_east_asia` 是本模块最重要的一条**：漏设 `w:eastAsia` 时**在 LibreOffice / 部分 WPS 下中文才出问题**，本机用 Word 打开看起来正常。它属于「只有特定查看器才暴露」的故障，**没有测试就一定会被漏掉**。

### 7.2 端点（`test_evaluation.py` 增补）

| 测试 | 断言 |
|---|---|
| `test_export_returns_200_and_binary` | 200；`content-type` 为 DOCX 的 MIME |
| `test_export_content_disposition_is_attachment` | 含 `attachment` |
| `test_export_content_disposition_has_rfc5987_filename` | 含 `filename*=UTF-8''`，且 `unquote` 后含岗位名与候选人姓名 |
| `test_export_filename_sanitized` | `candidate_name = 'A"; \r\nB/C'` → 头部**不含** `"` / CR / LF / 裸 `/`；`filename*` 可解码 |
| `test_export_filename_length_capped` | 超长姓名 → 文件名中段不超 60 字符 |
| `test_export_default_format_is_docx` | 不带 `format` → 200 |
| `test_export_unknown_format_400` | `?format=pdf` → **400**（不静默当 docx） |
| `test_export_before_evaluation_409` | 状态非 `evaluated` → 409「评估尚未完成」 |
| `test_export_when_report_missing_404` | `evaluated` 但无报告行 → 404 |
| `test_export_other_hrs_interview_403` | hr_b 导 hr_a 的面试 → 403 |
| `test_export_missing_interview_404` | 不存在的 id → 404 |
| `test_export_rejects_candidate` | candidate token → 403 |
| `test_export_allows_admin` | admin **可以**导出（HR 侧守卫允许 admin，与既有 HR 端点一致——这是刻意的确认用例，防止有人把守卫误写成只允许 hr） |
| `test_export_rejects_anonymous` | 无 token → 401 |
| `test_export_body_matches_builder` | 端点返回体与直接调 `build_report_docx` 的结果**长度一致** |
| `test_export_does_not_persist_anything` | 调用前后 `report` / `question_score` 等表**行数不变**（PRD §4.12「不落库导出记录」） |
| `test_candidate_feedback_export_absent` | 不存在任何候选人可访问的导出端点（`/candidate/.../export` → 404） |

### 7.3 依赖与回归

| 测试 / 检查 | 断言 |
|---|---|
| `python -c "import docx"` | 可导入（证明依赖已按镜像装好） |
| 既有 `test_evaluation.py` / `test_evaluation_stream.py` 全部用例 | **零回归** |
| `test_architecture.py` 全部用例 | **零回归**（`export.py` 是新增文件，架构测试的 `ai`/`core` 参数化不涉及它；`evaluation` 的禁止依赖集合未变） |
| `pytest tests/ -q` | **全部通过** |

> ⚠️ **`export.py` 的导入约束**：它**只 import** `python-docx`、标准库、`app.evaluation.schemas.ReportDetail`。若被写成 import `app.interview` 或 `Session`，会立刻让 `test_no_reverse_dependency[evaluation]` 或分层测试变红——**这是好事，说明约束在生效**。

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-06 / module-14 已完成（`get_report` 与 `evaluated` 状态可用）。

### Task 21.1：依赖落地

- [ ] `requirements.txt` 新增 `python-docx>=1.1`
- [ ] **用镜像安装**：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple python-docx`
- [ ] 验证：`python -c "import docx; print(docx.__version__ if hasattr(docx,'__version__') else 'ok')"`
- [ ] `backend/README.md` 补「安装须走清华镜像」的说明（§3.4）
- [ ] 提交

### Task 21.2：`export.py` 骨架与中文字体

- [ ] 新建 `app/evaluation/export.py`，实现 `build_report_docx` 的骨架（内存 `BytesIO`）
- [ ] 实现 `_set_default_font`（**含 `w:eastAsia`**，§3.2）
- [ ] 写 §7.1 的前三条失败测试 + **`test_default_font_sets_east_asia`**
- [ ] 运行确认通过
- [ ] 提交

### Task 21.3：八个区块的装配

- [ ] 实现 `_add_info_table` / `_add_bullets` / `_add_question_table` / `_add_dimension_table`
- [ ] 写 §7.1 其余失败测试（**含「长回答不截断」「空列表写（无）」「无图片」「不重排」**）
- [ ] 运行确认通过
- [ ] 提交

### Task 21.4：service 与文件名消毒

- [ ] `service.py` 新增 `ReportExport` dataclass 与 `export_report`（§4.2、§5.1）
- [ ] 实现 `_build_filename` / `_sanitize_filename`（§5.2）
- [ ] 写失败测试：格式非法 → 400；文件名消毒（含 `"` / CR / LF / `/`）；限长；消毒后为空 → `report.docx`
- [ ] 运行确认通过
- [ ] 提交

### Task 21.5：端点与头部

- [ ] `router.py` 新增 `GET /{interview_id}/report/export`，实现 `_content_disposition`（§4.1、§5.2）
- [ ] 写 §7.2 全部失败测试（**含 `filename*=UTF-8''` 与注入用例**）
- [ ] 运行确认通过
- [ ] 提交

### Task 21.6：全量回归

- [ ] 写 `test_export_does_not_persist_anything` 与 `test_candidate_feedback_export_absent`
- [ ] 运行 `pytest tests/ -q`，**全部通过**
- [ ] 核对 `export.py` 的 import 只有标准库 + `python-docx` + `ReportDetail`
- [ ] 提交

---

## 9. 验收标准

- [ ] `requirements.txt` 含 `python-docx>=1.1`，且**已在镜像下装好并可 import**
- [ ] `backend/README.md` **写明了走镜像的安装命令**
- [ ] 新增 `app/evaluation/export.py`，**唯一对外函数** `build_report_docx(report) -> bytes`
- [ ] `export.py` **不接收 `Session` / `User`**，不读库、不写盘、不记日志
- [ ] 文档含**八个区块**：标题 / 基本信息 / 总分 / 综合结论 / 优点 / 待改进 / 逐题评分表 / 多维评分表
- [ ] 逐题表 6 列且**回答原文不截断**；`answer=None` 显示「（未作答）」
- [ ] 多维表 3 列；**两个明细表的行序均沿用入参顺序，本模块不重排**
- [ ] 分数统一 1 位小数；`0.0` / `10.0` 边界正常
- [ ] **文档默认样式的 `w:eastAsia` 已设置**（有测试断言）
- [ ] **文档不含任何图片**（`inline_shapes` 为空，有测试断言）
- [ ] `strengths` / `weaknesses` 为空时写「（无）」；明细表为空时仍出表头
- [ ] 端点 `GET /interviews/{id}/report/export` 返回 **200 + DOCX MIME + `attachment` 头**
- [ ] `Content-Disposition` 同时含 ASCII 回退名与 **`filename*=UTF-8''`**；中文名可被正确解码
- [ ] **`candidate_name` 中的 `"` / CR / LF / `/` 被消毒**，有注入用例断言
- [ ] 文件名中段**限长 60 字符**；消毒后为空 → `report.docx`
- [ ] `format` 缺省 `docx`；**非 `docx` → 400**（不静默回退）
- [ ] 非 `evaluated` → **409「评估尚未完成」**（复用既有文案）
- [ ] 他人面试 → 403；无报告 → 404；无 token → 401；candidate → 403
- [ ] **导出前后数据库行数不变**（不落库导出记录）
- [ ] **不存在任何候选人可访问的导出端点**
- [ ] **未提供任何后端 PDF 接口**；未引入除 `python-docx` 外的依赖
- [ ] 无数据库变更、无配置项、无新错误码；既有用例零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **漏设 `w:eastAsia` 会让中文在部分查看器下退化** | 显式设置，并加断言测试 | python-docx 的 `font.name` **只改 `w:ascii`**，中文字符走 `eastAsia` 分支。漏掉时**本机 Word 看起来正常**，只在 LibreOffice / 部分 WPS 下暴露——没有测试必然漏 |
| **`candidate_name` 是自由输入，要进 HTTP 头部** | 消毒 + RFC 5987 编码 + 注入用例 | 这是本项目**第一处把用户输入放进头部**的地方（此前无 `Content-Disposition`）。含 `"` / CRLF 会破坏或注入头部 |
| **文件名含中文不能直接放进 `filename=`** | 双写 `filename` + `filename*` | `filename*` 是现代浏览器认的标准写法，ASCII 回退保证老客户端也能存盘 |
| **唯一新依赖，且本机直连 PyPI 不通** | 装走清华镜像，并把命令写进 README | 已实测：直连超时 5 次、且索引不全时会把包解析到 2021 年的 `0.8.11`。**环境事实必须写进文档**，否则下次重踩 |
| **逐题表包含回答全文会让文档很长** | 不截断 | 回答是分数的**证据**；截断会让「HR 复核当初为什么给这个分」失去依据，而 DOCX 正是留档交付物。Word 自动换行，排版代价可接受 |
| **装配失败不转成业务错误** | 让它成为 500 | `export.py` 是纯函数、输入已校验；失败只可能是编程错误或依赖异常。伪装成业务错误会把「代码有 bug」说成「这份报告不能导出」 |
| **前端拿到 500 后怎么办** | 契约写明：提示改用「导出 PDF」 | 浏览器打印**不依赖后端**，在后端故障时仍可用。**这是两条导出路径的实际价值**，不只是格式偏好 |
| **`format` 参数只有一个取值还要留** | 保留，非 `docx` 报 400 | PRD §8 已定该 URL 形状；保留参数让加格式不必改路径（改路径会破坏前端与已发出的链接）。**静默回退会让调用方以为拿到了别的格式** |
| **不用 `StreamingResponse`** | 用 `Response` | 内容已在内存完整生成，**没有流可流**。`StreamingResponse` 是给「边读边发」用的（既有 SSE 才是那个场景） |
| **`ReportExport` 不放 `schemas.py`** | 放 `service.py` | `schemas.py` 承载 HTTP 请求 / 响应模型；`ReportExport` 含 `bytes`，无法作为 Pydantic 响应模型，是内部传递结构 |
| **`ReportExport` 用 dataclass 而非 tuple** | dataclass | 三个字段里两个是 `str`，元组会让 `(content, filename)` 与 `(filename, content)` 的笔误无声通过 |
| **准备助手不做 DOCX** | 只走前端打印 PDF | 它是 HR 的现场工作稿；DOCX 的消费者是「留档 / 转发 / 二次编辑」，那是报告的用途。两处各写一份装配代码，成本高于收益 |
| **不内嵌字体、不做字体缺失检测** | 两者都不做 | 目标是 Windows 单机 PC，宋体必然存在；检测逻辑在 Linux CI 上会永远报缺字体，变成噪声 |
| **不落库导出记录** | 不落 | PRD §4.12 明确。加了就要回答「谁在什么时候导了几次」的用途问题，而 PRD 未定义该需求 |
| **`export.py` 单独成文件** | 是 | 它是纯函数 + 技术细节（与 `stream.py` 同形态）；塞进 `service.py` 会让「评估编排」与「文档排版」两个无关关注点混在一处，且 `service.py` 已 320 行 |
| **不支持页眉页脚 / 页码** | 不做 | python-docx 无高层 API，需要手写 XML；PRD 未要求，收益不成比例 |
