"""question 模块业务逻辑。"""

from sqlalchemy.orm import Session

from app.ai.base import GeneratedQuestion
from app.auth import service as auth_service
from app.auth.models import User
from app.core.exceptions import NotFoundError, ValidationError
from app.position import service as position_service
from app.question import repository
from app.question.models import SOURCE_AI, SOURCE_BANK, Question
from app.question.schemas import QuestionCreate, QuestionFilters, QuestionUpdate

DEFAULT_CATEGORY = "通用"
DEFAULT_DIFFICULTY = "medium"


def _get_visible(db: Session, user: User, question_id: int) -> Question:
    question = repository.get_by_id(db, question_id)
    if question is None:
        raise NotFoundError("题目不存在")
    auth_service.ensure_resource_visible(user, question.created_by, "题目")
    return question


def _assert_dimension_belongs(position_dimensions: list[str], dimension: str) -> str:
    """校验维度属于岗位，并返回 strip 后的规范值（精确匹配）。"""
    normalized = dimension.strip()
    for allowed in position_dimensions:
        if allowed == normalized:
            return allowed

    raise ValidationError(
        "该维度不属于岗位的评估维度",
        detail={"dimension": normalized, "allowed": position_dimensions},
    )


def _assert_position_visible(db: Session, user: User, position_id: int):
    """岗位不存在 → 404；不可见 → 403（复用 position 模块的校验）。"""
    return position_service.get_position(db, user, position_id)


# ------------------------------ 创建 ------------------------------


def create_question(db: Session, user: User, data: QuestionCreate) -> Question:
    position = _assert_position_visible(db, user, data.position_id)
    dimension = _assert_dimension_belongs(
        position.evaluation_dimensions, data.dimension
    )

    question = repository.create(
        db,
        position_id=position.id,
        category=data.category or DEFAULT_CATEGORY,
        dimension=dimension,
        content=data.content,
        difficulty=data.difficulty or DEFAULT_DIFFICULTY,
        tags=data.tags,
        source=SOURCE_BANK,  # 来源由服务端决定，客户端不可指定
        created_by=user.id,
    )
    db.commit()
    db.refresh(question)
    return question


# ------------------------------ 查询 ------------------------------


def list_questions(
    db: Session, user: User, filters: QuestionFilters
) -> list[Question]:
    return repository.list_filtered(db, auth_service.scope_owner_id(user), filters)


def get_question(db: Session, user: User, question_id: int) -> Question:
    return _get_visible(db, user, question_id)


# ------------------------------ 更新 ------------------------------


def update_question(
    db: Session, user: User, question_id: int, data: QuestionUpdate
) -> Question:
    question = _get_visible(db, user, question_id)

    # 允许改岗位 —— 但必须重新校验新岗位的可见性与维度合法性
    position = _assert_position_visible(db, user, data.position_id)
    dimension = _assert_dimension_belongs(
        position.evaluation_dimensions, data.dimension
    )

    repository.update(
        db,
        question,
        position_id=position.id,
        category=data.category or DEFAULT_CATEGORY,
        dimension=dimension,
        content=data.content,
        difficulty=data.difficulty or DEFAULT_DIFFICULTY,
        tags=data.tags,  # 全量替换
    )
    db.commit()
    db.refresh(question)
    return question


# ------------------------------ 删除 ------------------------------


def delete_question(db: Session, user: User, question_id: int) -> None:
    question = _get_visible(db, user, question_id)
    repository.delete(db, question)


# ------------------- 对 interview 的供给契约 -------------------


def list_candidates_for_position(
    db: Session, owner_id: int | None, position_id: int
) -> list[Question]:
    """出题候选集：稳定按 id 升序、受 owner_id 约束、不过滤 source。

    抽取算法（round-robin、跳过不合规维度、取满 N 题）全部由 interview 实现。
    """
    return repository.list_by_position(db, owner_id, position_id)


def bulk_create_from_ai(
    db: Session,
    user: User,
    position_id: int,
    items: list[GeneratedQuestion],
) -> list[Question]:
    """把 AI 生成的题目写入题库，source='ai'。

    由 interview 的出题组装在同一事务内调用；失败时随事务一并回滚。
    """
    if not items:
        return []

    questions = repository.bulk_insert(
        db,
        [
            {
                "position_id": position_id,
                "category": item.category or DEFAULT_CATEGORY,
                "dimension": item.dimension,
                "content": item.content,
                "difficulty": item.difficulty or DEFAULT_DIFFICULTY,
                "tags": item.tags,
                "source": SOURCE_AI,
                "created_by": user.id,
            }
            for item in items
        ],
    )
    db.flush()
    return questions
