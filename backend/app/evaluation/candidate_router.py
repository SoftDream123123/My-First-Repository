"""evaluation 模块的候选人侧端点（脱敏反馈）。

与 HR 端点（router.py）分文件：两组端点的守卫不同（candidate vs admin/hr）。

端点路径归属 `/candidate` 前缀但由 evaluation 包提供：**路径表达「谁在访问」，
包归属表达「数据属于谁」** —— 反馈读的是报告，数据在 evaluation 这里。
这与 interview 的 `/candidate/*` 端点由 interview 包提供是一致的。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_db, require_roles
from app.evaluation import service
from app.evaluation.schemas import CandidateFeedbackOut

router = APIRouter(prefix="/candidate", tags=["候选人反馈"])

# 候选人侧守卫精确匹配 —— admin 与 hr 在此不通行（module-09 §4.5）
_candidate_guard = require_roles("candidate")


@router.get(
    "/interviews/{interview_id}/feedback",
    response_model=CandidateFeedbackOut,
    summary="查看面向候选人的脱敏反馈",
)
def get_candidate_feedback(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> CandidateFeedbackOut:
    """**档位只来自服务端配置**，不接受客户端指定 —— 否则候选人传一个
    `?level=full` 就能拿到自己的总分（FastAPI 会忽略未声明的查询参数）。

    响应由白名单模型 `CandidateFeedbackOut` 序列化，结构上不可能包含
    逐题分、维度分或雷达图数据。
    """
    return service.get_candidate_feedback(db, user, interview_id)
