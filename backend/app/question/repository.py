"""question 模块数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.position.models import Position
from app.question.models import Question
from app.question.schemas import PracticeFilters, QuestionFilters


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
    if filters.question_type:
        stmt = stmt.where(Question.question_type == filters.question_type)
    if filters.keyword:
        stmt = stmt.where(Question.content.like(f"%{filters.keyword}%"))

    return list(db.execute(stmt.order_by(Question.id)).scalars().all())


def list_practice_candidates(
    db: Session, filters: PracticeFilters, limit: int
) -> list[Question]:
    """刷题取题的候选集。

    **不接 owner_id，有意取全库题目** —— 候选人不是题目的创建者，若沿用
    created_by 判据候选人将一题都取不到。题目本就要展示给候选人（题干是刷题内容），
    不是敏感数据；对外视图 PracticeQuestionOut 已剥离参考答案与建题人。

    恒按 id 升序，保证取题结果确定可复现。
    """
    stmt = select(Question)

    if filters.position_id is not None:
        stmt = stmt.where(Question.position_id == filters.position_id)
    if filters.category:
        stmt = stmt.where(Question.category == filters.category)
    if filters.dimension:
        stmt = stmt.where(Question.dimension == filters.dimension)
    if filters.difficulty:
        stmt = stmt.where(Question.difficulty == filters.difficulty)
    if filters.question_type:
        stmt = stmt.where(Question.question_type == filters.question_type)

    return list(
        db.execute(stmt.order_by(Question.id).limit(limit)).scalars().all()
    )


def list_positions_with_questions(db: Session) -> list[dict]:
    """「有题目的岗位」列表 —— 候选人端刷题筛选项的数据源。

    以 question 表为驱动分组计数，联 position 取名称。分组后只存在有题的分组，
    因此不需要 additional HAVING count(*) > 0。

    **不按 created_by 过滤**：口径必须与 list_practice_candidates 一致，
    否则候选人会看到「列表里有 A，但选了 A 取不到题」这类 UI 与 API 互相打架的情形。
    """
    stmt = (
        select(
            Question.position_id,
            Position.name,
            func.count(Question.id).label("question_count"),
        )
        .join(Position, Position.id == Question.position_id)
        .group_by(Question.position_id, Position.name)
        .order_by(Question.position_id)
    )

    return [
        {"id": row.position_id, "name": row.name, "question_count": row.question_count}
        for row in db.execute(stmt).all()
    ]


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


def get_by_ids(db: Session, question_ids: list[int]) -> dict[int, Question]:
    """批量取题，返回 {id: Question}。"""
    if not question_ids:
        return {}
    stmt = select(Question).where(Question.id.in_(question_ids))
    return {question.id: question for question in db.execute(stmt).scalars().all()}


def get_position_names(db: Session, position_ids: list[int]) -> dict[int, str]:
    """批量取岗位名，返回 {id: name}。

    供 practice 解析会话筛选条件里的岗位名 —— practice 不允许依赖 position 模块
    （plan §1.3），而 question 读 position 是允许的（list_positions_with_questions
    同理）。
    """
    if not position_ids:
        return {}
    stmt = select(Position.id, Position.name).where(Position.id.in_(position_ids))
    return {row[0]: row[1] for row in db.execute(stmt).all()}


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
