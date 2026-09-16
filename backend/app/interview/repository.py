"""interview 模块数据访问层。"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.interview.models import Answer, Interview, InterviewQuestion
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


# ------------------------------ 回答 ------------------------------


def upsert_answer(db: Session, interview_question_id: int, content: str) -> Answer:
    stmt = select(Answer).where(Answer.interview_question_id == interview_question_id)
    answer = db.execute(stmt).scalar_one_or_none()

    if answer is None:
        answer = Answer(interview_question_id=interview_question_id, content=content)
        db.add(answer)
    else:
        answer.content = content
        answer.recorded_at = datetime.now(UTC).replace(tzinfo=None)

    db.flush()
    return answer


def list_answers(db: Session, interview_id: int) -> list[Answer]:
    stmt = (
        select(Answer)
        .join(InterviewQuestion, Answer.interview_question_id == InterviewQuestion.id)
        .where(InterviewQuestion.interview_id == interview_id)
    )
    return list(db.execute(stmt).scalars().all())


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
    """只统计「非空回答」—— 空串表示候选人未作答。"""
    if not interview_ids:
        return {}
    stmt = (
        select(InterviewQuestion.interview_id, func.count(Answer.id))
        .join(Answer, Answer.interview_question_id == InterviewQuestion.id)
        .where(
            InterviewQuestion.interview_id.in_(interview_ids),
            Answer.content != "",
        )
        .group_by(InterviewQuestion.interview_id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}
