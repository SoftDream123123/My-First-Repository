# ai 模块执行计划书（MVP-2 刷题判分与候选人反馈）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：ai（新增三个能力：补参考答案、刷题判分、候选人反馈）
**所属包**：`backend/app/ai/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§6（AI Provider 契约新增三个方法）、§4.3（AI 补参考答案）、§4.7（刷题判分）、§4.9（候选人脱敏反馈）、§7（失败与降级）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-04 ai MVP-1](./2026-09-15-module-04-ai-plan.md)
**本模块被谁依赖**：[module-10 question](./2026-09-20-module-10-question-plan.md)（补参考答案）、[module-13 practice](./2026-09-20-module-13-practice-plan.md)（判分）、[module-14 evaluation](./2026-09-20-module-14-evaluation-feedback-plan.md)（候选人反馈）

> **与 module-04 的关系**：module-04 是 `ai` 模块的 MVP-1 计划书，仍然有效。本文档是**增量**，冲突时以本文档为准。

---

## Global Constraints（全局约束，摘自 PRD）

- `ai` 是**基础设施**，被 `question` / `practice` / `evaluation` 调用；**不得反向依赖任何业务模块**（§3.3、module-00 §1.2）
- **只接收原始值**（字符串、列表），**不接收 ORM 对象**（module-04 §3.4 的边界规则；本模块三个新方法必须同样遵守）
- 两个实现：**真实 Provider** 与 **Mock Provider**；Mock 必须**规则生成确定性结果**（§6）
- 通过配置项选择实现，**代码不写死**（§6）
- 评分统一 **0–10 分制**（§4.5）
- **AI 失败不阻塞其他功能**（§7）
- **不自动降级到 Mock**（module-04 §5.5 决策沿用）
- 刷题判分失败时：**`practice_item` 正常落库但 `is_correct` 为空，标记未判分，可后续重判**（§7）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §6）

| 子职责 | 内容 | 调用方 |
|---|---|---|
| 补参考答案 | 为缺参考答案的题目生成参考答案与解析 | question §5.2、practice |
| 刷题判分 | 对简答题作答判分并给出解析 | practice §5.2 |
| 候选人反馈 | 由报告生成面向候选人的脱敏反馈文本 | evaluation §5.x |
| 判分阈值常量 | 提供全项目唯一的及格线常量 | practice、evaluation |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **单选题判分** | PRD §4.7 明确「单选题：本地规则判分（不消耗 AI）」。判分由 `practice` 本地完成——见 §3.2「`grade_practice_answer` 为何仍接收 `question_type`」 |
| **题目生成/评估的既有四方法** | 归 module-04，本模块不改其签名与行为 |
| **判分结果落库** | `ai` 只做计算，不接触数据库（它连 ORM 都不接收） |
| **脱敏策略本身**（哪一档下发什么） | 由 `evaluation` 按配置决定并把 `level` 传进来；`ai` 只按 level 产出文本与是否含总分 |
| **题库查重、相似题推荐** | 不在 PRD 范围 |
| **流式判分** | PRD §1.3「流式出题不做」，判分为同步调用（仅评估环节流式） |
| 多语言 / 多模型路由 | 单机单 Provider，YAGNI |

### 1.3 依赖方向

```
question / practice / evaluation ──→ ai（单向）
ai ──→ core.config / core.exceptions
ai ✗→ auth / position / question / interview / evaluation / practice

（AIProvider 新增抽象方法不改变该方向：新方法只接收 str / list[str] / float）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/ai/base.py` | **改**：新增三个 dataclass、三个抽象方法、两个常量 |
| `backend/app/ai/mock_provider.py` | **改**：实现三个确定性规则 |
| `backend/app/ai/openai_provider.py` | **改**：实现三个方法（prompt + 解析容错 + 重试） |
| `backend/app/ai/factory.py` | **不改**：方法增加不影响工厂 |

**测试文件**：`backend/tests/test_mock_provider.py`（增补）、`backend/tests/test_openai_provider.py`（增补）

**本模块需修改的上游文件（**必读，容易漏**）**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| `backend/tests/test_interview.py` | 给 `FailingProvider(AIProvider)` 补三个方法的实现 | ⚠️ **它是 `AIProvider` 的直接子类**。新增抽象方法后，该测试类将无法实例化（`TypeError: Can't instantiate abstract class`），既有用例会集体失败 |

**无需修改的测试替身（已核实）**

| 替身 | 位置 | 为何不受影响 |
|---|---|---|
| `PartialDimensionProvider(MockProvider)` | `tests/test_evaluation.py:101` | 继承自 `MockProvider`，**自动获得**三个新方法 |
| `FailingProvider`（无基类） | `tests/test_evaluation.py:213`、`tests/test_evaluation_stream.py:239` | 普通类，靠鸭子类型被 monkeypatch 注入，非 ABC 子类 |
| `GatedProvider`（无基类） | `tests/test_evaluation_stream.py:43` | 同上 |

---

## 3. 接口契约（对应 PRD §6）

### 3.1 新增数据结构（**全项目新增 AI 能力的唯一数据契约**）

| dataclass | 字段 | 类型 | 说明 |
|---|---|---|---|
| `ReferenceAnswerResult` | `reference_answer` | str | 参考答案；单选题时为某个选项的**完整文本** |
| | `explanation` | str | 解析 |
| `PracticeGradeResult` | `score` | float | 0–10，一位小数 |
| | `is_correct` | bool | 等价于 `score >= PASS_THRESHOLD` |
| | `explanation` | str | 面向候选人的解析 |
| `CandidateFeedbackResult` | `conclusion` | str | 综合结论 |
| | `strengths` | list[str] | 优点 |
| | `weaknesses` | list[str] | 待改进 |
| | `overall_score` | float \| None | **`level='summary'` 时为 `None`**，`'full'` 时为原值 |

### 3.2 新增抽象方法签名（对应 PRD §6 的三个接口）

| 方法签名 | 返回 | 用途 |
|---|---|---|
| `generate_reference_answer(question_type: str, content: str, options: list[str], dimension: str)` | `ReferenceAnswerResult` | 为一题生成参考答案与解析 |
| `grade_practice_answer(question_type: str, content: str, reference_answer: str, user_answer: str)` | `PracticeGradeResult` | 刷题作答判分 + 解析 |
| `generate_candidate_feedback(level: str, conclusion: str, strengths: list[str], weaknesses: list[str], overall_score: float)` | `CandidateFeedbackResult` | 生成面向候选人的脱敏反馈 |

**两个新增模块级常量（`base.py`）**

| 常量 | 值 | 用途 |
|---|---|---|
| `PASS_THRESHOLD` | `6.5` | **全项目唯一的及格线**，见 §3.3 |
| `QUESTION_TYPE_SINGLE_CHOICE` / `QUESTION_TYPE_SHORT_ANSWER` | `"single_choice"` / `"short_answer"` | 判分支路的取值 |

> 题型常量在 `question.models` 与 `ai.base` 各定义一份，与既有 `SOURCE_BANK` / `SOURCE_AI` / `DIFFICULTY_*` 的现状一致：**`ai` 不能依赖 `question`**，因此常量必须各自定义。这是模块解耦换来的重复，不是疏漏。

**`grade_practice_answer` 为何仍接收 `question_type`**：即使 `practice` 对单选题不调用本方法，签名仍保留该参数，原因有二——① 真实 Provider 可据此定制 prompt（单选与简答的判分措辞不同）；② 签名与「题型」这一概念对齐，调用方无需在调用点做分支假设。**这不代表 `ai` 承担单选判分职责**，职责划分见 §1.2。

### 3.3 ⚠️ 判分阈值必须全项目唯一（`PASS_THRESHOLD = 6.5`）

现状：前端的及格线**已经**是 6.5，且写在两处——

| 位置 | 现状 |
|---|---|
| `frontend/src/components/shell.js` `scoreClass(score)` | `score >= 6.5 ? 'is-pass' : 'is-watch'` |
| `frontend/src/components/radar.js` | `const isPass = (score) => score >= 6.5` |

因此刷题判对的阈值**必须也是 6.5**，否则会出现「刷题判你答对了，但同一分数在报告页显示为需关注」的矛盾。本设计把该值收敛到 `ai.base.PASS_THRESHOLD` 一处定义，`practice` 从它导入使用。

| 决策 | 说明 |
|---|---|
| 常量放 `ai` 而非 `core` | 它是**判分规则**的一部分（Mock 的 `is_correct` 直接由它算出），与判分实现同处；放 `core` 会让「及格线」这一业务概念落入横切基础设施 |
| 后端 6.5 与前端 6.5 仍有两份实现 | 前端无法 import 后端常量（纯 JS + 无构建期共享）。**接受该重复，但必须两侧注释互相指向**；前端侧在 module-15 处理 |
| `is_correct` 由 Provider 计算而非调用方 | 避免调用方各自用不同阈值推导。Provider 返回的 `is_correct` 与 `score` 保证自洽 |

### 3.4 与 PRD §6 参数形态的差异说明（**不改变能力范围**）

| PRD §6 写法 | 本设计 | 原因 |
|---|---|---|
| `generate_reference_answer(question)` | `(question_type, content, options, dimension)` | 传 ORM 对象会让 `ai` 反向依赖 `question`，破坏依赖单向；且 Mock 单测需起库 |
| `grade_practice_answer(question, user_answer)` | `(question_type, content, reference_answer, user_answer)` | 同上 |
| `generate_candidate_feedback(report, level)` | `(level, conclusion, strengths, weaknesses, overall_score)` | 同上；`report` 是 `evaluation` 的表，`ai` 不得依赖它 |

这与 module-04 §3.3 对既有四方法的处理是同一手法。

---

## 4. Mock Provider 规则设计（对应 PRD §6「规则生成确定性结果」）

> 三条铁律：**无随机**、**同样输入必得同样输出**、**不访问数据库与网络**。

### 4.1 `generate_reference_answer`

| 题型 | 规则 |
|---|---|
| `short_answer` | 由题干长度选取固定模板（`_REFERENCE_TEMPLATES[len(content) % N]`），模板中代入 `dimension` 与题干前 20 字；`explanation` 用另一组固定模板生成 |
| `single_choice` | 取 `options[len(content) % len(options)]` 作为参考答案；`explanation` 用「正确答案是选项中的第 k 项，因为……」的固定模板 |
| `options` 为空但题型为单选 | 抛 `AIProviderError`（调用方本应在 schema 层拦住，这是防御性失败，与既有 `generate_questions` 在 `dims` 为空时抛错的写法一致） |

> **为何用「长度取模」而非随机**：既保证确定性（可测试、可演示复现），又让不同题干得到不同答案，避免所有题返回同一个答案而看不出 Mock 在工作。

### 4.2 `grade_practice_answer`

**第一步：空作答短路（两个实现必须一致，且不发网络请求）**

```
user_answer.strip() == ""  →  返回 PracticeGradeResult(
                                  score=0.0,
                                  is_correct=False,
                                  explanation="未作答"
                              )
```

> 与既有 `evaluate_answer` 对「未作答按 0 分处理」的约定一致（`interview/schemas.py` 的 `AnswerCreate` 注释即为此意）。

**第二步：按题型判分**

| 题型 | 规则 |
|---|---|
| `single_choice` | strip 后精确比较 `user_answer` 与 `reference_answer`；相等 → 10.0 / True，否则 → 0.0 / False。`explanation` 回报正确答案文本。（**`practice` 不会调用本分支**，此处实现为防御，见 §1.2） |
| `short_answer` | **字符二元组 Jaccard 相似度**，公式见下 |

**简答题判分公式（必须逐字实现，Mock 与真实实现之外的第三方实现也应遵循同一口径以便比较）**

```
1. 规范化：去掉两个字符串中的所有空白字符（中文无词边界，故不做分词）
2. 切 n-gram：取字符二元组集合（字符串长度 < 2 时退化为单字符集合）
3. 相似度 overlap = |A ∩ B| / |A ∪ B|（并集为空 → 0.0）
4. score = round(10 * overlap, 1)          ← 一位小数，与全项目 0–10 分制对齐
5. is_correct = score >= PASS_THRESHOLD    ← 6.5
```

| 边界 | 行为 |
|---|---|
| `reference_answer` 为空串 | 抛 `AIProviderError`。**调用方不应在这种情况下调用本方法**（`practice` 直接标记未判分，见 module-13 §5.2），这是防御性失败 |
| 任一方为单字符 | 退化为单字符集合，公式仍然成立 |
| 两者完全相同 | overlap = 1.0 → score 10.0 → True |
| 完全无重合 | overlap = 0.0 → score 0.0 → False |
| 恰好 6.5 边界 | `6.5 >= 6.5` → **判对**，`is_correct=True`（边界必须写明，否则实现者会各自猜） |
| 6.4 与 6.6 | 6.4 → False；6.6 → True（测试点覆盖阈值上下界） |

> **为何选 Jaccard 而非「关键词命中」**：中文没有空格分词，靠关键词表会把「判分规则」变成一份需要维护的词库；字符二元组是无词库、纯确定性、对近义改写有一定宽容度的方案，适合 Mock 的定位。**Mock 的判分质量不代表真实评分质量**——见 §10 风险。

### 4.3 `generate_candidate_feedback`

| `level` | 行为 |
|---|---|
| `summary` | 用固定模板润色 `conclusion` / `strengths` / `weaknesses`；**`overall_score = None`** |
| `full` | 同上，但**保留** `overall_score` 原值 |
| 未知取值 | **按 `summary` 处理**并记 `warning` 日志 |

| 设计决策 | 说明 |
|---|---|
| **未知 `level` 退化为 `summary`** | 「给得更少」是安全方向：即使配置被写错（如 `CANDIDATE_FEEDBACK_LEVEL=detailed`），候选人也不会意外看到自己的分数。同时打 warning，让配置错误可见 |
| Mock **不改变** 优点/待改进的条目数量与顺序 | 保持与报告一致，便于 HR 与候选人对照；Mock 只做措辞润色 |
| 不产出「录用建议」类结论 | PRD §1.3 未要求，且此类表述有合规风险 |

---

## 5. 真实 Provider 设计（`openai_provider.py` 增量）

### 5.1 调用形态

沿用 module-04 §5.1：`_request_json(system, user, temperature, expect_list)` + `ai_max_retries` 次重试；三个新方法各自组装一对 `system` / `user` 字符串。

### 5.2 Prompt 设计要素（不做模板持久化，内置于方法中）

| 方法 | system 要素 | user 要素 | 期望输出 |
|---|---|---|---|
| `generate_reference_answer` | 资深面试官 / 命题人；给出「标准答案 + 解析」 | 题型、题干、选项（单选时列出并标注该答案必须是其一）、维度 | JSON 对象：`reference_answer`、`explanation` |
| `grade_practice_answer` | 严格但公允的判卷人；按 0–10 打分 | 题型、题干、参考答案、候选人作答 | JSON 对象：`score`、`explanation`（**不要求模型给 `is_correct`**） |
| `generate_candidate_feedback` | 面向候选人的沟通者；措辞建设性、不含录用判断 | 结论文本、优点列表、待改进列表、（`level='full'` 时才给）总分 | JSON 对象：`conclusion`、`strengths`、`weaknesses` |

> **`is_correct` 不让模型输出**：它由 `PASS_THRESHOLD` 与 `score` 在后端推导，保证阈值唯一（§3.3）。让模型返回布尔值会引入第二个「是否判对」的判据。

### 5.3 响应解析容错

沿用 module-04 §5.3 的手法，并补充：

| 项 | 处理 |
|---|---|
| `score` | 经 `_clamp_score` 夹到 0–10，并 `round(..., 1)` |
| `is_correct` | **由本地推导**：`score >= PASS_THRESHOLD`，忽略模型可能返回的同名字段 |
| `reference_answer` 不在 `options` 内（单选） | **不在 provider 内纠正**：原样返回。由 `question.service` 判定并报 409（module-10 §5.2） |
| `strengths` / `weaknesses` 非数组 | 经 `_str_list` 转换；转换后为空则回落到空列表 |
| 字段缺失 | 抛 `AIProviderError`（不猜、不填默认答案） |

> **为何「答案不在选项内」的判定放在 `question` 而不是 `ai`**：这是**题目数据自洽性**的校验，属业务规则；`ai` 只负责生成，不知道选项是否合法。职责边界与 §1.2 一致。

### 5.4 失败与重试

沿用 module-04 §5.4：重试 `ai_max_retries` 次（默认 1）→ 仍失败抛 `AIProviderError`（502）。**不自动降级到 Mock**（module-04 §5.5）。

### 5.5 「不阻塞其他功能」的落实（PRD §7）

| 场景 | 行为 |
|---|---|
| 刷题判分失败 | `practice` 捕获 `AIProviderError` → `practice_item` 落库但 `is_correct` 为空 → **作答不丢失**，可重判（module-13 §5.2） |
| 补参考答案失败 | `question` 直接返回 502，**库中字段不变**（module-10 §5.2） |
| 候选人反馈生成失败 | `evaluation` 的反馈接口返回 502，**不影响 HR 侧报告**（module-14 §5.x） |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | 异常 | HTTP（由调用方转出） | message |
|---|---|---|---|
| 任何 AI 调用重试后仍失败 | `AIProviderError` | 502 | AI 服务调用失败，请稍后重试 |
| 单选补答案但 `options` 为空 | `AIProviderError` | 502 | 缺少选项，无法生成参考答案 |
| 简答判分但 `reference_answer` 为空 | `AIProviderError` | 502 | 该题缺少参考答案，无法判分 |
| 模型返回结构不符合预期 | `AIProviderError` | 502 | AI 返回内容格式无法解析 |

> 三个新方法**不引入任何新错误码**——全部复用既有的 `AI_PROVIDER_ERROR`（module-00 §6.3）。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `backend/tests/test_mock_provider.py`（增补）

**`generate_reference_answer`**

| 测试 | 断言 |
|---|---|
| `test_mock_reference_answer_short_answer` | 返回非空的 `reference_answer` 与 `explanation` |
| `test_mock_reference_answer_is_deterministic` | 同一输入连续调用两次，两次结果**完全相等** |
| `test_mock_reference_answer_differs_by_content` | 两道题干不同 → 参考答案不同（证明「长度取模」在起作用） |
| `test_mock_reference_answer_single_choice_in_options` | 返回值**必是 `options` 中的一项**（逐字相等） |
| `test_mock_reference_answer_single_choice_empty_options` | `options=[]` → `AIProviderError` |

**`grade_practice_answer`**

| 测试 | 断言 |
|---|---|
| `test_mock_grade_empty_answer` | 空串 / 纯空白 → `score == 0.0`、`is_correct is False`、解析为「未作答」 |
| `test_mock_grade_identical_answer` | 与参考答案完全相同 → `score == 10.0`、`is_correct is True` |
| `test_mock_grade_disjoint_answer` | 与参考答案无任何二元组重合 → `score == 0.0`、`is_correct is False` |
| `test_mock_grade_score_is_one_decimal` | 返回的 `score` 小数位 ≤ 1（与全项目 0–10 分制对齐） |
| `test_mock_grade_is_deterministic` | 同输入两次调用结果相等 |
| `test_mock_grade_threshold_boundary_just_below` | 构造 overlap 使 `score == 6.4` → `is_correct is False` |
| `test_mock_grade_threshold_boundary_at` | 构造 overlap 使 `score == 6.5` → `is_correct is True` |
| `test_mock_grade_threshold_boundary_just_above` | 构造 overlap 使 `score == 6.6` → `is_correct is True` |
| `test_mock_grade_is_correct_consistent_with_score` | 遍历多组输入，`is_correct == (score >= PASS_THRESHOLD)` 恒成立 |
| `test_mock_grade_single_choice_equal` | 单选且作答等于答案 → 10.0 / True（防御分支） |
| `test_mock_grade_single_choice_not_equal` | 单选且作答不同 → 0.0 / False |
| `test_mock_grade_short_answer_empty_reference` | 参考答案为 `""` → `AIProviderError` |
| `test_mock_grade_normalizes_whitespace` | 作答与答案只差空白字符 → 判为满分（§4.2 第 1 步） |
| `test_mock_grade_single_char_answer` | 单字符输入不抛异常，公式仍成立 |
| `test_mock_grade_does_not_touch_db` | 调用过程不查询数据库（用不含 DB 的环境直调） |

**`generate_candidate_feedback`**

| 测试 | 断言 |
|---|---|
| `test_mock_feedback_summary_hides_score` | `level='summary'` → `overall_score is None` |
| `test_mock_feedback_full_keeps_score` | `level='full'` → `overall_score` 等于传入值 |
| `test_mock_feedback_unknown_level_defaults_to_summary` | `level='detailed'` → `overall_score is None` |
| `test_mock_feedback_preserves_items` | 优点 / 待改进的**条目数量与顺序**与输入一致 |
| `test_mock_feedback_is_deterministic` | 同输入两次调用结果相等 |

**契约一致性**

| 测试 | 断言 |
|---|---|
| `test_mock_provider_implements_all_seven_methods` | `MockProvider` 可实例化（若漏实现抽象方法，此测试会以 `TypeError` 失败——**这是新增抽象方法的守门测试**） |
| `test_mock_provider_is_ai_provider` | `isinstance(MockProvider(), AIProvider)` |

### 7.2 `backend/tests/test_openai_provider.py`（增补，**不打真实 API**）

| 测试 | 断言 |
|---|---|
| `test_openai_reference_answer_parses_json` | 用 transport stub 返回合法 JSON → 正确解析为 dataclass |
| `test_openai_reference_answer_bad_json_raises` | 返回非 JSON → `AIProviderError` |
| `test_openai_grade_clamps_score` | 模型返回 `15.0` → `score == 10.0`；返回 `-3` → `0.0` |
| `test_openai_grade_derives_is_correct_locally` | 模型返回 `score=7.0` 且 `is_correct=false` → **后端仍判 True**（§5.2 决策） |
| `test_openai_grade_short_answer_empty_reference_short_circuits` | 参考答案为空 → 抛 `AIProviderError` 且**未发起请求**（断言 transport 未被调用） |
| `test_openai_grade_empty_answer_short_circuits` | 作答为空 → 直接返回 0 分且**未发起请求** |
| `test_openai_feedback_summary_omits_score` | `level='summary'` → `overall_score is None` |
| `test_openai_retries_then_raises` | transport 连续失败 → 重试 `ai_max_retries` 次后抛 `AIProviderError` |
| `test_openai_missing_field_raises` | JSON 缺 `reference_answer` → `AIProviderError`（不填默认值） |

### 7.3 架构与回归

| 测试 | 断言 |
|---|---|
| `test_ai_depends_on_no_business_module`（既有，`test_architecture.py`） | 新增代码后**仍通过**——三个新方法不得引入业务模块导入 |
| `test_interview.py` 既有用例 | `FailingProvider(AIProvider)` 补齐三个方法后，全部通过（§2 上游文件） |
| `test_evaluation.py` 既有 29 条 | `PartialDimensionProvider` 继承自 `MockProvider`，无需改动即通过 |
| `test_evaluation_stream.py` 既有 34 条 | `GatedProvider` / `FailingProvider` 非 ABC 子类，不受影响 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 11.1：数据结构与常量

- [ ] `base.py` 新增三个 dataclass、`PASS_THRESHOLD`、两个题型常量
- [ ] 写失败测试：三个 dataclass 可实例化、字段默认值正确（`overall_score` 可传 `None`）
- [ ] 运行确认通过
- [ ] 提交

### Task 11.2：抽象方法声明与守门测试

- [ ] `base.py` 声明三个 `@abstractmethod`
- [ ] 写 `test_mock_provider_implements_all_seven_methods`，运行确认**失败**（Mock 尚未实现）
- [ ] 补齐 `tests/test_interview.py` 的 `FailingProvider` 三个方法（否则既有用例崩溃）
- [ ] 提交

### Task 11.3：Mock 补参考答案

- [ ] 写 §7.1 中 `test_mock_reference_answer_*` 五条失败测试
- [ ] 运行确认失败
- [ ] 实现（模板 + 长度取模；单选取选项）
- [ ] 运行确认通过
- [ ] 提交

### Task 11.4：Mock 刷题判分

- [ ] 写 §7.1 中 `test_mock_grade_*` 十四条失败测试（**含三条阈值边界与一条 `is_correct` 自洽**）
- [ ] 运行确认失败
- [ ] 实现（空作答短路 → 题型分支 → Jaccard → 阈值）
- [ ] 运行确认通过
- [ ] 提交

### Task 11.5：Mock 候选人反馈

- [ ] 写 §7.1 中 `test_mock_feedback_*` 五条失败测试
- [ ] 运行确认失败
- [ ] 实现（level 分支 + 未知取值退化为 summary + warning 日志）
- [ ] 运行确认通过
- [ ] 提交

### Task 11.6：真实 Provider

- [ ] 写 §7.2 九条测试（transport stub，**不打真实 API**）
- [ ] 运行确认失败
- [ ] 实现三个方法（prompt + 解析 + `is_correct` 本地推导 + 重试）
- [ ] 运行确认通过
- [ ] 提交

### Task 11.7：全量回归

- [ ] 运行 `pytest tests/ -q`，**全部通过**（重点：`test_interview.py`、`test_evaluation*.py`、`test_architecture.py`、`test_ai_factory.py`）
- [ ] 提交

---

## 9. 验收标准

- [ ] `AIProvider` 共 **7 个抽象方法**；`MockProvider` / `OpenAIProvider` 全部实现
- [ ] 三个新方法**只接收原始值**，无任何业务模块导入（`test_architecture.py` 通过）
- [ ] Mock 三个方法的输出**完全确定**：同输入必得同输出，无随机
- [ ] 空作答在**两个实现**中都短路为 0 分且**不发起网络请求**
- [ ] 简答判分严格按 §4.2 公式实现：空白规范化 → 字符二元组 → Jaccard → 一位小数 → 与 `PASS_THRESHOLD` 比较
- [ ] `score == 6.4` 判错、`== 6.5` 判对、`== 6.6` 判对（三条边界用例通过）
- [ ] `is_correct` 恒等于 `score >= PASS_THRESHOLD`，**不由模型输出决定**
- [ ] `PASS_THRESHOLD` 一处定义（`ai.base`），值为 `6.5`，与前端 `scoreClass` / `radar.js` 的及格线一致
- [ ] `generate_candidate_feedback(level='summary')` 的 `overall_score` 为 `None`；未知 level 退化为 `summary` 并记 warning
- [ ] 单选补参考答案返回的答案**必在 `options` 内**
- [ ] 「答案不在选项内」不由 `ai` 纠正（交由 `question` 判 409）
- [ ] `FailingProvider(AIProvider)` 测试替身已补齐三个方法，`test_interview.py` 零回归
- [ ] 既有 `test_mock_provider.py` 45 条、`test_openai_provider.py` 22 条零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **新增抽象方法会打断既有测试替身** | 补齐 `tests/test_interview.py` 的 `FailingProvider`；其余替身经核实不受影响 | 它是唯一直接子类。另一条路（把新方法设为非抽象的 `NotImplementedError` 默认实现）会削弱契约，让漏实现悄无声息 |
| **Mock 的 Jaccard 判分不代表真实评分质量** | 明确声明 Mock 只保证**可演示、可测试、确定性** | Mock 的职责是让无 Key 环境跑通闭环，不是模拟 LLM 的判断力。若把它当质量基准会造成误判 |
| **及格线在前后端各有一份** | 后端收敛到 `PASS_THRESHOLD`；前端 6.5 由 module-15 加注释互相指向 | 纯 JS 前端无法 import 后端常量；构建期共享方案（生成常量文件）对单机小项目属过度设计 |
| 未知 `level` 静默退化为 `summary` | 退化 + warning 日志 | 「给得更少」是安全方向，但配置拼写错误必须留下可见痕迹 |
| `is_correct` 本地推导而非取模型输出 | 本地推导 | 阈值必须唯一；模型输出的布尔值会引入第二个判据 |
| 单选判分在 `practice` 而非 `ai` | 保持 PRD §4.7 的分工，但 provider 内实现防御分支 | 避免 `practice` 与 `ai` 的职责在实现时被混同；防御分支保证误调用时行为可预期 |
| 题型常量在两个模块各定义一份 | 接受重复 | `ai` 不得依赖 `question`，与既有 `SOURCE_*` / `DIFFICULTY_*` 的处理一致 |
| 三个新方法是否影响 `factory.py` | 不影响 | 工厂只按配置构造实现，与方法数量无关 |
