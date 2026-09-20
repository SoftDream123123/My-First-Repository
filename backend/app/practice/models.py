"""practice 模块数据模型：练习会话与待答项。

两张表都**不与 interview 发生任何关系** —— 刷题是独立的业务线（PRD §9）。
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# ---- 会话状态 ----
STATUS_ONGOING = "ongoing"
STATUS_FINISHED = "finished"
ALL_STATUSES = (STATUS_ONGOING, STATUS_FINISHED)

# ---- 难度（与 question 的取值一致；常量必须各自定义，practice 不依赖 question）----
DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"
DIFFICULTIES = (DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD)

# ---- 题型 ----
QUESTION_TYPE_SINGLE_CHOICE = "single_choice"
QUESTION_TYPE_SHORT_ANSWER = "short_answer"
QUESTION_TYPES = (QUESTION_TYPE_SINGLE_CHOICE, QUESTION_TYPE_SHORT_ANSWER)


class PracticeSession(Base):
    """一次练习会话。

    筛选条件（position / category / dimension / difficulty / question_type）在会话上留痕 ——
    否则无法回答「这次练的是哪类题」。position_id 允许 NULL：不选岗位就是
    「全库随机刷题」，这是刷题的常见用法，设为 NOT NULL 会强迫候选人先选岗位。
    """

    __tablename__ = "practice_session"
    __table_args__ = (
        Index("ix_practice_session_candidate", "candidate_user_id"),
        Index("ix_practice_session_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 练习归属 —— 候选人数据隔离的依据
    candidate_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    position_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("position.id", ondelete="RESTRICT"), nullable=True
    )
    # 本次练习关联的简历；NULL = 未关联（绝大多数练习如此）。
    # RESTRICT 而非 SET NULL：被练习关联的简历不可删除（module-17 §5.4 的 409
    # 依赖它），SET NULL 会让历史练习静默失去「这次是按哪份简历推荐的」这一事实。
    resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resume.id", ondelete="RESTRICT"), nullable=True
    )
    # 本次**是否真的**用 AI 按简历选排了题目。
    #
    # 它不是 resume_id 的冗余：resume_id 非空**不代表**真的按简历推荐了 ——
    # AI 可能失败或未命中，此时已降级为普通筛选（PRD §7）。两个字段回答两个
    # 不同问题：「候选人想用哪份简历」vs「系统实际做到了没有」。
    # 合并成一个字段会让降级变成**静默**：候选人关联了简历却拿到一堆通用题，
    # 界面上没有任何解释，只能认为功能坏了。
    resume_match_applied: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),  # MySQL 无 false 字面量，用 0
    )
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(50), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(
        Enum(*DIFFICULTIES, name="practice_difficulty"), nullable=True
    )
    question_type: Mapped[str | None] = mapped_column(
        Enum(*QUESTION_TYPES, name="practice_question_type"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(*ALL_STATUSES, name="practice_session_status"),
        nullable=False,
        default=STATUS_ONGOING,
        server_default=STATUS_ONGOING,
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    # 两个计数**每次提交后重算**，不累加 —— 同一题可重复提交（错题重练是正当用法），
    # 累加会让计数超过 total。重算永远等于事实。
    answered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    correct_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<PracticeSession id={self.id} status={self.status}>"


class PracticeItem(Base):
    """待答项 —— 会话开始时即按筛选条件生成，并写满题目快照。

    题目快照（content / options / reference_answer / dimension / question_type）
    让题库后续删改不影响进行中与历史练习的复看与判分。逐题提交只回填
    user_answer / is_correct / score / explanation / answered_at。

    两个快照字段是**刻意补充**的（PRD §5.2 未列）：
      dimension_snapshot  不加则按维度统计只能联表读 question.dimension，
                          题库改维度后历史练习的统计会跟着漂移
      question_type       不加则判分分支要联表读当前值；若 HR 在会话开始后把题
                          从简答改成单选，已有的空 options_snapshot 会与「单选」
                          分支冲突，判分直接崩
    """

    __tablename__ = "practice_item"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_practice_item_seq"),
        Index("ix_practice_item_session", "session_id"),
        Index("ix_practice_item_question", "question_id"),
        # 服务于错题本派生查询
        Index("ix_practice_item_correct", "is_correct"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_session.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question.id", ondelete="RESTRICT"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)

    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    options_snapshot: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    # 存量题目没有参考答案，或 HR 尚未补录 → 允许 NULL
    reference_answer_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    question_type: Mapped[str] = mapped_column(
        Enum(*QUESTION_TYPES, name="practice_item_question_type"), nullable=False
    )

    # NULL 表示**尚未提交**（与「提交了空串」不同）
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # **三态**：TRUE 判对 / FALSE 判错 / NULL 未判分。
    # NULL 是「未判分」这一独立事实（无参考答案，或 AI 判分失败），与「判错」
    # 语义完全不同 —— 错题本不能把未判分的题算进去，正确率的分母也不含它。
    # 加一个 is_scored 布尔表达同一事实只会让两个字段漂移。
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<PracticeItem id={self.id} seq={self.seq}>"
