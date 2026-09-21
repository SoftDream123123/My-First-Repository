# 权限守卫补全执行计划书（存量 HR 路由）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：横切 —— 存量 HR 侧路由的角色守卫补全与候选人隔离纵深防御
**涉及包**：`backend/app/core/`、`backend/app/auth/`、`backend/app/position/`、`backend/app/question/`、`backend/app/interview/`、`backend/app/evaluation/`
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.1（权限守卫收紧）、§4.6（候选人权限）、§9（非功能：权限守卫是强制项）
**前置依赖**：[module-00 core](./2026-09-15-module-00-core-plan.md)、[module-01 auth](./2026-09-15-module-01-auth-plan.md)、[module-09 auth 候选人侧](./2026-09-20-module-09-auth-plan.md)（提供 `require_roles`）
**后续依赖**：[module-12 interview](./2026-09-20-module-12-interview-invitation-plan.md)、[module-13 practice](./2026-09-20-module-13-practice-plan.md)、[module-14 evaluation](./2026-09-20-module-14-evaluation-feedback-plan.md)

---

## ⚠️ 执行顺序约束（**请先读这一节**）

本文件编号为 16、排在 MVP-2 各模块之后，这是**文档编号顺序，不是执行顺序**。

| 约束 | 说明 |
|---|---|
| 本模块必须与 [module-09](./2026-09-20-module-09-auth-plan.md) **同一批次发布**（先于或同时） | module-09 一旦把 `candidate` 写进 `user.role` 枚举，候选人就能注册并拿到 token。此刻存量 HR 路由**仍未挂角色守卫**，候选人 token 可以直接调 `/api/positions`、`/api/questions`、`/api/interviews*` —— 这是一个真实的越权窗口 |
| **不得先发布 module-09、后补本模块** | 两者之间任何时间差都构成越权窗口，哪怕只是本地调试后忘了合并 |
| 建议的落地顺序 | ① module-09 的 Task 9.3（`require_roles`）→ ② **本模块**（存量路由挂守卫）→ ③ module-09 的 Task 9.5/9.6（注册与凭邀请建号） |

> 之所以不把本模块的编号提到 09 之前：你明确要求「先写 MVP-2，后补全权限守卫」，本文档遵循该顺序编写；执行顺序的例外在此显式声明，避免执行者按编号顺序误解。

---

## Global Constraints（全局约束，摘自 PRD）

- **权限守卫收紧（本期必做，不是可选项）**：HR 侧全部接口显式校验角色（admin/hr），候选人侧接口校验 candidate（§4.1、§9）
- 权限校验工具需支持**多角色判定**（§4.1）—— 由 module-09 交付 `require_roles`
- 候选人数据隔离**不能复用 `created_by` 判据**（§4.1）
- 越权访问返回 **403**，语义为「资源存在但无权访问」（§7、module-01 §5.3）
- 角色不缓存在 JWT 中，每请求查库；**权限变更立即生效**（module-00 §5.2）
- 统一响应格式 `{code, message, detail}`（§7）
- **仍是单机 PC 端，技术栈不变**（§2）

---

## 1. 缺口与职责

### 1.1 三个必须闭合的缺口（均已核实到具体代码位置）

| # | 缺口 | 现状 | 后果 | 闭合方式 |
|---|---|---|---|---|
| 1 | **业务路由只有「已登录」校验** | `position` / `question` / `interview` / `evaluation` 的全部端点只依赖 `get_current_user`，无角色判定 | 候选人 token 可创建/读取/删除岗位、题目、面试 —— 越权且会污染 HR 数据 | 全部端点挂 `require_roles("admin","hr")`（§3） |
| 2 | **`scope_owner_id` 把所有非 admin 都当作 owner** | 实现为「`admin` → `None`，其余 → `user.id`」 | candidate 会落入 owner 分支，被当作「创建者是自己」处理，成为一个隐式的放行路径 | 在 `scope_owner_id` 内对非 admin/hr 角色**抛 `ForbiddenError`**（§4），作为纵深防御 |
| 3 | **`require_role` 只支持单角色相等** | 依赖工厂为 `role: str` 单值比较 | 无法表达「admin 与 hr 均可」，HR 侧守卫写不出来 | 由 module-09 交付 `require_roles(*roles)`，本文档逐路由使用（§3） |

> 缺口 1 是**主要风险**，缺口 2 是**纵深防御**。即使缺口 1 已闭合（候选人根本到不了 service 层），缺口 2 仍必须修：任何未来的新端点若漏挂守卫，`scope_owner_id` 是最后一道会拦住候选人的防线。

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **候选人侧路由的守卫**（`/api/candidate/*`、`/api/practice/*`） | 属 [module-12](./2026-09-20-module-12-interview-invitation-plan.md) / [module-13](./2026-09-20-module-13-practice-plan.md)。本文档只管**存量** HR 路由；新路由的守卫由各自模块在实现时直接挂上 |
| **候选人隔离判据**（「持有该面试的有效邀请」） | 属 module-12（数据在 `interview_invitation`） |
| **前端角色门禁** | 已存在（`router.js` 的 `adminOnly`、`shell.js` 的导航过滤）。候选人前端的角色门禁属 [module-15](./2026-09-20-module-15-candidate-frontend-plan.md) |
| **认证方式改造**（Refresh Token、会话表、权限中间件框架） | PRD 未要求。用**依赖工厂**逐端点声明是本项目既定的风格（module-00 §7），不引入全局中间件或策略引擎 |
| **给 `admin` 增加「能看到候选人练习数据」的能力** | PRD §4.6 未定义；admin 在候选人侧**不通行**（module-09 §4.5 的精确匹配规则），保持边界清晰 |
| 限流、审计日志 | 限流属刷题接口（module-13）；审计不在 PRD 范围 |

### 1.3 依赖方向（不变，仅增加依赖声明）

```
各业务 router ──→ core.deps.require_roles ──→ get_current_user ──→ auth 表
各业务 service ──→ auth.service.scope_owner_id / ensure_resource_visible

本模块不新增模块间依赖，只在既有 router 上增加一条 Depends 声明
```

---

## 2. 文件结构

| 文件 | 修改内容 |
|---|---|
| `backend/app/position/router.py` | 全部端点挂 `Depends(require_roles("admin","hr"))` |
| `backend/app/question/router.py` | 同上（**含 module-10 新增的补参考答案端点**） |
| `backend/app/interview/router.py` | 同上（**含 module-12 新增的邀请端点**） |
| `backend/app/evaluation/router.py` | 同上（评估触发、SSE 流、报告读取） |
| `backend/app/auth/router.py` | `/users*` 改用 `require_roles("admin")`（行为不变，统一写法） |
| `backend/app/auth/service.py` | `scope_owner_id` 增加非 admin/hr 的拒绝分支（§4） |

**测试文件**：新增 `backend/tests/test_permissions.py`

**本模块需修改的上游文件**

| 文件 | 修改内容 |
|---|---|
| `backend/README.md` | 补「生产部署应关闭 `CANDIDATE_SELF_REGISTER`」与「单机部署须 `--workers 1`」的说明（§7.4） |

---

## 3. 守卫落点清单

### 3.1 守卫规则（按路径前缀划分，**不要凭本表硬编码端点**）

| 路径前缀 | 守卫 | 备注 |
|---|---|---|
| `/api/health` | **无** | 部署探活，维持公开（module-00 §8） |
| `/api/auth/login`、`/api/auth/register` | **无** | 公开端点（§8） |
| `/api/auth/me` | 仅登录 | 三种角色都可读自己的信息 |
| `/api/users`、`/api/users/{id}` | `require_roles("admin")` | 现状即如此，改写为统一写法 |
| `/api/positions*` | `require_roles("admin","hr")` | 本模块新增 |
| `/api/questions*` | `require_roles("admin","hr")` | 本模块新增 |
| `/api/interviews*`（HR 动作） | `require_roles("admin","hr")` | 本模块新增 |
| `/api/interviews/{id}/report` | `require_roles("admin","hr")` | 在 evaluation 包内注册，勿漏 |
| `/api/candidate/*`、`/api/practice/*` | `require_roles("candidate")` | 属 module-12/13，本模块不实现 |
| **例外**：`POST /api/candidate/invitations/{code}/accept` | **无守卫（公开）** | 见 [module-12 §4.1](./2026-09-20-module-12-interview-invitation-plan.md)（2026-09-21 修正）：拿码的人可能**还没有账号**，要求先登录会让邀请链自相矛盾。它挂在 `/api/candidate` 前缀下，**但不属于上面那组守卫** —— 前缀是分类，守卫是逐个端点挂的 |

> **本表是规则，不是端点清单。** 执行时必须用 `app.routes` 枚举出当前真实路由（§7.1 的自维护不变量测试会做这件事），逐个核对。手抄端点清单在端点增删后必然失效——这正是本模块要修的那类「静默漏掉一处」的问题。

### 3.2 已知需覆盖的端点（按 module 计划书整理，**执行时以代码为准**）

| 包 | 端点（方法 + 路径） | 依据 |
|---|---|---|
| position | POST/GET `/positions`、GET/PUT/DELETE `/positions/{id}` | module-02 §4.1 |
| question | POST/GET `/questions`、GET/PUT/DELETE `/questions/{id}`、POST `/questions/{id}/reference-answer` | module-03 §4.1、module-10 §4.1 |
| interview | POST/GET `/interviews`、GET/PATCH `/interviews/{id}`、POST `/interviews/{id}/answers`、`/complete`、`/rollback` | module-05 §4.1 |
| evaluation | POST `/interviews/{id}/evaluate`、GET `/interviews/{id}/evaluation/stream`、GET `/interviews/{id}/report` | module-06 §4.1 |

> 若执行时发现实际端点与本表不一致，**以 `app.routes` 为准**，并回报差异（说明某份 module 计划书需要更新）。

---

## 4. `scope_owner_id` 纵深防御契约（`auth/service.py`）

### 4.1 改造后的语义

| `user.role` | `scope_owner_id(user)` 返回 | 行为 |
|---|---|---|
| `admin` | `None` | 不过滤，可见全部（PRD §4.1） |
| `hr` | `user.id` | 追加 `WHERE created_by = :owner_id`（PRD §4.1） |
| **其他（含 `candidate`）** | — | **抛 `ForbiddenError`（403）** |

### 4.2 设计要点

| 要点 | 理由 |
|---|---|
| **失败而非返回 `None`** | 返回 `None` 等于「不过滤」，会让候选人看到全部数据——这是最坏的失败方向。**默认拒绝**优于默认放行 |
| **失败而非返回 `user.id`** | 返回 `user.id` 会让候选人被当作「创建者」处理，在语义上伪造了一个事实 |
| **`ensure_resource_visible` 自动获得保护** | 它内部调用 `scope_owner_id`，因此单条资源的可见性判定同样拒绝候选人 |
| **`practice` 不受影响** | module-10 §5.5 已明确刷题取题**不接 `owner_id`**、不走该函数，因此候选人刷题不会撞上这个拒绝分支 |
| **不引入角色层级** | 与 module-09 §5.3 一致：只认 admin 与 hr 两个「可拥有 HR 数据」的角色，显式列出 |

---

## 5. 请求鉴权链路

### 5.1 依赖求解顺序

```
请求 → get_token（401：无 token / 格式错）
     → get_current_user（401：用户不存在 / 已禁用）
     → require_roles(...)（403：角色不符）
     → service（404 / 403：资源不存在 / 越权访问他人资源）
     → repository
```

| 要点 | 说明 |
|---|---|
| **守卫先于 body 校验** | FastAPI 求解依赖时不吞掉依赖抛出的异常，因此 `require_roles` 的 403 会**先于**请求体校验的 400 返回。这让 §7.1 的矩阵测试可以发送空请求体而稳定地断言 403 |
| **403 与 404 的分工** | 角色不符 → 403（连资源存在性都不进入）；角色正确但资源不属于自己 → 也是 403（module-01 §5.3 的既有约定：资源存在但无权访问） |
| **守卫不替代 service 内校验** | 同角色内仍需 `ensure_resource_visible`。守卫解决「是不是这类用户」，service 解决「是不是他的数据」，两者不可互相替代 |

---

## 6. 错误处理（对应 PRD §7）

| 场景 | code | HTTP | message |
|---|---|---|---|
| 无 token | `UNAUTHORIZED` | 401 | 未认证（既有） |
| token 失效 | `INVALID_TOKEN` | 401 | 登录状态已失效，请重新登录（既有） |
| **候选人调用 HR 侧任一端点** | `FORBIDDEN` | 403 | 无权限执行此操作 |
| **HR 调用 admin 专属端点** | `FORBIDDEN` | 403 | 无权限执行此操作（既有） |
| **候选人到达 `scope_owner_id`** | `FORBIDDEN` | 403 | 无权限执行此操作 |
| HR 访问他人资源 | `FORBIDDEN` | 403 | 无权限访问该{资源}（既有） |

> 守卫类错误**统一复用 `FORBIDDEN`**，不新增错误码，也不区分「角色不符」与「越权」的文案——对外无需暴露拒绝的原因是角色还是归属。

---

## 7. 测试设计（对应 PRD §10）

### 7.1 `backend/tests/test_permissions.py`（新增）

**A. 自维护不变量（最重要的两条）**

| 测试 | 断言 |
|---|---|
| `test_no_hr_route_reachable_by_candidate` | 遍历 `app.routes` 中路径以 `/api/positions`、`/api/questions`、`/api/interviews`、`/api/users` 开头的全部路由，用 **candidate token** 发起请求（路径参数统一替换为 `999999`），断言响应状态**恒为 403**；断言**不存在任何 2xx** |
| `test_no_hr_route_reachable_by_hr` | 同样遍历，但只针对路径以 `/api/users` 开头的路由，用 **hr token** 断言恒为 403（admin 专属） |

> 这两条测试的价值在于**它随路由自动扩展**：将来任何人新增 HR 端点而忘记挂守卫，测试立刻失败。若写成手抄端点清单，同样的疏漏不会被发现——那与本模块要修的缺口是同一类错误。

**A2. 候选人侧的对称扫测（`test_no_candidate_route_reachable_by_hr_side`，后补）**

| 测试 | 断言 |
|---|---|
| `test_no_candidate_route_reachable_by_hr_side[hr\|admin]` | 遍历路径以 `/api/candidate`、`/api/practice` 开头的全部路由，用 **hr / admin token** 发起请求，断言恒为 403 |

> ⚠️ **必须排除 `POST /api/candidate/invitations/{code}/accept`**（2026-09-21 修正）：
> 它是公开端点（§3.1 的例外），hr / admin 拿到它不会得到 403。
> 扫测里要维护一份**公开端点白名单**，而不是「凡 `/api/candidate` 前缀必 403」——
> 后者会把「前缀」误当成「守卫」，正是本模块 §3.1 开头警告的那种硬编码。

**B. 角色矩阵（存量端点，逐组断言）**

| 测试 | 断言 |
|---|---|
| `test_position_endpoints_reject_candidate` | 候选人对 position 全部端点 → 403 |
| `test_question_endpoints_reject_candidate` | 同上（含 `POST /questions/{id}/reference-answer`） |
| `test_interview_endpoints_reject_candidate` | 同上（含 `/answers`、`/complete`、`/rollback`） |
| `test_evaluation_endpoints_reject_candidate` | 候选人对 `POST /evaluate`、`GET /evaluation/stream`、`GET /report` → 403 |
| `test_hr_passes_hr_guards` | hr 对 position/question/interview/evaluation 各取一个端点 → **非 403**（证明确实放行，而非守卫把所有角色都拒了） |
| `test_admin_passes_hr_guards` | admin 同样放行 |
| `test_hr_rejected_on_admin_only_users` | hr 对 `/users` → 403 |

> 第 5、6 条是**反向断言**：只测「候选人被拒」无法发现「守卫把 hr 也拒了」这类过度收紧。两侧都要测。

**C. `scope_owner_id` 纵深防御**

| 测试 | 断言 |
|---|---|
| `test_scope_owner_id_candidate_raises` | 直接调用 `scope_owner_id(candidate_user)` → 抛 `ForbiddenError` |
| `test_scope_owner_id_hr_returns_id` | hr → `user.id`（既有行为，回归） |
| `test_scope_owner_id_admin_returns_none` | admin → `None`（既有行为，回归） |
| `test_ensure_resource_visible_rejects_candidate` | 候选人对任意 `created_by` 调用 → 抛 `ForbiddenError` |

**D. SSE 端点**

| 测试 | 断言 |
|---|---|
| `test_stream_rejects_candidate` | candidate token 请求 `GET /interviews/{id}/evaluation/stream` → **403 且不是 `text/event-stream`**（守卫必须在建立流之前生效，不能先开流再拒） |
| `test_stream_rejects_hr_for_others_interview` | hr 请求他人面试的流 → 403（既有行为，回归） |

### 7.2 回归（**必须全跑**）

| 项 | 期望 |
|---|---|
| `pytest tests/ -q` | **461 条既有用例全部通过** |
| 特别关注 | `test_auth.py`（24）、`test_position.py`（32）、`test_question.py`（44）、`test_interview.py`（62）、`test_evaluation.py`（29）、`test_evaluation_stream.py`（34）、`test_e2e_flows.py`（8）、`test_architecture.py`（9） |

**为何预期零回归**：既有测试的请求只使用 `admin_headers` / `hr_headers` / `other_hr_headers`（`conftest.py`），**没有任何用例使用非 admin/hr 角色的 token**。因此给 HR 路由加角色守卫对既有用例不可见。

> 这是**预期**，不是**结论**——必须实际跑完并确认。若出现回归，优先怀疑某条用例用了未登录请求去测「401」而实际先撞上守卫。

### 7.3 与架构测试的关系

| 项 | 说明 |
|---|---|
| `test_architecture.py` 是否需改 | **本模块不需要**。它校验依赖方向与分层，不涉及守卫 |
| 但需注意 | [module-13](./2026-09-20-module-13-practice-plan.md) 新增 `practice` 包时，必须把 `practice` 登记进该文件的 `ALL_MODULES`、`LAYERED_MODULES`、`FORBIDDEN_DEPENDENCIES`，否则分层约束测试不会覆盖它。已记入 [module-08 §7.2](./2026-09-15-module-08-e2e-plan.md) |

### 7.4 部署说明补全（`backend/README.md`）

| 内容 | 理由 |
|---|---|
| 生产部署应设 `CANDIDATE_SELF_REGISTER=false` | 自助注册默认开启是为了可演示；生产应只允许凭邀请码建号 |
| 单机部署须 `--workers 1` | 既有约束（module-06 §5.6 的进程内运行注册表），候选人侧未引入新的多进程需求，但需在文档里保持可见 |
| 候选人端与 HR 端的登录态按端分 key（`hr.*` / `candidate.*`） | 前端实现见 module-15；README 需说明「同一浏览器可同时登录两端」 |

---

## 8. 任务分解（TDD 步骤，无代码）

> 每步 2–5 分钟。**提交信息由你指定**。
> **前置**：module-09 的 Task 9.3（`require_roles`）已完成。

### Task 16.1：自维护不变量测试（**先写测试**）

- [ ] 写 §7.1-A 两条测试：遍历 `app.routes`，用 candidate / hr token 断言 403
- [ ] 运行确认**失败**（此刻 HR 路由尚未挂守卫，会返回 2xx 或进入 service 逻辑）
- [ ] 记录失败清单（即需要挂守卫的端点全集）
- [ ] 提交

### Task 16.2：`scope_owner_id` 纵深防御

- [ ] 写 §7.1-C 四条测试
- [ ] 运行确认失败
- [ ] 在 `auth/service.py` 增加非 admin/hr 的拒绝分支
- [ ] 运行确认通过
- [ ] 提交

### Task 16.3：position / question 路由挂守卫

- [ ] 按 §3.1 规则给两个 router 的全部端点加 `require_roles("admin","hr")`
- [ ] 运行 §7.1-A / §7.1-B 的相关断言
- [ ] 提交

### Task 16.4：interview / evaluation 路由挂守卫

- [ ] 同上（**含 SSE 端点，注意 §7.1-D 的「先拒绝再建流」**）
- [ ] 运行确认通过
- [ ] 提交

### Task 16.5：`/users*` 写法统一

- [ ] `auth/router.py` 三处 `require_role("admin")` 改为 `require_roles("admin")`
- [ ] 运行 `test_auth.py` 确认零回归
- [ ] 提交

### Task 16.6：全量回归

- [ ] 运行 `pytest tests/ -q`，**461 条既有用例 + 本模块新增用例全部通过**
- [ ] 若有回归，定位并修复（§7.2 的排查方向）
- [ ] 提交

### Task 16.7：部署说明

- [ ] 按 §7.4 补 `backend/README.md`
- [ ] 提交

---

## 9. 验收标准

- [ ] **`app.routes` 中不存在任何 HR 侧路由可被 candidate token 访问**（自维护不变量测试通过，且无 2xx）
- [ ] HR 侧全部端点挂 `require_roles("admin","hr")`；`/users*` 挂 `require_roles("admin")`
- [ ] hr 与 admin 在 HR 侧**确实放行**（反向断言通过，未被过度收紧）
- [ ] `scope_owner_id(candidate)` 抛 `ForbiddenError`；admin 返回 `None`、hr 返回 `user.id`（后两者为回归）
- [ ] `ensure_resource_visible` 对候选人抛 `ForbiddenError`
- [ ] SSE 端点对候选人**在建立流之前**返回 403，响应不是 `text/event-stream`
- [ ] 未引入任何新错误码（仍为 module-00 §6.3 的八个）
- [ ] **461 条既有用例零回归**
- [ ] `backend/README.md` 补全三条部署说明
- [ ] 与 module-09 **同批次发布**（§0 执行顺序约束）

---

## 10. 风险与设计权衡

| 风险 / 权衡 | 决策 | 理由 |
|---|---|---|
| **文档编号 16 但必须先于 module-09 发布** | 在文首单列「⚠️ 执行顺序约束」章节 | 按编号顺序执行会留下真实的越权窗口。这类约束必须写在最显眼处，而不是埋在风险表里 |
| **手抄端点清单必然失效** | 用 `app.routes` 遍历的自维护不变量测试，而不是端点清单测试 | 手写清单在本模块要修的问题上重犯同样的错：新增端点时静默漏改 |
| 只测「候选人被拒」会掩盖过度收紧 | 增加 hr / admin 的**反向断言** | 守卫写错方向（例如全部拒绝）时，单向测试仍会全绿 |
| `scope_owner_id` 抛错 vs 返回 `None` | 抛 `ForbiddenError` | 返回 `None` 等于不过滤，是最坏的失败方向；默认拒绝优于默认放行 |
| 是否引入全局权限中间件 | 不引入 | 项目既定风格是依赖工厂逐端点声明（module-00 §7）；中间件会隐藏「哪个端点被什么角色保护」这一事实 |
| 守卫与 service 内校验是否重复 | 保留两层 | 守卫答「是不是这类用户」，service 答「是不是他的数据」。删掉任一层都会留下缺口 |
| 候选人侧守卫是否在本模块实现 | 不在 | 属 module-12/13；本模块只负责存量路由，避免把两个模块的职责搅在一起 |
| 既有 461 条用例能否零回归 | **预期可以**（无用例使用非 admin/hr token），但必须实测 | 预期不是结论；SSE 与 401 类用例是最可能的回归点 |
