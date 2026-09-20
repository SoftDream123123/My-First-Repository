"""evaluation 模块 HTTP 端点：触发评估、SSE 事件流、报告查询与导出。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response, StreamingResponse
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


# ------------------------------ 报告导出 ------------------------------

# ASCII 回退名：现代浏览器都认 `filename*`，回退名只是让老客户端也能存下文件。
# 把中文拼音化需要额外映射表，收益不成比例。
_ASCII_FALLBACK_FILENAME = "report.docx"


def _content_disposition(filename: str) -> str:
    """RFC 5987 双写：ASCII 回退名 + 百分号编码的真实文件名。

    `safe=""` 让 `/` 等字符也被编码，避免文件名里的路径分隔符被当成路径。
    """
    encoded = quote(filename, safe="")
    return (
        f'attachment; filename="{_ASCII_FALLBACK_FILENAME}"; '
        f"filename*=UTF-8''{encoded}"
    )


@router.get(
    "/{interview_id}/report/export",
    summary="导出报告为 DOCX（返回文件流）",
)
def export_report(
    interview_id: int,
    format: str = Query(default="docx", description="当前仅支持 docx"),
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> Response:
    """**只做 DOCX**：PDF 走前端浏览器打印（`window.print()`），后端不提供 PDF 接口。

    用 `Response` 而不是 `StreamingResponse`：内容已在内存完整生成（一层流都没有），
    后者是给「边读边发」用的（既有 SSE 才是那个场景）。
    用 `attachment` 而不是 `inline`：DOCX 无法在标签页里预览，`inline` 只会得到
    一个无从选择的下载行为。
    """
    result = service.export_report(db, user, interview_id, format)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": _content_disposition(result.filename)},
    )
