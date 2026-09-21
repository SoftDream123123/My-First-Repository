"""作答邀请测试（计划书 module-12 §7.1）。

覆盖：生成、撤销、派生过期、接受。
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.auth import service as auth_service
from app.interview import repository
from app.interview.models import (
    INVITATION_ACCEPTED,
    INVITATION_PENDING,
    INVITATION_REVOKED,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_EVALUATED,
)


# `candidate_user` 夹具用的密码。接受邀请时若用户名已存在，**必须**填这个值 ——
# 复用已有候选人账号现在要校验密码（PRD §4.1/§7，2026-09-21 修正）。
CANDIDATE_PASSWORD = "cand12345678"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _fresh(db) -> None:
    """结束当前事务，让随后的读能看到别的连接刚提交的数据（REPEATABLE READ）。"""
    db.rollback()


def _create_interview(client, headers, position_id, name="张三") -> dict:
    resp = client.post(
        "/api/interviews",
        json={"position_id": position_id, "candidate_name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_invitation(client, headers, interview_id) -> dict:
    resp = client.post(f"/api/interviews/{interview_id}/invitations", headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _force_status(db, interview_id: int, status: str) -> None:
    _fresh(db)
    interview = repository.get_by_id(db, interview_id)
    interview.status = status
    db.commit()


def _force_expired(db, invitation_id: int) -> None:
    _fresh(db)
    invitation = repository.get_invitation_by_id(db, invitation_id)
    invitation.expires_at = _now() - timedelta(days=1)
    db.commit()


# ========================= 生成 =========================


class TestCreateInvitation:
    def test_ok(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        resp = client.post(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["status"] == INVITATION_PENDING
        assert len(body["code"]) >= 22  # token_urlsafe(16) → 22 字符
        assert body["accepted_at"] is None
        assert body["candidate_username"] is None

        # expires_at ≈ now + 7 天（默认 INVITATION_EXPIRE_DAYS）
        expires = datetime.fromisoformat(body["expires_at"])
        delta = expires - _now()
        assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)

    def test_codes_are_unique(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        codes = {
            _create_invitation(client, hr_headers, interview["id"])["code"]
            for _ in range(20)
        }
        assert len(codes) == 20

    @pytest.mark.parametrize(
        "status", [STATUS_DRAFT, STATUS_COMPLETED, STATUS_EVALUATED]
    )
    def test_requires_ongoing(self, client, db, hr_headers, position, status):
        interview = _create_interview(client, hr_headers, position.id)
        _force_status(db, interview["id"], status)

        resp = client.post(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        )
        assert resp.status_code == 409
        assert "进行中" in resp.json()["message"]

    def test_other_users_interview_forbidden(
        self, client, hr_headers, other_hr_headers, position
    ):
        interview = _create_interview(client, hr_headers, position.id)
        resp = client.post(
            f"/api/interviews/{interview['id']}/invitations",
            headers=other_hr_headers,
        )
        assert resp.status_code == 403

    def test_multiple_allowed(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        for _ in range(3):
            _create_invitation(client, hr_headers, interview["id"])

        listed = client.get(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        ).json()
        assert len(listed) == 3


# ========================= 撤销 =========================


class TestRevokeInvitation:
    def test_pending_ok(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])

        resp = client.delete(
            f"/api/interviews/{interview['id']}/invitations/{invitation['id']}",
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == INVITATION_REVOKED

    def test_revoked_is_idempotent(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])
        url = (
            f"/api/interviews/{interview['id']}/invitations/{invitation['id']}"
        )

        first = client.delete(url, headers=hr_headers)
        second = client.delete(url, headers=hr_headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == INVITATION_REVOKED

    def test_revoked_invitation_cannot_be_accepted(
        self, client, hr_headers, candidate_headers, position
    ):
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])
        client.delete(
            f"/api/interviews/{interview['id']}/invitations/{invitation['id']}",
            headers=hr_headers,
        )

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={"username": "someone", "password": "someone12345"},
            headers=candidate_headers,
        )
        assert resp.status_code == 409

    def test_revoke_accepted_succeeds_and_cuts_access(
        self, client, hr_headers, candidate_user, candidate_headers, position
    ):
        """撤销**已接受**的邀请：允许，且立即切断候选人的访问。

        计划书 §4.2 曾写「已接受的邀请不可撤销」，但 §5.1 把它明确列为**有意例外**，
        §5.6 的恢复路径（回退 → 撤销旧邀请 → 发新邀请）也依赖它。以 §5.1 为准。
        置 revoked 后 candidate_user_id / accepted_at 仍留在该行上。
        """
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])
        # 用 candidate_user 自己的用户名接受，绑定才会落在 candidate_headers 对应的账号上。
        # 密码必须是该账号的真实密码 —— 复用已有账号要校验（2026-09-21 修正）；
        # 此前这里填的是一个不相关的密码，能过**正是因为密码被忽略了**。
        client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={
                "username": candidate_user.username,
                "password": CANDIDATE_PASSWORD,
            },
            headers=candidate_headers,
        )
        # 撤销前可访问
        assert (
            client.get(
                f"/api/candidate/interviews/{interview['id']}", headers=candidate_headers
            ).status_code
            == 200
        )

        resp = client.delete(
            f"/api/interviews/{interview['id']}/invitations/{invitation['id']}",
            headers=hr_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == INVITATION_REVOKED
        # 「谁在何时接受了」这一事实被保留
        assert body["accepted_at"] is not None
        assert body["candidate_username"] == candidate_user.username

        # 撤销后立即 403
        assert (
            client.get(
                f"/api/candidate/interviews/{interview['id']}", headers=candidate_headers
            ).status_code
            == 403
        )


# ====================== 派生过期 ======================


class TestDerivedExpiry:
    def test_pending_before_expiry(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        _create_invitation(client, hr_headers, interview["id"])

        listed = client.get(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        ).json()
        assert listed[0]["status"] == INVITATION_PENDING

    def test_expired_after_expiry(self, client, db, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])
        _force_expired(db, invitation["id"])

        listed = client.get(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        ).json()
        assert listed[0]["status"] == "expired"

    def test_expired_is_not_persisted(self, client, db, hr_headers, position):
        """派生**不回写** —— 库里 status 仍是 pending。

        回写等于用一次读操作改变状态，会产生「谁先读谁写库」的隐式副作用。
        """
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])
        _force_expired(db, invitation["id"])

        client.get(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        )

        _fresh(db)
        stored = repository.get_invitation_by_id(db, invitation["id"])
        assert stored.status == INVITATION_PENDING  # 未被改写

    def test_accept_expired_rejected(
        self, client, db, hr_headers, candidate_headers, position
    ):
        interview = _create_interview(client, hr_headers, position.id)
        invitation = _create_invitation(client, hr_headers, interview["id"])
        _force_expired(db, invitation["id"])

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={"username": "late", "password": "late12345678"},
            headers=candidate_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["message"] == "邀请码无效或已失效"


# ========================= 接受 =========================


class TestAcceptInvitation:
    def _interview_with_invitation(self, client, hr_headers, position):
        interview = _create_interview(client, hr_headers, position.id)
        return interview, _create_invitation(client, hr_headers, interview["id"])

    def test_creates_candidate_account(
        self, client, db, hr_headers, candidate_headers, position
    ):
        interview, invitation = self._interview_with_invitation(
            client, hr_headers, position
        )

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={"username": "fresh_candidate", "password": "fresh12345"},
            headers=candidate_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["interview_id"] == interview["id"]

        _fresh(db)
        stored = repository.get_invitation_by_id(db, invitation["id"])
        assert stored.status == INVITATION_ACCEPTED
        assert stored.accepted_at is not None

        bound = auth_service.get_user_by_id(db, stored.candidate_user_id)
        assert bound.username == "fresh_candidate"
        assert bound.role == "candidate"

    def test_reuses_existing_candidate_account(
        self, client, db, hr_headers, candidate_headers, candidate_user, position
    ):
        """已存在同名 candidate 且**密码一致** → 复用同一 id，不新建、密码不变。"""
        interview, invitation = self._interview_with_invitation(
            client, hr_headers, position
        )
        before_hash = candidate_user.password_hash

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={"username": candidate_user.username, "password": CANDIDATE_PASSWORD},
            headers=candidate_headers,
        )
        assert resp.status_code == 200

        _fresh(db)
        stored = repository.get_invitation_by_id(db, invitation["id"])
        assert stored.candidate_user_id == candidate_user.id

        reused = auth_service.get_user_by_id(db, candidate_user.id)
        assert reused.password_hash == before_hash  # 密码未被改写

    def test_rejects_disabled_candidate_account(
        self,
        client,
        db,
        admin_headers,
        hr_headers,
        candidate_headers,
        candidate_user,
        position,
    ):
        """账号被禁用时不得复用绑定。

        复用会消耗掉一次性邀请码，而该账号此后 login 与 get_current_user
        都拒绝它 —— 候选人永远打不开这场面试，HR 也无法重新发码。
        """
        _, invitation = self._interview_with_invitation(client, hr_headers, position)

        resp = client.patch(
            f"/api/users/{candidate_user.id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={
                "username": candidate_user.username,
                "password": CANDIDATE_PASSWORD,
            },
            headers=candidate_headers,
        )
        assert resp.status_code == 401
        assert resp.json()["message"] == "账号已禁用，请联系管理员"

        # 拒绝必须是「完全不动」：码仍是 pending，可换回启用状态后再用
        _fresh(db)
        assert (
            repository.get_invitation_by_id(db, invitation["id"]).status
            == INVITATION_PENDING
        )

    def test_concurrent_accept_same_interview_binds_once(
        self, client, db, hr_headers, candidate_user, position
    ):
        """两条不同的码并发接受同一面试 → 只能产生一条绑定。

        「一次性接受」此前只是先查后写，没有数据库约束或行锁兜底：两个并发
        请求都能通过检查，候选人列表里同一场面试会出现两次
        （`list_accepted_interviews_for_candidate` 是 INNER JOIN，不去重）。
        """
        from app.core.db import SessionLocal
        from app.interview import service as interview_service

        interview = _create_interview(client, hr_headers, position.id)
        codes = [
            _create_invitation(client, hr_headers, interview["id"])["code"]
            for _ in range(2)
        ]

        results: list[str] = []
        barrier = threading.Barrier(len(codes))

        def _accept(code: str) -> None:
            session = SessionLocal()
            try:
                barrier.wait(timeout=10)
                interview_service.accept_invitation(
                    session, code, candidate_user.username, CANDIDATE_PASSWORD
                )
                results.append("ok")
            except Exception as exc:  # noqa: BLE001 - 并发失败也算一种结果
                results.append(type(exc).__name__)
            finally:
                session.close()

        threads = [
            threading.Thread(target=_accept, args=(code,)) for code in codes
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        assert results.count("ok") == 1, results

        _fresh(db)
        bound = [
            row.id
            for row, _ in repository.list_accepted_interviews_for_candidate(
                db, candidate_user.id
            )
        ]
        assert bound.count(interview["id"]) == 1

    def test_rejects_hr_username(
        self, client, db, hr_headers, candidate_headers, hr_user, position
    ):
        """绝不允许把 HR / admin 账号绑到候选人邀请上 —— 那是越权入口。"""
        _, invitation = self._interview_with_invitation(
            client, hr_headers, position
        )

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={"username": hr_user.username, "password": "whatever12345"},
            headers=candidate_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["message"] == "用户名已被占用"

        # 不得部分写入：邀请仍为 pending
        _fresh(db)
        assert (
            repository.get_invitation_by_id(db, invitation["id"]).status
            == INVITATION_PENDING
        )

    def test_twice_same_code_rejected(
        self, client, hr_headers, candidate_headers, position
    ):
        _, invitation = self._interview_with_invitation(client, hr_headers, position)
        payload = {"username": "twice", "password": "twice12345678"}

        first = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json=payload,
            headers=candidate_headers,
        )
        second = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json=payload,
            headers=candidate_headers,
        )
        assert first.status_code == 200
        assert second.status_code == 409  # 一次性接受

    def test_second_code_same_interview_rejected(
        self, client, hr_headers, candidate_headers, position
    ):
        """同一候选人用第二条码接受同一面试 → 409（否则列表出现重复项）。"""
        interview, first_invitation = self._interview_with_invitation(
            client, hr_headers, position
        )
        second_invitation = _create_invitation(client, hr_headers, interview["id"])
        payload = {"username": "dupe", "password": "dupe12345678"}

        assert (
            client.post(
                f"/api/candidate/invitations/{first_invitation['code']}/accept",
                json=payload,
                headers=candidate_headers,
            ).status_code
            == 200
        )

        resp = client.post(
            f"/api/candidate/invitations/{second_invitation['code']}/accept",
            json=payload,
            headers=candidate_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["message"] == "你已接受过该面试的邀请"

    def test_unknown_code_message_matches_expired(
        self, client, db, hr_headers, candidate_headers, position
    ):
        """未知码与过期码的**错误码与文案完全一致**（不泄露）。"""
        interview = _create_interview(client, hr_headers, position.id)
        expired = _create_invitation(client, hr_headers, interview["id"])
        _force_expired(db, expired["id"])

        payload = {"username": "probe", "password": "probe12345678"}
        unknown = client.post(
            "/api/candidate/invitations/definitely-not-a-real-code/accept",
            json=payload,
            headers=candidate_headers,
        )
        stale = client.post(
            f"/api/candidate/invitations/{expired['code']}/accept",
            json=payload,
            headers=candidate_headers,
        )

        assert unknown.status_code == stale.status_code == 409
        assert unknown.json()["code"] == stale.json()["code"] == "BUSINESS_ERROR"
        assert unknown.json()["message"] == stale.json()["message"]

    def test_response_has_no_token(
        self, client, hr_headers, candidate_headers, position
    ):
        _, invitation = self._interview_with_invitation(client, hr_headers, position)

        resp = client.post(
            f"/api/candidate/invitations/{invitation['code']}/accept",
            json={"username": "notoken", "password": "notoken12345"},
            headers=candidate_headers,
        )
        assert "token" not in resp.json()

    def test_does_not_leak_interview_existence(
        self, client, hr_headers, candidate_headers, position
    ):
        """失效场景的响应里不出现面试名、岗位名等任何面试信息。"""
        interview = _create_interview(client, hr_headers, position.id, name="李四")

        resp = client.post(
            "/api/candidate/invitations/nope-not-real/accept",
            json={"username": "peek", "password": "peek12345678"},
            headers=candidate_headers,
        )
        text = resp.text
        assert "李四" not in text
        assert "后端工程师" not in text
        assert "interview_id" not in text
        assert str(interview["id"]) not in text
