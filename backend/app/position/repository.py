"""position 模块数据访问层。

get_by_id 刻意不带权限过滤 —— repository 保持纯粹，
「谁有权看」是业务判断，归 service。
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.position.models import Position


def create(
    db: Session, name: str, jd: str, dimensions: list[str], created_by: int
) -> Position:
    position = Position(
        name=name, jd=jd, evaluation_dimensions=dimensions, created_by=created_by
    )
    db.add(position)
    return position


def list_by_owner(
    db: Session, owner_id: int | None, keyword: str | None = None
) -> list[Position]:
    """owner_id 为 None 表示不过滤（admin 可见全部）。"""
    stmt = select(Position)
    if owner_id is not None:
        stmt = stmt.where(Position.created_by == owner_id)
    if keyword:
        stmt = stmt.where(Position.name.like(f"%{keyword}%"))
    stmt = stmt.order_by(Position.id)
    return list(db.execute(stmt).scalars().all())


def get_by_id(db: Session, position_id: int) -> Position | None:
    return db.get(Position, position_id)


def get_by_owner_and_name(db: Session, owner_id: int, name: str) -> Position | None:
    stmt = select(Position).where(
        Position.created_by == owner_id, Position.name == name
    )
    return db.execute(stmt).scalar_one_or_none()


def update(db: Session, position: Position, **fields: object) -> Position:
    for key, value in fields.items():
        setattr(position, key, value)
    return position


def delete(db: Session, position: Position) -> None:
    """删除岗位。被 question / interview 引用时由外键 RESTRICT 拒绝。"""
    db.delete(position)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("该岗位已被题库或面试引用，无法删除") from exc
