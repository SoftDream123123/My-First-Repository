"""创建初始管理员账号。

用法：
    cd backend
    python scripts/seed_admin.py

幂等 —— 同名用户已存在则跳过，不报错、不覆盖密码。
凭据来自配置 ADMIN_USERNAME / ADMIN_PASSWORD（见 .env）。

为何不放进 Alembic 数据迁移：迁移应只承载结构变更。把有副作用的账号创建
写进迁移会导致回滚语义混乱，且生产环境不应在迁移中静默创建已知密码的账号。
"""

import sys
from pathlib import Path

# 允许以 `python scripts/seed_admin.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认 GBK，中文提示会乱码；显式切到 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.auth import repository, service  # noqa: E402
from app.auth.models import ROLE_ADMIN  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402

DEFAULT_PASSWORD = "admin12345"


def main() -> int:
    settings = get_settings()
    db = SessionLocal()

    try:
        existing = repository.get_by_username(db, settings.admin_username)
        if existing is not None:
            print(
                f"[跳过] 管理员 {settings.admin_username!r} 已存在"
                f"（id={existing.id}），未做任何改动。"
            )
            return 0

        user = service.create_user(
            db, settings.admin_username, settings.admin_password, ROLE_ADMIN
        )
        print(f"[成功] 已创建管理员：{user.username}（id={user.id}）")

        if settings.admin_password == DEFAULT_PASSWORD:
            print(
                "\n[警告] 当前使用的是默认密码。"
                "\n       生产环境请修改 .env 中的 ADMIN_PASSWORD 后重建账号。"
            )
        return 0

    except Exception as exc:  # noqa: BLE001 - CLI 入口，统一打印错误
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
