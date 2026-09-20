"""resume 模块数据访问层。

`get_by_id` 刻意不带权限过滤 —— repository 保持纯粹，「谁有权看」是业务判断，
归 service（与 position / practice 同构）。
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.resume.models import Resume


def create(
    db: Session,
    *,
    title: str,
    content: str,
    candidate_name: str | None,
    candidate_contact: str | None,
    created_by: int,
) -> Resume:
    resume = Resume(
        title=title,
        content=content,
        candidate_name=candidate_name,
        candidate_contact=candidate_contact,
        created_by=created_by,
    )
    db.add(resume)
    return resume


def get_by_id(db: Session, resume_id: int) -> Resume | None:
    return db.get(Resume, resume_id)


def list_by_creator(db: Session, creator_id: int, limit: int) -> list[Resume]:
    """只查本人，按 `updated_at` 倒序（最近改的在最上面）。

    隔离条件写在 SQL 里而非「取回来再过滤」—— 后者一旦忘记过滤就会泄露他人简历。
    同秒并列时用 id 兜底，保证顺序稳定。
    """
    stmt = (
        select(Resume)
        .where(Resume.created_by == creator_id)
        .order_by(Resume.updated_at.desc(), Resume.id.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def update(db: Session, resume: Resume, **fields: object) -> Resume:
    for key, value in fields.items():
        setattr(resume, key, value)
    return resume


def delete(db: Session, resume: Resume) -> None:
    """删除简历。被 interview / practice_session 引用时由外键 RESTRICT 拒绝。

    不做「先数引用再决定」的预检：预检会引入「数完到删除之间被关联」的竞态，
    而外键在任何时刻都是权威的。一次捕获 IntegrityError 就够 —— 与
    position/repository.py::delete 完全同构。捕获后必须 rollback，
    否则污染的事务会让后续操作连带失败。
    """
    db.delete(resume)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("该简历已被面试或练习关联，无法删除") from exc
