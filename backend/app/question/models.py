"""question 模块数据模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SOURCE_BANK = "bank"
SOURCE_AI = "ai"

DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"


class Question(Base):
    """题库题目。

    dimension 存字符串而非 ID —— 与 evaluation.dimension_score.dimension
    保持同一命名空间，评估打分时可直接按维度名归集，无需联表。
    """

    __tablename__ = "question"
    __table_args__ = (
        # 出题取数的主查询路径
        Index("ix_question_position_owner", "position_id", "created_by"),
        Index("ix_question_dimension", "dimension"),
        Index("ix_question_source", "source"),
        Index("ix_question_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("position.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="通用", server_default="通用"
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        Enum(DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD, name="question_difficulty"),
        nullable=False,
        default=DIFFICULTY_MEDIUM,
        server_default=DIFFICULTY_MEDIUM,
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(
        Enum(SOURCE_BANK, SOURCE_AI, name="question_source"),
        nullable=False,
        default=SOURCE_BANK,
        server_default=SOURCE_BANK,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Question id={self.id} source={self.source}>"
