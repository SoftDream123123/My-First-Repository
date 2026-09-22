# resume 上传解析 执行计划书（MVP-4 简历文件上传）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：resume **MVP-4 增量**（候选人上传 DOCX / PDF → 后端解析为纯文本 → 回填正文框）
**所属包**：`backend/app/resume/`（在既有包内**新增一个文件**，不新建 package）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§1.3（非目标：不保留原文件）、§2（新增依赖）、§4.10（简历管理）、§5.2（解析失败分支的边界）、§7（MVP-4 错误条目）、§8（候选人侧端点表）、§9（上传安全边界 + 依赖受控）、§10（测试策略）、§11（MVP-4 里程碑）
**前置依赖**：[module-17 resume](./2026-09-21-module-17-resume-plan.md)（本模块是它的增量，**不重复其任何内容**）
**本模块被谁依赖**：[module-26 候选人前端增量](./2026-09-22-module-26-candidate-frontend-plan.md)、[module-27 e2e](./2026-09-22-module-27-e2e-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **解析端点不落库、不落盘**：不建简历、不改简历、服务器上不留上传的文件（§4.10、§5.2）。这是本模块最重要的一条约束
- **不改表结构**：`resume` 表字段与 `backend/script.sql` 一字不动，**不写 alembic 迁移**（§4.10）
- **写入方仍只有候选人**；路由守卫 `require_roles("candidate")`，hr 与 admin 均不通行（§4.10）
- **解析出的文字不做截断**：超 20000 字符照样返回，由候选人自行精简（§4.10）
- **新增依赖仅两项**：`pypdf`、`python-multipart`；DOCX 复用既有 `python-docx`（§2）。安装**必须走清华镜像**
- **不新增错误码、不新增 HTTP 状态码**：四类失败一律 **400 `VALIDATION_ERROR`**（§7）
- **`resume` 仍不依赖任何业务模块**（§9、module-17 §1.3 的依赖方向不变）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.10）

| 子职责 | 内容 | PRD |
|---|---|---|
| 上传校验 | 扩展名白名单 + 文件头魔数复核 + 体积上限 | §4.10、§9 |
| 格式解析 | DOCX（段落 + 表格）、PDF（逐页文字层） | §4.10 |
| 文本归一化 | 统一换行、折叠连续空行、去首尾空白 | §4.10 |
| 失败表达 | 四类失败给出**可操作的中文文案**（提示改用粘贴） | §7 |
| 纯转换 | **只返回文本，不产生任何持久化副作用** | §5.2 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **保存原文件 / 提供「回看原件」** | PRD §1.3 明确列为非目标，并挪进 §11 的 V1.1。本模块把「文件去哪了」的答案定为「解析完即丢弃」 |
| **把解析结果直接建成简历** | PRD §4.10 要求回填后**由候选人确认**。端点保持无副作用，确认与保存走既有的 `POST/PUT /candidate/resumes` |
| **截断超长文本** | 与 module-17 §5.1「去首尾空白后判非空」「不静默截断」的既有约定冲突 |
| **OCR / 扫描件文字识别** | 会引入第二个重依赖（OCR 引擎）；PRD §4.10 把扫描件定为「提示改用粘贴」 |
| **`.doc`（97–2003 旧二进制格式）** | 需另外的库（如 antiword / libreoffice）；PRD §4.10 已明确不支持 |
| **结构化解析**（技能、年限、项目经历等字段） | PRD §4.10 未要求；module-17 §1.2 已排除 |
| **改动 `content` 的既有长度契约** | 20000 字符上限仍由 `POST/PUT` 的 service 层把关，本模块不重复实现 |
| **前端** | 属 [module-26](./2026-09-22-module-26-candidate-frontend-plan.md) |
| **端到端验证** | 属 [module-27](./2026-09-22-module-27-e2e-plan.md) |

### 1.3 依赖方向（保持不变）

```
resume.router ──→ resume.service ──→ resume.repository ──→ resume 表
                        │
                        └──→ resume.parser ──→ pypdf / python-docx（第三方，只读）

resume ✗→ interview / practice / position / question / evaluation / ai
```

> **`parser.py` 是 resume 包内的一个纯函数文件**，不依赖 `models` / `schemas` / `repository` / `service`，也不依赖任何业务模块。它只接受 `bytes` 与文件名，返回 `str`。这样它既能被 service 直接调，也能在单测里脱离数据库单独测。

---

## 2. 文件结构

**本模块新增**

| 文件 | 单一职责 |
|---|---|
| `backend/app/resume/parser.py` | 上传文件的校验与解析（纯函数，无 session、无 IO 落盘） |
| `backend/tests/test_resume_parser.py` | parser 单元测试（不经数据库、不经 HTTP） |

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/requirements.txt` | 新增 `pypdf>=5.0`、`python-multipart>=0.0.9`，并补镜像安装注释 | §2；`python-multipart` 缺失时 `UploadFile` 直接报错 |
| `backend/app/core/config.py` | 新增 `resume_upload_max_bytes` | §4.10 |
| `backend/.env.example` | 补 `RESUME_UPLOAD_MAX_BYTES` 一节（放在既有「简历（PRD §4.10）」一节内） | 与既有配置项文档习惯一致 |
| `backend/app/resume/schemas.py` | 新增 `ResumeParseResult` | §4.2 |
| `backend/app/resume/service.py` | 新增 `parse_uploaded_resume` | §4.3 |
| `backend/app/resume/router.py` | 新增 `POST /parse`，**声明位置必须在 `/{resume_id}` 那三条之前** | §4.1 的路由顺序 |
| `backend/tests/api/test_api_resume.py` | 新增该端点的用例（鉴权、四类失败、成功且不落库） | §10 |

> **`backend/script.sql` 不动、不写 alembic 迁移**：本模块零表结构变更（PRD §4.10）。这是本批次唯一一个「新增端点却不改库」的模块，执行时**不要"顺手"加字段**。
>
> **`backend/tests/test_architecture.py` 不需要改**：`test_five_layer_files_exist` 只断言那 5 个文件**存在**，不排斥额外文件；`parser.py` 不 import 任何业务模块，`test_no_reverse_dependency` 仍然绿。

---

## 3. 配置项

| 配置键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `RESUME_UPLOAD_MAX_BYTES` | int | `5242880`（5 MB） | 上传文件体积上限；超限 400（PRD §4.10） |

> **为何 5 MB**：简历 PDF 常见在 200 KB – 2 MB 区间；5 MB 给扫描件留了余量又不至于让一次请求把内存压垮。DOCX 解压后的展开体积另有独立上限（§5.3），**两者不是同一个数**。
>
> **为何进配置而不是写死在 parser 里**：与 `RESUME_CONTENT_MAX_LENGTH` 同理——它是**部署可调的量**，改它不该改代码。

---

## 4. 接口契约

### 4.1 对外 REST API

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/candidate/resumes/parse` | 上传 DOCX / PDF，解析为纯文本返回（**不落库**） | candidate | 200 |

**请求**：`multipart/form-data`，**唯一字段 `file`**（二进制）。不接收任何其他字段——尤其**不接收 `title` / `resume_id`**，避免把「解析」与「保存」两件事混在一个端点里。

> ⚠️ **路由声明顺序**：`POST /parse` 必须写在 `GET /{resume_id}` / `PUT /{resume_id}` / `DELETE /{resume_id}` **之前**。虽然本项目的 `/parse` 是 POST 而 `/{resume_id}` 那三条是 GET/PUT/DELETE（方法与路径都不撞），但顺序写错在日后加 `POST /{resume_id}` 类端点时会立刻演变成「`parse` 被当成 `resume_id` 解析」的 500。**按顺序写，不依赖方法不同来豁免。**

### 4.2 请求 / 响应结构

**`ResumeParseResult`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `content` | str | 解析出的纯文本全文（**不截断**） |

> **响应只有 `content` 一个字段**，刻意不加 `filename` / `char_count` / `page_count`：
> - `filename` 前端手里就有（`File.name`），回传是冗余；
> - `char_count` 前端 `content.length` 即得；
> - 页数/字数这类「解析统计」没有产品用途，加了就要为它写文档与测试。
>
> **失败不返回部分结果**：任何一类失败都返回 400 且**不返回已解析出的片段**。部分解析结果会让候选人误以为「这份文件就只有这些内容」。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `parse_uploaded_resume(data: bytes, filename: str) -> str` | 纯文本 | 体积校验 → 交给 `parser.parse_resume_file` → 返回文本（§5.1） |

> **service 层的方法刻意很薄**：它是「端点语义」与「解析算法」之间的接缝，承载体积校验（要读配置）与错误转译，算法本身全在 `parser.py`。这样 `parser.py` 能在不碰 `app.core.config` 单例的前提下被单测直接调用。

### 4.4 parser 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `parse_resume_file(data: bytes, filename: str) -> str` | 纯文本 | **纯函数**：无 session、不落盘、不读配置。校验与分发（§5.2） |
| `_parse_docx(data: bytes) -> str` | 纯文本 | 段落 + 表格（§5.4） |
| `_parse_pdf(data: bytes) -> str` | 纯文本 | 逐页文字层（§5.5） |
| `SUPPORTED_EXTENSIONS: tuple[str, ...]` | `(".docx", ".pdf")` | 供文案与校验共用，**单一事实来源** |

---

## 5. 业务流程设计

### 5.1 端点主流程

```
POST /candidate/resumes/parse
1. router：守卫 require_roles("candidate") → 非 candidate 一律 403
2. router：取 file 字段；缺失 → 400
3. router：data = file.file.read(limit + 1)      ← 见下方「为何 +1」
4. service.parse_uploaded_resume(data, file.filename)
     4.1 len(data) > limit           → 400「文件不能超过 5 MB」
     4.2 len(data) == 0              → 400「文件是空的」
     4.3 parser.parse_resume_file(data, filename)  → 文本
5. router：返回 ResumeParseResult(content=文本)
```

| 要点 | 说明 |
|---|---|
| **读 `limit + 1` 字节而非 `read()`** | 一次读满上限多一个字节即可判定「超限」，**不必把整个大文件读进内存**。这是本模块唯一一处真正的资源护栏 |
| **端点写成同步 `def`** | 全项目 router 均为同步 `def` + 同步 Session。这里**不引入 `async def`**——`UploadFile.file` 是同步可读的文件对象（Starlette 已把请求体缓冲到 `SpooledTemporaryFile`），同步读即可，与既有栈一致 |
| **`file.filename` 可能为 `None`** | 部分客户端不带文件名。取不到时按「扩展名未知」处理（400），**不抛 AttributeError** |
| **错误文案不出现文件名以外的用户输入** | 文案里可以带候选人自己的文件名（是他的输入，回显无风险），但**不得**回显原始异常、路径或库的内部结构（PRD §9） |

> ⚠️ **体积上限的真实效力边界（执行时不要误以为它是 DoS 防护）**：Starlette 在进入视图函数**之前**就已把整个请求体收完并缓冲到内存/临时文件，所以「读 `limit + 1`」省的是**我们的**内存，不是**服务器的**。真正的请求级上限要靠单机部署的进程参数或反向代理。**这一条必须写进 §7 的遗留项**，并由 module-26 在前端加一道 `file.size` 预检（超限则**根本不发请求**）来补足体验。

### 5.2 校验与分发

```
parse_resume_file(data, filename):
1. ext = 文件名最后一个 '.' 之后的部分，转小写
2. ext ∉ SUPPORTED_EXTENSIONS              → 400 类型不符
3. 魔数复核：
     ext == '.pdf'  → data[:5] == b'%PDF-'         否则 400
     ext == '.docx' → data[:4] == b'PK\x03\x04'    否则 400
4. 分发：'.docx' → _parse_docx(data)；'.pdf' → _parse_pdf(data)
5. 归一化（§5.6）
6. 结果为空或只有空白                     → 400 未提取到文字
```

| 要点 | 说明 |
|---|---|
| **魔数复核不是多余的** | 扩展名由客户端提供，改个名字就能绕过。PDF 的 `%PDF-` 与 DOCX 的 ZIP 容器头 `PK\x03\x04` 都是稳定特征，一行断言即可，成本极低（PRD §9 明确要求） |
| **`.docx` 与 `.doc` 必须分开判定** | `.doc` 是 OLE 复合文档，文件头是 `D0 CF 11 E0`，**既不是 ZIP 也不是白名单成员**。若只白名单扩展名而漏了魔数复核，`.doc` 改名 `.docx` 会走进 python-docx 并抛出难懂的库异常 |
| **区分「类型不符」与「文件损坏」两类文案** | 前者是「请上传 DOCX 或 PDF」，后者是「无法解析该文件」。文案不同，候选人能据此判断该换文件还是该换做法 |

### 5.3 DOCX 的展开体积护栏

```
_parse_docx(data):
前置：用 zipfile 打开，统计所有条目的 file_size 之和
      > DOCX_MAX_UNCOMPRESSED_BYTES（50 MB） → 400
      zipfile.BadZipFile                    → 400
```

| 要点 | 说明 |
|---|---|
| **为何要单独一道** | DOCX 本质是 ZIP，5 MB 的压缩包可以解出几个 GB（ZIP bomb）。字节上限拦不住它 |
| **为何 50 MB** | 正常简历的 DOCX 展开后通常在 1 MB 以下；50 MB 留了极大余量，正常文件不可能误伤 |
| **只统计、不解压** | 用 `ZipFile.infolist()` 读中央目录的 `file_size`，**不调用 `extractall`**，因此这道检查本身不吃内存 |

### 5.4 DOCX 解析

```
_parse_docx(data):
1. Document(BytesIO(data))               ← python-docx
2. 依文档顺序遍历 body 的子元素：
     w:p（段落）  → 取 paragraph.text，产出一行
     w:tbl（表格）→ 逐行逐格取单元格文本，同格内换行替换为空格，
                    同一行的各格用 '\t' 连接，产出一行
3. 返回行列表
```

| 要点 | 说明 |
|---|---|
| **必须取表格** | 简历里「教育经历」「工作经历」常做成表格。只取 `document.paragraphs` 会**整块丢掉**这些内容——这是本模块最容易漏、且漏了测试不易发现的一处（PRD §10 已把「表格内文字被提取」写进测试项） |
| **按 body 顺序遍历而非先段落后表格** | 先取完所有段落再取所有表格，会把表格内容整体挪到文末，段落与表格的相对位置错乱。用 [`docx` 的 body 子元素顺序遍历](https://python-docx.readthedocs.io/) 才能保持版序 |
| **不解析页眉页脚** | `section.header` / `footer` 在简历里通常是姓名或页码，取进来是噪声；且页码会污染文本。**此为刻意取舍，写进 §7 遗留项** |
| **不解析批注 / 修订痕迹** | 同上，属噪声来源；python-docx 默认也不暴露 |
| **不恢复粗体/字号等排版** | `content` 是纯文本字段，排版信息无处安放（PRD §4.10） |

### 5.5 PDF 解析

```
_parse_pdf(data):
1. reader = PdfReader(BytesIO(data))     ← pypdf
2. reader.is_encrypted 且无法用空密码解开 → 400「该 PDF 已加密」
3. 逐页 page.extract_text()，页与页之间用一个换行连接
4. 返回拼接结果
```

| 要点 | 说明 |
|---|---|
| **加密件先判再解析** | 直接 `extract_text()` 在加密件上会抛库异常；先判 `is_encrypted` 才能给出「该 PDF 已加密，请先解除密码保护」这种能照做的文案。**空密码加密在 PDF 里很常见**（很多导出工具默认加空密码），因此判定条件是「`is_encrypted` 且用空密码解不开」，而不是「`is_encrypted`」本身——否则会误伤一大批正常文件 |
| **扫描件靠「结果为空」倒推** | PDF 没有「这页是不是扫描件」的元数据。唯一可判的就是「逐页都取不到文字」。因此 §5.6 的空结果分支要**专门为扫描件写文案**：「未能从文件中提取到文字，它可能是扫描件或纯图片，请改为直接粘贴简历正文」 |
| **第三方库异常统一转 400** | pypdf 在损坏文件上会抛出多种异常类型（`PdfReadError` / `DependencyError` / 内建的 `ValueError` / `RecursionError` 等）。**这里刻意用宽 `except Exception`** 收口成 400，并在注释里写明理由：解析库的异常谱系不稳定，逐个枚举必然漏，而此处**兜底的安全性来自「不落库」**——宽捕获不会掩盖数据损坏，只会把「读不出来」如实告诉用户。**文案不带原始异常内容** |
| **页间不插分页符** | 简历文本是连续叙述，插 `---` 之类反而成为 AI 上下文里的噪声 |

### 5.6 文本归一化

| 步骤 | 做法 | 理由 |
|---|---|---|
| 换行统一 | `\r\n`、`\r` → `\n` | 前端 textarea 与后端都按 `\n` 处理，混入 `\r` 会带来肉眼不可见的差异 |
| 折叠空行 | 连续 ≥ 2 个空行 → 保留 1 个 | DOCX 与 PDF 抽取常产生成片的空段落（PDF 尤其：每行都是独立文本块）。不折叠会让候选人拿到一半是空行的正文 |
| 行尾空白 | 去掉每行尾部的空白 | PDF 抽取经常补出多余空格 |
| 整体 | 去首尾空白 | 与 module-17 §5.1 的既有约定一致 |

> **只做这四件事，不做重排**：不合并断行、不调换顺序、不删页眉页脚残留。任何「更聪明」的处理都会让系统偷偷改掉候选人的原文，而他看到的正文才是要被 AI 消费的内容——**他必须看到真实结果**。

---

## 6. 错误契约（PRD §7「MVP-4 新增」）

| 场景 | 状态码 | code | 文案要点 |
|---|---|---|---|
| `file` 字段缺失 | 400 | `VALIDATION_ERROR` | 「请选择要上传的文件」 |
| 文件为空（0 字节） | 400 | `VALIDATION_ERROR` | 「文件是空的」 |
| 扩展名不在白名单（含 `.doc`） | 400 | `VALIDATION_ERROR` | 点名**受支持的两种格式** |
| 魔数复核不符 | 400 | `VALIDATION_ERROR` | 与上一条同款——**不告诉上传方「你的文件头不对」**，那是在教人绕过 |
| 超过 `RESUME_UPLOAD_MAX_BYTES` | 400 | `VALIDATION_ERROR` | 给出实际上限（如「文件不能超过 5 MB」） |
| DOCX 展开体积超限 / `BadZipFile` | 400 | `VALIDATION_ERROR` | 「无法解析该文件」+ 提示改用粘贴 |
| PDF 已加密且空密码解不开 | 400 | `VALIDATION_ERROR` | 「该 PDF 已加密」+ 提示解除保护或改用粘贴 |
| 解析出空结果 / 只有空白 | 400 | `VALIDATION_ERROR` | 「可能是扫描件或纯图片」+ 提示改用粘贴 |

> **全部复用既有 `ValidationError`（400），不新增错误码、不新增状态码**（PRD §7 明确不新增 413）。本模块**不碰** `backend/app/core/exceptions.py`。
>
> **不使用 `detail.fields`**：`_field_error` 那套是给表单字段用的（前端会落到具体输入框下方）。上传的错误没有对应的输入框，**用普通 `ValidationError(message)`** 让前端弹 toast 即可（前端 `fieldErrors.fromServer` 见 `detail.fields` 不存在会返回 `false`，自动退回 toast，无需前端特判）。

---

## 7. 测试清单

`backend/tests/test_resume_parser.py`（纯 parser 单测，**不连库、不走 HTTP**）

| # | 用例 | 断言 |
|---|---|---|
| 1 | 正常 DOCX（段落） | 段落文字按序出现 |
| 2 | DOCX **含表格** | 表格内文字也被提取（PRD §10 指定项） |
| 3 | DOCX 段落与表格**交替** | 版序与原文一致 |
| 4 | 正常 PDF（有文字层） | 文字被提取 |
| 5 | `.doc` 扩展名 | 400 类型不符 |
| 6 | `.txt` / 无扩展名 / `filename=None` | 400，且**不抛 `AttributeError`** |
| 7 | `.docx` 扩展名但 PDF 内容（魔数不符） | 400 |
| 8 | 空字节 `b""` | 400「文件是空的」 |
| 9 | 损坏的 DOCX（随机字节 + `PK` 头） | 400，且**不泄露原始异常** |
| 10 | 损坏的 PDF（`%PDF-` 头 + 垃圾） | 400，同上 |
| 11 | 空密码加密的 PDF | **成功**解析（防误伤的回归线） |
| 12 | 非空密码加密的 PDF | 400「该 PDF 已加密」 |
| 13 | 无文字层的 PDF（空白页） | 400「可能是扫描件」 |
| 14 | 归一化：`\r\n` / 连续空行 / 行尾空格 | 归一化结果符合 §5.6 |
| 15 | DOCX 展开体积超限 | 400（构造一个高压缩比的小体积 DOCX） |

`backend/tests/api/test_api_resume.py`（端点层，新增）

| # | 用例 | 断言 |
|---|---|---|
| 16 | candidate 上传正常 DOCX | 200，`content` 非空 |
| 17 | **上传成功后库内简历数不变** | 与请求前一致（PRD §5.2「不落库」的**直接断言**） |
| 18 | hr token 调该端点 | 403 |
| 19 | 无 token | 401 |
| 20 | 缺 `file` 字段 | 400 |
| 21 | 超 `RESUME_UPLOAD_MAX_BYTES` | 400，文案含上限数值 |

> **测试用文件从哪来（本模块唯一的执行期风险）**：
> - **DOCX 无此问题**：`python-docx` 能**写**，在 fixture 里用 `Document()` 现造一个含段落与表格的 docx 到 `BytesIO`，**不引入任何二进制测试资产**。
> - **PDF 有**：`pypdf` 只能写结构、不能排版出文字。因此用例 4 / 11 / 12 / 13 需要一个**带文字层的 PDF 字节来源**。两条路，**优先第一条**：
>   1. 在测试里用一个**手写的最小 PDF 字节串**（单页、Helvetica、一行 `Tj`），约 500 字节的固定常量，放在 `test_resume_parser.py` 顶部作为 helper。加密与无文字层两种变体由 `pypdf` 的 writer 从它派生（`encrypt()` 加密码；`add_blank_page()` 造空页）。
>   2. 若手写 PDF 在 pypdf 上读取不稳定（不同版本对 `xref` 容错不同），退回**在 `backend/tests/fixtures/` 放一个几百字节的真实 PDF**，并从它派生两个变体。
>
> **执行时先试第 1 条，失败再退第 2 条，并在 commit message 里注明用了哪条**——这决定仓库里会不会多出二进制资产。

---

## 8. 与既有模块的接口影响

| 既有模块 | 是否受影响 | 说明 |
|---|---|---|
| `interview` / `practice` | **无** | 它们消费的是 `resume.content`（已存的纯文本）。上传只是**另一种产生 `content` 的方式**，对它们完全透明 |
| `evaluation` | **无** | 同上，报告与反馈读的是面试与作答，与简历来源无关 |
| `ai` | **无** | 本模块**不调任何 AI**。「按简历补题」与「按简历推荐」仍在 `interview` / `practice` 里发生，输入仍是 `content` 文本 |
| `resume` 既有五个端点 | **契约不变** | 长度上限、归属校验、删除保护全部原样。本模块**不修改** `create_resume` / `update_resume`（PRD §5.2 明确要求其错误契约不变） |
| `core` | 仅加一个配置键 | 不动 `exceptions.py`、不动 `deps.py` |

---

## 9. 遗留项与已知局限（交 module-27 汇总）

| # | 局限 | 性质 | 建议 |
|---|---|---|---|
| 1 | **体积上限拦不住「服务器已收完请求体」**：Starlette 在进视图前已缓冲整个请求体，`read(limit+1)` 省的是我们的内存，不是服务器的 | 单机部署下的已知边界 | 由 module-26 在前端加 `file.size` 预检（超限不发请求）作为体验层补足；诚实记入遗留 |
| 2 | **页眉页脚、批注、修订痕迹不进正文** | 刻意取舍（§5.4） | 若日后发现真实简历大量把关键信息放页眉（少见），再评估 |
| 3 | **扫描件不支持 OCR** | PRD §1.3 / §4.10 明确 | 文案已给出「改用粘贴」这一可操作出路 |
| 4 | **PDF 的分栏排版会被抽成断行交错** | pypdf 文字层抽取的固有限制 | 归一化**刻意不尝试修复**（§5.6）；候选人看到真实结果后自行整理 |
| 5 | **`.doc` 不支持** | PRD §4.10 明确 | 文案点名格式 |
| 6 | **上传文件不留存**：事后无法排查「某次解析为什么失败」 | PRD §1.3 的明确取舍 | 接受 |

---

## 10. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | 六个既有 resume 端点契约零变化 | `pytest backend/tests/test_resume.py backend/tests/api/test_api_resume.py` 原有用例全绿 |
| 2 | 上传解析成功后**库内简历数不变** | 用例 17 |
| 3 | DOCX 表格文字被提取 | 用例 2 |
| 4 | 四类失败全是 400 `VALIDATION_ERROR`，无新错误码 | 用例 5–15 |
| 5 | 空密码加密 PDF 不被误伤 | 用例 11 |
| 6 | hr / 未登录调该端点分别 403 / 401 | 用例 18、19 |
| 7 | `script.sql` 与 alembic 目录**零改动** | `git status` 确认 |
| 8 | 架构测试仍绿（`test_architecture.py` 无需改动） | `pytest backend/tests/test_architecture.py` |
| 9 | 依赖按清华镜像可装，`requirements.txt` 声明与 §2 一致 | 实机安装 |
