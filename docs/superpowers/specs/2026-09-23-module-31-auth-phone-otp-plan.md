# auth 手机验证码登录 执行计划书（MVP-5 §4.16）

> **文档性质**：设计文档，不含实现代码。文中接口以**签名与字段表**形式给出契约，不提供函数体。
> **文档类型**：模块级执行计划书（Module Execution Plan）

**模块**：auth **MVP-5 增量**（`user.phone` 列 + 验证码表 + `sms` 包 + 两个公开端点 + `accept` 免密分支）
**所属包**：`backend/app/auth/`（主）、`backend/app/sms/`（新包）、`backend/app/core/`（配置 / 异常 / 依赖）
**上游 PRD**：[2026-09-15-ai-interview-assistant-mvp-design.md](./2026-09-15-ai-interview-assistant-mvp-design.md)
**对应 PRD 章节**：§4.16（手机验证码登录）、§4.1（`accept` 免密分支）、§5.2（`phone` 列与验证码表）、§5.3 ⑨、§6（SMS Provider 契约）、§7（MVP-5 错误条目）、§8（两端点入表）、§9（安全边界）、§11（MVP-5）
**前置依赖**：[module-09 auth](./2026-09-20-module-09-auth-plan.md)、[module-12 作答邀请](./2026-09-20-module-12-interview-invitation-plan.md)（`accept` 端点在本模块被加一条分支）
**本模块被谁依赖**：[module-32 前端](./2026-09-23-module-32-frontend-phone-login-plan.md)

---

## Global Constraints（全局约束，摘自 PRD）

- ⚠️ **自动建号的角色恒为 `candidate`，不可配置**：手机号路径不得产出 hr / admin 账号（§4.16、§9）
- ⚠️ **`dev_code` 只在 `SMS_PROVIDER=mock` 时下发**；生产部署必须换真实 Provider（§6、§9）
- **验证码不落明文**：存 `sha256(code_salt + code)`（§4.16）
- **失败文案统一**：验证码不存在 / 过期 / 已消费 / 不匹配 → 同一句 401，**四类不得有任何可区分差异**（§4.16、§7）
- **发码响应不区分手机号是否已注册**（§4.16）
- **限流查库判定，不用进程内计数**（§4.16、§9）—— 与 practice 的手法**刻意不同**
- **手机号只存 11 位纯数字，不带国家码**（§4.16）
- **`accept` 免密分支的判据必须同时满足「带 token」与「token 指向目标账号」**（§4.1）
- 分层单向 `router → service → repository`；**router 不得直接 import repository**，**service 不得直接执行 SQL**（`test_architecture.py`）
- **`sms` 必须不依赖任何业务模块**（与 `ai` 同规，§3.3）
- **不新增任何第三方依赖**（§2）
- 仍是单机 PC 端，技术栈不变（§2）

---

## 1. 模块职责与边界

### 1.1 职责

| 子职责 | 内容 | PRD |
|---|---|---|
| `sms` 包 | Provider 抽象 + Mock 实现 + 工厂 + 启动期校验 | §3.3、§6 |
| 发码端点 | `POST /auth/phone/code` —— 三层限流校验 → 生成码 → 落库 → 交 Provider 发送 | §4.16 |
| 登录端点 | `POST /auth/phone/login` —— 取码比对 → 消费 → 取号或建号 → 签发 JWT | §4.16 |
| 自动建号 | 未绑定的手机号 → 建 `candidate` 账号（`username = "phone_" + phone`，随机不可知密码） | §4.16、§5.2 |
| admin 绑定 | `PATCH /users/{id}` 支持设置 / 解绑 `phone` | §4.1、§4.16 |
| `accept` 免密 | 持本人有效 JWT 时跳过密码比对 | §4.1 |
| 数据库变更 | `user.phone` 列 + `phone_verification_code` 表（模型 + `script.sql` + 增量 DDL） | §5.2 |

### 1.2 边界（明确不做）

| 不做 | 理由 |
|---|---|
| **真实短信 Provider** | PRD §1.3 非目标。只留接口位置，不实现运营商对接 |
| **用户自助绑定 / 换绑手机号** | PRD §1.3 非目标。HR / admin 的手机号只能由 admin 设置 |
| **国际手机号** | PRD §1.3 非目标。只支持大陆 11 位 |
| **把手机号回填到 `interview.candidate_contact`** | 那是 HR 手工填的联系方式（§4.4），与账号的 `phone` 是两个不同事实。自动回填会让「HR 填的联系方式」被账号绑定悄悄改写 |
| **补写 alembic 迁移** | PRD §11（MVP-5）明确不写。迁移链自 MVP-2 起已不完整，补一条会掩盖这个事实 |
| **回溯把 practice 的限流改成 429** | 见 §7「与 practice 的 409 不一致」。既有契约已固化，改它超出本批次范围 |
| **清理过期验证码的后台任务** | PRD §5.2：过期只在读取时派生判定，项目不引入调度器 |
| **前端** | 属 module-32 |

### 1.3 依赖方向（只新增一条边：`auth → sms`）

```
auth.router ─→ auth.service ─→ auth.repository ─→ auth 表（user / phone_verification_code）
                    │
                    └─→ sms.factory.get_provider() → sms.base.SmsProvider → MockSmsProvider
                        （发送验证码，不感知业务语义）

core.deps.get_optional_user ──(函数体内延迟导入)──→ auth.service
interview.candidate_router ─→ interview.service ─→ auth.service.create_candidate_account(actor=…)
```

> **`auth → sms` 是本批次唯一新增的依赖边**，方向为「业务 → 基础设施」，与既有的
> `interview → ai` 同向。`sms` 不反向依赖任何业务模块，也**不依赖 `auth`** —— 它只负责
> 「把一个字符串发到某个手机号」，验证码的生成 / 落库 / 比对 / 作废全在 `auth`（PRD §6）。
>
> **`core.deps.get_optional_user` 用函数体内延迟导入 `auth.service`**：与既有
> `get_current_user` 同一手法，保持 `core` 不顶层依赖业务模块（`test_architecture.py`
> 的 `test_core_has_no_top_level_business_import` 会拦）。

---

## 2. 数据库变更（本批次唯一改库结构的地方）

### 2.1 增量 DDL

```sql
-- ---- MVP-5：手机验证码登录（PRD §4.16）--------------------------------------

ALTER TABLE `user`
  ADD COLUMN `phone` VARCHAR(20) NULL
      COMMENT '11 位大陆手机号，纯数字不带国家码；NULL = 未绑定' AFTER `password_hash`,
  ADD UNIQUE KEY `ix_user_phone` (`phone`);

CREATE TABLE `phone_verification_code` (
  `id`          BIGINT      NOT NULL AUTO_INCREMENT,
  `phone`       VARCHAR(20) NOT NULL COMMENT '11 位大陆手机号，纯数字不带国家码',
  `code_hash`   VARCHAR(64) NOT NULL COMMENT 'sha256(code_salt + code)，绝不存明文',
  `code_salt`   VARCHAR(32) NOT NULL COMMENT '每行独立随机盐',
  `expires_at`  DATETIME    NOT NULL,
  `consumed_at` DATETIME    NULL     COMMENT '非空 = 已被成功使用，不可再用',
  `attempts`    INT         NOT NULL DEFAULT 0 COMMENT '校验失败次数，达上限即作废',
  `request_ip`  VARCHAR(45) NULL     COMMENT '发起请求的 IP（IPv6 最长 45 字符），供 IP 维度限流',
  `created_at`  DATETIME    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_phone_verification_code_phone` (`phone`),
  KEY `ix_phone_verification_code_created_at` (`created_at`),
  KEY `ix_phone_verification_code_request_ip` (`request_ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> **`UNIQUE KEY` + 可空是本设计的支点**：MySQL 的唯一索引**允许多个 NULL**，因此
> 「`phone` 可空且唯一」正好表达「有手机号的不许重复，没手机号的不算重复」——
> 不需要任何额外约束或哨兵值。
>
> **三列都建索引，因为三列都是查询条件**：`phone`（取该号最新有效码）、
> `created_at`（限流窗口统计）、`request_ip`（IP 限流）。这张表除此之外**没有业务查询**。

### 2.2 落地方式：改模型 + 同步 `script.sql` + 增量 DDL，**不写 alembic 迁移**

| 步骤 | 动作 |
|---|---|
| 1 | 改 `app/auth/models.py`：`User.phone` + 新模型 `PhoneVerificationCode` |
| 2 | 同步 `backend/script.sql`：`user` 表加列与唯一键，末尾追加新表（含上面的注释） |
| 3 | 对 **dev 库**执行 §2.1 的 DDL |
| 4 | 与 `information_schema` **实测比对**（列、类型、可空、索引逐项核对），结果记入验收 |

> ⚠️ **为什么不写迁移**（PRD §11 MVP-5 已记，此处复述执行侧理由）：
> 2026-09-21 统一收口后，**`backend/script.sql` 才是 schema 的事实来源**
> （见 [DDL 统一收口清单](../../tests/2026-09-21-DDL统一收口清单.md)）。而 alembic 链自 MVP-2 起
> 就**已不完整** —— 6 张表与十几个列都不在链上，`alembic upgrade head` 得不到一个可用的库。
> 此时补一条迁移，只会让「迁移链是完整的」这个错觉更难被发现。**留着一个明确不完整的链，
> 比留下一个看起来完整、实际缺表的链更安全。**
>
> **测试库不受影响**：`conftest.py` 的 `_prepare_database` 用
> `Base.metadata.drop_all` + `create_all` 建库，`_truncate_all` 用
> `Base.metadata.sorted_tables` 清表 —— **两者都从模型派生，新表自动纳入，无需改动 conftest**。

---

## 3. 文件结构

| 文件 | 动作 | 内容 |
|---|---|---|
| `backend/app/sms/__init__.py` | 新建 | 空 |
| `backend/app/sms/base.py` | 新建 | `SmsProvider` 抽象 + `mask_phone()` |
| `backend/app/sms/mock_provider.py` | 新建 | `MockSmsProvider` |
| `backend/app/sms/factory.py` | 新建 | `get_provider` / `reset_provider_cache` / `validate_provider_config` |
| `backend/app/core/config.py` | 改 | 新增 6 个配置项（§4.4） |
| `backend/app/core/exceptions.py` | 改 | 新增 `TooManyRequestsError`、`SmsProviderError` |
| `backend/app/core/deps.py` | 改 | 新增 `get_optional_user` |
| `backend/app/auth/models.py` | 改 | `User.phone` + 新模型 `PhoneVerificationCode` |
| `backend/app/auth/schemas.py` | 改 | `normalize_phone` + 三个新 schema；`UserOut.phone`；`UserUpdate.phone` |
| `backend/app/auth/repository.py` | 改 | 新增 6 个函数（§5） |
| `backend/app/auth/service.py` | 改 | `send_phone_code` / `login_by_phone`；`create_candidate_account(actor=)` 加免密分支；`update_user` 支持 `phone` |
| `backend/app/auth/router.py` | 改 | 两个新端点；`PATCH /users/{id}` 透传 `phone` |
| `backend/app/interview/schemas.py` | 改 | `InvitationAcceptRequest.password` 放宽为可选 |
| `backend/app/interview/service.py` | 改 | `accept_invitation` 透传 `actor` |
| `backend/app/interview/candidate_router.py` | 改 | `accept` 端点加 `get_optional_user` 并透传 |
| `backend/app/main.py` | 改 | 调 `validate_sms_provider_config()` |
| `backend/script.sql` | 改 | 同步 `user.phone` + 新表 |
| `backend/tests/test_architecture.py` | 改 | 登记 `sms` 包（**三处**，见下） |
| `backend/tests/test_auth_phone.py` | 新建 | service 层用例 |
| `backend/tests/api/test_api_auth.py` | 改 | 两端点 + 绑定手机号用例 |
| `backend/tests/test_auth_candidate.py` | 改 | `accept` 免密分支用例 |

> **`sms` 不建分层文件**：它像 `ai` 一样是**纯基础设施包**，不需要
> `models.py` / `schemas.py` / `repository.py` / `service.py` / `router.py`
> （`test_architecture.py` 的 `LAYERED_MODULES` 不含 `ai`，本批次也不加 `sms`）。
>
> ⚠️ **`test_architecture.py` 必须改三处，漏一处 `sms` 就完全不受保护**：
> 1. `ALL_MODULES` 加入 `"sms"`
> 2. `test_nine_modules_exist` 的 `assert len(ALL_MODULES) == 9` → `== 10`
>    （该断言是**防漏登记**用的：只写 `<=` 时，新增包却忘了登记会表现为「这个包的分层与
>    依赖方向不受任何测试保护」，而全部用例依然全绿）
> 3. 新增 `test_sms_depends_on_no_business_module`，与
>    `test_ai_depends_on_no_business_module` **逐字同构**（parametrize `app/sms/*.py`，
>    `_module_deps(path) & BUSINESS_MODULES` 必须为空）
> 4. 顺手更新模块 docstring 里的「九个独立 package」→「十个」（该注释已在 `ai` 之后列了
>    `practice` / `resume`，说明它本就随包增长而维护）

---

## 4. 接口契约

### 4.1 端点

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth/phone/code` | 公开 | 发送验证码 |
| POST | `/api/auth/phone/login` | 公开 | 验证码登录 |
| PATCH | `/api/users/{id}` | admin | **既有端点扩展**：支持 `phone` |

### 4.2 请求 / 响应

**`POST /api/auth/phone/code`**

```jsonc
// 请求
{ "phone": "13800138000" }

// 200
{ "expires_in": 300, "dev_code": "483920" }   // dev_code 仅 mock provider 下非 null
```

```jsonc
// 429（限流）
{ "code": "TOO_MANY_REQUESTS", "message": "发送过于频繁，请稍后再试",
  "detail": { "retry_after_seconds": 42 } }
```

**`POST /api/auth/phone/login`**

```jsonc
// 请求
{ "phone": "13800138000", "code": "483920" }

// 200 —— 与 /auth/login **逐字段一致**（复用 LoginResponse）
{ "token": "eyJ…", "user": { "id": 7, "username": "phone_13800138000",
                            "role": "candidate", "is_active": true,
                            "phone": "13800138000", "created_at": "…" } }
```

> **响应体复用 `LoginResponse` 是有意的**：前端按 `user.role` 分流到 HR 端或候选人端的
> 逻辑（`login.js` / `candidate-login.js`）因此**不需要第二套实现**（PRD §4.16）。

**`PATCH /api/users/{id}`**（既有端点，请求体加一个可选字段）

```jsonc
{ "role": "hr", "is_active": true, "phone": "13800138000" }  // 绑定
{ "phone": null }                                            // 解绑
```

> ⚠️ **必须能区分「不传 `phone`」与「传 `phone: null`」**：不传 = 不改，传 `null` = 解绑。
> 既有 `UserUpdate` 的 `role` / `is_active` 都用 `if role is not None` 判定，**区分不了这两者**
> —— 对这两个字段无害（没有「清空角色」的需求），但 `phone` 需要一个解除绑定的入口。
> 实现用 Pydantic v2 的 `payload.model_fields_set`：**`"phone" in payload.model_fields_set`**
> 表示调用方确实传了这个键（哪怕值是 `null`）。`auth.router` 据此决定是否把 `phone`
> 传进 service，`service.update_user` 的 `fields` 字典按同一判据组装。

### 4.3 service 层签名

```python
# auth/service.py
@dataclass
class PhoneCodeResult:
    expires_in: int
    dev_code: str | None      # 仅 provider.echoes_code 为真时非空


def send_phone_code(db: Session, phone: str, request_ip: str | None) -> PhoneCodeResult:
    """三层限流校验 → 生成并落码 → 交 sms Provider 发送。"""


def login_by_phone(db: Session, phone: str, code: str) -> LoginResult:
    """校验验证码 → 取号或建号 → 签发 JWT。**复用既有的 LoginResult**。"""


def create_candidate_account(
    db: Session, username: str, password: str | None, actor: User | None = None
) -> User:
    """既有函数**追加 `actor` 参数**（默认 None，既有调用点行为不变）。
    `actor` 非空且 `actor.id == existing.id` 时跳过密码比对（§4.1 免密分支）。"""


def update_user(db, actor, user_id, role=None, is_active=None, phone=UNSET) -> User:
    """既有函数**追加 `phone`**。用哨兵 `UNSET` 区分「不传」与「传 null」。"""
```

### 4.4 配置项（`core/config.py`）

| 配置 | 默认 | 用途 |
|---|---|---|
| `SMS_PROVIDER` | `"mock"` | Provider 选择（§6） |
| `PHONE_CODE_TTL_SECONDS` | `300` | 验证码有效期 |
| `PHONE_CODE_MAX_ATTEMPTS` | `5` | 单码错误上限，达即作废 |
| `PHONE_CODE_RESEND_INTERVAL_SECONDS` | `60` | 同号重发间隔 |
| `PHONE_CODE_MAX_PER_PHONE_PER_DAY` | `10` | 同号 24 小时上限 |
| `PHONE_CODE_MAX_PER_IP_PER_HOUR` | `20` | 同 IP 1 小时上限 |

> 全部进配置而非写死在代码里：它们是**产品可调**的量（TTL 太短用户来不及输入、太长则风险窗口
> 变大；上限太紧会误伤弱网重试、太松则挡不住短信轰炸）。与既有的
> `RESUME_UPLOAD_MAX_BYTES` / `CANDIDATE_FEEDBACK_LEVEL` 同一取舍。

### 4.5 `sms` 包契约

```python
# sms/base.py
def mask_phone(phone: str) -> str:
    """138****8000。手机号是 PII，日志里一律用掩码（§6）。"""


class SmsProvider(ABC):
    #: 是否把验证码回显给调用方（仅 Mock 为 True）。
    #: ⚠️ 用**能力标志**而非 isinstance 判断：service 因此不需要 import 任何具体
    #: Provider 类，也就不会有「service 认识 mock」这条隐性耦合（§6）。
    echoes_code: bool = False

    @abstractmethod
    def send_code(self, phone: str, code: str) -> None:
        """把验证码发到 phone。失败抛 SmsProviderError。"""


# sms/factory.py —— 与 ai/factory.py 逐项同构
PROVIDER_MOCK = "mock"
KNOWN_PROVIDERS = (PROVIDER_MOCK,)

def get_provider() -> SmsProvider: ...          # 单例缓存
def reset_provider_cache() -> None: ...         # 供测试切换实现
def validate_provider_config() -> None: ...     # 启动期 fail fast
```

> **`factory.py` 与 `ai/factory.py` 逐项同构**（单例缓存 + `reset_provider_cache` + 启动期校验），
> 是为了让「Agent 该在哪儿接入」这件事在两个包里有同一个答案。**未知 `SMS_PROVIDER` 取值
> 直接抛 `SmsProviderError` 并拒绝启动** —— 静默退回 Mock 会让生产在无人察觉的情况下
> 把验证码写进日志（§6）。

---

## 5. repository 层

`auth/repository.py` 新增（**全部查询只在这里**，`test_service_uses_repository_not_raw_sql` 会拦 service 里的裸 SQL）：

| 函数 | 用途 |
|---|---|
| `get_by_phone(db, phone) -> User \| None` | 手机号查账号（登录取号 / 唯一性校验） |
| `get_latest_code(db, phone) -> PhoneVerificationCode \| None` | 取该号**最新**一条码（**不论是否消费/过期** —— 供重发间隔判定） |
| `get_active_code(db, phone) -> PhoneVerificationCode \| None` | 取该号最新且**未消费、未过期、未达错误上限**的码（登录比对用） |
| `count_codes(db, *, phone=None, request_ip=None, since) -> int` | 限流计数（日上限 / IP 小时上限） |
| `invalidate_codes(db, phone) -> int` | 把该号所有未消费的码置为已消费（**新码发出即作废旧码**） |
| `create_code(db, ...) -> PhoneVerificationCode` | 落一条新码 |

> **`get_latest_code` 与 `get_active_code` 是两个函数而不是一个带参数**：它们的**判据不同**
> ——前者要回答「上次发码是什么时候」（消费过的也算），后者要回答「有没有可用的码」。
> 合成一个会让调用方每次都要想「我这次要不要过滤掉已消费的」，而滤错的方向是
> **放行一个已用过的码**，属于安全侧的错误。
>
> **`sms` 不碰 repository**：它没有表，也不需要数据访问（§1.3）。

---

## 6. 业务流程设计

### 6.1 发码（`send_phone_code`）

```
1. 归一化 + 校验手机号（schema 层完成，非法 → **400**，见 §7）
2. 限流三条，按序号短路（任一不过 → TooManyRequestsError，detail 带 retry_after_seconds）
   a. 同号重发间隔：get_latest_code(phone) 存在且 created_at > now - 60s
      → retry_after = 60 - (now - created_at)
   b. 同号日上限：count_codes(phone=…, since=now-24h) >= 10
      → retry_after = 该窗口内最早那条 + 24h - now
   c. 同 IP 小时上限：count_codes(request_ip=…, since=now-1h) >= 20
      → retry_after = 窗口内最早那条 + 1h - now
      （request_ip 为 None 时**跳过 c** —— 拿不到 IP 不应导致无法发码）
3. invalidate_codes(db, phone)    ← 新码发出即作废旧码
4. 生成 6 位数字码（secrets.randbelow(1_000_000) 补零到 6 位，**用 secrets 不用 random**）
5. 生成 16 字节随机盐，算 sha256(salt + code)
6. create_code(db, …)，commit
7. get_sms_provider().send_code(phone, code)   ← 失败抛 SmsProviderError，**不回滚第 6 步**
8. 返回 PhoneCodeResult(expires_in=TTL, dev_code=code if provider.echoes_code else None)
```

> **第 7 步失败不回滚第 6 步**（PRD §7）：真实运营商接口的失败**往往是超时而非未送达**，
> 回滚会制造「码已作废」的假象 —— 用户手机上收到一条永远用不了的验证码，而库里查不到它。
> 保留它让「重发」与「重试」两条路的代价一致。
>
> **第 3 步必须发生在第 6 步之前**：顺序颠倒会留下两条同时有效的码，攻击面乘以 N（§4.16）。

### 6.2 登录（`login_by_phone`）

```
1. 归一化 + 校验手机号（schema 层，非法 → **400**）
2. get_active_code(db, phone)
   · 取不到 → 抛 UnauthorizedError(_CODE_FAILED_MESSAGE)      ← 与 3 同一句文案
3. 比对 sha256(row.code_salt + code) 与 row.code_hash
   · 不符 → row.attempts += 1；若 attempts >= MAX → consumed_at = now（作废）
            commit；抛 UnauthorizedError(_CODE_FAILED_MESSAGE)  ← 与 2 同一句文案
4. 相符 → row.consumed_at = now（一次性消费），commit
5. get_by_phone(db, phone)
   · 有账号 → 若 not is_active → UnauthorizedError("账号已禁用，请联系管理员")
             否则 result_user = 该账号
   · 无账号 → result_user = _create_phone_candidate(db, phone)   ← 见 6.3
6. return LoginResult(token=create_access_token(result_user.id), user=result_user)
```

> `_CODE_FAILED_MESSAGE = "验证码错误或已失效"` —— **第 2 步与第 3 步必须用同一个模块级常量**，
> 与既有的 `_LOGIN_FAILED_MESSAGE` 同一手法。文案写两处就一定会分叉，而分叉本身就是
> 可区分的信号（§4.16）。

### 6.3 自动建号（`_create_phone_candidate`）

```
username = f"phone_{phone}"
password = secrets.token_urlsafe(32)          ← 不可知，永不告诉任何人
落库：create(db, username, hash_password(password), ROLE_CANDIDATE)
      并写 phone=phone
```

> ⚠️ **角色写死 `ROLE_CANDIDATE`，函数不接受 `role` 参数**：这是本模块唯一的安全红线
> （§4.16）。让角色可配置，就等于「知道某个手机号 → 拿到 HR 身份」。**不接受参数**
> 比「默认 candidate 但可覆盖」更难写错。
>
> **`password` 是随机不可知值**（§5.2）：这样不必给 `password_hash` 加可空分支
> （那会让 `login()` 多一条「凭据缺失」特例），又天然让密码登录路径拒绝该账号。
>
> **`username` 冲突的处理**：`_create_candidate` 已用「先查重 + 唯一索引兜底 + `IntegrityError`
> → `BusinessError("用户名已被占用")`」。`"phone_"` 前缀让这个冲突**几乎不可能发生**
> （需要有人把用户名取成 `phone_13800138000`）；万一发生，返回既有的 409 文案即可 ——
> 不为此另造分支。

### 6.4 `accept` 免密分支（`create_candidate_account`）

```
existing = get_by_username(db, username)
if existing is None:
    if not password: 抛 UnauthorizedError(_LOGIN_FAILED_MESSAGE)   ← 新建必须有密码
    return _create_candidate(db, username, password)

if existing.role != ROLE_CANDIDATE:
    raise BusinessError("用户名已被占用")                            ← 既有行为不变

# —— 以下是原有分支，仅新增最外层那一个 if ——
免密 = actor is not None and actor.id == existing.id
if not 免密:
    if not password or not verify_password(password, existing.password_hash):
        raise UnauthorizedError(_LOGIN_FAILED_MESSAGE)

if not existing.is_active:
    raise UnauthorizedError("账号已禁用，请联系管理员")
return existing
```

> ⚠️ **判据必须同时满足两条**（§4.1）：只认 `actor is not None` 会让攻击者用自己的 token
> 去绑他人的账号 —— 那正是「密码不符即拒绝」要防的事。`actor.id == existing.id` 保证
> **持 token 者只能绑定自己的账号**，因此不引入任何新的越权口。
>
> **`is_active` 校验在两条路径上都保留**：免密分支跳过的是**密码**，不是**禁用检查**。
> 被禁用的账号无论如何都不得被复用绑定（module-12 的既有结论：绑定会消耗掉一次性邀请码，
> 而该账号此后 `login` 与 `get_current_user` 都拒绝它）。
>
> **`actor` 的来源是 `get_optional_user`，它对任何解析失败都返回 `None`** ——
> 包括 token 无效、用户不存在、**账号已禁用**。后者的效果是「禁用账号持 token 时不走免密」，
> 随后仍被上面的 `is_active` 检查拦住，**不构成绕过**。

### 6.5 `get_optional_user`（`core/deps.py`）

```python
def get_optional_user(db=Depends(get_db), authorization=Header(default=None)) -> User | None:
    """尽力解析当前用户；**任何一步失败都返回 None，绝不抛错**。"""
```

> 语义与 `get_current_user` **刻意相反**：这里 token 无效**不是**错误，只是「没有加速可用」，
> 调用方随后会退回原有路径，**权限不会被放宽**（§4.1）。若这里抛 401，「带着过期 token 去激活」
> 会从「按密码正常激活」变成「激活失败」—— 是一个纯粹的功能退化。
>
> ⚠️ **需在执行时确认 `decode_token` 抛的异常类型**：它应抛 `InvalidTokenError`（`AppError` 子类）。
> 若它会抛出非 `AppError` 的异常（如 `jwt` 库的原始异常），则必须在此收口为 `None`，
> 否则公开端点会因一个坏 token 直接 500。

---

## 7. 错误契约

| 情形 | 状态码 / code | 文案 | 出处 |
|---|---|---|---|
| 手机号格式非法 | 400 `VALIDATION_ERROR` | 请求参数不合法（`detail.fields` 指出哪个字段） | §7 |
| 缺 `phone` / 缺 `code` | 400 `VALIDATION_ERROR` | 同上（字段必填缺失） | §7 |
| 发码限流（三条任一） | **429 `TOO_MANY_REQUESTS`** | 发送过于频繁，请稍后再试（`detail.retry_after_seconds`） | §7 |
| 验证码不存在 / 过期 / 已消费 / 不匹配 | 401 `UNAUTHORIZED` | **验证码错误或已失效**（四类**同一句**） | §4.16、§7 |
| 错误次数超上限 | 401 `UNAUTHORIZED` | 同上（码已作废，后续按「已失效」处理） | §7 |
| 账号已禁用 | 401 `UNAUTHORIZED` | 账号已禁用，请联系管理员（**`detail.reason = "account_disabled"`**） | §4.1、§4.16 |
| 手机号已被其他账号绑定 | 409 `BUSINESS_ERROR` | 该手机号已被占用（**不区分占用者角色**） | §7 |
| 短信发送失败 | **502 `SMS_PROVIDER_ERROR`** | 短信服务发送失败，请稍后重试（**码仍有效**） | §7 |
| `SMS_PROVIDER` 取值未知 | 启动即失败 | 抛 `SmsProviderError`，拒绝启动 | §6 |

### 与 practice 的 409 不一致（**有意为之，需在代码注释里说明**）

`practice/service.py::_check_rate_limit` 超限时抛的是 **`BusinessError` → 409**「操作过于频繁，
请稍后再试」。本批次发码限流用 **429**，两者不一致。取舍如下：

- **本批次用 429 是对的**：发码限流是**有明确重试时机**的失败，`Retry-After` / 429 是 HTTP
  为该场景预定义的语义，前端要据 `retry_after_seconds` 显示「45 秒后可重发」的倒计时。
  合并进 400/409 会让前端**永久失去这个信息**（PRD §7 已把这条与「不新增 413」的取舍对照说明）
- **不回溯改 practice**：practice 的限流契约已被既有测试与前端固化，改它属于超范围的
  **破坏性契约变更**（且它的重试窗口只有 60 秒、前端也没做倒计时，收益接近于零）
- ⚠️ **两处不一致必须在代码里留下痕迹**：在 `_check_rate_limit` 与 `TooManyRequestsError`
  两侧各加一行注释互指，否则下一个人会把其中一个「顺手改统一」而不知道代价

---

## 8. 测试清单

### `backend/tests/test_auth_phone.py`（新建，service 层）

`FakeSms` 通过 `monkeypatch.setattr("app.auth.service.get_sms_provider", lambda: fake)` 注入；
`fake.echoes_code` 可控，用于断言 `dev_code` 的出现与否。

| # | 用例 | 断言 |
|---|---|---|
| 1 | 首次发码 | 返回 `expires_in == 300`，`dev_code` 为 6 位数字 |
| 2 | **`dev_code` 在非 mock 下不出现** | `echoes_code=False` 时 `dev_code is None` |
| 3 | 同号 60 秒内重发 | `TooManyRequestsError`，`detail["retry_after_seconds"]` 在 1–60 |
| 4 | 同号 24 小时第 11 次 | `TooManyRequestsError`（造 10 条历史码后触发） |
| 5 | 同 IP 1 小时第 21 次 | `TooManyRequestsError`（换不同号、同 IP 造 20 条） |
| 6 | **新码使旧码立即失效** | 发两次码，用**第一条**的码登录 → 401（被 `invalidate_codes` 作废） |
| 7 | 验证码正确 → 登录成功 | 返回 `LoginResult`，`user.role == "candidate"` |
| 8 | **未知手机号 → 自动建号** | 断言账号被创建，且 `role == "candidate"`、`phone == 该号`、`username == "phone_" + 该号`；**并断言 `role != "hr" and role != "admin"`** |
| 9 | 自动建号的账号密码不可用 | 用空串 / 该手机号 / `"password"` 走 `/auth/login` 均 401（哈希原像不可知） |
| 10 | **已绑定 hr 手机号 → 登录得 hr 身份** | 手工给 hr 账号设 `phone`，验证码登录返回 `role == "hr"` |
| 11 | 码错误 → `attempts` 自增 | 断言库内 `attempts == 1`，响应为 401 |
| 12 | 错满 5 次 → 作废 | 第 6 次用**正确**的码 → 仍 401（`consumed_at` 已置位） |
| 13 | **四种失败文案逐字相同** | 不存在 / 过期 / 已消费 / 不匹配，四者 `message` 完全相同且均为 `"验证码错误或已失效"` |
| 14 | 码过期 | 手工把 `expires_at` 拨到过去 → 401 |
| 15 | 已消费的码不可再用 | 成功后用同一个码再登一次 → 401 |
| 16 | 被禁用账号（未绑定→不适用；已绑定） | 已绑定的账号 `is_active=False` → 401「账号已禁用，请联系管理员」 |
| 17 | **发码不因手机号是否已注册而不同** | 已注册 / 未注册两种手机号，发码响应**结构逐字段一致**（除 `dev_code` 值本身） |
| 18 | 短信发送失败 | `FakeSms` 抛 `SmsProviderError`；断言异常向上传播**且库内的码仍存在、仍未被消费**（对应 §6.1 的回滚取舍） |
| 19 | 手机号归一化 | `" 138 0013 8000 "` / `"+8613800138000"` / `"8613800138000"` 归一到 `"13800138000"`，且**只建一个账号** |

### `backend/tests/api/test_api_auth.py`（改，端点层）

| # | 用例 | 断言 |
|---|---|---|
| 20 | `POST /auth/phone/code` 正常 | 200，`expires_in` / `dev_code` 齐全 |
| 21 | 缺 `phone` / 格式非法 | **400** `VALIDATION_ERROR`（**不是 422** —— 项目统一收口为 400） |
| 22 | 限流 | 429 `TOO_MANY_REQUESTS`，`detail.retry_after_seconds` 存在 |
| 23 | `POST /auth/phone/login` 正常 | 200，响应体字段与 `/auth/login` **键集完全相同** |
| 24 | 验证码错 | 401，`code == "UNAUTHORIZED"` |
| 25 | **响应体与 `/auth/login` 同构** | 两个端点的响应 JSON **键集合完全相等**（防有人给手机登录另加字段，前端分流逻辑就得多一套） |
| 26 | `PATCH /users/{id}` 绑定手机号 | 200，`user.phone` 为该号 |
| 27 | 绑定已被占用的手机号 | 409「该手机号已被占用」 |
| 28 | **传 `phone: null` 解绑** | 200，`user.phone` 为 null |
| 29 | **不传 `phone` 时不动手机号** | 先绑定，再只传 `{"role":"hr"}` → `phone` **保持原值**（`model_fields_set` 判据） |
| 30 | HR token 调 `PATCH /users/{id}` | 403 |
| 31 | **既有 `/auth/login` 与 `/auth/register` 不受影响** | 两者的既有用例全绿（回归） |

### `backend/tests/test_auth_candidate.py`（改，`accept` 免密分支）

| # | 用例 | 断言 |
|---|---|---|
| 32 | 带**本人** token + 用户名是自己 + **不传密码** | 激活成功 |
| 33 | 带**本人** token + 用户名是自己 + 传了错密码 | 激活成功（免密分支下密码根本不参与） |
| 34 | 带**他人** token + 用户名是别人 | 401「用户名或密码错误」（**与既有密码不符同一文案**） |
| 35 | 带**他人** token + 用户名是别人 + **密码正确** | 激活成功（既有行为不变，免密只是少输一次） |
| 36 | 不带 token + 不传密码 | 401「用户名或密码错误」 |
| 37 | 不带 token + 密码正确 | 激活成功（既有行为不变） |
| 38 | **本人 token + 用户名不存在**（新建路径） | 不传密码 → 401；传密码 → 建号成功 |
| 39 | **被禁用账号持本人 token + 不传密码** | 401，且**邀请未被消费**（`status` 仍 `pending`、`candidate_user_id` 仍为空）。⚠️ 文案是**通用那句**「用户名或密码错误」而非「账号已禁用」：`get_optional_user` 对已禁用用户返回 `None`（见 §6.5），请求因此没走到免密分支，而是退回密码校验、而它没有密码。**结果一致：绑定不发生** —— 这条钉住的就是这个结果 |
| 40 | 过期 / 无效 token | 退化为「不带 token」路径（按密码校验），**不 500** |

### `backend/tests/test_architecture.py`（改）

| # | 用例 | 断言 |
|---|---|---|
| 41 | 十个包齐备 | `ALL_MODULES` 含 `sms`，`len == 10` |
| 42 | `sms` 不依赖业务模块 | 新增用例全绿 |

> `backend/tests/test_ai_factory.py` 与本模块**同构**，是 `sms` 工厂测试的模板：
> 建议同步新建 `test_sms_factory.py`（未知取值抛 `SmsProviderError`、单例缓存、
> `reset_provider_cache` 生效、`mask_phone` 输出形如 `138****8000`）。

---

## 9. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | ⚠️ **自动建号角色恒为 `candidate`** | 用例 8（含反向断言） |
| 2 | ⚠️ **`dev_code` 只在 mock 下发** | 用例 2、20 |
| 3 | 三层限流各自生效且带 `retry_after_seconds` | 用例 3、4、5、22 |
| 4 | **四种失败文案逐字相同** | 用例 13 |
| 5 | 新码发出即作废旧码 | 用例 6 |
| 6 | 验证码一次性 | 用例 12、15 |
| 7 | 已绑定 hr 手机号登录得 hr 身份 | 用例 10 |
| 8 | **`accept` 免密判据两条同时满足** | 用例 32–34 |
| 9 | 免密分支**未绕过** `is_active` | 用例 39 |
| 10 | 手机号归一化，不产生重复账号 | 用例 19 |
| 11 | **手机登录与密码登录响应体键集相同** | 用例 25 |
| 12 | 既有 auth 行为零回归 | 用例 31 + `pytest backend/tests/test_auth*.py backend/tests/api/test_api_auth.py backend/tests/api/test_api_candidate.py` |
| 13 | 分层与依赖方向全绿 | `pytest backend/tests/test_architecture.py` |
| 14 | `script.sql` 与 dev 库 `information_schema` **实测一致** | 逐列 / 逐索引核对，结果留档 |
| 15 | 无新增依赖 | `git status` 看 `requirements.txt` 未改 |

### 本批次**不跑**的验证（轻量档，用户已确认）

- ❌ 全量 e2e（`test_e2e_flows.py`、`smoke_e2e.py`）
- ❌ `test_state_machine_matrix.py` / 其他无关模块的测试
- ❌ 多 agent 代码走查、独立测试报告文档

**风险落在哪**：`accept` 端点被改动，而它的既有用例在 `test_api_candidate.py` 里
（**已列入用例 12 的回归范围**）。若这条回归不跑，免密分支可能悄悄破坏既有邀请链 ——
这是本批次风险最高的一处，因此**必须跑**。

---

## 附：模块依赖顺序

```
module-31（本模块）
  ├─ 1. 数据库：改模型 → 同步 script.sql → dev 库增量 DDL → information_schema 比对
  ├─ 2. sms 包：base / mock_provider / factory（+ test_sms_factory.py）
  ├─ 3. core：config 配置项 / exceptions 两个新错误 / deps.get_optional_user
  ├─ 4. auth：models → schemas → repository → service → router
  ├─ 5. interview：schemas.password 放宽 → service 透传 actor → candidate_router 加依赖
  ├─ 6. main.py：validate_sms_provider_config()
  └─ 7. test_architecture.py 登记 sms（**漏了则新包不受保护**）
        ↓
module-32（前端）
```

**步骤 1 必须最先做**：模型改了但库没改，服务起不来；而库改了模型没改，
`create_all` 建的测试库与 dev 库会分叉 —— 两边都是「测试全绿但演示炸掉」的经典成因。
