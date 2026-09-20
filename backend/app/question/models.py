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

# 题型（PRD §4.3）：刷题只做文本问答，不含编程题
QUESTION_TYPE_SINGLE_CHOICE = "single_choice"
QUESTION_TYPE_SHORT_ANSWER = "short_answer"


class Question(Base):
    """题库题目。

    dimension 存字符串而非 ID —— 与 evaluation.dimension_score.dimension
    保持同一命名空间，评估打分时可直接按维度名归集，无需联表。

    同一张表同时服务两条业务线：HR 出题抽取与候选人刷题取题。
    """

    __tablename__ = "question"
    __table_args__ = (
        # 出题取数的主查询路径
        Index("ix_question_position_owner", "position_id", "created_by"),
        Index("ix_question_dimension", "dimension"),
        Index("ix_question_source", "source"),
        Index("ix_question_created_by", "created_by"),
        # 刷题按题型取题（PRD §4.7）
        Index("ix_question_type", "question_type"),
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

    # ---- 刷题相关字段（MVP-2 新增，PRD §4.3）----
    # 默认简答：存量题目全部是纯文本题，按「简答」理解才符合事实。
    # 默认单选会凭空造出无选项的单选题。
    question_type: Mapped[str] = mapped_column(
        Enum(
            QUESTION_TYPE_SINGLE_CHOICE,
            QUESTION_TYPE_SHORT_ANSWER,
            name="question_type",
        ),
        nullable=False,
        default=QUESTION_TYPE_SHORT_ANSWER,
        server_default=QUESTION_TYPE_SHORT_ANSWER,
    )
    # 选项不建独立表：它是题目的从属属性，量级小（≤10）且无需跨题查询
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # 允许为 NULL：存量题目没有答案，且存在「先有题、后有答案」的中间态
    # （AI 生成后由 HR 确认）。若给空串默认值会把「未填写」与「故意留空」混为一谈。
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

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
