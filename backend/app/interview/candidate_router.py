"""interview 模块的候选人侧端点（在线答题）。

与 HR 端点分文件：两组端点的守卫不同（candidate vs admin/hr），放在同一 router
里容易在新增端点时挂错守卫 —— 而「挂错守卫」正是权限守卫补全要修的那类问题。
按守卫分文件，让「这个文件里的端点都是同一类角色」成为可读的事实。

**唯一的例外是 `accept`**：它**没有守卫（公开端点）**。拿邀请码的人往往还没有
账号，要求他先登录才能激活会让邀请链自相矛盾（没有账号 → 没有 token → 激活不了）。
它挂在本文件下只是因为路径前缀同属 `/api/candidate`，**守卫是逐个端点挂的，不是按文件挂的**
（PRD §4.1/§8、module-12 §4.1）。权限扫测必须把它排除。

面试状态的推进不在这里：候选人交卷**不改面试状态**，仍需 HR 手动 /complete
（PRD §5.1 的明确取舍）。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai.base import FEEDBACK_LEVEL_FULL
from app.auth.models import User
from app.core.config import get_settings
from app.core.deps import get_db, require_roles
from app.interview import service
from app.interview.schemas import (
    CandidateAnswerCreate,
    CandidateAnswerView,
    CandidateInterviewDetail,
    CandidateInterviewItem,
    CandidateResumeReviewView,
    InterviewResumeOut,
    InvitationAcceptRequest,
    InvitationAcceptResult,
    ResumeLinkRequest,
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
) -> InvitationAcceptResult:
    """**公开端点：不要求 JWT**（本文件里唯一一个）。

    账号不存在则创建（role=candidate），已存在且为 candidate 时**校验密码后**复用
    （密码不符 → 401「用户名或密码错误」，见 `auth.service.create_candidate_account`）。

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


@router.put(
    "/interviews/{interview_id}/resume",
    response_model=InterviewResumeOut | None,
    summary="关联 / 解除关联我的一份简历",
)
def link_my_resume(
    interview_id: int,
    payload: ResumeLinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> InterviewResumeOut | None:
    """`resume_id` 传 `null` 表示**解除关联**（不是「不修改」）。

    这是 HR 能看到候选人简历的**唯一通路** —— HR 侧没有任何简历 CRUD。
    仅 `ongoing` 允许变更；只能关联属于本人的简历（403）/ 存在的简历（404）。
    """
    return service.link_resume(db, user, interview_id, payload.resume_id)


@router.post(
    "/interviews/{interview_id}/resume-review",
    response_model=CandidateResumeReviewView,
    summary="评估我的简历与该场岗位的匹配度（不落库）",
)
def review_my_resume(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> CandidateResumeReviewView:
    """**无请求体**；按 `CANDIDATE_FEEDBACK_LEVEL` 脱敏，`summary` 档不下发分数。

    脱敏发生在**这一层（router）**，不在 service、也不在 ai：它是「谁在看」的
    问题 —— service 拿到的是与调用者身份无关的 AI 结果，只有 router 知道这是
    候选人端。这与 `generate_candidate_feedback` 把 `level` 传进 ai 层刻意不同：
    那里档位改变的是**文案本身**（两档是两份不同的文本），这里只决定分数发不发，
    是纯视图裁剪（module-27 §5.4）。

    `strengths` / `gaps` **不脱敏**：分数是评估结果，文案是可照做的建议（§4.15）。
    `conclusion` 也不改写 —— 后端生成的结论从来就不含去留判断（§4.9 的红线），
    无需为候选人另写一版。
    """
    result = service.review_resume_for_candidate(db, user, interview_id)
    level = get_settings().candidate_feedback_level
    return CandidateResumeReviewView(
        match_score=result.match_score if level == FEEDBACK_LEVEL_FULL else None,
        conclusion=result.conclusion,
        strengths=result.strengths,
        gaps=result.gaps,
    )
