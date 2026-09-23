"""auth 模块数据访问层。

只做数据操作，不做业务判断（「密码是否正确」「用户名是否重复」「这个码还能用吗」
属于 service）。
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.auth.models import PhoneVerificationCode, User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def get_by_phone(db: Session, phone: str) -> User | None:
    stmt = select(User).where(User.phone == phone)
    return db.execute(stmt).scalar_one_or_none()


def create(
    db: Session,
    username: str,
    password_hash: str,
    role: str,
    phone: str | None = None,
) -> User:
    user = User(
        username=username, password_hash=password_hash, role=role, phone=phone
    )
    db.add(user)
    return user


def list_all(db: Session) -> list[User]:
    stmt = select(User).order_by(User.id)
    return list(db.execute(stmt).scalars().all())


def update(db: Session, user: User, **fields: object) -> User:
    for key, value in fields.items():
        setattr(user, key, value)
    return user


# ------------------------------ 手机验证码 ------------------------------


def create_code(
    db: Session,
    *,
    phone: str,
    code_hash: str,
    code_salt: str,
    expires_at: datetime,
    request_ip: str | None,
) -> PhoneVerificationCode:
    row = PhoneVerificationCode(
        phone=phone,
        code_hash=code_hash,
        code_salt=code_salt,
        expires_at=expires_at,
        request_ip=request_ip,
    )
    db.add(row)
    return row


def get_latest_code(db: Session, phone: str) -> PhoneVerificationCode | None:
    """该号**最新**一条码，**不论是否已消费 / 已过期**。

    与 `get_active_code` 分成两个函数而不是一个带开关的，是因为它们回答的
    问题不同：本函数回答「上次发码是什么时候」（重发间隔判定要用它 ——
    已消费的码也算一次发送），后者回答「有没有可用的码」。
    合成一个会让调用方每次都要想「这次要不要过滤掉已消费的」，
    而滤错的方向是**放行一个用过的码**，属于安全侧的错误。
    """
    stmt = (
        select(PhoneVerificationCode)
        .where(PhoneVerificationCode.phone == phone)
        .order_by(PhoneVerificationCode.created_at.desc(), PhoneVerificationCode.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_active_code(
    db: Session, phone: str, now: datetime, max_attempts: int
) -> PhoneVerificationCode | None:
    """该号最新且**可用的**码：未消费、未过期、错误次数未达上限。

    三个条件全放在 SQL 里，三种失效情形因此都收敛成同一个 `None` ——
    正好对应 PRD §4.16 要求的「四种失败不得有任何可区分差异」：
    service 拿着 None 只会抛同一句 401，没有机会区分它们。
    """
    stmt = (
        select(PhoneVerificationCode)
        .where(
            PhoneVerificationCode.phone == phone,
            PhoneVerificationCode.consumed_at.is_(None),
            PhoneVerificationCode.expires_at > now,
            PhoneVerificationCode.attempts < max_attempts,
        )
        .order_by(PhoneVerificationCode.created_at.desc(), PhoneVerificationCode.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def count_codes(
    db: Session,
    *,
    since: datetime,
    phone: str | None = None,
    request_ip: str | None = None,
) -> int:
    """统计 `created_at > since` 且匹配条件的发码条数（限流用）。

    调用方必须**至少给一个**过滤条件：两个都不给就等于「统计全表近一小时」，
    那个数字会立刻把任何人的配额耗尽。
    """
    conditions = [PhoneVerificationCode.created_at > since]
    if phone is not None:
        conditions.append(PhoneVerificationCode.phone == phone)
    if request_ip is not None:
        conditions.append(PhoneVerificationCode.request_ip == request_ip)

    stmt = select(func.count()).select_from(PhoneVerificationCode).where(*conditions)
    return db.execute(stmt).scalar_one()


def earliest_code_since(
    db: Session,
    *,
    since: datetime,
    phone: str | None = None,
    request_ip: str | None = None,
) -> PhoneVerificationCode | None:
    """限流窗口内**最早**那条码。

    用于算 `retry_after_seconds`：配额在「最早那条滑出窗口」时恢复，
    因此恢复时刻 = 最早一条的 created_at + 窗口长度。
    """
    conditions = [PhoneVerificationCode.created_at > since]
    if phone is not None:
        conditions.append(PhoneVerificationCode.phone == phone)
    if request_ip is not None:
        conditions.append(PhoneVerificationCode.request_ip == request_ip)

    stmt = (
        select(PhoneVerificationCode)
        .where(*conditions)
        .order_by(PhoneVerificationCode.created_at.asc(), PhoneVerificationCode.id.asc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def invalidate_codes(db: Session, phone: str, now: datetime) -> int:
    """把该号所有未消费的码置为已消费，返回受影响行数。

    新码发出即作废旧码（PRD §4.16）：否则多个码同时有效，攻击面乘以 N。
    与「成功使用」共用 `consumed_at` —— 两者对读取方的语义完全相同（不可用），
    分成两个字段只会让 `get_active_code` 的 WHERE 更长而无任何新信息。
    """
    stmt = (
        # ⚠️ 用别名 `sa_update`：本模块自己有一个 `update(db, user, **fields)`
        # （见上），裸 `update` 会被它遮蔽，调用时抛
        # 「update() missing 1 required positional argument: 'user'」——
        # 报错指向的是一个被遮蔽的内建，排查方向很容易跑偏。
        sa_update(PhoneVerificationCode)
        .where(
            PhoneVerificationCode.phone == phone,
            PhoneVerificationCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    return db.execute(stmt).rowcount