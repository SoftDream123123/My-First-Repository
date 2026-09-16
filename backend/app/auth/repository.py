"""auth 模块数据访问层。

只做数据操作，不做业务判断（「密码是否正确」「用户名是否重复」属于 service）。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, username: str, password_hash: str, role: str) -> User:
    user = User(username=username, password_hash=password_hash, role=role)
    db.add(user)
    return user


def list_all(db: Session) -> list[User]:
    stmt = select(User).order_by(User.id)
    return list(db.execute(stmt).scalars().all())


def update(db: Session, user: User, **fields: object) -> User:
    for key, value in fields.items():
        setattr(user, key, value)
    return user
