"""practice 模块数据访问层。

错题本与统计**全部由 practice_item 派生**，不建表 —— 派生数据与源数据不会漂移。
"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.practice.models import PracticeItem, PracticeSession
from app.question.models import Question


# ------------------------------ 会话 ------------------------------


def create_session(db: Session, **fields: object) -> PracticeSession:
    session = PracticeSession(**fields)
    db.add(session)
    db.flush()
    return session


def get_session_by_id(db: Session, session_id: int) -> PracticeSession | None:
    """不带权限过滤 —— 归属判定在 service（ensure_owner_match）。"""
    return db.get(PracticeSession, session_id)


def update_session(
    db: Session, session: PracticeSession, **fields: object
) -> PracticeSession:
    for key, value in fields.items():
        setattr(session, key, value)
    db.flush()
    return session


def list_by_candidate(
    db: Session, candidate_user_id: int, status: str | None, limit: int
) -> list[PracticeSession]:
    """本人的会话列表，按 started_at 倒序（最近练的在最上面）。

    只查本人：隔离写在 SQL 条件里，不依赖「取回来再过滤」—— 后者一旦忘记
    过滤就会泄露他人的练习。

    **不联 position 表**：practice 的依赖白名单里没有 position（plan §1.3），
    岗位名由 question 模块代取（见 service.list_my_sessions）。
    """
    stmt = select(PracticeSession).where(
        PracticeSession.candidate_user_id == candidate_user_id
    )
    if status is not None:
        stmt = stmt.where(PracticeSession.status == status)

    stmt = stmt.order_by(
        PracticeSession.started_at.desc(), PracticeSession.id.desc()
    ).limit(limit)
    return list(db.execute(stmt).scalars().all())


# ------------------------------ 待答项 ------------------------------


def create_items(db: Session, items: list[dict]) -> list[PracticeItem]:
    entries = [PracticeItem(**item) for item in items]
    db.add_all(entries)
    db.flush()
    return entries


def get_item_by_id(db: Session, item_id: int) -> PracticeItem | None:
    return db.get(PracticeItem, item_id)


def list_items(db: Session, session_id: int) -> list[PracticeItem]:
    """按 seq 升序 —— 与出题顺序一致，保证复看时题目顺序稳定。"""
    stmt = (
        select(PracticeItem)
        .where(PracticeItem.session_id == session_id)
        .order_by(PracticeItem.seq)
    )
    return list(db.execute(stmt).scalars().all())


def update_item(db: Session, item: PracticeItem, **fields: object) -> PracticeItem:
    """写入待答项。

    **必须 flush**：本项目的 SessionLocal 配置了 `autoflush=False`，不 flush 的话
    紧随其后的 recount 聚合查询看不到刚写入的 user_answer / is_correct，
    算出来的计数恒为 0。本模块其他写入方法（create_items / create_session）
    同样显式 flush，保持一致。
    """
    for key, value in fields.items():
        setattr(item, key, value)
    db.flush()
    return item


def recount(db: Session, session_id: int) -> tuple[int, int]:
    """重算 (answered_count, correct_count)。

    **重算而非累加**：同一题可重复提交（错题重练是刷题的正当用法），
    累加会让计数超过 total。重算永远等于事实，累加则依赖「每次都能正确判断
    该不该加」这一脆弱假设。

    answered 用 `user_answer IS NOT NULL`（**含空串**）—— 空串是「提交了但未作答」，
    仍占一个已作答位，与判分时给空串记 0 分一致。
    """
    answered = db.execute(
        select(func.count(PracticeItem.id)).where(
            PracticeItem.session_id == session_id,
            PracticeItem.user_answer.is_not(None),
        )
    ).scalar_one()

    correct = db.execute(
        select(func.count(PracticeItem.id)).where(
            PracticeItem.session_id == session_id,
            PracticeItem.is_correct.is_(True),
        )
    ).scalar_one()

    return int(answered), int(correct)


# ------------------------ 错题本（派生查询）------------------------


def list_wrong_items(
    db: Session,
    candidate_user_id: int,
    position_id: int | None,
    dimension: str | None,
    question_type: str | None,
    limit: int,
) -> list[tuple[PracticeItem, int]]:
    """返回 (最近一次判错的那条, 累计判错次数)。

    **必须显式排除未判分**：`is_correct IS NULL` 是「未判分」，不是「判错」。
    写成 `NOT is_correct` 在 SQL 里对 NULL 求值为 NULL（不成立），看似安全，
    但显式写 `IS FALSE` 才是可读的意图。

    取「最近一条」用 max(id) 而不是 max(answered_at)：answered_at 的列精度是秒，
    同一秒内两次判错会并列，按时间取会返回多行。id 单调递增，天然无并列。
    """
    latest = (
        select(
            PracticeItem.question_id.label("question_id"),
            func.max(PracticeItem.id).label("latest_id"),
            func.count(PracticeItem.id).label("wrong_count"),
        )
        .select_from(PracticeItem)
        .join(PracticeSession, PracticeItem.session_id == PracticeSession.id)
        .where(
            PracticeSession.candidate_user_id == candidate_user_id,
            PracticeItem.is_correct.is_(False),
        )
        .group_by(PracticeItem.question_id)
        .subquery()
    )

    stmt = (
        select(PracticeItem, latest.c.wrong_count)
        .join(latest, PracticeItem.id == latest.c.latest_id)
    )

    if question_type:
        stmt = stmt.where(PracticeItem.question_type == question_type)
    if dimension:
        stmt = stmt.where(PracticeItem.dimension_snapshot == dimension)
    if position_id is not None:
        # 位置筛选读 question 的当前值（practice_item 未快照 position_id）；
        # 展示内容仍来自快照，只有筛选是实时口径。
        stmt = stmt.join(Question, PracticeItem.question_id == Question.id).where(
            Question.position_id == position_id
        )

    stmt = stmt.order_by(
        PracticeItem.answered_at.desc(), PracticeItem.id.desc()
    ).limit(limit)

    return [(row[0], int(row[1])) for row in db.execute(stmt).all()]


# ------------------------ 统计（派生查询）------------------------


def _stats_query(candidate_user_id: int, group_column=None):
    """统计口径的唯一落点 —— 汇总与分组共用，避免两处各算一套。

    answered = count(user_answer)    —— SQL 的 count 忽略 NULL
    scored   = count(is_correct)     —— 同上，故 NULL（未判分）自动被排除
    correct  = sum(is_correct IS TRUE)
    """
    answered = func.count(PracticeItem.user_answer).label("answered")
    scored = func.count(PracticeItem.is_correct).label("scored")
    correct = func.sum(
        case((PracticeItem.is_correct.is_(True), 1), else_=0)
    ).label("correct")

    columns = [answered, scored, correct] if group_column is None else [
        group_column.label("key"),
        answered,
        scored,
        correct,
    ]

    stmt = (
        select(*columns)
        .select_from(PracticeItem)
        .join(PracticeSession, PracticeItem.session_id == PracticeSession.id)
        .where(PracticeSession.candidate_user_id == candidate_user_id)
    )
    if group_column is not None:
        stmt = stmt.group_by(group_column).order_by(group_column)
    return stmt


def aggregate_stats(db: Session, candidate_user_id: int) -> dict:
    """全量统计 + 按维度 / 按题型分组。"""
    overall = db.execute(_stats_query(candidate_user_id)).one()

    by_dimension = [
        {"key": row.key, "answered": row.answered, "scored": row.scored, "correct": int(row.correct or 0)}
        for row in db.execute(
            _stats_query(candidate_user_id, PracticeItem.dimension_snapshot)
        ).all()
    ]
    by_type = [
        {"key": row.key, "answered": row.answered, "scored": row.scored, "correct": int(row.correct or 0)}
        for row in db.execute(
            _stats_query(candidate_user_id, PracticeItem.question_type)
        ).all()
    ]

    session_count = db.execute(
        select(func.count(PracticeSession.id)).where(
            PracticeSession.candidate_user_id == candidate_user_id
        )
    ).scalar_one()

    return {
        "total_answered": int(overall.answered or 0),
        "scored_count": int(overall.scored or 0),
        "correct_count": int(overall.correct or 0),
        "session_count": int(session_count or 0),
        "by_dimension": by_dimension,
        "by_type": by_type,
    }


def session_dimension_stats(db: Session, session_id: int) -> list[dict]:
    """单个会话内按维度分组 —— 练习小结用。与 aggregate_stats 同口径。"""
    answered = func.count(PracticeItem.user_answer).label("answered")
    correct = func.sum(
        case((PracticeItem.is_correct.is_(True), 1), else_=0)
    ).label("correct")

    stmt = (
        select(PracticeItem.dimension_snapshot.label("key"), answered, correct)
        .where(PracticeItem.session_id == session_id)
        .group_by(PracticeItem.dimension_snapshot)
        .order_by(PracticeItem.dimension_snapshot)
    )
    return [
        {"key": row.key, "answered": row.answered, "correct": int(row.correct or 0)}
        for row in db.execute(stmt).all()
    ]


def count_unscored(db: Session, session_id: int) -> int:
    """已提交但未判分的题数（用户提交过作答、却没能判出来）。"""
    return int(
        db.execute(
            select(func.count(PracticeItem.id)).where(
                PracticeItem.session_id == session_id,
                PracticeItem.user_answer.is_not(None),
                PracticeItem.is_correct.is_(None),
            )
        ).scalar_one()
    )
