"""API 接口测试 —— 模块 7/9：evaluation（评估 / 报告 / 导出 / 候选人反馈）。

覆盖 5 个 method-route：
    POST /api/interviews/{interview_id}/evaluate              触发评估（202）
    GET  /api/interviews/{interview_id}/evaluation/stream     SSE 流式评估
    GET  /api/interviews/{interview_id}/report                完整报告
    GET  /api/interviews/{interview_id}/report/export         导出 DOCX
    GET  /api/candidate/interviews/{interview_id}/feedback    候选人脱敏反馈

契约来源：
    docs/superpowers/specs/2026-09-15-module-06-evaluation-plan.md §4 / §5
    docs/superpowers/specs/2026-09-20-module-14-evaluation-feedback-plan.md §4
    docs/superpowers/specs/2026-09-21-module-21-evaluation-export-plan.md §4
    docs/apis/API接口文档.md §9.1–§9.5

⚠️ 本模块最重要的两条是**结构性**断言，不是值断言：
    · `CandidateFeedbackOut` 的键集合**恰好等于**白名单（多一个都不行）；
    · 原始响应文本里**根本不存在** `question_scores` / `dimension_scores` / `radar`。
    只断言「值等于 null」是不够的 —— 那说明字段在 schema 里，只是恰好为空。
"""

import pytest

from app.evaluation import stream
from tests.sse_helpers import read_events, wait_until_finished

ANSWER = "我在上一家公司负责过一个高并发的订单系统重构项目，通过引入缓存与分库分表，" * 3

FEEDBACK_KEYS = {
    "interview_id",
    "level",
    "conclusion",
    "strengths",
    "weaknesses",
    "overall_score",
    "generated_at",
}


@pytest.fixture(autouse=True)
def _clean_registry():
    """评估运行注册表是**进程内**的，用例之间必须清干净。"""
    stream.reset_registry()
    yield
    stream.reset_registry()


def _complete(client, headers, interview_id):
    resp = client.post(f"/api/interviews/{interview_id}/complete", headers=headers)
    assert resp.status_code == 200, resp.text


def _evaluate_and_drain(client, headers, interview_id):
    """触发评估并把 SSE 流读到终结 —— 之后面试即为 `evaluated`。"""
    triggered = client.post(f"/api/interviews/{interview_id}/evaluate", headers=headers)
    assert triggered.status_code == 202, triggered.text
    events = read_events(
        client, f"/api/interviews/{interview_id}/evaluation/stream", headers
    )
    wait_until_finished(interview_id)
    return events


@pytest.fixture
def evaluated_interview(client, hr_headers, position, db, hr_user):
    """一个已评估完的面试（HR 侧用例的公共前置）。

    前置用 service 直接造（更快也更稳），被用例测的那个端点才走 HTTP。
    """
    from app.interview import service as interview_service
    from app.interview.schemas import InterviewCreate

    detail = interview_service.create_interview(
        db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
    )
    for question in detail.questions:
        interview_service.save_answer(
            db, hr_user, detail.id, question.interview_question_id, ANSWER
        )
    interview_service.complete_interview(db, hr_user, detail.id)
    _evaluate_and_drain(client, hr_headers, detail.id)
    return detail.id


@pytest.fixture
def evaluated_accepted_interview(client, hr_headers, candidate_headers, accepted_interview):
    """候选人侧前置：已接受邀请、且面试已评估完。

    要先填好作答再完成 —— 否则评估拿不到回答，报告会是空的。
    """
    interview_id = accepted_interview["interview_id"]
    detail = client.get(f"/api/candidate/interviews/{interview_id}", headers=candidate_headers).json()
    for question in detail["questions"]:
        client.post(
            f"/api/candidate/interviews/{interview_id}/answers",
            json={"interview_question_id": question["interview_question_id"], "content": ANSWER},
            headers=candidate_headers,
        )
    client.post(f"/api/candidate/interviews/{interview_id}/submit", headers=candidate_headers)

    _complete(client, hr_headers, interview_id)
    _evaluate_and_drain(client, hr_headers, interview_id)
    return accepted_interview


# ===========================================================================
# 9.1 触发评估
# ===========================================================================


def test_trigger_returns_202_with_stream_url(client, hr_headers, position, practice_questions, db, hr_user):
    from app.interview import service as interview_service
    from app.interview.schemas import InterviewCreate

    detail = interview_service.create_interview(
        db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
    )
    for question in detail.questions:
        interview_service.save_answer(db, hr_user, detail.id, question.interview_question_id, ANSWER)
    interview_service.complete_interview(db, hr_user, detail.id)

    resp = client.post(f"/api/interviews/{detail.id}/evaluate", headers=hr_headers)

    assert resp.status_code == 202, "异步任务 → 202，不是 200"
    body = resp.json()
    assert body["interview_id"] == detail.id
    assert body["status"] == "evaluating"
    assert body["stream_url"] == f"/api/interviews/{detail.id}/evaluation/stream"


def test_trigger_rejects_non_completed(client, hr_headers, position, practice_questions):
    """只有 `completed` / `evaluated` 能触发；`ongoing` 是 409。"""
    created = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    resp = client.post(f"/api/interviews/{created['id']}/evaluate", headers=hr_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_trigger_nonexistent_is_404(client, hr_headers):
    assert client.post("/api/interviews/424242/evaluate", headers=hr_headers).status_code == 404


def test_trigger_other_hrs_interview_is_403(client, hr_headers, other_hr_headers, other_position):
    theirs = client.post(
        "/api/interviews",
        json={"position_id": other_position.id, "candidate_name": "李四"},
        headers=other_hr_headers,
    ).json()

    assert client.post(f"/api/interviews/{theirs['id']}/evaluate", headers=hr_headers).status_code == 403


def test_trigger_requires_token(client, position, practice_questions, db, hr_user):
    from app.interview import service as interview_service
    from app.interview.schemas import InterviewCreate

    detail = interview_service.create_interview(
        db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
    )
    interview_service.complete_interview(db, hr_user, detail.id)

    assert client.post(f"/api/interviews/{detail.id}/evaluate").status_code == 401


# ===========================================================================
# 9.2 SSE 流式评估
# ===========================================================================


def test_stream_event_sequence(client, hr_headers, position, practice_questions, db, hr_user):
    """事件序：`question`×N → `dimension`×M → `report`×1 → `done`。

    这条顺序是前端增量渲染的全部依据（逐题刷分数 → 雷达图逐维生长 → 出汇总）。
    """
    from app.interview import service as interview_service
    from app.interview.schemas import InterviewCreate

    detail = interview_service.create_interview(
        db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
    )
    for question in detail.questions:
        interview_service.save_answer(db, hr_user, detail.id, question.interview_question_id, ANSWER)
    interview_service.complete_interview(db, hr_user, detail.id)

    events = _evaluate_and_drain(client, hr_headers, detail.id)
    names = [name for name, _ in events]

    assert names[-1] == "done", f"必须以 done 收尾，实际序列：{names}"
    assert names.count("report") == 1
    assert "error" not in names, "done 与 error 互斥"

    q_count = names.count("question")
    dim_count = names.count("dimension")
    assert q_count == 8, "逐题评分事件数 = 题目数"
    assert dim_count == len(position.evaluation_dimensions)
    assert names.index("report") == q_count + dim_count, "report 在最后一批评分之后"

    # 分数必须落在 0–10 且 1 位小数
    for name, payload in events:
        if name in {"question", "dimension"}:
            assert 0.0 <= payload["score"] <= 10.0
            assert round(payload["score"], 1) == payload["score"]


def test_stream_headers(client, hr_headers, evaluated_interview):
    """SSE 三件套头：`text/event-stream` + `no-cache` + `X-Accel-Buffering: no`。

    最后一个防的是 Nginx 之类的反向代理缓冲 —— 少了它前端会「一次性收到全部事件」，
    看起来像流式其实不是。
    """
    with client.stream(
        "GET", f"/api/interviews/{evaluated_interview}/evaluation/stream", headers=hr_headers
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "no-cache" in response.headers.get("cache-control", "")
        assert response.headers.get("x-accel-buffering") == "no"


def test_stream_reconnect_replays_from_beginning(client, hr_headers, evaluated_interview):
    """断线重连 → **从头全量重放**（前端不需要自己缓存进度）。"""
    events = read_events(
        client, f"/api/interviews/{evaluated_interview}/evaluation/stream", headers=hr_headers
    )

    names = [name for name, _ in events]
    assert names.count("question") == 8, "重连也要拿到全部逐题事件"
    assert names[-1] == "done"


def test_stream_guard_runs_before_the_stream_opens(client, candidate_headers, hr_headers, evaluated_interview):
    """⚠️ 403 必须在开流**之前**返回 —— 响应不能是 `text/event-stream`。

    否则前端已经进入「正在接收流」的状态，而流里永远不会有事件，表现为静默挂住。
    """
    resp = client.get(
        f"/api/interviews/{evaluated_interview}/evaluation/stream", headers=candidate_headers
    )

    assert resp.status_code == 403
    assert "text/event-stream" not in resp.headers.get("content-type", "")
    assert resp.json()["code"] == "FORBIDDEN"


def test_stream_nonexistent_is_404(client, hr_headers):
    assert client.get("/api/interviews/424242/evaluation/stream", headers=hr_headers).status_code == 404


# ===========================================================================
# 9.3 报告
# ===========================================================================


def test_report_returns_full_structure(client, hr_headers, evaluated_interview, position):
    resp = client.get(f"/api/interviews/{evaluated_interview}/report", headers=hr_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {
        "interview_id",
        "candidate_name",
        "position_name",
        "overall_score",
        "conclusion",
        "strengths",
        "weaknesses",
        "evaluated_at",
        "dimension_scores",
        "question_scores",
    }
    assert body["interview_id"] == evaluated_interview
    assert body["position_name"] == position.name
    assert len(body["dimension_scores"]) == len(position.evaluation_dimensions)
    assert len(body["question_scores"]) == 8
    assert body["strengths"] and body["weaknesses"], "两者都**永不为空**（无则给占位文案）"


def test_report_scores_are_in_range_with_one_decimal(client, hr_headers, evaluated_interview):
    body = client.get(f"/api/interviews/{evaluated_interview}/report", headers=hr_headers).json()

    scores = [body["overall_score"]]
    scores += [d["score"] for d in body["dimension_scores"]]
    scores += [q["score"] for q in body["question_scores"]]

    for score in scores:
        assert 0.0 <= score <= 10.0, score
        assert round(score, 1) == score, score


def test_report_question_scores_are_ordered_by_seq(client, hr_headers, evaluated_interview):
    body = client.get(f"/api/interviews/{evaluated_interview}/report", headers=hr_headers).json()
    seqs = [q["seq"] for q in body["question_scores"]]

    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))


def test_report_before_evaluation_is_409(client, hr_headers, position, practice_questions):
    created = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    resp = client.get(f"/api/interviews/{created['id']}/report", headers=hr_headers)

    assert resp.status_code == 409
    assert "尚未完成" in resp.json()["message"]


def test_report_nonexistent_is_404(client, hr_headers):
    assert client.get("/api/interviews/424242/report", headers=hr_headers).status_code == 404


def test_report_other_hrs_interview_is_403(client, hr_headers, other_hr_headers, other_position):
    theirs = client.post(
        "/api/interviews",
        json={"position_id": other_position.id, "candidate_name": "李四"},
        headers=other_hr_headers,
    ).json()

    assert client.get(f"/api/interviews/{theirs['id']}/report", headers=hr_headers).status_code == 403


def test_report_rejects_candidate(client, candidate_headers, evaluated_interview):
    """候选人**没有**读报告的路 —— 他们只能读脱敏反馈（§9.5）。"""
    resp = client.get(f"/api/interviews/{evaluated_interview}/report", headers=candidate_headers)

    assert resp.status_code == 403


# ===========================================================================
# 9.4 导出 DOCX
# ===========================================================================


def test_export_returns_docx_binary_with_disposition(client, hr_headers, evaluated_interview):
    resp = client.get(
        f"/api/interviews/{evaluated_interview}/report/export?format=docx", headers=hr_headers
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert "filename*=UTF-8''" in disposition, "中文名走 RFC 5987"
    assert resp.content[:2] == b"PK", "DOCX 本质是 zip"


def test_export_format_defaults_to_docx(client, hr_headers, evaluated_interview):
    resp = client.get(f"/api/interviews/{evaluated_interview}/report/export", headers=hr_headers)

    assert resp.status_code == 200


def test_export_rejects_unknown_format_before_checking_state(client, hr_headers, position, practice_questions):
    """⚠️ `format` 的校验在读报告**之前** —— 状态不对也先报 400 而非 409。"""
    created = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    resp = client.get(
        f"/api/interviews/{created['id']}/report/export?format=pdf", headers=hr_headers
    )

    assert resp.status_code == 400, f"应因格式被拒，实际 {resp.status_code}"
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_export_before_evaluation_is_409(client, hr_headers, position, practice_questions):
    created = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    resp = client.get(
        f"/api/interviews/{created['id']}/report/export?format=docx", headers=hr_headers
    )

    assert resp.status_code == 409


def test_export_nonexistent_is_404(client, hr_headers):
    resp = client.get("/api/interviews/424242/report/export?format=docx", headers=hr_headers)

    assert resp.status_code == 404


def test_export_isolated_and_role_guarded(client, hr_headers, candidate_headers, evaluated_interview):
    resp = client.get(
        f"/api/interviews/{evaluated_interview}/report/export?format=docx", headers=candidate_headers
    )

    assert resp.status_code == 403, "候选人不能导出 HR 报告"


def test_candidate_feedback_export_route_does_not_exist(client, candidate_headers, evaluated_accepted_interview):
    """候选人的脱敏反馈**不提供导出**（PRD §4.12 明确不做）。"""
    resp = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback/export",
        headers=candidate_headers,
    )

    assert resp.status_code == 404


# ===========================================================================
# 9.5 候选人脱敏反馈
# ===========================================================================


def test_feedback_returns_exactly_the_whitelist(client, candidate_headers, evaluated_accepted_interview):
    """⚠️ 键集合**恰好等于**白名单 —— 用 `==` 而不是 `>=`。

    用子集断言的话，某天有人往 schema 里加一个 `question_scores` 字段，
    用例照样绿。脱敏必须靠「结构上不存在」来保证，所以这里必须相等。
    """
    resp = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=candidate_headers,
    )

    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == FEEDBACK_KEYS


def test_feedback_never_exposes_per_question_or_dimension_data(
    client, candidate_headers, evaluated_accepted_interview
):
    """在**原始响应文本**里搜，而不是只看解析后的键。

    解析后没有、但被嵌在某个字符串里（比如 conclusion 里带了一段 JSON），
    也算泄漏 —— 所以要对着 `resp.text` 搜。
    """
    resp = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=candidate_headers,
    )

    for forbidden in ("question_scores", "dimension_scores", "radar", "per_question"):
        assert forbidden not in resp.text, f"响应里泄漏了 {forbidden}"


def test_feedback_summary_hides_overall_score(client, candidate_headers, evaluated_accepted_interview):
    """默认 `summary` 档：`overall_score` 为 `null`（总分属「评估结果」，不属「候选人文案」）。"""
    body = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=candidate_headers,
    ).json()

    assert body["level"] == "summary"
    assert body["overall_score"] is None
    assert body["conclusion"] and body["strengths"] and body["weaknesses"]


def test_feedback_client_cannot_escalate_the_level(
    client, candidate_headers, evaluated_accepted_interview, monkeypatch
):
    """`?level=full` **无效** —— 档位只认服务端配置；顺带验证配置改成 full 后总分才下发。"""
    url = f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback"

    escalated = client.get(f"{url}?level=full", headers=candidate_headers).json()
    assert escalated["level"] == "summary", "客户端不能自己提档"
    assert escalated["overall_score"] is None

    from app.core.config import get_settings

    monkeypatch.setenv("CANDIDATE_FEEDBACK_LEVEL", "full")
    get_settings.cache_clear()
    try:
        opened = client.get(url, headers=candidate_headers).json()
        assert opened["level"] == "full"
        assert opened["overall_score"] is not None
        assert 0.0 <= opened["overall_score"] <= 10.0
        # 放开档位也**不放开**逐题分与维度分
        assert set(opened) == FEEDBACK_KEYS
    finally:
        get_settings.cache_clear()


def test_feedback_conclusion_has_no_hire_decision_wording(client, candidate_headers, evaluated_accepted_interview):
    """⚠️ 结论**不带去留判断**（PRD §4.9 修正）。

    「建议进入下一轮 / 不建议继续推进」这类话应由 HR 另行沟通，
    不应该出现在当事人自己能读到的页面上。
    """
    body = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=candidate_headers,
    ).json()

    banned = ("下一轮", "不建议", "不予", "淘汰", "录用", "通过面试", "不通过")
    hits = [w for w in banned if w in body["conclusion"]]
    assert not hits, f"结论里出现了去留判断：{hits} —— {body['conclusion']}"


def test_feedback_strengths_match_the_hr_report_items(
    client, hr_headers, candidate_headers, evaluated_accepted_interview
):
    """优点 / 待改进的**条目**与 HR 报告逐条一致（便于两处对照），只有结论被重写。"""
    interview_id = evaluated_accepted_interview["interview_id"]
    report = client.get(f"/api/interviews/{interview_id}/report", headers=hr_headers).json()
    feedback = client.get(
        f"/api/candidate/interviews/{interview_id}/feedback", headers=candidate_headers
    ).json()

    assert feedback["strengths"] == report["strengths"]
    assert feedback["weaknesses"] == report["weaknesses"]


def test_feedback_before_evaluation_is_409(client, candidate_headers, accepted_interview):
    resp = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/feedback",
        headers=candidate_headers,
    )

    assert resp.status_code == 409
    assert "尚未完成" in resp.json()["message"]


def test_feedback_without_accepted_invitation_is_403(client, other_candidate_headers, evaluated_accepted_interview):
    resp = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=other_candidate_headers,
    )

    assert resp.status_code == 403


def test_feedback_nonexistent_interview_is_404(client, candidate_headers):
    resp = client.get("/api/candidate/interviews/424242/feedback", headers=candidate_headers)

    assert resp.status_code == 404


def test_feedback_rejects_hr_side(client, hr_headers, evaluated_accepted_interview):
    """HR 侧的 token 不能读候选人反馈（守卫精确匹配）。"""
    resp = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=hr_headers,
    )

    assert resp.status_code == 403


def test_feedback_ai_failure_is_502(client, candidate_headers, evaluated_accepted_interview, monkeypatch):
    """首次生成反馈时 AI 挂了 → 502（不落缓存），而不是给出半截文案。"""
    from app.core.exceptions import AIProviderError

    class _Boom:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise AIProviderError()

            return _raise

    monkeypatch.setattr("app.evaluation.service.get_provider", lambda: _Boom())

    resp = client.get(
        f"/api/candidate/interviews/{evaluated_accepted_interview['interview_id']}/feedback",
        headers=candidate_headers,
    )

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_PROVIDER_ERROR"
