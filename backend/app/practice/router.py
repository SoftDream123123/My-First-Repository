"""practice 模块 HTTP 端点（九个）。

全部守卫 `require_roles("candidate")` —— 候选人是终端用户角色，
admin 与 hr 在候选人侧**不通行**（module-09 §4.5 的精确匹配规则）：
admin 一旦放行就会污染候选人的练习数据与作答归属。
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_db, require_roles
from app.practice import service
from app.practice.schemas import (
    PracticeItemResult,
    PracticeItemSubmit,
    PracticeSessionCreate,
    PracticeSessionDetail,
    PracticeSessionListItem,
    PracticeSessionSummary,
    PracticeStats,
    WrongBookItem,
)
from app.question.schemas import PracticeFilters, PracticePreviewOut

router = APIRouter(prefix="/practice", tags=["刷题（候选人）"])

_candidate_guard = require_roles("candidate")


@router.get(
    "/questions",
    response_model=PracticePreviewOut,
    summary="刷题取题（预览，不含答案）",
)
def preview_questions(
    position_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    dimension: str | None = Query(default=None),
    difficulty: str | None = Query(default=None, description="easy | medium | hard"),
    question_type: str | None = Query(
        default=None, description="single_choice | short_answer"
    ),
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticePreviewOut:
    """无状态预览 —— 不创建会话。

    响应 `{total, items}`：`total` 是符合条件的**真实题量**（不受 limit 截断），
    `items` 是截断后的题目预览（PracticeQuestionOut，**不含参考答案**），
    供下拉框取分类 / 维度的候选值。
    """
    filters = PracticeFilters(
        position_id=position_id,
        category=category,
        dimension=dimension,
        difficulty=difficulty,
        question_type=question_type,
    )
    return service.preview_questions(db, user, filters, limit)


@router.get(
    "/sessions",
    response_model=list[PracticeSessionListItem],
    summary="我的练习会话列表（含进行中）",
)
def list_my_sessions(
    session_status: str | None = Query(
        default=None, alias="status", description="ongoing | finished；缺省返回全部"
    ),
    limit: int = Query(default=service.SESSION_LIST_DEFAULT_LIMIT, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> list[PracticeSessionListItem]:
    """没有这个端点，候选人一旦离开未完成的练习就只能靠 URL 回去。

    **不含题目明细** —— 明细走 GET /practice/sessions/{id}。无会话时返回
    空数组（不是 404）：「还没练过」是正常状态。
    """
    return service.list_my_sessions(db, user, session_status, limit)


@router.post(
    "/sessions",
    response_model=PracticeSessionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="开始一次练习",
)
def start_session(
    payload: PracticeSessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticeSessionDetail:
    """取题并写题目快照。无符合题时返回 409 且**不创建会话**。"""
    return service.start_session(db, user, payload)


@router.get(
    "/sessions/{session_id}",
    response_model=PracticeSessionDetail,
    summary="练习详情与进度",
)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticeSessionDetail:
    """未提交的题不下发解析与参考答案（「提交后展示」规则的落点）。"""
    return service.get_session(db, user, session_id)


@router.post(
    "/sessions/{session_id}/items",
    response_model=PracticeItemResult,
    summary="提交某题作答（即时判分 + 解析）",
)
def submit_item(
    session_id: int,
    payload: PracticeItemSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticeItemResult:
    """AI 判分失败或题目无参考答案时返回 **200** 且 `is_correct` 为 null。

    不返回 5xx：作答本身已成功保存，报错会让前端以为提交失败而重试，
    与实际事实不符（PRD §7）。
    """
    return service.submit_item(db, user, session_id, payload)


@router.post(
    "/items/{item_id}/rescore",
    response_model=PracticeItemResult,
    summary="对未判分的题重新判分",
)
def rescore_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticeItemResult:
    """仅对**未判分**的项生效；已判分的项幂等返回既有结果，不重复调用 AI。

    已判分的项重判会改变正确答案与分数，等于允许「刷分」，因此明确拒绝。
    """
    return service.rescore_item(db, user, item_id)


@router.post(
    "/sessions/{session_id}/finish",
    response_model=PracticeSessionSummary,
    summary="结束练习，出小结",
)
def finish_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticeSessionSummary:
    """允许未答完就结束；重复调用幂等（finished_at 不变）。"""
    return service.finish_session(db, user, session_id)


@router.get(
    "/wrong-book",
    response_model=list[WrongBookItem],
    summary="错题本（由 practice_item 派生）",
)
def list_wrong_book(
    position_id: int | None = Query(default=None),
    dimension: str | None = Query(default=None),
    question_type: str | None = Query(default=None),
    limit: int = Query(default=service.WRONG_BOOK_DEFAULT_LIMIT, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> list[WrongBookItem]:
    """按 question_id 去重并给出 wrong_count；**未判分的题不算错题**。"""
    return service.list_wrong_book(
        db, user, position_id, dimension, question_type, limit
    )


@router.get("/stats", response_model=PracticeStats, summary="我的练习统计")
def get_stats(
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> PracticeStats:
    """正确率的分母是**已判分**数，不是已作答数。"""
    return service.get_stats(db, user)
