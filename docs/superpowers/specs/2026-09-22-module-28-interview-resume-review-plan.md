# interview 简历评估端点 执行计划书（MVP-4 §4.15）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：interview **MVP-4 增量**（简历 AI 评估的两个端点：HR 侧 + 候选人侧）
**所属包**：`backend/app/interview/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.15（简历 AI 评估）、§5.3 ⑧、§7（MVP-4 错误条目）、§8（两端点入表）、§9（候选人可见性）
**前置依赖**：[module-27 ai `evaluate_resume`](./2026-09-22-module-27-ai-resume-review-plan.md)、[module-19 interview](./2026-09-21-module-19-interview-plan.md)（本模块是它的增量）、[module-17 resume](./2026-09-21-module-17-resume-plan.md)
**本模块被谁依赖**：[module-29 前端增量](./2026-09-22-module-29-frontend-resume-review-plan.md)、[module-30 e2e](./2026-09-22-module-30-e2e-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **不落库、不缓存**：评估结果不写任何表，也不改变面试状态（§4.15）
- **不限面试状态**：`draft` / `ongoing` / `completed` / `evaluated` 均可触发 —— 与 §4.14 补题要求 `ongoing` **刻意相反**（评估不写数据，补题会追加题目）
- **候选人侧沿用 `CANDIDATE_FEEDBACK_LEVEL`**：`summary`（默认）不下发 `match_score`，`full` 才下发；亮点与差距在任何档位都下发（§4.15、§9）
- **结论不带去留判断**（§4.15、§4.9）
- AI 失败 → **502 `AI_PROVIDER_ERROR`，不降级**（§7）
- **越权一律 403**：HR 调他人面试、候选人调未接受邀请的面试（沿用既有的面试可见性语义）
- 分层单向 `router → service → repository`；**router 不得直接 import repository**（module-08 §5.4）
- **不新增错误码、不新增表、不新增依赖**（§7、§4.15）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| HR 侧端点 | `POST /interviews/{id}/resume-review`，判据同 §4.14 | §4.15 |
| 候选人侧端点 | `POST /candidate/interviews/{id}/resume-review`，判据同 §4.13 | §4.15 |
| 前置校验 | 未关联简历 / 岗位无维度 → 409 | §4.15、§7 |
| 取数组装 | 岗位（名 + JD + 维度）+ 该场简历正文 → 调 ai | §6 |
| 视图脱敏 | 候选人侧按 `CANDIDATE_FEEDBACK_LEVEL` 决定是否下发分数 | §4.15、§9 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **落库 / 缓存评估结果** | PRD §4.15 明确「不落库、每次现算」。**不要为它加表或加列** |
| **限制面试状态** | 评估无副作用，任何状态都能评估（§4.15）。**照抄补题的 `status != ongoing → 409` 是错的** |
| **把分数塞进报告 / 反馈** | 报告与候选人反馈的数据来源是**面试作答与评估**（§4.5、§4.9），简历评估是正交的另一件事 |
| **跳过分级、HR 也脱敏** | HR 侧始终带分数（§4.9 既有口径：HR 看全部评分） |
| **候选人侧回传 `job_level` 之类的档位参数** | 档位是**部署配置**，不是请求参数。让调用方传等于把脱敏开关交给了被脱敏的人 |
| **批量评估 / 多候选人对比** | PRD §1.3 非目标 |
| **前端 / e2e** | 属 module-29 / module-30 |

### 1.3 依赖方向（不新增任何边）

```
interview.router ────────┐
interview.candidate_router ┼─→ interview.service ─→ interview.repository ─→ interview 表
                          │            │
                          │            ├─→ position.service（JD + 维度）
                          │            ├─→ resume.service.load_unchecked（简历正文）
                          │            └─→ ai.get_provider()（evaluate_resume）
```

> **本模块不新增任何依赖边**：`interview` 早已同时依赖 position / resume / ai。这正是把端点放这里、而不是放 `resume` 的原因（`resume` 禁止依赖 `position`，PRD §3.3、§4.15）。

---

## 2. 文件结构

**本模块需修改的文件**

| 文件 | 修改内容 |
|---|---|
| `backend/app/interview/schemas.py` | 新增 `ResumeReviewView`（HR）与 `CandidateResumeReviewView`（候选人） |
| `backend/app/interview/service.py` | 新增 `review_resume`、`review_resume_for_candidate` 与共用的私有组装函数 |
| `backend/app/interview/router.py` | 新增 HR 端点 |
| `backend/app/interview/candidate_router.py` | 新增候选人端点 |
| `backend/tests/test_interview_resume_review.py`（新） | service 层用例 |
| `backend/tests/api/test_api_interview.py` | HR 端点用例 |
| `backend/tests/api/test_api_candidate.py` | 候选人端点用例 |

> **两个 service 函数写在既有的 `service.py` 里，不另开文件**：本项目的分层测试按 `router.py` / `service.py` / `repository.py` 三个固定文件名判定（`test_architecture.py` 的 `LAYER_FILES`）。另开一个 `resume_review.py` 会让「router 是否绕过 service」这类检查**看不到它**。`evaluation/export.py` 之所以能独立成文件，是因为它是**纯函数工具**而非 service 层（module-21 的取舍）。**本模块照 `service.py` 走。**
>
> **`repository.py` 不需改**：所需的读取（`get_resume_id_of_interview`、`get_position`）在 module-19 里**都已存在**。若执行时发现缺一个读取函数，加在 repository 层并**在 commit message 里说明**——不要在 service 里直接写查询（`test_service_uses_repository_not_raw_sql` 会拦）。

---

## 3. 接口契约

### 3.1 端点

| 方法 | 路径 | 守卫 | 说明 | 成功码 |
|---|---|---|---|---|
| POST | `/api/interviews/{id}/resume-review` | `require_roles(admin, hr)` | 对关联简历与该场岗位做 AI 匹配度评估 | 200 |
| POST | `/api/candidate/interviews/{id}/resume-review` | `require_roles(candidate)` | 同上，按档位脱敏 | 200 |

**请求**：**无请求体**。评估不需要任何参数——岗位来自面试、简历来自关联、档位来自配置。

> **为什么无请求体**：可传的参数只有「岗位」与「简历」，而两者都由面试决定，让调用方传等于给了越权的口子（传别人的 resume_id）。**与 `POST /interviews/{id}/invitations` 的「无请求体」同一形态**（module-12 已开此先例）。
>
> 因此前端用 `api.post(path)`（**不传 body**）——`api.js` 在 `body === undefined` 时不设 `Content-Type`，后端也不期待任何 body。

### 3.2 响应结构

**`ResumeReviewView`（HR 侧）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `match_score` | float | 0–10，1 位小数，**恒非空** |
| `conclusion` | str | 综合结论 |
| `strengths` | list[str] | 亮点，1–5 条 |
| `gaps` | list[str] | 差距，0–5 条 |

**`CandidateResumeReviewView`（候选人侧）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `match_score` | float \| **null** | `summary` 档为 `null`，`full` 档为 0–10 |
| `conclusion` / `strengths` / `gaps` | 同 HR | 任何档位都下发 |

> **两个 schema 而不是一个 + 可选字段**：两个端点本就是两个视图，字段可空性不同（HR 恒非空、候选人可为 null）。共用会把「HR 也可能拿到 null」写进类型里，让前端对 HR 侧写一段永远不触发的空值分支。
>
> **不新增「档位」字段下发**：候选人不需要知道部署配了哪一档。这与 module-14 处理 `generate_candidate_feedback` 的方式一致。

### 3.3 service 层签名

| 签名 | 返回 | 职责 |
|---|---|---|
| `review_resume(db, user, interview_id: int) -> ResumeReviewResult` | AI 结果 | HR 路径：`_get_visible` 判可见 → 组装 → 调 ai（§5.1） |
| `review_resume_for_candidate(db, user, interview_id: int) -> ResumeReviewResult` | AI 结果 | 候选人路径：`get_interview_for_candidate` 判可见 → 同一组装（§5.1） |
| `_build_resume_review(db, interview: Interview) -> ResumeReviewResult` | AI 结果 | **共用组装与前置校验**（§5.1） |

> **两个公开函数、一个私有组装**：两条权限链不同（`_get_visible` vs `get_interview_for_candidate`），但**校验与取数完全一致**。把组装抽出来是为了让「未关联简历」「岗位无维度」这两条前置条件**只有一处实现**——否则两条路径会各自漂移，出现「HR 侧报 409、候选人侧报 500」这种难以解释的差异。
>
> **两个公开函数都不做状态检查**（§1.2）。

---

## 4. repository 层

**不需新增函数。** 复用 module-19 既有的：

| 函数 | 用途 |
|---|---|
| `repository.get_resume_id_of_interview(db, interview_id)` | 取该场关联的简历 id |
| `repository.get_position(db, position_id)` | 取岗位（名称 + JD + `evaluation_dimensions`） |

> **不新增 `get_interview_resume_review` 之类**：评估没有持久化，repository 里没有任何对应的读写。

---

## 5. 业务流程设计

### 5.1 主流程

```
review_resume(db, user, interview_id):                 # HR 侧
1. interview = _get_visible(db, user, interview_id)     # 他人面试 → 403
2. return _build_resume_review(db, interview)

review_resume_for_candidate(db, user, interview_id):   # 候选人侧
1. interview = get_interview_for_candidate(db, user, interview_id)  # 未接受邀请 → 403
2. return _build_resume_review(db, interview)

_build_resume_review(db, interview):
1. resume_id = repository.get_resume_id_of_interview(db, interview.id)
     为 None → 409「该面试尚未关联简历」
2. resume = resume_service.load_unchecked(db, resume_id)     # 无权限过滤，module-17 §4.5
     为 None → 409「关联的简历已不可用」
3. position = repository.get_position(db, interview.position_id)
   dims = list(position.evaluation_dimensions) if position else []
     dims 为空 → 409「岗位未定义评估维度，无法评估简历」
4. return get_provider().evaluate_resume(
       position_name=position.name,
       jd=position.jd,
       dims=dims,
       resume_text=resume.content,
   )
```

| 要点 | 说明 |
|---|---|
| **`load_unchecked` 是唯一正确的读法** | HR 读的是**别人的**（候选人的）简历。用 `ensure_mine` 必然 403（module-17 §4.5 的契约）。**候选人侧也用它**——因为归属已由 `get_interview_for_candidate` 的邀请链判过，重复判一次反而会把 admin 之外的角色弄乱 |
| **步骤 1–3 与 AI 调用之间没有任何写操作** | 因此 AI 失败时**数据库零改动**，不需要补偿/回滚。与 §4.14 补题同一形态 |
| **409 而非 404** | 「面试存在但还没关联简历」是**状态不满足**，不是资源不存在。与 §4.14 补题的「该面试尚未关联简历」用同一码同一文案，**保证前端两条链路可用同一段处理** |
| **`position` 为 None 也走 409** | 若面试的 `position_id` 指向已不存在的岗位（理论上被 RESTRICT 挡住，但防御性保留），`dims` 会是空列表，自然落到 409。**不要为它单独加一个 404** |
| **不 catch `AIProviderError`** | 全局异常处理器已把它转成 502 `AI_PROVIDER_ERROR`（§7）。**在 service 里 catch 会让 502 变成一个自制的 500** |

### 5.2 视图脱敏（候选人侧）

```
router（候选人端点）:
1. result = service.review_resume_for_candidate(db, user, interview_id)
2. level = get_settings().candidate_feedback_level
3. match_score = result.match_score if level == FEEDBACK_LEVEL_FULL else None
4. return CandidateResumeReviewView(
       match_score=match_score,
       conclusion=result.conclusion,
       strengths=result.strengths,
       gaps=result.gaps,
   )
```

| 要点 | 说明 |
|---|---|
| **脱敏发生在 router 层，不在 service 也不在 ai** | 它是**「谁在看」**的问题：service 拿到的是 AI 结果（与调用者身份无关），router 才知道这是候选人端。**这与 `generate_candidate_feedback` 在 ai 层接收 `level` 的差异，理由见 module-27 §5.4**（那里档位改变文案本身，这里只决定分数发不发） |
| **档位常量复用 ai 层的 `FEEDBACK_LEVEL_FULL`** | `get_settings().candidate_feedback_level` 的取值白名单由 `core.config.CANDIDATE_FEEDBACK_LEVELS` 校验（非法即拒绝启动），ai 层另有一份同值常量（module-11 已记录这处刻意的重复）。**取哪一份都行，但只取一份，不要写字符串字面量 `"full"`** |
| **`strengths` / `gaps` 不脱敏** | §4.15 明确：任何档位都下发。它们与「分数」不同类——分数是评估结果，文案是可照做的建议 |
| **`conclusion` 不脱敏但也不改写** | 与 `generate_candidate_feedback` 的「重写」不同：本能力的结论**从来就不含去留判断**（module-27 §4.2 的措辞红线），因此无需为候选人重写一版 |

---

## 6. 错误契约（PRD §7）

| 场景 | 状态码 | code | 文案 |
|---|---|---|---|
| HR 调他人面试的评估 | 403 | `FORBIDDEN` | 沿用既有语义 |
| 候选人调未接受邀请的面试 | 403 | `FORBIDDEN` | 沿用既有语义 |
| 面试不存在 | 404 | `NOT_FOUND` | 沿用既有语义 |
| 未关联简历 | 409 | `BUSINESS_ERROR` | 「该面试尚未关联简历」 |
| 岗位未定义评估维度 | 409 | `BUSINESS_ERROR` | 「岗位未定义评估维度，无法评估简历」 |
| 关联的简历已不可用 | 409 | `BUSINESS_ERROR` | 「关联的简历已不可用」（防御性，与 §4.14 同款） |
| AI 调用失败 | 502 | `AI_PROVIDER_ERROR` | 由全局处理器产出，**不降级** |

> **错误码一个都不新增**：409 复用 `BusinessError`、502 复用 `AIProviderError`，两者都是既有类型。
>
> ⚠️ **「未关联简历」文案必须与 §4.14 补题逐字一致**（「该面试尚未关联简历」）：前端在面试详情页同时挂着「按简历补题」与「评估匹配度」两个按钮，两者前置条件相同、**前端据同一句文案决定「该引导用户去关联简历」**。文案漂移会让一个按钮的引导失效。

---

## 7. 测试清单

`backend/tests/test_interview_resume_review.py`（service 层，注入 mock Provider）

| # | 用例 | 断言 |
|---|---|---|
| 1 | 未关联简历（HR 路径） | `BusinessError`，文案「该面试尚未关联简历」 |
| 2 | 未关联简历（候选人路径） | 同码同文案（**两条路径必须一致**） |
| 3 | 岗位无 `evaluation_dimensions` | `BusinessError` |
| 4 | 正常评估 | 返回 `ResumeReviewResult`，分数在 0–10 |
| 5 | **评估后库内零变更** | 面试行、题目表、报告表、简历表**逐表断言无新增/无变更**（§4.15 的「不落库」直接断言） |
| 6 | 面试状态为 `draft` / `completed` | **均能评估成功**（与补题的 409 相反） |
| 7 | AI 抛 `AIProviderError` | 异常向上传播（**service 不吞**），且库内零变更 |
| 8 | HR 调他人面试 | `ForbiddenError` |
| 9 | 候选人调未接受邀请的面试 | `ForbiddenError` |

`backend/tests/api/test_api_interview.py`（HR 端点）

| # | 用例 | 断言 |
|---|---|---|
| 10 | 正常评估 | 200，四字段齐全，`match_score` 非 null |
| 11 | **HR 侧不受 `CANDIDATE_FEEDBACK_LEVEL` 影响** | 把配置设为 `summary`，HR 仍拿到分数（**这条防的是「脱敏写成全局」的错**） |
| 12 | 未关联简历 | 409 `BUSINESS_ERROR` |
| 13 | 无 token / 候选人 token | 401 / 403 |
| 14 | AI 失败 | 502 `AI_PROVIDER_ERROR` |
| 15 | **不做状态校验** | `completed` 的面试评估成功（200） |

`backend/tests/api/test_api_candidate.py`（候选人端点）

| # | 用例 | 断言 |
|---|---|---|
| 16 | `summary` 档（默认） | 200，`match_score` 为 **null**，`conclusion` / `strengths` / `gaps` **非空** |
| 17 | `full` 档 | 200，`match_score` 为 0–10 |
| 18 | HR token 调该端点 | 403（候选人侧守卫是精确匹配） |
| 19 | 未接受邀请的面试 | 403 |
| 20 | 未关联简历 | 409，**文案与 HR 侧逐字一致** |

---

## 8. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | 两个端点鉴权正确（HR 侧 401/403、候选人侧 403 精确匹配） | 用例 13、18 |
| 2 | **评估不落库** | 用例 5（逐表断言） |
| 3 | **不限面试状态** | 用例 6、15 |
| 4 | 候选人 `summary` 档拿不到分数、`full` 档拿到 | 用例 16、17 |
| 5 | **HR 侧不受档位影响** | 用例 11 |
| 6 | AI 失败 → 502，不降级 | 用例 14 |
| 7 | 两条路径的 409 文案逐字一致 | 用例 2、20 |
| 8 | 既有 interview 测试全绿（无回归） | `pytest backend/tests/test_interview*.py backend/tests/api/` |
| 9 | `test_architecture.py` 全绿且未改动 | 同上 |
| 10 | 无新增表、无新增错误码、无新增依赖 | `git status` + 人工确认 |
