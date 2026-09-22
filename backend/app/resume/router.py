"""resume 模块 HTTP 端点（候选人侧五个）。

全部守卫 `require_roles("candidate")` —— 候选人是终端用户角色，hr 与 admin
在候选人侧**都不通行**（module-09 §4.5 的精确匹配规则）。

本模块**没有 HR 侧端点**：HR 不提供简历 CRUD，只经 `GET /interviews/{id}/resume`
只读候选人关联的简历（由 interview 模块提供）。路径取 `/candidate/resumes`
而非 `/resumes`，是为了将来若出现 HR 侧端点时能落在 `/resumes/*` 上而不破坏前端。
"""

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.config import get_settings
from app.core.deps import get_db, require_roles
from app.resume import service
from app.resume.schemas import (
    RESUME_LIST_DEFAULT_LIMIT,
    RESUME_LIST_MAX_LIMIT,
    ResumeCreate,
    ResumeOut,
    ResumeParseResult,
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


@router.post(
    "/parse",
    response_model=ResumeParseResult,
    summary="上传 DOCX / PDF 解析为纯文本（不落库）",
)
def parse_resume_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_candidate_guard),
) -> ResumeParseResult:
    """把上传的简历文件抠成纯文本返回 —— **不落库、不落盘**（PRD §4.10、§5.2）。

    候选人在前端确认解析结果后才调 `POST` / `PUT` 保存，因此本端点不建简历、
    不改简历、不在服务器上留下那个文件。

    ⚠️ **声明位置必须在 `/{resume_id}` 那三条之前**：现在方法与路径都不撞
    （这里是 POST、那三条是 GET/PUT/DELETE），但顺序写错在日后加
    `POST /{resume_id}` 类端点时会立刻变成「parse 被当成 resume_id 解析」的 500。
    """
    # 按「上限 + 1」字节读：够判超限即可，不必把整个大文件读进内存
    limit = get_settings().resume_upload_max_bytes
    data = file.file.read(limit + 1)
    return ResumeParseResult(content=service.parse_uploaded_resume(data, file.filename))


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
