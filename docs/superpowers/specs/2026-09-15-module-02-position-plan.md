# position 模块执行计划书

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：position（岗位与评估维度）
**所属包**：`backend/app/position/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp.md](../plans/2026-09-15-ai-interview-assistant-mvp.md)
**设计规格**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 任务**：Task 2
**前置依赖**：core（[module-00](./2026-09-15-module-00-core-plan.md)）、auth（[module-01](./2026-09-15-module-01-auth-plan.md)）

---

## Global Constraints（全局约束）

- 后端严格分层：`router → service → repository → MySQL`，只允许自上而下依赖，不跨层调用、不反向依赖。
- 每个模块独立 Python package（`backend/app/<module>/`）。
- 数据隔离：普通 HR 仅见自己创建的数据，admin 见全部。
- 仅 PC 端，不做移动端响应式。
- 统一错误响应格式 `{code, message, detail}`。

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 |
|---|---|
| 岗位实体 | Position 表的定义与迁移 |
| 岗位管理 | 岗位的增、查、改、删 |
| 评估维度定义 | 维护岗位的评估维度列表，作为多维评分的依据 |
| 出题依据 | 为 interview 模块提供 JD 与维度，作为 AI 出题的输入 |

### 1.2 边界（明确不做）

- **不生成题目**：题目生成属于 interview（组装）+ ai（Provider）的职责。position 只提供输入。
- **不做题目关联**：题库中题目的 `position_id` 由 question 模块维护（外键指向本表），position 不反向查询题目。
- **不做面试关联查询**：position 不查询面试数据；「岗位是否被引用」由数据库外键约束判定（见 §5.3）。
- **不做软删除**：MVP 不做 `deleted_at`。
- **不做岗位模板 / 岗位复制**：不在 MVP 范围。

### 1.3 依赖方向

```
position.router ──→ position.service ──→ position.repository ──→ position 表
                          │
                          └──→ core.deps.get_current_user
                          └──→ auth.service.scope_owner_id（数据隔离判定）

position ──→ core, auth（单向）
interview ──→ position（读取 JD 与维度；通过 FK 约束反向保护）
question ──→ position（题目的 position_id 外键）
position ✗→ interview / question（不反向依赖）
```

---

## 2. 文件结构

| 文件 | 单一职责 |
|---|---|
| `backend/app/position/__init__.py` | 包标识 |
| `backend/app/position/models.py` | `Position` 模型定义 |
| `backend/app/position/schemas.py` | 请求 / 响应 Pydantic 模型 + 维度校验规则 |
| `backend/app/position/repository.py` | Position 表数据访问（含 `owner_id` 过滤） |
| `backend/app/position/service.py` | 业务逻辑：创建、列表、详情、更新、删除 |
| `backend/app/position/router.py` | `/api/positions/*` 端点 |

**测试文件**：`backend/tests/test_position.py`

**本模块需修改的上游文件**：

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 position router |
| `backend/alembic/versions/` | 新增 Position 表迁移 |

---

## 3. 数据模型设计

### 3.1 表 `position`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT | PK, AUTO_INCREMENT | 主键 |
| `name` | VARCHAR(100) | NOT NULL | 岗位名称 |
| `jd` | TEXT | NOT NULL | 岗位描述，AI 出题的主要依据 |
| `evaluation_dimensions` | JSON | NOT NULL | 评估维度列表，如 `["沟通能力","专业能力","逻辑思维","文化契合"]` |
| `created_by` | BIGINT | NOT NULL, FK → `user.id`, INDEX | 创建人，数据隔离依据 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | — |

**索引**：

| 索引 | 字段 | 类型 | 目的 |
|---|---|---|---|
| `uq_position_owner_name` | (`created_by`, `name`) | UNIQUE | 同一 HR 下岗位名唯一；不同 HR 可重名 |
| `ix_position_created_by` | (`created_by`) | INDEX | 数据隔离过滤 |

### 3.2 设计要点

- **岗位名按创建人唯一**（复合唯一索引）而非全局唯一：不同 HR 各自维护「后端工程师」是合理场景，全局唯一会造成无谓冲突。
- **`created_by` 外键指向 `user.id`**：用户不物理删除（见 auth §3.2），故外键安全。
- **`evaluation_dimensions` 用 JSON 列**：维度是岗位的可变长属性，用 JSON 避免额外的维度子表和关联查询。SQLite 与 MySQL 8 均支持。
- **维度以字符串存储（非 ID）**：`dimension_score.dimension` 同为字符串，评估结果与岗位维度定义直接可比对，无需联表。
- **`jd` NOT NULL**：JD 是 AI 出题的核心输入，缺失会使出题质量无保障。

### 3.3 评估维度校验规则（在 schemas 层实现）

| 规则 | 值 | 失败时 |
|---|---|---|
| 类型 | `list[str]` | 400 `VALIDATION_ERROR` |
| 数量下限 | ≥ 1 | 400，message「至少需要 1 个评估维度」 |
| 数量上限 | ≤ 10 | 400，message「评估维度不能超过 10 个」 |
| 单项长度 | 1–50 字符 | 400，`detail` 含越界项 |
| 去重 | strip 后**不区分大小写**比较 | 400，`detail` 含重复项 |
| 空串 | 不允许 | 400 |

> **去重语义**：`"沟通能力"` 与 `" 沟通能力 "` 视为重复；`"Communication"` 与 `"communication"` 视为重复。存储时保存 **strip 后的原始大小写**。

---

## 4. 接口契约

### 4.1 对外 REST API

| 方法 | 路径 | 说明 | 权限 | 成功码 |
|---|---|---|---|---|
| POST | `/api/positions` | 创建岗位 | 登录 | 201 |
| GET | `/api/positions` | 岗位列表（按数据隔离过滤） | 登录 | 200 |
| GET | `/api/positions/{id}` | 岗位详情 | 登录 + 可见 | 200 |
| PUT | `/api/positions/{id}` | 更新岗位 | 登录 + 可见 | 200 |
| DELETE | `/api/positions/{id}` | 删除岗位 | 登录 + 可见 | 204 |

> **删除成功返回 204 No Content**（无响应体）。其余错误一律走统一三字段格式。这是本项目对 204 的统一约定，question 模块的删除同样适用。

### 4.2 请求 / 响应结构

**Position 响应对象**（创建 / 详情 / 更新 / 列表项统一）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | — |
| `name` | str | — |
| `jd` | str | — |
| `evaluation_dimensions` | list[str] | — |
| `created_by` | int | 创建人 user id |
| `created_at` | datetime | ISO 8601 |

**POST `/api/positions`**

| 方向 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `name` | str | 必填，1–100 字符 |
| 请求 | `jd` | str | 必填，**1–10000 字符** |
| 请求 | `evaluation_dimensions` | list[str] | 必填，规则见 §3.3 |

**PUT `/api/positions/{id}`**：请求字段与 POST 相同，**全量替换**语义（`evaluation_dimensions` 整体替换，非追加）。

**GET `/api/positions`**：返回 Position 对象数组。支持可选查询参数 `keyword`（按 `name` 模糊匹配，服务端 `LIKE %keyword%`）。

> **列表是否分页**：MVP 不分页（与 auth 用户列表一致）。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 职责 |
|---|---|---|
| `create_position(db, user: User, data: PositionCreate) -> Position` | Position | 校验重名、落库、commit |
| `list_positions(db, user: User, keyword: str \| None) -> list[Position]` | 列表 | 用 `scope_owner_id` 过滤 |
| `get_position(db, user: User, position_id: int) -> Position` | Position | 不存在 → `NotFoundError`；不可见 → `ForbiddenError` |
| `update_position(db, user: User, position_id: int, data: PositionUpdate) -> Position` | Position | 同上校验 + 重名校验 |
| `delete_position(db, user: User, position_id: int) -> None` | — | 被引用时由 FK 约束拒绝 → 转 `BusinessError` |

### 4.4 repository 层方法签名

| 方法签名 | 返回 | 说明 |
|---|---|---|
| `create(db, name: str, jd: str, dimensions: list[str], created_by: int) -> Position` | Position | — |
| `list_by_owner(db, owner_id: int \| None, keyword: str \| None) -> list[Position]` | 列表 | `owner_id=None` 表示不过滤（admin） |
| `get_by_id(db, position_id: int) -> Position \| None` | Position | **不带权限过滤**，权限判定在 service |
| `get_by_owner_and_name(db, owner_id: int, name: str) -> Position \| None` | Position | 重名校验 |
| `update(db, position: Position, **fields) -> Position` | Position | — |
| `delete(db, position: Position) -> None` | — | 捕获 `IntegrityError` → 抛 `BusinessError` |

**分层约定**：`get_by_id` 故意不带权限过滤——repository 保持纯粹，「谁有权看」是业务判断，归 service。

---

## 5. 业务流程设计

### 5.1 创建岗位

```
1. schemas 层校验（name 长度、jd 长度、维度规则）
2. service：按 (created_by, name) 查重 → 已存在则 BUSINESS_ERROR
3. 维度 strip 后落库（保留原始大小写）
4. repository.create → commit
5. 并发冲突时唯一索引兜底 → IntegrityError → BUSINESS_ERROR
```

### 5.2 读取与权限判定（全项目统一的单条资源访问模式）

```
1. repository.get_by_id(position_id)
2. 为 None                    → NotFoundError（404）
3. scope_owner_id(user) 非 None 且 != position.created_by
                              → ForbiddenError（403）
4. 返回
```

> **为何返回 403 而非 404**：语义明确——资源存在但无权访问。此模式被 question / interview / evaluation 模块统一复用。**注意**：直接返回 403 会暴露「该 id 存在」，对内部 HR 系统可接受；若未来面向多租户需改为 404。

### 5.3 删除岗位

```
1. 按 §5.2 取回并校验权限
2. repository.delete(position) → DELETE FROM position WHERE id = ?
3. 若 question.position_id 或 interview.position_id 存在外键引用
   → 数据库抛 IntegrityError（ON DELETE RESTRICT）
   → repository 捕获并抛 BusinessError
   → 客户端收到 409「该岗位已被题库或面试引用，无法删除」
4. 否则 commit，返回 204
```

**为何用数据库外键而非跨模块代码检查**：

| 方案 | 问题 |
|---|---|
| position 直接查 interview / question 表 | 破坏模块边界，position 反向依赖其他业务的表结构 |
| 定义端口协议由 interview 注入实现 | 正确但 MVP 阶段引入不必要的抽象与启动期装配复杂度 |
| **外键 `ON DELETE RESTRICT`（本设计采用）** | 零跨模块代码耦合，完整性由数据库保证，且对并发删除天然正确 |

### 5.4 更新岗位对已存在面试的影响

| 变更 | 影响 |
|---|---|
| 改 `name` / `jd` | **不影响**已完成的面试（题目内容已存快照，见 interview §3.2） |
| 改 `evaluation_dimensions` | **不影响**已落库的历史评估结果（`dimension_score` 按维度名独立存储）；仅影响**此后**新触发的评估 |

> 设计上**不做**「岗位维度变更后自动重算历史评估」——那会产生无法解释的历史数据变动，且违背评估结果的时间点属性。

---

## 6. 错误处理

| 场景 | code | HTTP | message 示例 |
|---|---|---|---|
| 未带 / 无效 token | `UNAUTHORIZED` / `INVALID_TOKEN` | 401 | — |
| 岗位不存在 | `NOT_FOUND` | 404 | 岗位不存在 |
| 访问他人岗位 | `FORBIDDEN` | 403 | 无权限访问该岗位 |
| 同创建人下重名 | `BUSINESS_ERROR` | 409 | 该岗位名称已存在 |
| 删除被引用的岗位 | `BUSINESS_ERROR` | 409 | 该岗位已被题库或面试引用，无法删除 |
| 维度列表为空 / 超 10 个 / 有重复 | `VALIDATION_ERROR` | 400 | 见 §3.3（`detail` 含具体违规项） |
| `name` 为空或超长 | `VALIDATION_ERROR` | 400 | — |

---

## 7. 测试设计

`backend/tests/test_position.py`

### 7.1 鉴权与数据隔离

| 测试 | 断言 |
|---|---|
| `test_create_without_token` | 401 |
| `test_create_ok` | 201，响应含 `id` 与 `created_by` |
| `test_list_only_own_positions` | hr 创建的岗位，另一个 hr 查不到 |
| `test_admin_sees_all_positions` | admin 可看到所有 hr 创建的岗位 |
| `test_get_other_users_position_forbidden` | hr 访问他人岗位 → 403 `FORBIDDEN` |
| `test_get_nonexistent_position` | 404 `NOT_FOUND` |
| `test_update_other_users_position_forbidden` | 403 |
| `test_delete_other_users_position_forbidden` | 403 |

### 7.2 维度校验

| 测试 | 断言 |
|---|---|
| `test_create_empty_dimensions` | 400，message 含「至少需要 1 个」 |
| `test_create_too_many_dimensions` | 11 个维度 → 400，message 含「不能超过 10 个」 |
| `test_create_duplicate_dimensions` | `["沟通","沟通"]` → 400，`detail` 含重复项 |
| `test_create_duplicate_dimensions_case_insensitive` | `["Communication","communication"]` → 400 |
| `test_create_duplicate_dimensions_whitespace` | `[" 沟通 ","沟通"]` → 400 |
| `test_create_dimension_too_long` | 51 字符维度 → 400 |
| `test_dimensions_stored_stripped` | 传入 `" 沟通 "` → 落库为 `"沟通"`（保留大小写、去除首尾空白） |

### 7.3 CRUD 与业务规则

| 测试 | 断言 |
|---|---|
| `test_create_duplicate_name_same_owner` | 409 `BUSINESS_ERROR` |
| `test_create_same_name_different_owner` | 两个 hr 可各自建同名岗位，均 201 |
| `test_update_position` | 200，字段全部替换生效 |
| `test_update_duplicate_name` | 改名撞到同创建人已有岗位 → 409 |
| `test_update_dimensions_replaces_not_appends` | 由 `[A,B]` 改为 `[C]` → 结果为 `[C]` |
| `test_delete_ok` | 204，无响应体；再查 → 404 |
| `test_delete_referenced_by_question` | 存在题目引用 → 409 `BUSINESS_ERROR` |
| `test_delete_referenced_by_interview` | 存在面试引用 → 409 `BUSINESS_ERROR` |
| `test_list_with_keyword` | `keyword` 按 name 模糊匹配 |

> `test_delete_referenced_by_question` / `test_delete_referenced_by_interview` 需在对应模块完成后才能完整验证。**本模块先实现 FK 约束**，测试可先以直接插入关联行（绕过上层）的方式构造引用，不依赖 question / interview 模块是否已完成。

---

## 8. 任务分解（TDD 步骤，无代码）

### Task 2.1：Position 模型与迁移

- [ ] 定义 `Position` 模型（§3.1 全字段）
- [ ] 建立复合唯一索引 `(created_by, name)` 与 `created_by` 普通索引
- [ ] 定义 `created_by` → `user.id` 外键，`ON DELETE RESTRICT`
- [ ] 生成迁移、`alembic upgrade head`、验证索引与外键
- [ ] 提交

### Task 2.2：schema 与维度校验

- [ ] 定义 `PositionCreate`、`PositionUpdate`、`PositionOut`
- [ ] 实现 §3.3 的维度校验（数量、长度、strip 去重不区分大小写）
- [ ] 写 §7.2 全部失败测试
- [ ] 运行测试确认失败 → 实现 → 通过
- [ ] 提交

### Task 2.3：repository 层

- [ ] 写失败测试：`create` 后可查回；`list_by_owner(None)` 返回全部；`list_by_owner(id)` 仅返回该 owner
- [ ] 运行测试确认失败
- [ ] 实现 §4.4 六个方法（`delete` 含 IntegrityError 转换）
- [ ] 运行测试确认通过
- [ ] 提交

### Task 2.4：创建与列表

- [ ] 写 §7.1 中 `test_create_*`、`test_list_*` 失败测试
- [ ] 运行测试确认失败
- [ ] 实现 `service.create_position` / `list_positions` 与 `POST`、`GET` 端点
- [ ] 在 `main.py` 注册 router
- [ ] 运行测试确认通过
- [ ] 提交

### Task 2.5：详情 / 更新 / 删除

- [ ] 写 §7.1 剩余测试与 §7.3 全部失败测试
- [ ] 运行测试确认失败
- [ ] 实现 `get_position`（含 §5.2 权限模式）、`update_position`、`delete_position`
- [ ] 实现 `GET/{id}`、`PUT/{id}`、`DELETE/{id}` 端点
- [ ] 运行测试确认通过
- [ ] 提交

### Task 2.6：全量回归

- [ ] 运行 position 全部测试
- [ ] 运行 core / auth 测试，确认未被破坏
- [ ] 提交

---

## 9. 验收标准

- [ ] 岗位创建返回 201，响应含 `id`、`created_by`
- [ ] 同一创建人下岗位名唯一（409）；不同创建人可重名（201）
- [ ] 维度校验覆盖：空列表、超过 10 个、重复（含大小写与空白差异）、单项超长，均返回 400 `VALIDATION_ERROR`
- [ ] 维度落库为 strip 后、保留原始大小写的值
- [ ] hr 只能列出 / 访问自己创建的岗位；admin 可见全部
- [ ] 访问他人岗位返回 403；不存在的岗位返回 404
- [ ] 删除未被引用的岗位返回 204 且无响应体
- [ ] 删除被 question 或 interview 引用的岗位返回 409（由 FK RESTRICT 保证）
- [ ] `PUT` 对 `evaluation_dimensions` 为全量替换语义
- [ ] 全部 position 测试通过

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| 跨模块的「是否被引用」检查 | 由数据库外键 `ON DELETE RESTRICT` 承担 | 零跨模块代码耦合；并发安全；避免 position 反向依赖其他模块表结构 |
| 岗位名唯一性范围 | 按创建人唯一 | 不同 HR 维护同名岗位是常态，全局唯一无谓冲突 |
| 维度用 JSON 列 | 采用 | 避免维度子表与联表查询；SQLite / MySQL 8 均支持 |
| 访问他人资源返回 403 还是 404 | 403 | 语义明确；内部系统可接受信息暴露 |
| 岗位维度变更是否重算历史评估 | 不重算 | 保留评估结果的时间点属性 |
| 删除是否软删除 | 不软删除 | MVP YAGNI；被引用时本来就不允许删 |
| 列表是否分页 | 不分页（支持 keyword 过滤） | 内部系统数据量小 |
