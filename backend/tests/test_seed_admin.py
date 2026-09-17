"""seed_admin 脚本测试（计划书 module-01 §9-10、Task 1.8）。

`scripts/seed_admin.py` 是交付物里「新人按 README 就能拿到一个能登录的账号」
这条链路的关键一环，但计划书只给了手工验证步骤。这里把它自动化：
落库正确、可登录、重复执行不报错、不重复建号、不覆盖密码。
"""

import importlib.util
from pathlib import Path

import pytest

from app.auth import repository
from app.auth.models import ROLE_ADMIN
from app.core.config import get_settings
from app.core.security import verify_password

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_admin.py"


def _load_seed_module():
    """按文件路径加载 —— scripts/ 不是 package，无法直接 import。"""
    spec = importlib.util.spec_from_file_location("seed_admin_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_admin = _load_seed_module()


def _admin(db):
    db.rollback()  # 结束当前事务，避免读到早于脚本提交的 REPEATABLE READ 快照
    return repository.get_by_username(db, get_settings().admin_username)


def test_creates_loginable_admin(db):
    assert seed_admin.main() == 0

    user = _admin(db)
    assert user is not None
    assert user.role == ROLE_ADMIN
    assert user.is_active is True
    assert verify_password(get_settings().admin_password, user.password_hash)
    assert user.password_hash.startswith("$2b$")  # 绝不落明文


def test_seeded_admin_can_log_in(client):
    assert seed_admin.main() == 0

    resp = client.post(
        "/api/auth/login",
        json={
            "username": get_settings().admin_username,
            "password": get_settings().admin_password,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == ROLE_ADMIN


def test_is_idempotent(db):
    """重复执行：退出码仍为 0，不重复建号，也不覆盖已有密码。"""
    assert seed_admin.main() == 0
    first = _admin(db)
    assert first is not None

    assert seed_admin.main() == 0
    again = _admin(db)

    assert again.id == first.id
    assert again.password_hash == first.password_hash
    assert len([u for u in repository.list_all(db) if u.username == first.username]) == 1


def test_does_not_overwrite_existing_password(db):
    """同名账号已存在（且密码不同）时，脚本必须原样保留。"""
    from app.auth import service

    existing = service.create_user(
        db, get_settings().admin_username, "a-different-password", ROLE_ADMIN
    )
    db.commit()
    original_hash = existing.password_hash

    assert seed_admin.main() == 0

    assert _admin(db).password_hash == original_hash
    assert not verify_password(get_settings().admin_password, original_hash)


def test_warns_when_default_password_is_used(capsys):
    """脚本只在用到默认密码时打印告警 —— 提示生产必须改。"""
    settings = get_settings()
    if settings.admin_password != seed_admin.DEFAULT_PASSWORD:
        pytest.skip("当前 ADMIN_PASSWORD 非默认值，告警分支不适用")

    assert seed_admin.main() == 0
    assert "默认密码" in capsys.readouterr().out
