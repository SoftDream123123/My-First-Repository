"""evaluation 流式层：运行注册表、事件队列、SSE 生成、重连重放、孤儿自愈。

本层是薄薄的传输适配 —— 真正的评估编排在 service.py，以同步回调方式实现。
"""

import json
import logging
import queue
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.exceptions import AppError
from app.evaluation import repository, service as evaluation_service
from app.evaluation.schemas import EvaluationEvent
from app.interview import repository as interview_repository
from app.interview import service as interview_service
from app.interview.models import (
    STATUS_COMPLETED,
    STATUS_EVALUATED,
    STATUS_EVALUATING,
)

logger = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = 15
TERMINAL_EVENTS = ("done", "error")

RUN_RUNNING = "running"
RUN_DONE = "done"
RUN_FAILED = "failed"


# ---------------------------- 运行注册表 ----------------------------


@dataclass
class EvaluationRun:
    interview_id: int
    status: str = RUN_RUNNING
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    subscribers: list[queue.Queue] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)


_runs: dict[int, EvaluationRun] = {}
_runs_lock = threading.Lock()


def get_run(interview_id: int) -> EvaluationRun | None:
    with _runs_lock:
        return _runs.get(interview_id)


def remove_run(interview_id: int) -> None:
    with _runs_lock:
        _runs.pop(interview_id, None)


def _create_run(interview_id: int) -> EvaluationRun:
    run = EvaluationRun(interview_id=interview_id)
    with _runs_lock:
        _runs[interview_id] = run
    return run


def publish(run: EvaluationRun, name: str, payload: dict[str, Any]) -> None:
    """把事件追加到历史并投递给所有订阅者。"""
    with run.lock:
        run.events.append((name, payload))
        subscribers = list(run.subscribers)

    for subscriber in subscribers:
        subscriber.put((name, payload))


def _signal_end(run: EvaluationRun) -> None:
    with run.lock:
        subscribers = list(run.subscribers)
    for subscriber in subscribers:
        subscriber.put(None)


def publish_terminal(
    run: EvaluationRun, name: str, payload: dict[str, Any], status: str
) -> None:
    """终结事件与运行状态必须在**同一把锁内**写入。

    否则 `stream_events` 在锁内原子读取「事件列表 + 状态」时，可能读到
    「状态已终结、终结事件尚未入列」的组合，于是推出一段**没有终结事件**的
    截断流 —— 客户端既不报错也收不到 done/error，界面永远停在半截。
    """
    with run.lock:
        run.events.append((name, payload))
        run.status = status
        subscribers = list(run.subscribers)

    for subscriber in subscribers:
        subscriber.put((name, payload))

    _signal_end(run)


# ---------------------------- 后台运行器 ----------------------------


def _evaluate_in_thread(interview_id: int, run: EvaluationRun) -> None:
    """后台线程：拥有独立的 DB 会话（SQLAlchemy Session 非线程安全）。"""
    db: Session = SessionLocal()
    try:
        evaluation_service.evaluate_interview(
            db, interview_id, lambda event: publish(run, event.name, event.payload)
        )
        publish_terminal(run, "done", {"status": STATUS_EVALUATED}, RUN_DONE)
    except Exception as exc:  # noqa: BLE001 - 统一转为 error 事件
        logger.exception("面试 %s 评估失败", interview_id)
        db.rollback()
        _rollback_status(interview_id)
        publish_terminal(run, "error", _error_payload(exc), RUN_FAILED)
    finally:
        db.close()
        _signal_end(run)


def _rollback_status(interview_id: int) -> None:
    """失败处理（PRD §7）：状态回退 completed，使用全新会话以免受污染事务影响。"""
    db: Session = SessionLocal()
    try:
        interview_service.transition_back_to_completed(db, interview_id)
    except Exception:  # noqa: BLE001 - 回退失败只记日志，不再向上抛
        logger.exception("面试 %s 状态回退失败", interview_id)
        db.rollback()
    finally:
        db.close()


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {"code": exc.code, "message": exc.message}
    return {"code": "INTERNAL_ERROR", "message": "评估过程中发生错误，请重试"}


def start_run(interview_id: int) -> EvaluationRun:
    """创建运行并启动后台评估线程。"""
    remove_run(interview_id)  # 丢弃上一轮的运行记录（重新评估场景）
    run = _create_run(interview_id)

    thread = threading.Thread(
        target=_evaluate_in_thread,
        args=(interview_id, run),
        name=f"evaluation-{interview_id}",
        daemon=True,
    )
    thread.start()
    return run


# ---------------------------- 孤儿自愈 ----------------------------


def heal_orphan(db: Session, interview_id: int) -> None:
    """状态为 evaluating 但注册表中无运行记录 → 判定为孤儿（进程重启遗留）。

    注册表是「评估是否真的在跑」的唯一事实来源。
    """
    interview = interview_repository.get_by_id(db, interview_id)
    if interview is None:
        return
    if interview.status == STATUS_EVALUATING and get_run(interview_id) is None:
        interview_service.transition_back_to_completed(db, interview_id)


# ---------------------------- SSE 生成 ----------------------------


def format_event(name: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {name}\ndata: {data}\n\n"


def _synthesize_from_db(db: Session, interview_id: int) -> Iterator[tuple[str, dict]]:
    """注册表已清理但从库中有完整结果 → 合成一轮事件序列。

    对应 PRD §7「重连后可继续拉取进度**或查询最终结果**」。
    """
    items = interview_service.get_items_for_evaluation(db, interview_id)
    by_entry = {item.interview_question_id: item for item in items}

    scores = repository.list_question_scores(db, interview_id)
    total = len(scores)
    for index, score in enumerate(scores, start=1):
        item = by_entry.get(score.interview_question_id)
        if item is None:
            continue
        yield (
            "question",
            {
                "interview_question_id": score.interview_question_id,
                "seq": item.seq,
                "index": index,
                "total": total,
                "dimension": item.dimension,
                "score": float(score.score),
                "comment": score.comment,
            },
        )

    dimensions = repository.list_dimension_scores(db, interview_id)
    for index, dim in enumerate(dimensions, start=1):
        yield (
            "dimension",
            {
                "dimension": dim.dimension,
                "index": index,
                "total": len(dimensions),
                "score": float(dim.score),
                "comment": dim.comment,
            },
        )

    report = repository.get_report(db, interview_id)
    if report is not None:
        yield (
            "report",
            {
                "overall_score": float(report.overall_score),
                "conclusion": report.conclusion,
                "strengths": list(report.strengths),
                "weaknesses": list(report.weaknesses),
            },
        )

    yield ("done", {"status": STATUS_EVALUATED})


def stream_events(interview_id: int) -> Iterator[str]:
    """SSE 事件流生成器。

    生命周期：重放已推事件 → 订阅新事件 → 终结事件后关闭。
    客户端断开只是移除订阅者，**后台任务继续运行**（PRD §7）。
    """
    run = get_run(interview_id)

    if run is None:
        db: Session = SessionLocal()
        try:
            interview = interview_repository.get_by_id(db, interview_id)
            status = interview.status if interview else None

            if status == STATUS_EVALUATED:
                for name, payload in _synthesize_from_db(db, interview_id):
                    yield format_event(name, payload)
                return
        finally:
            db.close()

        yield format_event(
            "error",
            {"code": "BUSINESS_ERROR", "message": "当前无可用的评估进度"},
        )
        return

    # 1) 「订阅 + 取快照 + 读状态」必须在**同一把锁**内完成。
    #    若先取快照再订阅，两步之间 publish 的事件既不在快照里、也投递不到
    #    订阅者 —— 客户端会看到跳号，甚至永远等不到终结事件。
    subscriber: queue.Queue = queue.Queue()
    with run.lock:
        replayed = list(run.events)
        finished = run.status in (RUN_DONE, RUN_FAILED)
        if not finished:
            run.subscribers.append(subscriber)

    for name, payload in replayed:
        yield format_event(name, payload)

    if finished:
        # 与 publish_terminal 的原子写入配合：状态已终结 ⇒ 终结事件必在 replayed 中
        return

    # 2) 转发后续事件（此时已在订阅者名单内，不会漏）
    try:
        while True:
            try:
                item = subscriber.get(timeout=PING_INTERVAL_SECONDS)
            except queue.Empty:
                yield ": ping\n\n"  # 心跳，防止代理因空闲断开
                continue

            if item is None:
                return

            name, payload = item
            yield format_event(name, payload)
            if name in TERMINAL_EVENTS:
                return
    finally:
        with run.lock:
            if subscriber in run.subscribers:
                run.subscribers.remove(subscriber)


def snapshot_for_status(interview_id: int) -> EvaluationRun | None:
    return get_run(interview_id)


def reset_registry() -> None:
    """清空运行注册表 —— 仅供测试使用。"""
    with _runs_lock:
        _runs.clear()
