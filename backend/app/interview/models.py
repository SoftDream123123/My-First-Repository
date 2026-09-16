"""interview 模块数据模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# ---- 状态机取值（PRD §5.1）----
STATUS_DRAFT = "draft"
STATUS_ONGOING = "ongoing"
STATUS_COMPLETED = "completed"
STATUS_EVALUATING = "evaluating"
STATUS_EVALUATED = "evaluated"

ALL_STATUSES = (
    STATUS_DRAFT,
    STATUS_ONGOING,
    STATUS_COMPLETED,
    STATUS_EVALUATING,
    STATUS_EVALUATED,
)

SOURCE_BANK = "bank"
SOURCE_AI = "ai"


class Interview(Base):
    """面试实例。"""

    __tablename__ = "interview"
    __table_args__ = (Index("ix_interview_created_by", "created_by"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("position.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_name: Mapped[str] = mapped_column(String(100), nullable=False)
    candidate_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*ALL_STATUSES, name="interview_status"),
        nullable=False,
        default=STATUS_DRAFT,
        server_default=STATUS_DRAFT,
        index=True,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Interview id={self.id} status={self.status}>"


class InterviewQuestion(Base):
    """面试题 —— 三个快照字段是历史面试自洽的前提。

    content_snapshot   题干；题库改题后历史面试不受影响
    dimension_snapshot 考察维度；岗位维度改名后评估归集不会错位
    source_snapshot    来源；题库题目被删除后仍可还原出处
    """

    __tablename__ = "interview_question"
    __table_args__ = (
        UniqueConstraint("interview_id", "seq", name="uq_interview_question_seq"),
        Index("ix_interview_question_interview", "interview_id"),
        Index("ix_interview_question_question", "question_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question.id", ondelete="RESTRICT"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot: Mapped[str] = mapped_column(
        Enum(SOURCE_BANK, SOURCE_AI, name="interview_question_source"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<InterviewQuestion id={self.id} seq={self.seq}>"


class Answer(Base):
    """候选人回答 —— 以 interview_question_id 标识。

    要保证「一道面试题一条回答」，正确的唯一键就是 interview_question.id；
    用 (interview_id, question_id) 是绕道实现同一约束，且会阻碍
    「同一道题库题在一次面试中出现两次」的扩展。
    """

    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interview_question.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Answer id={self.id} iq={self.interview_question_id}>"
