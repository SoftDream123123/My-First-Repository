"""候选人在线答题测试（计划书 module-12 §7.2、§7.3）。

覆盖：可见性、作答、交卷、HR 覆盖、权限。
前置一律用 conftest 的 accepted_interview 夹具。
"""

from app.interview import repository, service as interview_service
from app.interview.models import (
    ANSWER_SOURCE_CANDIDATE,
    ANSWER_SOURCE_HR,
    STATUS_COMPLETED,
    STATUS_ONGOING,
)

CANDIDATE_PASSWORD = "cand12345678"


def _fresh(db) -> None:
    db.rollback()


def _detail(client, headers, interview_id) -> dict:
    resp = client.get(f"/api/candidate/interviews/{interview_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_interview(client, headers, position_id, name="张三") -> dict:
    resp = client.post(
        "/api/interviews",
        json={"position_id": position_id, "candidate_name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _invite(client, headers, interview_id) -> dict:
    resp = client.post(f"/api/interviews/{interview_id}/invitations", headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _entry_ids(client, headers, interview_id) -> list[int]:
    return [
        q["interview_question_id"]
        for q in _detail(client, headers, interview_id)["questions"]
    ]


def _save(client, headers, interview_id, entry_id, content):
    return client.post(
        f"/api/candidate/interviews/{interview_id}/answers",
        json={"interview_question_id": entry_id, "content": content},
        headers=headers,
    )


def _set_status(db, interview_id: int, status: str) -> None:
    _fresh(db)
    interview = repository.get_by_id(db, interview_id)
    interview.status = status
    db.commit()


# ========================= 可见性 =========================


class TestVisibility:
    def test_lists_only_accepted_interviews(
        self, client, hr_headers, candidate_headers, candidate_user, position
    ):
        """只返回本人 accepted 的面试；只有 pending 邀请的不出现。"""
        accepted = _create_interview(client, hr_headers, position.id, "受理者")
        pending_only = _create_interview(client, hr_headers, position.id, "未受理者")

        accepted_code = _invite(client, hr_headers, accepted["id"])["code"]
        _invite(client, hr_headers, pending_only["id"])  # 只发邀请，不接受

        client.post(
            f"/api/candidate/invitations/{accepted_code}/accept",
            json={"username": candidate_user.username, "password": CANDIDATE_PASSWORD},
            headers=candidate_headers,
        )

        listed = client.get(
            "/api/candidate/interviews", headers=candidate_headers
        ).json()
        assert [item["id"] for item in listed] == [accepted["id"]]
        assert listed[0]["submitted"] is False
        assert listed[0]["question_count"] > 0

    def test_cannot_access_pending_invitation_interview(
        self, client, hr_headers, candidate_headers, position
    ):
        interview = client.post(
            "/api/interviews",
            json={"position_id": position.id, "candidate_name": "张三"},
            headers=hr_headers,
        ).json()
        client.post(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        )

        resp = client.get(
            f"/api/candidate/interviews/{interview['id']}", headers=candidate_headers
        )
        assert resp.status_code == 403

    def test_cannot_access_other_candidates_interview(
        self, client, accepted_interview, other_candidate_headers
    ):
        resp = client.get(
            f"/api/candidate/interviews/{accepted_interview['interview_id']}",
            headers=other_candidate_headers,
        )
        assert resp.status_code == 403

    def test_detail_hides_hr_fields(self, client, candidate_headers, accepted_interview):
        """详情不含 created_by、评分、评语、其他候选人的作答。"""
        detail = _detail(
            client, candidate_headers, accepted_interview["interview_id"]
        )
        assert "created_by" not in detail
        for forbidden in ("question_scores", "dimension_scores", "report", "comments"):
            assert forbidden not in detail

        for question in detail["questions"]:
            for forbidden in ("score", "comment", "reference_answer", "explanation"):
                assert forbidden not in question
            assert set(question) == {
                "interview_question_id",
                "seq",
                "content",
                "dimension",
                "my_answer",
            }

    def test_detail_uses_snapshots(
        self, client, db, candidate_headers, accepted_interview
    ):
        """改题库题干后，候选人详情仍显示快照原值。"""
        interview_id = accepted_interview["interview_id"]
        original = _detail(client, candidate_headers, interview_id)["questions"][0][
            "content"
        ]

        _fresh(db)
        from app.question import repository as question_repository

        entry = repository.list_questions(db, interview_id)[0]
        question = question_repository.get_by_id(db, entry.question_id)
        question.content = "被彻底改写过的题干内容"
        db.commit()

        after = _detail(client, candidate_headers, interview_id)["questions"][0][
            "content"
        ]
        assert after == original

    def test_list_includes_accepted(
        self, client, candidate_headers, accepted_interview
    ):
        listed = client.get("/api/candidate/interviews", headers=candidate_headers).json()
        assert [item["id"] for item in listed] == [
            accepted_interview["interview_id"]
        ]


# ========================= 作答 =========================


class TestSaveAnswer:
    def test_ok(self, client, db, candidate_headers, accepted_interview, candidate_user):
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]

        resp = _save(client, candidate_headers, interview_id, entry_id, "我的回答内容")
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "我的回答内容"
        assert body["submitted_at"] is None

        _fresh(db)
        answer = next(
            a
            for a in repository.list_answers(db, interview_id)
            if a.interview_question_id == entry_id
        )
        assert answer.source == ANSWER_SOURCE_CANDIDATE
        assert answer.answered_by == candidate_user.id
        assert answer.submitted_at is None

    def test_only_ongoing(self, client, db, candidate_headers, accepted_interview):
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]
        _set_status(db, interview_id, STATUS_COMPLETED)

        resp = _save(client, candidate_headers, interview_id, entry_id, "回答")
        assert resp.status_code == 409

    def test_after_submit_rejected(
        self, client, candidate_headers, accepted_interview
    ):
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )

        resp = _save(client, candidate_headers, interview_id, entry_id, "交卷后想改")
        assert resp.status_code == 409
        assert resp.json()["message"] == "已交卷，不可修改作答"

    def test_other_question_rejected(
        self, client, hr_headers, candidate_headers, accepted_interview, position
    ):
        """传别的面试的 interview_question_id → 404。"""
        other = client.post(
            "/api/interviews",
            json={"position_id": position.id, "candidate_name": "另一个人"},
            headers=hr_headers,
        ).json()
        foreign_entry = client.get(
            f"/api/interviews/{other['id']}", headers=hr_headers
        ).json()["questions"][0]["interview_question_id"]

        resp = _save(
            client,
            candidate_headers,
            accepted_interview["interview_id"],
            foreign_entry,
            "越界作答",
        )
        assert resp.status_code == 404

    def test_ignores_source_in_body(
        self, client, db, candidate_headers, accepted_interview
    ):
        """请求体传 source='hr' 被忽略，库中仍为 candidate。"""
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]

        resp = client.post(
            f"/api/candidate/interviews/{interview_id}/answers",
            json={
                "interview_question_id": entry_id,
                "content": "回答",
                "source": ANSWER_SOURCE_HR,
            },
            headers=candidate_headers,
        )
        assert resp.status_code == 200

        _fresh(db)
        answer = next(
            a
            for a in repository.list_answers(db, interview_id)
            if a.interview_question_id == entry_id
        )
        assert answer.source == ANSWER_SOURCE_CANDIDATE

    def test_empty_string_allowed(
        self, client, candidate_headers, accepted_interview
    ):
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]

        resp = _save(client, candidate_headers, interview_id, entry_id, "")
        assert resp.status_code == 200

    def test_hr_can_save_after_candidate_submitted(
        self, client, hr_headers, candidate_headers, accepted_interview
    ):
        """**关键**：锁定只对候选人侧生效，HR 始终可修订作答（PRD §4.4）。"""
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )

        resp = client.post(
            f"/api/interviews/{interview_id}/answers",
            json={"interview_question_id": entry_id, "content": "HR 事后修订"},
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "HR 事后修订"


# ========================= 交卷 =========================


class TestSubmit:
    def test_writes_submitted_at_to_all_questions(
        self, client, db, candidate_headers, accepted_interview
    ):
        """3 题只答 1 题 → 交卷后全部题目均有作答行且都有 submitted_at。"""
        interview_id = accepted_interview["interview_id"]
        entries = _entry_ids(client, candidate_headers, interview_id)[:3]
        _save(client, candidate_headers, interview_id, entries[0], "只答这一题")

        resp = client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )
        assert resp.status_code == 200

        _fresh(db)
        answers = {
            a.interview_question_id: a
            for a in repository.list_answers(db, interview_id)
        }
        for entry_id in entries:
            assert entry_id in answers, "未作答的题应被补上作答行"
            assert answers[entry_id].submitted_at is not None
        assert answers[entries[1]].content == ""
        assert answers[entries[2]].content == ""

    def test_answered_count_excludes_blank(
        self, client, candidate_headers, accepted_interview
    ):
        interview_id = accepted_interview["interview_id"]
        entries = _entry_ids(client, candidate_headers, interview_id)
        _save(client, candidate_headers, interview_id, entries[0], "答了这一题")

        resp = client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )
        assert resp.json()["answered_count"] == 1  # 不是题目总数

    def test_is_idempotent(self, client, candidate_headers, accepted_interview):
        interview_id = accepted_interview["interview_id"]
        url = f"/api/candidate/interviews/{interview_id}/submit"

        first = client.post(url, headers=candidate_headers).json()
        second = client.post(url, headers=candidate_headers).json()

        assert first["submitted_at"] == second["submitted_at"]

    def test_after_hr_completed_returns_success(
        self, client, hr_headers, candidate_headers, accepted_interview
    ):
        """幂等检查先于状态检查 —— 否则重试会看到一个自相矛盾的 409。"""
        interview_id = accepted_interview["interview_id"]
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )
        client.post(
            f"/api/interviews/{interview_id}/complete", headers=hr_headers
        )

        resp = client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )
        assert resp.status_code == 200

    def test_does_not_change_interview_status(
        self, client, db, candidate_headers, accepted_interview
    ):
        """交卷不改面试状态（PRD §5.1）—— 仍需 HR 手动 /complete。"""
        interview_id = accepted_interview["interview_id"]
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )

        _fresh(db)
        assert repository.get_by_id(db, interview_id).status == STATUS_ONGOING

    def test_other_candidates_interview_forbidden(
        self, client, accepted_interview, other_candidate_headers
    ):
        resp = client.post(
            f"/api/candidate/interviews/{accepted_interview['interview_id']}/submit",
            headers=other_candidate_headers,
        )
        assert resp.status_code == 403

    def test_submitted_answer_is_read_by_evaluation_as_zero(
        self, client, db, candidate_headers, accepted_interview
    ):
        """交卷后未作答的题在评估侧视为「未作答」（按 0 分处理）。

        补的空串被 get_items_for_evaluation 归一为 None —— 这正是既有约定：
        空串表示未作答，评估按 0 分算。
        """
        interview_id = accepted_interview["interview_id"]
        entries = _entry_ids(client, candidate_headers, interview_id)
        _save(client, candidate_headers, interview_id, entries[0], "只有这一题有内容")
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )

        _fresh(db)
        items = {
            item.interview_question_id: item
            for item in interview_service.get_items_for_evaluation(db, interview_id)
        }
        assert items[entries[0]].answer == "只有这一题有内容"
        assert items[entries[1]].answer is None


# ======================= HR 覆盖 =======================


class TestHrOverwrite:
    def test_keeps_source_candidate(
        self, client, db, hr_headers, candidate_headers, accepted_interview, hr_user
    ):
        """覆盖后 source 仍为 candidate，answered_by 变为 HR，submitted_at 保留。

        source 答「最初从哪条通道进来」，answered_by 答「最后是谁改的」——
        两个不同的事实（PRD §5.2）。
        """
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]
        _save(client, candidate_headers, interview_id, entry_id, "候选人原答")
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )

        client.post(
            f"/api/interviews/{interview_id}/answers",
            json={"interview_question_id": entry_id, "content": "HR 覆盖后的内容"},
            headers=hr_headers,
        )

        _fresh(db)
        answer = next(
            a
            for a in repository.list_answers(db, interview_id)
            if a.interview_question_id == entry_id
        )
        assert answer.content == "HR 覆盖后的内容"
        assert answer.source == ANSWER_SOURCE_CANDIDATE  # 来源未被改写
        assert answer.answered_by == hr_user.id  # 最后修改者是 HR
        assert answer.submitted_at is not None  # 交卷事实保留

    def test_keeps_candidate_locked(
        self, client, hr_headers, candidate_headers, accepted_interview
    ):
        """HR 覆盖后候选人仍不能改 —— 锁定判据是 submitted_at，与谁最后修改无关。"""
        interview_id = accepted_interview["interview_id"]
        entry_id = _entry_ids(client, candidate_headers, interview_id)[0]
        _save(client, candidate_headers, interview_id, entry_id, "候选人原答")
        client.post(
            f"/api/candidate/interviews/{interview_id}/submit",
            headers=candidate_headers,
        )
        client.post(
            f"/api/interviews/{interview_id}/answers",
            json={"interview_question_id": entry_id, "content": "HR 覆盖"},
            headers=hr_headers,
        )

        resp = _save(client, candidate_headers, interview_id, entry_id, "候选人想再改")
        assert resp.status_code == 409

    def test_evaluation_supply_unchanged(
        self, client, db, candidate_headers, accepted_interview
    ):
        """加列后 get_items_for_evaluation 的语义不变。"""
        interview_id = accepted_interview["interview_id"]
        entries = _entry_ids(client, candidate_headers, interview_id)
        _save(client, candidate_headers, interview_id, entries[0], "回答内容")

        _fresh(db)
        items = interview_service.get_items_for_evaluation(db, interview_id)
        assert len(items) == len(entries)
        assert [item.seq for item in items] == list(range(1, len(entries) + 1))
        assert all(item.question for item in items)
        assert all(item.dimension for item in items)


# ========================= 权限 =========================


class TestPermissions:
    def test_invitation_endpoints_reject_candidate(
        self, client, db, hr_headers, candidate_headers, position
    ):
        interview = client.post(
            "/api/interviews",
            json={"position_id": position.id, "candidate_name": "张三"},
            headers=hr_headers,
        ).json()
        invitation = client.post(
            f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
        ).json()

        assert (
            client.post(
                f"/api/interviews/{interview['id']}/invitations",
                headers=candidate_headers,
            ).status_code
            == 403
        )
        assert (
            client.get(
                f"/api/interviews/{interview['id']}/invitations",
                headers=candidate_headers,
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/interviews/{interview['id']}/invitations/{invitation['id']}",
                headers=candidate_headers,
            ).status_code
            == 403
        )

    def test_candidate_endpoints_reject_hr_and_admin(
        self, client, hr_headers, admin_headers, accepted_interview
    ):
        """候选人侧守卫**精确匹配** —— admin 与 hr 都不通行。"""
        interview_id = accepted_interview["interview_id"]
        urls = [
            "/api/candidate/interviews",
            f"/api/candidate/interviews/{interview_id}",
        ]
        for url in urls:
            assert client.get(url, headers=hr_headers).status_code == 403
            assert client.get(url, headers=admin_headers).status_code == 403

        assert (
            client.post(
                f"/api/candidate/interviews/{interview_id}/submit", headers=hr_headers
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/candidate/interviews/{interview_id}/submit",
                headers=admin_headers,
            ).status_code
            == 403
        )

    def test_invitation_endpoints_reject_anonymous(self, client, accepted_interview):
        interview_id = accepted_interview["interview_id"]
        assert (
            client.get(f"/api/interviews/{interview_id}/invitations").status_code == 401
        )
        assert (
            client.get(f"/api/candidate/interviews/{interview_id}").status_code == 401
        )
