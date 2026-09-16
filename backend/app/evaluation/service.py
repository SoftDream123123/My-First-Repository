"""evaluation 模块业务逻辑 —— **同步编排，不含任何 SSE 逻辑**。

这是本模块最关键的切分：评估的业务编排（调 AI、写库、迁移状态）全部在这里，
以同步 + 回调的方式实现，因此可以在完全不涉及异步与网络设施的情况下被单测。
stream.py 只负责把回调变成队列推送。
"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.ai.base import QAPair
from app.ai.factory import get_provider
from app.auth import service as auth_service
from app.auth.models import User
from app.core.exceptions import BusinessError, NotFoundError
from app.evaluation import repository
from app.evaluation.schemas import (
    DimensionScoreItem,
    EvaluationEvent,
    QuestionScoreItem,
    ReportDetail,
)
from app.interview import service as interview_service
from app.interview.models import STATUS_EVALUATED

OnEvent = Callable[[EvaluationEvent], None]


def evaluate_interview(
    db: Session, interview_id: int, on_event: OnEvent
) -> None:
    """三阶段评估编排：逐题评分 → 多维评分 → 汇总报告 → 整批落库。

    结果在**最后一次性落库**（先推后写）—— 数据库要么是上一次的完整结果，
    要么是这一次的完整结果，永不存在混合态；失败也不损失既有数据。

    任何异常向外传播，由调用方（stream.py 的运行器）执行失败处理。
    """
    items = interview_service.get_items_for_evaluation(db, interview_id)
    dimensions = interview_service.get_evaluation_dimensions(db, interview_id)
    provider = get_provider()

    # 兜底进入 evaluating —— 路由通常已迁移，此处保证 service 可独立调用
    interview_service.begin_evaluation(db, interview_id)

    qa_pairs = [
        QAPair(dimension=item.dimension, question=item.question, answer=item.answer)
        for item in items
    ]

    # ---- 阶段 1：逐题评分 ----
    question_results: list[tuple[int, object]] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        result = provider.evaluate_answer(item.dimension, item.question, item.answer)
        question_results.append((item.interview_question_id, result))
        on_event(
            EvaluationEvent(
                "question",
                {
                    "interview_question_id": item.interview_question_id,
                    "seq": item.seq,
                    "index": index,
                    "total": total,
                    "dimension": item.dimension,
                    "score": result.score,
                    "comment": result.comment,
                },
            )
        )

    # ---- 阶段 2：多维评分 ----
    dimension_results = provider.evaluate_dimensions(dimensions, qa_pairs)
    for index, result in enumerate(dimension_results, start=1):
        on_event(
            EvaluationEvent(
                "dimension",
                {
                    "dimension": result.dimension,
                    "index": index,
                    "total": len(dimension_results),
                    "score": result.score,
                    "comment": result.comment,
                },
            )
        )

    # ---- 阶段 3：汇总报告 ----
    report = provider.summarize_report(
        dimensions, dimension_results, [r for _, r in question_results]
    )
    on_event(
        EvaluationEvent(
            "report",
            {
                "overall_score": report.overall_score,
                "conclusion": report.conclusion,
                "strengths": list(report.strengths),
                "weaknesses": list(report.weaknesses),
            },
        )
    )

    # ---- 阶段 4：整批落库（单事务）----
    repository.replace_question_scores(
        db,
        interview_id,
        [
            {
                "interview_id": interview_id,
                "interview_question_id": entry_id,
                "score": result.score,
                "comment": result.comment,
            }
            for entry_id, result in question_results
        ],
    )
    repository.replace_dimension_scores(
        db,
        interview_id,
        [
            {
                "interview_id": interview_id,
                "dimension": result.dimension,
                "score": result.score,
                "comment": result.comment,
            }
            for result in dimension_results
        ],
    )
    repository.upsert_report(
        db,
        interview_id,
        {
            "overall_score": report.overall_score,
            "conclusion": report.conclusion,
            "strengths": list(report.strengths),
            "weaknesses": list(report.weaknesses),
        },
    )
    interview_service.transition_to_evaluated(db, interview_id)


# ------------------------------ 报告读取 ------------------------------


def get_report(db: Session, user: User, interview_id: int) -> ReportDetail:
    """组装完整报告。仅 evaluated 状态可读 —— 期间不可读到半成品。"""
    detail = interview_service.get_interview(db, user, interview_id)

    if detail.status != STATUS_EVALUATED:
        raise BusinessError("评估尚未完成")

    report = repository.get_report(db, interview_id)
    if report is None:
        raise NotFoundError("报告不存在")

    # 逐题明细：用面试的快照与回答补齐，使报告页可独立渲染
    items = interview_service.get_items_for_evaluation(db, interview_id)
    scores = {
        s.interview_question_id: s
        for s in repository.list_question_scores(db, interview_id)
    }

    question_scores: list[QuestionScoreItem] = []
    for item in items:
        score = scores.get(item.interview_question_id)
        if score is None:
            continue
        question_scores.append(
            QuestionScoreItem(
                interview_question_id=item.interview_question_id,
                seq=item.seq,
                content=item.question,
                dimension=item.dimension,
                answer=item.answer,
                score=float(score.score),
                comment=score.comment,
            )
        )
    question_scores.sort(key=lambda q: q.seq)

    return ReportDetail(
        interview_id=interview_id,
        candidate_name=detail.candidate_name,
        position_name=detail.position_name,
        overall_score=float(report.overall_score),
        conclusion=report.conclusion,
        strengths=list(report.strengths),
        weaknesses=list(report.weaknesses),
        evaluated_at=report.updated_at,
        dimension_scores=[
            DimensionScoreItem(
                dimension=d.dimension, score=float(d.score), comment=d.comment
            )
            for d in repository.list_dimension_scores(db, interview_id)
        ],
        question_scores=question_scores,
    )


def list_question_scores(db: Session, interview_id: int):
    return repository.list_question_scores(db, interview_id)


def list_dimension_scores(db: Session, interview_id: int):
    return repository.list_dimension_scores(db, interview_id)


def ensure_visible(db: Session, user: User, interview_id: int) -> None:
    """校验面试存在与可见（供 stream.py 使用）。"""
    interview_service.get_interview(db, user, interview_id)


def scope_owner(user: User) -> int | None:
    return auth_service.scope_owner_id(user)
