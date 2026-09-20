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

# ---- 作答来源通道（PRD §5.2）----
ANSWER_SOURCE_HR = "hr"
ANSWER_SOURCE_CANDIDATE = "candidate"

# ---- 作答邀请状态（PRD §5.1）----
# 只存三个**终态**取值；`expired` 是派生态，不落库（见 service 的 _derive_status）。
# 用定时任务刷过期状态需要调度器（违反单机约束），且进程不常驻时状态会滞后失真。
INVITATION_PENDING = "pending"
INVITATION_ACCEPTED = "accepted"
INVITATION_REVOKED = "revoked"

INVITATION_DB_STATUSES = (
    INVITATION_PENDING,
    INVITATION_ACCEPTED,
    INVITATION_REVOKED,
)

# 对外呈现的第四个取值（派生，不入库）
INVITATION_EXPIRED = "expired"


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

    两条作答通道（HR 手工录入 / 候选人在线作答）**共用本表**，用三列表达来源：
      source       作答**最初**从哪条通道进来（HR 覆盖后仍保留 candidate）
      answered_by  **最后修改者**
      submitted_at 候选人**交卷**时刻；HR 手工录入时为 NULL

    source 与 answered_by 语义不同、不可合并：HR 覆盖候选人作答后
    source='candidate' 而 answered_by=HR，两个事实都需要保留（PRD §5.2）。

    刻意**不加 is_locked**：「候选人能否改」由 submitted_at 是否为空推导。
    两个字段表达同一状态必然漂移。
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
    source: Mapped[str] = mapped_column(
        Enum(ANSWER_SOURCE_HR, ANSWER_SOURCE_CANDIDATE, name="answer_source"),
        nullable=False,
        default=ANSWER_SOURCE_HR,
        server_default=ANSWER_SOURCE_HR,
    )
    # 允许为 NULL：迁移前的数据无法倒推修改者。
    # 空值表示未知，比编造一个值更诚实。
    answered_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Answer id={self.id} iq={self.interview_question_id}>"


class InterviewInvitation(Base):
    """作答邀请码（PRD §4.4、§5.2）。

    与面试状态机**解耦**：候选人作答只是输入通道，不进入面试状态机。

    **邀请码明文存储**：HR 需要在系统内展示与复制（PRD §1.3）。若只存哈希，
    生成时能显示一次、之后列表页就再也拿不到 —— 与 PRD 直接冲突。
    缓解措施：128 位熵、有效期默认 7 天、一次性接受、可随时撤销、
    候选人侧接口不泄露面试是否存在。代价是「数据库泄露即邀请泄露」。
    """

    __tablename__ = "interview_invitation"
    __table_args__ = (
        UniqueConstraint("code", name="uq_interview_invitation_code"),
        Index("ix_interview_invitation_interview", "interview_id"),
        Index("ix_interview_invitation_candidate", "candidate_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(*INVITATION_DB_STATUSES, name="invitation_status"),
        nullable=False,
        default=INVITATION_PENDING,
        server_default=INVITATION_PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<InterviewInvitation id={self.id} status={self.status}>"
