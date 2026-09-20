# practice 模块执行计划书（MVP-3 按简历推荐取题）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：practice（在既有练习会话 / 判分 / 错题本 / 统计之上，新增「按简历推荐取题」）
**所属包**：`backend/app/practice/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.7（刷题练习）、§5.2（`practice_session` 加两列）、§5.3 ⑤、§7（按简历推荐 AI 失败降级）、§8（practice 端点）、§9（分层）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-13 practice 主体](./2026-09-20-module-13-practice-plan.md)、[module-17 resume](./2026-09-21-module-17-resume-plan.md)、[module-18 ai](./2026-09-21-module-18-ai-plan.md)
**本模块被谁依赖**：[module-22 候选人前端](./2026-09-21-module-22-candidate-frontend-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- 按简历推荐是**可选**的：开始练习时关联一份**自己的**简历才触发；**未关联则完全走既有筛选取题**（§4.7）
- AI 只**从符合筛选条件的候选中挑选排序**，**不生成新题**（§4.7、§6）
- AI 失败 → **降级为原筛选取题，不阻塞开始练习**（§7）
- **候选池与既有筛选取题同源**，否则「筛出来的题」与「推荐出来的题」口径会不一致（§4.7）
- 候选人只能关联**自己的**简历；`resume_id` 由服务端校验归属（§4.6、§4.10）
- **`practice` 不依赖 `interview`**（既有铁律）；本次**也不新增** `position` 依赖（§3.3、§9）
- 取不到题**不建空会话**（既有约定，module-13 §5.1）
- 会话开始即写满题目**快照**，题库后续删改不影响进行中的练习（§5.2、既有约定）
- 判分分工、错题本派生、统计口径、限流实现**全部不变**（§4.7、§7）
- **仍是单机 PC 端，技术栈不变、不引入新依赖**（§2）

---

## 1. 模块职责与边界

### 1.1 职责（对应 PRD §4.7）

| 子职责 | 内容 | PRD |
|---|---|---|
| 关联简历起练 | `POST /practice/sessions` 新增可选 `resume_id` | §4.7 |
| 候选池扩大 | 有关联时取**更大的候选池**供 AI 挑选（否则 AI 只能重排，无法改进选什么） | §4.7 |
| 调 AI 选排 | 调 `ai.match_questions_by_resume`，按相关度取前 `size` 题 | §4.7 |
| 失败降级 | AI 失败或返回空 → 退回原筛选取题，**仍正常建会话** | §7 |
| 降级留痕 | 用 `resume_match_applied` 记录「本次是否真的按简历推荐了」 | §7（延伸） |
| 其余行为不变 | 快照、`seq`、判分、错题本、统计、限流**零改动** | §4.7 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **简历的增删改查** | 属 `resume`（module-17）。本模块只调 `ensure_mine` 校验归属、拿 `content` |
| **AI 的匹配规则** | 属 `ai`（module-18）。本模块只负责扩大池子、传参、降级 |
| **读取 `position` 表** | `practice` **禁止**依赖 `position`（`FORBIDDEN_DEPENDENCIES`，module-13 §1.3）。岗位名走 question 既有供给（§4.4） |
| **预览接口支持简历** | `GET /practice/questions` **不接 `resume_id`**。它是「有多少题可练」的展示，既有注释明确它「不创建会话、不写快照，因此也不计入限流」；让它调 AI 会**打破这一性质**，并产生未计入限流的 AI 消耗（§10） |
| **记忆「上次用的简历」** | 每次都显式传，不做服务端记忆。隐式状态会让「为什么这次推荐的题不一样」变得无法解释 |
| **修改既有判分 / 错题本 / 统计 / 限流** | 本次零改动。`resume_id` 只是一条附加的会话出身信息 |
| **在会话列表里显示简历** | 列表保持既有字段不变（少一次联表、少一档破坏既有断言的回归风险）。会话**详情**才暴露（§4.2） |
| **对未关联简历的会话做任何特殊处理** | 未关联时 `resume_id` 为 NULL、`resume_match_applied` 为 false，走既有逻辑 |

### 1.3 依赖方向

```
practice.router ──→ practice.service ──→ practice.repository ──→ practice 表族
                          │
                          ├──→ question.service（list_practice_questions / list_practice_positions）
                          ├──→ auth.service（ensure_owner_match）
                          ├──→ resume.service（ensure_mine）              ← 新增依赖边
                          └──→ ai.factory.get_provider()（match_questions_by_resume）

practice ──→ core / auth / question / resume / ai（单向）
practice ✗→ interview / position / evaluation（**禁止集合不变**）
```

> **本次只新增一条依赖边 `practice → resume`**，而 `resume` 不依赖任何业务模块（module-17 §1.3），因此不会与 `interview → resume` 形成循环。
>
> **`FORBIDDEN_DEPENDENCIES["practice"]` 是 `{interview, position, evaluation}`**（`test_architecture.py`），**本来就不含 `resume`**，故该集合**无需改动**；`resume` 的禁止集合也**不含 practice**（它谁都不依赖），因此 `practice → resume` 直接合法。
>
> **⚠️ 绝不为了拿岗位名而 import `position`**：那会立刻让 `test_no_reverse_dependency[practice]` 变红。岗位名必须走 §4.4 的既有供给。

---

## 2. 文件结构

| 文件 | 单一职责 | 本次改动 |
|---|---|---|
| `backend/app/practice/models.py` | 两张表 | **改**：`PracticeSession` 加两列（§3.1） |
| `backend/app/practice/schemas.py` | 请求 / 响应模型 | **改**：`PracticeSessionCreate` 加 `resume_id`；`PracticeSessionDetail` 加两个字段 |
| `backend/app/practice/repository.py` | 纯 CRUD 与派生查询 | **无改动**（`create_session(db, **fields)` 已接受任意字段） |
| `backend/app/practice/service.py` | 会话编排、判分、限流 | **改**：`start_session` 增三条分支；新增 **4 个内部辅助**（§4.3） |
| `backend/app/practice/router.py` | `/api/practice/*` 九个端点 | **无改动**（端点签名与路径不变，只是请求体多一个可选字段） |

**测试文件**

| 文件 | 本次改动 |
|---|---|
| `backend/tests/test_practice.py` | **改**：新增「按简历推荐」测试组 |
| `backend/tests/test_practice_router.py` | **改**：新增端点级用例（`resume_id` 归属、降级、响应字段） |
| `backend/tests/conftest.py` | **改**：复用 module-17 的 `resume` 夹具，无需新增 |

**本模块需修改的上游文件**

| 文件 | 修改内容 | 为何必要 |
|---|---|---|
| **无** | — | 本模块不新增配置项、不新增端点、不改 `question` / `auth` / `ai` |

> **这是 MVP-3 里改动面最小的业务模块**：5 个源文件里只有 3 个要动，路由层完全不动。
>
> **不写 alembic 迁移、不同步 `backend/script.sql`**（PRD §11）。

---

## 3. 数据模型设计

### 3.1 `practice_session` 表：新增两列（对应 PRD §5.2）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `resume_id` | BIGINT | NULL, FK → `resume.id` **RESTRICT** | 本次练习关联的简历；NULL = 未关联 |
| `resume_match_applied` | BOOLEAN | NOT NULL, DEFAULT `false` | **本次是否真的用 AI 按简历选排了题目** |

| 决策 | 理由 |
|---|---|
| **`RESTRICT` 而非 `SET NULL`** | 被练习关联的简历不可删除（module-17 §5.4 的 409 依赖它）。`SET NULL` 会让历史练习静默失去「这次是按哪份简历推荐的」这一事实 |
| **`resume_id` 允许 NULL** | 绝大多数练习不关联简历，这是常态 |
| **`resume_match_applied` 是必需的，不是冗余** | `resume_id` 非空 **不代表** 这次真的按简历推荐了——AI 可能失败或返回空，此时已降级为普通筛选（PRD §7）。**两个字段回答两个不同问题**：「候选人想用哪份简历」vs「系统实际做到了没有」。合并成一个字段会让降级变成静默 |
| **`DEFAULT false` + NOT NULL** | 未关联简历的会话恒为 false（无需显式写）；关联了但降级的也是 false。既有历史行在加列后自动为 false，语义正确 |

> **为什么要为「降级」单独加一列**（本项目的一贯态度）：module-13 §5.3 对 AI 判分失败留了解析文案、module-19 §5.3 要求补题失败时题目数不变。**降级必须可观测**，否则候选人关联了简历却拿到一堆通用题，界面上没有任何解释，只能认为是功能坏了。
>
> **若不加这一列**：前端无法区分「正常按筛选取题（未关联简历）」与「关联了但 AI 没生效」，也无法给出「按简历推荐暂不可用」的提示。

---

## 4. 接口契约

### 4.1 对外 REST API（守卫 `require_roles("candidate")`，**端点集合不变**）

| 方法 | 路径 | 本次变化 |
|---|---|---|
| POST | `/api/practice/sessions` | 请求体**新增可选** `resume_id` |
| GET | `/api/practice/sessions/{id}` | 响应**新增**两个字段（§4.2） |
| 其余七个端点 | — | **零改动**（含 `GET /practice/questions` 预览，**不接 `resume_id`**） |

### 4.2 请求 / 响应结构

**`PracticeSessionCreate`（改）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `resume_id` | int \| null | 可选，`Field(default=None, ge=1)` | **新增**。传了就按简历推荐；不传走既有筛选 |

**`PracticeSessionDetail`（改）**

| 字段 | 变化 | 说明 |
|---|---|---|
| `resume_id` | **新增**，`int \| null` | 本次练习关联的简历（未关联为 null） |
| `resume_match_applied` | **新增**，`bool` | 是否真的按简历选排了题目 |

**`PracticeSessionListItem`（**不变**）**

> 列表项**不加**这两个字段：既有的列表接口刻意「不含题目明细」以保持轻量（module-13 §4.2），加简历信息会带来同样的膨胀，而且列表主要在回答「我练过哪些」，不是在回答「当时用了哪份简历」。

**`PracticeSessionOut`（**不变**）** —— `POST /practice/sessions` 响应主体里的会话摘要

> 摘要的字段集**保持不变**，两个新字段只出现在**详情**（`PracticeSessionDetail`）与创建响应中的 `session`。⚠️ 执行时若发现创建响应复用了 `PracticeSessionOut`，**优先把新字段加在详情上**，不要为了省事改动摘要的形状。

### 4.3 service 层方法签名

| 方法签名 | 返回 | 变化 |
|---|---|---|
| `start_session(db, user, data: PracticeSessionCreate) -> PracticeSessionDetail` | 会话详情 | **行为扩展**（§5.1、§5.2） |
| `preview_questions(...)` / `get_session(...)` / `submit_item(...)` / `rescore_item(...)` / `finish_session(...)` / `list_wrong_book(...)` / `get_stats(...)` / `list_my_sessions(...)` | — | **零改动** |

**新增内部辅助（4 个，职责边界必须分清）**

| 签名 | 职责 | 不做什么 |
|---|---|---|
| `_pick_questions(db, user, filters, size, resume) -> tuple[list[Question], bool]` | **总入口**：无简历短路 → 放大池 → 推导 dims → 调 `_match_by_resume` → 降级取 `pool[:size]`。返回 `(题目, 是否用了 AI)` | 不直接调 Provider |
| `_match_by_resume(db, user, resume, position_id, dims, pool, size) -> list[Question] \| None` | **只负责 AI 这一段**：取岗位名、调 Provider、捕获 `AIProviderError`、按池内 id 过滤。**失败 / 未命中 / 结果全无效一律返回 `None`** | 不取池、不推导 dims、不降级、不写库 |
| `_resume_pool_size(size: int) -> int` | 池大小 `min(size*4, 100)`（§5.2） | — |
| `_position_name_for(db, position_id: int \| None) -> str` | 经 question 既有供给取岗位名（§4.4） | **不得 import `position`** |

> **`_pick_questions` 与 `_match_by_resume` 拆开的理由**：前者是**流程编排**（含降级决策），后者是**一次外部调用的封装**。合在一起的话，降级逻辑会与 AI 调用细节交织，「AI 失败要降级」这条 PRD 要求就埋进了 `except` 块里，测试也难以用注入的 Provider 单独覆盖 AI 段。

> **`_pick_questions` 返回 `(题目, bool)` 而不是只看题目**：`resume_match_applied` 必须由**取题时的事实**决定，不能用「题目是不是按相关度排的」之类的隐式推断（§5.1）。

### 4.4 岗位名的来源（**不得 import position**）

| 需求 | 供给 | 约束 |
|---|---|---|
| 岗位名 | `question_service.list_practice_positions(db)` → 按 `position_id` 查名称 | 该供给**只下发 id / 名称 / 题量，不下发 JD**（PRD §4.7、module-10 §4.4） |
| JD | **拿不到，也不该拿** | 同上。刷题不绑定岗位，JD 对「按简历选排」不是必需输入 |
| 岗位 id 未指定时 | 返回 `""` | 未选岗位即全库随机刷题（`position_id` 允许 NULL） |

> **`dims` 从候选池里推导，不从岗位取**：
> ```python
> dims = sorted({q.dimension for q in pool if q.dimension})
> ```
> 这样既绕开了 `position` 依赖，又保证 `dims` **必然非空**（池子非空 ⇒ 至少有一个维度），从根上避免 `ai` 层因 `dims` 为空而抛错（module-18 §4.1）。
>
> **JD 传空串**：`ai.match_questions_by_resume` 的真实实现会把 `jd` 放进 prompt；刷题场景传 `""` 时该行是空的。这是**已知且可接受**的，因为刷题确实没有岗位上下文——详见 §10 的权衡。

### 4.5 跨包契约

**本模块消费 `resume`（module-17 §4.5）**

| 调用 | 用途 |
|---|---|
| `resume.service.ensure_mine(db, user, resume_id) -> Resume` | 校验「这份简历是我的」并拿到 `content`；不存在 404 / 非本人 403，**由它抛** |

> **只需要 `ensure_mine`，不需要 `load_unchecked`**：刷题场景下简历的归属人就是调用者本人，不存在 `interview` 那种「HR 读候选人简历」的跨主体读取。
>
> ⚠️ **禁止 `practice` 直接 import `resume.repository`**（跨模块跳层无测试监管，见 module-17 §4.5）。`test_architecture.py` 只看同模块内引用，**不会拦下这条**。

**本模块消费 `question`（既有，无改动）**

| 调用 | 用途 |
|---|---|
| `question_service.list_practice_questions(db, filters, limit)` | 候选池取题。**与既有取题同一入口**，因此口径天然一致 |
| `question_service.list_practice_positions(db)` | 仅用于取岗位名（§4.4） |

---

## 5. 业务流程设计

### 5.1 `start_session` 的分支结构（改动总览）

```
start_session(db, user, data):
 1. _check_rate_limit(user)                          ← 既有，不变
 2. size 校验（超 PRACTICE_SESSION_SIZE_MAX → 400）  ← 既有，不变
 3. filters = PracticeFilters(...)                   ← 既有，不变
 4. ┌─ 新增：若 data.resume_id is not None
    │      resume = resume_service.ensure_mine(db, user, data.resume_id)   ← 404 / 403
    │   否则 resume = None
 5. ┌─ 新增：questions = _pick_questions(db, user, filters, size, resume)   ← §5.2
 6. 若 questions 为空 → BusinessError(409)            ← 既有，不变
 7. 建会话（**新增两个字段**）
        resume_id             = resume.id if resume else None
        resume_match_applied  = <第 5 步是否真的用了 AI>     ← §5.2
 8. 建待答项（**快照逻辑完全不变**，seq 从 1 开始）
 9. commit；返回 _session_detail(...)（响应含两个新字段）
```

| 要点 | 说明 |
|---|---|
| **第 4 步在取题之前** | 取不到简历就没有候选池可言；且归属校验应当先于任何取题动作，避免「先查了一堆题才发现简历不是你的」 |
| **第 7 步的 `resume_match_applied` 来自第 5 步的判定结果** | 第 5 步需返回「取到的题 + 是否用了 AI」两项信息。实现上让 `_pick_questions` 返回一个二元组或小 dataclass，**不要用「questions 是不是按相关度排的」这类隐式判断** |
| **第 8 步零改动** | 无论题目来自筛选还是 AI 选排，快照都照写。**AI 推荐不改变快照机制**——这是本模块能与既有判分 / 错题本 / 统计完全解耦的原因 |

### 5.2 取题分支与降级（**本模块的核心逻辑**）

> 本节的步骤 1–2、6–7 属 `_pick_questions`（流程编排与降级决策），步骤 3–5 属 `_match_by_resume`（AI 调用封装）。两者的职责边界见 §4.3。

```
_pick_questions(db, user, filters, size, resume) -> (questions, applied):
 1. 若 resume is None:
        return question_service.list_practice_questions(db, filters, size), False
        ← 未关联简历：与既有行为逐字一致（连 SQL 都一样）

 2. pool_size = _resume_pool_size(size)
    pool = question_service.list_practice_questions(db, filters, pool_size)
    若 pool 为空:
        return [], False          ← 交由第 6 步报 409「没有符合条件的题目」（既有文案）

    dims = sorted({q.dimension for q in pool if q.dimension})   ← 由池内维度推导（§4.4）
    picked = _match_by_resume(db, user, resume, filters.position_id, dims, pool, size)
    若 picked is None → return pool[:size], False               ← **降级**
    否则              → return picked, True


_match_by_resume(db, user, resume, position_id, dims, pool, size) -> list[Question] | None:
 3. position_name = _position_name_for(db, position_id)

 4. try:
        matched = get_provider().match_questions_by_resume(
            resume_text=resume.content,
            position_name=position_name,
            jd="",                         ← 见 §4.4：刷题没有 JD 上下文
            dims=dims,
            candidates=_briefs(pool),
            count=size,
        )
    except AIProviderError:
        logger.warning("按简历推荐失败，降级为筛选取题（user=%s）", user.id)
        return None

 5. 若 matched 为空:
        logger.info("按简历推荐未命中，降级为筛选取题（user=%s）", user.id)
        return None

 6. by_id = {q.id: q for q in pool}
    picked = [by_id[m.question_id] for m in matched if m.question_id in by_id]
    若 picked 为空 → return None          ← 理论上不可达（ai 层已过滤），双保险
    return picked                          ← 顺序即相关度顺序
```

| 决策 | 理由 |
|---|---|
| **候选池必须比 `size` 大** | 若只取 `size` 题再让 AI 排序，AI **只能重排、不能改选**——「按简历推荐」就退化成「换个顺序的同一批题」。**这是本设计的关键点**：池子不给大，整条功能没有意义 |
| **降级取 `pool[:size]`** | 降级后的结果必须**与不传 `resume_id` 时完全一致**。由于池子是按同一条 SQL（同一排序）取的前 `pool_size` 条，其前 `size` 条正是「不传 `resume_id` 时取到的 `size` 条」。**同一入口取两次，结果必然相同** |
| **AI 失败与「未命中」都降级，但日志级别不同** | 前者是故障（`warning`），后者是正常结论（`info`）。两者都不阻塞开练（PRD §7 只要求失败不阻塞，「未命中」一并降级是为了让候选人总能开练） |
| **不把 AI 失败上报为 5xx** | PRD §7 明确「不阻塞开始练习」。若报错，候选人会因为后端 AI 故障而无法刷题——**一个降级可用、一个完全不可用**，取舍明确 |
| **`picked` 用 `by_id` 再过滤一次** | `ai` 层已保证 id 来自池内（module-18 §5.3）。此处冗余是刻意的：`ai` 是抽象接口，不能假定将来换的实现也守约 |
| **`matched` 的顺序即相关度顺序** | `ai` 层返回的是**已按相关度降序**的列表（module-18 §4.1 的稳定排序）。本模块**不再排序**，否则会出现第二套相关度判据 |

**`_resume_pool_size`**

```
_resume_pool_size(size) = min(size * _RESUME_POOL_FACTOR, _RESUME_POOL_MAX)
    _RESUME_POOL_FACTOR = 4
    _RESUME_POOL_MAX    = 100
```

| 决策 | 理由 |
|---|---|
| **因子 4** | 默认 `size=10` → 池 40 题，AI 有足够挑选空间；`size` 上限 20 → 池 80，仍在单次 prompt 可承受范围（每题几十字，80 题约 4–6 千字） |
| **上限 100** | 防 `size` 与因子相乘后把整库塞进 prompt。**它是给 AI 上下文上的护栏**，与 `PRACTICE_SESSION_SIZE_MAX` 保护的是两件事 |
| **用模块常量而非配置项** | 它是**实现内部的比例**，不是运维旋钮：调它不会改变产品语义，只会改变 prompt 大小与挑选空间。加配置项会增加一个没人会去调的键 |

> ⚠️ **已知局限（必须写进文档，不要当作没问题）**：候选池来自 `list_practice_questions`，它是**按 id 排序**取前 N 条。因此当符合筛选条件的题目**多于池上限**时，**排在后面的题永远进不了推荐**。对题库规模不大的本项目（单机演示）无影响，但这是一个真实的偏差。修法（向量召回、全库打分）都超出 MVP 范围，**明确不做**（§10）。

### 5.3 降级路径的正确性论证（**为什么降级结果与「不关联简历」等价**）

```
不关联简历：  list_practice_questions(filters, size)      → 结果 R
关联 + 降级： list_practice_questions(filters, pool_size)[:size] → 结果 R'

pool_size = min(size*4, 100) >= size   （size 上限 20 ⇒ pool_size >= 20 >= size）
```

两次调用**同一条 SQL、同一排序**，只差 `limit`。因此前 `size` 条**逐条相同**（`limit` 只是截断，不影响前缀）。⇒ **`R' == R`**。

> **这个论证是「降级不引入行为差异」的保证**。若把池子的取法改成别的（比如按维度轮询、或加大后打乱），降级结果就会与不传 `resume_id` 时不同，产生「关联了简历反而拿到不一样的题」这种无从解释的现象。**执行时不得改动候选池的取法。**

### 5.4 与既有能力的关系（零改动的部分）

| 既有能力 | 本次是否受影响 | 说明 |
|---|---|---|
| 快照写入（`content_snapshot` 等 5 个字段） | **不变** | 题目来源与快照无关 |
| `seq` 从 1 开始 | **不变** | AI 返回的顺序即 `seq` 顺序，`enumerate(..., start=1)` 照用 |
| 单选题本地判分 / 简答 AI 判分 | **不变** | 判分只看 `question_type` 与参考答案 |
| AI 判分失败 → `is_correct` 为空 | **不变** | 与「推荐失败」是两回事：推荐失败影响**取题**，判分失败影响**评分** |
| 错题本 / 统计 | **不变** | 纯派生查询，与会话出身无关 |
| 限流 | **不变** | `start_session` 仍计一次；**AI 调用不额外计数**（见 §10） |
| `preview_questions` | **不变** | 不接 `resume_id`（§1.2） |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| `resume_id` 不存在 | `NOT_FOUND` | 404 | 简历不存在（`ensure_mine` 抛） |
| `resume_id` 非本人所有 | `FORBIDDEN` | 403 | 无权限访问该简历（`ensure_mine` 抛） |
| `resume_id` 越界（<1） | `VALIDATION_ERROR` | 400 | 请求参数不合法（`detail.fields`） |
| `size` 超上限 | `VALIDATION_ERROR` | 400 | `size` 不能超过 20（**既有文案，不变**） |
| 无符合条件的题目（含降级后仍无题） | `BUSINESS_ERROR` | 409 | 没有符合条件的题目，请调整筛选条件（**既有文案，不变**） |
| **按简历推荐 AI 失败** | — | **正常建会话** | **不报错**：降级为筛选取题，`resume_match_applied=false`（§5.2） |
| **按简历推荐未命中** | — | **正常建会话** | **不报错**：同上 |
| 限流超限 | `BUSINESS_ERROR` | 409 | 操作过于频繁，请稍后再试（**既有，不变**） |
| 守卫角色不符 | `FORBIDDEN` | 403 | 无权限执行此操作（module-16） |

> **不新增任何错误码**——全部复用 module-00 §6.3 的八个。
>
> **特别注意**：AI 推荐失败在这里**既不是 5xx 也不是业务错误，而是完全静默地降级并返回 201**。这与 module-13 §5.3「AI 判分失败返回 200」同一态度，但**理由更进一步**：判分失败时作答已保存所以不能报错；而推荐失败时**候选人根本还没做任何事**，报错等于因为后端 AI 故障而拒绝他刷题。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 未关联简历：既有行为零回归（**先写这组**）

| 测试 | 断言 |
|---|---|
| `test_start_without_resume_unchanged` | 不传 `resume_id` → 取题结果与既有用例完全一致 |
| `test_start_without_resume_has_nulls` | `resume_id` 为 null，`resume_match_applied` 为 **false** |
| `test_start_without_resume_does_not_call_ai` | **未调用** `match_questions_by_resume`（用 spy 断言） |
| 既有 `test_practice.py` / `test_practice_router.py` 全部用例 | **零回归** |

> **第一组必须是零回归验证**：本模块的改动落在最核心的 `start_session` 上，先证明「没关联简历时一行行为都没变」，才能认为改动是**纯增量**的。

### 7.2 按简历推荐正常路径

| 测试 | 断言 |
|---|---|
| `test_start_with_resume_applies_match` | Mock 返回 3 条 → 会话题数为 3，`resume_match_applied` 为 **true** |
| `test_start_with_resume_orders_by_match_result` | 会话内题目顺序 == Mock 返回的相关度顺序（**不是** id 顺序） |
| `test_start_with_resume_uses_larger_pool` | 断言传给 AI 的 `candidates` 长度 == `_resume_pool_size(size)`（池子确实被放大） |
| `test_start_with_resume_pool_capped` | `size=20` → 传给 AI 的候选数 `<= 100` |
| `test_start_with_resume_passes_resume_content` | 传给 AI 的 `resume_text` == 该简历的 `content` |
| `test_start_with_resume_derives_dims_from_pool` | 传给 AI 的 `dims` == 池中维度的有序去重集合 |
| `test_start_with_resume_position_name_lookup` | 指定 `position_id` → 传给 AI 的 `position_name` 为该岗位名；未指定 → `""` |
| `test_start_with_resume_jd_is_empty` | 传给 AI 的 `jd == ""`（刷题无 JD 上下文） |
| `test_start_with_resume_writes_snapshots` | 快照 5 个字段照写，与题库一致（**推荐不改变快照机制**） |
| `test_start_with_resume_seq_starts_at_one` | 追加题目的 `seq` 从 1 连续 |

### 7.3 降级路径（**本模块最重要的测试组**）

| 测试 | 断言 |
|---|---|
| `test_start_ai_failure_degrades` | 注入抛 `AIProviderError` 的 Provider → **201**，会话正常建成 |
| `test_start_ai_failure_flag_false` | 上述场景 `resume_match_applied` 为 **false**，`resume_id` **仍为简历 id** |
| `test_start_ai_failure_result_equals_no_resume` | **降级取到的题目与「不传 `resume_id`」逐条相同**（§5.3 的论证） |
| `test_start_ai_failure_still_counts_rate_limit` | 仍计了一次限流 |
| `test_start_ai_empty_result_degrades` | Mock 返回 `[]` → 201，`resume_match_applied` 为 false，题目为筛选结果 |
| `test_start_ai_empty_result_distinct_log` | 未命中走 `info` 而非 `warning`（区分「正常未命中」与「故障」） |
| `test_start_pool_empty_reports_409` | 筛选条件无任何题 → 409，**且未创建会话**（既有约定） |
| `test_start_ai_unknown_ids_degraded_safely` | Provider 返回池外 id → 全部被过滤；`picked` 为空 → 降级且 `applied=false` |

### 7.4 归属与隔离

| 测试 | 断言 |
|---|---|
| `test_start_with_other_candidates_resume_403` | 候选人 A 传 B 的简历 → 403 |
| `test_start_with_missing_resume_404` | 不存在的 `resume_id` → 404 |
| `test_start_with_resume_does_not_leak_collection` | 403 场景下**未执行任何取题或 AI 调用**（归属校验先于取题） |
| `test_start_endpoints_still_reject_hr` | hr 调 `POST /practice/sessions` → 403（既有回归） |
| `test_start_endpoints_still_reject_admin` | admin → 403（既有回归） |

### 7.5 契约与结构

| 测试 | 断言 |
|---|---|
| `test_session_detail_exposes_new_fields` | `GET /practice/sessions/{id}` 含 `resume_id` 与 `resume_match_applied` |
| `test_session_list_item_unchanged` | `GET /practice/sessions` 的列表项**不含**这两个字段（§4.2） |
| `test_preview_endpoint_has_no_resume_param` | `GET /practice/questions` 传 `resume_id` 被忽略（或 400），**且不调用 AI** |
| `test_practice_does_not_import_resume_repository` | **静态断言**：`practice/` 下任一文件**顶层**不出现 `from app.resume import repository` |
| `test_practice_does_not_import_position` | **静态断言**：`practice/` 下任一文件顶层不出现 `app.position`（防为拿岗位名而破戒，§1.3） |
| `test_no_reverse_dependency[practice]` | 既有架构用例仍通过（`FORBIDDEN_DEPENDENCIES` 未改动） |

> **后两条静态断言是「靠评审守不住、只能靠测试守」的典型**：跨模块跳层与「为了拿个岗位名就 import 一下 position」都不在 `test_architecture.py` 的覆盖内（它只看同模块内的层引用，且 `practice → position` 会被拦，但 `resolve 岗位名` 的诱惑是真实存在的）。

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-17（`resume.ensure_mine`）、module-18（`match_questions_by_resume`）已完成。

### Task 20.1：零回归基线

- [ ] 跑 `pytest tests/test_practice.py tests/test_practice_router.py -q`，确认**当前全绿**（记录基线）
- [ ] 写 §7.1 的三条「不传 `resume_id` 时行为不变」失败测试
- [ ] 提交

### Task 20.2：模型与 schema

- [ ] `PracticeSession` 加 `resume_id`（NULL, FK `RESTRICT`）与 `resume_match_applied`（NOT NULL DEFAULT false）（§3.1）
- [ ] `PracticeSessionCreate` 加 `resume_id`；`PracticeSessionDetail` 加两个字段（§4.2）
- [ ] **不写迁移**（PRD §11）
- [ ] 写失败测试：未关联时 `resume_match_applied` 为 false
- [ ] 提交

### Task 20.3：候选池与 AI 选排（不改 `start_session`）

- [ ] 新增 `_RESUME_POOL_FACTOR` / `_RESUME_POOL_MAX` 与 `_resume_pool_size`（§5.2）
- [ ] 新增 `_briefs` 适配（ORM → `QuestionBrief`）
- [ ] 新增 `_position_name_for`（走 `list_practice_positions`，**不得 import position**）（§4.4）
- [ ] 新增 `_match_by_resume`（**含 try/except 与空结果分支，一律返回 `None` 表示降级**）
- [ ] 新增 `_pick_questions`（编排 + 降级，返回 `(题目, applied)` 二元组）
- [ ] 写失败测试：池子大小、`dims` 推导、`jd == ""`、池外 id 被过滤
- [ ] 运行确认通过
- [ ] 提交

### Task 20.4：接入 `start_session`

- [ ] 按 §5.1 的九步改造 `start_session`（第 4、5、7 步是新增；其余不动）
- [ ] 写 §7.2 全部失败测试（**含「顺序为相关度顺序」「池子被放大」「快照照写」**）
- [ ] 运行确认通过
- [ ] 提交

### Task 20.5：降级路径

- [ ] 写 §7.3 全部失败测试（**含「降级结果与不传 `resume_id` 逐条相同」「`resume_id` 仍保留」「空结果与故障日志分级不同」**）
- [ ] 运行确认通过（实现应已具备，本任务主要是补测试与修正分支）
- [ ] 提交

### Task 20.6：归属、契约与全量回归

- [ ] 写 §7.4 / §7.5 全部测试（**含两条静态断言与「列表项不含新字段」**）
- [ ] 运行 `pytest tests/ -q`，**全部通过**（含 `test_practice.py` 既有用例零回归）
- [ ] 提交

---

## 9. 验收标准

- [ ] `practice_session` 新增 `resume_id`（NULL, FK `RESTRICT`）与 `resume_match_applied`（NOT NULL DEFAULT false）
- [ ] **只改模型、不写迁移、不同步 `script.sql`**
- [ ] `POST /practice/sessions` 接受可选 `resume_id`；**端点集合与路径不变**（仍九个）
- [ ] `PracticeSessionDetail` 含两个新字段；**列表项与摘要不变**
- [ ] `GET /practice/questions`（预览）**不接** `resume_id` **且不调用 AI**
- [ ] 未关联简历时，取题结果、快照、`seq`、限流**与改动前逐条一致**（零回归）
- [ ] 关联简历时，**候选池被放大**（`min(size*4, 100)`）后才调 AI——AI 能**改选**而不仅是重排
- [ ] 调 AI 时：`resume_text` 为简历正文、`dims` **由池内维度推导**、`position_name` 经 question 供给取得（未指定岗位时为 `""`）、`jd` 为 `""`
- [ ] AI 返回的顺序**即**会话内 `seq` 顺序，本模块**不二次排序**
- [ ] AI 失败 → **201 正常建会话**，`resume_match_applied=false`，题目与「不传 `resume_id`」**逐条相同**
- [ ] AI 返回空 → 同样降级；**日志级别与故障区分**（info vs warning）
- [ ] 降级时会话的 `resume_id` **仍保留**（表达「候选人想用哪份」这一事实）
- [ ] 池外 id 被过滤；过滤后为空则安全降级
- [ ] 关联非本人简历 → 403；不存在 → 404；**且校验先于取题**
- [ ] `practice` **未新增** `position` 依赖；顶层不 import `resume.repository`；**两条静态断言存在且通过**
- [ ] 判分 / 错题本 / 统计 / 限流 / 快照机制**零改动**
- [ ] 未新增配置项、未新增错误码；既有用例零回归

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **候选池不给大，AI 就只能重排** | 池 = `min(size*4, 100)` | 若只取 `size` 题再让 AI 排序，「按简历推荐」退化成「同一批题换个顺序」，整条功能失去意义。**这是本模块最关键的一个数字** |
| **候选池按 id 取前 N 条，池外的题永远进不了推荐** | 接受该偏差，并在文档写明 | 题库规模不大时无影响。修法（向量召回 / 全库打分）超出 MVP 范围。**写进文档而不是假装没有问题** |
| **降级结果必须与「不传 `resume_id`」完全一致** | 复用同一取题入口，只改 `limit` 后取前缀（§5.3 有论证） | 否则会出现「关联了简历反而拿到不一样的一组题」这种无法解释的现象 |
| **降级要不要留痕** | 新增 `resume_match_applied` 列 | 不加就无法区分「未关联简历」与「关联了但 AI 没生效」。降级静默 = 候选人以为功能坏了。与本项目「降级必须可观测」的一贯做法一致 |
| **AI 失败不返回 5xx** | 静默降级 → 201 | PRD §7 明确「不阻塞开始练习」。若报错，候选人会因为后端 AI 故障而**无法刷题**——降级可用 vs 完全不可用，取舍明确 |
| **不能 import `position` 拿岗位名** | 走 `question_service.list_practice_positions` | `FORBIDDEN_DEPENDENCIES["practice"]` 含 `position`，import 会让架构测试立刻变红。**但「为了拿个名字就破戒」的诱惑是真实的**，故加静态断言 |
| **JD 传空串** | 传 `""`，并在文档写明 | `list_practice_positions` 的契约**刻意不下发 JD**（PRD §4.7 明确），且刷题本来就不绑定岗位。真实 Provider 的 prompt 里该行为空，属已知的措辞质量损失，不影响选排逻辑 |
| **`resume_id` 越界（<1）在 schema 拦，不在 service** | `Field(ge=1)` | 它是纯粹的参数形态问题，不是业务规则，与 `size` 的处理方式（在 service 拦，因为上限来自配置项）不同——**差异的原因不同，不是不一致** |
| **AI 调用不计入限流** | 沿用既有「只有计分动作计数」的口径 | `start_session` 本身已计一次，AI 调用是它的内部环节，不构成额外的候选人动作 |
| **预览接口不支持简历** | 预览不接 `resume_id` | 既有注释明确预览「不创建会话、不写快照，因此也不计入限流」。让它调 AI 会**打破这一性质**，产生未计入限流的 AI 消耗，且预览是高频动作 |
| **不改 `repository.py`** | 不动 | `create_session(db, **fields)` 已接受任意字段，新增两列无需改仓储层。**能不动就不动**，减少回归面 |
| **列表项不加新字段** | 只加在详情 | 列表刻意「不含题目明细」以保持轻量（module-13 §4.2）。加简历信息会带来同样的膨胀，且列表要回答的是「练过哪些」 |
| **不做「上次用的简历」记忆** | 每次显式传 | 隐式状态会让「为什么这次推荐不一样」无法解释；也让「换一份简历」变成需要先清除记忆的操作 |
