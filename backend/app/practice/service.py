"""practice 模块业务逻辑：会话编排、判分分支、降级、派生统计、进程内限流。

**本模块不 import interview** —— 刷题与真实面试完全解耦（PRD §9）。
"""

import logging
import time
from collections import deque
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.base import QUESTION_TYPE_SINGLE_CHOICE, SCORE_MAX, SCORE_MIN
from app.ai.factory import get_provider
from app.auth import service as auth_service
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import (
    AIProviderError,
    BusinessError,
    NotFoundError,
    ValidationError,
)
from app.practice import repository
from app.practice.models import (
    STATUS_FINISHED,
    STATUS_ONGOING,
    PracticeItem,
    PracticeSession,
)
from app.practice.schemas import (
    DimensionAccuracy,
    DimensionStats,
    PracticeItemOut,
    PracticeItemResult,
    PracticeItemSubmit,
    PracticeProgress,
    PracticeSessionCreate,
    PracticeSessionDetail,
    PracticeSessionListItem,
    PracticeSessionOut,
    PracticeSessionSummary,
    PracticeStats,
    TypeStats,
    WrongBookItem,
)
from app.question import service as question_service
from app.question.schemas import PracticeFilters, PracticeQuestionOut

logger = logging.getLogger(__name__)

# 错题本的分页缺省与硬上限（plan §4.2）
WRONG_BOOK_DEFAULT_LIMIT = 50
WRONG_BOOK_MAX_LIMIT = 200

# 会话列表的分页缺省（上限由 PRACTICE_SESSION_LIST_MAX 配置提供）
SESSION_LIST_DEFAULT_LIMIT = 20

# 限流窗口长度（秒）。模块级常量便于测试缩短它而不必真的等 60 秒。
RATE_WINDOW_SECONDS = 60

# 进程内滑动窗口：{candidate_user_id: deque[单调时间戳]}。
#
# PRD §2 禁止引入 Redis 等中间件，故用进程内计数。**代价是必须单进程部署**
# （--workers 1）：多进程下各进程计数独立，限流会失效。与 SSE 的运行注册表
# 是同一根因。进程重启后计数清零，可接受 —— 限流是防误用与脚本刷题，不是计费。
_rate_windows: dict[int, deque[float]] = {}


def reset_rate_limit() -> None:
    """清空限流窗口。

    测试用。限流状态是**进程内模块级**的，不会随数据库清空而重置 ——
    不重置会跨用例累积，整套跑时随机触发 409。
    """
    _rate_windows.clear()


def _check_rate_limit(user: User) -> None:
    """滑动窗口限流，只对**计分动作**生效（开始练习 / 提交作答 / 重判）。

    读接口不计：浏览题目与历史不该消耗配额。
    """
    limit = get_settings().practice_rate_limit_per_minute
    if limit <= 0:
        return

    now = time.monotonic()
    bucket = _rate_windows.setdefault(user.id, deque())

    # 顺带剔除窗口外的旧时间戳，无需后台清理线程
    while bucket and now - bucket[0] > RATE_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= limit:
        raise BusinessError("操作过于频繁，请稍后再试")

    bucket.append(now)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _accuracy(correct: int, denominator: int) -> float | None:
    """正确率。分母为 0 → None（而不是除零或 0.0）。"""
    if not denominator:
        return None
    return round(correct / denominator, 4)


def _get_owned_session(db: Session, user: User, session_id: int) -> PracticeSession:
    """归属校验。

    用 `ensure_owner_match` 而**不是** `ensure_resource_visible` —— 后者基于
    created_by 且对 candidate 角色直接抛错（那是 HR 侧的纵深防御），
    候选人连自己的练习都会读不到。
    """
    session = repository.get_session_by_id(db, session_id)
    if session is None:
        raise NotFoundError("练习不存在")
    auth_service.ensure_owner_match(user, session.candidate_user_id, "练习")
    return session


def _question_view(item: PracticeItem, question) -> dict:
    """装配候选人可见的题目视图（PracticeQuestionOut）。

    题干 / 选项 / 维度 / 题型取**快照**；position_id / category / difficulty /
    tags 快照里没有，取题库当前值（它们不参与判分，也不涉及答案泄露）。
    """
    return PracticeQuestionOut(
        id=item.question_id,
        position_id=question.position_id if question else 0,
        category=question.category if question else "",
        dimension=item.dimension_snapshot,
        difficulty=question.difficulty if question else "",
        content=item.content_snapshot,
        question_type=item.question_type,
        options=list(item.options_snapshot or []),
        tags=list(question.tags or []) if question else [],
    ).model_dump()


def _item_view(item: PracticeItem, question) -> PracticeItemOut:
    submitted = item.user_answer is not None
    return PracticeItemOut(
        item_id=item.id,
        seq=item.seq,
        question=_question_view(item, question),
        user_answer=item.user_answer,
        is_correct=item.is_correct,
        score=float(item.score) if item.score is not None else None,
        # 「提交后展示」规则的落点：未提交就不下发解析与参考答案。
        # 不能靠「前端不显示」替代 —— 不下发就是不下发。
        explanation=item.explanation if submitted else None,
        reference_answer=item.reference_answer_snapshot if submitted else None,
    )


def _session_out(session: PracticeSession) -> PracticeSessionOut:
    return PracticeSessionOut(
        id=session.id,
        status=session.status,
        position_id=session.position_id,
        category=session.category,
        dimension=session.dimension,
        difficulty=session.difficulty,
        question_type=session.question_type,
        total=session.total,
        answered_count=session.answered_count,
        correct_count=session.correct_count,
        started_at=session.started_at,
        finished_at=session.finished_at,
    )


def _session_detail(db: Session, session: PracticeSession) -> PracticeSessionDetail:
    items = repository.list_items(db, session.id)
    supply = question_service.get_practice_supply(db, [i.question_id for i in items])
    return PracticeSessionDetail(
        session=_session_out(session),
        items=[_item_view(item, supply.get(item.question_id)) for item in items],
    )


# ---------------------------- 取题预览 ----------------------------


def preview_questions(
    db: Session, user: User, filters: PracticeFilters, limit: int | None
) -> list[dict]:
    """无状态预览：有哪些题可练（不含答案）。

    预览接口存在的意义是让前端在开始前显示「符合条件的题量」。它不创建会话、
    不写快照，因此也不计入限流。
    """
    settings = get_settings()
    size = limit if limit is not None else settings.practice_session_size_default
    if size > settings.practice_session_size_max:
        raise ValidationError(
            f"size 不能超过 {settings.practice_session_size_max}"
        )

    questions = question_service.list_practice_questions(db, filters, size)
    return [
        PracticeQuestionOut(
            id=question.id,
            position_id=question.position_id,
            category=question.category,
            dimension=question.dimension,
            difficulty=question.difficulty,
            content=question.content,
            question_type=question.question_type,
            options=list(question.options or []),
            tags=list(question.tags or []),
        ).model_dump()
        for question in questions
    ]


# ---------------------------- 开始练习 ----------------------------


def start_session(
    db: Session, user: User, data: PracticeSessionCreate
) -> PracticeSessionDetail:
    """取题 → 建会话 → 建待答项（写满快照）。"""
    _check_rate_limit(user)

    settings = get_settings()
    size = (
        data.size
        if data.size is not None
        else settings.practice_session_size_default
    )
    if size > settings.practice_session_size_max:
        # 超上限直接报错，**不静默截断** —— 静默截断会让前端显示的题量
        # 与实际不符，而候选人无从察觉
        raise ValidationError(
            f"size 不能超过 {settings.practice_session_size_max}"
        )

    filters = PracticeFilters(
        position_id=data.position_id,
        category=data.category,
        dimension=data.dimension,
        difficulty=data.difficulty,
        question_type=data.question_type,
    )
    questions = question_service.list_practice_questions(db, filters, size)

    if not questions:
        # 不建空会话：它对候选人毫无价值，且会污染「练习次数」统计
        raise BusinessError("没有符合条件的题目，请调整筛选条件")

    session = repository.create_session(
        db,
        candidate_user_id=user.id,
        position_id=data.position_id,
        category=data.category,
        dimension=data.dimension,
        difficulty=data.difficulty,
        question_type=data.question_type,
        status=STATUS_ONGOING,
        total=len(questions),
        answered_count=0,
        correct_count=0,
    )

    # 快照在会话开始时写满 —— 题库后续删改不影响进行中与历史练习。
    # 题数不足时按实际数量建会话，不补齐、不报错。
    repository.create_items(
        db,
        [
            {
                "session_id": session.id,
                "question_id": question.id,
                "seq": index,
                "content_snapshot": question.content,
                "options_snapshot": list(question.options or []),
                "reference_answer_snapshot": question.reference_answer,
                "dimension_snapshot": question.dimension,
                "question_type": question.question_type,
            }
            for index, question in enumerate(questions, start=1)
        ],
    )

    db.commit()
    db.refresh(session)
    return _session_detail(db, session)


def get_session(db: Session, user: User, session_id: int) -> PracticeSessionDetail:
    return _session_detail(db, _get_owned_session(db, user, session_id))


# ---------------------------- 判分（核心） ----------------------------


def _resolve_reference(db: Session, item: PracticeItem, question):
    """参考答案：**快照优先，为空则读题库当前值并回填快照**。

    为什么回退：会话开始时 HR 可能还没补参考答案（存量题、或还没点「AI 补答案」）。
    若死守空快照，这些题**永远判不了分**。回填保证后续一致性，也让
    「HR 补录答案后重新刷同一题」能正常判分。
    """
    reference = (item.reference_answer_snapshot or "").strip()
    if reference:
        return item.reference_answer_snapshot

    if question is None:
        return None

    current = (question.reference_answer or "").strip()
    if current:
        repository.update_item(db, item, reference_answer_snapshot=current)
        return current
    return None


def _grade(
    db: Session, item: PracticeItem, user_answer: str
) -> tuple[bool | None, float | None, str | None]:
    """判分分支。返回 (is_correct, score, explanation)。

    四条分支的职责划分很关键：
      空作答        → 判 0 分，**不调 AI**（省一次无意义调用）
      单选          → 本地比对，**不调 AI**（PRD §4.7 明确要求）
      简答无参考答案 → **不调 AI**，标记未判分（provider 对空答案会抛错）
      简答有参考答案 → 调 AI，失败降级为未判分
    """
    text = (user_answer or "").strip()

    supply = question_service.get_practice_supply(db, [item.question_id])
    question = supply.get(item.question_id)
    reference = _resolve_reference(db, item, question)

    # a) 空作答
    if not text:
        return False, SCORE_MIN, "未作答"

    # b) 单选题：本地规则判分
    if item.question_type == QUESTION_TYPE_SINGLE_CHOICE:
        expected = (reference or "").strip()
        is_correct = text == expected
        # 解析取题库的 explanation（可能为 NULL）—— 单选不消耗 AI，
        # 因此没有 AI 生成的解析可返回
        return (
            is_correct,
            SCORE_MAX if is_correct else SCORE_MIN,
            question.explanation if question else None,
        )

    # d) 简答但无参考答案：在 service 层提前判断，比让 provider 抛错再降级更清晰
    if not (reference or "").strip():
        return None, None, "该题暂无参考答案，本次不判分"

    # c) 简答：调 AI 判分
    try:
        result = get_provider().grade_practice_answer(
            item.question_type, item.content_snapshot, reference, text
        )
    except AIProviderError:
        # PRD §7：**不阻塞作答**。作答已成功保存，报 5xx 会与事实不符
        # （前端会以为提交失败而重试，而数据其实已落库）。
        logger.warning(
            "刷题判分失败，标记为未判分：session=%s item=%s",
            item.session_id,
            item.id,
        )
        return None, None, "AI 判分暂时不可用，本题稍后可重判"

    return result.is_correct, result.score, result.explanation


def _apply_grade(
    db: Session,
    session: PracticeSession,
    item: PracticeItem,
    user_answer: str,
) -> PracticeItemResult:
    is_correct, score, explanation = _grade(db, item, user_answer)

    repository.update_item(
        db,
        item,
        user_answer=user_answer,
        is_correct=is_correct,
        score=score,
        explanation=explanation,
        answered_at=_now(),
    )
    answered, correct = repository.recount(db, session.id)
    repository.update_session(
        db, session, answered_count=answered, correct_count=correct
    )
    db.commit()
    db.refresh(item)
    db.refresh(session)

    return _item_result(db, session, item)


def _item_result(
    db: Session, session: PracticeSession, item: PracticeItem
) -> PracticeItemResult:
    """判分结果视图。

    参考答案按题型分列：单选给 correct_answer，简答给 reference_answer。
    这样前端不必知道题型就能取到该展示的那一个。
    """
    is_single_choice = item.question_type == QUESTION_TYPE_SINGLE_CHOICE
    answer = item.reference_answer_snapshot
    if item.is_correct is None:
        answer = None  # 未判分时不透露答案

    return PracticeItemResult(
        item_id=item.id,
        seq=item.seq,
        user_answer=item.user_answer or "",
        is_correct=item.is_correct,
        score=float(item.score) if item.score is not None else None,
        correct_answer=answer if (is_single_choice and item.is_correct is not None) else None,
        reference_answer=None if is_single_choice else answer,
        explanation=item.explanation,
        progress=PracticeProgress(
            answered_count=session.answered_count,
            correct_count=session.correct_count,
            total=session.total,
        ),
    )


def submit_item(
    db: Session, user: User, session_id: int, data: PracticeItemSubmit
) -> PracticeItemResult:
    _check_rate_limit(user)

    session = _get_owned_session(db, user, session_id)
    if session.status != STATUS_ONGOING:
        raise BusinessError("本次练习已结束，不可继续作答")

    item = repository.get_item_by_id(db, data.item_id)
    if item is None or item.session_id != session.id:
        raise NotFoundError("题目不属于该练习")

    return _apply_grade(db, session, item, data.user_answer)


def rescore_item(db: Session, user: User, item_id: int) -> PracticeItemResult:
    """按题重判 —— 供未判分项补判（PRD §7「可后续重判」）。

    **仅允许重判未判分项**：已判分的项重判会改变正确答案与分数，等于允许刷分。
    已判分时幂等返回既有结果，且不重复调用 provider。
    """
    _check_rate_limit(user)

    item = repository.get_item_by_id(db, item_id)
    if item is None:
        raise NotFoundError("题目不属于该练习")

    session = repository.get_session_by_id(db, item.session_id)
    if session is None:
        raise NotFoundError("练习不存在")
    auth_service.ensure_owner_match(user, session.candidate_user_id, "练习")

    if item.is_correct is not None:
        return _item_result(db, session, item)  # 幂等：不重复判分

    if item.user_answer is None:
        raise BusinessError("该题尚未提交作答，无法重判")

    # 重走判分：重新解析参考答案、重新判分、重算计数
    is_correct, score, explanation = _grade(db, item, item.user_answer)
    repository.update_item(
        db, item, is_correct=is_correct, score=score, explanation=explanation
    )
    answered, correct = repository.recount(db, session.id)
    repository.update_session(
        db, session, answered_count=answered, correct_count=correct
    )
    db.commit()
    db.refresh(item)
    db.refresh(session)

    return _item_result(db, session, item)


# ---------------------------- 结束练习 ----------------------------


def _summary(db: Session, session: PracticeSession) -> PracticeSessionSummary:
    by_dimension = [
        DimensionAccuracy(
            dimension=row["key"],
            answered=row["answered"],
            correct=row["correct"],
            accuracy=_accuracy(row["correct"], row["answered"]),
        )
        for row in repository.session_dimension_stats(db, session.id)
    ]

    return PracticeSessionSummary(
        session_id=session.id,
        status=session.status,
        total=session.total,
        answered_count=session.answered_count,
        correct_count=session.correct_count,
        unscored_count=repository.count_unscored(db, session.id),
        accuracy=_accuracy(session.correct_count, session.answered_count),
        by_dimension=by_dimension,
    )


def finish_session(db: Session, user: User, session_id: int) -> PracticeSessionSummary:
    """结束练习。允许未答完就结束（否则候选人无法退出），且**幂等**。"""
    session = _get_owned_session(db, user, session_id)

    if session.status == STATUS_FINISHED:
        return _summary(db, session)  # 幂等：finished_at 不变

    repository.update_session(
        db, session, status=STATUS_FINISHED, finished_at=_now()
    )
    db.commit()
    db.refresh(session)
    return _summary(db, session)


# ---------------------------- 错题本 ----------------------------


def list_wrong_book(
    db: Session,
    user: User,
    position_id: int | None,
    dimension: str | None,
    question_type: str | None,
    limit: int,
) -> list[WrongBookItem]:
    if limit > WRONG_BOOK_MAX_LIMIT:
        raise ValidationError(f"limit 不能超过 {WRONG_BOOK_MAX_LIMIT}")

    rows = repository.list_wrong_items(
        db, user.id, position_id, dimension, question_type, limit
    )
    return [
        WrongBookItem(
            question_id=item.question_id,
            content=item.content_snapshot,
            options=list(item.options_snapshot or []),
            reference_answer=item.reference_answer_snapshot,
            explanation=item.explanation,
            my_wrong_answer=item.user_answer or "",
            wrong_count=wrong_count,
            last_wrong_at=item.answered_at,
        )
        for item, wrong_count in rows
    ]


# ---------------------------- 练习统计 ----------------------------


def get_stats(db: Session, user: User) -> PracticeStats:
    raw = repository.aggregate_stats(db, user.id)

    total_answered = raw["total_answered"]
    scored_count = raw["scored_count"]

    return PracticeStats(
        total_answered=total_answered,
        scored_count=scored_count,
        # 已作答的每一项要么已判分、要么未判分，故未判分数 = 已作答 - 已判分
        unscored_count=total_answered - scored_count,
        correct_count=raw["correct_count"],
        # 分母是**已判分**数：未判分的题与候选人水平无关（是 AI 没判出来），
        # 放进分母会系统性低估正确率
        accuracy=_accuracy(raw["correct_count"], scored_count),
        session_count=raw["session_count"],
        by_dimension=[
            DimensionStats(
                dimension=row["key"],
                answered=row["answered"],
                scored=row["scored"],
                correct=row["correct"],
                accuracy=_accuracy(row["correct"], row["scored"]),
            )
            for row in raw["by_dimension"]
        ],
        by_type=[
            TypeStats(
                question_type=row["key"],
                answered=row["answered"],
                scored=row["scored"],
                correct=row["correct"],
                accuracy=_accuracy(row["correct"], row["scored"]),
            )
            for row in raw["by_type"]
        ],
    )


# ---------------------------- 我的会话列表 ----------------------------


def list_my_sessions(
    db: Session, user: User, status: str | None, limit: int
) -> list[PracticeSessionListItem]:
    max_limit = get_settings().practice_session_list_max
    if limit > max_limit:
        # 超上限报错，不静默截断
        raise ValidationError(f"limit 不能超过 {max_limit}")

    rows = repository.list_by_candidate(db, user.id, status, limit)

    # 岗位名由 question 代取 —— practice 不依赖 position 模块（plan §1.3）
    position_ids = [s.position_id for s in rows if s.position_id is not None]
    position_names = question_service.get_position_names(db, position_ids)

    return [
        PracticeSessionListItem(
            session_id=session.id,
            status=session.status,
            position_name=(
                position_names.get(session.position_id)
                if session.position_id is not None
                else None
            ),
            category=session.category,
            dimension=session.dimension,
            difficulty=session.difficulty,
            question_type=session.question_type,
            total=session.total,
            answered_count=session.answered_count,
            correct_count=session.correct_count,
            started_at=session.started_at,
            finished_at=session.finished_at,
        )
        for session in rows
    ]
