"""evaluation SSE 层测试：事件序列、重连重放、幂等、失败回退、孤儿自愈。"""

import json
import time

import pytest

from app.evaluation import stream
from app.interview import service as interview_service
from app.interview.schemas import InterviewCreate

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


def _read_events(client, url, headers, stop_on=("done", "error")):
    """读取 SSE 直到终结事件。"""
    events = []
    with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        name = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                events.append((name, payload))
                if name in stop_on:
                    break
    return events


def _wait_until_finished(interview_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = stream.get_run(interview_id)
        if run is not None and run.status != stream.RUN_RUNNING:
            return run
        time.sleep(0.05)
    raise AssertionError("评估未在超时内结束")


def _trigger(client, headers, interview_id):
    return client.post(f"/api/interviews/{interview_id}/evaluate", headers=headers)


class SlowProvider:
    """每个方法都慢一点 —— 让「运行中」状态可被稳定观察到。"""

    def __init__(self, delegate, delay=0.15):
        self._delegate = delegate
        self._delay = delay

    def generate_questions(self, *args, **kwargs):
        return self._delegate.generate_questions(*args, **kwargs)

    def evaluate_answer(self, *args, **kwargs):
        time.sleep(self._delay)
        return self._delegate.evaluate_answer(*args, **kwargs)

    def evaluate_dimensions(self, *args, **kwargs):
        time.sleep(self._delay)
        return self._delegate.evaluate_dimensions(*args, **kwargs)

    def summarize_report(self, *args, **kwargs):
        time.sleep(self._delay)
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

        monkeypatch.setattr(
            "app.evaluation.service.get_provider",
            lambda: SlowProvider(get_provider()),
        )

        first = _trigger(client, hr_headers, completed_id)
        assert first.status_code == 202

        run_before = stream.get_run(completed_id)
        second = _trigger(client, hr_headers, completed_id)

        assert second.status_code == 202
        assert second.json()["stream_url"] == first.json()["stream_url"]
        assert stream.get_run(completed_id) is run_before  # 未创建第二个运行

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
