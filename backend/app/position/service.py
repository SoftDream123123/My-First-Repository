"""position 模块业务逻辑。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.models import User
from app.core.exceptions import BusinessError, NotFoundError
from app.position import repository
from app.position.models import Position
from app.position.schemas import PositionCreate, PositionUpdate


def _get_visible(db: Session, user: User, position_id: int) -> Position:
    """取回岗位并校验可见性 —— 项目统一的单条资源访问模式。"""
    position = repository.get_by_id(db, position_id)
    if position is None:
        raise NotFoundError("岗位不存在")
    auth_service.ensure_resource_visible(user, position.created_by, "岗位")
    return position


def create_position(db: Session, user: User, data: PositionCreate) -> Position:
    if repository.get_by_owner_and_name(db, user.id, data.name) is not None:
        raise BusinessError("该岗位名称已存在")

    position = repository.create(
        db, data.name, data.jd, data.evaluation_dimensions, user.id
    )
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发场景由唯一索引兜底，查重只为友好报错
        db.rollback()
        raise BusinessError("该岗位名称已存在") from exc

    db.refresh(position)
    return position


def list_positions(
    db: Session, user: User, keyword: str | None = None
) -> list[Position]:
    return repository.list_by_owner(db, auth_service.scope_owner_id(user), keyword)


def get_position(db: Session, user: User, position_id: int) -> Position:
    return _get_visible(db, user, position_id)


def update_position(
    db: Session, user: User, position_id: int, data: PositionUpdate
) -> Position:
    position = _get_visible(db, user, position_id)

    duplicate = repository.get_by_owner_and_name(db, position.created_by, data.name)
    if duplicate is not None and duplicate.id != position.id:
        raise BusinessError("该岗位名称已存在")

    repository.update(
        db,
        position,
        name=data.name,
        jd=data.jd,
        evaluation_dimensions=data.evaluation_dimensions,  # 全量替换
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("该岗位名称已存在") from exc

    db.refresh(position)
    return position


def delete_position(db: Session, user: User, position_id: int) -> None:
    position = _get_visible(db, user, position_id)
    repository.delete(db, position)
