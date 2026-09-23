# 前端 手机验证码登录 执行计划书（MVP-5 §4.16）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：前端 **MVP-5 增量**（两端登录页接入手机验证码 + 激活页隐藏密码字段 + admin 绑定手机号）
**所属工程**：`frontend/src/`（原生 HTML/CSS/JS + Vite）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.16（手机验证码登录）、§4.1（`accept` 免密分支的前端配合）、§8（两端点在表内）、§11（MVP-5 前端条目）
**前置依赖**：[module-31 后端](./2026-09-23-module-31-auth-phone-otp-plan.md)（**必须先完成**：两个端点与 `accept` 的 `password` 放宽在它里面）、[module-22 候选人前端](./2026-09-21-module-22-candidate-frontend-plan.md)、[module-23 HR 前端](./2026-09-21-module-23-hr-frontend-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- **无 UI 框架、无状态管理库、无新增依赖**（§2）
- **登录端点三角色共用**，页面按返回的 `user.role` 分流 —— 手机登录**同样如此**，不得默认来者都是 HR（§4.16）
- **两端登录态按端分 key**（`hr.*` / `candidate.*`），单浏览器可同时登录（§9）
- ⚠️ **前端测试只能测纯函数**（无 DOM 环境，module-07 §8.1 的既有决策）。**凡需要被测的判定，都必须先抽成导出函数** —— 留在 `render()` 里就等于永远不会被测到
- ⚠️ **不得把后端文案重写一遍**：业务错误（401 / 409 / 429）原样展示后端 `message`（既有约定）
- **常量前端无法 import 后端配置**，只能各写一份 —— 因此**必须用「常量守门」测试钉住**（既有约定，见 `resume-form.test.js` 末尾那条）
- 仍是单机 PC 端，仅 PC 布局（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| 共用组件 | `phone-login.js` —— 手机号 + 验证码两栏、60 秒重发倒计时、`dev_code` 提示 | §4.16 |
| HR 登录页 | 密码登录 / 手机号登录**双模式**；两种模式共用同一段角色分流 | §4.16 |
| 候选人登录页 | 在既有「登录 / 注册」之外加第三个模式「手机号登录」 | §4.16 |
| 激活页 | 已登录时**隐藏密码字段**（配合 §4.1 免密分支） | §4.1 |
| 用户管理页 | admin 给账号**绑定 / 解绑**手机号 | §4.1、§4.16 |
| `api.js` | `isCredentialCheck` 登记 `/auth/phone/login`（**漏了会清掉登录态**，见 §6.1） | §7 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **候选人端加「手机号注册」模式** | 手机号登录**本身就是**注册（首次即建号，§4.16）。再来一个「注册」模式是两条入口通向同一件事，只会让用户犹豫 |
| **HR 登录页加「手机号注册」** | HR 账号不能自助注册（§4.1）。未绑定的手机号在 HR 页登录会**自动建候选人号**并被分流到候选人端 |
| **用户自助绑定 / 换绑手机号** | PRD §1.3 非目标。只能 admin 在用户管理页设置 |
| **记住手机号 / 「上次用的号码」** | 属「候选人资料」增强，MVP 不做；且会把手机号写进 localStorage（PII 落盘） |
| **前端校验验证码格式之外的任何事** | 格式（6 位数字）拦一道是体验；其余（是否有效、是否过期、错误次数）**只有后端知道**，前端不得猜 |
| **真实短信 / 图形验证码 / 滑块** | PRD §1.3 非目标 |
| **改 `candidate-register` 相关** | 自助注册不受本批次影响 |

### 1.3 依赖方向

```
pages/login.js ────────────┐
pages/candidate-login.js ──┼─→ components/phone-login.js ─→ api.js（/auth/phone/code、/auth/phone/login）
pages/users.js ────────────┘                                    │
                                                                 └─→ session.js（token 随请求带上）
pages/candidate-activate.js ─→ api.js（accept；已登录时 token 自动随请求发出，服务端走免密分支）
```

> **`phone-login.js` 是组件不是页面**：它不做 `mount`、不决定去哪一端，只负责
> 「拿到手机号与验证码 → 调两个端点 → 把 `{token, user}` 交给调用方」。
> **分流留在两个登录页**，因为「去哪一端」是两个页面各自的知识：
> HR 页收到 candidate 角色要写成 `candidate.*` 并跳候选人端，候选人页收到非 candidate 要**拒绝**
> 而不是跳走（既有行为，见 §5.3）。

---

## 2. 文件结构

| 文件 | 动作 | 内容 |
|---|---|---|
| `frontend/src/components/phone-login.js` | **新建** | 组件 + 5 个导出纯函数 + 2 个导出常量 |
| `frontend/src/api.js` | 改 | `isCredentialCheck` **导出**并加 `/auth/phone/login` |
| `frontend/src/pages/login.js` | 改 | 双模式 + 抽出共用的角色分流 |
| `frontend/src/pages/candidate-login.js` | 改 | 第三个模式，`hidden` 切换两组 field |
| `frontend/src/pages/candidate-activate.js` | 改 | 已登录时隐藏密码字段、文案改口径 |
| `frontend/src/pages/users.js` | 改 | 手机号列 + 绑定 / 解绑弹窗 |
| `frontend/src/styles/components.css` | 改 | 手机号输入与倒计时按钮样式（复用既有 `.seg` / `.field` / `.btn`） |
| `frontend/src/__tests__/phone-login.test.js` | **新建** | 纯函数单测 + 常量守门 |
| `frontend/src/__tests__/api-interceptor.test.js` | **新建** | `isCredentialCheck` 单测（§5.1：把「哪些端点是凭据类」变成会红的清单） |

> **`components/` 下放组件是既有分层**（`form.js` / `modal.js` / `toast.js` / `radar.js` /
> `resume-review.js` 都在这）。**但注意 `components/` 里此前只有纯展示组件**（`resume-review.js`
> 带 API 调用，可作先例）—— 本组件带网络请求，与 `resume-review.js` 同类，不越界。

---

## 3. 接口契约

### 3.1 组件对外签名（`components/phone-login.js`）

```js
/**
 * 构建手机验证码登录表单。
 * @param {{ onSubmit: (result: {token: string, user: object}) => void|Promise<void> }} options
 *   onSubmit 由**调用方**负责分流与跳转（组件不知道有哪几端）。
 * @returns {HTMLElement} <form>
 */
export function buildPhoneLoginForm({ onSubmit }) {}
```

**组件内部行为**

| 步骤 | 动作 |
|---|---|
| 1 | 「获取验证码」按钮 → 校验手机号格式 → `api.post('/auth/phone/code', { phone })` |
| 2 | 成功 → 按钮进入 **60 秒倒计时**；若响应带 `dev_code`，**提示并自动填入验证码框**（见 3.3） |
| 3 | 429 → 按 `detail.retry_after_seconds` 进入倒计时（**不是用户的错，不该只弹一句 toast 就完了**） |
| 4 | 「登录」→ 校验两个字段 → `api.post('/auth/phone/login', { phone, code })` |
| 5 | 成功 → `onSubmit(result)`；失败 → 401 落到验证码字段的错误位，文案**原样用后端那句** |

### 3.2 导出纯函数与常量（**这就是可测面**）

```js
export const PHONE_CODE_LENGTH = 6;        // 与后端 6 位一致
export const PHONE_CODE_RESEND_SECONDS = 60; // 与后端 PHONE_CODE_RESEND_INTERVAL_SECONDS 默认值一致

/** 归一化：去空格 / 连字符 / 括号，去 +86 与 86 前缀。 */
export function normalizePhone(raw) {}

/** 是否 11 位大陆手机号（^1[3-9]\d{9}$）。 */
export function isValidPhone(raw) {}

/** 表单校验 → { phone?: string, code?: string }（空对象表示通过）。 */
export function validatePhoneLogin({ phone, code }) {}

/** 重发按钮的显示态 → { disabled: boolean, text: string }。 */
export function resendLabel(remainingSeconds) {}

/** 从 429 错误里取重试秒数；取不到则回落到 RESEND_SECONDS。 */
export function retryAfterSeconds(error) {}
```

> ⚠️ **`normalizePhone` 必须与后端 `auth/schemas.py::normalize_phone` 行为一致**：
> 前端先归一化再发请求，后端还会再归一化一次（纵深，不是重复）。
> 两边不一致的症状是「前端说格式对、后端说格式错」—— 一条谁也想不到去查前端的错误。
> **测试里用同一组样例**（`" 138 0013 8000 "` / `"+8613800138000"` / `"8613800138000"` /
> `"13800138000"` 四种写法都必须归一到 `"13800138000"`）。
>
> ⚠️ **`PHONE_CODE_RESEND_SECONDS = 60` 必须加「常量守门」测试**：前端 import 不到后端配置，
> 60 只能各写一份。用一条断言把值钉住，让改动成为一个**需要显式修改测试的动作**，
> 而不是静默漂移（沿用 `resume-form.test.js` 末尾那条既有手法）。
> 若它小于后端值，用户会点了重发却吃 429 —— 一个纯前端配错导致的假故障。

### 3.3 `dev_code` 的展示（演示路径，不是隐藏功能）

`SMS_PROVIDER=mock` 是默认值，此时后端在发码响应里回显 `dev_code`。前端**必须把它用起来**，
否则演示手机验证码就得去翻后端日志：

| 条件 | 行为 |
|---|---|
| 响应带 `dev_code`（非空） | ① 自动填入验证码框；② 在表单下方显示一条 `note-box`：`演示环境：验证码 483920` |
| `dev_code` 为 `null` | 什么都不显示，走正常的「短信已发送」提示 |

> **不把它做成可关闭的功能开关**：`dev_code` 出现与否**完全由后端 `SMS_PROVIDER` 决定**，
> 前端只是把它显示出来。生产部署换掉 Provider 后这个分支自然永不进入（PRD §6）。
> 前端**不知道也不判断**当前是不是 mock —— 判据只有「字段是否非空」。

### 3.4 `users.js` 的绑定 / 解绑

| 项 | 契约 |
|---|---|
| 列表列 | 在「角色」「状态」之间插入「手机号」列；未绑定显示 `—`（**不用空白**，空白看起来像加载失败） |
| 操作 | 行内新增「设置手机号」按钮 → `openModal` 内一个手机号输入框 |
| 提交 | `mutate(user.id, { phone: 输入值或 null }, '手机号已更新')`（复用既有 `mutate`） |
| 空输入 | 提交时传 `phone: null` → **解绑**（需在弹窗里明确提示「留空即解绑」，否则是一步破坏性操作却无预告） |
| 409 | 原样展示「该手机号已被占用」（不区分占用者角色，前端不猜） |
| 本机号码 / 当前用户 | **不特殊处理**：admin 也可以给自己绑手机号（§4.16 允许），后端没有禁止 |

---

## 4. 交互流程

### 4.1 HR 登录页（`pages/login.js`）

```
登录卡片顶部加一个 .seg 切换：[密码登录] [手机号登录]

密码模式  → 既有表单（用户名 + 密码）          ← 一行不改
手机号模式 → buildPhoneLoginForm({ onSubmit })  ← 组件整体替换两个 field

两种模式共用同一个分流函数：
    if (result.user?.role === 'candidate') {
        auth.saveTokenOn(result.token, result.user, 'candidate');
        navigate(defaultRoute('candidate'));
    } else {
        auth.saveToken(result.token, result.user);
        navigate(defaultRoute('hr', auth.isAdmin()));
    }
```

> ⚠️ **手机号模式同样必须按 `role` 分流**（§4.16）：HR 页上用一个**未绑定过的手机号**登录，
> 后端会**自动建一个候选人账号**并原样返回 `role: "candidate"`。此时若不分流，就会出现
> 「在 HR 页用手机号登录 → 进了 HR 工作台 → 里面空空如也、什么都看不到」——
> 症状（进去了但是空的）与原因（那是个候选人账号）离得很远。
>
> **把分流抽成一个本页的局部函数，两个模式共用**：写两份一定会分叉，而分叉的那一份
> 恰好是新加的手机号模式 —— 也就是本条要防的那个 bug 本身。

### 4.2 候选人登录页（`pages/candidate-login.js`）

`switcher` 从 `[['login','登录'], ['register','注册']]` 扩到三个：
`[['login','登录'], ['register','注册'], ['phone','手机号登录']]`。

`paint()` 里按 `mode` 切换**两组 field 的可见性**：

| mode | 用户名 field | 密码 field | 手机号 + 验证码 field | note 区 |
|---|---|---|---|---|
| `login` | 显示 | 显示 | 隐藏 | 「拿到邀请码了？去激活」 |
| `register` | 显示 | 显示 | 隐藏 | 同上（`registerClosed` 时是「凭邀请码进入」那一版） |
| `phone` | 隐藏 | 隐藏 | 显示 | 同上 |

> ⚠️ **必须用 `hidden` 属性切换，不能重建 input 元素**：既有代码特意说明
> 「这两个字段的内容在两种模式之间是共用的，**不重画**（重画会把已输入的内容清掉）」
> （module-22 的既有结论）。把 `render()` 改成按模式重建，会顺手破坏这条已修过的行为 ——
> 用户从「登录」切到「注册」再切回来，用户名被清空。
>
> 手机号 / 验证码两个 field **在页面构建时一次性创建**（与用户名/密码并列），
> 只是初始 `hidden`。这样也避免每次切模式都新建 DOM。
>
> **`registerClosed` 与 `phone` 模式正交**：自助注册关闭不影响手机号登录（它建号走的是
> 另一条路径，不受 `CANDIDATE_SELF_REGISTER` 控制 —— 见 §4.16「自动建号」）。
> `paint()` 里 `registerClosed` 的分支只应作用于 `register` 模式的展示，
> **不得让 `phone` 模式也显示「自助注册已关闭」**。

### 4.3 候选人激活页（`pages/candidate-activate.js`）

已登录时（`auth.isLoggedIn() && auth.isCandidate()`）**隐藏密码 field**，
并把它从必填校验里去掉。

```
已登录  → 只填邀请码 → api.post(/candidate/invitations/{code}/accept, { username: 当前账号 })
          ↑ token 由 api.js 自动带上 → 后端走 §4.1 免密分支
未登录  → 邀请码 + 用户名 + 密码（既有行为，一行不改）
```

> **只需在前端做「不发 password」这一件事**，免密由后端判定。前端**不得**自己判断
> 「我是手机号账号所以不用密码」—— 那是后端的知识，前端猜错会退化成「必填却不填」。
>
> **字段说明文案要跟着改**：既有那句「账号已存在时用它核对身份；新建账号时它就是新密码」
> 在已登录时是**错的**（已登录时密码根本不参与）。改为「已登录，无需再输入密码」。

### 4.4 倒计时的生命周期

| 事件 | 处理 |
|---|---|
| 发码成功 / 429 | 启动倒计时（60 或 `retry_after_seconds`） |
| 倒计时归零 | `clearInterval` + 按钮恢复可点（`resendLabel` 返回 `disabled: false`） |
| 模式切换 / 重新 `paint()` | 清掉旧 interval，`remaining` 归零 |
| 组件被替换（路由跳转） | **不额外处理** —— 泄漏的 interval 最多再跑 60 次即自行结束 |

> 最后一条是有意接受的：为「替换时清理」引入 `MutationObserver` 或组件销毁钩子，
> 成本远高于收益（本工程无组件生命周期概念）。**但计时器必须在归零时自行 `clearInterval`**
> —— 否则页面停留一小时后会攒下几十个永不停歇的 interval。

---

## 5. 错误处理

### 5.1 `api.js` 的 `isCredentialCheck` 要加 `/auth/phone/login`

```js
export function isCredentialCheck(path) {          // ← 顺带导出，见下
  return path === '/auth/login'
    || path === '/auth/phone/login'                // ← 本批次新增
    || /^\/candidate\/invitations\/[^/]+\/accept$/.test(path);
}
```

> ⚠️ **如实说明这条的作用（执行时核对，2026-09-23）**：它**不是**在修一个可复现的
> bug。核对过两条防线：
> - `router.decide` 把已登录用户从**同端**登录页重定向走（`router.js:164`），
>   而 `loggedIn` 取的是该路由所属那一端的状态；
> - `session.clear()` 是**按端**作用域的（`session.js:31`）—— 即便触发，登录页上
>   那一端本来就没有 token。
>
> 所以「输错验证码被登出」在今天的路由表下**不可达**。
>
> **那为什么仍然要加**：同一个类别的端点已经在别处**必需**过这一条 ——
> `/candidate/invitations/{code}/accept` 挂在 `/candidate/activate` 上，而那条路由是
> `open: true`（登录与否都可达、不重定向），因此「已登录 + 收到 401」对它是可达的。
> **凭据端点的分类与路由是否 open 是两件独立的事**，让两者必须彼此吻合才正确是
> 一种不必要的耦合：将来给某个同端路由加 `open: true`、或去掉守卫的重定向，
> 漏掉这一条就会变成真的 bug，而症状（莫名被登出）与原因（这个字符串比对）离得极远。
>
> - 顺带把 `isCredentialCheck` **导出**并加单测（module-32 §6）：它是纯函数，
>   而它把「哪个端点属于凭据类」这件事变成了一份**会红的清单** ——
>   新增凭据端点却忘了登记时看得出来。
> - `/auth/phone/code` **不需要登记**：它只返回 200 / 400 / 429，**永不返回 401**。
> - **该函数的 docstring 也要同步**（现写的是「这两个端点」）。

### 5.2 错误 → 界面

| 状态码 | 界面行为 | 出处 |
|---|---|---|
| **400** | 落到手机号字段的错误位（前端已先校验格式，正常走不到） | §7 |
| **429** | 「获取验证码」按钮进入 `retry_after_seconds` 倒计时；**不弹 toast** —— 倒计时本身就是提示，再弹一次是同一条信息的两次播报 | §7 |
| **401**（验证码错） | 落到验证码字段的错误位，文案原样用后端那句（`验证码错误或已失效`）。**不区分四种原因** —— 前端也无从区分，后端刻意统一 | §4.16 |
| **401**（账号禁用） | toast，文案原样用后端那句 | §4.1 |
| **502** | toast「短信服务发送失败，请稍后重试」**（原样用后端 message）**，按钮**立即恢复可点**（不是用户的问题，不该罚他等 60 秒） | §7 |
| **409**（`users.js` 绑号） | 原样展示「该手机号已被占用」 | §7 |

> ⚠️ **502 时按钮必须立即恢复可点**：若沿用「发码后必进倒计时」的逻辑，一次短信通道
> 故障会把用户锁在 60 秒之外，而他重试的愿望与能力都被前端拿走了。

---

## 6. 测试清单

`frontend/src/__tests__/phone-login.test.js`（**纯函数，无 DOM**）

| # | 用例 | 断言 |
|---|---|---|
| 1 | `normalizePhone` 四种写法 | `" 138 0013 8000 "` / `"+8613800138000"` / `"8613800138000"` / `"13800138000"` **全部**归一到 `"13800138000"` |
| 2 | `normalizePhone` 带连字符 / 括号 | `"138-0013-8000"` / `"(138)00138000"` → `"13800138000"` |
| 3 | `isValidPhone` 正例 | `"13800138000"` / `"19912345678"` → true |
| 4 | `isValidPhone` 反例 | `""` / `"1380013800"`（10 位）/ `"138001380000"`（12 位）/ `"12800138000"`（第 2 位是 2）/ `"aaaaa"` / `"13800138000x"` → false |
| 5 | `validatePhoneLogin` 两者皆空 | 返回**两个**字段的错误（不是只报第一个） |
| 6 | `validatePhoneLogin` 手机号合法、验证码非 6 位数字 | 仅 `code` 有错误 |
| 7 | `validatePhoneLogin` 全合法 | 返回 `{}` |
| 8 | `resendLabel(60)` | `{ disabled: true, text: '60 秒后重发' }` |
| 9 | `resendLabel(0)` | `{ disabled: false, text: '获取验证码' }` |
| 10 | `resendLabel(-5)`（防御） | 同 `0`，**不得**显示负数 |
| 11 | `retryAfterSeconds` 正常 | `{ detail: { retry_after_seconds: 42 } }` → 42 |
| 12 | `retryAfterSeconds` 缺失 / 非法 | `detail` 为 null / 该键缺失 / 值为 `"abc"` / 值为 `-1` → **一律回落到 60**（不得返回 `NaN`，否则按钮文案变成「NaN 秒后重发」） |
| 13 | **常量守门** | `PHONE_CODE_RESEND_SECONDS === 60` 且 `PHONE_CODE_LENGTH === 6`（与后端默认值一致，前端 import 不到，只能显式钉住） |

> **用例 5、6、10、12 是刻意的边界**：这四条都是「安静错」的类型 —— 写错不会报错，
> 只会让界面显示一个荒唐的值（负数秒、`NaN` 秒、只报一个错误）。而它们又都在
> 纯函数里，测起来零成本。

**手工冒烟（唯一的人工环节，用户已确认轻量档）**

| # | 步骤 | 期望 |
|---|---|---|
| 1 | 起后端 + Vite，打开 HR 登录页 | 有「密码登录 / 手机号登录」切换 |
| 2 | 切到手机号模式，填 `13800138000`，点获取验证码 | 按钮进入 60 秒倒计时；表单下方出现「演示环境：验证码 xxxxxx」且**已自动填入** |
| 3 | 点登录 | 进入**候选人端**（未绑定过的号自动建 candidate 号），候选人端显示已登录 |
| 4 | 再发一次码、故意填错 | 验证码字段显示「验证码错误或已失效」（错误落在**用户刚填错的那个框**下方）；页面**不跳转、不清登录态**（§5.1：这一条今天不可达，已由 `api-interceptor.test.js` 的纯函数用例兜住，冒烟只确认现象） |
| 5 | admin 在用户管理页给某 hr 账号绑手机号，再用该号在 HR 页登录 | 直接进入 **HR 工作台**，不是候选人端 |
| 6 | 连续点「获取验证码」 | 第二次起吃 429，按钮按 `retry_after_seconds` 倒计时 |
| 7 | 已登录状态下打开 `/candidate/activate` | **密码字段不存在**，只填邀请码即激活成功 |
| 8 | 原「用户名 + 密码」登录（HR 与候选人两端） | **行为与改动前一模一样**（回归） |

---

## 7. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | 纯函数 13 条用例全绿 | `npm test` |
| 2 | ⚠️ **手机号登录按 `role` 分流** | 冒烟 3、5 |
| 3 | 验证码输错的 401 落到验证码框（不是 toast）、且 `isCredentialCheck` 已含该路径 | 冒烟 4 + `api-interceptor.test.js`（**已由单测覆盖，不依赖冒烟**） |
| 4 | 429 进入倒计时、502 立即恢复可点 | 冒烟 6 + 代码走查 |
| 5 | `dev_code` 提示并自动填入 | 冒烟 2 |
| 6 | 已登录时激活页无密码字段且能激活 | 冒烟 7 |
| 7 | 既有密码登录零回归 | 冒烟 8 |
| 8 | `npm run build` 通过 | `npm run build` |
| 9 | 无新增依赖 | `git status` 看 `package.json` / `package-lock.json` 未改 |
| 10 | 两端登录态互不干扰（`hr.*` / `candidate.*`） | 冒烟 3 之后确认 HR 端仍可用 |

### 本批次**不跑**的验证（轻量档，用户已确认）

- ❌ Playwright / `webapp-testing` 自动化交互（纯函数单测 + 手工冒烟已覆盖本批次全部新增判定）
- ❌ 全量 e2e、多 agent 走查、独立测试报告文档

**风险落在哪**：`candidate-activate.js` 与 `candidate-login.js` 都是**既有已发布的页面**，
改动它们有可能碰到已修过的行为（尤其是「切模式不重画输入框」那条）。
**冒烟第 8 条（既有密码登录回归）与第 7 条是本批次风险最高的两处，必须手工走一遍。**

---

## 附：实施顺序

```
module-31 完成（两个端点可用、accept 的 password 已放宽）
  ├─ 1. api.js：isCredentialCheck 加 /auth/phone/login      ← 最先改，最小且影响面最大
  ├─ 2. components/phone-login.js：纯函数 + 组件
  ├─ 3. __tests__/phone-login.test.js                          ← 与第 2 步交替，先钉住纯函数
  ├─ 4. pages/login.js：双模式 + 抽出共用分流函数
  ├─ 5. pages/candidate-login.js：第三个模式（hidden 切换，不重建）
  ├─ 6. pages/candidate-activate.js：已登录隐藏密码 + 改文案
  ├─ 7. pages/users.js：手机号列 + 绑定/解绑弹窗
  ├─ 8. styles/components.css：必要样式（优先复用既有 class）
  └─ 9. 手工冒烟 8 条
```

**第 1 步必须是第一步**：它是一个 3 行的改动，但漏了它，冒烟第 4 条会失败，
而症状是「登录态莫名被清」—— 排查方向会先跑到 session/token 上，离真正的原因（拦截器判定）很远。
