"""Alembic 迁移环境。

两个关键点：
1. 连接串从应用配置读取，不在 alembic.ini 里重复维护。
2. **必须导入全部业务模型**，否则 autogenerate 会漏表 —— 这是 Alembic 最常见的坑。
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 允许以 `alembic` 命令在 backend/ 目录下直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base  # noqa: E402

# ---- 导入全部模型（新增模块时务必在此补充）----
import app.auth.models  # noqa: E402,F401
import app.evaluation.models  # noqa: E402,F401
import app.interview.models  # noqa: E402,F401
import app.position.models  # noqa: E402,F401
import app.practice.models  # noqa: E402,F401
import app.question.models  # noqa: E402,F401
import app.resume.models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连接数据库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
