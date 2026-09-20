"""interview 模块数据模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
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
# 面试题的来源之一：按候选人简历从题库匹配而来（PRD §4.14）。
# ⚠️ 取值定义在**本模块**而非 ai 包：它是 `interview_question.source_snapshot`
# 的字段值，与 AI 层的输出形状无关。`SOURCE_BANK` / `SOURCE_AI` 留在 ai 是因为
# 那两者是**题目自身**的来源（question.source），去处不同故不合并。
SOURCE_RESUME_MATCH = "resume_match"

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
    # 候选人关联到本场面试的简历。
    #
    # **写入方是候选人**（不是 HR）：简历由候选人提交，时间上晚于创建面试，
    # 因此创建面试的请求体不接受 resume_id（PRD §4.13、§8）。
    # RESTRICT 而非 SET NULL：SET NULL 会让「简历被删 → 面试静默失去简历」
    # 而不报错；RESTRICT 让删除方（候选人）收到 409 自行决定（module-17 §5.4）。
    resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resume.id", ondelete="RESTRICT"), nullable=True
    )
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
    # ⚠️ Enum 列：新增取值 `resume_match` 时，统一收口建表要执行的是
    #    ALTER TABLE interview_question MODIFY COLUMN source_snapshot
    #      ENUM('bank','ai','resume_match') NOT NULL
    # **不是 ADD COLUMN** —— 按「新增了哪些列 / 表」收集 DDL 会漏掉它，
    # 后果是补题时写入 resume_match 直接抛 Data truncated for column。
    #
    # 不改成 VARCHAR：为加一个取值而放开整列的取值约束，会丢掉数据库对
    # 「来源」的全部校验，代价大于一次 MODIFY COLUMN（module-19 §3.2）。
    source_snapshot: Mapped[str] = mapped_column(
        Enum(SOURCE_BANK, SOURCE_AI, SOURCE_RESUME_MATCH, name="interview_question_source"),
        nullable=False,
    )
    # AI 给出的匹配理由 —— 与 source_snapshot='resume_match' **成对出现**：
    # 非匹配来源的题恒为 NULL。两个事实并存，「有没有理由」与「是不是匹配来的」
    # 不会漂移（PRD §5.2）。
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class InterviewPrep(Base):
    """面试前准备助手的三部分产出（PRD §4.11、§5.2）。

    **一场面试唯一**（`interview_id` 加唯一约束）：重新生成即覆盖，不做版本历史。
    用唯一约束而不是「查询时取最新」，让「不可能有两条」成为数据库事实。

    **不进入面试状态机**：它是面试开始前的工作稿，「已生成 / 已编辑」与面试
    推进阶段相互正交。因此只用 `generated_at` / `edited_at` 记录事实，
    面试是否可生成由 `interview.status` 判定（见 service）。

    **不放 created_by**：能读写它的只有面试的拥有者，而面试本身已有
    `created_by`。再加一列会引入「两个 created_by 不一致怎么办」的伪问题。
    """

    __tablename__ = "interview_prep"
    __table_args__ = (
        UniqueConstraint("interview_id", name="uq_interview_prep_interview"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview.id", ondelete="CASCADE"), nullable=False
    )
    # 三个 JSON 列 NOT NULL：三部分**要么都有要么都没有**（ai 层的契约是
    # 「任一为空即整批失败」，见 module-18 §5.3）。允许 NULL 会引入
    # 「有记录但某部分缺失」这一无意义状态。
    #
    # 模型层给 default=list 仅为裸构造可用；**表上无 DEFAULT** —— MySQL 的
    # JSON 列不支持字面量默认值，实际写入永远显式供值。
    outline: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    focus_points: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    question_plan: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    # 最近一次 **AI 生成** 的时刻
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # 最近一次 **HR 手工编辑** 的时刻；AI 重新生成时置回 NULL ——
    # 「重新生成」意味着此前的编辑已被整体覆盖，留着旧值会让界面显示
    # 「已手工编辑」而内容其实是 AI 的（module-19 §3.3）。
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<InterviewPrep interview_id={self.interview_id}>"
