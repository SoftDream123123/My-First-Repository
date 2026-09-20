"""evaluation 模块业务逻辑 —— **同步编排，不含任何 SSE 逻辑**。

这是本模块最关键的切分：评估的业务编排（调 AI、写库、迁移状态）全部在这里，
以同步 + 回调的方式实现，因此可以在完全不涉及异步与网络设施的情况下被单测。
stream.py 只负责把回调变成队列推送。
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.base import FEEDBACK_LEVEL_FULL, QAPair, DimensionScoreResult
from app.ai.factory import get_provider
from app.auth import service as auth_service
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.evaluation import export, repository
from app.evaluation.schemas import (
    CandidateFeedbackOut,
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
    # 缓存失效：重新评估整体替换了报告，旧的候选人反馈必须一并作废，
    # 否则候选人会看到**上一轮**的反馈。
    #
    # 放在**同一事务**内，与报告替换同生共死 —— 开第二个事务会留下
    # 「报告已换、反馈还是旧的」的窗口。删除是本地 DB 操作，不调 AI，
    # 因此不会违反 PRD §7「AI 失败不阻塞其他功能」。
    #
    # 评估**失败**时不会走到这里，缓存自然保留 —— 报告未被替换，反馈仍有效。
    repository.delete_candidate_feedback(db, interview_id)

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


# -------------------------- 候选人脱敏反馈 --------------------------


def get_candidate_feedback(
    db: Session, user: User, interview_id: int
) -> CandidateFeedbackOut:
    """候选人查看脱敏反馈（懒生成 + 缓存 + 档位裁剪）。

    为什么是**懒生成**而不是在评估落库时生成：把反馈塞进评估事务有三个问题 ——
      ① 评估事务多一次 AI 调用，**评估的成功率被第二个调用拖累**；
      ② PRD §7 要求「AI 失败不阻塞其他功能」，塞进事务直接违反；
      ③ 无人查看反馈时白花一次调用。
    懒生成的代价（首次读取慢一次 AI 调用）只在评估完成后首次查看时发生。

    **档位不影响缓存内容**：缓存的是中性文案（不含总分），因此 summary 与 full
    共用同一份缓存 —— 切换配置立即生效、无需失效。

    可见性经 `interview.get_interview_for_candidate` —— 候选人能否访问某面试的
    **唯一判据**。本模块不重复实现它，否则「邀请撤销后是否仍可看反馈」会出现
    两套答案。
    """
    interview = interview_service.get_interview_for_candidate(db, user, interview_id)

    if interview.status != STATUS_EVALUATED:
        raise BusinessError("评估尚未完成")

    report = repository.get_report(db, interview_id)
    if report is None:
        # 防御：状态已是 evaluated 但报告缺失（理论不可达）
        raise BusinessError("评估尚未完成")

    level = get_settings().candidate_feedback_level
    feedback = repository.get_candidate_feedback(db, interview_id)
    if feedback is None:
        feedback = _generate_and_cache_feedback(db, interview_id, report, level)

    return CandidateFeedbackOut(
        interview_id=interview_id,
        level=level,
        conclusion=feedback.conclusion,
        strengths=list(feedback.strengths),
        weaknesses=list(feedback.weaknesses),
        # 总分**从 report 读**，不存进反馈表：存储层与可见性层解耦后，
        # 改档位配置不需要重新生成反馈
        overall_score=(
            float(report.overall_score) if level == FEEDBACK_LEVEL_FULL else None
        ),
        generated_at=feedback.generated_at,
    )


def _generate_and_cache_feedback(
    db: Session, interview_id: int, report, level: str
):
    """生成并落库。

    AI 失败时 `AIProviderError` 向外传播（502）且**不落库** —— 下次读取可重试。
    这与刷题判分返回 200 不同：反馈是**读接口**，读不到就是读不到；而刷题那边
    作答已成功保存，报错会与事实不符。
    """
    # 维度得分是**重写结论**的依据。判强弱的阈值（PASS_THRESHOLD）留在 ai 层，
    # 这里不另算一套「哪些算强项」，否则两处迟早不一致。
    dimension_scores = [
        DimensionScoreResult(
            dimension=row.dimension,
            score=float(row.score),
            comment=row.comment,
        )
        for row in repository.list_dimension_scores(db, interview_id)
    ]

    # 报告那句 conclusion **不传**：它含招聘方的去留判断，不该到候选人那边
    # （PRD §4.9）。不传是结构上的保证，而不是靠一句「不要复述」的提示。
    result = get_provider().generate_candidate_feedback(
        level,
        float(report.overall_score),
        list(report.strengths),
        list(report.weaknesses),
        dimension_scores,
    )

    payload = {
        "conclusion": result.conclusion,
        "strengths": list(result.strengths),
        "weaknesses": list(result.weaknesses),
    }

    try:
        feedback = repository.upsert_candidate_feedback(db, interview_id, payload)
        db.commit()
    except IntegrityError:
        # 并发首次读取撞上 interview_id 唯一索引 —— 对候选人而言「拿到反馈」这一
        # 目标已经达成，不报错：读取前者写入的那一行。
        db.rollback()
        existing = repository.get_candidate_feedback(db, interview_id)
        if existing is None:  # pragma: no cover - 理论不可达
            raise
        return existing

    db.refresh(feedback)  # generated_at 是 server_default，刷新后才可读
    return feedback


def list_dimension_scores(db: Session, interview_id: int):
    return repository.list_dimension_scores(db, interview_id)


def ensure_visible(db: Session, user: User, interview_id: int) -> None:
    """校验面试存在与可见（供 stream.py 使用）。"""
    interview_service.get_interview(db, user, interview_id)


def scope_owner(user: User) -> int | None:
    return auth_service.scope_owner_id(user)


# ------------------------------ 报告导出 ------------------------------

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# 当前只支持 docx。保留 format 参数（而非把格式写进路径）是为了将来加格式
# 不必改路径 —— 改路径会同时破坏前端与已发出的文档链接。
_EXPORT_FORMATS = ("docx",)

_FALLBACK_FILENAME = "report.docx"
_FILENAME_MIDDLE_MAX = 60
# `"` 会截断 Content-Disposition 的值、CR/LF 能注入额外头部、`/` 与 `\` 是路径分隔符。
# ASCII 控制字符由 ord(ch) < 0x20 一并剔除。
_UNSAFE_FILENAME_CHARS = frozenset('"\\/\r\n\t')


@dataclass
class ReportExport:
    """service → router 之间传递的导出结果。

    **不用 tuple**：三个字段里两个是字符串，元组会让 `(content, filename)` 与
    `(filename, content)` 这类笔误无声通过。
    定义在 service 而非 schemas：它含 `bytes`，无法作为 Pydantic 响应模型，
    是内部传递结构而非 HTTP 契约。
    """

    content: bytes
    filename: str
    media_type: str


def export_report(
    db: Session, user: User, interview_id: int, fmt: str
) -> ReportExport:
    """导出 HR 报告为 DOCX（PRD §4.12）。

    内容与报告接口**同源**（都走 `get_report`），因此自动继承它全部的可见性
    与状态校验：面试不存在 404 / 非本人 403 / 非 evaluated 409 / 无报告行 404。
    不额外落库任何导出记录。
    """
    if fmt not in _EXPORT_FORMATS:
        # 先校验格式再读库：格式错了就不该白读一次；且「参数错先于资源错」
        # 与 main.py 的全局校验收口方向一致。
        # **不静默当 docx** —— 静默回退会让调用方以为拿到了别的格式。
        raise ValidationError(
            "不支持的导出格式",
            detail={
                "fields": [
                    {
                        "field": "format",
                        "message": f"当前仅支持 {'/'.join(_EXPORT_FORMATS)}",
                    }
                ]
            },
        )

    report = get_report(db, user, interview_id)

    # 装配失败不强转成业务错误：export 是纯函数、输入已校验，失败只可能是
    # 编程错误或依赖异常 → 让它成为 500 + 完整堆栈（main.py 已覆盖）
    return ReportExport(
        content=export.build_report_docx(report),
        filename=_build_filename(report),
        media_type=_DOCX_MEDIA_TYPE,
    )


def _build_filename(report: ReportDetail) -> str:
    return _sanitize_filename(
        f"面试评估报告-{report.position_name}-{report.candidate_name}.docx"
    )


def _sanitize_filename(name: str) -> str:
    """剔除危险字符并限长，返回 UTF-8 文件名（百分号编码在 router 层做）。

    这是**业务规则**（文件名该长什么样）；百分号编码是 HTTP 协议细节。

    `candidate_name` / `position_name` 是 HR 自由填写的用户输入
    （`InterviewCreate` 对它们没有任何字符限制），而这是本项目**第一处**把用户
    输入放进 HTTP 头部的地方 —— 含 `"` 或 CRLF 会破坏甚至注入 `Content-Disposition`。
    """
    cleaned = "".join(
        char
        for char in name
        if char not in _UNSAFE_FILENAME_CHARS and ord(char) >= 0x20
    )

    stem, dot, suffix = cleaned.rpartition(".")
    if not dot:
        stem, suffix = cleaned, ""

    stem = stem.strip()[:_FILENAME_MIDDLE_MAX]
    if not stem:
        # 中段全被剔掉（如姓名是纯控制字符）→ 退化为固定回退名
        return _FALLBACK_FILENAME

    return f"{stem}.{suffix}" if suffix else stem
