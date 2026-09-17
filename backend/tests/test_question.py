"""question 模块测试：鉴权隔离、岗位与维度校验、字段校验、筛选、删除、供给契约。"""

import pytest

from app.question.models import Question
from app.question.schemas import QuestionFilters


def _create(client, headers, position_id, **overrides):
    payload = {
        "position_id": position_id,
        "dimension": "沟通能力",
        "content": "请描述一次你处理线上故障的完整过程。",
    }
    payload.update(overrides)
    return client.post("/api/questions", json=payload, headers=headers)


# --------------------------- 鉴权与隔离 ---------------------------


class TestAuthAndIsolation:
    def test_create_without_token(self, client, position):
        assert _create(client, {}, position.id).status_code == 401

    def test_create_ok(self, client, hr_headers, hr_user, position):
        resp = _create(client, hr_headers, position.id)
        assert resp.status_code == 201

        body = resp.json()
        assert body["source"] == "bank"  # 来源由服务端决定
        assert body["created_by"] == hr_user.id
        assert body["category"] == "通用"
        assert body["difficulty"] == "medium"
        assert body["tags"] == []

    def test_list_only_own_questions(
        self, client, hr_headers, other_hr_headers, position
    ):
        _create(client, hr_headers, position.id)

        assert len(client.get("/api/questions", headers=hr_headers).json()) == 1
        assert client.get("/api/questions", headers=other_hr_headers).json() == []

    def test_admin_sees_all_questions(
        self, client, hr_headers, admin_headers, position
    ):
        _create(client, hr_headers, position.id)
        assert len(client.get("/api/questions", headers=admin_headers).json()) == 1

    def test_get_other_users_question_forbidden(
        self, client, hr_headers, other_hr_headers, position
    ):
        question_id = _create(client, hr_headers, position.id).json()["id"]
        resp = client.get(f"/api/questions/{question_id}", headers=other_hr_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_get_nonexistent_question(self, client, hr_headers):
        resp = client.get("/api/questions/999999", headers=hr_headers)
        assert resp.status_code == 404

    def test_update_and_delete_other_users_question_forbidden(
        self, client, hr_headers, other_hr_headers, position
    ):
        question_id = _create(client, hr_headers, position.id).json()["id"]

        update = client.put(
            f"/api/questions/{question_id}",
            json={
                "position_id": position.id,
                "dimension": "沟通能力",
                "content": "改过的题干内容",
            },
            headers=other_hr_headers,
        )
        assert update.status_code == 403

        delete = client.delete(
            f"/api/questions/{question_id}", headers=other_hr_headers
        )
        assert delete.status_code == 403


# ------------------------ 岗位与维度校验 ------------------------


class TestPositionAndDimension:
    def test_create_with_nonexistent_position(self, client, hr_headers):
        assert _create(client, hr_headers, 999999).status_code == 404

    def test_create_with_other_users_position(
        self, client, other_hr_headers, position
    ):
        """position 属于 hr_user；用 other_hr 的 token 建题应被拒绝。"""
        resp = _create(client, other_hr_headers, position.id)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_create_with_invalid_dimension(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, dimension="不存在的维度")
        assert resp.status_code == 400

        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["detail"]["allowed"] == position.evaluation_dimensions

    def test_dimension_match_is_exact_after_strip(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, dimension=" 沟通能力 ")
        assert resp.status_code == 201
        assert resp.json()["dimension"] == "沟通能力"

    def test_update_to_other_position_revalidates_dimension(
        self, client, hr_headers, hr_user, db, position
    ):
        from app.core.security import create_access_token
        from app.position import service as position_service
        from app.position.schemas import PositionCreate

        other_position = position_service.create_position(
            db,
            hr_user,
            PositionCreate(
                name="产品经理",
                jd="负责产品规划与需求管理。",
                evaluation_dimensions=["产品sense"],
            ),
        )
        question_id = _create(client, hr_headers, position.id).json()["id"]

        resp = client.put(
            f"/api/questions/{question_id}",
            json={
                "position_id": other_position.id,
                "dimension": "沟通能力",  # 不属于新岗位
                "content": "改过的题干内容",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 400

    def test_update_to_other_position_ok(self, client, hr_headers, hr_user, db, position):
        from app.position import service as position_service
        from app.position.schemas import PositionCreate

        other_position = position_service.create_position(
            db,
            hr_user,
            PositionCreate(
                name="产品经理",
                jd="负责产品规划与需求管理。",
                evaluation_dimensions=["产品sense"],
            ),
        )
        question_id = _create(client, hr_headers, position.id).json()["id"]

        resp = client.put(
            f"/api/questions/{question_id}",
            json={
                "position_id": other_position.id,
                "dimension": "产品sense",
                "content": "改过的题干内容",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["position_id"] == other_position.id


# ---------------------------- 字段校验 ----------------------------





class TestFieldValidation:
    def test_content_too_short(self, client, hr_headers, position):
        assert _create(client, hr_headers, position.id, content="四个字").status_code == 400

    def test_content_too_long(self, client, hr_headers, position):
        assert (
            _create(client, hr_headers, position.id, content="字" * 2001).status_code
            == 400
        )

    def test_content_exactly_5_chars_ok(self, client, hr_headers, position):
        assert (
            _create(client, hr_headers, position.id, content="五个字符的").status_code
            == 201
        )

    def test_category_defaults_to_generic(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id)
        assert resp.json()["category"] == "通用"

    def test_category_can_be_set(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, category="行为")
        assert resp.json()["category"] == "行为"

    def test_difficulty_defaults_to_medium(self, client, hr_headers, position):
        assert _create(client, hr_headers, position.id).json()["difficulty"] == "medium"

    def test_invalid_difficulty(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, difficulty="very_hard")
        assert resp.status_code == 400

    def test_tags_default_empty(self, client, hr_headers, position):
        assert _create(client, hr_headers, position.id).json()["tags"] == []

    def test_tags_exceed_limit(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, tags=[f"t{i}" for i in range(11)])
        assert resp.status_code == 400

    def test_tags_dedup_after_strip(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, tags=["a", " a "])
        assert resp.json()["tags"] == ["a"]

    def test_tags_single_too_long(self, client, hr_headers, position):
        resp = _create(client, hr_headers, position.id, tags=["字" * 21])
        assert resp.status_code == 400

    def test_client_cannot_set_source(self, client, hr_headers, position):
        """请求体带 source=ai 也应落库为 bank。"""
        resp = _create(client, hr_headers, position.id, source="ai")
        assert resp.status_code == 201
        assert resp.json()["source"] == "bank"


# ------------------------------ 筛选 ------------------------------


class TestFiltering:
    @pytest.fixture
    def seeded(self, client, hr_headers, position):
        _create(client, hr_headers, position.id, dimension="沟通能力", category="行为",
                content="沟通类题目一的内容描述")
        _create(client, hr_headers, position.id, dimension="专业能力", category="技术",
                content="专业类题目二的内容描述")
        _create(client, hr_headers, position.id, dimension="专业能力", category="技术",
                content="专业类题目三的内容描述")
        return position

    def test_filter_by_position(self, client, hr_headers, seeded):
        resp = client.get(
            f"/api/questions?position_id={seeded.id}", headers=hr_headers
        )
        assert len(resp.json()) == 3

    def test_filter_by_position_no_match(self, client, hr_headers, seeded):
        resp = client.get("/api/questions?position_id=999999", headers=hr_headers)
        assert resp.json() == []

    def test_filter_by_category(self, client, hr_headers, seeded):
        resp = client.get("/api/questions?category=技术", headers=hr_headers)
        assert len(resp.json()) == 2

    def test_filter_by_dimension(self, client, hr_headers, seeded):
        resp = client.get("/api/questions?dimension=沟通能力", headers=hr_headers)
        assert len(resp.json()) == 1

    def test_filter_by_keyword(self, client, hr_headers, seeded):
        resp = client.get("/api/questions?keyword=沟通类", headers=hr_headers)
        assert len(resp.json()) == 1

    def test_filter_combined_is_and(self, client, hr_headers, seeded):
        resp = client.get(
            "/api/questions?category=技术&dimension=沟通能力", headers=hr_headers
        )
        assert resp.json() == []

    def test_filter_by_source(self, client, hr_headers, seeded):
        resp = client.get("/api/questions?source=bank", headers=hr_headers)
        assert len(resp.json()) == 3

        resp = client.get("/api/questions?source=ai", headers=hr_headers)
        assert resp.json() == []

    def test_filter_respects_isolation(
        self, client, hr_headers, other_hr_headers, seeded, position
    ):
        """筛选不得越过 created_by 边界 —— 即便条件完全匹配。"""
        resp = client.get(
            f"/api/questions?position_id={position.id}&category=技术",
            headers=other_hr_headers,
        )
        assert resp.json() == []


# ------------------------------ 删除 ------------------------------


class TestDelete:
    def test_delete_ok(self, client, hr_headers, position):
        question_id = _create(client, hr_headers, position.id).json()["id"]

        resp = client.delete(f"/api/questions/{question_id}", headers=hr_headers)
        assert resp.status_code == 204
        assert resp.content == b""

        assert (
            client.get(f"/api/questions/{question_id}", headers=hr_headers).status_code
            == 404
        )

    def test_delete_referenced_by_interview(self, client, hr_headers, position):
        """题目被面试引用时不可删除 —— 由外键 ON DELETE RESTRICT 保证。"""
        question_id = _create(client, hr_headers, position.id).json()["id"]

        detail = client.post(
            "/api/interviews",
            json={"position_id": position.id, "candidate_name": "张三"},
            headers=hr_headers,
        ).json()
        referenced = {
            q["content"]
            for q in detail["questions"]
            if q["source"] == "bank"
        }
        assert _content_of(client, hr_headers, question_id) in referenced

        resp = client.delete(f"/api/questions/{question_id}", headers=hr_headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"
        assert "无法删除" in resp.json()["message"]


def _content_of(client, headers, question_id):
    return client.get(f"/api/questions/{question_id}", headers=headers).json()["content"]


# ------------------------ 对 interview 的供给契约 ------------------------


class TestSupplyContract:
    """供给契约测试。

    注意：这些用例通过 HTTP 建题、再用 db 夹具读取。MySQL 默认 REPEATABLE READ
    下 db 夹具的事务快照早于 HTTP 请求的提交，故读取前必须先结束当前事务。
    """

    def test_list_candidates_returns_position_questions(
        self, client, hr_headers, db, hr_user, position
    ):
        from app.question import service

        _create(client, hr_headers, position.id)
        _create(client, hr_headers, position.id)
        db.rollback()

        candidates = service.list_candidates_for_position(db, hr_user.id, position.id)
        assert len(candidates) == 2

    def test_list_candidates_ordered_by_id(self, client, hr_headers, db, hr_user, position):
        from app.question import service

        for _ in range(3):
            _create(client, hr_headers, position.id)
        db.rollback()

        candidates = service.list_candidates_for_position(db, hr_user.id, position.id)
        ids = [q.id for q in candidates]
        assert len(ids) == 3
        assert ids == sorted(ids)

    def test_list_candidates_respects_owner(self, client, hr_headers, db, other_hr, position):
        from app.question import service

        _create(client, hr_headers, position.id)
        db.rollback()

        assert service.list_candidates_for_position(db, other_hr.id, position.id) == []

    def test_list_candidates_with_none_owner_returns_all(
        self, client, hr_headers, db, position
    ):
        from app.question import service

        _create(client, hr_headers, position.id)
        db.rollback()

        candidates = service.list_candidates_for_position(db, None, position.id)
        assert len(candidates) == 1

    def test_list_candidates_includes_ai_source(
        self, client, hr_headers, db, hr_user, position
    ):
        """供给契约不按 source 过滤 —— 手工题与 AI 题都是候选。"""
        from app.question import service

        _create(client, hr_headers, position.id)  # 一道手工题
        db.rollback()

        # 建一场面试：AI 补的题会以 source='ai' 落回题库
        created = client.post(
            "/api/interviews",
            json={"position_id": position.id, "candidate_name": "张三"},
            headers=hr_headers,
        )
        assert created.status_code == 201
        db.rollback()

        candidates = service.list_candidates_for_position(db, hr_user.id, position.id)
        assert {q.source for q in candidates} == {"bank", "ai"}

    def test_bulk_create_from_ai_sets_source_ai(self, db, hr_user, position):
        from app.ai.base import GeneratedQuestion
        from app.question import service

        items = [
            GeneratedQuestion(content="AI 生成的题目一", dimension="沟通能力"),
            GeneratedQuestion(content="AI 生成的题目二", dimension="专业能力"),
        ]
        created = service.bulk_create_from_ai(db, hr_user, position.id, items)
        db.commit()

        assert len(created) == 2
        assert all(q.source == "ai" for q in created)
        assert all(q.created_by == hr_user.id for q in created)
        assert all(q.position_id == position.id for q in created)

    def test_bulk_create_from_ai_empty(self, db, hr_user, position):
        from app.question import service

        assert service.bulk_create_from_ai(db, hr_user, position.id, []) == []


# --------------------------- 仓储层细节 ---------------------------


def test_list_filtered_none_owner_returns_all(db, hr_user, other_hr, position):
    from app.question import repository

    repository.create(
        db,
        position_id=position.id,
        category="通用",
        dimension="沟通能力",
        content="题目内容一二三",
        difficulty="medium",
        tags=[],
        source="bank",
        created_by=other_hr.id,
    )
    db.commit()

    assert len(repository.list_filtered(db, None, QuestionFilters())) == 1
    assert len(repository.list_filtered(db, hr_user.id, QuestionFilters())) == 0


def test_question_model_repr(db, hr_user, position):
    question = Question(
        position_id=position.id,
        category="通用",
        dimension="沟通能力",
        content="题目内容一二三",
        difficulty="medium",
        tags=[],
        source="bank",
        created_by=hr_user.id,
    )
    assert "bank" in repr(question)
