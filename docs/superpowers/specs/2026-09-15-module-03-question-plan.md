# question 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：question（题库）
**所属包**：`backend/app/question/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.3（题库管理）、§5.2（`question` 实体）、§8（question API）
**前置依赖**：core（[module-00](./2026-09-15-module-00-core-plan.md)）、auth（[module-01](./2026-09-15-module-01-auth-plan.md)）、position（[module-02](./2026-09-15-module-02-position-plan.md)）

---

## Global Constraints（全局约束，摘自 PRD）

- 后端分层：**router → service → repository → MySQL，严格单向依赖**（§2、§3.2）
- 每个模块独立 Python package（§2、§3.3）
- 统一响应格式：**`{code, message, detail}`**（§7）
- 统一前缀 `/api`，**除登录外均需 JWT**（§8）
- **数据隔离：普通 HR 只能访问自己创建的数据；admin 可访问全部**（§4.1）
- 仅 PC 端（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.3）

| 子职责 | 内容 |
|---|---|
| 题目实体 | `question` 表的定义与迁移 |
| 题库管理 | 题目的增、查、改、删（PRD §4.3） |
| 多维筛选 | 按岗位 / 分类 / 维度筛选（PRD §4.3） |
| 出题供给 | 为 interview 的出题组装提供候选题目查询（PRD §4.3「可被面试抽取复用」、§5.3 ①） |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **抽取与组装** | 从题库抽 N 题、与 AI 题目合并、生成快照，全部属于 interview 模块（PRD §5.3 ①）。question 只提供「给定岗位，返回候选题目」的查询能力 |
| **题目去重 / 相似度检测** | 不在 PRD 范围 |
| **题目导入导出** | 不在 PRD 范围 |
| **岗位维度的级联同步** | 岗位维度变更后，历史题目的 `dimension` 不做强制迁移（见 §5.5） |
| **反向查询面试** | 「题目是否被面试引用」由数据库外键约束判定，处理方式与 position §5.3 一致 |

### 1.3 依赖方向（对应 PRD §3.3）

```
question.router ──→ question.service ──→ question.repository ──→ question 表
                          │
                          ├──→ core.deps.get_current_user
                          ├──→ auth.service.scope_owner_id
                          └──→ position.service.get_position（校验岗位存在与可见性）

question ──→ core, auth, position（单向）
interview ──→ question（查询候选题目、写入 AI 题目）
question ✗→ interview（不反向依赖）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/question/__init__.py` | 包标识 |
| `backend/app/question/models.py` | `Question` 模型定义 |
| `backend/app/question/schemas.py` | 请求 / 响应 Pydantic 模型 + 字段校验 |
| `backend/app/question/repository.py` | `question` 表数据访问（含 `owner_id` 过滤与多维筛选） |
| `backend/app/question/service.py` | 业务逻辑：CRUD、岗位与维度校验、候选查询 |
| `backend/app/question/router.py` | `/api/questions/*` 端点 |

**测试文件**：`backend/tests/test_question.py`

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 question router |
| `backend/alembic/versions/` | 新增 `question` 表迁移 |

---

## 3. 数据模型设计

### 3.1 表 `question`（对应 PRD §5.2 的 `question` 实体）

PRD §5.2 列出字段：`id, position_id, category, dimension, content, difficulty, tags, source`。本设计补充 `created_by` 与 `created_at`：

| 字段 | 类型 | 约束 | 说明 | 来源 |
|---|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 | PRD §5.2 |
| `position_id` | BIGINT | NOT NULL, FK → `position.id` **RESTRICT**, INDEX | 所属岗位 | PRD §5.2 |
| `category` | VARCHAR(50) | NOT NULL, DEFAULT `'通用'` | 题目分类（如 技术 / 行为 / 场景 / 通用） | PRD §5.2 |
| `dimension` | VARCHAR(50) | NOT NULL, INDEX | 对应评估维度 | PRD §5.2 |
| `content` | TEXT | NOT NULL | 题干 | PRD §5.2 |
| `difficulty` | ENUM('easy','medium','hard') | NOT NULL, DEFAULT `'medium'` | 难度 | PRD §5.2 |
| `tags` | JSON | NOT NULL, DEFAULT `[]` | 标签列表 | PRD §5.2 |
| `source` | ENUM('bank','ai') | NOT NULL, DEFAULT `'bank'`, INDEX | 来源 | PRD §5.2 |
| `created_by` | BIGINT | NOT NULL, FK → `user.id`, INDEX | **创建人，数据隔离依据** | **本设计新增** |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — | **本设计新增** |

**为何必须新增 `created_by`**：PRD §4.1 要求「普通 HR 只能访问自己创建的数据」。`question` 若要参与数据隔离，就必须有归属字段。`created_at` 则为其余所有实体一致的审计字段。

**索引**

| 索引 | 字段 | 类型 | 目的 |
|---|---|---|---|
| `ix_question_position_owner` | (`position_id`, `created_by`) | INDEX | **出题取数的主查询路径**（PRD §5.3 ①） |
| `ix_question_dimension` | (`dimension`) | INDEX | 按维度筛选（PRD §4.3） |
| `ix_question_source` | (`source`) | INDEX | 按来源筛选 |
| `ix_question_created_by` | (`created_by`) | INDEX | 数据隔离过滤（PRD §4.1） |

### 3.2 设计要点

| 要点 | 理由 |
|---|---|
| **`position_id` 外键 `ON DELETE RESTRICT`** | 题目必须挂在岗位上；岗位被题目引用时不可删除（position §5.3） |
| **`dimension` 存字符串而非 ID** | 与 `evaluation.dimension_score.dimension` 保持同一命名空间，评估打分时可直接按维度名归集，无需联表（PRD §5.2） |
| **`created_by` 与岗位的 `created_by` 可能不同** | 数据隔离以**题目自身的 `created_by`** 为准；正常情况下二者一致（创建题目时会校验岗位可见性）。admin 可为他人岗位建题，此时以建题人为准 |
| **`tags` 用 JSON 数组** | 标签是弱结构属性，不需要独立标签表与多对多关联（YAGNI） |
| **`difficulty` 用枚举** | 限定取值，避免脏数据；AI 生成时也映射到这三档 |
| **无内容唯一约束** | 允许同岗位存在内容相近的题目。AI 可能生成近似题目，强制唯一会造成**入库失败而非可解释的报错** |

### 3.3 字段校验规则

PRD §4.3 未定义字段边界，本设计补齐：

| 字段 | 规则 | 失败 |
|---|---|---|
| `position_id` | 必填；岗位必须存在且对当前用户**可见** | 404 / 403 |
| `dimension` | 必填，1–50 字符；**必须属于所属岗位的 `evaluation_dimensions`**（strip 后精确匹配） | 400 `VALIDATION_ERROR` |
| `category` | 可选；缺省 `"通用"`；1–50 字符 | 400 |
| `content` | 必填，**5–2000 字符** | 400 |
| `difficulty` | 可选；缺省 `medium`；取值 `easy`/`medium`/`hard` | 400 |
| `tags` | 可选；缺省 `[]`；**≤ 10 个**；单个 1–20 字符；strip 后去重 | 400 |
| `source` | **客户端不可指定**，由服务端决定（见 §5.4） | — |

> **`dimension` 必须属于岗位维度**这一校验是本模块最重要的数据质量防线：它保证「题目 → 岗位 → 维度」三者自洽，是后续「多维评分」能正确归集数据的前提（PRD §4.5）。

---

## 4. 接口契约（对应 PRD §8）

### 4.1 对外 REST API

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/questions` | 创建题目 | 登录 + 岗位可见 | 201 |
| GET | `/api/questions` | 题目列表（支持多维筛选） | 登录 | 200 |
| GET | `/api/questions/{id}` | 题目详情 | 登录 + 可见 | 200 |
| PUT | `/api/questions/{id}` | 更新题目 | 登录 + 可见 | 200 |
| DELETE | `/api/questions/{id}` | 删除题目 | 登录 + 可见 | **204** |

### 4.2 请求 / 响应结构

**Question 响应对象**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | — |
| `position_id` | int | — |
| `category` | str | — |
| `dimension` | str | — |
| `content` | str | — |
| `difficulty` | str | `easy` \| `medium` \| `hard` |
| `tags` | list[str] | — |
| `source` | str | `bank` \| `ai` |
| `created_by` | int | — |
| `created_at` | datetime | ISO 8601 |

**POST `/api/questions`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `position_id` | int | 必填 |
| 请求 | `category` | str \| 可选 | 缺省 `"通用"` |
| 请求 | `dimension` | str | 必填，须属岗位维度 |
| 请求 | `content` | str | 必填，5–2000 字符 |
| 请求 | `difficulty` | str \| 可选 | 缺省 `medium` |
| 请求 | `tags` | list[str] \| 可选 | 缺省 `[]` |

**GET `/api/questions` 查询参数**（PRD §4.3 要求支持按岗位 / 分类 / 维度筛选）

| 参数 | 类型 | 说明 | 来源 |
|---|---|---|---|
| `position_id` | int \| 可选 | 按岗位过滤 | PRD §4.3 |
| `category` | str \| 可选 | 精确匹配 | PRD §4.3 |
| `dimension` | str \| 可选 | 精确匹配 | PRD §4.3 |
| `source` | str \| 可选 | `bank` \| `ai` | 本设计补充 |
| `keyword` | str \| 可选 | 按 `content` 模糊匹配 | 本设计补充 |

多个参数为 **AND** 关系。MVP 不分页。

> **为何补充 `source` 筛选**：PRD §5.2 定义了 `source` 字段区分「题库题」与「AI 题」。若不能按其筛选，HR 无从分辨与清理 AI 生成的题目——该筛选是 `source` 字段有用的前提。

**PUT `/api/questions/{id}`**：请求字段与 POST 一致，**全量替换**（`tags` 整体替换）。

> **`position_id` 是否可改**：允许。改岗位时必须**重新校验**新岗位的可见性与 `dimension` 合法性（`dimension` 若不属于新岗位则报 400）。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_question(db, user: User, data: QuestionCreate) -> Question` | Question | 校验岗位可见 + dimension 合法 → 落库（`source='bank'`） |
| `list_questions(db, user: User, filters: QuestionFilters) -> list[Question]` | 列表 | `scope_owner_id` 过滤 + 多维筛选 |
| `get_question(db, user: User, question_id: int) -> Question` | Question | 不存在 → 404；不可见 → 403 |
| `update_question(db, user: User, question_id: int, data: QuestionUpdate) -> Question` | Question | 同上校验 |
| `delete_question(db, user: User, question_id: int) -> None` | — | 被面试引用时由外键拒绝 → `BusinessError` |
| `list_candidates_for_position(db, owner_id: int \| None, position_id: int) -> list[Question]` | 列表 | **供 interview 出题使用**（§5.6） |
| `bulk_create_from_ai(db, user: User, position_id: int, items: list[GeneratedQuestion]) -> list[Question]` | 列表 | **供 interview 使用**：AI 题目入库（§5.4） |

`QuestionFilters` 字段：`position_id: int | None`、`category: str | None`、`dimension: str | None`、`source: str | None`、`keyword: str | None`。

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create(db, **fields) -> Question` | Question | — |
| `list_filtered(db, owner_id: int \| None, filters: QuestionFilters) -> list[Question]` | 列表 | `owner_id=None` 表示不过滤 |
| `list_by_position(db, owner_id: int \| None, position_id: int) -> list[Question]` | 列表 | 出题候选查询，**按 `id` 升序**保证稳定 |
| `get_by_id(db, question_id: int) -> Question \| None` | Question | **不带权限过滤** |
| `update(db, question: Question, **fields) -> Question` | Question | — |
| `delete(db, question: Question) -> None` | — | 捕获 `IntegrityError` → 抛 `BusinessError` |
| `bulk_insert(db, items: list[dict]) -> list[Question]` | 列表 | AI 题目批量入库 |

---

## 5. 业务流程设计

### 5.1 创建题目

```
1. schemas 层校验（content 长度、tags 规则、difficulty 取值）
2. service → position.service.get_position(db, user, position_id)
      不存在 → 404；不可见 → 403
3. 校验 dimension ∈ position.evaluation_dimensions（strip 后精确匹配）
      不匹配 → 400 VALIDATION_ERROR，detail 含合法维度列表
4. category 缺省填充 "通用"；tags strip 去重
5. repository.create(source='bank', created_by=user.id) → commit
```

### 5.2 单条资源访问权限模式

与 auth §5.3 / position §5.2 完全一致：`get_by_id` → `None` 则 404 → `scope_owner_id(user)` 非 `None` 且不匹配 `created_by` 则 403。

### 5.3 删除题目

```
1. 按 §5.2 取回并校验权限
2. repository.delete → 若 interview_question.question_id 存在外键引用
   → IntegrityError → BusinessError「该题目已被面试引用，无法删除」
3. 否则 204
```

### 5.4 AI 生成题目的入库路径（`source='ai'` 的产生方式）

PRD §5.2 定义了 `source: bank | ai` 两个取值，但未说明 `ai` 从何而来。本设计明确：

**interview 出题组装时，AI 补充生成的题目自动写入题库，`source='ai'`，`created_by` 为该面试的创建人。**

| 论点 | 说明 |
|---|---|
| 为何自动入库 | `source` 字段需要真实的产生来源；入库后 AI 出的好题能在后续面试中被复用，**题库随使用增长**（契合 PRD §1.2 的「提供可复用的题库」目标） |
| 为何 `created_by` 用面试创建人 | 数据隔离一致：该 HR 能在自己的题库里看到 AI 为自己的面试生成的题（PRD §4.1） |
| 代价 | 题库会被 AI 题目填充。由 `source` 筛选（§4.2）与「删除」能力兜底；HR 可按 `source=bank` 只看手工题 |
| 为何不由客户端指定 `source` | 来源是**服务端事实**（人工投递 vs AI 生成），客户端传参可伪造 |

**幂等性**：同一面试只出题一次（由 interview 的状态机保证），因此不会重复写入。

### 5.5 岗位维度变更对已有题目的影响

| 场景 | 行为 |
|---|---|
| 岗位维度被删除后，已有题目仍引用该维度 | **不自动清理**，也不报错 |
| 出题抽取时 | interview 的抽取算法**跳过** `dimension` 已不在岗位维度列表中的题目 |
| 更新题目时 | 若新 `dimension` 不在当前岗位维度中 → **400**，强制收敛 |

> **理由**：静默删除或改写历史题目会丢失数据；把「不合规题目」的处理放在抽取环节，既不丢数据又能保证新面试的题目合规。

### 5.6 出题候选查询（对 interview 的供给契约）

```
list_candidates_for_position(db, owner_id, position_id)
  → 返回该岗位下、属于 owner_id 范围内的全部题目
  → 按 id 升序（保证抽取算法的确定性基础）
  → 不过滤 source（AI 题与人工题都可作为候选）
```

**职责边界**：round-robin 抽取、跳过不合规维度、取满 N 题、AI 补齐——**全部在 interview 模块实现**（PRD §5.3 ①）。question 模块只保证「按稳定顺序返回候选集」。

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 未带 / 无效 token | `UNAUTHORIZED` / `INVALID_TOKEN` | 401 | — |
| 题目不存在 | `NOT_FOUND` | 404 | 题目不存在 |
| 访问他人题目 | `FORBIDDEN` | 403 | 无权限访问该题目 |
| 岗位不存在 | `NOT_FOUND` | 404 | 岗位不存在 |
| 岗位不可见 | `FORBIDDEN` | 403 | 无权限访问该岗位 |
| **`dimension` 不属于岗位维度** | `VALIDATION_ERROR` | 400 | 该维度不属于岗位的评估维度（`detail` 含合法维度列表） |
| `content` 过短 / 过长 | `VALIDATION_ERROR` | 400 | 题目内容需 5–2000 字符 |
| `tags` 超 10 个 / 单项超长 | `VALIDATION_ERROR` | 400 | — |
| `difficulty` 取值非法 | `VALIDATION_ERROR` | 400 | — |
| **删除被面试引用的题目** | `BUSINESS_ERROR` | 409 | 该题目已被面试引用，无法删除 |

---

## 7. 测试设计（对应 PRD §10）

### 7.1 鉴权与数据隔离（PRD §4.1、§8）

| 测试 | 断言 |
|---|---|
| `test_create_without_token` | 401 |
| `test_create_ok` | 201，**`source == "bank"`**，`created_by` 正确 |
| `test_list_only_own_questions` | 另一 hr 看不到 |
| `test_admin_sees_all_questions` | admin 可见全部 |
| `test_get_other_users_question_forbidden` | 403 |
| `test_get_nonexistent_question` | 404 |
| `test_update_delete_other_users_question_forbidden` | 403 |

### 7.2 岗位与维度校验（§3.3、§5.1）

| 测试 | 断言 |
|---|---|
| `test_create_with_nonexistent_position` | 404 |
| `test_create_with_other_users_position` | 403 |
| `test_create_with_invalid_dimension` | 400，**`detail` 含合法维度列表** |
| `test_create_dimension_match_is_exact_after_strip` | 岗位维度为 `"沟通能力"`，传 `" 沟通能力 "` → 201 且落库为 `"沟通能力"` |
| `test_update_question_to_other_position_revalidates_dimension` | 改到新岗位但 dimension 不属于新岗位 → 400 |
| `test_update_question_to_other_position_ok` | dimension 合法时 200 |

### 7.3 字段校验（§3.3）

| 测试 | 断言 |
|---|---|
| `test_content_too_short` | 4 字符 → 400 |
| `test_content_too_long` | 2001 字符 → 400 |
| `test_category_defaults_to_generic` | 不传 `category` → 落库 `"通用"` |
| `test_difficulty_defaults_to_medium` | 不传 → `"medium"` |
| `test_invalid_difficulty` | `"very_hard"` → 400 |
| `test_tags_defaults_to_empty` | 不传 → `[]` |
| `test_tags_exceed_limit` | 11 个 → 400 |
| `test_tags_dedup_after_strip` | `["a"," a "]` → 落库 `["a"]` |
| `test_tags_single_too_long` | 21 字符 → 400 |
| `test_client_cannot_set_source` | 请求体带 `source: "ai"` → 落库仍为 `"bank"`（服务端决定） |

### 7.4 筛选（PRD §4.3）

| 测试 | 断言 |
|---|---|
| `test_filter_by_position` | 仅返回该岗位题目 |
| `test_filter_by_category` | 精确匹配 |
| `test_filter_by_dimension` | 精确匹配 |
| `test_filter_by_source` | `source=ai` 仅返回 AI 题 |
| `test_filter_by_keyword` | 按 `content` 模糊匹配 |
| `test_filter_combined_is_and` | 多参数同时生效为 **AND** |
| `test_filter_respects_isolation` | **筛选结果不越过 `created_by` 边界** |

### 7.5 删除

| 测试 | 断言 |
|---|---|
| `test_delete_ok` | 204，**无响应体** |
| `test_delete_referenced_by_interview` | 409 `BUSINESS_ERROR` |

### 7.6 对 interview 的供给契约（§5.6）

| 测试 | 断言 |
|---|---|
| `test_list_candidates_returns_position_questions` | 返回指定岗位全部题目 |
| `test_list_candidates_ordered_by_id` | 结果**按 `id` 升序** |
| `test_list_candidates_respects_owner` | 不返回他人题目 |
| `test_list_candidates_includes_ai_source` | 不过滤 `source`，AI 题也在候选集内 |
| `test_bulk_create_from_ai_sets_source_ai` | 入库题目 `source == "ai"`，`created_by` 正确 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。

### Task 3.1：`Question` 模型与迁移

- [ ] 定义 `Question` 模型（§3.1 全字段、枚举、JSON 列）
- [ ] 建立四个索引与两个外键约束（`position_id` RESTRICT）
- [ ] 生成迁移、`alembic upgrade head`、验证结构
- [ ] 提交

### Task 3.2：schema 与字段校验

- [ ] 定义 `QuestionCreate`、`QuestionUpdate`、`QuestionOut`、`QuestionFilters`
- [ ] 实现 §3.3 的字段校验（content 长度、tags 规则、difficulty 取值）
- [ ] 写 §7.3 全部失败测试
- [ ] 运行确认失败 → 实现 → 通过
- [ ] 提交

### Task 3.3：repository 层

- [ ] 写失败测试：`list_by_position` 返回稳定 `id` 升序；`list_filtered` 组合筛选生效
- [ ] 运行确认失败
- [ ] 实现 §4.4 七个方法
- [ ] 运行确认通过
- [ ] 提交

### Task 3.4：创建题目（含岗位与维度校验）

- [ ] 写 §7.2 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `service.create_question`（调 `position.service.get_position` 校验可见性 + 维度合法性）
- [ ] 实现 `POST /api/questions`，在 `main.py` 注册 router
- [ ] 运行确认通过
- [ ] 提交

### Task 3.5：列表与多维筛选

- [ ] 写 §7.1、§7.4 相关失败测试
- [ ] 运行确认失败
- [ ] 实现 `service.list_questions` 与 `GET /api/questions`（含查询参数解析）
- [ ] 运行确认通过
- [ ] 提交

### Task 3.6：详情 / 更新 / 删除

- [ ] 写 §7.1 剩余与 §7.5 失败测试
- [ ] 运行确认失败
- [ ] 实现 `get_question`、`update_question`、`delete_question` 与三个端点
- [ ] 运行确认通过
- [ ] 提交

### Task 3.7：对 interview 的供给接口

- [ ] 写 §7.6 全部失败测试
- [ ] 运行确认失败
- [ ] 实现 `list_candidates_for_position`、`bulk_create_from_ai`
- [ ] 运行确认通过
- [ ] 提交

### Task 3.8：全量回归

- [ ] 运行 question 全部测试
- [ ] 运行 core / auth / position 测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] 创建题目返回 201，**`source` 恒为 `bank`**（客户端无法指定）
- [ ] `dimension` 不属于所属岗位维度时返回 400，**`detail` 含合法维度列表**
- [ ] 岗位不存在返回 404，岗位不可见返回 403
- [ ] `content` 长度、`tags` 数量与长度校验生效
- [ ] `category` 缺省 `"通用"`，`difficulty` 缺省 `medium`，`tags` 缺省 `[]`
- [ ] `tags` strip 去重生效
- [ ] 按岗位 / 分类 / 维度筛选生效（PRD §4.3）；补充的 `source` / `keyword` 筛选同样生效；多参数为 AND
- [ ] **筛选结果不越过数据隔离边界**（PRD §4.1）
- [ ] `PUT` 对 `tags` 为全量替换语义
- [ ] 删除未被引用的题目返回 **204 且无响应体**
- [ ] 删除被面试引用的题目返回 409（由外键 RESTRICT 保证）
- [ ] `list_candidates_for_position` 按 `id` 升序返回，受 `owner_id` 约束，**不过滤 `source`**
- [ ] `bulk_create_from_ai` 入库题目 `source == "ai"`
- [ ] 全部 question 测试通过

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| PRD §5.2 未给 `question` 定义归属字段 | **新增 `created_by`** | PRD §4.1 的数据隔离要求必须有归属字段才能落地。属补齐 |
| `source='ai'` 从何而来 | **interview 出题时 AI 题目自动入库** | `source` 需真实来源；好题可复用，契合 PRD §1.2「可复用的题库」；由筛选与删除兜底 |
| 是否允许客户端指定 `source` | **不允许** | 来源是服务端事实，客户端传参可伪造 |
| 是否禁止内容重复的题目 | **不禁止** | AI 可能生成近似题目，唯一约束会导致入库失败而非可解释错误 |
| 岗位维度变更后已有题目怎么办 | **不清理、不改写；抽取时跳过不合规项** | 不丢数据；新面试的题目保证合规 |
| 建题人 ≠ 岗位拥有者时以谁为准 | **以建题人为准** | admin 可为他人的岗位建题；隔离语义以数据归属为准 |
| 为何补充 `source` / `keyword` 筛选 | 补充 | `source` 是 PRD 定义的字段，不能筛选则无法分辨与清理 AI 题目 |
| 是否建标签表 | **不建，用 JSON 数组** | YAGNI，标签无需反向查询 |
| 题目是否支持排序字段 | **不支持** | 题目在面试中的顺序由 `interview_question.seq` 决定，属面试实例的属性 |
| 列表是否分页 | **不分页** | 内部系统数据量小；多维筛选已足够 |
