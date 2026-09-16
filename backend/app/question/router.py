"""question 模块 HTTP 端点。"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_current_user, get_db
from app.question import service
from app.question.schemas import (
    QuestionCreate,
    QuestionFilters,
    QuestionOut,
    QuestionUpdate,
)

router = APIRouter(prefix="/questions", tags=["题库"])


@router.post(
    "",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建题目",
)
def create_question(
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuestionOut:
    return QuestionOut.model_validate(service.create_question(db, user, payload))


@router.get("", response_model=list[QuestionOut], summary="题目列表（多维筛选）")
def list_questions(
    position_id: int | None = Query(default=None, description="按岗位过滤"),
    category: str | None = Query(default=None, description="精确匹配分类"),
    dimension: str | None = Query(default=None, description="精确匹配维度"),
    source: str | None = Query(default=None, description="bank | ai"),
    keyword: str | None = Query(default=None, description="按题干模糊匹配"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[QuestionOut]:
    filters = QuestionFilters(
        position_id=position_id,
        category=category,
        dimension=dimension,
        source=source,
        keyword=keyword,
    )
    return [
        QuestionOut.model_validate(q)
        for q in service.list_questions(db, user, filters)
    ]


@router.get("/{question_id}", response_model=QuestionOut, summary="题目详情")
def get_question(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuestionOut:
    return QuestionOut.model_validate(service.get_question(db, user, question_id))


@router.put("/{question_id}", response_model=QuestionOut, summary="更新题目")
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuestionOut:
    return QuestionOut.model_validate(
        service.update_question(db, user, question_id, payload)
    )


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除题目",
)
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    service.delete_question(db, user, question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
