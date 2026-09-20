"""question 模块业务逻辑。"""

from sqlalchemy.orm import Session

from app.ai.base import GeneratedQuestion
from app.ai.factory import get_provider
from app.auth import service as auth_service
from app.auth.models import User
from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.position import service as position_service
from app.question import repository
from app.question.models import (
    QUESTION_TYPE_SHORT_ANSWER,
    QUESTION_TYPE_SINGLE_CHOICE,
    SOURCE_AI,
    SOURCE_BANK,
    Question,
)
from app.question.schemas import (
    PracticeFilters,
    PracticePositionOut,
    QuestionCreate,
    QuestionFilters,
    QuestionUpdate,
)

DEFAULT_CATEGORY = "通用"
DEFAULT_DIFFICULTY = "medium"

MIN_CHOICE_OPTIONS = 2
MAX_CHOICE_OPTIONS = 10
MAX_OPTION_LENGTH = 200


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


def _clean_text(value: str | None) -> str | None:
    """空串与纯空白一律归一为 None —— 「没填」与「填了空白」不该是两种事实。"""
    if value is None:
        return None
    return value.strip() or None


def _validate_type_payload(
    question_type: str,
    options: list[str],
    reference_answer: str | None,
) -> tuple[list[str], str | None]:
    """按题型校验选项与参考答案，返回规范化后的 (options, reference_answer)。

    放在 service 而不是 schema：报错文案随题型不同（「单选题至少需要 2 个选项」
    与「简答题不应包含选项」是两条不同规则），且与既有的 _assert_dimension_belongs
    是同一风格 —— 跨字段规则集中一处，文案可直接展示给用户。
    """
    cleaned: list[str] = []
    for raw in options:
        item = raw.strip()
        if not item:
            raise ValidationError("选项不能为空")
        if len(item) > MAX_OPTION_LENGTH:
            raise ValidationError(f"单个选项不能超过 {MAX_OPTION_LENGTH} 个字符")
        cleaned.append(item)

    if len(set(cleaned)) != len(cleaned):
        raise ValidationError("选项不能重复")

    answer = _clean_text(reference_answer)

    if question_type == QUESTION_TYPE_SINGLE_CHOICE:
        if len(cleaned) < MIN_CHOICE_OPTIONS:
            raise ValidationError("单选题至少需要 2 个选项")
        if len(cleaned) > MAX_CHOICE_OPTIONS:
            raise ValidationError(f"单选题最多 {MAX_CHOICE_OPTIONS} 个选项")
        if answer is None:
            raise ValidationError("单选题必须提供参考答案")
        if answer not in cleaned:
            # 这条校验是单选题可判分的前提：判分时拿候选人选项与
            # reference_answer 做文本比较，答案不在选项内则永远判不对。
            raise ValidationError(
                "参考答案必须是选项之一", detail={"options": cleaned}
            )
        return cleaned, answer

    # 简答题：不得带选项；参考答案可为空（存量题目都没有）
    if cleaned:
        raise ValidationError("简答题不应包含选项")
    return [], answer


# ------------------------------ 创建 ------------------------------


def create_question(db: Session, user: User, data: QuestionCreate) -> Question:
    position = _assert_position_visible(db, user, data.position_id)
    dimension = _assert_dimension_belongs(
        position.evaluation_dimensions, data.dimension
    )

    question_type = data.question_type or QUESTION_TYPE_SHORT_ANSWER
    options, reference_answer = _validate_type_payload(
        question_type, data.options or [], data.reference_answer
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
        question_type=question_type,
        options=options,
        reference_answer=reference_answer,
        explanation=_clean_text(data.explanation),
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

    # 四个刷题字段的「缺省 = 保持不变」语义。
    #
    # 这是对全量替换语义的一处**有意例外**：它们是在既有实体上新增的字段，
    # 若缺省即视为清空，那么 HR 改一个错别字就会把单选题的选项与答案一起抹掉。
    # 想显式清空时传 null（reference_answer/explanation）或空数组（options）。
    provided = data.model_fields_set

    question_type = (
        data.question_type
        if "question_type" in provided and data.question_type is not None
        else question.question_type
    )
    raw_options = (
        data.options
        if "options" in provided and data.options is not None
        else list(question.options or [])
    )
    raw_reference = (
        data.reference_answer
        if "reference_answer" in provided
        else question.reference_answer
    )
    explanation = (
        _clean_text(data.explanation)
        if "explanation" in provided
        else question.explanation
    )

    # 校验的是「合并后的最终形态」，因此把简答改成单选题而没补选项时，
    # 这里会以 400 拒绝，而不是先落库再暴露不一致。
    options, reference_answer = _validate_type_payload(
        question_type, raw_options, raw_reference
    )

    repository.update(
        db,
        question,
        position_id=position.id,
        category=data.category or DEFAULT_CATEGORY,
        dimension=dimension,
        content=data.content,
        difficulty=data.difficulty or DEFAULT_DIFFICULTY,
        tags=data.tags,
        question_type=question_type,
        options=options,
        reference_answer=reference_answer,
        explanation=explanation,
    )
    db.commit()
    db.refresh(question)
    return question


# ------------------------------ 删除 ------------------------------


def delete_question(db: Session, user: User, question_id: int) -> None:
    question = _get_visible(db, user, question_id)
    repository.delete(db, question)


# -------------------------- AI 补参考答案 --------------------------


def generate_reference_answer(db: Session, user: User, question_id: int) -> Question:
    """调 AI 生成参考答案与解析并写回。

    PRD §4.3 要求「AI 生成后由 HR 确认」——「确认」落在**可编辑**上：生成只是
    把字段写回，HR 随后可用 PUT 改任意内容。不引入「草稿 / 已确认」状态位。
    """
    question = _get_visible(db, user, question_id)

    result = get_provider().generate_reference_answer(
        question.question_type,
        question.content,
        list(question.options or []),
        question.dimension,
    )

    if (
        question.question_type == QUESTION_TYPE_SINGLE_CHOICE
        and result.reference_answer not in (question.options or [])
    ):
        # 不做「吸附到最接近的选项」—— 静默改写会**伪造正确答案**，
        # 比让 HR 看到不一致更危险。因此报错且**不落库**。
        raise BusinessError(
            "AI 生成的答案不在选项中，请手工确认",
            detail={
                "generated": result.reference_answer,
                "options": list(question.options or []),
            },
        )

    repository.update(
        db,
        question,
        reference_answer=result.reference_answer,
        explanation=result.explanation,
    )
    db.commit()
    db.refresh(question)
    return question


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
                # AI 出题链路只产出题干 —— 题型取默认的简答，
                # 选项与参考答案留空由 HR 后续补录或调补答案接口
                "question_type": QUESTION_TYPE_SHORT_ANSWER,
                "options": [],
                "created_by": user.id,
            }
            for item in items
        ],
    )
    db.flush()
    return questions


# ---------------------- 对 practice 的供给契约 ----------------------


def list_practice_questions(
    db: Session, filters: PracticeFilters, limit: int
) -> list[Question]:
    """刷题取题的唯一入口（供 practice 调用）。

    **有意不按 created_by 过滤** —— 候选人取全库题目，理由见
    repository.list_practice_candidates 的说明。这是本项目唯一一处
    对数据隔离的放宽，显式记录在案，避免它以「忘了过滤」的形式存在。
    """
    return repository.list_practice_candidates(db, filters, limit)


def list_practice_positions(db: Session) -> list[PracticePositionOut]:
    """候选人端的刷题岗位筛选项。

    签名里**没有 user** —— 该查询不做任何角色相关的过滤，这是在类型层面
    表达「这里不做隔离」，比收下 user 却在函数体里忽略它更不容易被误解。
    """
    return [
        PracticePositionOut(**row)
        for row in repository.list_positions_with_questions(db)
    ]


def get_practice_supply(db: Session, question_ids: list[int]) -> dict[int, Question]:
    """供 practice 装配候选人视图与取判分依据。

    不接 `user`、不做可见性过滤 —— 与 list_practice_questions 的口径一致
    （候选人取全库题目）。会话开始后题目**不可能被删除**（practice_item 对
    question 是 RESTRICT），因此这里的命中率是有保证的。

    用途有二：① 补上快照未覆盖的展示字段（position_id / category / difficulty /
    tags）；② 判分时读取题库当前的参考答案与解析。题干、选项、维度、题型一律
    仍以**快照**为准，保证历史练习不受题库改动影响。
    """
    return repository.get_by_ids(db, question_ids)


def get_position_names(db: Session, position_ids: list[int]) -> dict[int, str]:
    """批量取岗位名 —— 供 practice 展示会话筛选条件。

    由本模块代取而不是让 practice 直接读 position 表：practice 的依赖白名单里
    没有 position（plan §1.3），而 question 读 position 是允许的。
    """
    return repository.get_position_names(db, position_ids)
