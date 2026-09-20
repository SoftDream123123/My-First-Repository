"""interview 模块 HTTP 端点。

状态迁移一律走动词端点（/complete、/rollback）—— 迁移有前置条件与副作用，
作为 PATCH 的字段更新容易被绕过校验。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.models import ROLE_ADMIN, ROLE_HR, User
from app.core.config import get_settings
from app.core.deps import get_db, require_roles
from app.interview import service
from app.interview.schemas import (
    AnswerCreate,
    InterviewCreate,
    InterviewDetail,
    InterviewListItem,
    InterviewPatch,
    InterviewResumeOut,
    InvitationView,
    MatchRequest,
    MatchResult,
    PrepOut,
    PrepUpdate,
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


# ---------------------------- 作答邀请 ----------------------------


@router.post(
    "/{interview_id}/invitations",
    response_model=InvitationView,
    status_code=status.HTTP_201_CREATED,
    summary="生成作答邀请码",
)
def create_invitation(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InvitationView:
    """无请求体 —— 有效期由配置项 INVITATION_EXPIRE_DAYS 推导。

    响应含**明文** code 供 HR 复制（PRD §1.3：邀请码在系统内展示与复制，不发邮件）。
    """
    return service.create_invitation(db, user, interview_id)


@router.get(
    "/{interview_id}/invitations",
    response_model=list[InvitationView],
    summary="邀请列表与状态",
)
def list_invitations(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> list[InvitationView]:
    return service.list_invitations(db, user, interview_id)


@router.delete(
    "/{interview_id}/invitations/{invitation_id}",
    response_model=InvitationView,
    summary="撤销邀请",
)
def revoke_invitation(
    interview_id: int,
    invitation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InvitationView:
    """返回 200 + 更新后的对象，而不是 204。

    撤销后前端需要展示该条的最终状态（revoked）；返回对象比空响应更有用。
    与 `DELETE /questions/{id}` 的 204 不同，此处有明确的响应内容。
    """
    return service.revoke_invitation(db, user, interview_id, invitation_id)


# ---------------------- 简历（只读）与按简历补题 ----------------------


@router.get(
    "/{interview_id}/resume",
    response_model=InterviewResumeOut,
    summary="读取本场关联的候选人简历（未关联则 404）",
)
def get_interview_resume(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> InterviewResumeOut:
    """HR 不提供简历 CRUD —— 这是只读端点，判据是「该面试属于我」。"""
    return service.get_interview_resume(db, user, interview_id)


@router.post(
    "/{interview_id}/questions/match",
    response_model=MatchResult,
    summary="按简历从题库补题（追加、幂等）",
)
def match_questions_by_resume(
    interview_id: int,
    payload: MatchRequest = MatchRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> MatchResult:
    """**POST 而非 PUT**：它会追加数据（每次调用都改变结果），不是幂等替换。

    重复调用不会产生重复题目，但**会继续叠加**新题 —— 响应里的
    `added_count` / `total_questions` 就是给前端提示「本次新增 N 题，本场共 M 题」。
    """
    count = (
        payload.count
        if payload.count is not None
        else get_settings().resume_match_count
    )
    return service.match_questions_by_resume(db, user, interview_id, count)


# ------------------------- 面试前准备助手 -------------------------


@router.post(
    "/{interview_id}/prep",
    response_model=PrepOut,
    summary="生成 / 重新生成准备提纲（整体覆盖）",
)
def generate_prep(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> PrepOut:
    """一次生成即整批落库，**不做流式**（PRD §4.11）。

    AI 失败返回 502，且已有提纲（含 generated_at）保持不变。
    """
    return service.generate_prep(db, user, interview_id)


@router.get(
    "/{interview_id}/prep",
    response_model=PrepOut,
    summary="查看准备提纲（未生成则 404）",
)
def get_prep(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> PrepOut:
    """未生成时 404 而非空对象 —— 前端据此显示「生成准备提纲」按钮。"""
    return service.get_prep(db, user, interview_id)


@router.put(
    "/{interview_id}/prep",
    response_model=PrepOut,
    summary="编辑准备提纲（整体覆盖三部分）",
)
def update_prep(
    interview_id: int,
    payload: PrepUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> PrepOut:
    """三部分**全部必填**：整体替换语义让「未提交的部分怎么办」这个问题消失。

    未生成就编辑 → 404（不自动创建）。
    """
    return service.update_prep(db, user, interview_id, payload)
