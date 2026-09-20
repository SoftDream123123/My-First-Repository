"""interview 模块业务逻辑：出题组装、回答记录、状态机、作答邀请、在线答题。"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.ai.base import QAPair
from app.ai.factory import get_provider
from app.auth import service as auth_service
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.interview import repository
from app.interview.models import (
    ANSWER_SOURCE_CANDIDATE,
    INVITATION_ACCEPTED,
    INVITATION_EXPIRED,
    INVITATION_PENDING,
    INVITATION_REVOKED,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_EVALUATED,
    STATUS_EVALUATING,
    STATUS_ONGOING,
    Interview,
    InterviewInvitation,
)
from app.interview.schemas import (
    CandidateAnswerCreate,
    CandidateAnswerView,
    CandidateInterviewDetail,
    CandidateInterviewItem,
    CandidateQuestionItem,
    InterviewCreate,
    InterviewDetail,
    InterviewListItem,
    InterviewPatch,
    InvitationAcceptResult,
    InvitationView,
    QuestionItem,
    SubmitResult,
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
                answer_source=answer.source if answer else None,
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
    """HR 手工录入 / 覆盖作答。仅 ongoing 状态允许 —— 保证评估依据不被篡改。

    **不传 source**：候选人交上来的作答被 HR 覆盖后，来源仍是 candidate
    （PRD §5.2 要求保留「最初从哪条通道进来」这一事实）。
    **传 answered_by=user.id**：记录最后修改者。HR 覆盖候选人作答后，
    source='candidate' 而 answered_by=HR，两个事实并存。

    **本方法对候选人交卷**不受影响 —— 交卷锁定只约束候选人通道，
    HR 始终可以修订作答（PRD §4.4）。
    """
    interview = _get_visible(db, user, interview_id)

    if interview.status != STATUS_ONGOING:
        raise BusinessError("当前状态下不可修改回答，请先回退到进行中")

    entry = repository.get_question_entry(db, interview_question_id)
    if entry is None or entry.interview_id != interview.id:
        raise NotFoundError("题目不属于该面试")

    repository.upsert_answer(
        db, interview_question_id, content, answered_by=user.id
    )
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


# ==================== 作答邀请（HR 侧）====================

# 四种失效原因（码不存在 / 已撤销 / 已接受 / 已过期）**共用同一文案**。
# 区分它们等于提供了一个邀请码探测接口（PRD §7 明确「不泄露面试是否存在」）。
# 注意这不适用于「用户名已被占用」「已接受过该面试」—— 它们发生在码校验**之后**，
# 此时码已确定有效，泄露面为零。
_INVITATION_INVALID_MESSAGE = "邀请码无效或已失效"


def _generate_code(db: Session) -> str:
    """secrets.token_urlsafe(16) → 22 个 URL-safe 字符（约 128 位熵）。

    循环查重只为给出友好结果；UNIQUE 索引兜住并发插入。
    """
    while True:
        code = secrets.token_urlsafe(16)
        if repository.get_invitation_by_code(db, code) is None:
            return code


def _derive_status(invitation: InterviewInvitation, now: datetime) -> str:
    """派生 expired —— **不回写**。

    回写等于用一次读操作改变状态，会产生「谁先读谁写库」的隐式副作用。
    「当前时间」由调用方传入而非写死在 SQL 里，保证可测。
    """
    if invitation.status == INVITATION_PENDING and invitation.expires_at < now:
        return INVITATION_EXPIRED
    return invitation.status


def _invitation_view(db: Session, invitation: InterviewInvitation) -> InvitationView:
    username = None
    if invitation.candidate_user_id is not None:
        candidate = auth_service.get_user_by_id(db, invitation.candidate_user_id)
        username = candidate.username if candidate else None

    return InvitationView(
        id=invitation.id,
        interview_id=invitation.interview_id,
        code=invitation.code,
        status=_derive_status(invitation, _now()),
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        candidate_username=username,
        created_at=invitation.created_at,
    )


def create_invitation(db: Session, user: User, interview_id: int) -> InvitationView:
    """生成作答邀请码。

    只在 `ongoing` 面试上可发：面试一旦 completed，作答通道本就不接受写入，
    此时邀请已无意义 —— 提前拦住比让候选人白答一场更友好。
    """
    interview = _get_visible(db, user, interview_id)

    if interview.status != STATUS_ONGOING:
        raise BusinessError(
            "当前状态下不可生成邀请，请先将面试置为进行中",
            detail={"status": interview.status},
        )

    invitation = repository.create_invitation(
        db,
        interview_id=interview.id,
        code=_generate_code(db),
        status=INVITATION_PENDING,
        expires_at=_now() + timedelta(days=get_settings().invitation_expire_days),
        created_by=user.id,
    )
    db.commit()
    db.refresh(invitation)
    return _invitation_view(db, invitation)


def list_invitations(
    db: Session, user: User, interview_id: int
) -> list[InvitationView]:
    _get_visible(db, user, interview_id)
    return [
        _invitation_view(db, invitation)
        for invitation in repository.list_invitations(db, interview_id)
    ]


def revoke_invitation(
    db: Session, user: User, interview_id: int, invitation_id: int
) -> InvitationView:
    """撤销邀请。

      pending  → revoked
      accepted → revoked   ← **有意允许**：这是切断已接受候选人访问的唯一手段，
                              也是「回退后撤销旧邀请再发新邀请」这一恢复路径的前提。
                              置 revoked 后 get_accepted_invitation 立即不再命中，
                              而 candidate_user_id / accepted_at 仍留在该行上，
                              「谁在何时接受了」这一事实没有被抹掉。
      revoked  → 幂等返回，不报错
      已过期的 pending → 允许置 revoked，语义上等于「不再重发」
    """
    _get_visible(db, user, interview_id)

    invitation = repository.get_invitation_by_id(db, invitation_id)
    if invitation is None or invitation.interview_id != interview_id:
        raise NotFoundError("邀请不存在")

    if invitation.status == INVITATION_REVOKED:
        return _invitation_view(db, invitation)  # 幂等

    repository.update_invitation(db, invitation, status=INVITATION_REVOKED)
    db.commit()
    db.refresh(invitation)
    return _invitation_view(db, invitation)


# ==================== 候选人侧 ====================


def get_interview_for_candidate(db: Session, user: User, interview_id: int) -> Interview:
    """候选人可见性判定的**唯一入口**。

    所有候选人端点（含 evaluation 的 /feedback）都必须经此取面试 —— 任何直接
    repository.get_by_id 的写法都会绕过隔离。

    判据是「持有该面试的**有效邀请**」，**不是 created_by**：候选人不是面试的
    创建者（那是 HR），按 created_by 过滤会让候选人看不到自己的任何面试。

    不使用 ensure_resource_visible：它基于 created_by，且对 candidate 角色会
    直接抛错（那是 HR 侧的纵深防御）。
    """
    interview = repository.get_by_id(db, interview_id)
    if interview is None:
        raise NotFoundError("面试不存在")

    invitation = repository.get_accepted_invitation(db, interview_id, user.id)
    if invitation is None:
        raise ForbiddenError("无权限访问该面试")

    return interview


def accept_invitation(
    db: Session, code: str, username: str, password: str
) -> InvitationAcceptResult:
    """凭邀请码激活并绑定面试。

    账号创建**委托 auth**（auth_service.create_candidate_account），不在本模块
    复制「用户名唯一性 / 密码哈希 / 角色约束」规则。

    刻意不接 `user` 参数：绑定到哪个账号由请求体里的 username 决定（§5.3），
    与调用者身份无关。角色守卫在 router 层。签名里放一个不用的 user 会让人
    误以为「绑定的是当前登录者」。
    """
    invitation = repository.get_invitation_by_code(db, code)

    if (
        invitation is None
        or invitation.status != INVITATION_PENDING
        or invitation.expires_at < _now()
    ):
        raise BusinessError(_INVITATION_INVALID_MESSAGE)

    candidate = auth_service.create_candidate_account(db, username, password)

    # 否则同一候选人可用第二条码重复接受同一面试，产生两条绑定记录，
    # 候选人端的面试列表会出现重复项。
    if (
        repository.get_accepted_invitation(
            db, invitation.interview_id, candidate.id
        )
        is not None
    ):
        raise BusinessError("你已接受过该面试的邀请")

    repository.update_invitation(
        db,
        invitation,
        candidate_user_id=candidate.id,
        accepted_at=_now(),
        status=INVITATION_ACCEPTED,
    )
    db.commit()
    db.refresh(invitation)

    interview = repository.get_by_id(db, invitation.interview_id)
    position = repository.get_position(db, interview.position_id)
    question_count = len(repository.list_questions(db, interview.id))

    return InvitationAcceptResult(
        interview_id=interview.id,
        interview={
            "id": interview.id,
            "position_name": position.name if position else "",
            "candidate_name": interview.candidate_name,
            "status": interview.status,
            "question_count": question_count,
        },
    )


def list_my_interviews(db: Session, user: User) -> list[CandidateInterviewItem]:
    """我参与的面试（仅 accepted 且绑定本人）。"""
    rows = repository.list_accepted_interviews_for_candidate(db, user.id)
    interview_ids = [interview.id for interview, _ in rows]

    question_counts = repository.count_questions(db, interview_ids)
    answer_counts = repository.count_answers(db, interview_ids)

    return [
        CandidateInterviewItem(
            id=interview.id,
            position_name=position_name,
            status=interview.status,
            question_count=question_counts.get(interview.id, 0),
            answered_count=answer_counts.get(interview.id, 0),
            submitted=repository.get_submitted_at(db, interview.id) is not None,
            created_at=interview.created_at,
        )
        for interview, position_name in rows
    ]


def get_candidate_interview_detail(
    db: Session, user: User, interview_id: int
) -> CandidateInterviewDetail:
    """面试详情 —— **只含题目与我自己的作答**。

    content / dimension 取自快照，因此天然不含参考答案
    （content_snapshot 只快照题干），这是既有设计带来的安全收益。
    """
    interview = get_interview_for_candidate(db, user, interview_id)
    position = repository.get_position(db, interview.position_id)

    answers = {
        answer.interview_question_id: answer
        for answer in repository.list_answers(db, interview.id)
    }
    submitted_at = repository.get_submitted_at(db, interview.id)

    questions = [
        CandidateQuestionItem(
            interview_question_id=entry.id,
            seq=entry.seq,
            content=entry.content_snapshot,
            dimension=entry.dimension_snapshot,
            my_answer=answers[entry.id].content if entry.id in answers else None,
        )
        for entry in repository.list_questions(db, interview.id)
    ]

    return CandidateInterviewDetail(
        id=interview.id,
        position_name=position.name if position else "",
        status=interview.status,
        created_at=interview.created_at,
        submitted=submitted_at is not None,
        submitted_at=submitted_at,
        questions=questions,
    )


def save_candidate_answer(
    db: Session, user: User, interview_id: int, data: CandidateAnswerCreate
) -> CandidateAnswerView:
    """候选人在线作答（仅 ongoing 且未交卷时允许）。

    与 HR 通道共用同一条 `ongoing` 限定 —— 这不是巧合：**两条通道写的是同一份
    数据**，对数据的写入约束自然应当一致。

    source / answered_by 由服务端写入，请求体不接受（与 QuestionCreate 不接收
    source 同一手法）。
    """
    interview = get_interview_for_candidate(db, user, interview_id)

    if interview.status != STATUS_ONGOING:
        raise BusinessError("当前状态下不可作答")

    if repository.get_submitted_at(db, interview.id) is not None:
        raise BusinessError("已交卷，不可修改作答")

    entry = repository.get_question_entry(db, data.interview_question_id)
    if entry is None or entry.interview_id != interview.id:
        raise NotFoundError("题目不属于该面试")

    answer = repository.upsert_answer(
        db,
        data.interview_question_id,
        data.content,
        source=ANSWER_SOURCE_CANDIDATE,
        answered_by=user.id,
    )
    db.commit()
    db.refresh(answer)

    return CandidateAnswerView(
        interview_question_id=answer.interview_question_id,
        content=answer.content,
        submitted_at=answer.submitted_at,
    )


def _count_non_empty_answers(db: Session, interview_id: int) -> int:
    """实际有内容的作答数 —— **不含交卷时补的空串**。

    它回答的是「候选人答了几题」，而不是「有几条记录」。
    """
    return sum(
        1
        for answer in repository.list_answers(db, interview_id)
        if answer.content.strip() != ""
    )


def submit_interview(db: Session, user: User, interview_id: int) -> SubmitResult:
    """交卷：给全部题写 submitted_at（未作答的补空串），候选人侧锁定。

    **幂等检查先于状态检查**：已交卷后 HR 可能已把面试推进到 completed，
    若先判状态会返回 409，让前端重试看到一个自相矛盾的错误。

    **不改面试状态** —— PRD §5.1 的明确取舍，HR 仍需手动 /complete。
    """
    interview = get_interview_for_candidate(db, user, interview_id)

    existing = repository.get_submitted_at(db, interview.id)
    if existing is not None:
        return SubmitResult(
            interview_id=interview.id,
            submitted_at=existing,  # 返回**首次**交卷时刻，不刷新它
            answered_count=_count_non_empty_answers(db, interview.id),
        )

    if interview.status != STATUS_ONGOING:
        raise BusinessError("当前状态下不可交卷")

    submitted_at = _now()
    entry_ids = [e.id for e in repository.list_questions(db, interview.id)]

    repository.bulk_upsert_empty_answers(
        db, entry_ids, submitted_at, user.id
    )
    repository.mark_all_submitted(db, interview.id, submitted_at)
    db.commit()

    # 返回**落库后**的值，而不是内存里的 submitted_at：
    # MySQL 的 DATETIME 列不带小数秒，写进去的值会被取整。若直接返回内存值，
    # 首次响应的时刻与后续幂等重试读到的时刻会差一个亚秒，看起来像「不幂等」。
    stored = repository.get_submitted_at(db, interview.id) or submitted_at

    return SubmitResult(
        interview_id=interview.id,
        submitted_at=stored,
        answered_count=_count_non_empty_answers(db, interview.id),
    )
