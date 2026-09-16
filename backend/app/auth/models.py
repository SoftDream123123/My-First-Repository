"""auth 模块数据模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ROLE_ADMIN = "admin"
ROLE_HR = "hr"


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
    role: Mapped[str] = mapped_column(
        Enum(ROLE_ADMIN, ROLE_HR, name="user_role"),
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
