"""evaluation 模块 HTTP 端点：触发评估、SSE 事件流、报告查询。"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.models import ROLE_ADMIN, ROLE_HR, User
from app.core.deps import get_db, require_roles
from app.evaluation import service, stream
from app.evaluation.schemas import EvaluateTriggerResponse, ReportDetail
from app.interview import service as interview_service
from app.interview.models import STATUS_EVALUATING

router = APIRouter(prefix="/interviews", tags=["评估"])

# HR 侧端点：admin 与 hr 均可，candidate 一律 403（PRD §4.1）。
# 候选人反馈端点属同一 URL 前缀但守卫不同，注册在 candidate_router.py。
_hr_guard = require_roles(ROLE_ADMIN, ROLE_HR)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 让 nginx 不缓冲流式响应
}


@router.post(
    "/{interview_id}/evaluate",
    response_model=EvaluateTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="触发评估（幂等），返回 SSE 流地址",
)
def trigger_evaluation(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> EvaluateTriggerResponse:
    service.ensure_visible(db, user, interview_id)

    # 进程重启遗留的孤儿评估：状态卡在 evaluating 但已无运行记录
    stream.heal_orphan(db, interview_id)

    existing = stream.get_run(interview_id)
    if existing is not None and existing.status == stream.RUN_RUNNING:
        # 幂等：已在评估中则不重复触发
        return EvaluateTriggerResponse(
            interview_id=interview_id,
            status=STATUS_EVALUATING,
            stream_url=f"/api/interviews/{interview_id}/evaluation/stream",
        )

    interview_service.begin_evaluation(db, interview_id)
    stream.start_run(interview_id)

    return EvaluateTriggerResponse(
        interview_id=interview_id,
        status=STATUS_EVALUATING,
        stream_url=f"/api/interviews/{interview_id}/evaluation/stream",
    )


@router.get(
    "/{interview_id}/evaluation/stream",
    summary="SSE 流式评估进度",
    response_class=StreamingResponse,
)
def evaluation_stream(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> StreamingResponse:
    service.ensure_visible(db, user, interview_id)
    stream.heal_orphan(db, interview_id)

    return StreamingResponse(
        stream.stream_events(interview_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get(
    "/{interview_id}/report", response_model=ReportDetail, summary="获取完整报告"
)
def get_report(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> ReportDetail:
    return service.get_report(db, user, interview_id)
