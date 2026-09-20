"""evaluation 模块数据模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# 评分精度：DECIMAL(3,1) —— 定点类型避免浮点误差累积到总分平均值里
SCORE_PRECISION = (3, 1)


class QuestionScore(Base):
    """逐题评分。"""

    __tablename__ = "question_score"
    __table_args__ = (
        UniqueConstraint(
            "interview_id",
            "interview_question_id",
            name="uq_question_score_interview_entry",
        ),
        Index("ix_question_score_interview", "interview_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 冗余 interview_id 是刻意的：「清空某面试全部评分」与「按面试查询」
    # 是最高频操作，冗余这一列让二者免于联表
    interview_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview.id", ondelete="CASCADE"), nullable=False
    )
    interview_question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interview_question.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Numeric(*SCORE_PRECISION), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<QuestionScore iq={self.interview_question_id} score={self.score}>"


class DimensionScore(Base):
    """多维评分（供雷达图）。"""

    __tablename__ = "dimension_score"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "dimension", name="uq_dimension_score_interview_dim"
        ),
        Index("ix_dimension_score_interview", "interview_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(*SCORE_PRECISION), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<DimensionScore {self.dimension}={self.score}>"


class Report(Base):
    """汇总报告。一次面试一份。"""

    __tablename__ = "report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interview.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    overall_score: Mapped[float] = mapped_column(
        Numeric(*SCORE_PRECISION), nullable=False
    )
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    weaknesses: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Report interview={self.interview_id} overall={self.overall_score}>"


class CandidateFeedback(Base):
    """面向候选人的脱敏反馈。

    **PRD §5.2 的实体表未列出本表**，是本设计的补充（见 module-14 §3.1）。

    为什么独立成表而不是给 report 加三列：
      · 把两份**受众不同、可见性规则不同**的文本混在一张表里，``report`` 的
        任何读取路径（含 HR 报告接口）都可能不小心把候选人字段带出去；
      · 独立表让可见性边界落在**表**这一层 —— HR 报告接口**结构上读不到**
        候选人字段，且 ``report`` 的 schema 完全不动，直接满足 PRD §4.9
        「HR 端报告视图保持不变」。

    两点刻意的缺失：
      · **没有 updated_at**：反馈的输入是报告，报告重评即整体替换。支持「更新」
        就必须回答「哪一部分过期了」；整行删除重建把这个问题消掉。
      · **不存总分**：总分属于「评估结果」而非「候选人文案」。存储层与可见性层
        解耦后，**改档位配置不需要重新生成反馈**。
    """

    __tablename__ = "candidate_feedback"
    __table_args__ = (
        # 一次面试一份候选人反馈；并发首次生成由它兜底
        UniqueConstraint("interview_id", name="uq_candidate_feedback_interview"),
        Index("ix_candidate_feedback_interview", "interview_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview.id", ondelete="CASCADE"), nullable=False
    )
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    weaknesses: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<CandidateFeedback interview={self.interview_id}>"
