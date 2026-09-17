"""evaluation SSE 层测试：事件序列、重连重放、幂等、失败回退、孤儿自愈。"""

import threading

import pytest

from app.evaluation import stream
from app.interview import service as interview_service
from app.interview.schemas import InterviewCreate
from tests.sse_helpers import read_events as _read_events
from tests.sse_helpers import wait_until_finished as _wait_until_finished

ANSWER = "我在上一家公司负责过一个高并发的订单系统重构项目，通过引入缓存与分库分表，" * 3


# ------------------------------ 辅助 ------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    stream.reset_registry()
    yield
    stream.reset_registry()


@pytest.fixture
def completed_id(db, hr_user, position):
    detail = interview_service.create_interview(
        db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
    )
    for question in detail.questions:
        interview_service.save_answer(
            db, hr_user, detail.id, question.interview_question_id, ANSWER
        )
    interview_service.complete_interview(db, hr_user, detail.id)
    return detail.id


def _trigger(client, headers, interview_id):
    return client.post(f"/api/interviews/{interview_id}/evaluate", headers=headers)


class GatedProvider:
    """被闸门挡住的 Provider —— 让「运行中」成为**确定**状态而非时间赌注。

    原本用 sleep 拖慢评估来制造观察窗口，那是时间竞态：机器一卡或后台线程被
    调度延迟，第一次运行就可能在第二次触发前跑完，于是 start_run 创建出新的
    运行对象，`get_run(id) is run_before` 这条断言随机失败（约 1/10 概率）。
    改用事件闸门后，测试不放行则运行必然停在 RUNNING，断言完全确定。
    """

    def __init__(self, delegate, gate: threading.Event):
        self._delegate = delegate
        self._gate = gate

    def generate_questions(self, *args, **kwargs):
        return self._delegate.generate_questions(*args, **kwargs)

    def evaluate_answer(self, *args, **kwargs):
        self._gate.wait(timeout=10)  # 兜底：即使测试异常也不会永久挂住线程
        return self._delegate.evaluate_answer(*args, **kwargs)

    def evaluate_dimensions(self, *args, **kwargs):
        return self._delegate.evaluate_dimensions(*args, **kwargs)

    def summarize_report(self, *args, **kwargs):
        return self._delegate.summarize_report(*args, **kwargs)


# ---------------------------- 触发端点 ----------------------------


class TestTrigger:
    def test_returns_202_and_stream_url(self, client, hr_headers, completed_id):
        resp = _trigger(client, hr_headers, completed_id)

        assert resp.status_code == 202
        body = resp.json()
        assert body["interview_id"] == completed_id
        assert body["status"] == "evaluating"
        assert body["stream_url"].endswith("/evaluation/stream")
        _wait_until_finished(completed_id)

    def test_requires_auth(self, client, completed_id):
        assert client.post(f"/api/interviews/{completed_id}/evaluate").status_code == 401

    def test_nonexistent_interview(self, client, hr_headers):
        assert _trigger(client, hr_headers, 999999).status_code == 404

    def test_other_user_forbidden(self, client, other_hr_headers, completed_id):
        assert _trigger(client, other_hr_headers, completed_id).status_code == 403

    def test_ongoing_interview_rejected(self, client, hr_headers, db, hr_user, position):
        detail = interview_service.create_interview(
            db, hr_user, InterviewCreate(position_id=position.id, candidate_name="李四")
        )
        resp = _trigger(client, hr_headers, detail.id)
        assert resp.status_code == 409

    def test_idempotent_when_running(self, client, hr_headers, completed_id, monkeypatch):
        from app.ai.factory import get_provider

        gate = threading.Event()
        monkeypatch.setattr(
            "app.evaluation.service.get_provider",
            lambda: GatedProvider(get_provider(), gate),
        )

        try:
            first = _trigger(client, hr_headers, completed_id)
            assert first.status_code == 202

            run_before = stream.get_run(completed_id)
            assert run_before is not None and run_before.status == stream.RUN_RUNNING

            second = _trigger(client, hr_headers, completed_id)

            assert second.status_code == 202
            assert second.json()["stream_url"] == first.json()["stream_url"]
            assert stream.get_run(completed_id) is run_before  # 未创建第二个运行
        finally:
            gate.set()  # 放行后台线程，避免断言失败时任务悬停

        _wait_until_finished(completed_id)


# ---------------------------- 事件流 ----------------------------


class TestEventStream:
    def test_events_sequence(self, client, hr_headers, completed_id):
        _trigger(client, hr_headers, completed_id)
        events = _read_events(
            client,
            f"/api/interviews/{completed_id}/evaluation/stream",
            hr_headers,
        )

        names = [name for name, _ in events]
        assert names == ["question"] * 8 + ["dimension"] * 3 + ["report", "done"]

    def test_ends_with_done(self, client, hr_headers, completed_id):
        _trigger(client, hr_headers, completed_id)
        events = _read_events(
            client, f"/api/interviews/{completed_id}/evaluation/stream", hr_headers
        )

        name, payload = events[-1]
        assert name == "done"
        assert payload["status"] == "evaluated"

    def test_content_type(self, client, hr_headers, completed_id):
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        with client.stream(
            "GET",
            f"/api/interviews/{completed_id}/evaluation/stream",
            headers=hr_headers,
        ) as response:
            assert response.headers["content-type"].startswith("text/event-stream")

    def test_stream_headers(self, client, hr_headers, completed_id):
        """计划书 §4.3：流式响应必须带齐防缓冲头。"""
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        with client.stream(
            "GET",
            f"/api/interviews/{completed_id}/evaluation/stream",
            headers=hr_headers,
        ) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"

    def test_requires_auth(self, client, completed_id):
        resp = client.get(f"/api/interviews/{completed_id}/evaluation/stream")
        assert resp.status_code == 401

    def test_other_user_forbidden(self, client, other_hr_headers, completed_id):
        resp = client.get(
            f"/api/interviews/{completed_id}/evaluation/stream",
            headers=other_hr_headers,
        )
        assert resp.status_code == 403

    def test_nonexistent_interview(self, client, hr_headers):
        resp = client.get(
            "/api/interviews/999999/evaluation/stream", headers=hr_headers
        )
        assert resp.status_code == 404

    def test_reconnect_replays_events(self, client, hr_headers, completed_id):
        """断线重连 → 从头重放已推事件（PRD §7）。"""
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        first = _read_events(
            client, f"/api/interviews/{completed_id}/evaluation/stream", hr_headers
        )
        second = _read_events(
            client, f"/api/interviews/{completed_id}/evaluation/stream", hr_headers
        )

        assert [n for n, _ in first] == [n for n, _ in second]
        assert len(first) == 13

    def test_synthesizes_from_db_when_registry_cleared(
        self, client, hr_headers, completed_id
    ):
        """注册表已清理但状态为 evaluated → 从库中合成完整事件序列。"""
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        stream.reset_registry()  # 模拟进程重启后注册表为空

        events = _read_events(
            client, f"/api/interviews/{completed_id}/evaluation/stream", hr_headers
        )
        names = [n for n, _ in events]
        assert names == ["question"] * 8 + ["dimension"] * 3 + ["report", "done"]

    def test_pushes_error_when_no_progress_available(self, client, hr_headers, db, hr_user, position):
        """未评估且无运行记录 → 推 error 事件。"""
        detail = interview_service.create_interview(
            db, hr_user, InterviewCreate(position_id=position.id, candidate_name="王五")
        )

        events = _read_events(
            client, f"/api/interviews/{detail.id}/evaluation/stream", hr_headers
        )
        assert [n for n, _ in events] == ["error"]


# ---------------------------- 失败处理 ----------------------------


class FailingProvider:
    def generate_questions(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("不应调用出题")

    def evaluate_answer(self, *args, **kwargs):
        from app.core.exceptions import AIProviderError

        raise AIProviderError("模拟评估失败")

    def evaluate_dimensions(self, *args, **kwargs):  # pragma: no cover
        from app.core.exceptions import AIProviderError

        raise AIProviderError("模拟评估失败")

    def summarize_report(self, *args, **kwargs):  # pragma: no cover
        from app.core.exceptions import AIProviderError

        raise AIProviderError("模拟评估失败")


class TestFailureHandling:
    def test_pushes_error_event(self, client, hr_headers, completed_id, monkeypatch):
        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: FailingProvider()
        )

        _trigger(client, hr_headers, completed_id)
        events = _read_events(
            client, f"/api/interviews/{completed_id}/evaluation/stream", hr_headers
        )

        name, payload = events[-1]
        assert name == "error"
        assert payload["code"] == "AI_PROVIDER_ERROR"

    def test_status_rolls_back_to_completed(self, client, hr_headers, db, completed_id, monkeypatch):
        """PRD §7：失败后状态回退 completed，可重新触发。"""
        from app.interview import repository as interview_repo

        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: FailingProvider()
        )

        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        db.rollback()
        assert interview_repo.get_by_id(db, completed_id).status == "completed"

    def test_failure_leaves_no_residue(self, client, hr_headers, db, completed_id, monkeypatch):
        from app.evaluation import repository

        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: FailingProvider()
        )

        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        db.rollback()
        assert repository.list_question_scores(db, completed_id) == []
        assert repository.get_report(db, completed_id) is None

    def test_can_retrigger_after_failure(self, client, hr_headers, completed_id, monkeypatch):
        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: FailingProvider()
        )
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        monkeypatch.undo()
        resp = _trigger(client, hr_headers, completed_id)
        assert resp.status_code == 202

        events = _read_events(
            client, f"/api/interviews/{completed_id}/evaluation/stream", hr_headers
        )
        assert events[-1][0] == "done"


# ---------------------------- 孤儿自愈 ----------------------------


class TestOrphanHealing:
    def test_orphan_evaluation_self_heals(self, client, hr_headers, db, completed_id):
        """状态卡在 evaluating 但注册表为空（进程重启遗留）→ 自愈后可重新触发。"""
        from app.interview import repository as interview_repo

        interview = interview_repo.get_by_id(db, completed_id)
        interview.status = "evaluating"
        db.commit()

        assert stream.get_run(completed_id) is None

        resp = _trigger(client, hr_headers, completed_id)
        assert resp.status_code == 202

        _wait_until_finished(completed_id)

        # Session.get() 会直接命中 identity map 而不回查数据库，
        # 因此必须先失效缓存对象，否则读到的是本会话早先加载的旧状态。
        db.expire_all()
        assert interview_repo.get_by_id(db, completed_id).status == "evaluated"

    def test_heal_orphan_moves_back_to_completed(self, db, completed_id):
        from app.interview import repository as interview_repo

        interview = interview_repo.get_by_id(db, completed_id)
        interview.status = "evaluating"
        db.commit()

        stream.heal_orphan(db, completed_id)

        assert interview_repo.get_by_id(db, completed_id).status == "completed"

    def test_heal_orphan_noop_when_run_exists(self, db, completed_id):
        from app.interview import repository as interview_repo

        interview = interview_repo.get_by_id(db, completed_id)
        interview.status = "evaluating"
        db.commit()
        stream._create_run(completed_id)

        stream.heal_orphan(db, completed_id)

        assert interview_repo.get_by_id(db, completed_id).status == "evaluating"


# ---------------------------- 报告端点 ----------------------------


class TestReportEndpoint:
    def test_report_after_evaluation(self, client, hr_headers, completed_id):
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        resp = client.get(f"/api/interviews/{completed_id}/report", headers=hr_headers)
        assert resp.status_code == 200

        body = resp.json()
        assert body["overall_score"] >= 0
        assert body["conclusion"]
        assert len(body["dimension_scores"]) == 3
        assert len(body["question_scores"]) == 8

    def test_report_includes_position_name_and_evaluated_at(
        self, client, hr_headers, completed_id
    ):
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        body = client.get(
            f"/api/interviews/{completed_id}/report", headers=hr_headers
        ).json()

        assert body["candidate_name"] == "张三"
        assert body["position_name"] == "后端工程师"
        assert body["evaluated_at"]
        assert body["strengths"] and body["weaknesses"]

    def test_report_all_scores_in_range(self, client, hr_headers, completed_id):
        """计划书 §4.3-5：逐题分、维度分、总分均在 0–10 且保留 1 位小数。"""
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        body = client.get(
            f"/api/interviews/{completed_id}/report", headers=hr_headers
        ).json()

        scores = [body["overall_score"]]
        scores += [q["score"] for q in body["question_scores"]]
        scores += [d["score"] for d in body["dimension_scores"]]

        for score in scores:
            assert 0.0 <= score <= 10.0
            assert round(score, 1) == score

    def test_report_uses_snapshot_content(self, client, hr_headers, db, completed_id):
        """评估后改写题库题干，报告仍显示评估时的快照。"""
        _trigger(client, hr_headers, completed_id)
        _wait_until_finished(completed_id)

        before = client.get(
            f"/api/interviews/{completed_id}/report", headers=hr_headers
        ).json()

        from app.interview import repository as interview_repo
        from app.question import repository as question_repo

        position_id = interview_repo.get_by_id(db, completed_id).position_id
        for question in question_repo.list_by_position(db, None, position_id):
            question.content = "题库题干已被彻底改写"
        db.commit()

        after = client.get(
            f"/api/interviews/{completed_id}/report", headers=hr_headers
        ).json()

        assert [q["content"] for q in after["question_scores"]] == [
            q["content"] for q in before["question_scores"]
        ]
        assert all(
            "已被彻底改写" not in q["content"] for q in after["question_scores"]
        )

    def test_report_nonexistent_interview_404(self, client, hr_headers):
        resp = client.get("/api/interviews/999999/report", headers=hr_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_report_before_evaluation_409(self, client, hr_headers, completed_id):
        resp = client.get(f"/api/interviews/{completed_id}/report", headers=hr_headers)
        assert resp.status_code == 409

    def test_report_requires_auth(self, client, completed_id):
        assert client.get(f"/api/interviews/{completed_id}/report").status_code == 401

    def test_report_other_user_forbidden(self, client, other_hr_headers, completed_id):
        resp = client.get(
            f"/api/interviews/{completed_id}/report", headers=other_hr_headers
        )
        assert resp.status_code == 403


def test_disconnect_does_not_stop_task(client, hr_headers, completed_id):
    """断开 SSE 连接不影响后台评估任务（PRD §7）。"""
    _trigger(client, hr_headers, completed_id)

    with client.stream(
        "GET",
        f"/api/interviews/{completed_id}/evaluation/stream",
        headers=hr_headers,
    ) as response:
        assert response.status_code == 200
        next(response.iter_lines())  # 只读一行就断开

    run = _wait_until_finished(completed_id)
    assert run.status == stream.RUN_DONE


# ---------------------------- 重放窗口竞态 ----------------------------


class TestReplayWindow:
    """重放窗口不得吞掉终结事件。

    真实竞态：`stream_events` 先 materialize 一份快照、再单独读 `run.status`；
    而后台线程是**先置 `run.status`、再 publish 终结事件**。若后台恰好在这两步
    之间完成，生成器会直接 `return`，客户端收到的是一段**没有终结事件**的截断流。

    这违反 module-06 §5.5「done 与 error 互斥且**必有其一**」：前端会表现为
    评估永远停在半截 —— 既不报错，也不出现「连接已断开 / 重新连接」提示。

    竞态无法靠 sleep 稳定命中，这里用白盒方式把交错**固定**下来：直接操控运行
    对象，把「取快照 → 后台完成 → 读状态」这个顺序显式写出来。
    """

    INTERVIEW_ID = 424242  # 仅存在于注册表，不涉及数据库

    @pytest.fixture(autouse=True)
    def _fast_ping(self, monkeypatch):
        """把心跳压到毫秒级 —— 流若被截断，测试要快速失败而不是挂住等心跳。"""
        monkeypatch.setattr(stream, "PING_INTERVAL_SECONDS", 0.05)

    @staticmethod
    def _drain(generator, limit=10) -> str:
        """有界读取：流若已截断，不能让测试无限等下去。"""
        chunks = []
        for _ in range(limit):
            try:
                chunks.append(next(generator))
            except StopIteration:
                break
        return "".join(chunks)

    def test_terminal_event_survives_completion_landing_mid_replay(self):
        run = stream._create_run(self.INTERVIEW_ID)
        stream.publish(run, "question", {"seq": 1, "score": 7.0})

        generator = stream.stream_events(self.INTERVIEW_ID)
        first = next(generator)  # 快照在此刻被取走
        assert "event: question" in first

        # 后台恰好在「取快照」与「读状态」之间完成
        run.status = stream.RUN_DONE
        stream.publish(run, "done", {"status": "evaluated"})

        delivered = first + self._drain(generator)
        assert "event: done" in delivered, (
            "运行在重放途中终结时，流仍必须以终结事件收尾，"
            "否则客户端静默停在半截且无任何提示"
        )

    def test_events_published_after_replay_are_delivered_exactly_once(self):
        """订阅与取快照必须原子 —— 否则同一事件会既走重放又走队列，客户端看到重复。"""
        run = stream._create_run(self.INTERVIEW_ID)
        stream.publish(run, "question", {"seq": 1, "score": 7.0})

        generator = stream.stream_events(self.INTERVIEW_ID)
        delivered = next(generator)

        stream.publish(run, "report", {"overall_score": 7.0})
        stream.publish(run, "done", {"status": "evaluated"})
        delivered += self._drain(generator)

        assert delivered.count("event: question") == 1
        assert delivered.count("event: report") == 1
        assert delivered.count("event: done") == 1
