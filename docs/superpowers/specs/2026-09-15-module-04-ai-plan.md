# ai 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：ai（AI Provider 抽象与实现）
**所属包**：`backend/app/ai/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§6（AI Provider 接口契约）、§3.3（依赖方向）、§7（AI 调用失败处理）
**前置依赖**：core（[module-00](./2026-09-15-module-00-core-plan.md)）

> **MVP-2 增量（2026-09-20）**：`AIProvider` 新增三个抽象方法 —— `generate_reference_answer`、`grade_practice_answer`、`generate_candidate_feedback`（共 7 个方法），并新增全项目唯一的判分阈值常量 `PASS_THRESHOLD = 6.5`。本文档的 §3.2、§10 已按增量同步修正；**增量部分的完整契约（含 Mock 确定性规则、真实 Provider prompt、测试点、以及需同步修改的测试替身）以 [module-11 ai 刷题判分与候选人反馈](./2026-09-20-module-11-ai-plan.md) 为准**。

---

## Global Constraints（全局约束，摘自 PRD）

- 后端分层：**router → service → repository → MySQL**（§2、§3.2）
- 每个模块独立 Python package（§2、§3.3）
- **AI 能力通过抽象接口接入**：`ai` 包对外暴露抽象接口，被 `interview` / `evaluation` 调用（§6）
- **真实 Provider 与 Mock Provider 可配置切换，代码不写死**（§6）
- **Mock Provider：规则生成确定性结果，用于无 Key 演示与测试**（§6、§9）
- **AI 调用失败**：重试 1 次 → 仍失败则评估任务标记失败、状态回退 `completed`，可重新触发；**不阻塞其他功能**（§7）
- 评分统一 **0–10 分制**（§4.5）
- 统一响应格式 `{code, message, detail}`（§7）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §6）

| 子职责 | 内容 |
|---|---|
| 能力契约 | 定义 AI 的四个能力接口及其输入输出数据结构（PRD §6） |
| Mock 实现 | 基于规则的**确定性**实现，用于无 Key 演示与自动化测试（PRD §6） |
| 真实实现 | 调用大模型 API 的实现（PRD §6） |
| 选择机制 | 按配置返回具体实现的工厂（PRD §6「通过配置项选择」） |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **注册 HTTP 路由** | PRD §6 将其定位为被 `interview` / `evaluation` 调用的**能力包**，无对外端点 |
| **访问数据库** | Provider 是**纯函数式**能力，不持有 Session、不读写任何表。落库是 interview / evaluation 的职责（PRD §3.2 分层） |
| **依赖任何业务模块** | PRD §3.3 给出的 `ai` 依赖列为「—」。见 §3.3「传原始值」约束 |
| **Prompt 模板持久化** | Prompt 内置于实现中，MVP 不做可配置 Prompt 管理 |
| **token 计数与成本核算** | 不在 PRD 范围 |
| **结果缓存** | 不在 PRD 范围 |

### 1.3 依赖方向（对应 PRD §3.3，**`ai` 的依赖列为空**）

```
interview.service ──┐
                    ├──→ ai.factory.get_provider() ──→ AIProvider（抽象）
evaluation.service ─┘                                     ├── MockProvider
                                                          └── OpenAIProvider
                                                              └── httpx（外部 API）

ai ──→ core.exceptions（AIProviderError）
ai ✗→ 任何业务模块（position / question / interview / evaluation）
业务模块 ✓→ ai
```

**关键约束**：`ai` 处在依赖图的最底层，与 `core` 平级但彼此独立。这让 `ai` 可以被任意模块安全调用，也让 **Mock 实现可以在完全不启动数据库的情况下被单测**（PRD §9 要求的可测试性）。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/ai/__init__.py` | 包标识 |
| `backend/app/ai/base.py` | `AIProvider` 抽象基类 + 四个返回数据结构 + `QAPair` 输入结构 |
| `backend/app/ai/mock_provider.py` | **确定性**规则实现（PRD §6） |
| `backend/app/ai/openai_provider.py` | 真实 Provider：httpx + Prompt 构造 + 响应解析 + 重试（PRD §6、§7） |
| `backend/app/ai/factory.py` | `get_provider()`：按配置返回实现并缓存单例（PRD §6） |

**测试文件**：`backend/tests/test_mock_provider.py`、`backend/tests/test_ai_factory.py`、`backend/tests/test_openai_provider.py`

> **文件划分说明**：本模块保持四个源文件，`base.py` 同时承载抽象方法与返回数据结构。理由：数据结构即接口契约的一部分，分开放置会让「改接口」变成跨文件操作，反而增加遗漏风险。

---

## 3. 接口契约（对应 PRD §6）

### 3.1 数据结构（**全项目对 AI 能力的唯一数据契约**）

**`QAPair`**（输入结构，承载一道题的维度、题干与回答）

| 字段 | 类型 | 说明 |
|---|---|---|
| `dimension` | str | 该题考察的维度 |
| `question` | str | 题干 |
| `answer` | str \| None | 候选人回答；**未作答时为 `None`** |

**`GeneratedQuestion`**（`generate_questions` 的输出元素）

| 字段 | 类型 | 约束 |
|---|---|---|
| `content` | str | 题干，非空 |
| `dimension` | str | **必须属于传入的 `dims`** |
| `difficulty` | str | `easy` \| `medium` \| `hard` |
| `category` | str | 缺省 `"通用"` |
| `tags` | list[str] | 缺省 `[]` |
| `source` | str | **恒为 `"ai"`**（对应 PRD §5.2 的 `source` 字段） |

**`QuestionScoreResult`**（`evaluate_answer` 的输出）

| 字段 | 类型 | 约束 |
|---|---|---|
| `score` | float | **0.0–10.0**，保留 1 位小数（PRD §4.5） |
| `comment` | str | 评语，非空 |

**`DimensionScoreResult`**（`evaluate_dimensions` 的输出元素）

| 字段 | 类型 | 约束 |
|---|---|---|
| `dimension` | str | 必须属于传入的 `dims` |
| `score` | float | 0.0–10.0，保留 1 位小数 |
| `comment` | str | 评语，非空 |

**`ReportResult`**（`summarize_report` 的输出，对应 PRD §5.2 的 `report` 实体）

| 字段 | 类型 | 约束 |
|---|---|---|
| `overall_score` | float | 0.0–10.0，保留 1 位小数 |
| `conclusion` | str | 综合结论段落（PRD §4.5「综合结论」） |
| `strengths` | list[str] | 优势条目；**不可为空列表** |
| `weaknesses` | list[str] | 待改进条目；**不可为空列表** |

> **`strengths` / `weaknesses` 为何用列表而非段落文本**：报告页需要按条目渲染（序号 / 图标），结构化列表比在前端按换行符切分更可靠。落库时存为 JSON 列（对应 PRD §5.2 的 `report` 字段）。

### 3.2 抽象基类方法签名（对应 PRD §6 的接口；**MVP-2 起共 7 个方法**）

| 方法签名 | 返回 | PRD §6 对应 |
|---|---|---|
| `generate_questions(position_name: str, jd: str, dims: list[str], existing_contents: list[str], count: int) -> list[GeneratedQuestion]` | 列表 | 出题接口 |
| `evaluate_answer(dimension: str, question: str, answer: str \| None) -> QuestionScoreResult` | 结果 | 单题打分 + 评语 |
| `evaluate_dimensions(dims: list[str], qa_pairs: list[QAPair]) -> list[DimensionScoreResult]` | 列表 | 综合多维打分 + 评语 |
| `summarize_report(dims: list[str], dimension_scores: list[DimensionScoreResult], question_scores: list[QuestionScoreResult]) -> ReportResult` | 结果 | 汇总总分/结论/优点/待改进 |

**MVP-2 新增的三个方法**（完整契约见 [module-11 §3](./2026-09-20-module-11-ai-plan.md)）

| 方法签名 | 返回 | PRD §6 对应 |
|---|---|---|
| `generate_reference_answer(question_type: str, content: str, options: list[str], dimension: str) -> ReferenceAnswerResult` | 结果 | 补参考答案（§4.3） |
| `grade_practice_answer(question_type: str, content: str, reference_answer: str, user_answer: str) -> PracticeGradeResult` | 结果 | 刷题判分 + 解析（§4.7） |
| `generate_candidate_feedback(level: str, overall_score: float, strengths: list[str], weaknesses: list[str], dimension_scores: list[DimensionScoreResult]) -> CandidateFeedbackResult` | 结果 | 候选人脱敏反馈（§4.9）。⚠️ **入参不含报告结论**（2026-09-21 修正）：它含招聘方的去留判断，不给才是结构上的保证 |

> ⚠️ **新增抽象方法会打断既有测试替身**：`backend/tests/test_interview.py` 中的 `FailingProvider` 直接继承 `AIProvider`，必须补齐三个方法，否则既有用例将因无法实例化而集体失败。其余替身（`PartialDimensionProvider` 继承自 `MockProvider`、`FailingProvider`/`GatedProvider` 为普通类）经核实不受影响。清单见 module-11 §2。

### 3.3 与 PRD §6 参数形态的差异说明（**不改变能力范围**）

| PRD §6 签名 | 本设计签名 | 差异原因 |
|---|---|---|
| `generate_questions(position, dims, bank_questions, count)` | `generate_questions(position_name, jd, dims, existing_contents, count)` | ① 传**原始值**而非 ORM 对象，满足 PRD §3.3「`ai` 依赖为空」；② 拆出 `jd`——它是出题的核心输入（PRD §5.3 ①）；③ `bank_questions` 收窄为 `existing_contents`（只需题干用于去重） |
| `evaluate_answer(question, answer)` | `evaluate_answer(dimension, question, answer)` | 增加 `dimension`，让单题评语能围绕维度展开 |
| `evaluate_dimensions(answers, dims)` | `evaluate_dimensions(dims, qa_pairs)` | 参数顺序调整为「先声明维度」；`answers` 提升为 `qa_pairs`（含维度与题干——评分需要上下文，只有答案无法评） |
| `summarize_report(all_scores, dims)` | `summarize_report(dims, dimension_scores, question_scores)` | 拆开 `all_scores`：汇总需要**区分**维度分与逐题分（前者定结论，后者做明细引用） |

**PRD §6 的能力清单（四个方法、两个实现、可配置切换）完全保留**，上述仅为参数形态调整。

**MVP-2 的三个新方法沿用同一手法**：PRD §6 写作 `generate_reference_answer(question)` / `grade_practice_answer(question, user_answer)` / `generate_candidate_feedback(report, level)`，本设计一律替换为原始值参数（逐一对照见 [module-11 §3.4](./2026-09-20-module-11-ai-plan.md)），原因与本节相同。

### 3.4 「传原始值」的设计约束（**本模块最重要的边界规则**）

| 禁止 | 允许 |
|---|---|
| `generate_questions(position: Position, ...)` | `generate_questions(position_name: str, jd: str, ...)` |
| 在 `ai` 中 `from app.position.models import Position` | `ai` 中**不出现任何业务模块 import** |

**理由**

| 论点 | 说明 |
|---|---|
| 依赖方向 | 若 `ai` 接收 ORM 对象，`ai → position`、`ai → interview` 的依赖会立即出现，违背 PRD §3.3 中 `ai` 依赖为空的约定 |
| 可测性 | Mock Provider 的测试**无需建库、无需构造 ORM 实例**，传入字符串即可（PRD §9） |
| 可替换性 | 真实 Provider 要把输入序列化成 Prompt，本来也只需要字符串 |

### 3.5 工厂契约（对应 PRD §6「通过配置项选择使用哪个 Provider」）

| 签名 | 行为 |
|---|---|
| `get_provider() -> AIProvider` | 读 `settings.PROVIDER_NAME`：`"mock"` → `MockProvider()`；`"openai"` → `OpenAIProvider()`；**其他值 → 抛配置错误（fail fast）** |
| `reset_provider_cache() -> None` | 清空单例缓存，**供测试切换实现使用** |

**设计要点**

- Provider 实例**无状态**，工厂内部缓存单例，避免每次调用重新构造（真实 Provider 可复用 httpx client）。
- `OPENAI` 模式下若 `OPENAI_API_KEY` 为空 → **构造时即报错**，而非等到第一次调用才失败。

---

## 4. Mock Provider 规则设计（对应 PRD §6「规则生成确定性结果」）

> **核心要求**：**相同输入必须产生完全相同输出**。不允许任何随机性、时间戳、哈希随机化、字典序依赖。这是 Mock 能作为**测试基准**（PRD §10）的前提。

### 4.1 `generate_questions`

| 步骤 | 规则 |
|---|---|
| 维度分配 | 第 `i` 题（`i` 从 0 起）使用 `dims[i % len(dims)]` |
| 题干生成 | 按 `i % 3` 循环套用三个模板（见下表），填入 `position_name` 与 `dimension` |
| 难度 | 按 `i % 3` 循环取 `easy` → `medium` → `hard` |
| `category` | 恒为 `"通用"` |
| `tags` | `[dimension]` |
| `source` | 恒为 `"ai"` |
| 边界 | `count <= 0` → 返回空列表；`dims` 为空 → 抛 `AIProviderError`（无维度无法出题） |
| `existing_contents` 去重 | 若生成的题干与已有题干完全相同，追加「（变体N）」后缀直至不冲突，`N` 从 1 递增（确定性） |

**题干模板表**（`{position}` = 岗位名，`{dim}` = 维度）

| 序号 | 模板 |
|---|---|
| 1 | `关于{dim}：请描述一次你在{position}相关工作中遇到的具体挑战，以及你的处理方式。` |
| 2 | `关于{dim}：如果让你从零开始改进{position}岗位的一项关键流程，你会怎么做？` |
| 3 | `关于{dim}：请举例说明你如何衡量自己在{dim}方面的表现。` |

### 4.2 `evaluate_answer`

| 条件 | 基础分 |
|---|---|
| `answer` 为 `None`、空串或仅空白 | **0.0**（评语「未作答」） |
| 长度 < 20 | **3.0** |
| 20 ≤ 长度 < 100 | **5.0** |
| 100 ≤ 长度 < 300 | **7.0** |
| 长度 ≥ 300 | **8.5** |

**具体化加分**（在基础分上叠加）

| 标记 | 命中一次 |
|---|---|
| 含数字（正则 `\d`） | +0.5 |
| 含 `%` 或 `百分比` | +0.5 |
| 含 `项目` 或 `案例` | +0.5 |
| 含 `例如` 或 `比如` | +0.5 |

- 加分总和**上限 +1.5**
- 最终结果 **clamp 到 [0.0, 10.0]**（PRD §4.5 的 0–10 分制），保留 1 位小数
- 长度按 **strip 后的字符数**计算

**评语模板**（按最终分数分档，`{dim}` = 维度）

| 分档 | 评语 |
|---|---|
| 0.0 | `未作答，{dim}维度无法评估。` |
| 0.1–4.9 | `回答较简略，尚未体现出{dim}方面的具体经验。` |
| 5.0–7.9 | `回答基本切题，在{dim}方面有一定体现，建议补充更多细节与量化结果。` |
| 8.0–10.0 | `回答详实，{dim}方面有清晰的具体事例支撑，表达有条理。` |

### 4.3 `evaluate_dimensions`

| 规则 | 说明 |
|---|---|
| 聚合方式 | 对每个 `dim`，取 `qa_pairs` 中 `dimension == dim` 的**全部单题分**求算术平均 |
| 无对应题目 | `score = 0.0`，评语 `该维度在本次面试中无对应题目。` |
| 保留精度 | 1 位小数 |
| 返回顺序 | **与传入 `dims` 顺序完全一致**（保证雷达图轴序稳定） |

**评语模板**（`{dim}` = 维度）

| 分档 | 评语 |
|---|---|
| 0.0 | `该维度在本次面试中无对应题目。` |
| 0.1–4.9 | `{dim}维度表现偏弱，建议在后续轮次中重点考察。` |
| 5.0–7.9 | `{dim}维度表现中等，基本达到岗位要求。` |
| 8.0–10.0 | `{dim}维度表现突出，是本次面试的加分项。` |

### 4.4 `summarize_report`

| 字段 | 规则 |
|---|---|
| `overall_score` | `dimension_scores` 中所有分数的算术平均，保留 1 位小数；列表为空 → `0.0` |
| `conclusion` | 按 `overall_score` 分档取模板（见下表） |
| `strengths` | `score >= 6.5` 的维度，条目格式 `f"{dim}（{score}）：表现较好"`；**为空时填 `["本次面试暂无明显优势维度"]`** |
| `weaknesses` | `score < 6.5` 的维度，条目格式 `f"{dim}（{score}）：有待提升"`；**为空时填 `["本次面试暂无明显薄弱维度"]`** |

**结论模板**

| `overall_score` | `conclusion` |
|---|---|
| 0.0 | `本次面试缺少有效作答，无法形成评估结论。` |
| 0.1–3.9 | `整体表现未达预期，建议暂不推进。` |
| 4.0–5.9 | `整体表现一般，建议针对薄弱维度追加考察。` |
| 6.0–7.9 | `整体表现良好，建议结合岗位要求综合评估。` |
| 8.0–10.0 | `整体表现优秀，建议进入下一轮。` |

> `dimension_scores` 为空列表的情况（岗位未定义维度，理论上被 position 校验阻止）**必须有确定行为，不得抛异常**。

---

## 5. 真实 Provider 设计（`openai_provider.py`）

### 5.1 调用形态

| 项 | 设计 |
|---|---|
| HTTP 客户端 | `httpx`，超时取 `settings.AI_TIMEOUT_SECONDS` |
| 接口 | Chat Completions 兼容接口（`{base_url}/chat/completions`） |
| 认证 | `Authorization: Bearer {OPENAI_API_KEY}` |
| 模型 | `settings.OPENAI_MODEL` |
| 温度 | **出题用较高温度（如 0.7）以保证多样性；评分与汇总用低温度（如 0.2）以保证稳定** |

### 5.2 Prompt 设计要素（不做模板持久化，内置于方法中）

| 方法 | Prompt 必须包含 |
|---|---|
| `generate_questions` | 岗位名、JD 全文、评估维度列表、**已有题干**（明确要求「不得与以下题目重复」）、需生成的数量、每题的字段要求（题干/维度/难度）、**要求输出 JSON 数组**、要求 `dimension` 只能取给定维度之一 |
| `evaluate_answer` | 维度、题干、候选人回答、**评分区间 0–10**、评分应参考「具体性、相关性、深度」、要求输出单个 JSON 对象（`score`、`comment`） |
| `evaluate_dimensions` | 维度列表、该维度下的问答对、要求逐维度输出、要求输出 JSON 数组 |
| `summarize_report` | 维度分列表、逐题分列表、要求输出 JSON 对象（`overall_score`、`conclusion`、`strengths`、`weaknesses`），并明确 `strengths` / `weaknesses` 为**字符串数组** |

### 5.3 响应解析容错

| 情况 | 处理 |
|---|---|
| 响应被 markdown 代码围栏包裹 | 剥离 ```json / ``` 围栏后再解析 |
| 响应前后有解释性文字 | 提取**首个** `{` 到**最后一个** `}`（或 `[` 到 `]`）的子串再解析 |
| 解析后 `score` 越界 | clamp 到 [0.0, 10.0] |
| 解析后 `dimension` 不在给定维度中 | **映射到最接近的给定维度**；若无从判断则丢弃该条（`evaluate_dimensions` 中该维度按 0.0 处理） |
| `strengths` / `weaknesses` 为空数组 | 填入与 Mock 相同的占位条目，**保证契约一致** |
| JSON 解析彻底失败 | 计入失败，触发重试 |

### 5.4 失败与重试（对应 PRD §7）

| 失败类型 | 处理 |
|---|---|
| 连接失败 / 超时 | 重试 |
| HTTP 4xx / 5xx | 重试 |
| JSON 解析失败 | 重试 |
| 重试次数 | `settings.AI_MAX_RETRIES`（默认 **1**，即最多尝试 2 次——PRD §7「重试 1 次」） |
| 重试后仍失败 | **抛 `AIProviderError`**（502），由调用方决定业务影响 |

### 5.5 ⚠️ 不自动降级到 Mock 的设计决策

PRD §7 规定「AI 调用失败：重试 1 次 → 仍失败则**评估任务标记失败、状态回退 `completed`，可重新触发**」。据此，真实 Provider 失败时**不**自动回退到 MockProvider：

| 论点 | 说明 |
|---|---|
| **符合 PRD §7** | PRD 明确要求「标记失败 + 回退状态 + 可重新触发」，而非「静默降级继续跑」 |
| 语义误导 | 静默降级会让用户以为看到的是 AI 评估结果，实际是规则模板输出，**评分毫无参考价值** |
| 掩盖故障 | 运维侧无法感知真实 Provider 已不可用 |
| 责任清晰 | 失败就失败，由上层（interview / evaluation）明确告知用户并允许重试 |

Mock 仅在 `PROVIDER_NAME=mock` 时**显式**启用。

### 5.6 ⚠️ 「不阻塞其他功能」的落实（**PRD §7 的另一个要求**）

PRD §7 要求 AI 失败「**不阻塞其他功能**」。本设计据此要求：

| 约束 | 落实方式 |
|---|---|
| `ai` 不持有全局锁 / 不阻塞事件循环 | 真实 Provider 用 httpx 调用；失败时立即抛异常，不做长时间内部重试或排队 |
| 失败影响面限于当次调用 | `AIProviderError` 只向调用方冒泡，`ai` 不写任何全局状态 |
| 出题失败只影响该次面试创建 | interview 整体回滚该次创建（见 interview 模块） |
| 评估失败只影响该次评估 | evaluation 状态回退 `completed`，**用户的其他面试不受影响**（见 evaluation 模块） |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | 异常 | code | HTTP |
|---|---|---|---|
| 真实 Provider 重试后仍失败 | `AIProviderError` | `AI_PROVIDER_ERROR` | 502 |
| `PROVIDER_NAME` 取值非法 | 启动期配置错误 | — | 服务启动失败（fail fast） |
| `openai` 模式下缺 `OPENAI_API_KEY` | 构造期 `AIProviderError` | `AI_PROVIDER_ERROR` | 502 |
| `generate_questions` 传入空 `dims` | `AIProviderError` | `AI_PROVIDER_ERROR` | 502 |

> **异常冒泡后的处理**：`AIProviderError` 由调用方（interview / evaluation）的 service 捕获并决定业务影响。**`ai` 模块只负责抛出，不做业务决策**——这是分层的要求（PRD §3.2）。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 本模块测试的最大特点

**不需要数据库、不需要 TestClient**，纯函数调用即可。这是「`ai` 不依赖业务模块」（§3.4）这一约束带来的直接收益，也是 PRD §10「service 层注入 mock Provider 测业务逻辑」的基础。

### 7.2 `test_mock_provider.py`

**出题**

| 测试 | 断言 |
|---|---|
| `test_generate_returns_exact_count` | `count=3` → 返回 3 条 |
| `test_generate_count_zero` | `count=0` → 空列表 |
| `test_generate_count_negative` | `count=-1` → 空列表 |
| `test_generate_empty_dims_raises` | `dims=[]` → `AIProviderError` |
| `test_generate_dimensions_cycled` | `dims=[A,B]`、`count=5` → 维度依次为 A,B,A,B,A |
| `test_generate_source_always_ai` | 所有条目 `source == "ai"` |
| `test_generate_difficulty_cycled` | 依次 `easy, medium, hard, easy, ...` |
| `test_generate_deterministic` | **同参数调用两次，结果完全相等** |
| `test_generate_avoids_existing_contents` | `existing_contents` 含会撞车的题干 → 生成结果与其不重复 |
| `test_generate_dims_never_empty` | 每条 `dimension ∈ dims` |

**逐题评分**

| 测试 | 断言 |
|---|---|
| `test_evaluate_none_answer_scores_zero` | `answer=None` → `score == 0.0` |
| `test_evaluate_empty_answer_scores_zero` | `answer=""` → `0.0` |
| `test_evaluate_whitespace_answer_scores_zero` | `answer="   \n "` → `0.0` |
| `test_evaluate_length_tiers` | 各档长度（10 / 50 / 150 / 400 字符）分别得 3.0 / 5.0 / 7.0 / 8.5（无加分标记时） |
| `test_evaluate_bonus_capped` | 同时命中四类标记 → 加分不超过 +1.5 |
| `test_evaluate_clamped_to_ten` | 强行构造高分场景 → **不超过 10.0** |
| `test_evaluate_score_in_zero_to_ten` | 结果始终落在 [0, 10]（PRD §4.5） |
| `test_evaluate_one_decimal_place` | 结果保留 1 位小数 |
| `test_evaluate_comment_by_tier` | 各分档评语符合模板 |
| `test_evaluate_deterministic` | 同输入两次结果相等 |

**多维评分**

| 测试 | 断言 |
|---|---|
| `test_dimensions_covers_all_input_dims` | 返回项覆盖传入的**全部**维度 |
| `test_dimensions_order_matches_input` | **返回顺序与 `dims` 一致** |
| `test_dimensions_average` | 某维度两题分别 5.0 / 7.0 → 该维度 6.0 |
| `test_dimensions_no_question_scores_zero` | 某维度无对应题目 → 0.0 + 指定评语 |
| `test_dimensions_one_decimal_place` | 保留 1 位小数 |

**汇总报告**

| 测试 | 断言 |
|---|---|
| `test_report_four_fields_present` | **四个字段齐全且非空** |
| `test_report_overall_is_average` | 三个维度 6.0/8.0/10.0 → `overall_score == 8.0` |
| `test_report_overall_in_range` | 结果落在 [0, 10] |
| `test_report_empty_dimension_scores` | 空列表 → `overall_score == 0.0`，**不抛异常** |
| `test_report_strengths_threshold` | 仅 ≥ 6.5 的维度进入 `strengths` |
| `test_report_weaknesses_threshold` | 仅 < 6.5 的维度进入 `weaknesses` |
| `test_report_strengths_not_empty` | 全部维度都 < 6.5 → `strengths` 为**占位条目，不是空列表** |
| `test_report_weaknesses_not_empty` | 全部维度都 ≥ 6.5 → `weaknesses` 为**占位条目，不是空列表** |
| `test_report_conclusion_by_tier` | 各分档结论文本符合模板 |

### 7.3 `test_ai_factory.py`（对应 PRD §6「配置项切换」）

| 测试 | 断言 |
|---|---|
| `test_factory_returns_mock_by_default` | 默认配置 → `MockProvider` 实例 |
| `test_factory_returns_openai_when_configured` | `PROVIDER_NAME=openai` + 有 Key → `OpenAIProvider` 实例 |
| `test_factory_invalid_name_raises` | `PROVIDER_NAME=bogus` → **抛配置错误（fail fast）** |
| `test_factory_openai_without_key_raises` | `PROVIDER_NAME=openai` 且无 Key → **构造期即报错** |
| `test_factory_caches_instance` | 两次调用返回**同一对象** |
| `test_reset_cache` | `reset_provider_cache()` 后返回新对象 |
| `test_mock_provider_conforms_to_abstract` | `MockProvider` 是 `AIProvider` 的实例（**契约一致性**） |
| `test_openai_provider_conforms_to_abstract` | `OpenAIProvider` 是 `AIProvider` 的实例 |

### 7.4 `test_openai_provider.py`（**不打真实 API**）

| 测试 | 断言 |
|---|---|
| `test_strips_markdown_fence` | 响应被 ```json 包裹 → 正确解析 |
| `test_extracts_json_from_prose` | 响应前后有解释文字 → 提取 JSON 成功 |
| `test_clamps_out_of_range_score` | 返回 `score: 15` → clamp 为 10.0 |
| `test_empty_strengths_gets_placeholder` | 模型返回空数组 → 填入占位条目 |
| `test_retries_on_failure_then_raises` | 两次都失败 → 抛 `AIProviderError` |
| `test_retries_once_then_succeeds` | 第一次失败、第二次成功 → 返回结果，调用计数为 2 |
| `test_timeout_raises_provider_error` | 超时 → `AIProviderError` |

> 全部用 **mock 的 httpx 响应**构造，测试套件**不依赖网络与 API Key**。

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 4.1：数据结构与抽象基类

- [ ] 定义 `QAPair`、`GeneratedQuestion`、`QuestionScoreResult`、`DimensionScoreResult`、`ReportResult`（§3.1 全字段）
- [ ] 定义 `AIProvider` 抽象基类与 §3.2 的四个抽象方法（方法体仅 `raise NotImplementedError`）
- [ ] 写测试：抽象类**不可直接实例化**；四个方法均被声明为抽象
- [ ] 运行确认通过
- [ ] 提交

### Task 4.2：Mock 出题

- [ ] 写 §7.2 中出题相关的失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.generate_questions`（§4.1 规则）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.3：Mock 逐题评分

- [ ] 写 §7.2 中逐题评分相关的失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.evaluate_answer`（§4.2 规则）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.4：Mock 多维评分

- [ ] 写 §7.2 中多维评分相关的失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.evaluate_dimensions`（§4.3 规则）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.5：Mock 汇总报告

- [ ] 写 §7.2 中汇总报告相关的失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.summarize_report`（§4.4 规则，**含空列表兜底与占位条目**）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.6：工厂与配置校验

- [ ] 写 §7.3 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `get_provider()` 与 `reset_provider_cache()`（含缓存、非法值 fail fast、缺 Key 报错）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.7：真实 Provider

- [ ] 实现 `OpenAIProvider` 构造（校验 Key、建 httpx client、超时配置）
- [ ] 实现四个方法的 Prompt 构造（§5.2 要素）
- [ ] 实现响应解析容错（§5.3：剥离围栏、提取 JSON、clamp、空数组兜底）
- [ ] 实现重试逻辑（§5.4）
- [ ] 写 §7.4 全部失败测试（**用 mock 的 httpx 响应，不打真实 API**）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.8：全量回归

- [ ] 运行 ai 全部测试
- [ ] 运行 core 测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] `AIProvider` 为抽象基类，**四个方法齐备**（PRD §6）
- [ ] **`MockProvider` 与 `OpenAIProvider` 均为 `AIProvider` 的实例**（契约一致）
- [ ] `MockProvider` 满足「同输入同输出」：所有方法均有确定性测试
- [ ] `MockProvider` 出题：数量准确、维度按 `dims` 循环、难度循环、`source` 恒为 `ai`
- [ ] `MockProvider` 评分：空/空白回答得 0.0；长度分档正确；加分上限 +1.5；结果 **clamp 到 [0,10]** 且保留 1 位小数（PRD §4.5）
- [ ] `MockProvider` 多维评分：覆盖全部传入维度、**顺序一致**、无题目维度得 0.0
- [ ] `MockProvider` 汇总：`overall_score` 为维度分均值；`strengths` / `weaknesses` **永不为空列表**；空输入不抛异常
- [ ] `get_provider()` 按配置返回实现且缓存单例；非法配置 **fail fast**；`openai` 缺 Key 时报错（PRD §6）
- [ ] `OpenAIProvider` 解析容错覆盖：围栏剥离、越界 clamp、维度兜底、解析失败重试
- [ ] 真实 Provider 失败时**不自动降级**到 Mock，抛 `AIProviderError`（PRD §7）
- [ ] **`ai` 模块中不存在对任何业务模块的 import**（PRD §3.3）
- [ ] 全部 ai 测试通过，且**不依赖数据库、不依赖网络**

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| `ai` 是否接收 ORM 对象 | **只接收原始值** | 保住 PRD §3.3 的「`ai` 依赖为空」；可测性大幅提升；真实 Provider 本就需要序列化 |
| 真实 Provider 失败是否降级到 Mock | **不降级** | PRD §7 明确要求「标记失败 + 回退状态 + 可重新触发」，而非静默降级；降级也会把模板结果伪装成 AI 结果 |
| 抽象方法的参数形态与 PRD §6 有出入 | 已逐条对照说明（§3.3） | 满足「`ai` 不依赖业务模块」的约束；**能力范围不变** |
| Mock 是否引入随机性以保证题目多样 | **不引入** | 确定性是 Mock 作为测试基准（PRD §10）的前提；多样性由真实 Provider 提供 |
| Prompt 是否外置为可配置文件 | **不外置** | 避免引入配置管理复杂度；MVP 无多租户 Prompt 定制需求 |
| 真实 Provider 的 JSON 解析容错做到什么程度 | 围栏剥离 + 子串提取 + 字段兜底 | 大模型输出不完全可控，容错不足会让评估频繁失败（PRD §7 的失败回退虽能兜底，但体验差） |
| Provider 是否持有数据库 Session | **不持有** | 保持纯函数式；落库归 interview / evaluation（PRD §3.2 分层） |
| 是否做结果缓存 | **不做** | MVP YAGNI；缓存会引入失效策略与额外状态 |
| **（MVP-2）新增抽象方法打断测试替身** | 补齐 `tests/test_interview.py` 的 `FailingProvider`；其余替身经核实不受影响 | 它是唯一直接继承 `AIProvider` 的替身；不改则既有用例因无法实例化而集体失败 |
| **（MVP-2）判分阈值出现第二处定义** | 收敛为 `ai.base.PASS_THRESHOLD = 6.5`，前端 6.5 由 module-15 加注释互相指向 | 前端已用 6.5 判及格（`shell.js` 的 `scoreClass`、`radar.js` 的 `isPass`）。若刷题用别的阈值，会出现「判你答对但报告显示需关注」的矛盾 |
| **（MVP-2）Mock 的规则判分被误当作评分质量基准** | 明确声明 Mock 只保证可演示、可测试、确定性 | Mock 的职责不是模拟 LLM 的判断力；把它当基准会导致对真实评分质量的误判 |
