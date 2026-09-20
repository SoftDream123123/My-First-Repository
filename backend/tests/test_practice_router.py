"""practice 模块端点、鉴权与隔离测试（计划书 module-13 §7.4 会话列表、§7.6）。
"""

import pytest

from app.practice import service as practice_service
from app.practice.models import STATUS_FINISHED, STATUS_ONGOING
from app.practice.schemas import PracticeSessionCreate

PRACTICE_ENDPOINTS = [
    ("GET", "/api/practice/questions"),
    ("GET", "/api/practice/sessions"),
    ("POST", "/api/practice/sessions"),
    ("GET", "/api/practice/sessions/999999"),
    ("POST", "/api/practice/sessions/999999/items"),
    ("POST", "/api/practice/items/999999/rescore"),
    ("POST", "/api/practice/sessions/999999/finish"),
    ("GET", "/api/practice/wrong-book"),
    ("GET", "/api/practice/stats"),
]


def _start(db, user, **kwargs):
    return practice_service.start_session(db, user, PracticeSessionCreate(**kwargs))


# ==================== 会话列表 ====================


class TestSessionList:
    URL = "/api/practice/sessions"

    def test_only_own(
        self, client, db, candidate_user, other_candidate, candidate_headers, practice_questions
    ):
        _start(db, candidate_user, size=1)
        _start(db, other_candidate, size=1)

        listed = client.get(self.URL, headers=candidate_headers).json()
        assert len(listed) == 1

    def test_includes_ongoing(
        self, client, db, candidate_user, candidate_headers, practice_questions
    ):
        finished = _start(db, candidate_user, size=1)
        _start(db, candidate_user, size=1)
        practice_service.finish_session(db, candidate_user, finished.session.id)

        listed = client.get(self.URL, headers=candidate_headers).json()
        assert len(listed) == 2  # 缺省返回全部，含进行中

    def test_filter_status(
        self, client, db, candidate_user, candidate_headers, practice_questions
    ):
        finished = _start(db, candidate_user, size=1)
        ongoing = _start(db, candidate_user, size=1)
        practice_service.finish_session(db, candidate_user, finished.session.id)

        only_ongoing = client.get(
            self.URL, params={"status": STATUS_ONGOING}, headers=candidate_headers
        ).json()
        assert [item["session_id"] for item in only_ongoing] == [ongoing.session.id]

        only_finished = client.get(
            self.URL, params={"status": STATUS_FINISHED}, headers=candidate_headers
        ).json()
        assert [item["session_id"] for item in only_finished] == [finished.session.id]

    def test_ordered_by_started_desc(
        self, client, db, candidate_user, candidate_headers, practice_questions
    ):
        ids = [_start(db, candidate_user, size=1).session.id for _ in range(3)]

        listed = client.get(self.URL, headers=candidate_headers).json()
        returned = [item["session_id"] for item in listed]
        assert returned == sorted(ids, reverse=True)

    def test_excludes_item_details(
        self, client, db, candidate_user, candidate_headers, practice_questions
    ):
        _start(db, candidate_user, size=1)

        listed = client.get(self.URL, headers=candidate_headers).json()
        for forbidden in ("items", "content", "options", "user_answer"):
            assert forbidden not in listed[0]

    def test_empty_returns_empty_array(self, client, candidate_headers):
        resp = client.get(self.URL, headers=candidate_headers)
        assert resp.status_code == 200
        assert resp.json() == []  # 不是 404

    def test_limit_capped(self, client, candidate_headers):
        """超上限 → 400，不静默截断。"""
        resp = client.get(
            self.URL, params={"limit": 99999}, headers=candidate_headers
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"

    def test_rejects_hr(self, client, hr_headers):
        assert client.get(self.URL, headers=hr_headers).status_code == 403


# ==================== 鉴权与隔离 ====================


class TestAuthAndIsolation:
    @pytest.mark.parametrize("method,path", PRACTICE_ENDPOINTS)
    def test_rejects_hr(self, client, hr_headers, method, path):
        resp = client.request(method, path, json={}, headers=hr_headers)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", PRACTICE_ENDPOINTS)
    def test_rejects_admin(self, client, admin_headers, method, path):
        """admin 在候选人侧**精确匹配**下不通行 —— 否则会污染候选人的练习数据。"""
        resp = client.request(method, path, json={}, headers=admin_headers)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", PRACTICE_ENDPOINTS)
    def test_rejects_anonymous(self, client, method, path):
        resp = client.request(method, path, json={})
        assert resp.status_code == 401

    def test_all_nine_endpoints_covered(self):
        """守门断言：上面三个参数化测试必须覆盖全部九个端点。"""
        assert len(PRACTICE_ENDPOINTS) == 9

    def test_session_detail_hides_reference_before_submit(
        self, client, candidate_headers, practice_session
    ):
        detail = client.get(
            f"/api/practice/sessions/{practice_session.session.id}",
            headers=candidate_headers,
        ).json()

        for item in detail["items"]:
            assert item["user_answer"] is None
            assert item["explanation"] is None
            assert item["reference_answer"] is None
            assert item["is_correct"] is None
            assert item["score"] is None
            assert "reference_answer" not in item["question"]
            assert "explanation" not in item["question"]

    def test_session_detail_reveals_after_submit(
        self, client, candidate_headers, practice_session
    ):
        item = practice_session.items[0]
        client.post(
            f"/api/practice/sessions/{practice_session.session.id}/items",
            json={"item_id": item.item_id, "user_answer": "我的作答"},
            headers=candidate_headers,
        )

        detail = client.get(
            f"/api/practice/sessions/{practice_session.session.id}",
            headers=candidate_headers,
        ).json()
        submitted = next(
            row for row in detail["items"] if row["item_id"] == item.item_id
        )
        assert submitted["user_answer"] == "我的作答"
        assert submitted["reference_answer"] is not None  # 提交后才下发

    def test_preview_response_has_no_answer_fields(self, client, candidate_headers, practice_questions):
        items = client.get("/api/practice/questions", headers=candidate_headers).json()
        assert items
        for item in items:
            assert "reference_answer" not in item
            assert "explanation" not in item

    def test_other_candidates_session_forbidden(
        self, client, other_candidate_headers, practice_session
    ):
        resp = client.get(
            f"/api/practice/sessions/{practice_session.session.id}",
            headers=other_candidate_headers,
        )
        assert resp.status_code == 403

    def test_own_session_accessible(self, client, candidate_headers, practice_session):
        resp = client.get(
            f"/api/practice/sessions/{practice_session.session.id}",
            headers=candidate_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["session"]["total"] == 4


# ==================== 端点行为 ====================


class TestEndpoints:
    def test_start_and_submit_flow(self, client, candidate_headers, practice_questions):
        created = client.post(
            "/api/practice/sessions", json={"size": 2}, headers=candidate_headers
        )
        assert created.status_code == 201
        body = created.json()
        assert body["session"]["total"] == 2

        item = body["items"][0]
        submitted = client.post(
            f"/api/practice/sessions/{body['session']['id']}/items",
            json={"item_id": item["item_id"], "user_answer": "答案"},
            headers=candidate_headers,
        )
        assert submitted.status_code == 200
        assert submitted.json()["progress"]["answered_count"] == 1

    def test_no_matching_questions_returns_409(self, client, candidate_headers):
        resp = client.post(
            "/api/practice/sessions",
            json={"dimension": "不存在的维度"},
            headers=candidate_headers,
        )
        assert resp.status_code == 409

    def test_size_over_max_returns_400(self, client, candidate_headers):
        resp = client.post(
            "/api/practice/sessions", json={"size": 999}, headers=candidate_headers
        )
        assert resp.status_code == 400

    def test_finish_then_submit_rejected(
        self, client, candidate_headers, practice_session
    ):
        session_id = practice_session.session.id
        assert (
            client.post(
                f"/api/practice/sessions/{session_id}/finish", headers=candidate_headers
            ).status_code
            == 200
        )

        resp = client.post(
            f"/api/practice/sessions/{session_id}/items",
            json={"item_id": practice_session.items[0].item_id, "user_answer": "x"},
            headers=candidate_headers,
        )
        assert resp.status_code == 409

    def test_wrong_book_and_stats(self, client, candidate_headers, practice_session):
        assert client.get("/api/practice/wrong-book", headers=candidate_headers).json() == []

        stats = client.get("/api/practice/stats", headers=candidate_headers).json()
        assert stats["total_answered"] == 0
        assert stats["accuracy"] is None

    def test_wrong_book_limit_capped(self, client, candidate_headers):
        resp = client.get(
            "/api/practice/wrong-book", params={"limit": 9999}, headers=candidate_headers
        )
        assert resp.status_code == 400

    def test_answer_over_max_length_returns_400(
        self, client, candidate_headers, practice_session
    ):
        resp = client.post(
            f"/api/practice/sessions/{practice_session.session.id}/items",
            json={
                "item_id": practice_session.items[0].item_id,
                "user_answer": "x" * 5001,
            },
            headers=candidate_headers,
        )
        assert resp.status_code == 400
