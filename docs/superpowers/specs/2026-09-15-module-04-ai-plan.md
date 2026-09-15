# ai 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：ai（AI Provider 抽象与实现）
**所属包**：`backend/app/ai/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp.md](../plans/2026-09-15-ai-interview-assistant-mvp.md)
**设计规格**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 任务**：Task 4
**前置依赖**：core（[module-00](./2026-09-15-module-00-core-plan.md)）

---

## Global Constraints（全局约束）

- 后端严格分层：`router → service → repository → MySQL`，只允许自上而下依赖，不跨层调用、不反向依赖。
- 每个模块独立 Python package（`backend/app/<module>/`）。
- **AI 通过抽象接口接入，真实 Provider 与 Mock Provider 可配置切换，代码不写死。**
- 评分统一 0–10 分制（逐题、维度、总分）。
- 统一错误响应格式 `{code, message, detail}`。

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 |
|---|---|
| 能力契约 | 定义 AI 的四个能力接口（出题、逐题评分、多维评分、汇总报告）及其输入输出数据结构 |
| Mock 实现 | 基于规则的**确定性**实现，用于无 Key 演示与自动化测试 |
| 真实实现 | 调用大模型 API 的实现 |
| 选择机制 | 按配置返回具体实现的工厂 |

### 1.2 边界（明确不做）

- **不注册任何 HTTP 路由**：ai 是服务端内部能力，无对外端点。
- **不访问数据库**：Provider 是**纯函数式**能力，不持有 Session、不读写任何表。落库是 interview / evaluation 的职责。
- **不依赖任何业务模块**：ai **不 import** position / question / interview / evaluation。所有输入以**原始值**（字符串、列表）传入，见 §3.3。
- **不做 Prompt 模板的持久化配置**：Prompt 内置于实现中，MVP 不做可配置 Prompt 管理。
- **不做 token 计数与成本核算**：不在 MVP 范围。
- **不做结果缓存**：不在 MVP 范围。

### 1.3 依赖方向

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

> **关键设计约束**：`ai` 处在依赖图的最底层，与 `core` 平级但彼此独立。这让 `ai` 可以被任意模块安全调用，也让 Mock 实现可以在完全不启动数据库的情况下被单测。

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/ai/__init__.py` | 包标识 |
| `backend/app/ai/base.py` | `AIProvider` 抽象基类 + 四个返回数据结构 + `QAPair` 输入结构 |
| `backend/app/ai/mock_provider.py` | 确定性规则实现 |
| `backend/app/ai/openai_provider.py` | 大模型 API 实现（httpx + Prompt 构造 + 响应解析 + 重试） |
| `backend/app/ai/factory.py` | `get_provider()`：按配置返回实现并缓存单例 |

**测试文件**：`backend/tests/test_mock_provider.py`、`backend/tests/test_ai_factory.py`

> **文件划分说明**：本模块按 PRD 保持四个文件，`base.py` 同时承载抽象方法与返回数据结构。理由：数据结构即接口契约的一部分，分开放置会让「改接口」变成跨文件操作，反而增加遗漏风险。

---

## 3. 接口契约

### 3.1 数据结构（**全项目对 AI 能力的唯一数据契约**）

**`QAPair`**（输入结构，承载一道题的维度、题干与回答）

| 字段 | 类型 | 说明 |
|---|---|---|
| `dimension` | str | 该题考察的维度 |
| `question` | str | 题干 |
| `answer` | str \| None | 候选人回答；未作答时为 `None` |

**`GeneratedQuestion`**（`generate_questions` 的输出元素）

| 字段 | 类型 | 约束 |
|---|---|---|
| `content` | str | 题干，非空 |
| `dimension` | str | 必须属于传入的 `dims` |
| `difficulty` | str | `easy` \| `medium` \| `hard` |
| `category` | str | 缺省 `"通用"` |
| `tags` | list[str] | 缺省 `[]` |
| `source` | str | **恒为 `"ai"`** |

**`QuestionScoreResult`**（`evaluate_answer` 的输出）

| 字段 | 类型 | 约束 |
|---|---|---|
| `score` | float | **0.0–10.0**，保留 1 位小数 |
| `comment` | str | 评语，非空 |

**`DimensionScoreResult`**（`evaluate_dimensions` 的输出元素）

| 字段 | 类型 | 约束 |
|---|---|---|
| `dimension` | str | 必须属于传入的 `dims` |
| `score` | float | 0.0–10.0，保留 1 位小数 |
| `comment` | str | 评语，非空 |

**`ReportResult`**（`summarize_report` 的输出）

| 字段 | 类型 | 约束 |
|---|---|---|
| `overall_score` | float | 0.0–10.0，保留 1 位小数 |
| `conclusion` | str | 综合结论段落 |
| `strengths` | list[str] | 优势条目；**不可为空列表**，无优势时填占位条目 |
| `weaknesses` | list[str] | 待改进条目；**不可为空列表**，无短板时填占位条目 |

> **`strengths` / `weaknesses` 为何用列表而非段落文本**：报告页需要按条目渲染（序号 / 图标），结构化列表比在前端按换行符切分更可靠。落库时存为 JSON 列。

### 3.2 抽象基类方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `generate_questions(position_name: str, jd: str, dims: list[str], existing_contents: list[str], count: int) -> list[GeneratedQuestion]` | 列表 | 生成 `count` 道新题；`existing_contents` 为已有题干，用于避免重复 |
| `evaluate_answer(dimension: str, question: str, answer: str \| None) -> QuestionScoreResult` | 结果 | 单题评分 |
| `evaluate_dimensions(dims: list[str], qa_pairs: list[QAPair]) -> list[DimensionScoreResult]` | 列表 | 逐维度评分，**返回顺序与 `dims` 一致** |
| `summarize_report(dims: list[str], dimension_scores: list[DimensionScoreResult], question_scores: list[QuestionScoreResult]) -> ReportResult` | 结果 | 汇总报告 |

**方法名与 PRD 的差异说明**：

| PRD 中的签名 | 本设计签名 | 差异原因 |
|---|---|---|
| `generate_questions(position, dims, bank_questions, count)` | `generate_questions(position_name, jd, dims, existing_contents, count)` | ① 传**原始值**而非 ORM 对象，使 ai 不依赖业务模块；② 拆出 `jd`，它是出题的核心输入；③ `bank_questions` 改为 `existing_contents`（仅需题干用于去重） |
| `evaluate_answer(question, answer)` | `evaluate_answer(dimension, question, answer)` | 增加 `dimension`，让单题评语能围绕维度展开 |
| `evaluate_dimensions(answers, dims)` | `evaluate_dimensions(dims, qa_pairs)` | 参数顺序调整为「先声明维度」，且 `answers` 提升为 `qa_pairs`（含维度与题干，评分需要上下文） |
| `summarize_report(all_scores, dims)` | `summarize_report(dims, dimension_scores, question_scores)` | 拆开 `all_scores`：汇总需要区分维度分与逐题分（前者定结论，后者做明细引用） |

> 上述差异**不改变能力范围**，仅调整参数形态以满足「ai 不依赖业务模块」这一分层约束。PRD §6 的能力清单（四个方法、两个实现、可配置切换）完全保留。

### 3.3 「传原始值」的设计约束（**本模块最重要的边界规则**）

| 禁止 | 允许 |
|---|---|
| `generate_questions(position: Position, ...)` | `generate_questions(position_name: str, jd: str, ...)` |
| 在 ai 中 `from app.position.models import Position` | ai 中不出现任何业务模块 import |

**理由**：

1. **依赖方向**：若 ai 接收 ORM 对象，`ai → position`、`ai → interview` 的依赖会立即出现，破坏分层。
2. **可测性**：Mock Provider 的测试无需建库、无需构造 ORM 实例，传入字符串即可。
3. **可替换性**：真实 Provider 要把输入序列化成 Prompt，本来也只需要字符串。

### 3.4 工厂契约

| 签名 | 行为 |
|---|---|
| `get_provider() -> AIProvider` | 读 `settings.PROVIDER_NAME`：`"mock"` → `MockProvider()`；`"openai"` → `OpenAIProvider()`；其他值 → **抛配置错误**（fail fast） |
| `reset_provider_cache() -> None` | 清空单例缓存，**供测试切换实现使用** |

**设计要点**：

- Provider 实例**无状态**，工厂内部缓存单例，避免每次调用重新构造（真实 Provider 可复用 httpx client）。
- `OPENAI` 模式下若 `OPENAI_API_KEY` 为空 → **构造时即报错**，而非等到第一次调用才失败。

---

## 4. Mock Provider 规则设计（确定性）

> **核心要求**：**相同输入必须产生完全相同输出**。不允许任何随机性、时间戳、哈希随机化、字典序依赖。这是 Mock 能作为测试基准的前提。

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
| `existing_contents` | 仅用于校验：若生成的题干与已有题干完全相同，追加「（变体N）」后缀直至不冲突，`N` 从 1 递增（确定性） |

**题干模板表**

| 序号 | 模板（`{position}` = 岗位名，`{dim}` = 维度） |
|---|---|
| 1 | `关于{dim}：请描述一次你在{position}相关工作中遇到的具体挑战，以及你的处理方式。` |
| 2 | `关于{dim}：如果让你从零开始改进{position}岗位的一项关键流程，你会怎么做？` |
| 3 | `关于{dim}：请举例说明你如何衡量自己在{dim}方面的表现。` |

### 4.2 `evaluate_answer`

| 条件 | 分数 |
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
- 最终结果 **clamp 到 [0.0, 10.0]**，保留 1 位小数
- 长度按 **strip 后的字符数**计算

**评语模板**（按最终分数分档）

| 分档 | 评语（`{dim}` = 维度） |
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
| 返回顺序 | **与传入 `dims` 顺序完全一致** |

**评语模板**（按分数分档）

| 分档 | 评语（`{dim}` = 维度） |
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

> `dimension_scores` 为空列表的情况（岗位未定义维度，理论上被 position 校验阻止）必须有确定行为，不得抛异常。

---

## 5. 真实 Provider 设计（openai_provider.py）

### 5.1 调用形态

| 项 | 设计 |
|---|---|
| HTTP 客户端 | `httpx`，超时取 `settings.AI_TIMEOUT_SECONDS` |
| 接口 | Chat Completions 兼容接口（`{base_url}/chat/completions`） |
| 认证 | `Authorization: Bearer {OPENAI_API_KEY}` |
| 模型 | `settings.OPENAI_MODEL` |
| 温度 | 出题用较高温度（如 0.7）以保证多样性；评分与汇总用低温度（如 0.2）以保证稳定 |

### 5.2 Prompt 设计要素（不做模板持久化，内置于方法中）

| 方法 | Prompt 必须包含 |
|---|---|
| `generate_questions` | 岗位名、JD 全文、评估维度列表、**已有题干**（明确要求「不得与以下题目重复」）、需要生成的数量、每题的字段要求（题干/维度/难度）、**要求输出 JSON 数组**、要求 `dimension` 只能取给定维度之一 |
| `evaluate_answer` | 维度、题干、候选人回答、**评分区间 0–10**、评分应参考「具体性、相关性、深度」、要求输出单个 JSON 对象（`score`、`comment`） |
| `evaluate_dimensions` | 维度列表、该维度下的问答对、要求逐维度输出、要求输出 JSON 数组 |
| `summarize_report` | 维度分列表、逐题分列表、要求输出 JSON 对象（`overall_score`、`conclusion`、`strengths`、`weaknesses`），并明确 `strengths` / `weaknesses` 为字符串数组 |

### 5.3 响应解析容错

| 情况 | 处理 |
|---|---|
| 响应被 markdown 代码围栏包裹 | 剥离 ```json / ``` 围栏后再解析 |
| 响应前后有解释性文字 | 提取**首个** `{` 到**最后一个** `}`（或 `[` 到 `]`）的子串再解析 |
| 解析后 `score` 越界 | clamp 到 [0.0, 10.0] |
| 解析后 `dimension` 不在给定维度中 | **映射到最接近的给定维度**；若无从判断则丢弃该条（`evaluate_dimensions` 中该维度按 0.0 处理） |
| `strengths` / `weaknesses` 为空数组 | 填入与 Mock 相同的占位条目，保证契约一致 |
| JSON 解析彻底失败 | 计入失败，触发重试 |

### 5.4 失败与重试

| 失败类型 | 处理 |
|---|---|
| 连接失败 / 超时 | 重试 |
| HTTP 4xx / 5xx | 重试 |
| JSON 解析失败 | 重试 |
| 重试次数 | `settings.AI_MAX_RETRIES`（默认 1，即最多尝试 2 次） |
| 重试后仍失败 | 抛 `AIProviderError`（502） |

### 5.5 **不自动降级到 Mock 的设计决策**

真实 Provider 调用失败时，**不**自动回退到 MockProvider。理由：

| 论点 | 说明 |
|---|---|
| 语义误导 | 静默降级会让用户以为看到的是 AI 评估结果，实际是规则模板输出，评分毫无参考价值 |
| 掩盖故障 | 运维侧无法感知真实 Provider 已不可用 |
| 责任清晰 | 失败就失败，由上层（interview / evaluation）明确告知用户并允许重试，见 interview §6、evaluation §6 |

Mock 仅在 `PROVIDER_NAME=mock` 时**显式**启用。

---

## 6. 错误处理

| 场景 | 异常 | code | HTTP |
|---|---|---|---|
| 真实 Provider 重试后仍失败 | `AIProviderError` | `AI_PROVIDER_ERROR` | 502 |
| `PROVIDER_NAME` 取值非法 | 启动期配置错误 | — | 服务启动失败（fail fast） |
| `openai` 模式下缺 `OPENAI_API_KEY` | 构造期 `AIProviderError` | `AI_PROVIDER_ERROR` | 502 |
| `generate_questions` 传入空 `dims` | `AIProviderError` | `AI_PROVIDER_ERROR` | 502 |

> **异常冒泡后的处理**：`AIProviderError` 由调用方（interview / evaluation）的 service 捕获并决定业务影响，详见 interview §6、evaluation §6。ai 模块只负责抛出，不做业务决策。

---

## 7. 测试设计

`backend/tests/test_mock_provider.py`

> **本模块测试的最大特点：不需要数据库、不需要 TestClient**，纯函数调用即可。这是「ai 不依赖业务模块」这一约束带来的直接收益。

### 7.1 出题

| 测试 | 断言 |
|---|---|
| `test_generate_returns_exact_count` | `count=3` → 返回 3 条 |
| `test_generate_count_zero` | `count=0` → 空列表 |
| `test_generate_count_negative` | `count=-1` → 空列表 |
| `test_generate_empty_dims_raises` | `dims=[]` → `AIProviderError` |
| `test_generate_dimensions_cycled` | `dims=[A,B]`、`count=5` → 维度依次为 A,B,A,B,A |
| `test_generate_source_always_ai` | 所有条目 `source == "ai"` |
| `test_generate_difficulty_cycled` | 依次 `easy, medium, hard, easy, ...` |
| `test_generate_deterministic` | 同参数调用两次，结果**完全相等** |
| `test_generate_avoids_existing_contents` | `existing_contents` 含会撞车的题干 → 生成结果与其不重复 |
| `test_generate_dims_never_empty` | 每条 `dimension ∈ dims` |

### 7.2 逐题评分

| 测试 | 断言 |
|---|---|
| `test_evaluate_none_answer_scores_zero` | `answer=None` → `score == 0.0` |
| `test_evaluate_empty_answer_scores_zero` | `answer=""` → `0.0` |
| `test_evaluate_whitespace_answer_scores_zero` | `answer="   \n "` → `0.0` |
| `test_evaluate_length_tiers` | 各档长度（10 / 50 / 150 / 400 字符）分别得 3.0 / 5.0 / 7.0 / 8.5（无加分标记时） |
| `test_evaluate_bonus_capped` | 同时命中四类标记 → 加分不超过 +1.5 |
| `test_evaluate_clamped_to_ten` | 强行构造高分场景 → 不超过 10.0 |
| `test_evaluate_one_decimal_place` | 结果保留 1 位小数 |
| `test_evaluate_comment_by_tier` | 各分档评语符合模板 |
| `test_evaluate_deterministic` | 同输入两次结果相等 |

### 7.3 多维评分

| 测试 | 断言 |
|---|---|
| `test_dimensions_covers_all_input_dims` | 返回项覆盖传入的**全部**维度 |
| `test_dimensions_order_matches_input` | 返回顺序与 `dims` 一致 |
| `test_dimensions_average` | 某维度两题分别 5.0 / 7.0 → 该维度 6.0 |
| `test_dimensions_no_question_scores_zero` | 某维度无对应题目 → 0.0 + 指定评语 |
| `test_dimensions_one_decimal_place` | 保留 1 位小数 |

### 7.4 汇总报告

| 测试 | 断言 |
|---|---|
| `test_report_four_fields_present` | 四个字段齐全且非空 |
| `test_report_overall_is_average` | 三个维度 6.0/8.0/10.0 → `overall_score == 8.0` |
| `test_report_empty_dimension_scores` | 空列表 → `overall_score == 0.0`，**不抛异常** |
| `test_report_strengths_threshold` | 仅 ≥ 6.5 的维度进入 `strengths` |
| `test_report_weaknesses_threshold` | 仅 < 6.5 的维度进入 `weaknesses` |
| `test_report_strengths_not_empty` | 全部维度都 < 6.5 → `strengths` 为占位条目，**不是空列表** |
| `test_report_weaknesses_not_empty` | 全部维度都 ≥ 6.5 → `weaknesses` 为占位条目，**不是空列表** |
| `test_report_conclusion_by_tier` | 各分档结论文本符合模板 |

### 7.5 工厂

`backend/tests/test_ai_factory.py`

| 测试 | 断言 |
|---|---|
| `test_factory_returns_mock_by_default` | 默认配置 → `MockProvider` 实例 |
| `test_factory_returns_openai_when_configured` | `PROVIDER_NAME=openai` + 有 Key → `OpenAIProvider` 实例 |
| `test_factory_invalid_name_raises` | `PROVIDER_NAME=bogus` → 抛配置错误 |
| `test_factory_openai_without_key_raises` | `PROVIDER_NAME=openai` 且无 Key → 抛错 |
| `test_factory_caches_instance` | 两次调用返回**同一对象** |
| `test_reset_cache` | `reset_provider_cache()` 后返回新对象 |
| `test_mock_provider_conforms_to_abstract` | `MockProvider` 是 `AIProvider` 的实例（契约一致性） |

---

## 8. 任务分解（TDD 步骤，无代码）

### Task 4.1：数据结构与抽象基类

- [ ] 定义 `QAPair`、`GeneratedQuestion`、`QuestionScoreResult`、`DimensionScoreResult`、`ReportResult`（§3.1 全字段）
- [ ] 定义 `AIProvider` 抽象基类与 §3.2 的四个抽象方法（方法体仅 `raise NotImplementedError`）
- [ ] 写测试：抽象类**不可直接实例化**；四个方法均被声明为抽象
- [ ] 运行确认通过
- [ ] 提交

### Task 4.2：Mock 出题

- [ ] 写 §7.1 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.generate_questions`（§4.1 规则）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.3：Mock 逐题评分

- [ ] 写 §7.2 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.evaluate_answer`（§4.2 规则）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.4：Mock 多维评分

- [ ] 写 §7.3 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.evaluate_dimensions`（§4.3 规则）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.5：Mock 汇总报告

- [ ] 写 §7.4 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `MockProvider.summarize_report`（§4.4 规则，含空列表兜底与占位条目）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.6：工厂与配置校验

- [ ] 写 §7.5 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `get_provider()` 与 `reset_provider_cache()`（含缓存、非法值 fail fast、缺 Key 报错）
- [ ] 运行确认通过
- [ ] 提交

### Task 4.7：真实 Provider

- [ ] 实现 `OpenAIProvider` 构造（校验 Key、建 httpx client、超时配置）
- [ ] 实现四个方法的 Prompt 构造（§5.2 要素）
- [ ] 实现响应解析容错（§5.3：剥离围栏、提取 JSON、clamp、空数组兜底）
- [ ] 实现重试逻辑（§5.4）
- [ ] 写测试：**用 mock 的 httpx 响应**验证「围栏剥离」「越界 clamp」「解析失败重试后抛 `AIProviderError`」——**不打真实 API**
- [ ] 运行确认通过
- [ ] 提交

### Task 4.8：全量回归

- [ ] 运行 ai 全部测试
- [ ] 运行 core 测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] `AIProvider` 为抽象基类，四个方法齐备
- [ ] `MockProvider` 满足「同输入同输出」：所有方法均有确定性测试
- [ ] `MockProvider` 出题：数量准确、维度按 `dims` 循环、难度循环、`source` 恒为 `ai`
- [ ] `MockProvider` 评分：空/空白回答得 0.0；长度分档正确；加分上限 +1.5；结果 clamp 到 [0,10] 且保留 1 位小数
- [ ] `MockProvider` 多维评分：覆盖全部传入维度、顺序一致、无题目维度得 0.0
- [ ] `MockProvider` 汇总：`overall_score` 为维度分均值；`strengths` / `weaknesses` **永不为空列表**；空输入不抛异常
- [ ] `get_provider()` 按配置返回实现且缓存单例；非法配置 fail fast；`openai` 缺 Key 时报错
- [ ] `OpenAIProvider` 解析容错覆盖：围栏剥离、越界 clamp、维度兜底、解析失败重试
- [ ] 真实 Provider 失败时**不自动降级**到 Mock，抛 `AIProviderError`
- [ ] ai 模块中**不存在**对任何业务模块的 import
- [ ] 全部 ai 测试通过，且**不依赖数据库**

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| ai 是否接收 ORM 对象 | 只接收原始值 | 保住依赖方向；可测性大幅提升；真实 Provider 本就需要序列化 |
| 真实 Provider 失败是否降级到 Mock | **不降级** | 避免把模板结果伪装成 AI 结果，语义误导；故障应显式暴露 |
| 抽象方法的参数形态与 PRD 有出入 | 已逐条对照说明（§3.2） | 满足「ai 不依赖业务模块」的分层约束；能力范围不变 |
| Mock 是否引入随机性以保证题目多样 | **不引入** | 确定性是 Mock 作为测试基准的前提；多样性由真实 Provider 提供 |
| Prompt 是否外置为可配置文件 | 不外置，内置 | 避免引入配置管理复杂度；MVP 无多租户 Prompt 定制需求 |
| 真实 Provider 的 JSON 解析容错做到什么程度 | 做到「围栏剥离 + 子串提取 + 字段兜底」 | 大模型输出不完全可控，容错不足会让评估频繁失败 |
| Provider 是否持有数据库 Session | 不持有 | 保持纯函数式；落库归 interview / evaluation |
| 是否做结果缓存 | 不做 | MVP YAGNI；缓存会引入失效策略与额外状态 |
