"""resume 模块数据模型。

简历只存**纯文本**：不存原文件、不存解析产物，因此不存在解析失败分支
（PRD §1.3、§5.2）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Resume(Base):
    """简历表。

    写入方**只有候选人**，`created_by` 恒为候选人用户 id（PRD §4.10）。
    HR 的读取权限不在本表判定，而在「该简历是否关联到自己名下的某场面试」
    上判定 —— 判据由 interview 实现，本模块只提供无权限过滤的读取。
    """

    __tablename__ = "resume"
    __table_args__ = (
        Index("ix_resume_created_by", "created_by"),
        # 刻意**不加** (created_by, title) 唯一约束：候选人保留两份都叫
        # 「通用简历」是无害的用法（与 position 的 uq_position_owner_name 不同，
        # 岗位名是 HR 的检索键，简历标题不是）。
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    # 正文上限由 RESUME_CONTENT_MAX_LENGTH + service 层校验承担：
    # 20000 字符已超 VARCHAR 的实用上限，故用 TEXT。
    content: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # 本表是项目里第一张带 updated_at 的表：简历是唯一由用户反复编辑的自有内容，
    # 且 PRD §4.13 要求「候选人改简历后 HR 需重新触发补题」，HR 需要判断手上这份
    # 是不是最新的。onupdate 由 SQLAlchemy 在每次 UPDATE 时带上 NOW()。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Resume id={self.id} title={self.title!r}>"
