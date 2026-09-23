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
        """已存在同名 candidate 且**密码一致** → 复用，不新建、密码不变。"""
        before_hash = candidate_user.password_hash

        reused = service.create_candidate_account(
            db, candidate_user.username, "cand12345678"
        )

        assert reused.id == candidate_user.id
        assert reused.password_hash == before_hash

        from app.auth import repository

        assert repository.get_by_username(db, candidate_user.username) is not None

    def test_create_candidate_account_rejects_wrong_password(self, db, candidate_user):
        """⚠️ 已存在同名 candidate 但**密码不符** → 401，且不得复用该账号。

        这条守卫是 2026-09-21 补上的（PRD §4.1/§7、module-09 §5.2）：缺了它，
        「知道对方用户名」就等于能把自己的邀请码绑到对方账号上，进而读到对方的面试。
        文案与登录失败**完全一致**，以免成为「该用户名是否存在」的探测器。
        """
        from app.core.exceptions import UnauthorizedError

        before_hash = candidate_user.password_hash

        with pytest.raises(UnauthorizedError) as excinfo:
            service.create_candidate_account(db, candidate_user.username, "wrong-password")

        assert excinfo.value.status_code == 401
        assert excinfo.value.message == "用户名或密码错误"
        # 失败不能改动任何东西
        from app.auth import repository

        unchanged = repository.get_by_username(db, candidate_user.username)
        assert unchanged.password_hash == before_hash

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


# ===========================================================================
# accept 的免密分支（MVP-5，PRD §4.1）
# ===========================================================================


CANDIDATE_PASSWORD = "cand12345678"


def _make_invitation(client, hr_headers, position) -> dict:
    """HR 建面试 → 生成邀请码。返回邀请码响应体。"""
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "李四"},
        headers=hr_headers,
    ).json()
    return client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()


def _accept(client, code: str, payload: dict, headers: dict | None = None):
    return client.post(
        f"/api/candidate/invitations/{code}/accept", json=payload, headers=headers or {}
    )


class TestAcceptPasswordlessBranch:
    """已持有该账号的有效 JWT 时免密（PRD §4.1，2026-09-23）。

    这不是可选的便利功能：**手机号自动建号的账号没有可用密码**
    （见 `auth.service._create_phone_candidate`），没有这条分支，用手机号注册的
    候选人拿到邀请码后将永远无法激活 —— 报「用户名或密码错误」，而他根本没有密码。

    免密能成立的理由：密码的职责是「证明你是这个账号的主人」，而已持有该账号的
    有效 JWT 是同一件事的**更强证明**。
    """

    def test_own_token_without_password_succeeds(
        self, client, hr_headers, position, candidate_user, candidate_headers
    ):
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username},  # 刻意不带 password
            candidate_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["interview_id"] == invitation["interview_id"]

    def test_own_token_with_wrong_password_still_succeeds(
        self, client, hr_headers, position, candidate_user, candidate_headers
    ):
        """免密分支下密码**根本不参与** —— 连错密码也不影响。"""
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username, "password": "totally-wrong-1"},
            candidate_headers,
        )

        assert resp.status_code == 200, resp.text

    def test_another_users_token_is_rejected(
        self, client, hr_headers, position, candidate_user, other_candidate_headers
    ):
        """⚠️ 判据的核心：只满足「带 token」不够，token 必须**指向目标账号**。

        只认前者会让攻击者用自己的 token 去绑他人的账号 —— 那正是
        「密码不符即拒绝」要防的同一件事。文案与密码不符完全一致。
        """
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username},
            other_candidate_headers,
        )

        assert resp.status_code == 401
        assert resp.json()["message"] == "用户名或密码错误"

    def test_another_users_token_with_correct_password_succeeds(
        self, client, hr_headers, position, candidate_user, other_candidate_headers
    ):
        """既有行为不变：免密只是**少输一次密码**，没有放宽也无所谓收紧。"""
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username, "password": CANDIDATE_PASSWORD},
            other_candidate_headers,
        )

        assert resp.status_code == 200, resp.text

    def test_no_token_and_no_password_is_rejected(self, client, hr_headers, position, candidate_user):
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(client, invitation["code"], {"username": candidate_user.username})

        assert resp.status_code == 401
        assert resp.json()["message"] == "用户名或密码错误"

    def test_no_token_with_correct_password_succeeds(
        self, client, hr_headers, position, candidate_user
    ):
        """公开端点的既有主路径 —— 一行改动都不能碰。"""
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username, "password": CANDIDATE_PASSWORD},
        )

        assert resp.status_code == 200, resp.text

    def test_own_token_does_not_let_you_create_a_new_account_without_password(
        self, client, hr_headers, position, candidate_headers
    ):
        """免密只对「账号已存在且就是持 token 者本人」生效。

        新建路径没有「本人的账号」可以证明，因此仍必须有密码。
        """
        invitation = _make_invitation(client, hr_headers, position)

        without_password = _accept(
            client,
            invitation["code"],
            {"username": "brand_new_candidate"},
            candidate_headers,
        )
        assert without_password.status_code == 401
        assert without_password.json()["message"] == "用户名或密码错误"

        with_password = _accept(
            client,
            invitation["code"],
            {"username": "brand_new_candidate", "password": "brandnew12345"},
            candidate_headers,
        )
        assert with_password.status_code == 200, with_password.text

    def test_disabled_account_cannot_activate_with_own_token(
        self, client, db, admin_user, hr_headers, position, candidate_user, candidate_headers
    ):
        """禁用账号不得借免密分支被复用绑定（module-12 的既有结论）。

        ⚠️ 文案是**通用那句**而不是「账号已禁用」，这是有意的：`get_optional_user`
        对已禁用用户返回 None（与 `get_current_user` 保持同一条规则 ——
        它只认「get_current_user 也会接受」的用户），因此请求根本没走到免密分支，
        而是退回密码校验，而它没有密码。
        两处的结果一致：**绑定不发生**。这条用例钉住的就是这个结果。
        """
        invitation = _make_invitation(client, hr_headers, position)
        service.update_user(db, admin_user, candidate_user.id, is_active=False)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username},
            candidate_headers,
        )

        assert resp.status_code == 401

        # 断言真正重要的那件事：邀请**没有被消费**
        from app.interview import repository as interview_repository

        row = interview_repository.get_invitation_by_code(db, invitation["code"])
        assert row.status == "pending"
        assert row.candidate_user_id is None

    def test_garbage_token_degrades_to_password_path_not_500(
        self, client, hr_headers, position, candidate_user
    ):
        """坏 token 不是错误，只是「没有加速可用」（PRD §4.1）。

        若 `get_optional_user` 改成像 `get_current_user` 那样抛 401，
        「带过期 token 去激活」会从「按密码正常激活」退化成「激活失败」——
        一个纯粹的功能退化，且症状与原因离得很远。
        """
        invitation = _make_invitation(client, hr_headers, position)

        resp = _accept(
            client,
            invitation["code"],
            {"username": candidate_user.username, "password": CANDIDATE_PASSWORD},
            {"Authorization": "Bearer not-a-real-token"},
        )

        assert resp.status_code == 200, resp.text
