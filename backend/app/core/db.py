"""数据库基础：engine、Session 工厂、声明式 Base、请求级会话。

事务边界在 service 层 —— repository 只做单次数据操作，
commit / rollback 由 service 显式控制。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    echo=_settings.sql_echo,
    pool_pre_ping=True,  # 连接失效时自动重连，避免 MySQL 8h 超时导致的 "server has gone away"
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # 避免 commit 后访问属性触发额外查询 / DetachedInstanceError
)


class Base(DeclarativeBase):
    """所有业务模型的声明式基类。不定义任何业务字段。"""


def get_db() -> Generator[Session, None, None]:
    """请求级数据库会话：正常结束关闭，异常时先回滚再抛出。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
