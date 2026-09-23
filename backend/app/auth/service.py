"""auth 模块业务逻辑：登录、用户管理、数据隔离判定。"""

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.models import (
    PHONE_USERNAME_PREFIX,
    ROLE_ADMIN,
    ROLE_CANDIDATE,
    ROLE_HR,
    PhoneVerificationCode,
    User,
)
from app.core.config import get_settings
from app.core.exceptions import (
    BusinessError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
    UnauthorizedError,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.sms.factory import get_provider as get_sms_provider

# 用户名或密码错误时的统一文案 —— 用户不存在与密码错误必须返回完全相同的响应，
# 避免攻击者据此枚举出系统中已存在的用户名。
_LOGIN_FAILED_MESSAGE = "用户名或密码错误"

# 账号被禁用时的文案。三处（密码登录 / 手机验证码登录 / 凭邀请复用账号）共用
# 同一个常量：三处的语义完全相同，写三份就一定会分叉。
_ACCOUNT_DISABLED_MESSAGE = "账号已禁用，请联系管理员"

# 验证码不可用时的统一文案（PRD §4.16）。
#
# ⚠️ 四种情形共用这一句：**码不存在 / 已过期 / 已消费 / 不匹配**。
# 任何可区分的差异都会把这个端点变成验证码状态探测器。刻意与 _LOGIN_FAILED_MESSAGE
# 分开写而不是复用：前者说的是「用户名或密码」，这里说的是「验证码」——
# 用户看到的文案必须指向他刚刚填错的那个框。
_CODE_FAILED_MESSAGE = "验证码错误或已失效"

# 发码被限流时的文案。429 的 detail 里带 retry_after_seconds，前端据此显示倒计时。
_RATE_LIMITED_MESSAGE = "发送过于频繁，请稍后再试"


class _UnsetType:
    """哨兵类型：区分「不传 phone」与「传 phone=None（解绑）」（PRD §4.1）。

    用哨兵而不是 `None` 做默认值：`None` 已经是「解绑」这个**有意义**的取值，
    不能同时兼任「没传」。与 Pydantic 的 `model_fields_set` 是同一手法，
    两层各管一段（router 判请求体有没有这个键，service 判自己收到了什么）。
    """

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return "UNSET"


UNSET = _UnsetType()


@dataclass
class LoginResult:
    token: str
    user: User


@dataclass
class PhoneCodeResult:
    """发码结果。

    `dev_code` 仅当 Provider 会把验证码回显时非空（默认的 Mock 就是）
    —— 判据是 `provider.echoes_code` 这个**能力标志**，不是 isinstance，
    因此本模块不需要 import 任何具体 Provider 类。
    """

    expires_in: int
    dev_code: str | None


def _now() -> datetime:
    """本地时间基准：与 `phone_verification_code` 的 DATETIME 列一致（naive UTC）。

    与 practice.service._now 同一手法 —— 会话时区已钉死在 UTC（core.db），
    因此这里用 naive UTC 才能与 `func.now()` 的 server default 对齐。
    """
    return datetime.now(UTC).replace(tzinfo=None)



def get_user_by_id(db: Session, user_id: int) -> User | None:
    """供 core.deps.get_current_user 使用。"""
    return repository.get_by_id(db, user_id)


def login(db: Session, username: str, password: str) -> LoginResult:
    """校验凭据并签发 JWT。"""
    user = repository.get_by_username(db, username)

    if user is None or not verify_password(password, user.password_hash):
        # 时序加固：用户不存在时也执行一次哈希比对，拉平两条分支的响应时间
        if user is None:
            verify_password(password, hash_password("timing-attack-mitigation"))
        raise UnauthorizedError(_LOGIN_FAILED_MESSAGE)

    if not user.is_active:
        raise UnauthorizedError(_ACCOUNT_DISABLED_MESSAGE)

    return LoginResult(token=create_access_token(user.id), user=user)


# ------------------------------ 手机验证码登录 ------------------------------


def _hash_code(salt: str, code: str) -> str:
    """sha256(salt + code)。

    用 sha256 而非 bcrypt 的理由见 `models.PhoneVerificationCode` 的类注释：
    抗暴力的屏障是「5 分钟 + 一次性 + 错 5 次作废」三条窗口约束，不是哈希强度。
    """
    return hashlib.sha256(f"{salt}{code}".encode("utf-8")).hexdigest()


def send_phone_code(
    db: Session, phone: str, request_ip: str | None
) -> PhoneCodeResult:
    """三层限流校验 → 生成并落码 → 交 sms Provider 发送（PRD §4.16）。"""
    settings = get_settings()
    now = _now()

    _check_send_rate_limit(db, phone, request_ip, now, settings)

    # 新码发出即作废旧码（PRD §4.16）。必须发生在落新码**之前** ——
    # 顺序颠倒会留下两条同时有效的码，攻击面乘以 N。
    repository.invalidate_codes(db, phone, now)

    # secrets 而非 random：验证码是安全凭据，random 是可预测的 Mersenne Twister。
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)

    repository.create_code(
        db,
        phone=phone,
        code_hash=_hash_code(salt, code),
        code_salt=salt,
        expires_at=now + timedelta(seconds=settings.phone_code_ttl_seconds),
        request_ip=request_ip,
    )
    db.commit()

    provider = get_sms_provider()
    # ⚠️ 发送失败**不回滚上面那条码**（PRD §7）：真实运营商接口的失败往往是
    # 超时而非未送达。回滚会制造「码已作废」的假象 —— 用户在手机上收到一条
    # 永远用不了的验证码，而库里查不到它的存在，事后无从解释。
    # 保留它让「重发」与「重试」两条路的代价一致。
    provider.send_code(phone, code)

    return PhoneCodeResult(
        expires_in=settings.phone_code_ttl_seconds,
        dev_code=code if provider.echoes_code else None,
    )


def _check_send_rate_limit(
    db: Session, phone: str, request_ip: str | None, now: datetime, settings
) -> None:
    """发码的三层限流，任一不过即抛 429（PRD §4.16）。

    顺序按「最可能命中且最便宜」排：重发间隔只需读一行；日上限与 IP 上限各要
    一次 count，且要再读一行算恢复时刻。

    状态一律**查库判定**，不用进程内计数 —— 24 小时 / 1 小时这类窗口用内存维护
    既复杂又会在重启后清零，而验证码本来就要落库，查库是顺手的事（PRD §9）。
    """
    # ① 同一手机号的重发间隔
    latest = repository.get_latest_code(db, phone)
    if latest is not None:
        elapsed = (now - latest.created_at).total_seconds()
        interval = settings.phone_code_resend_interval_seconds
        if elapsed < interval:
            raise TooManyRequestsError(
                _RATE_LIMITED_MESSAGE,
                detail={"retry_after_seconds": max(1, math.ceil(interval - elapsed))},
            )

    # ② 同一手机号 24 小时上限
    day_window = timedelta(days=1)
    day_ago = now - day_window
    if (
        repository.count_codes(db, phone=phone, since=day_ago)
        >= settings.phone_code_max_per_phone_per_day
    ):
        raise TooManyRequestsError(
            "该手机号今日验证码次数已达上限，请明天再试",
            detail={
                "retry_after_seconds": _seconds_until_room(
                    db, since=day_ago, window=day_window, now=now, phone=phone
                )
            },
        )

    # ③ 同一 IP 1 小时上限。拿不到 IP（request.client 为 None）时**跳过**本层 ——
    # 缺失这个信息不该导致用户完全无法发码。
    if request_ip is not None:
        hour_window = timedelta(hours=1)
        hour_ago = now - hour_window
        if (
            repository.count_codes(db, request_ip=request_ip, since=hour_ago)
            >= settings.phone_code_max_per_ip_per_hour
        ):
            raise TooManyRequestsError(
                "当前网络发送次数过多，请稍后再试",
                detail={
                    "retry_after_seconds": _seconds_until_room(
                        db,
                        since=hour_ago,
                        window=hour_window,
                        now=now,
                        request_ip=request_ip,
                    )
                },
            )


def _seconds_until_room(
    db: Session,
    *,
    since: datetime,
    window: timedelta,
    now: datetime,
    phone: str | None = None,
    request_ip: str | None = None,
) -> int:
    """配额还剩几秒恢复 = 窗口内**最早**那条码滑出窗口的时刻 - now。

    用「最早一条」而不是「现在 + 窗口」：后者会让用户永远等不到，因为每次请求
    都把恢复时刻往后推。最早那条滑出窗口，配额就腾出一个位置。
    """
    earliest = repository.earliest_code_since(
        db, since=since, phone=phone, request_ip=request_ip
    )
    if earliest is None:
        # 不可达：count 已超限就说明窗口内必有行。给 1 秒兜底而不是 0，
        # 否则前端会拿到 retry_after_seconds=0 而立刻重试、再次吃 429。
        return 1
    remaining = (earliest.created_at + window - now).total_seconds()
    return max(1, math.ceil(remaining))


def login_by_phone(db: Session, phone: str, code: str) -> LoginResult:
    """校验验证码 → 取号或建号 → 签发 JWT（PRD §4.16）。

    返回值复用 `LoginResult`，使端点能给出与 `/auth/login` **逐字段一致**的
    响应体 —— 前端按 user.role 分流的逻辑因此不需要第二套实现。
    """
    settings = get_settings()
    now = _now()

    row = repository.get_active_code(
        db, phone, now, settings.phone_code_max_attempts
    )
    if row is None:
        # 不存在 / 已过期 / 已消费 / 错误次数达上限，四者都落到这里，共用同一句文案。
        raise UnauthorizedError(_CODE_FAILED_MESSAGE)

    if not hmac.compare_digest(_hash_code(row.code_salt, code), row.code_hash):
        _register_failed_attempt(db, row, now, settings)
        raise UnauthorizedError(_CODE_FAILED_MESSAGE)

    user = repository.get_by_phone(db, phone)
    if user is not None and not user.is_active:
        # 刻意**不消费这个码**：禁用的原因与验证码无关，换任何通道都不会成功；
        # 但也没必要把人仅有的一次正确输入判成「已用完」。
        #
        # `detail.reason` 与 `POST /auth/register` 被关闭时的 `self_register_disabled`
        # 是同一手法：前端要靠它把这条错误**放到合适的位置**（toast）而不是塞进
        # 验证码输入框下方 —— 两条错误同为 401，文案判别是脆的。
        raise UnauthorizedError(
            _ACCOUNT_DISABLED_MESSAGE, detail={"reason": "account_disabled"}
        )

    row.consumed_at = now  # 一次性消费
    db.commit()

    if user is None:
        user = _create_phone_candidate(db, phone)

    return LoginResult(token=create_access_token(user.id), user=user)


def _register_failed_attempt(
    db: Session, row: PhoneVerificationCode, now: datetime, settings
) -> None:
    """错一次记一次；达上限即作废该码。

    作废时置 `consumed_at`（与「成功使用」共用该列）—— 下次 `get_active_code`
    的 WHERE 会直接跳过它，用户即使改填正确的码也只会得到同一句 401。
    这正是 PRD §4.16 要求的行为：错满之后该码不再可用。
    """
    row.attempts += 1
    if row.attempts >= settings.phone_code_max_attempts:
        row.consumed_at = now
    db.commit()


def _create_phone_candidate(db: Session, phone: str) -> User:
    """为首次用手机号登录的人建一个 `candidate` 账号（PRD §4.16）。

    ⚠️ **角色写死 `ROLE_CANDIDATE`，本函数刻意不接受 role 参数。**
    这是手机验证码登录唯一的安全红线：若「手机号 → 账号」这条路径可能产出
    hr / admin，那么「知道某个手机号」就等于「拿到 HR 身份」。
    **不接受参数**比「默认 candidate 但可被覆盖」更难写错 —— 后者只需要一个
    调用点手滑就能把提权入口打开。

    HR / admin 想用手机号登录，只能由 admin 在用户管理页把号码绑到**已存在**的
    账号上（PRD §4.1），那条路径受 admin 守卫保护。

    密码是**随机不可知值**：这样不必给 password_hash 加可空分支（那会让
    `login()` 多一条「凭据缺失」特例），又天然让密码登录路径拒绝该账号 ——
    没有人能猜中这个哈希的原像。该账号要绑定邀请码时走 `accept` 的免密分支。
    """
    user = repository.create(
        db,
        f"{PHONE_USERNAME_PREFIX}{phone}",
        hash_password(secrets.token_urlsafe(32)),
        ROLE_CANDIDATE,
        phone=phone,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发下唯一索引兜底。正常路径撞不上（username 带 `phone_` 前缀、phone
        # 刚被 `get_by_phone` 确认未绑定），但真撞了不能让 500 冒出去。
        db.rollback()
        raise BusinessError("该手机号或用户名已被占用") from exc

    db.refresh(user)
    return user


def create_user(db: Session, username: str, password: str, role: str) -> User:
    """创建用户（仅 admin 可达）。"""
    if repository.get_by_username(db, username) is not None:
        raise BusinessError("用户名已存在")

    user = repository.create(db, username, hash_password(password), role)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发场景下由唯一索引兜底，查重只是为了给出友好报错
        db.rollback()
        raise BusinessError("用户名已存在") from exc

    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return repository.list_all(db)


def update_user(
    db: Session,
    actor: User,
    user_id: int,
    role: str | None = None,
    is_active: bool | None = None,
    phone: str | None | _UnsetType = UNSET,
) -> User:
    """修改用户角色 / 启用状态 / 绑定手机号（仅 admin 可达）。"""
    # 防呆：避免管理员把自己降级或禁用，导致系统无人可管。
    #
    # ⚠️ 只在**真的要改角色或状态**时才拦，不能无条件拦 —— 否则 admin 就没法
    # 给自己的账号绑手机号了（PRD §4.16 允许 admin 用手机号登录 HR 端，
    # 且没有理由要求他必须请另一个 admin 来代劳）。给自己绑手机号不会让任何人
    # 失去管理能力，因此与本防呆的目的不冲突。
    if actor.id == user_id and (role is not None or is_active is not None):
        raise BusinessError("不能修改自己的角色或状态")

    user = repository.get_by_id(db, user_id)
    if user is None:
        raise NotFoundError("用户不存在")

    fields: dict[str, object] = {}
    if role is not None:
        fields["role"] = role
    if is_active is not None:
        fields["is_active"] = is_active
    # 哨兵判据：`UNSET` = 请求体里没有 phone 这个键（不改），
    # `None` = 显式传了 null（解绑）。见 _UnsetType 的注释。
    if not isinstance(phone, _UnsetType):
        fields["phone"] = phone

    if fields:
        try:
            repository.update(db, user, **fields)
            db.commit()
        except IntegrityError as exc:
            # 手机号唯一索引兜底。文案与 4.1 的「用户名已被占用」同一口径：
            # **不区分占用者角色** —— 区分等于提供了一个账号探测接口。
            db.rollback()
            raise BusinessError("该手机号已被占用") from exc
        db.refresh(user)

    return user


def scope_owner_id(user: User) -> int | None:
    """数据隔离的统一判定入口。

    admin → None（不过滤，可见全部）
    hr    → user.id（各业务模块据此追加 WHERE created_by = :owner_id）

    其他角色（含 candidate）→ 抛 ForbiddenError。

    这是**纵深防御**：候选人不是 HR 数据的可见者，而 HR 侧路由的角色守卫
    本应在此之前就拦下他们。此处的拒绝不依赖守卫是否挂全 —— 任何漏挂守卫的
    新端点，都会在这里被拦住。两种错误做法都比抛错更糟：
      · 返回 None         → 等于不过滤，候选人看到全部数据（最坏的失败方向）
      · 返回 user.id      → 把候选人当作「创建者」，语义上伪造了一个事实
    """
    if user.role == ROLE_ADMIN:
        return None
    if user.role == ROLE_HR:
        return user.id
    raise ForbiddenError()


def ensure_resource_visible(user: User, created_by: int, label: str) -> None:
    """统一的单条资源可见性校验。

    各业务模块「取回一条记录后判断能否访问」时调用，保证隔离规则只有一处实现。
    不可见时抛 ForbiddenError（403）而非 NotFoundError —— 语义明确：资源存在但无权访问。
    """
    owner_id = scope_owner_id(user)
    if owner_id is not None and created_by != owner_id:
        raise ForbiddenError(f"无权限访问该{label}")


def ensure_owner_match(user: User, owner_id: int, label: str) -> None:
    """通用的资源归属校验：这条记录是不是我的。

    与 `ensure_resource_visible` 的分工必须分清：
      · `scope_owner_id` / `ensure_resource_visible` 回答「HR 能看到哪些」
        —— 判据是 `created_by`，且对 candidate 角色直接抛错。
      · `ensure_owner_match` 回答「这条记录是不是我的」—— 适合
        `practice_session.candidate_user_id` 这类**非 HR 拥有**的资源。

    候选人必须走本函数：用 `ensure_resource_visible` 会让候选人连自己的
    练习都读不到（见 module-16 §4 的纵深防御）。
    """
    if user.role == ROLE_ADMIN:
        return
    if user.id != owner_id:
        raise ForbiddenError(f"无权限访问该{label}")


def register_candidate(db: Session, username: str, password: str) -> User:
    """候选人自助注册（公开端点，PRD §4.1）。

    只创建 candidate 角色账号。用户名命名空间与 admin/hr 共享，
    因此「已被占用」不区分占用者角色 —— 区分等于提供了一个账号角色探测接口。
    """
    if not get_settings().candidate_self_register:
        raise BusinessError(
            "候选人自助注册已关闭，请使用邀请码激活",
            detail={"reason": "self_register_disabled"},
        )

    return _create_candidate(db, username, password)


def create_candidate_account(
    db: Session, username: str, password: str | None, actor: User | None = None
) -> User:
    """凭邀请码创建 / 复用候选人账号（供 interview 模块调用）。

    与自助注册的区别：**不校验 CANDIDATE_SELF_REGISTER 开关**。
    该开关控制的是「开放注册」，不是「凭邀请建号」—— 关闭自助注册后，
    邀请码仍是候选人的唯一入口，必须可用。

    已存在同名 candidate 时**校验身份后复用**该账号（候选人可能已注册了刷题账号，
    不应被迫换用户名）。**身份不成立即拒绝**，见函数体里的说明。

    已存在同名 hr/admin 时**硬拒绝** —— 否则 HR 账号会被
    写进 interview_invitation.candidate_user_id，从而获得候选人才有的
    「查看脱敏反馈」通道，且身份语义自相矛盾。这是越权入口。

    `actor` 是 `core.deps.get_optional_user` 的产物（带了有效 JWT 就是那个用户，
    否则为 None）。它只影响**身份证明的方式**，不影响任何权限判定（PRD §4.1）。
    """
    existing = repository.get_by_username(db, username)
    if existing is not None:
        if existing.role == ROLE_CANDIDATE:
            # 复用已有账号**必须先证明身份**（PRD §4.1/§7、module-09 §5.2）。
            #
            # 少了这一步，「知道对方用户名」就等于能把自己的邀请码绑到对方账号上，
            # 进而读到对方的面试 —— 比它原先要防的「凭码重置他人密码」更严重。
            if not _identity_proven(existing, password, actor):
                # 文案复用登录失败的那一句：不新增可区分的信号。残余的「该用户名是否
                # 存在」可探测性只对**持有有效邀请码**的人成立，而邀请码一次性、高熵、私发。
                raise UnauthorizedError(_LOGIN_FAILED_MESSAGE)
            # 禁用账号不得被复用绑定：绑定会消耗掉一次性邀请码，而该账号此后
            # login 与 get_current_user 都拒绝它 —— 候选人永远打不开这场面试，
            # HR 也无法重新发码。文案与登录一致。
            #
            # ⚠️ 这一条对**两条身份证明路径都生效**：免密分支跳过的是「密码」，
            # 不是「禁用检查」。见 module-31 §6.4。
            if not existing.is_active:
                raise UnauthorizedError(_ACCOUNT_DISABLED_MESSAGE)
            return existing
        raise BusinessError("用户名已被占用")

    if not password:
        # 新建账号必须有密码。免密分支只对「账号已存在、且持 token 者就是它本人」
        # 生效 —— 新建路径没有「本人的账号」可以证明，因此不适用。
        # 报 401 而非 422：后者会让前端凭状态码反推出「密码其实可选」这一实现细节。
        raise UnauthorizedError(_LOGIN_FAILED_MESSAGE)

    return _create_candidate(db, username, password)


def _identity_proven(
    existing: User, password: str | None, actor: User | None
) -> bool:
    """能否证明调用者就是这个账号的主人（PRD §4.1 的免密分支）。

    两条判据**必须同时**满足：

      · `actor` 非空 —— 请求带了有效的 Authorization
      · `actor.id == existing.id` —— 该 token 指向的**就是**这次要绑定的账号

    只认前者会让攻击者用自己的 token 去绑他人的账号，而那正是「密码不符即拒绝」
    要防的同一件事，防线不能松。两条同时满足时，攻击者能绑的只有他自己的账号
    —— 那是合法操作，因此**不引入任何新的越权口**。

    为何免密是合理的：密码的职责是「证明你是这个账号的主人」。已持有该账号的
    有效 JWT 是**同一件事的更强证明** —— token 只可能来自一次成功登录（要么验过
    密码，要么验过手机验证码）。再要一次密码是对同一事实的重复索取，
    没有增加任何安全性。

    对手机验证码登录来说这条分支不是可选的：手机号自动建号的账号没有可用密码
    （见 `_create_phone_candidate`），没有它，用手机号注册的候选人拿到邀请码后
    将**永远无法激活** —— 报「用户名或密码错误」，而他根本没有密码。
    """
    if actor is not None and actor.id == existing.id:
        return True
    return bool(password) and verify_password(password, existing.password_hash)


def _create_candidate(db: Session, username: str, password: str) -> User:
    """创建 candidate 账号（两个入口共用的落库部分）。"""
    if repository.get_by_username(db, username) is not None:
        raise BusinessError("用户名已被占用")

    user = repository.create(db, username, hash_password(password), ROLE_CANDIDATE)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发场景下由唯一索引兜底；查重只是为了给出友好报错
        db.rollback()
        raise BusinessError("用户名已被占用") from exc

    db.refresh(user)
    return user
