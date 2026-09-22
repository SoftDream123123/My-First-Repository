# ai 简历评估能力 执行计划书（MVP-4 §4.15）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：ai **MVP-4 增量**（新增 `evaluate_resume` 能力：对简历与岗位做匹配度评估）
**所属包**：`backend/app/ai/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.15（简历 AI 评估）、§6（AI Provider 接口契约）、§5.3 ⑧
**前置依赖**：[module-04 / module-11 / module-18 ai](./2026-09-21-module-18-ai-plan.md)（本模块是它的增量，**不重复其内容**）
**本模块被谁依赖**：[module-28 interview 简历评估端点](./2026-09-22-module-28-interview-resume-review-plan.md)、[module-30 e2e](./2026-09-22-module-30-e2e-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **`ai` 不依赖任何业务模块**：本能力的入参全是**原始值**（岗位名 / JD / 维度列表 / 简历正文），不含任何 ORM 对象、不含 position_id / resume_id（§6、module-08 §5.3-5）
- **Mock 必须确定性**：同输入必得同输出，不允许随机数、时间戳、字典序依赖（module-04 既有约定）
- 匹配度分用**全项目同一把尺** `SCORE_MIN`–`SCORE_MAX`（0–10），不另算一套（§6）
- `resume_text` 为空、`dims` 为空 → **抛 `AIProviderError`**，与 `match_questions_by_resume` 同款（§6）
- **只评不挑**：不接触题库，不返回任何题目 id（§6）
- **本能力不做脱敏**：`summary` / `full` 档位是**端点层**的事，不是 AI 层的事（§4.15、module-28 §5.2）
- **不引入新依赖、不新增配置项**（§2）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| 抽象契约 | `AIProvider.evaluate_resume` 抽象方法 + 入参约束的 docstring | §6 |
| 结果载体 | 新增 dataclass `ResumeReviewResult` | §6 |
| Mock 实现 | 规则驱动的确定性评估（二元组覆盖率） | §4.15 |
| 真实实现 | 构造 prompt → 要求 JSON → 解析与校验 | §6 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **按档位脱敏（不下发分数）** | 那是**端点层**的视图职责（module-28 §5.2）。AI 层不该知道调用者是 HR 还是候选人——这与 `generate_candidate_feedback` 传 `level` **刻意不同**，理由见 §5.4 |
| **落库 / 缓存** | PRD §4.15 明确「不落库、每次现算」。ai 层本来就没有 DB 会话（module-04 既有设计） |
| **读岗位 / 读简历 / 判权限** | 全是调用方（`interview`）的职责；ai 只收原始值（§6） |
| **多候选人横向对比** | PRD §1.3 非目标 |
| **简历结构化解析**（抽取技能/年限字段） | PRD §4.10 未要求；本能力直接在正文上算覆盖率 |
| **OCR / 文件解析** | 属 module-25，与本模块无关 |
| **端点、前端、e2e** | 属 module-28 / 29 / 30 |

---

## 2. 文件结构

**本模块需修改的文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/ai/base.py` | 新增 dataclass `ResumeReviewResult`；`AIProvider` 新增抽象方法 `evaluate_resume` |
| `backend/app/ai/mock_provider.py` | 实现 `evaluate_resume` + 私有辅助函数 |
| `backend/app/ai/openai_provider.py` | 实现 `evaluate_resume` |
| `backend/tests/test_ai_mock_provider.py`（或既有的 ai 测试文件） | 新增 Mock 用例 |

> **`factory.py` / `__init__.py` 不需改**：工厂只做 Provider 选择，不枚举方法。
>
> **`test_architecture.py` 不需改**：`ai` 的约束是「不依赖业务模块」，本模块仍只依赖标准库与 `core.exceptions`。
>
> **新增抽象方法会立刻让两个实现类编译不过**，这是有意的——ABC 的作用就是逼两套实现同时补齐。**不要为了「先跑起来」把它写成带默认实现的普通方法**。

---

## 3. 结果载体契约

**`ResumeReviewResult`**（`base.py`，与既有 `InterviewPrepResult` 等同层）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `match_score` | float | `SCORE_MIN` ≤ x ≤ `SCORE_MAX`（0–10），保留 1 位小数 | 岗位匹配度分 |
| `conclusion` | str | 非空 | 综合结论（一段话），**不含去留判断** |
| `strengths` | list[str] | 1–5 条 | 亮点 / 匹配点 |
| `gaps` | list[str] | 0–5 条 | 差距 / 建议补充项 |

| 决策 | 理由 |
|---|---|
| **`gaps` 允许为空，`strengths` 不允许** | 「这份简历没什么明显差距」是可能的正当结论；但「一条亮点都找不到」意味着评估本身失败了，说明输入或算法有问题。允许 strengths 为空会让「评分坏了」与「简历真的差」不可区分——与 module-18「『没有』与『坏了』必须可区分」同一原则 |
| **不复用 `ReportResult` / `CandidateFeedbackResult`** | 三者语义不同：`ReportResult` 是面试后的总分结论、`CandidateFeedbackResult` 是报告的脱敏重写、本结果是**岗位匹配度**。共用一个 dataclass 会让字段名（`overall_score` vs `match_score`）失去含义 |
| **不含 `dimension_scores`** | 逐维度打分是面试评估的能力（§4.5）。简历评估按 §4.15 只产出四项，多给维度分会让前端多画一个雷达图，而 PRD 未要求 |
| **`match_score` 恒为 float，不用 `float \| None`** | 「候选人看不到分数」是**端点**的视图行为（module-28 的 schema 负责），不是 AI 层的产出差异。让 AI 层返回 None 会把授权逻辑混进能力层 |

---

## 4. 接口签名

### 4.1 抽象方法

| 签名 | 说明 |
|---|---|
| `evaluate_resume(position_name: str, jd: str, dims: list[str], resume_text: str) -> ResumeReviewResult` | 见 `base.py` 的 docstring 契约 |

**入参约束（写进 docstring）**

| 入参 | 约束 |
|---|---|
| `position_name` | 岗位名；空则用「该岗位」兜底，**不抛错**（与 `generate_interview_prep` 的 `candidate_name` 同一处理） |
| `jd` | 岗位描述；允许为空（岗位可以不填 JD），此时评估依据只剩 `dims` |
| `dims` | **必填**，为空抛 `AIProviderError`（没有维度就没有评估依据，PRD §4.15 的前置条件正是这条） |
| `resume_text` | **必填**，为空或全空白抛 `AIProviderError`（与 `match_questions_by_resume` 同款；调用方本应先判出「未关联简历」而整条路都不调用它） |

> **`resume_text` 抛错而 `jd` 不抛错**，这条不对称是刻意的：简历是**被评估的对象**，没有它评估无从谈起；JD 只是**评估依据之一**，岗位可以只有维度没有 JD，此时仍能给出有意义的评估。**执行时不要「顺手统一」成两者都必填。**

### 4.2 Mock 实现算法（确定性）

```
evaluate_resume(position_name, jd, dims, resume_text):
1. 前置校验（§4.1）→ 不满足抛 AIProviderError
2. 依据文本 basis = jd + 各维度名拼接
3. 覆盖度 coverage = _overlap_ratio(basis 的二元组, resume_text 的二元组)
     ← 复用既有的「以依据自身大小作分母」的算法（module-04 的 _resume_overlap
       已经把「为什么不用 Jaccard」的理由写在注释里，本模块沿用同一函数）
4. match_score = round1(SCORE_MIN + coverage * (SCORE_MAX - SCORE_MIN))
     再夹到 [SCORE_MIN, SCORE_MAX]
5. 逐维度算覆盖度：
     覆盖度 > 0 的维度，按覆盖度降序 → strengths（至多 5 条，
       文案：「简历中体现了{维度}相关经历」）
     覆盖度为 0 的维度，按维度名原序 → gaps（至多 5 条，
       文案：「简历中未见{维度}相关经历，建议补充具体事例」）
6. 若 strengths 为空（所有维度都没命中）→ 用一条兜底亮点，保证非空
7. conclusion 由 match_score 落档生成（见下表），**措辞不含去留判断**
8. 返回 ResumeReviewResult
```

**结论档位文案（必须避开去留判断）**

| 分数区间 | 结论方向 |
|---|---|
| ≥ 8.0 | 简历与岗位要求的重合度高，多维度的经历都有体现 |
| 6.5 – 8.0（含 `PASS_THRESHOLD`） | 简历与岗位要求有较好重合，部分维度可再补充具体事例 |
| 4.0 – 6.5 | 简历与岗位要求部分重合，多个维度缺少可对应的经历描述 |
| < 4.0 | 简历与该岗位要求重合较少，建议按岗位维度补充相关经历与成果 |

> ⚠️ **措辞红线**：任何档位都**不得**出现「建议进入下一轮 / 不建议继续推进 / 建议淘汰 / 符合录用标准」这类**去留判断**。这是 §4.9 已确立的原则，§4.15 明确沿用。上面四档说的都是**简历与岗位的重合度**，不是「要不要这个人」。
>
> **档位边界用 `PASS_THRESHOLD`（6.5）对齐**：与 `summarize_report` 同一把尺，避免「面试 6.5 算过、简历 6.5 算不过」这种内部不一致。

> **为什么 Mock 也要算真东西**：Mock 是自动化测试的基准，也是无 Key 演示时的产出。若它只返回一句固定文案，测试就测不出「维度覆盖影响结论」这条逻辑，演示也看不出简历质量与结论的关系。**但确定性不能破**：算法里不能有随机、不能有集合遍历顺序依赖（`_bigrams` 返回 set，聚合时必须先排序——这是 module-04 踩过的坑，注释里已记录）。

### 4.3 真实实现（OpenAI Provider）

| 环节 | 做法 |
|---|---|
| 前置校验 | 与 Mock **完全一致**（同一套抛错条件） |
| prompt | system：资深招聘顾问，评估简历与岗位的匹配度；user：岗位名 + JD + 维度列表（JSON）+ 简历正文，要求输出 JSON |
| 期望输出 | `{"match_score": float, "conclusion": str, "strengths": [str], "gaps": [str]}` |
| 解析 | 复用既有的 JSON 解析与容错工具（module-18 已建立） |
| 校验 | `match_score` 非数值 → `AIProviderError`；数值则夹到 `[SCORE_MIN, SCORE_MAX]` 并 `round1`；`strengths` 为空 → `AIProviderError`（§3 的「不许空」）；`gaps` 空则接受 |
| 措辞约束 | prompt 里**显式要求**「不得给出录用与否的建议，只描述简历与岗位的重合度」 |
| 失败 | 任何解析/校验失败 → `AIProviderError`，由端点转 502（module-28 §6） |

> **prompt 里的措辞约束是必要的一层，但不是唯一一层**：模型可能不遵守。因此 §5.5 的测试要**断言输出结构与分数区间**；「文案里没出现去留判断」这条只对 Mock 做硬断言（Mock 是我们自己写的，可控），对真实 Provider 由 prompt 约束 —— **这一点要在 module-30 的遗留项里如实记录**。

---

## 5. 关键设计说明

### 5.1 为什么不放在 `resume` 包

`resume` 包**禁止依赖 `position`**（`test_architecture.py` 的 `FORBIDDEN_DEPENDENCIES["resume"]`）。而本能力需要岗位的 JD 与评估维度。因此能力虽与「简历」相关，**调用方位只能是 `interview`**（module-28）。

> ai 层本身仍只收原始值，所以**这条架构约束对本模块无影响**——它影响的是端点放哪。

### 5.2 为什么 ai 层不做脱敏

`summary` / `full` 是**「谁在看」**的问题。`ai` 是一个能力层，它不该知道调用者是 HR 还是候选人；把这个开关塞进来，等于让能力层依赖授权语义。**端点层持有调用者身份，由它决定下发什么**（module-28 §5.2）。

### 5.3 与 `match_questions_by_resume` 的分工

| | `match_questions_by_resume` | `evaluate_resume` |
|---|---|---|
| 输入 | 简历 + 岗位 + **题库候选池** | 简历 + 岗位 |
| 输出 | 题目 id + 匹配理由 | 分数 + 结论 + 亮点 + 差距 |
| 与 AI 的关系 | 从既有池子里**挑** | 对简历**评** |
| 写库 | 由调用方追加题目 | **不写** |

> 两者都吃 `resume_text`，但一个是「挑题」一个是「评人」。**不要为了「复用」把两者合并成一个方法**——合并后调用方每次都要多传一个题库池，而评估根本不需要它。

### 5.4 与 `generate_candidate_feedback` 传 `level` 的差异（执行时最易起疑的一处）

`generate_candidate_feedback(level=...)` 把档位**传进了 ai 层**；本模块**不传**。这不是疏漏：

| | 为什么档位要在 ai 层 |
|---|---|
| `generate_candidate_feedback` | 档位**改变产出文案本身**——`summary` 与 `full` 的结论是两份不同的文本（`_candidate_conclusion` 的逻辑依赖档位）。既然文案不同，就只能是生成时决定 |
| `evaluate_resume` | 档位**只决定「分数发不发」**，四种产出的文本完全一样。后缀裁剪是纯视图操作，放在端点层即可，且这样 ai 层能保持「与调用者身份无关」 |

### 5.5 测试要点

| # | 用例 | 断言 |
|---|---|---|
| 1 | **确定性**：同一输入连调两次 | 两个 `ResumeReviewResult` 逐字段相等 |
| 2 | `resume_text=""` / `"   "` | 抛 `AIProviderError` |
| 3 | `dims=[]` | 抛 `AIProviderError` |
| 4 | 简历高度覆盖 JD 与维度 | `match_score` 明显高于「简历与维度无关」那一组 |
| 5 | `match_score` 范围 | 恒在 `[SCORE_MIN, SCORE_MAX]`，且为 1 位小数 |
| 6 | `strengths` 非空 | **任何输入下都非空**（含「全维度未命中」的兜底分支） |
| 7 | `gaps` 覆盖未命中维度 | 未命中的维度名出现在 `gaps` 里 |
| 8 | **措辞红线** | `conclusion` 对四档分数分别断言**不含**「进入下一轮」「不建议」「淘汰」「录用」等词 |
| 9 | `strengths` / `gaps` 条数 | 各不超过 5 条 |
| 10 | 两个 Provider 的入参校验一致 | Mock 抛错的输入，真实 Provider 在**发起请求前**也抛错（用不可达的 base_url 验证「没发请求」） |
| 11 | `position_name` 为空 | 正常运行，不抛错（兜底为「该岗位」） |
| 12 | `jd` 为空、`dims` 非空 | 正常运行 |

---

## 6. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | `AIProvider` 新增抽象方法后，**两个实现都补齐**，无遗漏 | 类实例化不报 `TypeError` |
| 2 | Mock 确定性用例通过 | §5.5 用例 1 |
| 3 | 措辞红线用例通过 | §5.5 用例 8 |
| 4 | 既有 ai 测试全绿（**无回归**） | `pytest backend/tests/test_ai*.py` |
| 5 | `test_architecture.py` 全绿且**未改动** | 同上 |
| 6 | 无新增依赖、无新增配置项 | `git status` + `requirements.txt` 未动 |
