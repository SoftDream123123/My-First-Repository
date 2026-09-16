"""interview 模块业务逻辑：出题组装、回答记录、状态机。"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.base import QAPair
from app.ai.factory import get_provider
from app.auth import service as auth_service
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import BusinessError, NotFoundError
from app.interview import repository
from app.interview.models import (
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_EVALUATED,
    STATUS_EVALUATING,
    STATUS_ONGOING,
    Interview,
)
from app.interview.schemas import (
    InterviewCreate,
    InterviewDetail,
    InterviewListItem,
    InterviewPatch,
    QuestionItem,
)
from app.position import service as position_service
from app.question import service as question_service

# ------------------------------ 状态机 ------------------------------

_STATUS_LABELS = {
    STATUS_DRAFT: "草稿",
    STATUS_ONGOING: "进行中",
    STATUS_COMPLETED: "已完成",
    STATUS_EVALUATING: "评估中",
    STATUS_EVALUATED: "已评估",
}

# 状态迁移表 —— 未列出的迁移一律拒绝。
# 说明：
#   evaluating → completed  是 PRD §7「AI 失败回退 completed」的必要条件
#   evaluated  → evaluating 落实 PRD §5.1 的「可重新评估」
#   evaluated  → ongoing    与 completed → ongoing 同源（回退修改回答）
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_ONGOING},
    STATUS_ONGOING: {STATUS_COMPLETED},
    STATUS_COMPLETED: {STATUS_EVALUATING, STATUS_ONGOING},
    STATUS_EVALUATING: {STATUS_EVALUATED, STATUS_COMPLETED},
    STATUS_EVALUATED: {STATUS_EVALUATING, STATUS_ONGOING},
}


def _assert_transition(current: str, target: str) -> None:
    """所有状态变更的唯一入口 —— 不允许任何地方直接赋值 status。"""
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise BusinessError(
            f"不允许从「{_STATUS_LABELS.get(current, current)}」"
            f"迁移到「{_STATUS_LABELS.get(target, target)}」",
            detail={"from": current, "to": target},
        )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class EvaluationItem:
    """供 evaluation 使用的一条面试题记录（比 QAPair 多带 id 与 seq）。"""

    interview_question_id: int
    seq: int
    dimension: str
    question: str
    answer: str | None


# ---------------------------- 读取与权限 ----------------------------


def _get_visible(db: Session, user: User, interview_id: int) -> Interview:
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")
    auth_service.ensure_resource_visible(user, interview.created_by, "面试")
    return interview


def _build_questions_and_answers(
    db: Session, interview_id: int
) -> list[QuestionItem]:
    entries = repository.list_questions(db, interview_id)
    answers = {a.interview_question_id: a for a in repository.list_answers(db, interview_id)}

    items: list[QuestionItem] = []
    for entry in entries:
        answer = answers.get(entry.id)
        items.append(
            QuestionItem(
                interview_question_id=entry.id,
                seq=entry.seq,
                content=entry.content_snapshot,
                dimension=entry.dimension_snapshot,
                source=entry.source_snapshot,
                answer=answer.content if answer else None,
                recorded_at=answer.recorded_at if answer else None,
            )
        )
    return items


def _detail(db: Session, interview: Interview) -> InterviewDetail:
    position = repository.get_position(db, interview.position_id)
    questions = _build_questions_and_answers(db, interview.id)

    return InterviewDetail(
        id=interview.id,
        position_id=interview.position_id,
        position_name=position.name if position else "",
        candidate_name=interview.candidate_name,
        candidate_contact=interview.candidate_contact,
        status=interview.status,
        created_at=interview.created_at,
        completed_at=interview.completed_at,
        question_count=len(questions),
        answered_count=sum(1 for q in questions if q.answer not in (None, "")),
        jd=position.jd if position else "",
        evaluation_dimensions=list(position.evaluation_dimensions) if position else [],
        questions=questions,
    )


def get_interview(db: Session, user: User, interview_id: int) -> InterviewDetail:
    return _detail(db, _get_visible(db, user, interview_id))


def list_interviews(db: Session, user: User) -> list[InterviewListItem]:
    rows = repository.list_by_owner(db, auth_service.scope_owner_id(user))
    interview_ids = [interview.id for interview, _ in rows]

    question_counts = repository.count_questions(db, interview_ids)
    answer_counts = repository.count_answers(db, interview_ids)

    return [
        InterviewListItem(
            id=interview.id,
            position_id=interview.position_id,
            position_name=position_name,
            candidate_name=interview.candidate_name,
            candidate_contact=interview.candidate_contact,
            status=interview.status,
            created_at=interview.created_at,
            completed_at=interview.completed_at,
            question_count=question_counts.get(interview.id, 0),
            answered_count=answer_counts.get(interview.id, 0),
        )
        for interview, position_name in rows
    ]


# ---------------------------- 出题组装 ----------------------------


def _filter_valid_candidates(candidates, dimensions: list[str]):
    """剔除 dimension 已不在岗位维度列表中的题目（岗位维度改过之后的历史题）。"""
    return [q for q in candidates if q.dimension in dimensions]


def _round_robin_pick(groups: dict[str, list], dimensions: list[str], count: int):
    """按维度轮询抽取，保证各维度题目数尽量平均。

    组内已按 id 升序 —— 抽取结果完全确定，便于测试断言。
    """
    cursors = {dim: 0 for dim in dimensions}
    picked: list = []

    while len(picked) < count:
        progressed = False
        for dim in dimensions:
            if len(picked) >= count:
                break
            index = cursors[dim]
            if index < len(groups[dim]):
                picked.append(groups[dim][index])
                cursors[dim] = index + 1
                progressed = True
        if not progressed:  # 所有维度都已抽空
            break

    return picked


def _assemble_questions(
    db: Session, user: User, position, interview: Interview
) -> None:
    """题库抽 N 题 + AI 补 M 题，合并编号并写快照。

    need_ai = M + (N - K) —— 保证总题数恒为 N + M，题库不足时由 AI 补足差额。
    """
    settings = get_settings()
    want_from_bank = settings.question_count_from_bank
    want_from_ai = settings.question_count_from_ai

    dimensions = list(position.evaluation_dimensions)
    if not dimensions:
        raise BusinessError("岗位未定义评估维度，无法出题")

    candidates = question_service.list_candidates_for_position(
        db, user.id, position.id
    )
    valid = _filter_valid_candidates(candidates, dimensions)

    groups: dict[str, list] = {dim: [] for dim in dimensions}
    for question in valid:  # 已按 id 升序
        groups[question.dimension].append(question)

    picked = _round_robin_pick(groups, dimensions, want_from_bank)
    need_ai = want_from_ai + (want_from_bank - len(picked))

    ai_questions = []
    if need_ai > 0:
        generated = get_provider().generate_questions(
            position_name=position.name,
            jd=position.jd,
            dims=dimensions,
            existing_contents=[q.content for q in picked],
            count=need_ai,
        )
        # 防御：AI 返回的维度若不在岗位维度内，丢弃该条
        generated = [g for g in generated if g.dimension in dimensions]
        ai_questions = question_service.bulk_create_from_ai(
            db, user, position.id, generated
        )

    items: list[dict] = []
    seq = 1

    for question in picked:  # 题库题在前，按抽取顺序
        items.append(
            {
                "interview_id": interview.id,
                "question_id": question.id,
                "seq": seq,
                "content_snapshot": question.content,
                "dimension_snapshot": question.dimension,
                "source_snapshot": question.source,
            }
        )
        seq += 1

    for question in ai_questions:  # AI 题在后
        items.append(
            {
                "interview_id": interview.id,
                "question_id": question.id,
                "seq": seq,
                "content_snapshot": question.content,
                "dimension_snapshot": question.dimension,
                "source_snapshot": question.source,
            }
        )
        seq += 1

    repository.create_questions(db, items)


def create_interview(
    db: Session, user: User, data: InterviewCreate
) -> InterviewDetail:
    """单事务：建面试 + 出题组装 + 置 ongoing。

    AI 出题失败时整体回滚 —— 要么面试创建成功且题目齐备，要么什么都没发生。
    """
    position = position_service.get_position(db, user, data.position_id)

    try:
        interview = repository.create_interview(
            db,
            position_id=position.id,
            candidate_name=data.candidate_name,
            contact=data.candidate_contact,
            created_by=user.id,
        )

        _assemble_questions(db, user, position, interview)

        _assert_transition(STATUS_DRAFT, STATUS_ONGOING)
        interview.status = STATUS_ONGOING

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(interview)
    return _detail(db, interview)


# ---------------------------- 回答记录 ----------------------------


def save_answer(
    db: Session,
    user: User,
    interview_id: int,
    interview_question_id: int,
    content: str,
) -> QuestionItem:
    """保存/更新回答。仅 ongoing 状态允许 —— 保证评估依据不被篡改。"""
    interview = _get_visible(db, user, interview_id)

    if interview.status != STATUS_ONGOING:
        raise BusinessError("当前状态下不可修改回答，请先回退到进行中")

    entry = repository.get_question_entry(db, interview_question_id)
    if entry is None or entry.interview_id != interview.id:
        raise NotFoundError("题目不属于该面试")

    repository.upsert_answer(db, interview_question_id, content)
    db.commit()

    for item in _build_questions_and_answers(db, interview.id):
        if item.interview_question_id == interview_question_id:
            return item

    raise NotFoundError("题目不属于该面试")  # pragma: no cover - 理论不可达


# ---------------------------- 状态迁移端点 ----------------------------


def _transition(db: Session, user: User, interview_id: int, target: str) -> InterviewDetail:
    interview = _get_visible(db, user, interview_id)
    _assert_transition(interview.status, target)

    interview.status = target
    if target == STATUS_COMPLETED:
        interview.completed_at = _now()
    elif target == STATUS_ONGOING:
        interview.completed_at = None

    db.commit()
    db.refresh(interview)
    return _detail(db, interview)


def complete_interview(db: Session, user: User, interview_id: int) -> InterviewDetail:
    return _transition(db, user, interview_id, STATUS_COMPLETED)


def rollback_interview(db: Session, user: User, interview_id: int) -> InterviewDetail:
    return _transition(db, user, interview_id, STATUS_ONGOING)


def update_candidate(
    db: Session, user: User, interview_id: int, data: InterviewPatch
) -> InterviewDetail:
    """只改候选人信息；evaluating / evaluated 下拒绝。"""
    interview = _get_visible(db, user, interview_id)

    if interview.status in (STATUS_EVALUATING, STATUS_EVALUATED):
        raise BusinessError("评估中或已评估的面试不可修改候选人信息")

    fields: dict[str, object] = {}
    if data.candidate_name is not None:
        fields["candidate_name"] = data.candidate_name
    if "candidate_contact" in data.model_fields_set:
        fields["candidate_contact"] = data.candidate_contact

    if fields:
        repository.update_interview(db, interview, **fields)
        db.commit()
        db.refresh(interview)

    return _detail(db, interview)


# ------------------- 对 evaluation 的供给契约 -------------------


def get_items_for_evaluation(db: Session, interview_id: int) -> list[EvaluationItem]:
    """evaluation 读取面试数据的完整契约。

    维度与题干取自**快照**；未作答的 answer 为 None（而非空串）。
    比 QAPair 多带 interview_question_id 与 seq —— SSE 事件载荷需要它们。
    """
    entries = repository.list_questions(db, interview_id)
    answers = repository.list_answers(db, interview_id)
    by_entry = {a.interview_question_id: a.content for a in answers}

    items: list[EvaluationItem] = []
    for entry in entries:
        content = by_entry.get(entry.id)
        if content is not None and content.strip() == "":
            content = None  # 空串表示未作答
        items.append(
            EvaluationItem(
                interview_question_id=entry.id,
                seq=entry.seq,
                dimension=entry.dimension_snapshot,
                question=entry.content_snapshot,
                answer=content,
            )
        )
    return items


def get_answers_for_evaluation(db: Session, interview_id: int) -> list[QAPair]:
    """QAPair 视图 —— 供 ai Provider 使用。"""
    return [
        QAPair(dimension=item.dimension, question=item.question, answer=item.answer)
        for item in get_items_for_evaluation(db, interview_id)
    ]


def get_position_id(db: Session, interview_id: int) -> int:
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")
    return interview.position_id


def get_evaluation_dimensions(db: Session, interview_id: int) -> list[str]:
    """取岗位**当前**的评估维度 —— 维度是「按什么标准评」，权威定义在岗位。"""
    position = repository.get_position(db, get_position_id(db, interview_id))
    return list(position.evaluation_dimensions) if position else []


def begin_evaluation(db: Session, interview_id: int) -> None:
    """进入评估：completed / evaluated → evaluating。

    幂等 —— 已在 evaluating 则直接返回。这让 evaluate_interview 可以独立调用，
    而不必依赖调用方先做过状态迁移。
    """
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")
    if interview.status == STATUS_EVALUATING:
        return

    _assert_transition(interview.status, STATUS_EVALUATING)
    interview.status = STATUS_EVALUATING
    db.commit()


def transition_to_evaluating(db: Session, interview_id: int) -> None:
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")
    _assert_transition(interview.status, STATUS_EVALUATING)
    interview.status = STATUS_EVALUATING
    db.commit()


def transition_to_evaluated(db: Session, interview_id: int) -> None:
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")
    _assert_transition(interview.status, STATUS_EVALUATED)
    interview.status = STATUS_EVALUATED
    db.commit()


def transition_back_to_completed(db: Session, interview_id: int) -> None:
    """评估失败时回退（PRD §7）—— 让用户可立即重新触发。"""
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")
    _assert_transition(interview.status, STATUS_COMPLETED)
    interview.status = STATUS_COMPLETED
    db.commit()
