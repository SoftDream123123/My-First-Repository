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
        body = client.get("/api/practice/questions", headers=candidate_headers).json()
        items = body["items"]
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


# ============ MVP-3：按简历推荐（module-20 §7.4 / §7.5）============

SESSION_URL = "/api/practice/sessions"


def _practice_top_level_modules() -> set[str]:
    """`practice/` 下所有文件的**顶层** app.* 导入（函数体内延迟导入不算）。"""
    import ast
    from pathlib import Path

    app_dir = Path(__file__).resolve().parent.parent / "app" / "practice"
    modules: set[str] = set()

    for path in sorted(app_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("app.")
            ):
                modules.update(f"{node.module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                modules.update(
                    alias.name for alias in node.names if alias.name.startswith("app.")
                )

    return modules


class TestResumeRecommendationEndpoint:
    def test_create_response_carries_new_fields(
        self, client, candidate_headers, practice_questions, resume
    ):
        created = client.post(
            SESSION_URL, json={"size": 1, "resume_id": resume.id}, headers=candidate_headers
        )

        assert created.status_code == 201, created.text
        assert created.json()["resume_id"] == resume.id
        assert "resume_match_applied" in created.json()

    def test_session_detail_exposes_new_fields(
        self, client, candidate_headers, practice_questions
    ):
        created = client.post(
            SESSION_URL, json={"size": 1}, headers=candidate_headers
        ).json()
        session_id = created["session"]["id"]

        fetched = client.get(
            f"{SESSION_URL}/{session_id}", headers=candidate_headers
        ).json()

        assert fetched["resume_id"] is None
        assert fetched["resume_match_applied"] is False

    def test_list_items_unchanged(
        self, client, candidate_headers, practice_questions, resume
    ):
        """列表项刻意不加这两个字段（保持轻量，回答的是「练过哪些」）。"""
        client.post(
            SESSION_URL, json={"size": 1, "resume_id": resume.id}, headers=candidate_headers
        )

        listed = client.get(SESSION_URL, headers=candidate_headers).json()

        assert listed
        assert all("resume_id" not in item for item in listed)
        assert all("resume_match_applied" not in item for item in listed)

    def test_preview_ignores_resume_param_and_never_calls_ai(
        self, client, candidate_headers, practice_questions, monkeypatch
    ):
        """预览接口不接 `resume_id`：它不建会话、不写快照，也不该消耗未计入限流的 AI。"""
        from app.ai.mock_provider import MockProvider

        calls: list[dict] = []

        class _Spy(MockProvider):
            def match_questions_by_resume(self, *args, **kwargs):
                calls.append(kwargs)
                return []

        monkeypatch.setattr("app.practice.service.get_provider", lambda: _Spy())

        resp = client.get(
            "/api/practice/questions", params={"resume_id": 1}, headers=candidate_headers
        )

        assert resp.status_code == 200
        assert calls == []

    def test_start_rejects_hr_and_admin(
        self, client, hr_headers, admin_headers, practice_questions
    ):
        for headers in (hr_headers, admin_headers):
            resp = client.post(SESSION_URL, json={"size": 1}, headers=headers)
            assert resp.status_code == 403

    def test_other_candidates_resume_403(
        self, client, candidate_headers, other_resume, practice_questions
    ):
        resp = client.post(
            SESSION_URL,
            json={"size": 1, "resume_id": other_resume.id},
            headers=candidate_headers,
        )
        assert resp.status_code == 403

    def test_missing_resume_404(self, client, candidate_headers, practice_questions):
        resp = client.post(
            SESSION_URL, json={"size": 1, "resume_id": 999999}, headers=candidate_headers
        )
        assert resp.status_code == 404

    def test_resume_id_below_one_is_400(
        self, client, candidate_headers, practice_questions
    ):
        resp = client.post(
            SESSION_URL, json={"size": 1, "resume_id": 0}, headers=candidate_headers
        )
        assert resp.status_code == 400

    def test_ai_failure_still_creates_session(
        self, client, candidate_headers, practice_questions, resume, monkeypatch
    ):
        """AI 推荐失败**不是**错误：照常 201 建会话，只是标记为未按简历推荐。"""
        from app.ai.mock_provider import MockProvider
        from app.core.exceptions import AIProviderError

        class _Failing(MockProvider):
            def match_questions_by_resume(self, *args, **kwargs):
                raise AIProviderError("模拟推荐失败")

        monkeypatch.setattr("app.practice.service.get_provider", lambda: _Failing())

        resp = client.post(
            SESSION_URL, json={"size": 2, "resume_id": resume.id}, headers=candidate_headers
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["resume_match_applied"] is False
        assert resp.json()["resume_id"] == resume.id


class TestModuleBoundaries:
    def test_practice_does_not_import_resume_repository(self):
        """跨模块跳层无人监管（架构测试只看同模块内引用），用静态断言补上。"""
        offenders = [
            module
            for module in _practice_top_level_modules()
            if module.startswith("app.resume") and module != "app.resume.service"
        ]
        assert not offenders, f"practice 越过 resume 的 service 层：{offenders}"

    def test_practice_does_not_import_position(self):
        """取岗位名必须走 question 的既有供给 —— 为拿个名字 import position 会让架构测试变红。"""
        offenders = [
            module
            for module in _practice_top_level_modules()
            if module.startswith("app.position")
        ]
        assert not offenders, f"practice 引入了被禁止的 position 依赖：{offenders}"
