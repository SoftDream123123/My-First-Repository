"""端到端流程测试（计划书 module-08 §4 的三条核心流程 + §5.1 数据隔离）。

各模块自己的测试验证自己的边界；本文件验证**串起来之后**的真实行为——
岗位 → 题库 → 面试出题 → 录入回答 → 流式评估 → 报告，一条链路走到底，
用的是真实的 HTTP 客户端与 Mock Provider（不需要网络、不需要 API Key）。
"""

import pytest

from tests.sse_helpers import read_events

DIMS = ["沟通能力", "专业能力", "逻辑思维", "文化契合"]

ANSWER = "我在上一家公司负责过一个高并发的订单系统重构项目，通过引入缓存与分库分表，" * 3

POSITION_JD = "负责后端服务的开发与维护，要求熟悉 Python 与数据库设计。"


@pytest.fixture
def position_with_bank(client, hr_headers):
    """一个含 4 个维度的岗位 + 3 道手工题（分属前 3 个维度，各 1 道）。"""
    resp = client.post(
        "/api/positions",
        json={
            "name": "后端工程师",
            "jd": POSITION_JD,
            "evaluation_dimensions": list(DIMS),
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201
    position_id = resp.json()["id"]

    for dimension in DIMS[:3]:
        created = client.post(
            "/api/questions",
            json={
                "position_id": position_id,
                "dimension": dimension,
                "content": f"关于{dimension}的一道手工题目内容描述",
            },
            headers=hr_headers,
        )
        assert created.status_code == 201

    return position_id


@pytest.fixture
def interview(client, hr_headers, position_with_bank):
    """创建面试（同步出题），返回详情。"""
    resp = client.post(
        "/api/interviews",
        json={"position_id": position_with_bank, "candidate_name": "张三"},
        headers=hr_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def completed_interview(client, hr_headers, interview):
    """逐题作答并标记完成的面试 —— 评估流程的前置状态。"""
    for question in interview["questions"]:
        saved = client.post(
            f"/api/interviews/{interview['id']}/answers",
            json={
                "interview_question_id": question["interview_question_id"],
                "content": ANSWER,
            },
            headers=hr_headers,
        )
        assert saved.status_code == 200

    done = client.post(
        f"/api/interviews/{interview['id']}/complete", headers=hr_headers
    )
    assert done.json()["status"] == "completed"
    return interview


# ------------------- 流程① 创建面试 + 出题（同步） -------------------


class TestFlow1CreateAndAssemble:
    def test_assembles_n_plus_m_questions_in_order(self, interview):
        """§4.1-3/4：共 8 题（3 手工 + 5 AI），前三道手工，seq 从 1 连续。"""
        assert interview["status"] == "ongoing"
        assert interview["question_count"] == 8

        questions = interview["questions"]
        assert [q["seq"] for q in questions] == list(range(1, 9))
        assert [q["source"] for q in questions] == ["bank"] * 3 + ["ai"] * 5
        assert all(q["dimension"] in DIMS for q in questions)
        assert all(q["content"].strip() for q in questions)
        assert all(q["answer"] is None for q in questions)

    def test_ai_questions_are_written_back_to_bank(
        self, client, hr_headers, position_with_bank, interview
    ):
        """§4.1-5：出题会往题库补 5 道 source='ai' 的题目。"""
        bank = client.get(
            f"/api/questions?position_id={position_with_bank}", headers=hr_headers
        ).json()

        assert len(bank) == 8  # 3 手工 + 5 AI
        assert len([q for q in bank if q["source"] == "ai"]) == 5

    def test_historical_interview_keeps_snapshot(
        self, client, hr_headers, position_with_bank, interview
    ):
        """§4.1-6：改题库题干后，面试详情仍显示出题时的快照。"""
        first = interview["questions"][0]
        bank = client.get(
            f"/api/questions?position_id={position_with_bank}", headers=hr_headers
        ).json()
        bank_row = next(q for q in bank if q["content"] == first["content"])

        edited = client.put(
            f"/api/questions/{bank_row['id']}",
            json={
                "position_id": position_with_bank,
                "dimension": first["dimension"],
                "content": "题干已被彻底改写，不应出现在历史面试里",
            },
            headers=hr_headers,
        )
        assert edited.status_code == 200

        refreshed = client.get(
            f"/api/interviews/{interview['id']}", headers=hr_headers
        ).json()
        assert [q["content"] for q in refreshed["questions"]] == [
            q["content"] for q in interview["questions"]
        ]

    def test_position_dimension_change_does_not_affect_history(
        self, client, hr_headers, position_with_bank, interview
    ):
        """§4.1-7：岗位维度改小后，历史面试的题目与维度不受影响。"""
        shrunk = client.put(
            f"/api/positions/{position_with_bank}",
            json={
                "name": "后端工程师",
                "jd": POSITION_JD,
                "evaluation_dimensions": [DIMS[0]],
            },
            headers=hr_headers,
        )
        assert shrunk.status_code == 200

        after = client.get(f"/api/interviews/{interview['id']}", headers=hr_headers).json()
        assert [q["dimension"] for q in after["questions"]] == [
            q["dimension"] for q in interview["questions"]
        ]
        assert after["question_count"] == 8


# --------------------- 流程② 面试进行（手动录入） ---------------------


class TestFlow2Recording:
    def test_record_edit_complete_rollback(self, client, hr_headers, interview):
        interview_id = interview["id"]
        questions = interview["questions"]
        answer_url = f"/api/interviews/{interview_id}/answers"

        # §4.2-1：逐题录入，最后一题留空
        for question in questions[:-1]:
            resp = client.post(
                answer_url,
                json={
                    "interview_question_id": question["interview_question_id"],
                    "content": ANSWER,
                },
                headers=hr_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["answer"] == ANSWER
            assert resp.json()["recorded_at"] is not None

        assert client.get("/api/interviews", headers=hr_headers).json()[0][
            "answered_count"
        ] == 7

        # §4.2-2：修改已录入的回答 —— 更新而非新增，条数不变
        first = questions[0]
        resp = client.post(
            answer_url,
            json={
                "interview_question_id": first["interview_question_id"],
                "content": "修改后的回答内容",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "修改后的回答内容"
        assert client.get("/api/interviews", headers=hr_headers).json()[0][
            "answered_count"
        ] == 7

        # §4.2-3：标记完成 → completed_at 非空
        resp = client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)
        assert resp.json()["status"] == "completed"
        assert resp.json()["completed_at"] is not None

        # §4.2-4：完成后不可再修改回答
        resp = client.post(
            answer_url,
            json={"interview_question_id": first["interview_question_id"], "content": "完成后修改"},
            headers=hr_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

        # §4.2-5：回退到进行中 → 可改 → 再完成
        resp = client.post(f"/api/interviews/{interview_id}/rollback", headers=hr_headers)
        assert resp.json()["status"] == "ongoing"
        assert resp.json()["completed_at"] is None

        resp = client.post(
            answer_url,
            json={
                "interview_question_id": first["interview_question_id"],
                "content": "回退之后重新修改的回答",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200

        resp = client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)
        assert resp.json()["status"] == "completed"
        assert resp.json()["completed_at"] is not None


# ----------------------- 流程③ 流式评估（SSE） -----------------------


class TestFlow3StreamingEvaluation:
    def test_evaluate_stream_report_reevaluate(
        self, client, hr_headers, completed_interview
    ):
        interview_id = completed_interview["id"]
        stream_url = f"/api/interviews/{interview_id}/evaluation/stream"

        # §4.3-1：触发评估 → evaluating，并拿到流地址
        resp = client.post(f"/api/interviews/{interview_id}/evaluate", headers=hr_headers)
        assert resp.status_code == 202
        assert resp.json()["status"] == "evaluating"
        assert resp.json()["stream_url"] == stream_url

        # §4.3-2/3/4：逐题 → 逐维度 → 汇总，按序到达后以 done 收尾
        events = read_events(client, stream_url, hr_headers)
        assert [name for name, _ in events] == (
            ["question"] * 8 + ["dimension"] * len(DIMS) + ["report", "done"]
        )

        # §4.3-5：逐题分与维度分均在 0–10，保留 1 位小数
        for name, payload in events:
            if name in ("question", "dimension"):
                assert 0.0 <= payload["score"] <= 10.0
                assert round(payload["score"], 1) == payload["score"]

        # §4.3-6/7：报告完整，且重新 GET（等价于刷新页面）仍能读到
        report = client.get(f"/api/interviews/{interview_id}/report", headers=hr_headers)
        assert report.status_code == 200

        body = report.json()
        assert len(body["question_scores"]) == 8
        assert len(body["dimension_scores"]) == len(DIMS)
        assert 0.0 <= body["overall_score"] <= 10.0
        assert body["conclusion"]
        assert body["strengths"] and body["weaknesses"]
        assert {d["dimension"] for d in body["dimension_scores"]} == set(DIMS)

        detail = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
        assert detail["status"] == "evaluated"

        # §4.3-8：重新评估 —— 进度重走，逐题条数不翻倍
        resp = client.post(f"/api/interviews/{interview_id}/evaluate", headers=hr_headers)
        assert resp.status_code == 202
        assert [name for name, _ in read_events(client, stream_url, hr_headers)][-1] == "done"

        again = client.get(f"/api/interviews/{interview_id}/report", headers=hr_headers).json()
        assert len(again["question_scores"]) == 8
        assert len(again["dimension_scores"]) == len(DIMS)


# ------------------------- §5.1 数据隔离 -------------------------


class TestDataIsolationAcrossModules:
    def test_other_hr_sees_nothing(
        self, client, hr_headers, other_hr_headers, position_with_bank, interview
    ):
        """§5.1-2/3：hr_B 三个列表均为空，直接改 id 访问详情为 403。"""
        assert client.get("/api/positions", headers=hr_headers).json()
        assert client.get("/api/questions", headers=hr_headers).json()
        assert client.get("/api/interviews", headers=hr_headers).json()

        for path in ("/api/positions", "/api/questions", "/api/interviews"):
            assert client.get(path, headers=other_hr_headers).json() == []

        assert (
            client.get(
                f"/api/positions/{position_with_bank}", headers=other_hr_headers
            ).status_code
            == 403
        )
        assert (
            client.get(
                f"/api/interviews/{interview['id']}", headers=other_hr_headers
            ).status_code
            == 403
        )

    def test_admin_sees_everything(
        self, client, admin_headers, position_with_bank, interview
    ):
        """§5.1-5：admin 三个列表均可见到 hr 的数据。"""
        for path in ("/api/positions", "/api/questions", "/api/interviews"):
            assert client.get(path, headers=admin_headers).json()

        assert (
            client.get(
                f"/api/interviews/{interview['id']}", headers=admin_headers
            ).status_code
            == 200
        )


# ------------- 流程⑥ 简历关联与按简历补题（MVP-3） -------------


@pytest.fixture
def candidate_session(client):
    """候选人自助注册 → 登录 → 返回登录头。"""
    registered = client.post(
        "/api/auth/register",
        json={"username": "e2e_candidate", "password": "cand12345678"},
    )
    assert registered.status_code == 201, registered.text

    login = client.post(
        "/api/auth/login",
        json={"username": "e2e_candidate", "password": "cand12345678"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}


@pytest.fixture
def accepted_interview_id(client, hr_headers, candidate_session, interview):
    """HR 发邀请码 → 候选人凭码接受并绑定该面试。"""
    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    accepted = client.post(
        f"/api/candidate/invitations/{invitation['code']}/accept",
        json={"username": "e2e_candidate", "password": "cand12345678"},
        headers=candidate_session,
    )
    assert accepted.status_code == 200, accepted.text
    return interview["id"]


def _create_resume(client, candidate_session, title="张三-后端开发"):
    resp = client.post(
        "/api/candidate/resumes",
        json={
            "title": title,
            "content": (
                "五年 Python 后端开发经验，熟悉 FastAPI 与 MySQL，"
                "主导过订单系统重构与支付链路拆分。"
            ),
        },
        headers=candidate_session,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_bank_questions(client, hr_headers, position_id, dimensions, prefix="补题用"):
    """往岗位题库补题 —— 本场面试已把原题库抽空，补题需要新的候选。"""
    for index, dimension in enumerate(dimensions):
        created = client.post(
            "/api/questions",
            json={
                "position_id": position_id,
                "dimension": dimension,
                "content": f"{prefix}的{dimension}题目第{index + 1}道内容描述",
            },
            headers=hr_headers,
        )
        assert created.status_code == 201, created.text


class TestFlow6ResumeDrivenMatching:
    def test_link_resume_then_match(
        self, client, hr_headers, candidate_session, accepted_interview_id, position_with_bank
    ):
        interview_id = accepted_interview_id

        # 1) 候选人录入简历并关联到面试（这是简历进入出题流程的唯一通路）
        resume = _create_resume(client, candidate_session)
        linked = client.put(
            f"/api/candidate/interviews/{interview_id}/resume",
            json={"resume_id": resume["id"]},
            headers=candidate_session,
        )
        assert linked.status_code == 200, linked.text

        # 2) HR 只读该简历 —— 权限判据是「面试属于我」
        seen = client.get(f"/api/interviews/{interview_id}/resume", headers=hr_headers)
        assert seen.status_code == 200
        assert seen.json()["resume_id"] == resume["id"]
        assert "created_by" not in seen.json()

        # 3) 补题
        _add_bank_questions(client, hr_headers, position_with_bank, DIMS[:3])
        before = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()

        body = client.post(
            f"/api/interviews/{interview_id}/questions/match", headers=hr_headers
        ).json()
        assert body["added_count"] > 0
        assert body["total_questions"] == before["question_count"] + body["added_count"]

        # 4) 追加项带来源与理由；HR 看得到，候选人看不到
        detail = client.get(
            f"/api/interviews/{interview_id}", headers=hr_headers
        ).json()
        added_ids = {item["interview_question_id"] for item in body["added"]}
        added_rows = [
            q for q in detail["questions"] if q["interview_question_id"] in added_ids
        ]
        assert all(q["source"] == "resume_match" for q in added_rows)
        assert all(q["match_reason"] for q in added_rows)

        mine = client.get(
            f"/api/candidate/interviews/{interview_id}", headers=candidate_session
        ).json()
        assert all("match_reason" not in q for q in mine["questions"])

    def test_repeated_match_never_duplicates(
        self, client, hr_headers, candidate_session, accepted_interview_id, position_with_bank
    ):
        interview_id = accepted_interview_id
        resume = _create_resume(client, candidate_session)
        client.put(
            f"/api/candidate/interviews/{interview_id}/resume",
            json={"resume_id": resume["id"]},
            headers=candidate_session,
        )
        _add_bank_questions(client, hr_headers, position_with_bank, DIMS[:3] + DIMS[:3])

        client.post(f"/api/interviews/{interview_id}/questions/match", headers=hr_headers)
        client.post(f"/api/interviews/{interview_id}/questions/match", headers=hr_headers)

        detail = client.get(
            f"/api/interviews/{interview_id}", headers=hr_headers
        ).json()
        question_ids = [q["interview_question_id"] for q in detail["questions"]]
        assert len(question_ids) == len(set(question_ids))

    def test_match_without_resume_409(self, client, hr_headers, accepted_interview_id):
        resp = client.post(
            f"/api/interviews/{accepted_interview_id}/questions/match", headers=hr_headers
        )
        assert resp.status_code == 409


# ------------- 流程⑦ 面试前准备（MVP-3） -------------


class TestFlow7InterviewPrep:
    def _url(self, interview_id):
        return f"/api/interviews/{interview_id}/prep"

    def _link_resume(self, client, candidate_session, interview_id):
        resume = _create_resume(client, candidate_session)
        client.put(
            f"/api/candidate/interviews/{interview_id}/resume",
            json={"resume_id": resume["id"]},
            headers=candidate_session,
        )

    def test_generate_edit_regenerate_then_freeze(
        self, client, hr_headers, candidate_session, accepted_interview_id
    ):
        interview_id = accepted_interview_id
        self._link_resume(client, candidate_session, interview_id)

        # 未生成时读取 → 404（前端据此显示「生成准备提纲」按钮）
        assert client.get(self._url(interview_id), headers=hr_headers).status_code == 404

        created = client.post(self._url(interview_id), headers=hr_headers)
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["outline"] and body["focus_points"] and body["question_plan"]
        assert body["edited_at"] is None
        # 已关联简历 → 考察重点里应有「简历核对」
        assert any(point["dimension"] == "简历核对" for point in body["focus_points"])

        # 编辑：整体覆盖三部分，edited_at 落上，generated_at 不变
        payload = {
            "outline": [{**body["outline"][0], "notes": "HR 手改过的要点"}],
            "focus_points": body["focus_points"],
            "question_plan": body["question_plan"],
        }
        edited = client.put(
            self._url(interview_id), json=payload, headers=hr_headers
        ).json()
        assert edited["outline"][0]["notes"] == "HR 手改过的要点"
        assert edited["edited_at"]
        assert edited["generated_at"] == body["generated_at"]

        # 重新生成：整体覆盖，并清掉编辑标记
        regenerated = client.post(self._url(interview_id), headers=hr_headers).json()
        assert regenerated["edited_at"] is None

        # 面试完成后冻结：生成与编辑都 409
        client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)
        assert client.post(self._url(interview_id), headers=hr_headers).status_code == 409
        assert (
            client.put(
                self._url(interview_id), json=payload, headers=hr_headers
            ).status_code
            == 409
        )
