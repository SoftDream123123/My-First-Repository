"""position 模块 HTTP 端点。"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_current_user, get_db
from app.position import service
from app.position.schemas import PositionCreate, PositionOut, PositionUpdate

router = APIRouter(prefix="/positions", tags=["岗位"])


@router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建岗位",
)
def create_position(
    payload: PositionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PositionOut:
    return PositionOut.model_validate(service.create_position(db, user, payload))


@router.get("", response_model=list[PositionOut], summary="岗位列表")
def list_positions(
    keyword: str | None = Query(default=None, description="按岗位名模糊匹配"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PositionOut]:
    positions = service.list_positions(db, user, keyword)
    return [PositionOut.model_validate(p) for p in positions]


@router.get("/{position_id}", response_model=PositionOut, summary="岗位详情")
def get_position(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PositionOut:
    return PositionOut.model_validate(service.get_position(db, user, position_id))


@router.put("/{position_id}", response_model=PositionOut, summary="更新岗位")
def update_position(
    position_id: int,
    payload: PositionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
) -> Response:
    service.delete_position(db, user, position_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
