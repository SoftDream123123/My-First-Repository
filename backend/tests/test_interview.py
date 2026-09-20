"""interview 模块测试：出题组装、回答记录、状态机、供给契约。"""

import pytest

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
