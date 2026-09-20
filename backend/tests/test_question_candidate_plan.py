"""question 模块 MVP-2 测试（计划书 module-10 §7）。

覆盖：题型字段校验、AI 补参考答案、筛选与对 practice 的供给契约、
候选人视图剥离答案、存量数据回归、刷题岗位筛选项。
"""

import pytest

from app.question import service as question_service
from app.question.schemas import PracticeFilters, PracticeQuestionOut


def _fresh(db):
    """结束当前事务，让随后的读能看到别的连接刚提交的数据。

    `db` 夹具是一个长生命周期会话；MySQL 默认 REPEATABLE READ 下它的事务快照
    在第一次查询时就固定了，因此**看不到 HTTP 请求（另一连接）刚提交的行**。
    rollback 结束该事务，下一次查询会重新取快照。
    """
    db.rollback()


def _create(client, headers, position_id, **overrides):
    payload = {
        "position_id": position_id,
        "dimension": "沟通能力",
        "content": "这是一道用于测试的题目内容描述文本",
    }
    payload.update(overrides)
    return client.post("/api/questions", json=payload, headers=headers)


# 注：跨 HR 的用例需要「另一个 HR 的岗位」，用 conftest 的 other_position 夹具。


# ========================= 7.1 字段校验 =========================


class TestSingleChoiceValidation:
    def test_create_single_choice_ok(self, client, hr_headers, position):
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["选项甲", "选项乙", "选项丙"],
            reference_answer="选项乙",
            explanation="因为乙最贴合题干。",
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["question_type"] == "single_choice"
        assert body["options"] == ["选项甲", "选项乙", "选项丙"]
        assert body["reference_answer"] == "选项乙"
        assert body["explanation"] == "因为乙最贴合题干。"

    def test_create_single_choice_without_options(self, client, hr_headers, position):
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            reference_answer="选项甲",
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "单选题至少需要 2 个选项"

    def test_create_single_choice_single_option(self, client, hr_headers, position):
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["唯一的选项"],
            reference_answer="唯一的选项",
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "单选题至少需要 2 个选项"

    def test_create_single_choice_without_reference(self, client, hr_headers, position):
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["选项甲", "选项乙"],
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "单选题必须提供参考答案"

    def test_create_single_choice_reference_not_in_options(
        self, client, hr_headers, position
    ):
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["选项甲", "选项乙"],
            reference_answer="选项丙",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["message"] == "参考答案必须是选项之一"
        assert body["detail"]["options"] == ["选项甲", "选项乙"]

    def test_create_single_choice_duplicate_options(
        self, client, hr_headers, position
    ):
        """strip 后重复即拒绝 —— 不静默去重，否则选项数会与 HR 填的不一致。"""
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["选项甲", " 选项甲 ", "选项乙"],
            reference_answer="选项甲",
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "选项不能重复"


class TestShortAnswerValidation:
    def test_create_short_answer_with_options(self, client, hr_headers, position):
        resp = _create(
            client,
            hr_headers,
            position.id,
            question_type="short_answer",
            options=["选项甲", "选项乙"],
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "简答题不应包含选项"

    def test_create_short_answer_without_reference_ok(
        self, client, hr_headers, position
    ):
        resp = _create(client, hr_headers, position.id, question_type="short_answer")
        assert resp.status_code == 201

        body = resp.json()
        assert body["options"] == []
        assert body["reference_answer"] is None
        assert body["explanation"] is None

    def test_create_default_question_type_is_short_answer(
        self, client, hr_headers, position
    ):
        """不传 question_type → 落库为短答。

        存量题目全是纯文本题，默认单选会凭空造出无选项的单选题。
        """
        resp = _create(client, hr_headers, position.id)
        assert resp.status_code == 201
        assert resp.json()["question_type"] == "short_answer"

    def test_create_invalid_question_type(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, question_type="essay")
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"


class TestUpdateSemantics:
    def _create_short_answer(self, client, hr_headers, position_id, **kw):
        resp = _create(
            client,
            hr_headers,
            position_id,
            question_type="short_answer",
            reference_answer="原有的参考答案",
            explanation="原有的解析",
            **kw,
        )
        assert resp.status_code == 201
        return resp.json()

    def test_update_short_answer_to_single_choice_requires_full_payload(
        self, client, hr_headers, position
    ):
        created = self._create_short_answer(client, hr_headers, position.id)

        base = {
            "position_id": position.id,
            "dimension": "沟通能力",
            "content": created["content"],
        }

        # 只改题型、不补选项 → 400（合并后的最终形态不合法）
        resp = client.put(
            f"/api/questions/{created['id']}",
            json={**base, "question_type": "single_choice"},
            headers=hr_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "单选题至少需要 2 个选项"

        # 补齐选项与参考答案 → 200
        resp = client.put(
            f"/api/questions/{created['id']}",
            json={
                **base,
                "question_type": "single_choice",
                "options": ["选项甲", "选项乙"],
                "reference_answer": "选项甲",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["question_type"] == "single_choice"
        assert body["options"] == ["选项甲", "选项乙"]

    def test_update_does_not_silently_clear_reference(
        self, client, hr_headers, position
    ):
        """改题干时未提交新字段 → 参考答案与解析保持不变。

        这是对全量替换语义的有意例外：新字段缺省表示「不改动」，
        否则 HR 改个错别字就会把参考答案一起抹掉。
        """
        created = self._create_short_answer(client, hr_headers, position.id)

        resp = client.put(
            f"/api/questions/{created['id']}",
            json={
                "position_id": position.id,
                "dimension": "沟通能力",
                "content": "改过之后的题干内容描述文本",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["content"] == "改过之后的题干内容描述文本"
        assert body["reference_answer"] == "原有的参考答案"
        assert body["explanation"] == "原有的解析"
        assert body["question_type"] == "short_answer"

    def test_update_can_explicitly_clear_reference(
        self, client, hr_headers, position
    ):
        """显式传 null 才是清空 —— 与「缺省」区分开。"""
        created = self._create_short_answer(client, hr_headers, position.id)

        resp = client.put(
            f"/api/questions/{created['id']}",
            json={
                "position_id": position.id,
                "dimension": "沟通能力",
                "content": created["content"],
                "reference_answer": None,
                "explanation": None,
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["reference_answer"] is None
        assert resp.json()["explanation"] is None


# ==================== 7.2 AI 补参考答案 ====================


class TestGenerateReferenceAnswer:
    def test_short_answer(self, client, hr_headers, position):
        created = _create(client, hr_headers, position.id).json()

        resp = client.post(
            f"/api/questions/{created['id']}/reference-answer", headers=hr_headers
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["reference_answer"]
        assert body["explanation"]

    def test_single_choice_picks_option(self, client, hr_headers, position):
        options = ["选项甲", "选项乙", "选项丙"]
        created = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=options,
            reference_answer="选项甲",
        ).json()

        resp = client.post(
            f"/api/questions/{created['id']}/reference-answer", headers=hr_headers
        )
        assert resp.status_code == 200
        assert resp.json()["reference_answer"] in options

    def test_rejects_answer_out_of_options(self, client, hr_headers, db, position, monkeypatch):
        """答案不在选项内 → 409 且**库中字段未被修改**（不伪造正确答案）。"""
        options = ["选项甲", "选项乙"]
        created = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=options,
            reference_answer="选项甲",
        ).json()

        class OutOfOptionsProvider:
            def generate_reference_answer(self, *a, **kw):
                from app.ai.base import ReferenceAnswerResult

                return ReferenceAnswerResult(
                    reference_answer="选项之外的臆造答案", explanation="解析"
                )

        monkeypatch.setattr(
            "app.question.service.get_provider", lambda: OutOfOptionsProvider()
        )

        resp = client.post(
            f"/api/questions/{created['id']}/reference-answer", headers=hr_headers
        )
        assert resp.status_code == 409
        assert resp.json()["message"] == "AI 生成的答案不在选项中，请手工确认"

        _fresh(db)
        from app.question import repository

        assert repository.get_by_id(db, created["id"]).reference_answer == "选项甲"

    def test_ai_failure(self, client, hr_headers, db, position, monkeypatch):
        created = _create(
            client, hr_headers, position.id, reference_answer="原来的答案"
        ).json()

        class FailingProvider:
            def generate_reference_answer(self, *a, **kw):
                from app.core.exceptions import AIProviderError

                raise AIProviderError("模拟失败")

        monkeypatch.setattr(
            "app.question.service.get_provider", lambda: FailingProvider()
        )

        resp = client.post(
            f"/api/questions/{created['id']}/reference-answer", headers=hr_headers
        )
        assert resp.status_code == 502
        assert resp.json()["code"] == "AI_PROVIDER_ERROR"

        _fresh(db)
        from app.question import repository

        assert repository.get_by_id(db, created["id"]).reference_answer == "原来的答案"

    def test_visibility(self, client, hr_headers, other_hr_headers, position):
        created = _create(client, hr_headers, position.id).json()

        assert (
            client.post(
                f"/api/questions/{created['id']}/reference-answer",
                headers=other_hr_headers,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/questions/999999/reference-answer", headers=hr_headers
            ).status_code
            == 404
        )

    def test_passes_raw_values(self, client, hr_headers, position, monkeypatch):
        """传给 Provider 的必须是原始值，不能是 ORM 对象（module-04 §3.4）。"""
        created = _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["选项甲", "选项乙"],
            reference_answer="选项甲",
        ).json()

        captured = {}

        class SpyProvider:
            def generate_reference_answer(self, question_type, content, options, dimension):
                from app.ai.base import ReferenceAnswerResult

                captured["args"] = (question_type, content, options, dimension)
                return ReferenceAnswerResult(reference_answer="选项甲", explanation="解析")

        monkeypatch.setattr(
            "app.question.service.get_provider", lambda: SpyProvider()
        )

        assert (
            client.post(
                f"/api/questions/{created['id']}/reference-answer", headers=hr_headers
            ).status_code
            == 200
        )

        question_type, content, options, dimension = captured["args"]
        assert isinstance(question_type, str)
        assert isinstance(content, str)
        assert isinstance(options, list) and all(isinstance(o, str) for o in options)
        assert isinstance(dimension, str)
        # 不是 ORM 对象
        assert not hasattr(content, "created_by")


# ================== 7.3 筛选与供给契约 ==================


class TestFiltersAndSupply:
    def test_list_filter_by_question_type(self, client, hr_headers, position):
        _create(client, hr_headers, position.id, question_type="short_answer")
        _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["甲", "乙"],
            reference_answer="甲",
        )

        resp = client.get(
            "/api/questions", params={"question_type": "single_choice"}, headers=hr_headers
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["question_type"] == "single_choice"

    def test_list_filter_combined(self, client, hr_headers, position):
        _create(
            client, hr_headers, position.id, difficulty="easy", dimension="沟通能力"
        )
        _create(
            client, hr_headers, position.id, difficulty="hard", dimension="沟通能力"
        )
        _create(
            client, hr_headers, position.id, difficulty="hard", dimension="专业能力"
        )

        resp = client.get(
            "/api/questions",
            params={"question_type": "short_answer", "difficulty": "hard", "dimension": "专业能力"},
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_practice_candidates_ignores_owner(
        self, client, db, hr_headers, other_hr_headers, position, other_position
    ):
        """刷题取题**有意不按 created_by 过滤** —— 跨 HR 的题都能取到。"""
        _create(client, hr_headers, position.id)
        _create(client, other_hr_headers, other_position.id)

        _fresh(db)
        result = question_service.list_practice_questions(
            db, PracticeFilters(), limit=100
        )
        assert len(result) == 2

    def test_list_practice_candidates_order_by_id(
        self, client, db, hr_headers, position
    ):
        created = [
            _create(client, hr_headers, position.id).json()["id"] for _ in range(3)
        ]

        _fresh(db)
        result = question_service.list_practice_questions(
            db, PracticeFilters(), limit=100
        )
        ids = [q.id for q in result]
        assert ids == sorted(ids)
        assert set(ids) == set(created)

    def test_list_practice_candidates_respects_limit(
        self, client, db, hr_headers, position
    ):
        for _ in range(5):
            _create(client, hr_headers, position.id)

        _fresh(db)
        result = question_service.list_practice_questions(
            db, PracticeFilters(), limit=2
        )
        assert len(result) == 2

    def test_list_practice_candidates_filter_by_type(
        self, client, db, hr_headers, position
    ):
        _create(client, hr_headers, position.id, question_type="short_answer")
        _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["甲", "乙"],
            reference_answer="甲",
        )

        _fresh(db)
        result = question_service.list_practice_questions(
            db, PracticeFilters(question_type="single_choice"), limit=100
        )
        assert len(result) == 1
        assert result[0].question_type == "single_choice"


# ================== 7.4 候选人视图剥离答案 ==================


class TestPracticeQuestionOut:
    """PracticeQuestionOut 是刷题闭环的安全边界（见 schemas 的说明）。"""

    @pytest.fixture
    def single_choice_payload(self, client, hr_headers, position):
        return _create(
            client,
            hr_headers,
            position.id,
            question_type="single_choice",
            options=["选项甲", "选项乙"],
            reference_answer="选项甲",
            explanation="因为甲最贴合。",
        ).json()

    def test_has_no_reference_answer(self, single_choice_payload):
        dumped = PracticeQuestionOut.model_validate(single_choice_payload).model_dump()
        assert "reference_answer" not in dumped

    def test_has_no_explanation(self, single_choice_payload):
        dumped = PracticeQuestionOut.model_validate(single_choice_payload).model_dump()
        assert "explanation" not in dumped

    def test_has_no_source_or_creator(self, single_choice_payload):
        dumped = PracticeQuestionOut.model_validate(single_choice_payload).model_dump()
        for field in ("source", "created_by", "created_at"):
            assert field not in dumped

    def test_keeps_options(self, single_choice_payload):
        """选项**必须**存在，否则前端单选框没有内容可渲染。"""
        dumped = PracticeQuestionOut.model_validate(single_choice_payload).model_dump()
        assert dumped.get("options") == ["选项甲", "选项乙"]
        assert dumped["question_type"] == "single_choice"


# ==================== 7.5 存量数据回归 ====================


class TestLegacyData:
    def test_existing_questions_default_to_short_answer(
        self, client, db, hr_headers, position, hr_user
    ):
        """直接落库（模拟迁移前写入的数据）→ 题型取默认简答、选项为空。"""
        from app.question import repository

        question = repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="迁移前写入的一道旧题目内容",
            difficulty="medium",
            tags=[],
            source="bank",
            created_by=hr_user.id,
        )
        db.commit()
        db.refresh(question)

        assert question.question_type == "short_answer"
        assert question.options == []

    def test_existing_questions_still_extractable_by_interview(
        self, client, db, hr_headers, position, hr_user
    ):
        """出题候选查询不受新字段影响（module-05 §5.2 保持可用）。"""
        _create(client, hr_headers, position.id)

        _fresh(db)
        candidates = question_service.list_candidates_for_position(
            db, hr_user.id, position.id
        )
        assert len(candidates) == 1
        assert candidates[0].content

    def test_question_out_includes_new_fields(self, client, hr_headers, position):
        created = _create(client, hr_headers, position.id).json()
        for field in ("question_type", "options", "reference_answer", "explanation"):
            assert field in created


# ================== 7.6 刷题岗位筛选项 ==================


class TestPracticePositions:
    URL = "/api/candidate/positions"

    def test_only_with_questions(
        self, client, hr_headers, candidate_headers, position, other_position
    ):
        _create(client, hr_headers, position.id)

        resp = client.get(self.URL, headers=candidate_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == position.id

    def test_counts_questions(self, client, hr_headers, candidate_headers, position):
        for _ in range(3):
            _create(client, hr_headers, position.id)

        items = client.get(self.URL, headers=candidate_headers).json()
        assert items[0]["question_count"] == 3

    def test_ignores_owner(
        self,
        client,
        hr_headers,
        other_hr_headers,
        candidate_headers,
        position,
        other_position,
    ):
        """口径与取题一致：跨 HR 的岗位都要返回，否则筛选项与取题结果对不上。"""
        _create(client, hr_headers, position.id)
        _create(client, other_hr_headers, other_position.id)

        items = client.get(self.URL, headers=candidate_headers).json()
        assert len(items) == 2
        assert {item["id"] for item in items} == {position.id, other_position.id}

    def test_order_by_id(
        self, client, hr_headers, candidate_headers, position, other_position
    ):
        _create(client, hr_headers, position.id)
        _create(client, hr_headers, other_position.id)

        items = client.get(self.URL, headers=candidate_headers).json()
        ids = [item["id"] for item in items]
        assert ids == sorted(ids)

    def test_out_has_no_jd(self, client, hr_headers, candidate_headers, position):
        _create(client, hr_headers, position.id)
        items = client.get(self.URL, headers=candidate_headers).json()
        assert "jd" not in items[0]

    def test_out_has_no_creator_fields(
        self, client, hr_headers, candidate_headers, position
    ):
        _create(client, hr_headers, position.id)
        items = client.get(self.URL, headers=candidate_headers).json()
        for field in ("created_by", "created_at"):
            assert field not in items[0]

    def test_requires_candidate(
        self, client, hr_headers, admin_headers, candidate_headers, position
    ):
        """hr 与 admin 在候选人侧**精确匹配**下都不通行。"""
        assert client.get(self.URL, headers=hr_headers).status_code == 403
        assert client.get(self.URL, headers=admin_headers).status_code == 403
        assert client.get(self.URL).status_code == 401

    def test_position_with_all_questions_deleted_not_listed(
        self, client, hr_headers, candidate_headers, position
    ):
        created = _create(client, hr_headers, position.id).json()
        assert len(client.get(self.URL, headers=candidate_headers).json()) == 1

        assert (
            client.delete(
                f"/api/questions/{created['id']}", headers=hr_headers
            ).status_code
            == 204
        )
        assert client.get(self.URL, headers=candidate_headers).json() == []
