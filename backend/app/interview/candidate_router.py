"""interview 模块的候选人侧端点（在线答题）。

与 HR 端点分文件：两组端点的守卫不同（candidate vs admin/hr），放在同一 router
里容易在新增端点时挂错守卫 —— 而「挂错守卫」正是权限守卫补全要修的那类问题。
按守卫分文件，让「这个文件里的端点都是同一类角色」成为可读的事实。

面试状态的推进不在这里：候选人交卷**不改面试状态**，仍需 HR 手动 /complete
（PRD §5.1 的明确取舍）。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_db, require_roles
from app.interview import service
from app.interview.schemas import (
    CandidateAnswerCreate,
    CandidateAnswerView,
    CandidateInterviewDetail,
    CandidateInterviewItem,
    InvitationAcceptRequest,
    InvitationAcceptResult,
    SubmitResult,
)

router = APIRouter(prefix="/candidate", tags=["在线答题（候选人）"])

# 候选人侧守卫精确匹配 —— admin 与 hr 在此不通行（module-09 §4.5）
_candidate_guard = require_roles("candidate")


@router.post(
    "/invitations/{code}/accept",
    response_model=InvitationAcceptResult,
    summary="凭邀请码激活并绑定面试",
)
def accept_invitation(
    code: str,
    payload: InvitationAcceptRequest,
    db: Session = Depends(get_db),
    _: User = Depends(_candidate_guard),
) -> InvitationAcceptResult:
    """账号不存在则创建（role=candidate），已存在且为 candidate 则复用。

    **响应不含 token** —— 与自助注册一致，登录态由 /auth/login 单独获取。
    四种失效原因（码不存在 / 已撤销 / 已接受 / 已过期）返回同一文案，
    且响应中不出现任何面试信息，避免成为邀请码探测接口。
    """
    return service.accept_invitation(db, code, payload.username, payload.password)


@router.get(
    "/interviews",
    response_model=list[CandidateInterviewItem],
    summary="我参与的面试列表",
)
def list_my_interviews(
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> list[CandidateInterviewItem]:
    return service.list_my_interviews(db, user)


@router.get(
    "/interviews/{interview_id}",
    response_model=CandidateInterviewDetail,
    summary="面试详情（仅题目与我自己的作答）",
)
def get_my_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> CandidateInterviewDetail:
    return service.get_candidate_interview_detail(db, user, interview_id)


@router.post(
    "/interviews/{interview_id}/answers",
    response_model=CandidateAnswerView,
    summary="保存 / 更新我的作答",
)
def save_my_answer(
    interview_id: int,
    payload: CandidateAnswerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> CandidateAnswerView:
    """交卷后拒绝（409）。source / answered_by 由服务端写入，请求体不接受。"""
    return service.save_candidate_answer(db, user, interview_id, payload)


@router.post(
    "/interviews/{interview_id}/submit",
    response_model=SubmitResult,
    status_code=status.HTTP_200_OK,
    summary="交卷（幂等）",
)
def submit_my_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> SubmitResult:
    """无请求体。重复调用返回**首次**交卷时刻，不刷新它。"""
    return service.submit_interview(db, user, interview_id)
