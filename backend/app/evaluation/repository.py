"""evaluation 模块数据访问层。

replace_* 为「先删后插」的整批替换语义 —— 重新评估时不会产生重复行。
"""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.evaluation.models import DimensionScore, QuestionScore, Report


def replace_question_scores(
    db: Session, interview_id: int, items: list[dict]
) -> None:
    db.execute(delete(QuestionScore).where(QuestionScore.interview_id == interview_id))
    db.add_all([QuestionScore(**item) for item in items])
    db.flush()


def replace_dimension_scores(
    db: Session, interview_id: int, items: list[dict]
) -> None:
    db.execute(
        delete(DimensionScore).where(DimensionScore.interview_id == interview_id)
    )
    db.add_all([DimensionScore(**item) for item in items])
    db.flush()


def upsert_report(db: Session, interview_id: int, data: dict) -> Report:
    stmt = select(Report).where(Report.interview_id == interview_id)
    report = db.execute(stmt).scalar_one_or_none()

    if report is None:
        report = Report(interview_id=interview_id, **data)
        db.add(report)
    else:
        for key, value in data.items():
            setattr(report, key, value)
        report.updated_at = datetime.now(UTC).replace(tzinfo=None)

    db.flush()
    return report


def list_question_scores(db: Session, interview_id: int) -> list[QuestionScore]:
    stmt = (
        select(QuestionScore)
        .where(QuestionScore.interview_id == interview_id)
        .order_by(QuestionScore.id)
    )
    return list(db.execute(stmt).scalars().all())


def list_dimension_scores(db: Session, interview_id: int) -> list[DimensionScore]:
    stmt = (
        select(DimensionScore)
        .where(DimensionScore.interview_id == interview_id)
        .order_by(DimensionScore.id)
    )
    return list(db.execute(stmt).scalars().all())


def get_report(db: Session, interview_id: int) -> Report | None:
    stmt = select(Report).where(Report.interview_id == interview_id)
    return db.execute(stmt).scalar_one_or_none()


def delete_all_for_interview(db: Session, interview_id: int) -> None:
    """清空该面试的全部评估结果（供失败清理）。"""
    db.execute(delete(QuestionScore).where(QuestionScore.interview_id == interview_id))
    db.execute(
        delete(DimensionScore).where(DimensionScore.interview_id == interview_id)
    )
    db.execute(delete(Report).where(Report.interview_id == interview_id))
    db.flush()
