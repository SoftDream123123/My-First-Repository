"""报告 DOCX 装配（module-21）。

**纯函数**：输入 `ReportDetail`、输出 `bytes`，不碰数据库、不碰 FastAPI、
不写磁盘、不记日志。因此它可以用最便宜的方式单测 —— 构造一个 `ReportDetail`
即可，不需要任何夹具或请求上下文。

放在本模块而非 service.py：它与 `stream.py` 同形态 —— 一个专注的技术细节，
不属 router / service / repository 任何一层。塞进 service.py 会让「评估编排」
与「文档排版」两个无关的关注点混在一处。

**不含雷达图**（PRD §4.12 明确）：需要图形的场景走前端浏览器打印 PDF。
"""

from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from app.evaluation.schemas import ReportDetail

TITLE = "面试评估报告"

# 中文字体必须设 `w:eastAsia`，只设 `w:ascii` 不够 —— 中文字符走的是 eastAsia
# 分支。python-docx 的 `style.font.name = ...` **只改 w:ascii**，因此必须拿到
# rFonts 元素显式设置。漏掉时在本机 Word 里看起来完全正常，只在 LibreOffice /
# 部分 WPS 下退化甚至出方框 —— 属于「只有特定查看器才暴露」的故障。
_EAST_ASIA_FONT = "宋体"
_ASCII_FONT = "Calibri"
_FONT_STYLES = ("Normal", "Heading 1", "Heading 2")

_PLACEHOLDER_EMPTY = "（无）"
_PLACEHOLDER_UNANSWERED = "（未作答）"

_INFO_ROWS = ("岗位", "候选人", "评估时间")
_QUESTION_HEADERS = ("序号", "考察维度", "题目", "回答", "得分", "评语")
_DIMENSION_HEADERS = ("维度", "得分", "评语")

_TIME_FORMAT = "%Y-%m-%d %H:%M"


def build_report_docx(report: ReportDetail) -> bytes:
    """把一份报告渲染成 DOCX 字节流（全程在内存，不落盘）。"""
    document = Document()
    _set_default_font(document)

    # 1) 标题
    document.add_heading(TITLE, level=1)

    # 2) 基本信息
    _add_info_table(document, report)

    # 3) 总分 —— 统一 1 位小数，与报告页 / 雷达图 / summarize_report 的口径一致，
    #    避免同一个分数在两处显示成 7 与 7.0
    document.add_heading("总分", level=2)
    document.add_paragraph(f"{report.overall_score:.1f} / 10")

    # 4) 综合结论
    document.add_heading("综合结论", level=2)
    document.add_paragraph(report.conclusion)

    # 5) 优点 / 6) 待改进
    document.add_heading("优点", level=2)
    _add_bullets(document, report.strengths)

    document.add_heading("待改进", level=2)
    _add_bullets(document, report.weaknesses)

    # 7) 逐题评分 / 8) 多维评分
    document.add_heading("逐题评分", level=2)
    _add_question_table(document, report)

    document.add_heading("多维评分", level=2)
    _add_dimension_table(document, report)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _set_default_font(document: Document) -> None:
    """给默认样式与标题样式设置西文 + **中文（eastAsia）** 字体。

    在这里做一次，而不是在每个 add_paragraph 处重复设置。
    """
    for style_name in _FONT_STYLES:
        try:
            style = document.styles[style_name]
        except KeyError:  # pragma: no cover - 内置样式必然存在
            continue

        style.font.name = _ASCII_FONT
        rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        rfonts.set(qn("w:eastAsia"), _EAST_ASIA_FONT)


def _add_info_table(document: Document, report: ReportDetail) -> None:
    document.add_heading("基本信息", level=2)

    table = document.add_table(rows=len(_INFO_ROWS), cols=2)
    table.style = "Table Grid"

    values = (
        report.position_name,
        report.candidate_name,
        report.evaluated_at.strftime(_TIME_FORMAT),
    )
    for row, (label, value) in zip(table.rows, zip(_INFO_ROWS, values), strict=True):
        row.cells[0].text = label
        row.cells[1].text = value


def _add_bullets(document: Document, items: list[str]) -> None:
    """逐条输出；空列表写「（无）」—— 比整块消失更容易察觉异常。"""
    if not items:
        document.add_paragraph(_PLACEHOLDER_EMPTY)
        return

    for item in items:
        document.add_paragraph(item, style="List Bullet")


def _add_question_table(document: Document, report: ReportDetail) -> None:
    """逐题评分表（6 列）。

    **回答原文不截断**：它是分数的证据，截断会让「HR 复核当初为什么给这个分」
    失去依据，而 DOCX 正是留档交付物。Word 会自动换行。
    行序沿用入参（`get_report` 已按 seq 排好），本模块**不重排**。
    """
    table = document.add_table(rows=1, cols=len(_QUESTION_HEADERS))
    table.style = "Table Grid"

    for cell, header in zip(table.rows[0].cells, _QUESTION_HEADERS, strict=True):
        cell.text = header

    for item in report.question_scores:
        cells = table.add_row().cells
        values = (
            str(item.seq),
            item.dimension,
            item.content,
            item.answer if item.answer else _PLACEHOLDER_UNANSWERED,
            f"{item.score:.1f}",
            item.comment,
        )
        for cell, value in zip(cells, values, strict=True):
            cell.text = value


def _add_dimension_table(document: Document, report: ReportDetail) -> None:
    """多维评分表（3 列）。行序沿用入参 —— 重排会引入第二套维度顺序口径。"""
    table = document.add_table(rows=1, cols=len(_DIMENSION_HEADERS))
    table.style = "Table Grid"

    for cell, header in zip(table.rows[0].cells, _DIMENSION_HEADERS, strict=True):
        cell.text = header

    for dimension in report.dimension_scores:
        cells = table.add_row().cells
        values = (dimension.dimension, f"{dimension.score:.1f}", dimension.comment)
        for cell, value in zip(cells, values, strict=True):
            cell.text = value
