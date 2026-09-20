"""auth 模块候选人侧测试（计划书 module-09 §7.1、§7.4）。

覆盖：自助注册、凭邀请建号、角色不可指派、迁移安全性。
"""

import importlib.util
from functools import lru_cache
from pathlib import Path

import pytest
from sqlalchemy import text

from app.auth import service
from app.core.config import get_settings


@pytest.fixture
def self_register_off(monkeypatch):
    """关闭自助注册开关。

    配置是 lru_cache 单例，必须清缓存才会重新读取环境变量。
    """
    monkeypatch.setenv("CANDIDATE_SELF_REGISTER", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestCandidateRegister:
    def test_register_candidate_success(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"username": "newbie", "password": "newbie12345"},
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["role"] == "candidate"
        assert body["username"] == "newbie"
        assert body["is_active"] is True
        assert "password_hash" not in body

    def test_register_candidate_response_has_no_token(self, client):
        """注册与登录是两个动作 —— 响应不发 token（module-09 §5.1）。"""
        resp = client.post(
            "/api/auth/register",
            json={"username": "newbie", "password": "newbie12345"},
        )
        assert "token" not in resp.json()

    def test_register_candidate_password_hashed(self, client, db):
        client.post(
            "/api/auth/register",
            json={"username": "newbie", "password": "newbie12345"},
        )
        stored = db.execute(
            text("SELECT password_hash FROM `user` WHERE username = 'newbie'")
        ).scalar_one()

        assert stored != "newbie12345"
        assert stored.startswith("$2")  # bcrypt 前缀

    def test_register_candidate_duplicate_username(self, client, candidate_user):
        resp = client.post(
            "/api/auth/register",
            json={"username": candidate_user.username, "password": "whatever123"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"
        assert resp.json()["message"] == "用户名已被占用"

    def test_register_candidate_username_taken_by_hr_same_message(
        self, client, hr_user
    ):
        """占用者是 HR 时错误码与文案必须完全一致 —— 否则等于角色探测接口。"""
        resp = client.post(
            "/api/auth/register",
            json={"username": hr_user.username, "password": "whatever123"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"
        assert resp.json()["message"] == "用户名已被占用"

    def test_register_candidate_short_password(self, client):
        resp = client.post(
            "/api/auth/register", json={"username": "newbie", "password": "short"}
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert any(f["field"] == "password" for f in body["detail"]["fields"])

    def test_register_candidate_disabled_by_config(self, client, self_register_off):
        resp = client.post(
            "/api/auth/register",
            json={"username": "newbie", "password": "newbie12345"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "BUSINESS_ERROR"
        assert body["detail"]["reason"] == "self_register_disabled"

    def test_register_candidate_does_not_create_hr(self, client, db):
        """请求体塞 role 也无效 —— 落库角色恒为 candidate。"""
        resp = client.post(
            "/api/auth/register",
            json={"username": "newbie", "password": "newbie12345", "role": "hr"},
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "candidate"

        stored = db.execute(
            text("SELECT role FROM `user` WHERE username = 'newbie'")
        ).scalar_one()
        assert stored == "candidate"

    def test_candidate_can_login(self, client, candidate_user):
        resp = client.post(
            "/api/auth/login",
            json={
                "username": candidate_user.username,
                "password": "cand12345678",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["role"] == "candidate"
        assert body["token"]

    def test_candidate_can_call_me(self, client, candidate_user, candidate_headers):
        resp = client.get("/api/auth/me", headers=candidate_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == candidate_user.username

    def test_candidate_cannot_call_users(self, client, candidate_headers):
        resp = client.get("/api/users", headers=candidate_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"


class TestCreateCandidateAccount:
    """凭邀请建号（module-09 §5.2）—— 不校验自助注册开关。"""

    def test_create_candidate_account_new(self, db):
        user = service.create_candidate_account(db, "invitee", "invitee12345")
        assert user.role == "candidate"
        assert user.username == "invitee"

    def test_create_candidate_account_reuses_candidate(self, db, candidate_user):
        """已存在同名 candidate → 复用，不新建、密码不变。"""
        before_hash = candidate_user.password_hash

        reused = service.create_candidate_account(
            db, candidate_user.username, "a-different-password"
        )

        assert reused.id == candidate_user.id
        assert reused.password_hash == before_hash

        from app.auth import repository

        assert repository.get_by_username(db, candidate_user.username) is not None

    def test_create_candidate_account_rejects_hr(self, db, hr_user):
        """绝不允许把 HR / admin 账号绑到候选人邀请上 —— 这是越权入口。"""
        from app.core.exceptions import BusinessError

        with pytest.raises(BusinessError) as exc:
            service.create_candidate_account(db, hr_user.username, "whatever12345")

        assert exc.value.message == "用户名已被占用"

    def test_create_candidate_account_ignores_self_register_flag(
        self, db, self_register_off
    ):
        """开关关闭时仍可凭邀请建号 —— 邀请码是唯一入口，必须可用。"""
        user = service.create_candidate_account(db, "invitee", "invitee12345")
        assert user.role == "candidate"


class TestRoleAssignment:
    """候选人角色不可由 admin 指派（PRD §4.1）。"""

    def test_admin_cannot_assign_candidate_role(self, client, admin_headers):
        resp = client.post(
            "/api/users",
            json={
                "username": "sneaky",
                "password": "sneaky12345",
                "role": "candidate",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"

    def test_admin_cannot_patch_to_candidate(self, client, admin_headers, hr_user):
        resp = client.patch(
            f"/api/users/{hr_user.id}",
            json={"role": "candidate"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"


@lru_cache
def _migration_module():
    """按文件路径加载迁移模块。

    不能用 `import alembic.versions....` —— `backend/alembic/` 与已安装的
    `alembic` 库同名，且它没有 `__init__.py`（是目录而非包）。按 PEP 420，
    扫描到带 `__init__.py` 的常规包时后者胜出，于是该 import 会解析到
    第三方库而非本项目的迁移目录。
    """
    path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "b7f1c2a4d8e6_add_candidate_role.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_add_candidate_role", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRoleEnumMigration:
    def test_role_enum_includes_candidate(self, db, candidate_user):
        """迁移后 user.role 可写入 candidate 并读回。"""
        stored = db.execute(
            text("SELECT role FROM `user` WHERE id = :uid"),
            {"uid": candidate_user.id},
        ).scalar_one()
        assert stored == "candidate"

    def test_downgrade_protected_when_candidate_exists(self, db, candidate_user):
        """存在候选人账号时降级必须抛错，且不改写该行数据。

        直接调用迁移模块的守卫函数，而不是真的跑一次 downgrade —— 后者会把
        测试库的枚举收回去，破坏同一会话中后续用例的前置状态。
        """
        ensure_no_candidates = _migration_module().ensure_no_candidates

        with pytest.raises(RuntimeError, match="candidate"):
            ensure_no_candidates(db.connection())

        # 数据未被改写
        db.expire_all()
        stored = db.execute(
            text("SELECT role FROM `user` WHERE id = :uid"),
            {"uid": candidate_user.id},
        ).scalar_one()
        assert stored == "candidate"

    def test_downgrade_guard_passes_without_candidates(self, db, hr_user):
        """无候选人时守卫放行（不阻塞正常降级）。"""
        ensure_no_candidates = _migration_module().ensure_no_candidates

        ensure_no_candidates(db.connection())
