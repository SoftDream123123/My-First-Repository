"""position 模块数据模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Position(Base):
    """岗位表。

    评估维度以 JSON 数组存储（字符串），与 dimension_score.dimension 保持
    同一命名空间 —— 评估打分时可直接按维度名归集，无需联表。
    """

    __tablename__ = "position"
    __table_args__ = (
        # 同一 HR 下岗位名唯一；不同 HR 可各自维护同名岗位
        Index("uq_position_owner_name", "created_by", "name", unique=True),
        Index("ix_position_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    jd: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Position id={self.id} name={self.name!r}>"
