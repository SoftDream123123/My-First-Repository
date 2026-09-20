# 候选人前端执行计划书（MVP-2 面试者端）

> **文档状态**：⚠️ **待编写** —— 编号与文件名已预留，本轮（2026-09-20）**未产出内容**。
> 本文档不是可执行的计划书，请勿据此实施。已完成的部分见文末「已确认的现状与固定契约」。

**模块**：frontend 候选人端（路由、页面、会话按端分离）
**所属工程**：`frontend/`（**同一 Vite 工程内**，不新建工程）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§2（技术栈与单机约束）、§3.1（`/candidate` 端）、§4.6（候选人可见范围）、§4.7（刷题）、§4.8（在线答题）、§4.9（反馈）、§9（会话按端分 key）

---

## 待编写的章节（沿用 module-00～16 的统一模板）

1. 模块职责与边界（不新建工程、不引入框架/UI 库/图表库；仅 PC；不做移动端响应式）
2. 文件结构（新增页面模块清单 + **需修改的既有文件清单**，见下）
3. 路由与页面设计（候选人路由表、导航、登录/注册/激活页、刷题页、我的面试、答题页、反馈页）
4. 会话与鉴权设计（**按端分 key**、`api.js` 如何选取 token、守卫如何区分两端）
5. 各页面设计（数据获取、加载/失败/空态、表单与校验、错误展示）
6. 样式设计（复用既有 class 与 design token；CSS 仍归入现有四个文件）
7. 测试设计（纯函数单测 + `mock/*.html` 手工走查）
8. 任务分解（步骤，无代码）
9. 验收标准
10. 风险与设计权衡

---

## 已确认的现状（编写时按此为准，勿凭印象）

| 位置 | 现状 | 对本模块的意义 |
|---|---|---|
| `frontend/src/session.js` | 固定键 `hr.token` / `hr.user`（第 9-10 行） | ⚠️ **必须改为按端分 key**（`hr.*` / `candidate.*`），否则单浏览器内两端互相顶号，PRD §9 的演示路径走不通 |
| `frontend/src/router.js` | 路由表为 `{ path, key, isPublic?, adminOnly? }`；`guard()` 依次判 public → 已登录 → `adminOnly`；`DEFAULT_ROUTE = '/interviews'`；hash 路由 | 需新增**候选人路由组与角色门禁**（现有只有 `adminOnly` 一种门禁，没有 `hrOnly` / 角色数组） |
| `frontend/src/main.js` | 静态 `registerPages({...})` 注册 7 个页面；`boot()` 调 `auth.refreshUser()` 后 `start(app)`；统一 401 处理器跳 `#/login` | 新增页面须在此注册；`boot` 与 401 跳转需**按当前端**决定行为 |
| `frontend/src/components/shell.js` | `createShell()` 构建 HR 外壳（侧栏 brand 写死「HR 工作台」）；`NAV` 为 HR 导航且支持 `adminOnly` 过滤 | 候选人端需要**自己的外壳与导航**（brand、导航项、顶栏文案均不同） |
| `frontend/src/api.js` | `BASE = '/api'`（相对路径）；token 经 `session.getToken()` 注入；204 → `null`；401 集中处理 | token 来源须改为「按当前端」，且**不能破坏 HR 端既有行为** |
| `frontend/src/pages/*.js` | 页面契约：`export async function render(container, params)`，可选 `destroy()`；模态用 `openModal` / `confirmModal`；表单错误用 `fieldErrors` 且**键名必须等于后端 `detail.fields[].field`** | 候选人页面须沿用同一契约与写法 |
| `frontend/src/dom.js` | `el` / `append` / `clear` / `mount` / `frag` / `when`；`text:` 是**唯一**文本路径（全仓 `innerHTML` 出现 0 次） | 新页面只能用这套原语，不得引入 HTML 字符串 |
| `frontend/index.html` | 四个 CSS 以 `<link>` 级联：`tokens → base → components → pages` | 新样式并入既有文件，**不新增 CSS 文件** |
| `frontend/vite.config.js` | 端口 5173；`/api` 代理到 `localhost:8000`；无多页/多入口配置；Vitest 配置内嵌于此，只测**纯函数**（无 jsdom） | 候选人端是**同一 SPA 的另一组路由**，不是第二个入口 |
| `frontend/standalone.html` | 单文件原型快照，**已冻结、不可再生成**（生成脚本已删除），与 `src/` 不同步 | **不要编辑** |
| `frontend/src/components/radar.js` | `isPass` 阈值为 **6.5**；`shell.js` 的 `scoreClass` 亦为 6.5 | 候选人端**不展示雷达图与逐题分**（PRD §4.9）；若将来放开，阈值仍须与后端 `PASS_THRESHOLD` 一致 |

---

## 固定契约（编写本文件时**必须遵守，不得另立**）

| 契约 | 出处 |
|---|---|
| 候选人端与 HR 端是**同一 Vite 工程内的两组路由**；不新建工程、不换框架、不加构建产物 | PRD §2、§3.1 |
| 仅 PC 端，不做移动端响应式 | PRD §2 |
| 会话**按端分 key**（`hr.*` / `candidate.*`），保证单浏览器可同时保持两端登录 | PRD §9；[module-08 §3.7](./2026-09-15-module-08-e2e-plan.md) |
| 自助注册响应**不含 token**，前端注册成功后**自动调 `/auth/login`** | [module-09 §5.1](./2026-09-20-module-09-auth-plan.md) |
| 候选人页面路由与端点：注册/登录、邀请激活、刷题、我的面试与作答、反馈 | [module-12（待编写）](./2026-09-20-module-12-interview-invitation-plan.md)、[module-13（待编写）](./2026-09-20-module-13-practice-plan.md)、[module-14（待编写）](./2026-09-20-module-14-evaluation-feedback-plan.md) |
| 刷题取题响应**不含参考答案与解析**；提交后才展示 | [module-10 §4.2](./2026-09-20-module-10-question-plan.md) |
| 反馈页**只**展示结论/优点/待改进；不得渲染总分、逐题分、雷达图 | PRD §4.9 |
| 候选人端**不得**出现 HR 导航项（岗位/题库/用户管理）；HR 端不得出现候选人导航项 | PRD §4.6 |
| 后端错误文案**原样展示**（`error.message`），前端不重写 | 既有约定（`api.js`） |
| 后端错误码与字段名以 [API 接口文档](../../apis/API接口文档.md) 为准，不凭印象 | 既有约定 |
| E2E 走查清单（流程④⑤ + 越权 4 项）中有 3 项依赖本模块 | [module-08 §4.5](./2026-09-15-module-08-e2e-plan.md) |

**必须同步更新的既有文档**：`docs/apis/API接口文档.md`（新增候选人端与 practice 端共 13 个端点）、`frontend/README.md`（两端入口与演示步骤）。
