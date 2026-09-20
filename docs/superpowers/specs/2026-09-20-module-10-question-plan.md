# question 模块执行计划书（MVP-2 题型与参考答案）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：question（题型扩展、选项、参考答案与解析、对刷题的供给）
**所属包**：`backend/app/question/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.3（题库新增字段）、§4.7（刷题取题）、§5.2（`question` 实体）、§6（`generate_reference_answer`）
**前置依赖**：[module-00](./2026-09-15-module-00-core-plan.md)、[module-01 auth](./2026-09-15-module-01-auth-plan.md)、[module-02 position](./2026-09-15-module-02-position-plan.md)、[module-03 question MVP-1](./2026-09-15-module-03-question-plan.md)、[module-11 ai](./2026-09-20-module-11-ai-plan.md)
**本模块被谁依赖**：[module-13 practice](./2026-09-20-module-13-practice-plan.md)（取题与判分依据）

> **与 module-03 的关系**：module-03 是本题库模块的 MVP-1 计划书，仍然有效。本文档是**增量**，冲突时以本文档为准（§3.1 的字段表为准绳）。

---

## Global Constraints（全局约束，摘自 PRD）

- 题目字段新增：**题型（单选 `single_choice` / 简答 `short_answer`）、选项列表、参考答案、解析**（§4.3）
- 题型取**枚举两值**；刷题仅做**文本问答**，不含编程题（§1.3）
- 题库**同时服务** HR 出题与候选人刷题（§1.2、§4.3）
- **候选人取题时不得下发参考答案与解析**（由 §4.7「提交后展示」与 §4.9 的脱敏原则推出）
- 参考答案与解析可由 HR 手工录入，简答题亦可**调 AI 生成后由 HR 确认**（§4.3）
- 数据隔离：题目的可见性仍按 `created_by`（§4.1）——**唯一例外见 §5.5**
- 统一响应格式 `{code, message, detail}`（§7）
- 分页不做（沿用 module-03）；**仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.3）

| 子职责 | 内容 | PRD |
|---|---|---|
| 题型扩展 | `question_type` 字段与两值枚举 | §4.3 |
| 选项 | 单选题的 `options` 列表及其校验 | §4.3 |
| 参考答案与解析 | `reference_answer` / `explanation` 字段、校验与落库 | §4.3 |
| 筛选扩展 | 列表新增按 `question_type` 筛选 | §4.3 |
| AI 补参考答案 | HR 触发「为一题生成参考答案与解析」的端点 | §4.3、§6 |
| **对刷题的供给契约** | 提供按条件取题的 repository/service 入口，以及**剥离参考答案**的对外视图 | §4.7 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **编程题 / 代码沙箱** | PRD §1.3 明确不做；题型只有两个取值，新增取值需先扩 PRD |
| **候选人侧取题端点** | 取题 HTTP 端点属 `practice` 模块（module-13）。本模块只提供**被调用**的供给契约，不注册候选人可见的路由 |
| **多选、判断、填空等题型** | PRD §4.3 只列单选与简答。YAGNI：多选会改变判分规则与选项 schema |
| **题干富文本 / 图片** | PRD 未要求，且富文本会引入 XSS 面（前端已声明「无 HTML 注入点」） |
| **题库发布 / 上架状态** | 见 §5.5 的隔离放宽说明与风险表 |
| 题目查重、相似题合并 | 不在 PRD 范围 |

### 1.3 依赖方向

```
question.router ──→ question.service ──→ question.repository ──→ question 表
                          │
                          ├──→ auth.service（scope_owner_id / ensure_resource_visible）
                          ├──→ position.service（岗位可见性与维度校验）
                          └──→ ai.get_provider()（补参考答案）

question ──→ core / auth / position / ai（单向）
question ✗→ interview / evaluation / practice（不变）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/question/models.py` | **改**：新增四个字段与 `question_type` 枚举 |
| `backend/app/question/schemas.py` | **改**：字段校验、`PracticeQuestionOut`、`PracticeFilters` |
| `backend/app/question/repository.py` | **改**：筛选条件扩展、`list_practice_candidates` |
| `backend/app/question/service.py` | **改**：创建/更新校验、`generate_reference_answer`、`list_practice_questions` |
| `backend/app/question/router.py` | **改**：新增 `POST /{id}/reference-answer`、列表增筛选参数 |

**测试文件**：`backend/tests/test_question_candidate_plan.py`（新增，覆盖本文档全部测试点）

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/alembic/versions/` | 新增迁移：加四列（**注意 JSON 列的分步写法，见 §3.3**） |
| `backend/script.sql` | 同步 `question` 表四列定义 |

---

## 3. 数据模型设计

### 3.1 表 `question`（对应 PRD §5.2，**本表为字段定义准绳**）

在 module-03 §3.1 的基础上新增四列：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `question_type` | ENUM('single_choice','short_answer') | NOT NULL, DEFAULT `'short_answer'`, INDEX | **新增**：题型 |
| `options` | JSON | NOT NULL, DEFAULT `[]` | **新增**：单选题的选项列表；简答题必须为空数组 |
| `reference_answer` | TEXT | **NULL** | **新增**：参考答案；单选题为某个选项的文本 |
| `explanation` | TEXT | **NULL** | **新增**：解析；可为空 |

**索引**

| 索引 | 字段 | 目的 |
|---|---|---|
| `ix_question_type` | (`question_type`) | 刷题按题型取题（§4.7） |

> `reference_answer` 与 `explanation` **允许为 NULL**：存量题目没有这两项，且 PRD §4.3 允许「AI 生成后由 HR 确认」——即存在「先有题、后有答案」的中间态。若设为 NOT NULL 并给空串默认值，会把「未填写」与「故意留空」混为一谈。

### 3.2 设计要点

| 要点 | 理由 |
|---|---|
| **`question_type` 默认 `short_answer`** | 存量题目全部是纯文本题目，按「简答」理解才符合事实。默认单选会凭空造出无选项的单选题 |
| **`options` 不建独立表** | 选项是题目的从属属性，量级小（≤10）、无需跨题查询。独立表会引入连接与排序字段（YAGNI，与 `tags` 用 JSON 同一判断） |
| **单选题的参考答案是选项文本，而非下标** | 选项可被编辑重排；存文本则重排后答案仍然正确。存下标会在编辑选项顺序时静默指向另一个选项——这是最危险的一类数据损坏 |
| **题干快照与参考答案不联动** | `interview_question.content_snapshot` 只快照题干（module-05 §3.2）。候选人在线答题看到的是快照，因此**天然不含参考答案**——这是既有设计带来的额外安全收益，本文档不改变它 |
| **两个新视图分离 HR 与候选人** | `QuestionOut`（HR，含答案）与 `PracticeQuestionOut`（候选人，剥离答案）。见 §4.2 |

### 3.3 迁移设计（**JSON 列是本次的坑**）

| 列 | 迁移写法 |
|---|---|
| `question_type` | `op.add_column` 一步完成：ENUM 支持 `server_default='short_answer'`，存量行自动取该值 |
| `reference_answer` / `explanation` | `op.add_column` 一步完成：可空 TEXT，无回填需求 |
| `options` | **必须分三步**：① 加**可空** JSON 列 → ② `UPDATE question SET options = JSON_ARRAY() WHERE options IS NULL` → ③ `alter_column` 改 NOT NULL |

> **为何 `options` 不能一步加完**：MySQL 不支持给 JSON 列一个普通的字面量默认值（8.0.13+ 才支持 `DEFAULT (JSON_ARRAY())` 这样的表达式默认值，且 SQLAlchemy 的 `server_default` 表达它很别扭）。对一张可能已有数据的表直接加 NOT NULL 且无默认值的 JSON 列会失败。分三步是跨版本都安全的写法，且第③步之后**去掉列默认值**，与模型定义（Python 侧 `default=list`）保持一致。

`downgrade()`：删四列与 `ix_question_type` 索引，无需数据保护（不涉及取值收回）。

---

## 4. 接口契约

### 4.1 对外 REST API（对应 PRD §8）

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/questions` | 创建题目（扩展字段） | admin, hr | 201 |
| GET | `/api/questions` | 列表（**新增 `question_type` 筛选**） | admin, hr | 200 |
| GET | `/api/questions/{id}` | 详情 | admin, hr | 200 |
| PUT | `/api/questions/{id}` | 更新（扩展字段） | admin, hr | 200 |
| DELETE | `/api/questions/{id}` | 删除 | admin, hr | 204 |
| POST | `/api/questions/{id}/reference-answer` | **新增**：调 AI 生成参考答案与解析并落库 | admin, hr | 200 |

> 本模块**不注册任何候选人可见的路由**。候选人取题走 `practice` 模块（module-13），它复用本模块的 `list_practice_questions`。

### 4.2 请求 / 响应结构

**`QuestionOut`（HR 视图，在 module-03 基础上增补字段）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `question_type` | str | `single_choice` \| `short_answer` |
| `options` | list[str] | 简答题为空数组 |
| `reference_answer` | str \| null | — |
| `explanation` | str \| null | — |

其余字段（`id` / `position_id` / `category` / `dimension` / `content` / `difficulty` / `tags` / `source` / `created_by` / `created_at`）不变。

**`PracticeQuestionOut`（候选人视图，新增）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` / `position_id` | int | — |
| `category` / `dimension` / `difficulty` | str | — |
| `content` | str | 题干 |
| `question_type` | str | 决定前端渲染单选还是文本框 |
| `options` | list[str] | **必须下发**，否则单选框无内容可渲染 |
| `tags` | list[str] | — |
| ~~`reference_answer`~~ | — | **不下发** |
| ~~`explanation`~~ | ~~str~~ | **不下发** |
| ~~`source` / `created_by` / `created_at`~~ | — | **不下发**：候选人无需知道题目来源与建题人 |

> **这是本模块最重要的安全边界**：`PracticeQuestionOut` 由 practice 在「取题」阶段使用；`reference_answer` 与 `explanation` 只在**提交作答之后**由 practice 的判分响应返回。若沿用 `QuestionOut` 直接下发，候选人一次请求就能拿到全部答案，刷题闭环失去意义。

**POST `/api/questions` / PUT `/api/questions/{id}` 新增请求字段**

| 字段 | 类型 | 约束 |
|---|---|---|
| `question_type` | str \| 可选 | 缺省 `short_answer` |
| `options` | list[str] \| 可选 | 缺省 `[]`；单选 2–10 个，单个 1–200 字符，strip 后去重 |
| `reference_answer` | str \| null \| 可选 | 单选题**必填**且须等于某个选项；简答题可空。≤ 2000 字符 |
| `explanation` | str \| null \| 可选 | ≤ 2000 字符 |

**GET `/api/questions` 新增查询参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `question_type` | str \| 可选 | `single_choice` \| `short_answer` |

**POST `/api/questions/{id}/reference-answer`**

| 方向 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 请求 | — | — | 无请求体（题目信息从路径与库中读取） |
| 响应 | `QuestionOut` | — | 已写回 `reference_answer` 与 `explanation` 的题目 |

### 4.3 字段校验规则（扩展 module-03 §3.3）

| 字段 | 规则 | 失败 |
|---|---|---|
| `question_type` | 取值 `single_choice` / `short_answer`；缺省 `short_answer` | 400 |
| `options` | `single_choice`：**2–10 个**，单个 1–200 字符，strip 后去重，去重后仍须 ≥ 2；`short_answer`：**必须为空数组** | 400 |
| `reference_answer` | `single_choice`：**必填**，且 strip 后必须等于 `options` 中某一项（**精确匹配**）；`short_answer`：可空；≤ 2000 字符 | 400 |
| `explanation` | 可空；≤ 2000 字符 | 400 |

> **「参考答案必须是某个选项」这条校验是单选题可判分的前提**：判分时是拿候选人选项与 `reference_answer` 做文本比较（§5.4），若答案不在选项内，则永远不可能判对。这里与 module-03 §3.3「`dimension` 必须属于岗位维度」是同一类防线。

### 4.4 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_question(db, user, data) -> Question` | Question | 增补新字段校验后落库 |
| `update_question(db, user, question_id, data) -> Question` | Question | 同上 |
| `list_questions(db, user, filters) -> list[Question]` | 列表 | 增补 `question_type` 筛选 |
| `generate_reference_answer(db, user, question_id) -> Question` | Question | 可见性校验 → 调 AI → 写回两个字段 |
| `list_practice_questions(db, filters: PracticeFilters, limit: int) -> list[Question]` | 列表 | **供 practice 取题**（§5.5） |

沿用（不改）：`get_question`、`delete_question`、`list_candidates_for_position`、`bulk_create_from_ai`。

### 4.5 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `list_filtered(db, owner_id, filters)` | 列表 | `filters` 增加 `question_type` |
| `list_practice_candidates(db, filters: PracticeFilters, limit: int) -> list[Question]` | 列表 | **新增**，按 `id` 升序；**不接 `owner_id`**（理由见 §5.5） |
| `get_by_id` / `create` / `update` / `delete` / `list_by_position` / `bulk_insert` | — | 不变 |

**`PracticeFilters` 字段**：`position_id: int | None`、`category: str | None`、`dimension: str | None`、`difficulty: str | None`、`question_type: str | None`。

### 4.6 对 `ai` 的调用点

| 调用 | 方法 | 说明 |
|---|---|---|
| 补参考答案 | `provider.generate_reference_answer(question_type, content, options, dimension)` | 见 [module-11 §3.1](./2026-09-20-module-11-ai-plan.md) |

**只传原始值**：传题型字符串、题干、选项列表、维度名——**不传 ORM 对象**（module-04 §3.4 的边界规则）。

---

## 5. 业务流程设计

### 5.1 创建 / 更新题目（扩展）

```
1. 岗位可见性校验（既有）
2. dimension 属于岗位维度（既有，module-03 §5.1）
3. 【新增】按 question_type 分支校验 options 与 reference_answer（§4.3）
4. 落库；source 仍由服务端决定
```

> 更新题目时 `question_type` 可改（简答 ↔ 单选），但改类型会同时触发第 3 步校验：例如把简答题改成单选题，必须一并提交合法的 `options` 与 `reference_answer`，否则 400。**不自动清空旧答案**——静默丢数据比报错更糟。

### 5.2 AI 补参考答案流程

```
1. service 取题并做可见性校验（404 / 403）
2. 调 provider.generate_reference_answer(题型, 题干, 选项, 维度)
3. 写回 reference_answer 与 explanation
4. 【单选题特例】若 AI 返回的答案不在 options 内，取 options 中与返回文本最接近的一项？—— 不。
   直接落库并提示：见下方决策
```

| 决策 | 说明 |
|---|---|
| **不做「AI 答案吸附到选项」的自动纠正** | AI 返回的文本若不在选项内，说明它可能给出了自己臆造的答案。此时静默改写为某个选项会**伪造正确答案**，比让 HR 看到不一致更危险。处理方式：`BusinessError`（409）「AI 生成的答案不在选项中，请手工确认」，**不落库**。HR 可改选正确选项后重试或手工填写 |
| 简答题无此问题 | 简答的参考答案是自由文本，直接落库 |
| **HR 的确认权** | PRD §4.3 要求「AI 生成后由 HR 确认」。本设计把「确认」落在**可编辑**上：生成只是把字段写回，HR 随后可用 PUT 修改任意内容。不引入「草稿/已确认」状态位（YAGNI） |
| AI 失败 | 抛 `AIProviderError`（502），不写库（沿用 module-04 §5.5「不自动降级到 Mock」） |

### 5.3 存量题目的影响

| 项 | 处理 |
|---|---|
| 已有题目 | 迁移后 `question_type='short_answer'`、`options=[]`、两个文本字段为 NULL |
| 能否刷题 | **能**，但只能作为简答题；无参考答案时判分被标记为未判分（module-13 §5.2） |
| 能否被面试抽取 | **能**，抽取逻辑（module-05 §5.2）只读 `content` 与 `dimension`，不受新字段影响 |
| 需要 HR 做什么 | 若要获得选择题刷题体验，需新录或改造单选题（见 §10 风险） |

### 5.4 单选题与简答题的判分依据（**供 practice 使用**）

| 题型 | 判分方 | 依据 | 归属 |
|---|---|---|---|
| `single_choice` | **practice 模块本地规则** | 候选人选项文本 strip 后与 `reference_answer` strip 后精确比较 | module-13 |
| `short_answer` | **`ai.grade_practice_answer`** | 题干 + 参考答案 + 候选人作答 | module-11 |

> 本模块**不实现判分**，只保证「单选题的 `reference_answer` 一定落在 `options` 内」（§4.3 校验），从而让 practice 的等值比较成立。判分阈值全项目统一为 **6.5**，定义见 module-11 §3.3。

### 5.5 对 practice 的供给契约（**含一处有意的隔离放宽**）

| 项 | 契约 |
|---|---|
| 方法 | `service.list_practice_questions(db, filters: PracticeFilters, limit: int) -> list[Question]` |
| 排序 | 按 `id` 升序，保证取题结果**确定可复现**（与 module-03 §4.4「出题候选查询按 id 升序」同一理由） |
| 数量 | `limit` 必须有上限（module-13 建议 20），防止一次拉全库 |
| 过滤 | 按 `position_id` / `category` / `dimension` / `difficulty` / `question_type` |
| **不按 `created_by` 过滤** | ⚠️ **有意放宽**，见下 |

**为何刷题取题不按 `created_by` 过滤**：候选人不是题目的创建者（`question.created_by` 是 HR）。若沿用 `scope_owner_id` 判据，候选人取不到任何题目——刷题功能直接不可用。因此刷题取题**取全库题目**。

| 影响 | 评估 |
|---|---|
| 候选人可看到所有 HR 建的题目 | 可接受：题目**本来就要展示给候选人**（题干是刷题内容），不是敏感数据 |
| 跨 HR 数据是否泄露 | 泄露面仅限题干与维度；`PracticeQuestionOut` 已剥离 `created_by`、`source`、参考答案 |
| 未来若需多租户 / 按岗位发布 | 需引入「题目发布状态」或「岗位归属可见性」。**本 MVP 明确不做**，已记入 §10 风险 |

> 这是本次设计里**唯一一处对数据隔离的放宽**，必须显式记录在案，不能让它以「忘了过滤」的形式存在。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 单选题未提供 `options` 或不足 2 项 | `VALIDATION_ERROR` | 400 | 单选题至少需要 2 个选项 |
| 简答题带了 `options` | `VALIDATION_ERROR` | 400 | 简答题不应包含选项 |
| 单选题 `reference_answer` 缺失 | `VALIDATION_ERROR` | 400 | 单选题必须提供参考答案 |
| `reference_answer` 不在 `options` 内 | `VALIDATION_ERROR` | 400 | 参考答案必须是选项之一（`detail` 含 `options` 列表） |
| 选项重复（strip 后） | `VALIDATION_ERROR` | 400 | 选项不能重复 |
| 选项/答案/解析超长 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| 题型取值非法 | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| AI 返回的答案不在选项中 | `BUSINESS_ERROR` | 409 | AI 生成的答案不在选项中，请手工确认 |
| AI 调用失败 | `AI_PROVIDER_ERROR` | 502 | AI 服务调用失败，请稍后重试 |
| 题目不存在 / 不可见 | `NOT_FOUND` / `FORBIDDEN` | 404 / 403 | 题目不存在 / 无权限访问该题目（既有行为） |

---

## 7. 测试设计（对应 PRD §10）

### 7.1 字段校验

| 测试 | 断言 |
|---|---|
| `test_create_single_choice_ok` | 201，`question_type`/`options`/`reference_answer` 正确落库 |
| `test_create_single_choice_without_options` | 400，message 为「单选题至少需要 2 个选项」 |
| `test_create_single_choice_single_option` | 只给 1 个选项 → 400 |
| `test_create_single_choice_without_reference` | 400，message 为「单选题必须提供参考答案」 |
| `test_create_single_choice_reference_not_in_options` | 400，`detail` 含 `options` |
| `test_create_single_choice_duplicate_options` | 选项 strip 后重复 → 400 |
| `test_create_short_answer_with_options` | 400，message 为「简答题不应包含选项」 |
| `test_create_short_answer_without_reference_ok` | 201，两个文本字段为 NULL |
| `test_create_default_question_type_is_short_answer` | 不传 `question_type` → 落库为 `short_answer` |
| `test_create_invalid_question_type` | 400 |
| `test_update_short_answer_to_single_choice_requires_full_payload` | 300+ 缺选项 → 400；补齐后 200 |
| `test_update_does_not_silently_clear_reference` | 改题干后 `reference_answer` 保持不变 |

### 7.2 AI 补参考答案

| 测试 | 断言 |
|---|---|
| `test_generate_reference_answer_short_answer` | 200，两个字段非空 |
| `test_generate_reference_answer_single_choice_picks_option` | Mock 返回的答案落在 `options` 内，落库成功 |
| `test_generate_reference_answer_rejects_answer_out_of_options` | 构造返回选项外文本的 Provider → 409 `BUSINESS_ERROR`，且**库中字段未被修改** |
| `test_generate_reference_answer_ai_failure` | Provider 抛 `AIProviderError` → 502，库中字段未被修改 |
| `test_generate_reference_answer_visibility` | 他人题目 → 403；不存在 → 404 |
| `test_generate_reference_answer_passes_raw_values` | 用 spy Provider 断言收到的参数是 str / list[str]，**不是 ORM 对象**（module-04 §3.4） |

### 7.3 筛选与供给契约

| 测试 | 断言 |
|---|---|
| `test_list_filter_by_question_type` | 只返回指定题型 |
| `test_list_filter_combined` | 题型 + 难度 + 维度组合筛选为 AND 关系 |
| `test_list_practice_candidates_ignores_owner` | **由 hr_a 与 hr_b 各建一题**，`list_practice_questions` 两题都返回（§5.5 放宽） |
| `test_list_practice_candidates_order_by_id` | 返回顺序与 `id` 升序一致（可复现） |
| `test_list_practice_candidates_respects_limit` | `limit` 生效 |
| `test_list_practice_candidates_filter_by_type` | 按题型过滤生效 |

### 7.4 候选人视图剥离答案

| 测试 | 断言 |
|---|---|
| `test_practice_question_out_has_no_reference_answer` | 序列化结果**不含** `reference_answer` 键 |
| `test_practice_question_out_has_no_explanation` | **不含** `explanation` 键 |
| `test_practice_question_out_has_no_source_or_creator` | **不含** `source` / `created_by` / `created_at` |
| `test_practice_question_out_keeps_options` | 单选题的 `options` **必须存在**（前端要渲染选项） |

### 7.5 存量数据回归

| 测试 | 断言 |
|---|---|
| `test_existing_questions_default_to_short_answer` | 迁移后既有题目的题型为 `short_answer`、`options` 为 `[]` |
| `test_existing_questions_still_extractable_by_interview` | `list_candidates_for_position` 仍返回既有题目（module-05 §5.2 未受影响） |
| `test_question_out_includes_new_fields` | HR 的题目响应包含四个新字段（前端 module-07 的表单可扩展） |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 10.1：模型与迁移

- [ ] `models.py` 新增 `QUESTION_TYPE_*` 常量、四个字段与 `ix_question_type` 索引
- [ ] 生成迁移，**`options` 列按 §3.3 的三步写法**
- [ ] 同步 `backend/script.sql`
- [ ] 写 §7.5 的 `test_existing_questions_default_to_short_answer`
- [ ] 运行 `alembic upgrade head` / `downgrade` 验证
- [ ] 提交

### Task 10.2：schema 与字段校验

- [ ] schema 增补四个字段与校验（§4.3）
- [ ] 写 §7.1 全部失败测试
- [ ] 运行确认失败 → 实现 → 通过
- [ ] 提交

### Task 10.3：新增 `PracticeQuestionOut` 与 `PracticeFilters`

- [ ] 定义两个 schema
- [ ] 写 §7.4 四条剥离测试（**含 `options` 必须保留**）
- [ ] 运行确认通过
- [ ] 提交

### Task 10.4：repository 与筛选扩展

- [ ] `list_filtered` 增加 `question_type`
- [ ] 新增 `list_practice_candidates`（按 id 升序、支持 limit）
- [ ] 写 §7.3 全部测试
- [ ] 运行确认通过
- [ ] 提交

### Task 10.5：AI 补参考答案

- [ ] 写 §7.2 六条测试（**含「答案不在选项中不落库」与「不传 ORM」**）
- [ ] 运行确认失败
- [ ] 实现 `service.generate_reference_answer` 与 `POST /questions/{id}/reference-answer`
- [ ] 运行确认通过
- [ ] 提交

### Task 10.6：全量回归

- [ ] 运行 `pytest tests/ -q`，`test_question.py` 既有 44 条与全部其他用例通过
- [ ] 提交

---

## 9. 验收标准

- [ ] `question` 表含 `question_type` / `options` / `reference_answer` / `explanation` 四列，迁移可升降级
- [ ] 存量题目迁移后 `question_type='short_answer'`、`options=[]`，仍可被面试抽取
- [ ] 单选题必须 ≥ 2 个不重复选项，且参考答案必须是其中之一（否则 400）
- [ ] 简答题不得带选项（否则 400）
- [ ] 改题型不会静默清空已有参考答案
- [ ] `POST /questions/{id}/reference-answer` 可生成并落库；**答案不在选项内时 409 且不落库**
- [ ] 列表可按 `question_type` 筛选，且与既有筛选为 AND 关系
- [ ] `PracticeQuestionOut` **不含** 参考答案、解析、来源、建题人；**必须含** 选项
- [ ] 刷题取题**不按 `created_by` 过滤**（跨 HR 题目均可取），且记录在案（§5.5）
- [ ] 对 `ai` 的调用**只传原始值**
- [ ] 既有 `test_question.py` 44 条零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **MySQL JSON 列不能一步加为 NOT NULL** | 迁移分三步（§3.3） | 对已有数据的表直接加 NOT NULL 无默认值的 JSON 列会失败；分三步跨版本安全 |
| **刷题取题不按 `created_by` 过滤** | 有意放宽，已显式记录 | 候选人非题目创建者，沿用 owner 判据会导致无题可取。泄露面仅题干与维度，且候选人本就该看到题干 |
| **存量题目全是简答题** | 接受，MVP 不自动改造 | 迁移把存量题定为简答是唯一符合事实的选择；选择题刷题体验需 HR 新录。若演示需要选择题，应在 seed/演示脚本中补几道（module-16 §7 收尾项） |
| 参考答案存文本而非选项下标 | 存文本 | 存下标会在选项重排后静默指向另一选项——静默的错误答案比报错更危险 |
| AI 答案不在选项内 | 409 拒绝且不落库，不自动吸附 | 自动吸附等于伪造正确答案 |
| 是否需要「题目发布状态」 | 明确不做 | PRD 未要求；引入会牵出发布/下架状态机与候选人可见性规则。已记入本表，未来多租户时再议 |
| `PracticeQuestionOut` 放在 question 而非 practice | 放在 question | 它描述的是 `question` 实体的对外视图；放在 practice 会让「剥离答案」这条安全规则离数据定义更远 |
| `explanation` 与 `reference_answer` 是否合并 | 分两列 | 语义不同：参考答案用于判分，解析用于教学。合并后「有答案无解析」无法表达 |
