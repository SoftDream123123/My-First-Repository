"""interview 模块 HTTP 端点。

状态迁移一律走动词端点（/complete、/rollback）—— 迁移有前置条件与副作用，
作为 PATCH 的字段更新容易被绕过校验。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_current_user, get_db
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


@router.post(
    "",
    response_model=InterviewDetail,
    status_code=status.HTTP_201_CREATED,
    summary="创建面试（含同步出题组装）",
)
def create_interview(
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewDetail:
    return service.create_interview(db, user, payload)


@router.get("", response_model=list[InterviewListItem], summary="面试列表")
def list_interviews(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[InterviewListItem]:
    return service.list_interviews(db, user)


@router.get("/{interview_id}", response_model=InterviewDetail, summary="面试详情")
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewDetail:
    return service.get_interview(db, user, interview_id)


@router.patch(
    "/{interview_id}", response_model=InterviewDetail, summary="更新候选人信息"
)
def update_candidate(
    interview_id: int,
    payload: InterviewPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
) -> InterviewDetail:
    return service.rollback_interview(db, user, interview_id)
