"""interview 模块数据访问层。"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.interview.models import (
    ANSWER_SOURCE_CANDIDATE,
    INVITATION_ACCEPTED,
    Answer,
    Interview,
    InterviewInvitation,
    InterviewPrep,
    InterviewQuestion,
)
from app.position.models import Position


# ------------------------------ 面试 ------------------------------


def create_interview(
    db: Session,
    position_id: int,
    candidate_name: str,
    contact: str | None,
    created_by: int,
) -> Interview:
    interview = Interview(
        position_id=position_id,
        candidate_name=candidate_name,
        candidate_contact=contact,
        status="draft",
        created_by=created_by,
    )
    db.add(interview)
    db.flush()  # 取得 id，供后续写入面试题
    return interview


def list_by_owner(
    db: Session, owner_id: int | None
) -> list[tuple[Interview, str]]:
    """返回 (面试, 岗位名) 列表。owner_id 为 None 表示不过滤（admin）。"""
    stmt = select(Interview, Position.name).join(
        Position, Interview.position_id == Position.id
    )
    if owner_id is not None:
        stmt = stmt.where(Interview.created_by == owner_id)
    stmt = stmt.order_by(Interview.id.desc())  # 新的在前
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def get_by_id(db: Session, interview_id: int) -> Interview | None:
    """不带权限过滤 —— 权限判定在 service。"""
    return db.get(Interview, interview_id)


def get_position(db: Session, position_id: int) -> Position | None:
    return db.get(Position, position_id)


def update_interview(db: Session, interview: Interview, **fields: object) -> Interview:
    for key, value in fields.items():
        setattr(interview, key, value)
    return interview


# ---------------------------- 面试题 ----------------------------


def create_questions(db: Session, items: list[dict]) -> list[InterviewQuestion]:
    questions = [InterviewQuestion(**item) for item in items]
    db.add_all(questions)
    db.flush()
    return questions


def list_questions(db: Session, interview_id: int) -> list[InterviewQuestion]:
    stmt = (
        select(InterviewQuestion)
        .where(InterviewQuestion.interview_id == interview_id)
        .order_by(InterviewQuestion.seq)
    )
    return list(db.execute(stmt).scalars().all())


def get_question_entry(db: Session, entry_id: int) -> InterviewQuestion | None:
    return db.get(InterviewQuestion, entry_id)


def list_question_ids(db: Session, interview_id: int) -> set[int]:
    """本场已有的**题库题目 id** 集合 —— 补题幂等的依据。

    补题前把本场已有题从候选池里剔除，AI 因此不可能再挑到它们：
    「重复调用不产生重复题目」由此保证（注意它**不**意味着「重复调用无效果」，
    池子变小后 AI 会挑下一批不存在的题，见 service.match_questions_by_resume）。
    """
    stmt = select(InterviewQuestion.question_id).where(
        InterviewQuestion.interview_id == interview_id
    )
    return set(db.execute(stmt).scalars().all())


def max_seq(db: Session, interview_id: int) -> int:
    """本场最大 seq；无题时返回 0（追加时从 +1 续接，不重排既有题目）。"""
    stmt = select(func.max(InterviewQuestion.seq)).where(
        InterviewQuestion.interview_id == interview_id
    )
    return db.execute(stmt).scalar_one_or_none() or 0


def get_resume_id_of_interview(db: Session, interview_id: int) -> int | None:
    """集中一处读 `interview.resume_id`。

    「HR 读简历 / 补题 / 生成准备提纲」三处都经此读取。未关联时**如何表现由
    调用方决定**（404 / 409 / 走无简历分支），这里只给事实 —— 集中一处是为了
    让这条约定有地方可写，而不是把三种语义统一掉。
    """
    stmt = select(Interview.resume_id).where(Interview.id == interview_id)
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------- 面试前准备 ----------------------------


def get_prep_by_interview(db: Session, interview_id: int) -> InterviewPrep | None:
    """不带权限过滤 —— 权限判定在 service（与既有约定一致）。"""
    stmt = select(InterviewPrep).where(InterviewPrep.interview_id == interview_id)
    return db.execute(stmt).scalars().first()


def create_prep(db: Session, **fields: object) -> InterviewPrep:
    prep = InterviewPrep(**fields)
    db.add(prep)
    db.flush()
    return prep


def update_prep(
    db: Session, prep: InterviewPrep, **fields: object
) -> InterviewPrep:
    for key, value in fields.items():
        setattr(prep, key, value)
    return prep


# ------------------------------ 回答 ------------------------------


def upsert_answer(
    db: Session,
    interview_question_id: int,
    content: str,
    *,
    source: str | None = None,
    answered_by: int | None = None,
) -> Answer:
    """写入 / 更新一条作答。

    两条通道共用本方法：
      HR 通道       只传 content（+ answered_by）；不传 source，走模型默认 'hr'
      候选人通道     传 source='candidate' 与 answered_by

    `source` **只在插入时生效，更新时一律不动** —— 它答的是「作答最初从哪条
    通道进来」。候选人编辑了 HR 预填的作答，来源仍是 hr；HR 覆盖了候选人的
    作答，来源仍是 candidate（PRD §5.2 要求保留该事实）。

    `submitted_at` 刻意不接受参数：交卷时刻只由 submit 流程写入，
    作答保存路径不应触碰它（否则候选人交卷后再保存会刷新交卷时间）。
    """
    stmt = select(Answer).where(Answer.interview_question_id == interview_question_id)
    answer = db.execute(stmt).scalar_one_or_none()

    if answer is None:
        answer = Answer(
            interview_question_id=interview_question_id,
            content=content,
            answered_by=answered_by,
            **({"source": source} if source is not None else {}),
        )
        db.add(answer)
    else:
        answer.content = content
        answer.recorded_at = datetime.now(UTC).replace(tzinfo=None)
        if answered_by is not None:
            answer.answered_by = answered_by

    db.flush()
    return answer


def list_answers(db: Session, interview_id: int) -> list[Answer]:
    stmt = (
        select(Answer)
        .join(InterviewQuestion, Answer.interview_question_id == InterviewQuestion.id)
        .where(InterviewQuestion.interview_id == interview_id)
    )
    return list(db.execute(stmt).scalars().all())


# ---------------------------- 交卷 ----------------------------


def bulk_upsert_empty_answers(
    db: Session, entry_ids: list[int], submitted_at: datetime, answered_by: int
) -> None:
    """给未作答的题补空串作答行（交卷时调用）。

    为什么补行：交卷是**面试级**事实，而 submitted_at 存在 answer 行上。
    若候选人第 5 题没作答，就没有第 5 题的 answer 行，交卷时间无处可存。
    补空串之后每道题都有作答行，评估取数也不必处理缺失。

    空串在既有约定中正是「未作答，按 0 分处理」；与「没记录」的区别在于
    现在有明确的事实 —— **他确实选择了不作答**。
    """
    if not entry_ids:
        return

    existing = set(
        db.execute(
            select(Answer.interview_question_id).where(
                Answer.interview_question_id.in_(entry_ids)
            )
        )
        .scalars()
        .all()
    )

    for entry_id in entry_ids:
        if entry_id in existing:
            continue
        db.add(
            Answer(
                interview_question_id=entry_id,
                content="",
                answered_by=answered_by,
                source=ANSWER_SOURCE_CANDIDATE,
                submitted_at=submitted_at,
            )
        )

    db.flush()


def mark_all_submitted(
    db: Session, interview_id: int, submitted_at: datetime
) -> None:
    """给该面试的**全部**作答行写交卷时刻（交卷时调用，与补空串同一事务）。"""
    stmt = (
        select(Answer)
        .join(InterviewQuestion, Answer.interview_question_id == InterviewQuestion.id)
        .where(InterviewQuestion.interview_id == interview_id)
    )
    for answer in db.execute(stmt).scalars().all():
        if answer.submitted_at is None:
            answer.submitted_at = submitted_at
    db.flush()


def get_submitted_at(db: Session, interview_id: int) -> datetime | None:
    """本人是否已交卷 —— 任一条作答的 submitted_at 非空即视为已交卷。

    交卷会给全部行写同一时刻，故 MAX 就是首次交卷时刻（供幂等返回）。
    """
    stmt = (
        select(func.max(Answer.submitted_at))
        .join(InterviewQuestion, Answer.interview_question_id == InterviewQuestion.id)
        .where(InterviewQuestion.interview_id == interview_id)
    )
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------- 作答邀请 ----------------------------


def create_invitation(db: Session, **fields: object) -> InterviewInvitation:
    invitation = InterviewInvitation(**fields)
    db.add(invitation)
    db.flush()
    return invitation


def lock_interview(db: Session, interview_id: int) -> Interview | None:
    """对面试行加排他锁 —— 串行化同一场面试的并发操作。

    用于 `accept_invitation` 的「一次性接受」语义。锁必须落在**真实存在**的
    行上：对「尚未存在的接受记录」加锁只能拿到间隙锁，而间隙锁之间互不冲突，
    挡不住两个并发请求同时通过检查。面试行是现成的、唯一的互斥点。
    """
    stmt = select(Interview).where(Interview.id == interview_id).with_for_update()
    return db.execute(stmt).scalars().first()


def get_invitation_by_code(
    db: Session, code: str, *, for_update: bool = False
) -> InterviewInvitation | None:
    """不带权限过滤 —— 权限判定在 service。

    `for_update=True` 走当前读，绕过事务快照读到最新已提交版本；判定
    「这条码是否已被并发请求消耗掉」必须用它。同时 `populate_existing` 强制
    覆盖身份映射里已加载的实例 —— 否则同一行先前已被本会话读过时，
    SQLAlchemy 会直接复用旧属性，当前读也白做。
    """
    stmt = select(InterviewInvitation).where(InterviewInvitation.code == code)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.execute(stmt).scalars().first()


def get_invitation_by_id(
    db: Session, invitation_id: int
) -> InterviewInvitation | None:
    return db.get(InterviewInvitation, invitation_id)


def list_invitations(db: Session, interview_id: int) -> list[InterviewInvitation]:
    stmt = (
        select(InterviewInvitation)
        .where(InterviewInvitation.interview_id == interview_id)
        .order_by(InterviewInvitation.created_at.desc(), InterviewInvitation.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def update_invitation(
    db: Session, invitation: InterviewInvitation, **fields: object
) -> InterviewInvitation:
    for key, value in fields.items():
        setattr(invitation, key, value)
    return invitation


def get_accepted_invitation(
    db: Session,
    interview_id: int,
    candidate_user_id: int,
    *,
    for_update: bool = False,
) -> InterviewInvitation | None:
    """候选人可见性判定的数据源（见 service.get_interview_for_candidate）。

    只有 status='accepted' 且绑定本人的邀请才算数。

    「撤销已接受的邀请」如何处理：**把 status 置为 revoked**。于是本查询天然
    排除它，访问被立即切断，而 candidate_user_id 与 accepted_at 仍留在该行上
    ——「谁在何时接受了」这一事实没有被抹掉。撤销后该行不再有第二种解释，
    因此不需要额外的 NOT EXISTS 条件。

    `for_update=True` 用于接受邀请的临界区：那里已持有面试行锁，本查询必须
    走当前读才能看见并发事务刚提交的那一行（快照读会读到旧版本，从而漏判）。
    """
    stmt = select(InterviewInvitation).where(
        InterviewInvitation.interview_id == interview_id,
        InterviewInvitation.candidate_user_id == candidate_user_id,
        InterviewInvitation.status == INVITATION_ACCEPTED,
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.execute(stmt).scalars().first()


def list_accepted_interviews_for_candidate(
    db: Session, candidate_user_id: int
) -> list[tuple[Interview, str]]:
    """候选人端「我参与的面试」列表，返回 (面试, 岗位名)。"""
    stmt = (
        select(Interview, Position.name)
        .join(InterviewInvitation, InterviewInvitation.interview_id == Interview.id)
        .join(Position, Interview.position_id == Position.id)
        .where(
            InterviewInvitation.candidate_user_id == candidate_user_id,
            InterviewInvitation.status == INVITATION_ACCEPTED,
        )
        .order_by(Interview.id.desc())
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


# ---------------------------- 聚合计数 ----------------------------


def count_questions(db: Session, interview_ids: list[int]) -> dict[int, int]:
    if not interview_ids:
        return {}
    stmt = (
        select(InterviewQuestion.interview_id, func.count(InterviewQuestion.id))
        .where(InterviewQuestion.interview_id.in_(interview_ids))
        .group_by(InterviewQuestion.interview_id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def count_answers(db: Session, interview_ids: list[int]) -> dict[int, int]:
    """只统计「非空回答」—— 空串表示候选人未作答。

    用 `TRIM(...) != ""` 与 service 侧 `_is_answered`（`content.strip()`）同口径：
    只写了空格的作答算未作答。此前这里只判 `content != ""`，同一份数据
    在交卷响应（0 题）与列表接口（1 题）会给出相反的结论。
    """
    if not interview_ids:
        return {}
    stmt = (
        select(InterviewQuestion.interview_id, func.count(Answer.id))
        .join(Answer, Answer.interview_question_id == InterviewQuestion.id)
        .where(
            InterviewQuestion.interview_id.in_(interview_ids),
            func.trim(Answer.content) != "",
        )
        .group_by(InterviewQuestion.interview_id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}
