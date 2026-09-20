"""interview 模块 HTTP 端点。

状态迁移一律走动词端点（/complete、/rollback）—— 迁移有前置条件与副作用，
作为 PATCH 的字段更新容易被绕过校验。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.models import ROLE_ADMIN, ROLE_HR, User
from app.core.deps import get_db, require_roles
from app.interview import service
from app.interview.schemas import (
    AnswerCreate,
    InterviewCreate,
    InterviewDetail,
    InterviewListItem,
    InterviewPatch,
    QuestionItem,
)

router = APIRouter(prefix="/interviews", tags=["面试"])

# HR 侧端点：admin 与 hr 均可，candidate 一律 403（PRD §4.1）。
# 候选人侧端点守卫不同，因此拆在 candidate_router.py，不与此处混放。
_hr_guard = require_roles(ROLE_ADMIN, ROLE_HR)


@router.post(
    "",
    response_model=InterviewDetail,
    status_code=status.HTTP_201_CREATED,
    summary="创建面试（含同步出题组装）",
)
def create_interview(
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InterviewDetail:
    return service.create_interview(db, user, payload)


@router.get("", response_model=list[InterviewListItem], summary="面试列表")
def list_interviews(
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> list[InterviewListItem]:
    return service.list_interviews(db, user)


@router.get("/{interview_id}", response_model=InterviewDetail, summary="面试详情")
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InterviewDetail:
    return service.get_interview(db, user, interview_id)


@router.patch(
    "/{interview_id}", response_model=InterviewDetail, summary="更新候选人信息"
)
def update_candidate(
    interview_id: int,
    payload: InterviewPatch,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InterviewDetail:
    return service.update_candidate(db, user, interview_id, payload)


@router.post(
    "/{interview_id}/answers",
    response_model=QuestionItem,
    summary="保存 / 更新某题回答",
)
def save_answer(
    interview_id: int,
    payload: AnswerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> QuestionItem:
    return service.save_answer(
        db, user, interview_id, payload.interview_question_id, payload.content
    )


@router.post(
    "/{interview_id}/complete", response_model=InterviewDetail, summary="标记面试完成"
)
def complete_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InterviewDetail:
    return service.complete_interview(db, user, interview_id)


@router.post(
    "/{interview_id}/rollback",
    response_model=InterviewDetail,
    summary="回退到进行中",
)
def rollback_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InterviewDetail:
    return service.rollback_interview(db, user, interview_id)
