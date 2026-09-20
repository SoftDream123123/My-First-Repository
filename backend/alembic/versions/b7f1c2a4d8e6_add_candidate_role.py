"""extend user_role enum with candidate

Revision ID: b7f1c2a4d8e6
Revises: ebfc6ff09bbf
Create Date: 2026-09-20 10:00:00.000000

仅扩展 `user.role` 的枚举取值，不新增字段、不新增表（PRD §4.1、§5.2）。

downgrade 必须显式失败而非静默丢数据：MySQL 收回 ENUM 取值时，存量
`role='candidate'` 会被写成空字符串或截断值 —— 这是静默的数据损坏。
候选人账号还可能已绑定邀请（interview_invitation.candidate_user_id），
删号会让链接悬空。显式失败优于静默损坏。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f1c2a4d8e6"
down_revision: Union[str, None] = "ebfc6ff09bbf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TYPE = sa.Enum("admin", "hr", name="user_role")
_NEW_TYPE = sa.Enum("admin", "hr", "candidate", name="user_role")


def ensure_no_candidates(bind: sa.engine.Connection) -> None:
    """存在 candidate 行时抛错终止降级。

    抽成独立函数是为了让它可被直接单测 —— 在测试里真的跑一次 downgrade 会把
    测试库的枚举收回去，破坏同一会话中后续用例的前置状态。
    """
    count = bind.execute(
        sa.text("SELECT COUNT(*) FROM `user` WHERE role = 'candidate'")
    ).scalar_one()

    if count:
        raise RuntimeError(
            f"库中存在 {count} 个 role='candidate' 的账号，无法收回 user_role 枚举取值。"
            "请先迁移或删除这些候选人账号（注意它们可能已被 interview_invitation 引用），"
            "再执行降级。"
        )


def upgrade() -> None:
    op.alter_column(
        "user",
        "role",
        existing_type=_OLD_TYPE,
        type_=_NEW_TYPE,
        existing_nullable=False,
        existing_server_default="hr",
    )


def downgrade() -> None:
    ensure_no_candidates(op.get_bind())

    op.alter_column(
        "user",
        "role",
        existing_type=_NEW_TYPE,
        type_=_OLD_TYPE,
        existing_nullable=False,
        existing_server_default="hr",
    )
