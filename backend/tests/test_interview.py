"""interview 模块测试：出题组装、回答记录、状态机、供给契约、
简历关联 / HR 读简历 / 按简历补题 / 面试前准备助手（MVP-3）。"""

import pytest

from app.ai.mock_provider import MockProvider
from app.core.exceptions import AIProviderError
from app.interview.models import (
    STATUS_COMPLETED,
    STATUS_EVALUATED,
    STATUS_EVALUATING,
    STATUS_ONGOING,
)

DIMS = ["沟通能力", "专业能力", "逻辑思维"]


# ------------------------------ 辅助 ------------------------------


def _create_interview(client, headers, position_id, name="张三", contact=None):
    payload = {"position_id": position_id, "candidate_name": name}
    if contact is not None:
        payload["candidate_contact"] = contact
    return client.post("/api/interviews", json=payload, headers=headers)


def _seed_question(db, position_id, owner_id, dimension, content=None, source="bank"):
    """直接落库一道题，避免走 HTTP 的开销。"""
    from app.question import repository

    question = repository.create(
        db,
        position_id=position_id,
        category="通用",
        dimension=dimension,
        content=content or f"{dimension} 的题目内容描述文本",
        difficulty="medium",
        tags=[],
        source=source,
        created_by=owner_id,
    )
    db.commit()
    return question


@pytest.fixture
def bank(db, position, hr_user):
    """题库：三个维度各 2 题，共 6 题。"""
    for dim in DIMS:
        for i in range(2):
            _seed_question(db, position.id, hr_user.id, dim, f"{dim}题目{i + 1}的内容描述")
    return position


# --------------------------- 鉴权与隔离 ---------------------------


class TestAuthAndIsolation:
    def test_create_without_token(self, client, position):
        assert _create_interview(client, {}, position.id).status_code == 401

    def test_list_only_own_interviews(
        self, client, hr_headers, other_hr_headers, position
    ):
        _create_interview(client, hr_headers, position.id)

        assert len(client.get("/api/interviews", headers=hr_headers).json()) == 1
        assert client.get("/api/interviews", headers=other_hr_headers).json() == []

    def test_admin_sees_all_interviews(
        self, client, hr_headers, admin_headers, position
    ):
        _create_interview(client, hr_headers, position.id)
        assert len(client.get("/api/interviews", headers=admin_headers).json()) == 1

    def test_get_other_users_interview_forbidden(
        self, client, hr_headers, other_hr_headers, position
    ):
        interview_id = _create_interview(client, hr_headers, position.id).json()["id"]

        resp = client.get(f"/api/interviews/{interview_id}", headers=other_hr_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_get_nonexistent_interview(self, client, hr_headers):
        resp = client.get("/api/interviews/999999", headers=hr_headers)
        assert resp.status_code == 404

    def test_save_answer_other_users_interview_forbidden(
        self, client, hr_headers, other_hr_headers, bank
    ):
        detail = _create_interview(client, hr_headers, bank.id).json()
        entry_id = detail["questions"][0]["interview_question_id"]

        resp = client.post(
            f"/api/interviews/{detail['id']}/answers",
            json={"interview_question_id": entry_id, "content": "回答内容"},
            headers=other_hr_headers,
        )
        assert resp.status_code == 403

    def test_complete_other_users_interview_forbidden(
        self, client, hr_headers, other_hr_headers, bank
    ):
        interview_id = _create_interview(client, hr_headers, bank.id).json()["id"]
        resp = client.post(
            f"/api/interviews/{interview_id}/complete", headers=other_hr_headers
        )
        assert resp.status_code == 403


# ---------------------------- 出题组装 ----------------------------


class TestQuestionAssembly:
    def test_generates_n_plus_m_questions(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        assert detail["question_count"] == 8  # 5 题库 + 3 AI

    def test_seq_starts_at_one_and_contiguous(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        seqs = [q["seq"] for q in detail["questions"]]
        assert seqs == list(range(1, 9))

    def test_bank_questions_come_first(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        sources = [q["source"] for q in detail["questions"]]
        assert sources == ["bank"] * 5 + ["ai"] * 3

    def test_snapshots_written(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        for q in detail["questions"]:
            assert q["content"].strip()
            assert q["dimension"] in DIMS
            assert q["source"] in ("bank", "ai")

    def test_dimension_snapshot_matches_bank_question(
        self, client, hr_headers, db, bank
    ):
        detail = _create_interview(client, hr_headers, bank.id).json()
        bank_items = [q for q in detail["questions"] if q["source"] == "bank"]

        from app.question import repository

        for item in bank_items:
            entries = repository.list_by_position(db, None, bank.id)
            by_content = {q.content: q.dimension for q in entries}
            assert by_content[item["content"]] == item["dimension"]

    def test_empty_bank_all_ai(self, client, hr_headers, position):
        detail = _create_interview(client, hr_headers, position.id).json()
        assert detail["question_count"] == 8
        assert all(q["source"] == "ai" for q in detail["questions"])

    def test_insufficient_bank_pads_with_ai(self, client, hr_headers, db, hr_user, position):
        _seed_question(db, position.id, hr_user.id, "沟通能力", "仅有的两道题之一内容")
        _seed_question(db, position.id, hr_user.id, "专业能力", "仅有的两道题之二内容")

        detail = _create_interview(client, hr_headers, position.id).json()
        assert detail["question_count"] == 8
        sources = [q["source"] for q in detail["questions"]]
        assert sources.count("bank") == 2
        assert sources.count("ai") == 6

    def test_dimension_round_robin(self, client, hr_headers, db, hr_user, position):
        """单维度题量充足时不会把其他维度抽空。"""
        for i in range(10):
            _seed_question(db, position.id, hr_user.id, "沟通能力", f"沟通题{i}的内容描述")

        detail = _create_interview(client, hr_headers, position.id).json()
        bank_dims = [q["dimension"] for q in detail["questions"] if q["source"] == "bank"]
        # 沟通能力有 10 题，但仍按维度轮询 —— 其他维度无题可抽，故全部来自沟通能力
        assert len(bank_dims) == 5

    def test_stale_dimension_skipped(self, client, hr_headers, db, hr_user, position):
        """dimension 已不在岗位维度内的题目不被抽取。"""
        _seed_question(db, position.id, hr_user.id, "已废弃维度", "这道题的维度已经不在岗位上了")

        detail = _create_interview(client, hr_headers, position.id).json()
        assert all(q["dimension"] in DIMS for q in detail["questions"])
        assert all("已废弃维度" not in q["content"] for q in detail["questions"])

    def test_ai_questions_saved_to_bank(self, client, hr_headers, db, hr_user, position):
        _create_interview(client, hr_headers, position.id)
        db.rollback()

        from app.question import repository

        candidates = repository.list_by_position(db, hr_user.id, position.id)
        ai_questions = [q for q in candidates if q.source == "ai"]
        assert len(ai_questions) == 8
        assert all(q.created_by == hr_user.id for q in ai_questions)

    def test_ai_failure_rolls_back_everything(
        self, client, hr_headers, db, hr_user, position, monkeypatch
    ):
        from app.ai.mock_provider import MockProvider
        from app.core.exceptions import AIProviderError

        class FailingProvider(MockProvider):
            """只把出题那一路打断，其余能力沿用 Mock。

            继承 `MockProvider` 而不是直接实现 `AIProvider`：后者是 ABC，每新增
            一个抽象方法（如 module-18 的两个简历驱动方法）都会让本类无法实例化，
            表现为整个测试报 TypeError 而非这条断言失败 —— 与本用例要验证的
            「AI 失败时事务回滚」毫无关系。继承 Mock 后，接口增长不再波及这里。
            """

            def generate_questions(self, *a, **kw):
                raise AIProviderError("模拟出题失败")

        monkeypatch.setattr(
            "app.interview.service.get_provider", lambda: FailingProvider()
        )

        resp = _create_interview(client, hr_headers, position.id)
        assert resp.status_code == 502
        assert resp.json()["code"] == "AI_PROVIDER_ERROR"

        db.rollback()
        from app.interview import repository as interview_repo
        from app.question import repository as question_repo

        assert interview_repo.list_by_owner(db, None) == []
        assert question_repo.list_by_position(db, None, position.id) == []

    def test_create_with_invisible_position(self, client, other_hr_headers, position):
        resp = _create_interview(client, other_hr_headers, position.id)
        assert resp.status_code == 403

    def test_create_with_nonexistent_position(self, client, hr_headers):
        assert _create_interview(client, hr_headers, 999999).status_code == 404

    def test_generation_is_deterministic(self, client, hr_headers, bank):
        first = _create_interview(client, hr_headers, bank.id, name="甲").json()
        second = _create_interview(client, hr_headers, bank.id, name="乙").json()

        assert [q["content"] for q in first["questions"]] == [
            q["content"] for q in second["questions"]
        ]

    def test_status_is_ongoing_after_create(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        assert detail["status"] == STATUS_ONGOING


# ---------------------------- 回答记录 ----------------------------


class TestAnswerRecording:
    @pytest.fixture
    def interview(self, client, hr_headers, bank):
        return _create_interview(client, hr_headers, bank.id).json()

    def _save(self, client, headers, interview, entry_id, content):
        return client.post(
            f"/api/interviews/{interview['id']}/answers",
            json={"interview_question_id": entry_id, "content": content},
            headers=headers,
        )

    def test_save_answer_ok(self, client, hr_headers, interview):
        entry_id = interview["questions"][0]["interview_question_id"]
        resp = self._save(client, hr_headers, interview, entry_id, "这是我的回答内容")

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "这是我的回答内容"
        assert body["recorded_at"] is not None

    def test_save_answer_updates_existing(self, client, hr_headers, db, interview):
        entry_id = interview["questions"][0]["interview_question_id"]

        self._save(client, hr_headers, interview, entry_id, "第一次回答的内容")
        self._save(client, hr_headers, interview, entry_id, "第二次修改后的回答内容")

        db.rollback()
        from app.interview import repository

        answers = repository.list_answers(db, interview["id"])
        assert len(answers) == 1
        assert answers[0].content == "第二次修改后的回答内容"

    def test_save_empty_answer_allowed(self, client, hr_headers, interview):
        entry_id = interview["questions"][0]["interview_question_id"]
        resp = self._save(client, hr_headers, interview, entry_id, "")
        assert resp.status_code == 200
        assert resp.json()["answer"] == ""

    def test_save_answer_wrong_interview(self, client, hr_headers, interview, bank):
        other = _create_interview(client, hr_headers, bank.id, name="李四").json()
        foreign_entry = other["questions"][0]["interview_question_id"]

        resp = self._save(client, hr_headers, interview, foreign_entry, "串场回答")
        assert resp.status_code == 404

    def test_save_answer_content_too_long(self, client, hr_headers, interview):
        entry_id = interview["questions"][0]["interview_question_id"]
        resp = self._save(client, hr_headers, interview, entry_id, "字" * 10001)
        assert resp.status_code == 400

    def test_save_answer_not_ongoing(self, client, hr_headers, interview):
        entry_id = interview["questions"][0]["interview_question_id"]
        client.post(f"/api/interviews/{interview['id']}/complete", headers=hr_headers)

        resp = self._save(client, hr_headers, interview, entry_id, "完成后修改")
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"


# ------------------------------ 状态机 ------------------------------


class TestStateMachine:
    @pytest.fixture
    def interview(self, client, hr_headers, bank):
        return _create_interview(client, hr_headers, bank.id).json()

    def test_complete_from_ongoing(self, client, hr_headers, interview):
        resp = client.post(
            f"/api/interviews/{interview['id']}/complete", headers=hr_headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == STATUS_COMPLETED
        assert resp.json()["completed_at"] is not None

    def test_complete_twice_rejected(self, client, hr_headers, interview):
        client.post(f"/api/interviews/{interview['id']}/complete", headers=hr_headers)
        resp = client.post(
            f"/api/interviews/{interview['id']}/complete", headers=hr_headers
        )
        assert resp.status_code == 409

    def test_rollback_from_completed(self, client, hr_headers, interview):
        client.post(f"/api/interviews/{interview['id']}/complete", headers=hr_headers)

        resp = client.post(
            f"/api/interviews/{interview['id']}/rollback", headers=hr_headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == STATUS_ONGOING
        assert resp.json()["completed_at"] is None

    def test_rollback_from_ongoing_rejected(self, client, hr_headers, interview):
        resp = client.post(
            f"/api/interviews/{interview['id']}/rollback", headers=hr_headers
        )
        assert resp.status_code == 409

    def test_error_detail_contains_from_and_to(self, client, hr_headers, interview):
        resp = client.post(
            f"/api/interviews/{interview['id']}/rollback", headers=hr_headers
        )
        detail = resp.json()["detail"]
        assert detail["from"] == STATUS_ONGOING
        assert detail["to"] == STATUS_ONGOING


def _complete(db, interview):
    """把面试推进到 completed —— 触发评估的前置状态。"""
    from app.auth import repository as auth_repository
    from app.interview import service

    owner = auth_repository.get_by_id(db, interview.created_by)
    service.complete_interview(db, owner, interview.id)


class TestStateMachineServiceLevel:
    """直接调用迁移方法，覆盖端点上没有暴露的路径。"""

    @pytest.fixture
    def interview(self, client, hr_headers, db, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        db.rollback()
        from app.interview import repository

        return repository.get_by_id(db, detail["id"])

    def test_transition_to_evaluating_from_ongoing_rejected(self, db, interview):
        from app.core.exceptions import BusinessError
        from app.interview import service

        with pytest.raises(BusinessError):
            service.transition_to_evaluating(db, interview.id)

    def test_transition_to_evaluated_requires_evaluating(self, db, interview):
        from app.core.exceptions import BusinessError
        from app.interview import service

        _complete(db, interview)

        with pytest.raises(BusinessError):
            service.transition_to_evaluated(db, interview.id)

    def test_transition_back_to_completed_from_evaluating(self, db, interview):
        from app.interview import repository, service

        _complete(db, interview)
        service.transition_to_evaluating(db, interview.id)
        service.transition_back_to_completed(db, interview.id)

        assert repository.get_by_id(db, interview.id).status == STATUS_COMPLETED

    def test_reevaluate_from_evaluated(self, db, interview):
        from app.interview import repository, service

        _complete(db, interview)
        service.transition_to_evaluating(db, interview.id)
        service.transition_to_evaluated(db, interview.id)
        service.transition_to_evaluating(db, interview.id)  # 重新评估

        assert repository.get_by_id(db, interview.id).status == STATUS_EVALUATING

    def test_rollback_from_evaluated(self, db, interview):
        from app.auth import repository as auth_repository
        from app.interview import repository, service

        _complete(db, interview)
        service.transition_to_evaluating(db, interview.id)
        service.transition_to_evaluated(db, interview.id)

        owner = auth_repository.get_by_id(db, interview.created_by)
        service.rollback_interview(db, owner, interview.id)

        assert repository.get_by_id(db, interview.id).status == STATUS_ONGOING

    def test_complete_twice_rejected_at_service_level(self, db, interview):
        from app.auth import repository as auth_repository
        from app.core.exceptions import BusinessError
        from app.interview import service

        owner = auth_repository.get_by_id(db, interview.created_by)
        service.complete_interview(db, owner, interview.id)

        with pytest.raises(BusinessError):
            service.complete_interview(db, owner, interview.id)


class TestIllegalTransitionsOverHttp:
    """计划书 §5.4.3 的「操作矩阵」在端点层逐格成立。

    service 层已由 test_state_machine_matrix.py 覆盖全矩阵；这里补的是
    「端点确实把这些非法操作挡住了」—— 两者缺一不可。
    """

    @pytest.fixture
    def ongoing_row(self, client, hr_headers, db, bank):
        """绕过 HTTP 取到 ORM 对象，便于直接推进状态。"""
        detail = _create_interview(client, hr_headers, bank.id).json()
        db.rollback()
        from app.interview import repository

        return repository.get_by_id(db, detail["id"])

    def test_save_answer_when_evaluating_rejected(
        self, client, hr_headers, db, ongoing_row
    ):
        from app.interview import repository, service

        _complete(db, ongoing_row)
        service.transition_to_evaluating(db, ongoing_row.id)

        entry_id = repository.list_questions(db, ongoing_row.id)[0].id
        resp = client.post(
            f"/api/interviews/{ongoing_row.id}/answers",
            json={"interview_question_id": entry_id, "content": "评估中修改的回答"},
            headers=hr_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

    def test_complete_from_evaluated_rejected(
        self, client, hr_headers, db, ongoing_row
    ):
        from app.interview import service

        _complete(db, ongoing_row)
        service.transition_to_evaluating(db, ongoing_row.id)
        service.transition_to_evaluated(db, ongoing_row.id)

        resp = client.post(
            f"/api/interviews/{ongoing_row.id}/complete", headers=hr_headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

    def test_rollback_from_evaluating_rejected(
        self, client, hr_headers, db, ongoing_row
    ):
        from app.interview import service

        _complete(db, ongoing_row)
        service.transition_to_evaluating(db, ongoing_row.id)

        resp = client.post(
            f"/api/interviews/{ongoing_row.id}/rollback", headers=hr_headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"


# --------------------------- 候选人信息 ---------------------------


class TestCandidateUpdate:
    @pytest.fixture
    def interview(self, client, hr_headers, bank):
        return _create_interview(client, hr_headers, bank.id, contact="old@example.com").json()

    def _patch(self, client, headers, interview_id, payload):
        return client.patch(
            f"/api/interviews/{interview_id}", json=payload, headers=headers
        )

    def test_update_when_ongoing(self, client, hr_headers, interview):
        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_name": "新名字"}
        )
        assert resp.status_code == 200
        assert resp.json()["candidate_name"] == "新名字"

    def test_update_when_completed(self, client, hr_headers, interview):
        client.post(f"/api/interviews/{interview['id']}/complete", headers=hr_headers)

        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_name": "完成后改名"}
        )
        assert resp.status_code == 200

    def test_update_when_evaluating(self, client, hr_headers, db, interview):
        from app.auth import repository as auth_repository
        from app.interview import repository, service

        obj = repository.get_by_id(db, interview["id"])
        owner = auth_repository.get_by_id(db, obj.created_by)
        service.complete_interview(db, owner, obj.id)
        service.transition_to_evaluating(db, obj.id)

        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_name": "评估中改名"}
        )
        assert resp.status_code == 409

    def test_update_when_evaluated(self, client, hr_headers, db, interview):
        from app.auth import repository as auth_repository
        from app.interview import repository, service

        obj = repository.get_by_id(db, interview["id"])
        owner = auth_repository.get_by_id(db, obj.created_by)
        service.complete_interview(db, owner, obj.id)
        service.transition_to_evaluating(db, obj.id)
        service.transition_to_evaluated(db, obj.id)

        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_name": "评估后改名"}
        )
        assert resp.status_code == 409

    def test_update_does_not_change_status(self, client, hr_headers, interview):
        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_name": "改名"}
        )
        assert resp.json()["status"] == STATUS_ONGOING

    def test_name_too_long(self, client, hr_headers, interview):
        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_name": "字" * 101}
        )
        assert resp.status_code == 400

    def test_clear_contact(self, client, hr_headers, interview):
        resp = self._patch(
            client, hr_headers, interview["id"], {"candidate_contact": None}
        )
        assert resp.status_code == 200
        assert resp.json()["candidate_contact"] is None


# ---------------------------- 详情与列表 ----------------------------


class TestDetailAndList:
    def test_detail_includes_questions_ordered_by_seq(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        seqs = [q["seq"] for q in detail["questions"]]
        assert seqs == sorted(seqs)

    def test_unanswered_question_answer_is_none(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        assert all(q["answer"] is None for q in detail["questions"])

    def test_list_includes_position_name(self, client, hr_headers, bank):
        _create_interview(client, hr_headers, bank.id)
        item = client.get("/api/interviews", headers=hr_headers).json()[0]
        assert item["position_name"] == bank.name

    def test_list_includes_counts(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        entry_id = detail["questions"][0]["interview_question_id"]

        client.post(
            f"/api/interviews/{detail['id']}/answers",
            json={"interview_question_id": entry_id, "content": "回答内容"},
            headers=hr_headers,
        )

        item = client.get("/api/interviews", headers=hr_headers).json()[0]
        assert item["question_count"] == 8
        assert item["answered_count"] == 1

    def test_empty_answer_not_counted(self, client, hr_headers, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        entry_id = detail["questions"][0]["interview_question_id"]

        client.post(
            f"/api/interviews/{detail['id']}/answers",
            json={"interview_question_id": entry_id, "content": ""},
            headers=hr_headers,
        )

        item = client.get("/api/interviews", headers=hr_headers).json()[0]
        assert item["answered_count"] == 0

    def test_detail_uses_snapshot_not_live_question(
        self, client, hr_headers, db, bank
    ):
        """修改题库题目后，面试详情仍显示出题时的快照。"""
        detail = _create_interview(client, hr_headers, bank.id).json()
        original = next(q for q in detail["questions"] if q["source"] == "bank")

        from app.question import repository

        question = repository.list_by_position(db, None, bank.id)[0]
        question.content = "被彻底改写的题干内容"
        db.commit()
        db.rollback()

        refreshed = client.get(
            f"/api/interviews/{detail['id']}", headers=hr_headers
        ).json()
        same_entry = next(
            q
            for q in refreshed["questions"]
            if q["interview_question_id"] == original["interview_question_id"]
        )
        assert same_entry["content"] == original["content"]


# ------------------------ 对 evaluation 的供给 ------------------------


class TestEvaluationSupply:
    @pytest.fixture
    def interview(self, client, hr_headers, db, bank):
        detail = _create_interview(client, hr_headers, bank.id).json()
        db.rollback()
        return detail

    def test_answers_shape(self, db, interview):
        from app.interview import service

        pairs = service.get_answers_for_evaluation(db, interview["id"])
        assert len(pairs) == 8
        assert all(p.dimension in DIMS for p in pairs)
        assert all(p.question for p in pairs)

    def test_answers_ordered_by_seq(self, db, interview):
        from app.interview import service

        pairs = service.get_answers_for_evaluation(db, interview["id"])
        expected = [q["content"] for q in interview["questions"]]
        assert [p.question for p in pairs] == expected

    def test_unanswered_is_none(self, db, interview):
        from app.interview import service

        pairs = service.get_answers_for_evaluation(db, interview["id"])
        assert all(p.answer is None for p in pairs)

    def test_empty_answer_treated_as_none(self, client, hr_headers, db, interview):
        from app.interview import service

        entry_id = interview["questions"][0]["interview_question_id"]
        client.post(
            f"/api/interviews/{interview['id']}/answers",
            json={"interview_question_id": entry_id, "content": ""},
            headers=hr_headers,
        )
        db.rollback()

        pairs = service.get_answers_for_evaluation(db, interview["id"])
        first = next(p for p in pairs if p.question == interview["questions"][0]["content"])
        assert first.answer is None

    def test_uses_snapshot_dimension_and_question(self, db, interview):
        from app.interview import service

        pairs = service.get_answers_for_evaluation(db, interview["id"])
        by_question = {q["content"]: q["dimension"] for q in interview["questions"]}
        for pair in pairs:
            assert by_question[pair.question] == pair.dimension

    def test_get_evaluation_dimensions_from_position(self, db, bank, interview):
        from app.interview import service

        assert service.get_evaluation_dimensions(db, interview["id"]) == DIMS

    def test_get_position_id(self, db, bank, interview):
        from app.interview import service

        assert service.get_position_id(db, interview["id"]) == bank.id


# ============ MVP-3：简历关联 / HR 读简历 / 按简历补题 / 准备助手 ============
# 对应计划书 module-19 §7.1 – §7.5。

MATCH_URL = "/api/interviews/{}/questions/match"
PREP_URL = "/api/interviews/{}/prep"
LINK_URL = "/api/candidate/interviews/{}/resume"
HR_RESUME_URL = "/api/interviews/{}/resume"


def _fresh(db):
    """结束当前事务，让随后的读能看到别的连接刚提交的数据（REPEATABLE READ）。"""
    db.rollback()


def _row(db, interview_id):
    from app.interview import repository as interview_repo

    return interview_repo.get_by_id(db, interview_id)


def _advance(db, interview_id, target, owner):
    """用**真实的状态机迁移**把面试推到目标状态（不直接赋值绕过校验）。"""
    from app.interview import service

    if target == STATUS_ONGOING:
        return

    # 面试是经 HTTP 创建的（另一个连接提交），而 db 会话可能还停在更早的快照上
    # —— REPEATABLE READ 下会读到「面试不存在」。先结束当前事务再读。
    _fresh(db)

    service.complete_interview(db, owner, interview_id)
    if target == STATUS_COMPLETED:
        return

    service.begin_evaluation(db, interview_id)
    if target == STATUS_EVALUATING:
        return

    service.transition_to_evaluated(db, interview_id)


def _draft_interview(db, position, owner, name="张三"):
    """直接落一条 draft 面试 —— 经 HTTP 创建必然是 ongoing，draft 只能这样造。"""
    from app.interview import repository as interview_repo

    interview = interview_repo.create_interview(
        db,
        position_id=position.id,
        candidate_name=name,
        contact=None,
        created_by=owner.id,
    )
    db.commit()
    db.refresh(interview)
    return interview


def _hr_detail(client, hr_headers, interview_id):
    resp = client.get(f"/api/interviews/{interview_id}", headers=hr_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _seed_pool(db, position, owner, count=4, prefix="补题池"):
    """在**面试创建之后**再落一批题库题，作为补题的候选池。

    必须在面试之后：`linked_interview` 的面试是在空题库下创建的，出题组装会把
    8 道 AI 题一并写进题库，而它们又都在本场面试里 —— 于是
    「岗位题库 − 本场已有题」是空的，补题会直接 409。
    写成夹具也不行：夹具与 `linked_interview` 之间没有执行顺序保证，
    若题库先就位，那些题会被出题组装抽走，池子又空了。
    """
    return [
        _seed_question(
            db,
            position.id,
            owner.id,
            DIMS[i % len(DIMS)],
            f"{prefix}第{i}题的内容描述文本",
        )
        for i in range(count)
    ]


def _match(client, headers, interview_id, body=None):
    """按简历补题。`body=None` 时**不带请求体** —— 缺省题数取配置项。"""
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    return client.post(MATCH_URL.format(interview_id), **kwargs)


def _prep_row(db, interview_id):
    """(generated_at, edited_at, 行数) —— 用于断言「失败时什么都没发生」。"""
    from sqlalchemy import func, select

    from app.interview.models import InterviewPrep

    prep = (
        db.execute(
            select(InterviewPrep).where(InterviewPrep.interview_id == interview_id)
        )
        .scalars()
        .first()
    )
    total = db.execute(
        select(func.count(InterviewPrep.id)).where(
            InterviewPrep.interview_id == interview_id
        )
    ).scalar_one()
    if prep is None:
        return None, None, total
    return prep.generated_at, prep.edited_at, total


class _MatchProvider(MockProvider):
    """只覆写按简历匹配那一路，用于精确控场；其余能力沿用 Mock。"""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def match_questions_by_resume(self, *args, **kwargs):
        if self._error is not None:
            raise AIProviderError(self._error)
        return list(self._result or [])


class _PrepProvider(MockProvider):
    """只覆写准备提纲那一路（error 非空时模拟 AI 故障）。"""

    def __init__(self, error=None):
        self._error = error

    def generate_interview_prep(self, *args, **kwargs):
        if self._error is not None:
            raise AIProviderError(self._error)
        return super().generate_interview_prep(*args, **kwargs)


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr("app.interview.service.get_provider", lambda: provider)


# ==================== §7.1 候选人关联简历 ====================


class TestLinkResume:
    def _link(self, client, headers, interview_id, resume_id):
        return client.put(
            LINK_URL.format(interview_id),
            json={"resume_id": resume_id},
            headers=headers,
        )

    def test_link_resume_ok(
        self, client, db, accepted_interview, candidate_headers, resume
    ):
        interview_id = accepted_interview["interview_id"]

        resp = self._link(client, candidate_headers, interview_id, resume.id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["resume_id"] == resume.id

        _fresh(db)
        assert _row(db, interview_id).resume_id == resume.id

    def test_link_resume_null_unlinks(
        self, client, db, accepted_interview, candidate_headers, resume
    ):
        interview_id = accepted_interview["interview_id"]
        self._link(client, candidate_headers, interview_id, resume.id)

        resp = self._link(client, candidate_headers, interview_id, None)
        assert resp.status_code == 200
        assert resp.json() is None

        _fresh(db)
        assert _row(db, interview_id).resume_id is None

    def test_link_resume_other_candidates_resume_403(
        self, client, db, accepted_interview, candidate_headers, other_resume
    ):
        interview_id = accepted_interview["interview_id"]

        resp = self._link(client, candidate_headers, interview_id, other_resume.id)
        assert resp.status_code == 403

        _fresh(db)
        assert _row(db, interview_id).resume_id is None  # 归属校验失败时不写入

    def test_link_resume_missing_resume_404(
        self, client, accepted_interview, candidate_headers
    ):
        resp = self._link(
            client, candidate_headers, accepted_interview["interview_id"], 999999
        )
        assert resp.status_code == 404

    def test_link_resume_without_invitation_403(
        self, client, hr_headers, position, candidate_headers, resume
    ):
        interview_id = _create_interview(client, hr_headers, position.id).json()["id"]

        resp = self._link(client, candidate_headers, interview_id, resume.id)
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "target", [STATUS_COMPLETED, STATUS_EVALUATING, STATUS_EVALUATED]
    )
    def test_link_resume_after_ongoing_409(
        self, client, db, accepted_interview, candidate_headers, resume, hr_user, target
    ):
        """白名单写法的关键覆盖：evaluating / evaluated 也是候选人可达的状态。"""
        interview_id = accepted_interview["interview_id"]
        _advance(db, interview_id, target, hr_user)

        resp = self._link(client, candidate_headers, interview_id, resume.id)
        assert resp.status_code == 409

        _fresh(db)
        assert _row(db, interview_id).resume_id is None

    def test_link_resume_does_not_change_interview_status(
        self, client, db, accepted_interview, candidate_headers, resume
    ):
        interview_id = accepted_interview["interview_id"]
        self._link(client, candidate_headers, interview_id, resume.id)

        _fresh(db)
        assert _row(db, interview_id).status == STATUS_ONGOING

    def test_link_resume_replaces_previous(
        self, client, db, accepted_interview, candidate_headers, resume
    ):
        interview_id = accepted_interview["interview_id"]
        second = client.post(
            "/api/candidate/resumes",
            json={"title": "第二份简历", "content": "另一份简历的正文内容描述。"},
            headers=candidate_headers,
        ).json()

        self._link(client, candidate_headers, interview_id, resume.id)
        self._link(client, candidate_headers, interview_id, second["id"])

        _fresh(db)
        assert _row(db, interview_id).resume_id == second["id"]


# ==================== §7.2 HR 读取关联简历 ====================


class TestHrReadsInterviewResume:
    def test_ok(self, client, hr_headers, linked_interview, resume):
        body = client.get(
            HR_RESUME_URL.format(linked_interview["interview_id"]), headers=hr_headers
        ).json()

        assert body["resume_id"] == resume.id
        assert body["title"] == resume.title
        assert body["content"] == resume.content

    def test_unlinked_404(self, client, hr_headers, accepted_interview):
        """未关联是 404 而非 403 —— 前端据此显示「候选人尚未提交简历」。"""
        resp = client.get(
            HR_RESUME_URL.format(accepted_interview["interview_id"]), headers=hr_headers
        )
        assert resp.status_code == 404

    def test_other_hrs_interview_403(self, client, other_hr_headers, linked_interview):
        resp = client.get(
            HR_RESUME_URL.format(linked_interview["interview_id"]),
            headers=other_hr_headers,
        )
        assert resp.status_code == 403

    def test_excludes_created_by_and_has_updated_at(
        self, client, hr_headers, linked_interview
    ):
        body = client.get(
            HR_RESUME_URL.format(linked_interview["interview_id"]), headers=hr_headers
        ).json()

        assert "created_by" not in body
        assert "created_at" not in body
        assert body["updated_at"]  # HR 据此判断手上这份是否最新

    def test_rejects_candidate(self, client, candidate_headers, linked_interview):
        resp = client.get(
            HR_RESUME_URL.format(linked_interview["interview_id"]),
            headers=candidate_headers,
        )
        assert resp.status_code == 403


# ==================== §7.3 按简历补题（本模块最重要的测试组）====================


class TestMatchQuestionsByResume:
    def test_appends_questions(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        before = _hr_detail(client, hr_headers, interview_id)["question_count"]

        body = _match(client, hr_headers, interview_id).json()

        assert body["added_count"] > 0
        assert len(body["added"]) == body["added_count"]
        assert body["total_questions"] == before + body["added_count"]
        assert (
            _hr_detail(client, hr_headers, interview_id)["question_count"]
            == before + body["added_count"]
        )

    def test_sets_source_and_reason(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        added = _match(client, hr_headers, interview_id).json()["added"]
        added_ids = {item["interview_question_id"] for item in added}

        questions = _hr_detail(client, hr_headers, interview_id)["questions"]
        matched = [q for q in questions if q["interview_question_id"] in added_ids]
        others = [q for q in questions if q["interview_question_id"] not in added_ids]

        assert all(q["source"] == "resume_match" for q in matched)
        assert all(q["match_reason"] for q in matched)
        # 非匹配来源的题：match_reason 恒为 null，来源也不是 resume_match
        assert all(q["match_reason"] is None for q in others)
        assert all(q["source"] != "resume_match" for q in others)

    def test_seq_continues(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        before = [
            q["seq"] for q in _hr_detail(client, hr_headers, interview_id)["questions"]
        ]

        added = _match(client, hr_headers, interview_id).json()["added"]
        added_seqs = [item["seq"] for item in added]

        assert added_seqs == list(range(max(before) + 1, max(before) + 1 + len(added)))
        assert not (set(added_seqs) & set(before))  # 与既有 seq 不重号

    def test_does_not_touch_existing_questions(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        before = [
            (q["interview_question_id"], q["content"], q["source"], q["match_reason"])
            for q in _hr_detail(client, hr_headers, interview_id)["questions"]
        ]

        _match(client, hr_headers, interview_id)

        kept = {row[0] for row in before}
        after = [
            (q["interview_question_id"], q["content"], q["source"], q["match_reason"])
            for q in _hr_detail(client, hr_headers, interview_id)["questions"]
            if q["interview_question_id"] in kept
        ]
        assert after == before

    def test_without_resume_409(self, client, hr_headers, accepted_interview):
        resp = _match(client, hr_headers, accepted_interview["interview_id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

    @pytest.mark.parametrize(
        "target", [STATUS_COMPLETED, STATUS_EVALUATING, STATUS_EVALUATED]
    )
    def test_non_ongoing_409(
        self, client, db, hr_headers, linked_interview, hr_user, target
    ):
        interview_id = linked_interview["interview_id"]
        _advance(db, interview_id, target, hr_user)

        assert _match(client, hr_headers, interview_id).status_code == 409

    def test_draft_409(self, client, db, hr_headers, position, hr_user):
        draft = _draft_interview(db, position, hr_user)
        assert _match(client, hr_headers, draft.id).status_code == 409

    def test_excludes_questions_already_in_interview(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        existing = {
            q["interview_question_id"]
            for q in _hr_detail(client, hr_headers, interview_id)["questions"]
        }

        added = _match(client, hr_headers, interview_id).json()["added"]

        assert not ({item["interview_question_id"] for item in added} & existing)

    def test_repeated_call_adds_new_questions_only(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        interview_id = linked_interview["interview_id"]
        for i in range(6):  # 保证池子够两轮
            _seed_question(
                db, position.id, hr_user.id, DIMS[i % 3], f"两轮补题题干{i}的内容描述"
            )

        first = {
            item["interview_question_id"]
            for item in _match(client, hr_headers, interview_id).json()["added"]
        }
        second = {
            item["interview_question_id"]
            for item in _match(client, hr_headers, interview_id).json()["added"]
        }

        assert first and second
        assert not (first & second)  # 两次追加无交集（但都非空 → 会累加）

    def test_repeated_call_never_duplicates(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        interview_id = linked_interview["interview_id"]
        _seed_pool(db, position, hr_user, count=9)
        for _ in range(3):
            _match(client, hr_headers, interview_id)

        _fresh(db)
        from app.interview import repository as interview_repo

        question_ids = [
            entry.question_id
            for entry in interview_repo.list_questions(db, interview_id)
        ]
        assert len(question_ids) == len(set(question_ids))

    def test_exhausts_pool_then_409(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        interview_id = linked_interview["interview_id"]
        _seed_pool(db, position, hr_user)

        _match(client, hr_headers, interview_id, {"count": 20})  # 一次把池子取尽
        resp = _match(client, hr_headers, interview_id, {"count": 20})

        assert resp.status_code == 409
        assert "没有可补充" in resp.json()["message"]

    def test_ai_returns_empty_gives_200(
        self, client, db, hr_headers, linked_interview, position, hr_user, monkeypatch
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        before = _hr_detail(client, hr_headers, interview_id)["question_count"]
        _use_provider(monkeypatch, _MatchProvider(result=[]))

        resp = _match(client, hr_headers, interview_id)

        assert resp.status_code == 200
        assert resp.json()["added_count"] == 0
        assert resp.json()["total_questions"] == before
        _fresh(db)
        assert _hr_detail(client, hr_headers, interview_id)["question_count"] == before

    def test_ai_failure_leaves_interview_unchanged(
        self, client, db, hr_headers, linked_interview, position, hr_user, monkeypatch
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        before = _hr_detail(client, hr_headers, interview_id)["questions"]
        _use_provider(monkeypatch, _MatchProvider(error="模拟匹配失败"))

        resp = _match(client, hr_headers, interview_id)

        assert resp.status_code == 502
        assert resp.json()["code"] == "AI_PROVIDER_ERROR"
        _fresh(db)
        assert _hr_detail(client, hr_headers, interview_id)["questions"] == before

    def test_ai_failure_does_not_commit(
        self, client, db, hr_headers, linked_interview, position, hr_user, monkeypatch
    ):
        """失败后不得留下任何半写的匹配题（把「没有」与「坏了」分开看）。"""
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        _use_provider(monkeypatch, _MatchProvider(error="模拟匹配失败"))
        assert _match(client, hr_headers, interview_id).status_code == 502

        _fresh(db)
        from app.interview import repository as interview_repo

        entries = interview_repo.list_questions(db, interview_id)
        assert all(entry.source_snapshot != "resume_match" for entry in entries)
        assert all(entry.match_reason is None for entry in entries)

    def test_drops_ids_outside_pool(
        self, client, db, hr_headers, linked_interview, position, hr_user, monkeypatch
    ):
        from app.ai.base import MatchedQuestion

        interview_id = linked_interview["interview_id"]
        real = _seed_question(
            db, position.id, hr_user.id, DIMS[0], "池内合法题干的内容描述"
        )
        _use_provider(
            monkeypatch,
            _MatchProvider(
                result=[
                    MatchedQuestion(question_id=999999, reason="编造的题"),
                    MatchedQuestion(question_id=real.id, reason="池内真实题目"),
                ]
            ),
        )

        body = _match(client, hr_headers, interview_id).json()

        assert body["added_count"] == 1
        assert body["added"][0]["content"] == real.content

    def test_count_default_from_config(
        self, client, db, hr_headers, linked_interview, position, hr_user, monkeypatch
    ):
        from app.core.config import get_settings

        for i in range(5):
            _seed_question(
                db, position.id, hr_user.id, DIMS[i % 3], f"配置题数题干{i}的内容描述"
            )
        monkeypatch.setenv("RESUME_MATCH_COUNT", "2")
        get_settings.cache_clear()
        try:
            body = _match(client, hr_headers, linked_interview["interview_id"]).json()
            assert body["added_count"] == 2
        finally:
            get_settings.cache_clear()

    def test_count_capped(self, client, hr_headers, linked_interview):
        resp = _match(
            client, hr_headers, linked_interview["interview_id"], {"count": 21}
        )
        assert resp.status_code == 400

    def test_pool_comes_from_position_question_bank(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        """候选池与出题组装同源：岗位题库里的题确实能被补进来。"""
        seeded = _seed_question(
            db, position.id, hr_user.id, DIMS[0], "同源验证题题干的内容描述文本"
        )

        added = _match(
            client, hr_headers, linked_interview["interview_id"], {"count": 20}
        ).json()["added"]

        assert seeded.id in {item["interview_question_id"] for item in added}

    def test_filters_invalid_dimensions(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        """维度已不在岗位维度内的历史题不得被选中（与出题组装同一判据）。"""
        _seed_pool(db, position, hr_user)
        stale = _seed_question(
            db, position.id, hr_user.id, "已废弃维度", "历史遗留题题干的内容描述"
        )

        added = _match(
            client, hr_headers, linked_interview["interview_id"], {"count": 20}
        ).json()["added"]

        assert added  # 池子里有合规题，证明不是「因为池子空才没有它」
        assert stale.id not in {item["interview_question_id"] for item in added}

    def test_other_hrs_interview_403(self, client, other_hr_headers, linked_interview):
        resp = _match(client, other_hr_headers, linked_interview["interview_id"])
        assert resp.status_code == 403

    def test_response_includes_reason_for_ui(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        added = _match(client, hr_headers, linked_interview["interview_id"]).json()[
            "added"
        ]

        assert added
        assert all(item["match_reason"] for item in added)

    def test_rejects_candidate(self, client, candidate_headers, linked_interview):
        resp = _match(client, candidate_headers, linked_interview["interview_id"])
        assert resp.status_code == 403


# ==================== §7.4 面试前准备助手 ====================


class TestInterviewPrep:
    @pytest.fixture
    def interview(self, client, hr_headers, position):
        """ongoing 面试（创建即同步出题，Mock 会补足题量）。"""
        return _create_interview(client, hr_headers, position.id).json()

    def _generate(self, client, hr_headers, interview_id):
        return client.post(PREP_URL.format(interview_id), headers=hr_headers)

    def _get(self, client, hr_headers, interview_id):
        return client.get(PREP_URL.format(interview_id), headers=hr_headers)

    def _update(self, client, hr_headers, interview_id, payload):
        return client.put(PREP_URL.format(interview_id), json=payload, headers=hr_headers)

    def test_generate_prep_persists_three_sections(
        self, client, db, hr_headers, interview
    ):
        resp = self._generate(client, hr_headers, interview["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["interview_id"] == interview["id"]
        assert body["outline"] and body["focus_points"] and body["question_plan"]

        _fresh(db)
        from app.interview import repository as interview_repo

        prep = interview_repo.get_prep_by_interview(db, interview["id"])
        assert prep is not None
        assert prep.outline == body["outline"]
        assert prep.focus_points == body["focus_points"]
        assert prep.question_plan == body["question_plan"]

    def test_generate_prep_sets_generated_at(self, client, hr_headers, interview):
        body = self._generate(client, hr_headers, interview["id"]).json()

        assert body["generated_at"]
        assert body["edited_at"] is None  # 刚生成的内容是 AI 原样产出

    def test_generate_prep_regenerate_overwrites(
        self, client, db, hr_headers, interview
    ):
        first = self._generate(client, hr_headers, interview["id"]).json()
        second = self._generate(client, hr_headers, interview["id"]).json()

        assert second["interview_id"] == first["interview_id"]

        _fresh(db)
        assert _prep_row(db, interview["id"])[2] == 1  # 一场面试唯一

    def test_generate_prep_regenerate_clears_edited_at(
        self, client, hr_headers, interview, prep_payload
    ):
        interview_id = interview["id"]
        self._generate(client, hr_headers, interview_id)
        edited = self._update(client, hr_headers, interview_id, prep_payload).json()
        assert edited["edited_at"]

        regenerated = self._generate(client, hr_headers, interview_id).json()

        # 重新生成覆盖了 HR 的编辑，标记必须同步清除
        assert regenerated["edited_at"] is None

    def test_generate_prep_without_resume_ok(
        self, client, hr_headers, accepted_interview
    ):
        resp = self._generate(client, hr_headers, accepted_interview["interview_id"])

        assert resp.status_code == 200
        assert resp.json()["focus_points"]

    def test_generate_prep_in_draft_allowed(
        self, client, db, hr_headers, position, hr_user
    ):
        draft = _draft_interview(db, position, hr_user)

        resp = self._generate(client, hr_headers, draft.id)

        assert resp.status_code == 200
        assert resp.json()["question_plan"]  # 本场无题目也能生成

    def test_generate_prep_without_questions_ok(
        self, client, db, hr_headers, position, hr_user
    ):
        draft = _draft_interview(db, position, hr_user)
        assert self._generate(client, hr_headers, draft.id).status_code == 200

    @pytest.mark.parametrize(
        "target", [STATUS_COMPLETED, STATUS_EVALUATING, STATUS_EVALUATED]
    )
    def test_generate_prep_after_completed_409(
        self, client, db, hr_headers, interview, hr_user, target
    ):
        _advance(db, interview["id"], target, hr_user)

        assert self._generate(client, hr_headers, interview["id"]).status_code == 409

    def test_generate_prep_empty_dims_409(
        self, client, db, hr_headers, position, interview
    ):
        position.evaluation_dimensions = []
        db.commit()

        assert self._generate(client, hr_headers, interview["id"]).status_code == 409

    def test_generate_prep_ai_failure_leaves_existing_intact(
        self, client, hr_headers, interview, monkeypatch
    ):
        """重新生成失败应表现为「什么都没发生」，而不是旧提纲被清空。"""
        first = self._generate(client, hr_headers, interview["id"]).json()
        _use_provider(monkeypatch, _PrepProvider(error="模拟提纲失败"))

        resp = self._generate(client, hr_headers, interview["id"])

        assert resp.status_code == 502
        again = self._get(client, hr_headers, interview["id"]).json()
        assert again["outline"] == first["outline"]
        assert again["generated_at"] == first["generated_at"]

    def test_generate_prep_ai_failure_first_time_no_row(
        self, client, db, hr_headers, interview, monkeypatch
    ):
        _use_provider(monkeypatch, _PrepProvider(error="模拟提纲失败"))

        assert self._generate(client, hr_headers, interview["id"]).status_code == 502
        assert self._get(client, hr_headers, interview["id"]).status_code == 404

        _fresh(db)
        assert _prep_row(db, interview["id"])[2] == 0

    def test_get_prep_not_generated_404(self, client, hr_headers, interview):
        assert self._get(client, hr_headers, interview["id"]).status_code == 404

    def test_get_prep_ok(self, client, hr_headers, interview):
        created = self._generate(client, hr_headers, interview["id"]).json()

        fetched = self._get(client, hr_headers, interview["id"]).json()

        assert fetched["outline"] == created["outline"]
        assert fetched["focus_points"] == created["focus_points"]
        assert fetched["question_plan"] == created["question_plan"]

    def test_update_prep_overwrites_three_sections(
        self, client, hr_headers, interview, prep_payload
    ):
        created = self._generate(client, hr_headers, interview["id"]).json()

        body = self._update(client, hr_headers, interview["id"], prep_payload).json()

        assert body["outline"] == prep_payload["outline"]
        assert body["focus_points"] == prep_payload["focus_points"]
        assert body["question_plan"] == prep_payload["question_plan"]
        assert body["edited_at"]  # HR 改过了
        assert body["generated_at"] == created["generated_at"]  # 编辑不改生成时刻

    def test_update_prep_missing_section_400(
        self, client, hr_headers, interview, prep_payload
    ):
        self._generate(client, hr_headers, interview["id"])
        payload = dict(prep_payload)
        payload.pop("question_plan")  # 三部分全必填

        assert self._update(client, hr_headers, interview["id"], payload).status_code == 400

    def test_update_prep_not_generated_404(
        self, client, db, hr_headers, interview, prep_payload
    ):
        """未生成就编辑是错误用法 —— 不自动创建（generated_at 会无从取值）。"""
        resp = self._update(client, hr_headers, interview["id"], prep_payload)

        assert resp.status_code == 404
        _fresh(db)
        assert _prep_row(db, interview["id"])[2] == 0

    def test_update_prep_after_completed_409(
        self, client, db, hr_headers, interview, prep_payload, hr_user
    ):
        self._generate(client, hr_headers, interview["id"])
        _advance(db, interview["id"], STATUS_COMPLETED, hr_user)

        resp = self._update(client, hr_headers, interview["id"], prep_payload)

        assert resp.status_code == 409

    def test_prep_isolated_by_hr(self, client, hr_headers, other_hr_headers, interview):
        self._generate(client, hr_headers, interview["id"])

        assert self._get(client, other_hr_headers, interview["id"]).status_code == 403


# ==================== §7.5 契约与隔离 ====================


class TestVisibilityContracts:
    def test_candidate_question_item_has_no_match_reason(
        self, client, candidate_headers, accepted_interview
    ):
        body = client.get(
            f"/api/candidate/interviews/{accepted_interview['interview_id']}",
            headers=candidate_headers,
        ).json()

        assert body["questions"]
        assert all("match_reason" not in item for item in body["questions"])

    def test_candidate_detail_has_no_match_reason_after_match(
        self, client, hr_headers, candidate_headers, linked_interview
    ):
        """补题**之后**新追加的题，同样不得把 match_reason 带给候选人。

        match_reason 描述「候选人简历的哪段经历对应这道题」，属 HR 的评估思路；
        复用 HR 的 schema 是最容易发生的泄露方式（module-19 §4.2）。
        """
        interview_id = linked_interview["interview_id"]
        _match(client, hr_headers, interview_id)

        body = client.get(
            f"/api/candidate/interviews/{interview_id}", headers=candidate_headers
        ).json()

        assert body["questions"]
        assert all("match_reason" not in item for item in body["questions"])
        assert all("source" not in item for item in body["questions"])

    def test_question_item_exposes_match_reason_to_hr(
        self, client, db, hr_headers, linked_interview, position, hr_user
    ):
        _seed_pool(db, position, hr_user)
        interview_id = linked_interview["interview_id"]
        _match(client, hr_headers, interview_id)

        questions = _hr_detail(client, hr_headers, interview_id)["questions"]
        assert all("match_reason" in item for item in questions)
        assert any(item["match_reason"] for item in questions)

    def test_interview_detail_has_resume_id(
        self, client, hr_headers, linked_interview, resume, position
    ):
        # 未关联的那场必须**另建**：linked_interview 本身就依赖同一个面试对象
        unlinked_id = _create_interview(
            client, hr_headers, position.id, name="未关联简历的候选人"
        ).json()["id"]

        unlinked = _hr_detail(client, hr_headers, unlinked_id)
        linked = _hr_detail(client, hr_headers, linked_interview["interview_id"])

        assert unlinked["resume_id"] is None
        assert linked["resume_id"] == resume.id

    def test_briefs_converts_orm_to_raw_values(self, db, position, hr_user):
        """喂给 ai 的必须是原始值 —— 这是 ai 不依赖任何业务模块的前提。"""
        from app.ai.base import QuestionBrief
        from app.interview import service

        question = _seed_question(
            db, position.id, hr_user.id, DIMS[0], "转换验证题干的内容描述文本"
        )

        briefs = service._briefs([question])

        assert len(briefs) == 1
        assert isinstance(briefs[0], QuestionBrief)
        assert (
            briefs[0].question_id,
            briefs[0].content,
            briefs[0].dimension,
            briefs[0].category,
        ) == (question.id, question.content, question.dimension, question.category)

    def test_briefs_from_entries_uses_snapshots(self, db, linked_interview):
        """准备助手喂给 ai 的是**面试题快照**，不是题库题 —— 两者字段不同。

        InterviewQuestion 没有 content / dimension（那是 question 表的列），
        直接套用 `_briefs` 会 AttributeError（这正是快照字段的用途）。
        """
        from app.ai.base import QuestionBrief
        from app.interview import repository as interview_repo
        from app.interview import service

        entries = interview_repo.list_questions(db, linked_interview["interview_id"])
        briefs = service._briefs_from_entries(entries)

        assert briefs
        assert all(isinstance(brief, QuestionBrief) for brief in briefs)
        assert (briefs[0].question_id, briefs[0].content, briefs[0].dimension) == (
            entries[0].id,
            entries[0].content_snapshot,
            entries[0].dimension_snapshot,
        )

    def test_interview_does_not_import_resume_repository(self):
        """静态断言：跨模块跳层不会被任何架构测试拦住（只看同模块内引用）。

        `interview` 顶层 `from app.resume import repository` 在架构测试眼里只是
        「合法依赖 resume」—— 必须靠这条断言守住 service 层不被绕过。
        """
        import ast
        from pathlib import Path

        app_dir = Path(__file__).resolve().parent.parent / "app" / "interview"
        allowed = "app.resume.service"
        offenders: list[str] = []

        for path in sorted(app_dir.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:  # 只看顶层导入；函数体内延迟导入不算依赖
                modules: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
                elif isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)

                for module in modules:
                    if module.startswith("app.resume") and module != allowed:
                        offenders.append(f"{path.name}: {module}")

        assert not offenders, f"interview 越过 resume 的 service 层：{offenders}"
