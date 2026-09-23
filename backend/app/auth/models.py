"""auth 模块数据模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ROLE_ADMIN = "admin"
ROLE_HR = "hr"
ROLE_CANDIDATE = "candidate"

# 手机号账号的用户名前缀（PRD §4.16）。
#
# 为何不直接用手机号当用户名：HR 手工创建账号时很可能把手机号填进用户名字段，
# 那时 `13800138000` 已被占用，而真人拿这个号首次验证码登录时会撞 username 的
# 唯一约束 —— 建号失败，且没有任何人能解开的死路。加前缀让两个命名空间不重叠。
PHONE_USERNAME_PREFIX = "phone_"


class User(Base):
    """用户表。

    用户不做物理删除，只做 is_active=False —— 因为 position / question /
    interview 均通过 created_by 关联本表，物理删除会造成外键悬空。
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 绑定的手机号（PRD §4.16，MVP-5）。可空且唯一。
    #
    # ⚠️ 唯一索引**允许多个 NULL**，所以「可空 + 唯一」这个组合正好表达
    # 「有手机号的不许重复，没手机号的不算重复」——不需要哨兵值或额外约束。
    #
    # 只存 **11 位纯数字**，不带国家码：若允许 `+8613800138000` 与
    # `13800138000` 两种写法，唯一约束就挡不住「同一个号占两行」，
    # 而这个号的主人会拿到两个账号。归一化在 auth.schemas.normalize_phone。
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )
    role: Mapped[str] = mapped_column(
        Enum(ROLE_ADMIN, ROLE_HR, ROLE_CANDIDATE, name="user_role"),
        nullable=False,
        default=ROLE_HR,
        server_default=ROLE_HR,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<User id={self.id} username={self.username!r} role={self.role}>"


class PhoneVerificationCode(Base):
    """手机验证码（PRD §4.16，MVP-5）。

    **不存明文**：`code_hash = sha256(code_salt + code)`。库被读走也不等于能登录。

    用 sha256 而非 bcrypt 是有意的：验证码只有 6 位数字（熵 10^6），抗暴力的
    真正屏障是「5 分钟有效期 + 一次性 + 错 5 次作废」这三条窗口约束，而不是
    哈希强度；bcrypt 会给每次登录加约 200ms，且它本就不是为**短时效低熵值**设计的。

    过期**不做后台清理**（PRD §5.2）：与邀请码过期同一取舍，项目不引入调度器。
    判定只在读取时派生 —— `get_active_code` 的 WHERE 里带 `expires_at > now`。
    行数增长有界：限流已把单个手机号限制在每天 10 条以内。
    """

    __tablename__ = "phone_verification_code"
    __table_args__ = (
        # 三列都建索引，因为**三列都是查询条件**：phone 取该号最新有效码、
        # created_at 做限流窗口统计、request_ip 做 IP 维度限流。
        # 这张表除此之外没有任何业务查询。
        Index("ix_phone_verification_code_phone", "phone"),
        Index("ix_phone_verification_code_created_at", "created_at"),
        Index("ix_phone_verification_code_request_ip", "request_ip"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_salt: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # 非空 = 已被成功使用（或已被新码作废），不可再用。
    # 「作废」与「已用」共用这一个字段：两者对读取方的语义完全相同（不可用），
    # 分成两个字段只会让 `get_active_code` 的 WHERE 更长而没有任何新信息。
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<PhoneVerificationCode id={self.id} phone={self.phone!r}>"
