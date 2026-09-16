"""question 模块数据访问层。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.question.models import Question
from app.question.schemas import QuestionFilters


def create(db: Session, **fields: object) -> Question:
    question = Question(**fields)
    db.add(question)
    return question


def bulk_insert(db: Session, items: list[dict]) -> list[Question]:
    questions = [Question(**item) for item in items]
    db.add_all(questions)
    return questions


def list_filtered(
    db: Session, owner_id: int | None, filters: QuestionFilters
) -> list[Question]:
    """owner_id 为 None 表示不过滤（admin 可见全部）。"""
    stmt = select(Question)

    if owner_id is not None:
        stmt = stmt.where(Question.created_by == owner_id)
    if filters.position_id is not None:
        stmt = stmt.where(Question.position_id == filters.position_id)
    if filters.category:
        stmt = stmt.where(Question.category == filters.category)
    if filters.dimension:
        stmt = stmt.where(Question.dimension == filters.dimension)
    if filters.source:
        stmt = stmt.where(Question.source == filters.source)
    if filters.keyword:
        stmt = stmt.where(Question.content.like(f"%{filters.keyword}%"))

    return list(db.execute(stmt.order_by(Question.id)).scalars().all())


def list_by_position(
    db: Session, owner_id: int | None, position_id: int
) -> list[Question]:
    """出题候选查询。

    恒按 id 升序 —— 这是 interview 抽取算法确定性的基础。
    不过滤 source：AI 题与人工题都可作为候选。
    """
    stmt = select(Question).where(Question.position_id == position_id)
    if owner_id is not None:
        stmt = stmt.where(Question.created_by == owner_id)
    return list(db.execute(stmt.order_by(Question.id)).scalars().all())


def get_by_id(db: Session, question_id: int) -> Question | None:
    """不带权限过滤 —— 权限判定在 service。"""
    return db.get(Question, question_id)


def update(db: Session, question: Question, **fields: object) -> Question:
    for key, value in fields.items():
        setattr(question, key, value)
    return question


def delete(db: Session, question: Question) -> None:
    """删除题目。被面试引用时由外键 RESTRICT 拒绝。"""
    db.delete(question)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("该题目已被面试引用，无法删除") from exc
