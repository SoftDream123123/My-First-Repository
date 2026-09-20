"""报告 DOCX 装配测试（module-21 §7.1）。

手法是 **round-trip**：把 `build_report_docx` 的输出用 python-docx 重新打开，
再断言段落与表格内容。比按字节断言可读、可维护，而且真正验证了
「这个文件能被 Word 打开」——纯字节断言做不到这一点。

本文件不需要任何夹具：`export.py` 是纯函数，构造一个 `ReportDetail` 即可。
"""

from datetime import datetime
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from app.evaluation.export import TITLE, build_report_docx
from app.evaluation.schemas import DimensionScoreItem, QuestionScoreItem, ReportDetail

SECTION_TITLES = (
    TITLE,
    "基本信息",
    "总分",
    "综合结论",
    "优点",
    "待改进",
    "逐题评分",
    "多维评分",
)

QUESTION_HEADERS = ("序号", "考察维度", "题目", "回答", "得分", "评语")
DIMENSION_HEADERS = ("维度", "得分", "评语")


def _report(**overrides) -> ReportDetail:
    payload = {
        "interview_id": 1,
        "candidate_name": "张三",
        "position_name": "后端工程师",
        "overall_score": 7.5,
        "conclusion": "整体表现良好，建议结合岗位要求综合评估。",
        "strengths": ["沟通能力（8.0）：表现较好"],
        "weaknesses": ["逻辑思维（5.0）：有待提升"],
        "evaluated_at": datetime(2026, 9, 21, 10, 30),
        "dimension_scores": [
            DimensionScoreItem(dimension="沟通能力", score=8.0, comment="表达清晰"),
            DimensionScoreItem(dimension="逻辑思维", score=5.0, comment="需加强"),
        ],
        "question_scores": [
            QuestionScoreItem(
                interview_question_id=11,
                seq=1,
                content="第一题的题干",
                dimension="沟通能力",
                answer="第一题的回答",
                score=8.0,
                comment="回答详实",
            ),
            QuestionScoreItem(
                interview_question_id=12,
                seq=2,
                content="第二题的题干",
                dimension="逻辑思维",
                answer=None,
                score=5.0,
                comment="回答简略",
            ),
        ],
    }
    payload.update(overrides)
    return ReportDetail(**payload)


def _open(content: bytes) -> Document:
    return Document(BytesIO(content))


def _all_text(content: bytes) -> str:
    document = _open(content)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def test_returns_bytes_starting_with_zip_magic():
    content = build_report_docx(_report())

    assert isinstance(content, bytes)
    assert content[:2] == b"PK"  # DOCX 是 zip 容器


def test_output_opens_as_document():
    document = _open(build_report_docx(_report()))

    assert document.paragraphs


def test_contains_all_eight_sections():
    text = _all_text(build_report_docx(_report()))

    for title in SECTION_TITLES:
        assert title in text, f"缺少区块：{title}"


def test_info_table_rows():
    document = _open(build_report_docx(_report()))
    info = document.tables[0]

    assert len(info.rows) == 3
    assert info.rows[0].cells[0].text == "岗位"
    assert info.rows[0].cells[1].text == "后端工程师"
    assert info.rows[1].cells[1].text == "张三"
    assert info.rows[2].cells[1].text == "2026-09-21 10:30"


def test_overall_score_formatted_one_decimal():
    """统一 1 位小数，与报告页 / 雷达图 / summarize_report 的口径一致。"""
    text = _all_text(build_report_docx(_report(overall_score=7.0)))

    assert "7.0 / 10" in text


def test_conclusion_present():
    text = _all_text(build_report_docx(_report()))

    assert "整体表现良好，建议结合岗位要求综合评估。" in text


def test_strengths_and_weaknesses_bulleted():
    document = _open(build_report_docx(_report()))
    styles = {
        paragraph.text: paragraph.style.name for paragraph in document.paragraphs
    }

    assert styles["沟通能力（8.0）：表现较好"] == "List Bullet"
    assert styles["逻辑思维（5.0）：有待提升"] == "List Bullet"


def test_empty_strengths_renders_placeholder():
    text = _all_text(build_report_docx(_report(strengths=[], weaknesses=[])))

    assert "（无）" in text


def test_question_table_has_header_and_rows():
    report = _report()
    document = _open(build_report_docx(report))
    table = document.tables[1]

    assert tuple(cell.text for cell in table.rows[0].cells) == QUESTION_HEADERS
    assert len(table.rows) == 1 + len(report.question_scores)


def test_question_table_keeps_full_answer():
    """回答是分数的证据，**不截断** —— 截断会让 HR 无法复核当初为什么给这个分。"""
    long_answer = "详" * 5000
    report = _report(
        question_scores=[
            QuestionScoreItem(
                interview_question_id=11,
                seq=1,
                content="题干",
                dimension="沟通能力",
                answer=long_answer,
                score=8.0,
                comment="很详细",
            )
        ]
    )

    table = _open(build_report_docx(report)).tables[1]

    assert table.rows[1].cells[3].text == long_answer


def test_null_answer_renders_placeholder():
    table = _open(build_report_docx(_report())).tables[1]

    assert table.rows[2].cells[3].text == "（未作答）"


def test_question_rows_ordered_by_seq():
    """行序沿用入参（get_report 已按 seq 排好），本模块**不重排**。"""
    report = _report(
        question_scores=[
            QuestionScoreItem(
                interview_question_id=13,
                seq=1,
                content="第一题",
                dimension="沟通能力",
                answer="答一",
                score=8.0,
                comment="好",
            ),
            QuestionScoreItem(
                interview_question_id=14,
                seq=2,
                content="第二题",
                dimension="专业能力",
                answer="答二",
                score=6.0,
                comment="中",
            ),
        ]
    )

    table = _open(build_report_docx(report)).tables[1]

    assert [table.rows[i].cells[2].text for i in (1, 2)] == ["第一题", "第二题"]
    assert [table.rows[i].cells[0].text for i in (1, 2)] == ["1", "2"]


def test_dimension_table_has_header_and_rows():
    report = _report()
    table = _open(build_report_docx(report)).tables[2]

    assert tuple(cell.text for cell in table.rows[0].cells) == DIMENSION_HEADERS
    assert len(table.rows) == 1 + len(report.dimension_scores)


def test_dimension_order_preserved():
    report = _report(
        dimension_scores=[
            DimensionScoreItem(dimension="乙维度", score=6.0, comment="b"),
            DimensionScoreItem(dimension="甲维度", score=8.0, comment="a"),
        ]
    )

    table = _open(build_report_docx(report)).tables[2]

    assert [table.rows[i].cells[0].text for i in (1, 2)] == ["乙维度", "甲维度"]


def test_no_images():
    """PRD §4.12 明确不放雷达图 —— 需要图形走前端打印 PDF。"""
    document = _open(build_report_docx(_report()))

    assert len(document.inline_shapes) == 0


def test_default_font_sets_east_asia():
    """⚠️ 本模块最重要的一条断言。

    中文字符走 `w:eastAsia` 分支，而 python-docx 的 `style.font.name = ...`
    **只改 `w:ascii`**。漏设时本机 Word 打开完全正常，只在 LibreOffice /
    部分 WPS 下退化甚至出方框 —— 没有这条测试必然被漏掉。
    """
    document = _open(build_report_docx(_report()))

    for style_name in ("Normal", "Heading 1", "Heading 2"):
        rfonts = document.styles[style_name].element.rPr.rFonts
        assert rfonts.get(qn("w:eastAsia")) == "宋体", f"{style_name} 未设置中文字体"


def test_boundary_scores():
    text = _all_text(
        build_report_docx(
            _report(
                overall_score=0.0,
                dimension_scores=[
                    DimensionScoreItem(dimension="沟通能力", score=10.0, comment="满分")
                ],
            )
        )
    )

    assert "0.0 / 10" in text
    assert "10.0" in text


def test_empty_tables_still_render_headers():
    """明细表为空时仍输出表头 —— 空表比整块消失更容易察觉异常。"""
    document = _open(
        build_report_docx(_report(question_scores=[], dimension_scores=[]))
    )

    assert tuple(cell.text for cell in document.tables[1].rows[0].cells) == (
        QUESTION_HEADERS
    )
    assert tuple(cell.text for cell in document.tables[2].rows[0].cells) == (
        DIMENSION_HEADERS
    )
    assert len(document.tables[1].rows) == 1
    assert len(document.tables[2].rows) == 1


def test_pure_function_no_side_effects():
    """同一份入参调用两次，两次输出都能被打开 —— 不依赖任何全局状态。"""
    report = _report()

    first = build_report_docx(report)
    second = build_report_docx(report)

    assert _open(first).paragraphs
    assert _open(second).paragraphs
    assert _all_text(first) == _all_text(second)
