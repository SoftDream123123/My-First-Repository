# ai 模块执行计划书（MVP-3 简历匹配与面试前准备）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：ai（在既有 7 个能力之上新增 2 个：按简历匹配题目、生成面试前准备提纲）
**所属包**：`backend/app/ai/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.14（简历匹配补题）、§4.11（面试前准备助手）、§4.7（刷题按简历推荐）、§6（AI Provider 契约）、§7（降级）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-11 ai 既有能力](./2026-09-20-module-11-ai-plan.md)
**本模块被谁依赖**：[module-19 interview](./2026-09-21-module-19-interview-plan.md)、[module-20 practice](./2026-09-21-module-20-practice-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **`ai` 只接收原始值**（str / int / list / dataclass），**绝不接收 ORM 对象**——这是 `ai` 不依赖任何业务模块的前提（§3.3、`ai/base.py` 模块 docstring）
- `match_questions_by_resume` **只从传入的题库候选中挑选，不生成新题**（§6）
- 两个方法的 `resume_text` **均为可选语义**：`match_questions_by_resume` 未关联简历时**整体不参与**；`generate_interview_prep` 未关联简历时**仍可生成**（§6）
- 无 Key 时由 **Mock Provider 给出确定性结果**，保证可演示与可测试（§9）
- Mock **不允许任何随机性**：相同输入必须产生完全相同输出（`mock_provider.py` 模块 docstring）
- 真实 Provider **失败后抛 `AIProviderError`，绝不自动降级到 Mock**（`openai_provider.py` 模块 docstring）
- 准备助手产出三部分：**面试提纲 / 考察重点 / 问题预案**，一次生成即整批返回，**不做流式**（§4.11）
- **不引入任何新依赖**；**仍是单机 PC 端**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §6）

| 子职责 | 内容 | PRD |
|---|---|---|
| 按简历匹配题目 | 从传入的题库候选中按简历相关度挑选并排序，返回**题目 id + 匹配理由** | §4.14、§4.7 |
| 生成面试前准备提纲 | 产出面试提纲 / 考察重点 / 问题预案三部分 | §4.11 |
| Mock 实现 | 两个方法的**确定性**规则版本 | §9 |
| 真实实现 | 两个方法的 prompt 设计与**容错解析** | §6 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **取题库候选池** | 调用方（`interview` / `practice`）负责按岗位或筛选条件取出候选再传入。本模块**看不到数据库** |
| **把匹配结果写库** | `interview_question` 的追加、`seq` 续接、`source_snapshot='resume_match'` 全属 `interview`（module-19） |
| **决定匹配题数** | `count` 由调用方给出（PRD 的默认 3 属调用方配置，module-19 §3.3） |
| **为 prep 结果落库** | `interview_prep` 的读写与覆盖语义属 `interview`（module-19） |
| **判断简历是否存在 / 是否本人** | 属 `resume`（module-17）。本模块只接收已取出的 `resume_text` 字符串 |
| **`source_snapshot` 的取值常量** | `'resume_match'` 是 `interview_question` 的字段值，**属 `interview`**，不在本模块定义（§3.3） |
| **任何流式能力** | PRD §4.11 明确「一次生成即整批落库，不做流式」 |
| **Prompt 模板的持久化 / 可配置** | 与既有 7 个方法一致，模板内置在方法体内（module-11 §5.2） |

### 1.3 依赖方向

```
interview.service ──┐
practice.service  ──┴──→ ai.factory.get_provider() ──→ AIProvider（抽象）
                                                          ├── MockProvider
                                                          └── OpenAIProvider

ai ──→ core（单向）
ai ✗→ auth / position / question / resume / interview / evaluation / practice
```

> **本模块零新增依赖边。** 两个新方法仍只吃原始值与 dataclass，因此 `test_ai_depends_on_no_business_module` 自动覆盖新增代码——**只要新方法里没有 `from app.interview import ...`，约束就自动成立**。

---

## 2. 文件结构

| 文件 | 单一职责 | 本次改动 |
|---|---|---|
| `backend/app/ai/__init__.py` | 包标识 | 无 |
| `backend/app/ai/base.py` | 数据结构 + 抽象基类 + 常量 | **改**：新增 6 个 dataclass、2 个抽象方法、更新类 docstring |
| `backend/app/ai/mock_provider.py` | 规则驱动的确定性实现 | **改**：实现 2 个方法 + 新增 1 个私有相似度函数 + 模板常量 |
| `backend/app/ai/factory.py` | Provider 选择与缓存 | **无改动** |
| `backend/app/ai/openai_provider.py` | 大模型 API 实现 | **改**：实现 2 个方法 + 解析容错 |

**测试文件**

| 文件 | 本次改动 |
|---|---|
| `backend/tests/test_mock_provider.py` | **改**：新增 2 个测试类；**`test_mock_provider_implements_all_seven_methods` 改名并断言 7 → 9** |
| `backend/tests/test_openai_provider.py` | **改**：新增 2 个测试类（`MockTransport`，不打真实 API） |
| `backend/tests/test_ai_factory.py` | **无改动**（`test_mock_conforms_to_abstract` 断言的是「Mock 满足抽象」，自动跟随新方法） |

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| **`backend/app/ai/base.py:127`（类 docstring）** | 「七个方法覆盖两条业务线」→「**九个方法覆盖三条业务线**」，并补一行「简历驱动的匹配与准备」 | ⚠️ **docstring 不会因新增方法而自动更新**，是最容易静默过时的地方 |
| **`backend/tests/test_mock_provider.py:481-486`** | `test_mock_provider_implements_all_seven_methods` → `..._all_nine_methods`；断言 `== 7` → `== 9` | ⚠️ **硬编码断言**，不改则测试**直接失败**（这类失败是好失败——它逼你面对接口变更） |

> **本模块不碰数据库、不加迁移、不加配置项**：纯能力层变更。

---

## 3. 数据结构设计（契约）

### 3.1 新增 6 个 dataclass（`base.py`）

**`QuestionBrief` —— 题目的精简形态，两个新方法共用**

| 字段 | 类型 | 说明 |
|---|---|---|
| `question_id` | int | 题库题目 id；**匹配结果的回传键** |
| `content` | str | 题干 |
| `dimension` | str | 考察维度 |
| `category` | str | 分类 |

> **为什么两个方法共用一个 dataclass**：`match` 需要「id + 题干 + 维度 + 分类」来打分与回传 id；`prep` 需要「题干 + 维度」来生成考察意图。**后者的需求是前者的子集**，因此不另建一个只少两个字段的 `PrepQuestionInput`——重复的 dataclass 会让调用方写两次转换代码，而两个方法永远由同一批调用方（`interview` / `practice`）以同一份数据喂。
>
> **命名用中性词 `Brief` 而非 `Candidate`**：`Candidate` 在本项目里专指候选人（`candidate` 角色、`candidate_name`），用它做题库题目的名字会造成严重误读。

**`MatchedQuestion` —— 匹配结果**

| 字段 | 类型 | 说明 |
|---|---|---|
| `question_id` | int | **必须来自传入的候选池**；本层负责过滤掉池外的 id |
| `reason` | str | 匹配理由，落库到 `interview_question.match_reason` |

**`PrepOutlineStage` —— 提纲的一个阶段**

| 字段 | 类型 | 说明 |
|---|---|---|
| `seq` | int | 从 1 开始 |
| `phase` | str | 阶段名（如「能力考察」） |
| `duration_min` | int | 该阶段时长（分钟），恒 > 0 |
| `notes` | str | 该阶段的要点 |

**`PrepFocusPoint` / `PrepQuestionItem` / `InterviewPrepResult`**

| dataclass | 字段 | 说明 |
|---|---|---|
| `PrepFocusPoint` | `dimension: str`、`point: str`、`reason: str` | 考察重点：应验证什么能力项、为什么 |
| `PrepQuestionItem` | `question: str`、`intent: str`、`follow_ups: list[str]` | 问题预案：建议提问、考察意图、可追问方向 |
| `InterviewPrepResult` | `outline: list[PrepOutlineStage]`、`focus_points: list[PrepFocusPoint]`、`question_plan: list[PrepQuestionItem]` | 三部分整体返回 |

> **三部分用三个具名 dataclass，而不是 `dict[str, Any]`**：这三个结构会**原样序列化进 `interview_prep` 的三个 JSON 列**（module-19 §3.x），前端直接按字段名渲染。用 dict 会失去字段名的编译期约束，「`follow_ups` 写成 `followups`」这类错误要到前端才炸。dataclass → JSON 的映射是确定的，且与既有 `ReportResult` / `CandidateFeedbackResult` 同一手法。

### 3.2 新增 2 个抽象方法签名（`base.py` 的 `AIProvider`）

| 方法签名 | 返回 | 调用方 |
|---|---|---|
| `match_questions_by_resume(resume_text: str, position_name: str, jd: str, dims: list[str], candidates: list[QuestionBrief], count: int) -> list[MatchedQuestion]` | 匹配结果（按相关度降序） | `interview`（按简历补题）、`practice`（按简历推荐） |
| `generate_interview_prep(position_name: str, jd: str, dims: list[str], candidate_name: str, resume_text: str \| None, questions: list[QuestionBrief]) -> InterviewPrepResult` | 三部分准备提纲 | `interview`（准备助手） |

**与 PRD §6 参数形态的差异说明（不改变能力范围）**

| PRD §6 写法 | 本设计 | 原因 |
|---|---|---|
| `position` | `position_name: str` + `jd: str` | 与既有 `generate_questions(position_name, jd, ...)` **完全同构**。PRD 的 `position` 是概念值，既有约定已把它拆成两个原始值 |
| `candidate` | `candidate_name: str` | 同上；只取姓名用于称谓 |
| `bank_questions` / `questions` | `list[QuestionBrief]` | 统一形态（§3.1） |
| `resume_text`（可选） | `str`（match）/ `str \| None`（prep） | 见下方「**两种可选语义的差别**」 |

**⚠️ 两种「可选」语义完全不同，实现时不可混淆**

| 方法 | `resume_text` 为空时的行为 | 依据 |
|---|---|---|
| `match_questions_by_resume` | **抛 `AIProviderError`**——调用方本应判出「未关联简历」并**整条路都不调用**本方法 | PRD §6「未关联简历时 `match_questions_by_resume` 整体不参与（出题少一路、推荐走原筛选逻辑）」 |
| `generate_interview_prep` | **正常运行**，产出不含简历针对性的提纲 | PRD §4.11「输入：… + 简历（**可选**，未关联简历也能生成）」 |

> 这一条必须写死在文档里：两个方法的同名参数行为相反，是**最容易写错**的地方。执行者若把两者的 `resume_text` 空值处理「统一」掉，会分别破坏两条降级路径。

### 3.3 三个「不定义在本模块」的常量（**边界声明**）

| 概念 | 取值 | 定义位置 | 为什么不在 ai |
|---|---|---|---|
| `interview_question.source_snapshot = 'resume_match'` | `"resume_match"` | **`interview`** | 它是 `interview_question` 的字段值，与 AI 层的输出形状无关。本模块返回的 `MatchedQuestion` **不含 source**——写什么 source 是调用方的事 |
| 补题默认题数（PRD 的「默认 3」） | `3` | **`interview`** 配置项 | 是调用方的业务参数，本模块只接受 `count` |
| 候选池的取法（按岗位 / 按筛选） | — | **`interview` / `practice`** | 本模块看不到数据库（§1.2） |

> **`SOURCE_BANK` / `SOURCE_AI` 留在 ai 的原因与 `resume_match` 不同**：前两者是**题目自身的来源**（`question.source`），由 `generate_questions` 直接生产；`resume_match` 是**面试题目的来源快照**（`interview_question.source_snapshot`），由 `interview` 生产。**同名字段、不同去处**，因此不放在一起。

### 3.4 既有常量与约定的复用（不新增）

| 复用项 | 位置 | 用法 |
|---|---|---|
| `SCORE_MIN` / `SCORE_MAX` | `base.py` | 本次不涉及评分，**不使用** |
| `PASS_THRESHOLD` | `base.py` | 本次**不涉及判分**，不引入第二个阈值 |
| `_similarity`（bigram Jaccard） | `mock_provider.py` | **不复用**——见 §4.1 的理由 |
| `_coerce_dimension` | `openai_provider.py` | **复用**：`match` 与 `prep` 都要把模型返回的维度吸附到给定 `dims` |
| `_str_list` | `openai_provider.py` | **复用**：`follow_ups` 与 `focus_points` 的字符串数组清洗 |
| `_request_json` + 重试 | `openai_provider.py` | **复用**：两个新方法都走它，因此自动获得同一套重试与围栏剥离 |

---

## 4. Mock Provider 规则设计（对应 PRD §6「规则生成确定性结果」）

### 4.1 `match_questions_by_resume`

**前置失败（抛 `AIProviderError`）**

| 条件 | 消息 |
|---|---|
| `resume_text` 去空白后为空 | 「缺少简历内容，无法按简历匹配题目」 |
| `dims` 为空 | 「缺少评估维度，无法按简历匹配题目」 |

**短路返回（不抛错）**

| 条件 | 返回 | 理由 |
|---|---|---|
| `count <= 0` | `[]` | 与 `generate_questions` 一致的既有约定 |
| `candidates` 为空 | `[]` | 「题库里没有可匹配的题」是**正常业务状态**，不是错误——**与 `dims` 为空不同**（那是岗位配置缺失）。由调用方决定要不要报 409 |

**打分公式（确定性，无随机、无时间戳）**

```
对候选池中每个 c：
    dim_hit  = 1.0 若 c.dimension 是 resume_text 的子串，否则 0.0
    cat_hit  = 1.0 若 c.category  是 resume_text 的子串，否则 0.0
    overlap  = _resume_overlap(c.content, resume_text)        ← [0, 1]
    score    = 3.0 * dim_hit + 1.5 * cat_hit + 2.0 * overlap

稳定排序：score 降序，**同分按 question_id 升序**   ← 同分必须有确定次序
取前 count 条，逐条生成 reason
```

**`_resume_overlap` —— 新增的私有相似度函数（**刻意不复用 `_similarity`**）**

```
_resume_overlap(question_text, resume_text) = |A ∩ B| / |A|
    其中 A = _bigrams(question_text)（题干，短）
         B = _bigrams(resume_text)（简历，可达 2 万字）
      A 为空 → 0.0
```

| 决策 | 理由 |
|---|---|
| **不用既有的 `_similarity`（Jaccard）** | Jaccard 的分母是**并集**。简历 2 万字、题干几十字时，并集被简历完全主导，相似度会塌到 1e-3 量级——**任何阈值都失去分辨力**，等于这个信号不存在。刷题判分能用它，是因为参考答案与作答长度量级相当，简历匹配不是同一场景 |
| **用「题干二元组被简历覆盖的比例」** | 分母是题干自身的大小，量级稳定在 [0, 1]，语义清晰：「这道题的用词有多大比例出现在简历里」。题干 30 个二元组、命中 12 个 → 0.4，可解释、可设阈值 |
| **阈值 `_MATCH_OVERLAP_MIN = 0.3`** | 只用于 **reason 的措辞分档**，不参与排序（排序用连续分数）。因此阈值取值的敏感性低——它只影响文案是「有重合」还是「通用考察项」 |
| **复用 `_bigrams`** | 它是既有的、已测的切分函数，重写一份只会引入第二个中文切分口径 |

**`reason` 分档（确定性）**

| 条件（按顺序判） | reason |
|---|---|
| `dim_hit` 且 `overlap >= 0.3` | 「简历中体现了{dim}相关经历，且本题题干与其表述有重合，属于高相关题目。」 |
| `dim_hit` | 「简历中体现了{dim}相关经历，本题直接考察该维度。」 |
| `cat_hit` | 「简历中的{category}方向与本题一致。」 |
| `overlap >= 0.3` | 「本题题干与简历表述有一定重合。」 |
| 否则 | 「本题与岗位评估维度相关，作为通用考察项。」 |

> **全零分数时的行为**：排序退化为 `question_id` 升序，取 id 最小的 count 条，reason 一律走最后一档。这是**确定性**的（不依赖字典序、不依赖插入顺序），可作为测试基准。

### 4.2 `generate_interview_prep`

**前置失败（抛 `AIProviderError`）**

| 条件 | 消息 |
|---|---|
| `dims` 为空 | 「缺少评估维度，无法生成面试准备提纲」 |

**允许为空、不报错**：`resume_text`（走无简历分支）、`candidate_name`（用「候选人」兜底）、`questions`（问题预案全由维度生成）。

**产出规则**

`outline` —— 固定四阶段（总 45 分钟），仅 `notes` 随输入变化：

| seq | phase | duration_min | notes 随输入的变化 |
|---|---|---|---|
| 1 | 开场与自我介绍 | 5 | 含 `candidate_name`（空则「候选人」） |
| 2 | 经历核对 | 10 | **有简历** → 指向简历项目经历；**无简历** → 改为围绕岗位要求做开放式了解 |
| 3 | 能力考察 | 20 | 含 `'、'.join(dims)` |
| 4 | 候选人提问与收尾 | 10 | 固定文案 |

`focus_points` —— **每个维度一条**（按 `dims` 顺序，索引取模选模板），**有简历时额外追加一条「简历核对」**：

| 来源 | dimension | 说明 |
|---|---|---|
| 每个 `dim` | 该维度名 | `point` / `reason` 由模板按索引确定 |
| 简历追加项 | `"简历核对"` | 引用简历首 `_RESUME_SNIPPET_LEN = 40` 字，提示确认本人在项目中的实际贡献 |

`question_plan` —— 上限 `_PREP_MAX_QUESTIONS = 4`：

```
1. 先取传入的 questions（本场已有题目），逐条生成：
     question  = q.content
     intent    = 模板[索引] 填入 q.dimension
     follow_ups = 两个追问模板[索引]
2. 若不足 4 条，按 dims 循环补建议问题，直到 4 条或补满（dims 非空，故必然补满）
```

> **为什么先取已有题目再补**：本场题目是 HR 已经决定要问的，问题预案把它们纳入才「和这场面试对得上」。若只按维度生成建议题，产出会与本场题目脱节。补齐到 4 条保证短面试也有足够预案。
>
> **为什么不超 4 条**：45 分钟的提纲里塞 10 个问题预案没有可执行性。上限是产品判断，写在常量里便于调整。

**确定性自查**：以上全部规则只依赖入参（`position_name` / `dims` / `candidate_name` / `resume_text` 的**长度与内容判断** / `questions` 的顺序），**无随机、无时间戳、无字典序依赖**。

---

## 5. 真实 Provider 设计（`openai_provider.py` 增量）

### 5.1 调用形态

| 方法 | `_request_json` 参数 | temperature |
|---|---|---|
| `match_questions_by_resume` | `expect_list=True` | `0.2`（选题目要求稳定） |
| `generate_interview_prep` | `expect_list=False`（返回对象） | `0.3`（提纲需要一点组织自由度） |

两者自动复用 `_request_json` 的**重试 + 代码围栏剥离 + 子串提取**（`_parse_json`），无需新增解析基础设施。

### 5.2 Prompt 设计要素（不做模板持久化，内置于方法中）

**`match_questions_by_resume`**

| 要素 | 内容 |
|---|---|
| system | 资深面试官，负责**从已有题库中挑选**与候选人简历最相关的题目 |
| user 输入 | 岗位名 + JD + 评估维度列表 + **简历全文** + 候选题清单（**带 `question_id`**）+ `count` |
| 硬约束（必须写入 prompt） | ① `question_id` **必须**来自给定清单，**不得编造、不得改写**；② 至多返回 `count` 条；③ 每条给出 `reason`，说明与简历中的**哪段经历**相关 |
| 输出 | JSON 数组：`[{"question_id": 数值, "reason": "字符串"}]` |
| 收尾 | 「只输出 JSON，不要任何解释文字。」 |

**`generate_interview_prep`**

| 要素 | 内容 |
|---|---|
| system | 资深面试官/招聘专家，为一场**即将开始**的面试准备提纲 |
| user 输入 | 岗位名 + JD + 评估维度 + 候选人姓名 + **简历（无则明确写「（候选人未提供简历）」）** + 本场已有题目（无则「（无）」） |
| 输出结构（必须在 prompt 中列全字段） | `{"outline": [{"seq","phase","duration_min","notes"}], "focus_points": [{"dimension","point","reason"}], "question_plan": [{"question","intent","follow_ups":["..."]}]}` |
| 附加要求 | ① `dimension` **必须**来自给定维度列表；② `duration_min` 为正整数；③ `follow_ups` 为字符串数组；④ 有简历时，`focus_points` 至少有一条与简历经历直接相关 |
| 收尾 | 「只输出 JSON，不要任何解释文字。」 |

> **无简历时必须在 prompt 里显式写「（候选人未提供简历）」**，而不是省略该段：省略会让模型自行猜测候选人有简历，产出「针对简历中提到的…」这类**引用不存在内容**的提纲。显式写「未提供」把事实交给模型，它才会改走无简历的写法。

### 5.3 响应解析容错

| 方法 | 容错规则 |
|---|---|
| `match_questions_by_resume` | ① 非 `list` → 抛错；② 逐项要求 `dict`，否则跳过；③ `question_id` 用 `int()` 转换，失败则跳过；④ **不在候选池 id 集合内 → 跳过（绝不伪造）**；⑤ 重复 id → 只保留首次；⑥ 截断到 `count` 条；⑦ `reason` 去空白，空则填「与岗位评估维度相关」 |
| `generate_interview_prep` | ① 非 `dict` → 抛错；② **三部分任一解析后为空 → 抛 `AIProviderError`**；③ `duration_min` 非正整数 → 回落 `5`；④ `seq` 缺失 → 按数组下标补 1..n；⑤ `dimension` 经 `_coerce_dimension` 吸附，失败则该条跳过；⑥ `follow_ups` 用 `_str_list` 清洗 |

**⚠️ 「三部分任一为空就抛错」的取舍**

| 方案 | 结果 |
|---|---|
| **本设计：任一为空 → 抛错** | 一场准备提纲缺了「考察重点」或「问题预案」就不具备可用性，而重试成本只有一次点击。**宁可整批失败，也不要交付半份看起来像坏了的东西** |
| 备选：允许部分为空并落库 | 前端会渲染出三块里空两块的面板，HR 无法判断「是 AI 没生成还是本来就该空」。且落库后需要额外的「部分成功」状态表达，PRD §4.11 没有这个概念 |

`match` 的**空结果与解析失败要区分开**：

| 情形 | 行为 |
|---|---|
| 模型返回**空数组** | 返回 `[]`——「确实没有相关题目」是正当结论，由调用方报「无匹配题目」 |
| 模型返回**非空数组但所有 id 都无效** | 抛 `AIProviderError`——这是**输出不合格**，不是「无匹配」。静默返 `[]` 会把 AI 故障伪装成正常结论 |

> 这两个分支的区分是刻意的：**「没有」和「坏了」必须能被区分**，否则线上只会看到「匹配不出来」，无法定位。

### 5.4 失败与重试

沿用既有 `_request_json`：重试 `AI_MAX_RETRIES + 1` 次（网络失败与解析失败共用同一计数），仍失败抛 `AIProviderError`，**不自动降级到 Mock**。降级决策权在调用方（module-19 §5.x / module-20 §5.x）。

### 5.5 「只挑不生成」的落实（PRD §6）

| 层面 | 保证方式 |
|---|---|
| Prompt | 明确「从给定清单中挑选」，并要求 id 来自清单 |
| 解析 | **池外 id 一律丢弃**——即使模型返回了一个不存在的 id，它也不会进入结果 |
| 数据结构 | `MatchedQuestion` **只有 `question_id` 与 `reason`，没有题面字段**——即使模型编造了题面，也无处安放 |

> **第三层是结构性的**：前两层是「检查」，第三层是「无从表达」。新题要进入结果，必须先在题库里存在并被调用方放进候选池。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | 行为 |
|---|---|
| `match` 的 `resume_text` 为空 | 抛 `AIProviderError`（调用方本应不调用，见 §3.2） |
| `match` / `prep` 的 `dims` 为空 | 抛 `AIProviderError` |
| `match` 的 `count <= 0` | 返回 `[]`（不抛错） |
| `match` 的候选池为空 | 返回 `[]`（不抛错，由调用方决定是否报业务错误） |
| `prep` 的 `resume_text` / `candidate_name` / `questions` 为空 | **正常执行**（§4.2） |
| 真实 Provider 网络 / 解析失败 | 重试后抛 `AIProviderError` |
| `match` 返回的 id 全部无效 | 抛 `AIProviderError`（§5.3） |
| `prep` 三部分任一为空 | 抛 `AIProviderError`（§5.3） |

> **本模块不定义任何 HTTP 状态码、不新增错误码**——`ai` 是被调用的能力层，无对外端点。HTTP 语义由调用方决定（PRD §7 的 409 等均由 `interview` / `practice` 抛出）。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 Mock：`match_questions_by_resume`（增补 `test_mock_provider.py`）

| 测试 | 断言 |
|---|---|
| `test_match_same_input_same_output` | 连续调用两次 → 结果**完全相等**（确定性的核心断言） |
| `test_match_blank_resume_raises` | 空 / 纯空白简历 → `AIProviderError` |
| `test_match_empty_dims_raises` | `dims=[]` → `AIProviderError` |
| `test_match_count_zero_returns_empty` | `count=0` → `[]`，**不抛错** |
| `test_match_empty_candidates_returns_empty` | 候选池空 → `[]`，**不抛错** |
| `test_match_dimension_hit_ranks_first` | 简历含「专业能力」，两题分别属「专业能力」「沟通能力」→ 前者排第一 |
| `test_match_respects_count` | 池 10 题、`count=3` → 返回 3 条 |
| `test_match_ids_all_from_pool` | 返回的每个 `question_id` **都在候选池内** |
| `test_match_tie_break_by_question_id` | 构造完全同分的两题 → 结果按 `question_id` **升序** |
| `test_match_reason_mentions_dimension_when_hit` | 维度命中时 reason 含该维度名 |
| `test_match_all_zero_scores_is_deterministic` | 简历与所有题都无交集 → 结果等于「按 id 升序的前 count 条」，reason 为通用文案 |
| `test_match_overlap_uses_question_denominator` | 长简历 + 题干用词被覆盖 → `_resume_overlap` 显著大于 **0**（证明没有误用 Jaccard，见 §4.1） |

> **最后一条是本模块最重要的一条测试**：若执行者「顺手复用」`_similarity`（Jaccard），该值会塌到 1e-3 量级、断言失败。它把「用对分母」这个非显然的设计决策钉住。

### 7.2 Mock：`generate_interview_prep`（增补）

| 测试 | 断言 |
|---|---|
| `test_prep_same_input_same_output` | 连续两次调用结果完全相等 |
| `test_prep_empty_dims_raises` | `dims=[]` → `AIProviderError` |
| `test_prep_without_resume_ok` | `resume_text=None` → 正常返回三部分非空 |
| `test_prep_without_resume_has_no_resume_focus` | 无简历时 `focus_points` **不含** `dimension == "简历核对"` |
| `test_prep_with_resume_adds_resume_focus` | 有简历时**含** `"简历核对"` 条目，且 reason 含简历片段 |
| `test_prep_without_candidate_name_uses_default` | `candidate_name=""` → 正常返回（不抛错） |
| `test_prep_outline_total_duration` | `outline` 四阶段、`duration_min` 合计 == 45，`seq` 为 1..4 |
| `test_prep_focus_points_cover_all_dims` | `focus_points` 覆盖 `dims` 中每个维度（在有简历时多一条） |
| `test_prep_question_plan_uses_existing_questions_first` | 传入 2 道本场题 → `question_plan` 前两条的 `question` 等于它们的题干 |
| `test_prep_question_plan_pads_to_max` | 传入 0 道题 → `question_plan` 长度为 4，且全部由 `dims` 生成 |
| `test_prep_question_plan_capped` | 传入 10 道题 → 长度仍为 **4** |
| `test_prep_without_questions_ok` | `questions=[]` → 正常返回三部分非空 |
| `test_prep_follow_ups_are_non_empty_lists` | 每条 `follow_ups` 非空且元素非空串 |

### 7.3 真实 Provider（增补 `test_openai_provider.py`，**不打真实 API**）

| 测试 | 断言 |
|---|---|
| `test_openai_match_parses_valid_response` | `MockTransport` 返回合法数组 → 解析出正确的 id 与 reason |
| `test_openai_match_drops_unknown_ids` | 返回含**池外 id** 的数组 → 该条被丢弃，其余保留 |
| `test_openai_match_dedupes_ids` | 同一 id 出现两次 → 只保留一条 |
| `test_openai_match_all_ids_invalid_raises` | 非空数组但 id 全无效 → **抛 `AIProviderError`**（§5.3） |
| `test_openai_match_empty_array_returns_empty` | 空数组 → `[]`，**不抛错** |
| `test_openai_match_truncates_to_count` | 返回条数超 `count` → 截断 |
| `test_openai_match_strips_code_fence` | 返回被 ``` 包裹的 JSON → 正常解析 |
| `test_openai_prep_parses_valid_response` | 合法对象 → 三部分字段与类型正确 |
| `test_openai_prep_empty_section_raises` | `outline` 为空数组 → **抛 `AIProviderError`** |
| `test_openai_prep_invalid_duration_falls_back` | `duration_min` 为 `"十分钟"` / `0` / 负数 → 回落 `5` |
| `test_openai_prep_seq_filled_when_missing` | `seq` 缺失 → 按顺序补 1..n |
| `test_openai_prep_coerces_dimension` | 模型返回的维度为给定维度的子串 → 被吸附到正确维度 |
| `test_openai_prep_follow_ups_sanitized` | `follow_ups` 含非字符串 / 空串 → 清洗后只留非空字符串 |
| `test_openai_prep_non_dict_raises` | 返回数组而非对象 → 抛 `AIProviderError` |

### 7.4 抽象契约与既有回归

| 测试 | 断言 |
|---|---|
| `test_mock_provider_implements_all_nine_methods`（**改名 + 改断言**） | `len(AIProvider.__abstractmethods__) == 9`；`MockProvider.__abstractmethods__` 为空 |
| `test_mock_provider_is_ai_provider`（既有） | 仍通过 |
| `test_mock_conforms_to_abstract`（既有，`test_ai_factory.py`） | 仍通过——它断言「Mock 满足抽象」，自动跟随新方法 |
| `test_ai_depends_on_no_business_module`（既有，参数化于 `ai/*.py`） | **自动覆盖改动后的三个文件**，且必须仍全绿——这是「新方法没引入业务依赖」的唯一机械保证 |
| 既有 7 个方法的全部用例 | **零回归**（本次不改它们的行为） |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-11（既有 7 个方法）已完成。
> **本模块无数据库、无配置、无端点**，因此任务数比业务模块少。

### Task 18.1：数据结构与抽象方法声明

- [ ] `base.py` 新增 6 个 dataclass（`QuestionBrief` / `MatchedQuestion` / `PrepOutlineStage` / `PrepFocusPoint` / `PrepQuestionItem` / `InterviewPrepResult`，见 §3.1）
- [ ] `base.py` 的 `AIProvider` 新增 2 个抽象方法（§3.2）
- [ ] **更新 `base.py:127` 的类 docstring**：「七个方法覆盖两条业务线」→「九个方法覆盖三条业务线」
- [ ] **改 `test_mock_provider.py:481-486`**：测试改名 + 断言 `7 → 9`
- [ ] 运行 `pytest tests/test_mock_provider.py -q`，确认**因 Mock 缺实现而失败**（预期失败）
- [ ] 提交

### Task 18.2：Mock —— `match_questions_by_resume`

- [ ] 新增 `_resume_overlap` 与 `_MATCH_OVERLAP_MIN`（§4.1）
- [ ] 实现打分、稳定排序、reason 分档
- [ ] 写 §7.1 全部失败测试（**含「两次调用结果相同」「同分按 id 升序」「overlap 未被 Jaccard 化」**）
- [ ] 运行确认通过
- [ ] 提交

### Task 18.3：Mock —— `generate_interview_prep`

- [ ] 实现四阶段 outline、按维度 focus_points（有简历时追加「简历核对」）、问题预案（先本场题后补足到 4）
- [ ] 写 §7.2 全部失败测试（**含「无简历也能生成」「有/无简历的 focus_points 差异」「预案上限 4」**）
- [ ] 运行确认通过
- [ ] 提交

### Task 18.4：真实 Provider

- [ ] 实现两个方法的 prompt（§5.2）与容错解析（§5.3）
- [ ] 写 §7.3 全部失败测试（**含「池外 id 丢弃」「全无效抛错」「空数组返空」「三部分任一为空抛错」**）
- [ ] 运行确认通过
- [ ] 提交

### Task 18.5：契约与全量回归

- [ ] 运行 `pytest tests/test_mock_provider.py tests/test_openai_provider.py tests/test_ai_factory.py -q`
- [ ] 运行 `pytest tests/test_architecture.py -q`，确认 `test_ai_depends_on_no_business_module` 覆盖新代码且全绿
- [ ] 运行 `pytest tests/ -q`，**全部通过**（证明既有 7 个方法零回归）
- [ ] 提交

---

## 9. 验收标准

- [ ] `AIProvider` 有 **9 个**抽象方法；`test_mock_provider_implements_all_nine_methods` 断言 `== 9`
- [ ] **`base.py` 的类 docstring 已从「七个方法 / 两条业务线」更新为「九个方法 / 三条业务线」**
- [ ] 6 个新 dataclass 定义齐全（`QuestionBrief` / `MatchedQuestion` / `PrepOutlineStage` / `PrepFocusPoint` / `PrepQuestionItem` / `InterviewPrepResult`）
- [ ] `ai` 的顶层导入**仍只有 `core`**（架构测试全绿）；两个新方法**不接收任何 ORM 对象**
- [ ] `match_questions_by_resume` 的返回 id **恒来自传入候选池**，池外 id 被丢弃
- [ ] 「模型返回空数组」返回 `[]`，「非空数组但 id 全无效」抛 `AIProviderError`——**两分支可区分**
- [ ] `_resume_overlap` 用**题干作分母**，未被实现为 Jaccard；有测试钉住
- [ ] `match` 在 `resume_text` 为空时**抛错**；`prep` 在 `resume_text` 为空时**正常生成**——两者行为相反且各有测试
- [ ] Mock 两个方法**连续两次调用结果完全一致**
- [ ] `match` 同分时按 `question_id` 升序（确定性）
- [ ] `prep` 三部分**均非空**；无简历时**不含**「简历核对」条目，有简历时**含**且有简历片段
- [ ] `prep` 的 `outline` 为四阶段、合计 45 分钟；`question_plan` 上限 **4** 条且**优先使用本场已有题目**
- [ ] `prep` 在真实 Provider 下三部分任一为空 → 抛 `AIProviderError`
- [ ] **未引入任何新依赖、未新增配置项、未新增错误码、无数据库改动**
- [ ] 既有 7 个方法的用例**零回归**

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **`AIProvider` 方法数被硬断言为 7** | 本次改为 9，并改名测试 | `test_mock_provider.py:485` 直接断言 `__abstractmethods__` 长度。不改则测试红——这是**有益的失败**，它强制接口变更被显式承认而不是悄悄发生 |
| **`base.py` 的 docstring 会静默过时** | 在 Task 18.1 里显式列为一步 | docstring 不参与测试，没人改它也不会红。这类「文档与事实漂移」只能靠计划书钉住 |
| **复用 `_similarity`（Jaccard）会毁掉简历匹配信号** | 新增 `_resume_overlap`，改用题干作分母 | 简历 2 万字主导并集，Jaccard 塌到 1e-3，阈值失去意义。刷题判分能用是因为两者长度量级相当——**同一函数不该在两个量级差 1000 倍的场景里复用** |
| **两个方法的 `resume_text` 空值行为相反** | `match` 抛错、`prep` 正常执行，并在 §3.2 用表格写死 | PRD §6 与 §4.11 的要求本就不同。若实现者「统一」处理，会分别破坏两条降级路径 |
| **`prep` 三部分任一为空即整批失败** | 抛错，允许部分为空反而更糟 | 缺「考察重点」的提纲不可用；前端渲染三块空两块的界面无法解释。重试成本只有一次点击 |
| **「空结果」与「解析失败」必须可区分** | 空数组返 `[]`；非空但 id 全无效则抛错 | 静默返 `[]` 会把 AI 故障伪装成「无匹配题目」，线上只剩「匹配不出来」这一种症状，无法定位 |
| **`QuestionBrief` 一个 dataclass 服务两个方法** | 共用，不建第二份 | `prep` 的需求是 `match` 的子集；两份 dataclass 会让同一批调用方写两遍转换代码 |
| **`QuestionBrief` 不叫 `CandidateQuestion`** | 用中性名 | `Candidate` 在本项目专指候选人，会造成严重误读 |
| **`'resume_match'` 常量不放 `ai`** | 放 `interview` | 它是 `interview_question.source_snapshot` 的取值，与 AI 层输出无关。`SOURCE_BANK` / `SOURCE_AI` 属 `question.source`，去处不同故不合并 |
| **`MatchedQuestion` 不含题面字段** | 结构上只留 `question_id` + `reason` | 让「编造新题」在**结构上无从表达**，而非仅靠 prompt 与解析两层检查 |
| **Mock 的 `outline` 时长固定 45 分钟** | 硬编码在模板里 | Mock 的职责是确定性与可演示，不是拟真。真实 Provider 由模型按岗位自定 |
| **`question_plan` 上限 4 条** | 常量 `_PREP_MAX_QUESTIONS = 4` | 45 分钟提纲里塞 10 个问题预案没有可执行性。产品判断，写成常量便于调整 |
| **无简历时 prompt 里显式写「（候选人未提供简历）」** | 写入 prompt，不省略该段 | 省略会让模型自行假设有简历，产出「针对简历中提到的…」这类**引用不存在内容**的提纲 |
| **不新增配置项** | `count` 由调用方给，其余为常量 | 本模块没有需要运维调整的旋钮；把「补题默认 3」放在 `interview` 才能和该模块的其他配置放在一起 |
