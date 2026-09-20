"""position 模块 HTTP 端点。"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.models import ROLE_ADMIN, ROLE_HR, User
from app.core.deps import get_db, require_roles
from app.position import service
from app.position.schemas import PositionCreate, PositionOut, PositionUpdate

router = APIRouter(prefix="/positions", tags=["岗位"])

# 本模块全部端点均为 HR 侧：admin 与 hr 均可，candidate 一律 403（PRD §4.1）。
_hr_guard = require_roles(ROLE_ADMIN, ROLE_HR)


@router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建岗位",
)
def create_position(
    payload: PositionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> PositionOut:
    return PositionOut.model_validate(service.create_position(db, user, payload))


@router.get("", response_model=list[PositionOut], summary="岗位列表")
def list_positions(
    keyword: str | None = Query(default=None, description="按岗位名模糊匹配"),
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> list[PositionOut]:
    positions = service.list_positions(db, user, keyword)
    return [PositionOut.model_validate(p) for p in positions]


@router.get("/{position_id}", response_model=PositionOut, summary="岗位详情")
def get_position(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> PositionOut:
    return PositionOut.model_validate(service.get_position(db, user, position_id))


@router.put("/{position_id}", response_model=PositionOut, summary="更新岗位")
def update_position(
    position_id: int,
    payload: PositionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> PositionOut:
    return PositionOut.model_validate(
        service.update_position(db, user, position_id, payload)
    )


@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除岗位",
)
def delete_position(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> Response:
    service.delete_position(db, user, position_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
