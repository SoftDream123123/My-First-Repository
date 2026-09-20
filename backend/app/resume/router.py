"""resume 模块 HTTP 端点（候选人侧五个）。

全部守卫 `require_roles("candidate")` —— 候选人是终端用户角色，hr 与 admin
在候选人侧**都不通行**（module-09 §4.5 的精确匹配规则）。

本模块**没有 HR 侧端点**：HR 不提供简历 CRUD，只经 `GET /interviews/{id}/resume`
只读候选人关联的简历（由 interview 模块提供）。路径取 `/candidate/resumes`
而非 `/resumes`，是为了将来若出现 HR 侧端点时能落在 `/resumes/*` 上而不破坏前端。
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_db, require_roles
from app.resume import service
from app.resume.schemas import (
    RESUME_LIST_DEFAULT_LIMIT,
    RESUME_LIST_MAX_LIMIT,
    ResumeCreate,
    ResumeOut,
    ResumeUpdate,
)

router = APIRouter(prefix="/candidate/resumes", tags=["简历（候选人）"])

_candidate_guard = require_roles("candidate")


@router.post(
    "",
    response_model=ResumeOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建我的简历",
)
def create_resume(
    payload: ResumeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> ResumeOut:
    return ResumeOut.model_validate(service.create_resume(db, user, payload))


@router.get("", response_model=list[ResumeOut], summary="我的简历列表")
def list_my_resumes(
    limit: int = Query(
        default=RESUME_LIST_DEFAULT_LIMIT,
        ge=1,
        le=RESUME_LIST_MAX_LIMIT,
        description="超出上限直接报错，不静默截断",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> list[ResumeOut]:
    resumes = service.list_my_resumes(db, user, limit)
    return [ResumeOut.model_validate(r) for r in resumes]


@router.get("/{resume_id}", response_model=ResumeOut, summary="简历详情")
def get_my_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> ResumeOut:
    return ResumeOut.model_validate(service.get_my_resume(db, user, resume_id))


@router.put("/{resume_id}", response_model=ResumeOut, summary="更新我的简历（部分更新）")
def update_resume(
    resume_id: int,
    payload: ResumeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> ResumeOut:
    return ResumeOut.model_validate(
        service.update_resume(db, user, resume_id, payload)
    )


@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除我的简历（被面试或练习关联则 409）",
)
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> Response:
    service.delete_resume(db, user, resume_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
