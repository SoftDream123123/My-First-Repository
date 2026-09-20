"""MockProvider 测试。

特点：**不需要数据库、不需要 HTTP**，纯函数调用即可 ——
这是「ai 不依赖业务模块」这一约束带来的直接收益。
"""

import inspect

import pytest

from app.ai.base import AIProvider, DimensionScoreResult, QAPair
from app.ai.mock_provider import MockProvider
from app.core.exceptions import AIProviderError

DIMS = ["沟通能力", "专业能力", "逻辑思维"]

# 候选人反馈的入参：维度得分决定结论里点哪几个维度（阈值 PASS_THRESHOLD = 6.5）
FEEDBACK_DIMS = [
    DimensionScoreResult("沟通能力", 7.3, "评语"),
    DimensionScoreResult("文化契合", 5.1, "评语"),
]


def _dims(*pairs: tuple[str, float]) -> list[DimensionScoreResult]:
    return [DimensionScoreResult(name, score, "评语") for name, score in pairs]


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider()


# ------------------------------- 出题 -------------------------------


class TestGenerateQuestions:
    def test_returns_exact_count(self, provider):
        result = provider.generate_questions("后端工程师", "JD", DIMS, [], 3)
        assert len(result) == 3

    def test_count_zero_returns_empty(self, provider):
        assert provider.generate_questions("岗位", "JD", DIMS, [], 0) == []

    def test_count_negative_returns_empty(self, provider):
        assert provider.generate_questions("岗位", "JD", DIMS, [], -1) == []

    def test_empty_dims_raises(self, provider):
        with pytest.raises(AIProviderError):
            provider.generate_questions("岗位", "JD", [], [], 3)

    def test_dimensions_cycled(self, provider):
        result = provider.generate_questions("岗位", "JD", ["A", "B"], [], 5)
        assert [q.dimension for q in result] == ["A", "B", "A", "B", "A"]

    def test_dimension_always_within_dims(self, provider):
        result = provider.generate_questions("岗位", "JD", DIMS, [], 10)
        assert all(q.dimension in DIMS for q in result)

    def test_source_always_ai(self, provider):
        result = provider.generate_questions("岗位", "JD", DIMS, [], 5)
        assert all(q.source == "ai" for q in result)

    def test_difficulty_cycled(self, provider):
        result = provider.generate_questions("岗位", "JD", DIMS, [], 4)
        assert [q.difficulty for q in result] == ["easy", "medium", "hard", "easy"]

    def test_category_defaults_to_generic(self, provider):
        result = provider.generate_questions("岗位", "JD", DIMS, [], 2)
        assert all(q.category == "通用" for q in result)

    def test_tags_contain_dimension(self, provider):
        result = provider.generate_questions("岗位", "JD", DIMS, [], 3)
        assert all(q.tags == [q.dimension] for q in result)

    def test_content_is_non_empty(self, provider):
        result = provider.generate_questions("岗位", "JD", DIMS, [], 5)
        assert all(q.content.strip() for q in result)

    def test_deterministic(self, provider):
        """同参数调用两次，结果必须完全相等。"""
        first = provider.generate_questions("岗位", "JD", DIMS, [], 6)
        second = provider.generate_questions("岗位", "JD", DIMS, [], 6)
        assert first == second

    def test_avoids_existing_contents(self, provider):
        first = provider.generate_questions("岗位", "JD", DIMS, [], 3)
        existing = [q.content for q in first]

        second = provider.generate_questions("岗位", "JD", DIMS, existing, 3)
        assert all(q.content not in existing for q in second)

    def test_dedup_within_single_call(self, provider):
        """同一批生成内部也不应出现重复题干。"""
        result = provider.generate_questions("岗位", "JD", ["单一维度"], [], 6)
        contents = [q.content for q in result]
        assert len(contents) == len(set(contents))


# ----------------------------- 逐题评分 -----------------------------


class TestEvaluateAnswer:
    def test_none_answer_scores_zero(self, provider):
        result = provider.evaluate_answer("沟通能力", "题干", None)
        assert result.score == 0.0
        assert "无法评估" in result.comment

    def test_empty_answer_scores_zero(self, provider):
        assert provider.evaluate_answer("沟通能力", "题干", "").score == 0.0

    def test_whitespace_answer_scores_zero(self, provider):
        assert provider.evaluate_answer("沟通能力", "题干", "   \n\t ").score == 0.0

    @pytest.mark.parametrize(
        "length,expected",
        [(10, 3.0), (50, 5.0), (150, 7.0), (400, 8.5)],
    )
    def test_length_tiers(self, provider, length, expected):
        # 用不含数字 / 关键词的字符，排除加分干扰
        answer = "啊" * length
        assert provider.evaluate_answer("沟通能力", "题干", answer).score == expected

    def test_boundary_length_20(self, provider):
        assert provider.evaluate_answer("沟通", "题", "啊" * 20).score == 5.0

    def test_boundary_length_100(self, provider):
        assert provider.evaluate_answer("沟通", "题", "啊" * 100).score == 7.0

    def test_boundary_length_300(self, provider):
        assert provider.evaluate_answer("沟通", "题", "啊" * 300).score == 8.5

    def test_bonus_applied(self, provider):
        answer = "啊" * 20 + "1"
        assert provider.evaluate_answer("沟通", "题", answer).score == 5.5

    def test_bonus_capped_at_one_point_five(self, provider):
        answer = "啊" * 20 + "1 50% 项目 例如"
        assert provider.evaluate_answer("沟通", "题", answer).score == 6.5

    def test_score_never_exceeds_ten(self, provider):
        answer = "啊" * 500 + "1 50% 项目 例如"
        assert provider.evaluate_answer("沟通", "题", answer).score == 10.0

    def test_score_always_in_range(self, provider):
        for text in ["", "短", "啊" * 50, "啊" * 200, "啊" * 500 + "1234567890%项目例如"]:
            score = provider.evaluate_answer("沟通", "题", text).score
            assert 0.0 <= score <= 10.0

    def test_one_decimal_place(self, provider):
        score = provider.evaluate_answer("沟通", "题", "啊" * 20 + "1").score
        assert round(score, 1) == score

    def test_comment_tiers(self, provider):
        assert "无法评估" in provider.evaluate_answer("沟通", "题", None).comment
        assert "较简略" in provider.evaluate_answer("沟通", "题", "啊" * 10).comment
        assert "基本切题" in provider.evaluate_answer("沟通", "题", "啊" * 50).comment
        assert "详实" in provider.evaluate_answer("沟通", "题", "啊" * 400).comment

    def test_comment_mentions_dimension(self, provider):
        comment = provider.evaluate_answer("专业能力", "题", "啊" * 50).comment
        assert "专业能力" in comment

    def test_deterministic(self, provider):
        a = provider.evaluate_answer("沟通", "题", "啊" * 50 + "1")
        b = provider.evaluate_answer("沟通", "题", "啊" * 50 + "1")
        assert a == b


# ----------------------------- 多维评分 -----------------------------


class TestEvaluateDimensions:
    def test_covers_all_input_dims(self, provider):
        pairs = [QAPair("沟通能力", "题1", "答" * 50)]
        result = provider.evaluate_dimensions(DIMS, pairs)
        assert {r.dimension for r in result} == set(DIMS)

    def test_order_matches_input(self, provider):
        result = provider.evaluate_dimensions(DIMS, [])
        assert [r.dimension for r in result] == DIMS

    def test_average_of_question_scores(self, provider):
        short = QAPair("沟通能力", "题1", "啊" * 20)  # 5.0
        long = QAPair("沟通能力", "题2", "啊" * 100)  # 7.0
        result = provider.evaluate_dimensions(["沟通能力"], [short, long])
        assert result[0].score == 6.0

    def test_no_question_scores_zero(self, provider):
        result = provider.evaluate_dimensions(["无题维度"], [])
        assert result[0].score == 0.0
        assert "无对应题目" in result[0].comment

    def test_one_decimal_place(self, provider):
        pairs = [
            QAPair("沟通能力", "题1", "啊" * 20),   # 5.0
            QAPair("沟通能力", "题2", "啊" * 50),   # 5.0
            QAPair("沟通能力", "题3", "啊" * 100),  # 7.0
        ]
        result = provider.evaluate_dimensions(["沟通能力"], pairs)
        assert result[0].score == round(result[0].score, 1)

    def test_comment_by_tier(self, provider):
        weak = provider.evaluate_dimensions(["A"], [QAPair("A", "题", "啊" * 10)])[0]
        good = provider.evaluate_dimensions(["A"], [QAPair("A", "题", "啊" * 400)])[0]
        assert "偏弱" in weak.comment
        assert "突出" in good.comment


# ----------------------------- 汇总报告 -----------------------------


class TestSummarizeReport:
    def _scores(self, provider, values):
        from app.ai.base import DimensionScoreResult

        return [
            DimensionScoreResult(dimension=f"维度{i}", score=v, comment="c")
            for i, v in enumerate(values)
        ]

    def test_four_fields_present_and_non_empty(self, provider):
        result = provider.summarize_report([], self._scores(provider, [6.0, 8.0]), [])
        assert result.conclusion
        assert result.strengths
        assert result.weaknesses
        assert isinstance(result.overall_score, float)

    def test_overall_score_is_average(self, provider):
        result = provider.summarize_report(
            [], self._scores(provider, [6.0, 8.0, 10.0]), []
        )
        assert result.overall_score == 8.0

    def test_overall_in_range(self, provider):
        result = provider.summarize_report([], self._scores(provider, [0.0, 10.0]), [])
        assert 0.0 <= result.overall_score <= 10.0

    def test_empty_dimension_scores_does_not_raise(self, provider):
        result = provider.summarize_report([], [], [])
        assert result.overall_score == 0.0
        assert result.conclusion

    def test_strengths_threshold(self, provider):
        result = provider.summarize_report(
            [], self._scores(provider, [7.0, 6.5, 6.4]), []
        )
        assert len(result.strengths) == 2

    def test_weaknesses_threshold(self, provider):
        result = provider.summarize_report(
            [], self._scores(provider, [7.0, 6.5, 6.4]), []
        )
        assert len(result.weaknesses) == 1

    def test_strengths_never_empty_list(self, provider):
        result = provider.summarize_report([], self._scores(provider, [1.0, 2.0]), [])
        assert result.strengths == ["本次面试暂无明显优势维度"]

    def test_weaknesses_never_empty_list(self, provider):
        result = provider.summarize_report([], self._scores(provider, [9.0, 8.0]), [])
        assert result.weaknesses == ["本次面试暂无明显薄弱维度"]

    def test_conclusion_by_tier(self, provider):
        cases = [
            ([], "无法形成评估结论"),
            ([2.0], "未达预期"),
            ([5.0], "表现一般"),
            ([7.0], "表现良好"),
            ([9.0], "表现优秀"),
        ]
        for values, expected in cases:
            result = provider.summarize_report([], self._scores(provider, values), [])
            assert expected in result.conclusion

    def test_strength_entry_format(self, provider):
        result = provider.summarize_report([], self._scores(provider, [8.0]), [])
        assert "8.0" in result.strengths[0]
        assert "表现较好" in result.strengths[0]


# ======================= MVP-2：补参考答案 =======================


class TestGenerateReferenceAnswer:
    def test_short_answer_returns_non_empty(self, provider):
        result = provider.generate_reference_answer(
            "short_answer", "请描述一次你遇到的挑战", [], "沟通能力"
        )
        assert result.reference_answer.strip()
        assert result.explanation.strip()

    def test_is_deterministic(self, provider):
        args = ("short_answer", "同一道题干内容", [], "沟通能力")
        assert provider.generate_reference_answer(*args) == (
            provider.generate_reference_answer(*args)
        )

    def test_differs_by_content(self, provider):
        first = provider.generate_reference_answer(
            "short_answer", "第一道题的题干内容", [], "沟通能力"
        )
        second = provider.generate_reference_answer(
            "short_answer", "另一道完全不同的题干", [], "沟通能力"
        )
        assert first.reference_answer != second.reference_answer

    def test_single_choice_answer_is_verbatim_option(self, provider):
        options = ["选项甲", "选项乙", "选项丙"]
        result = provider.generate_reference_answer(
            "single_choice", "某道单选题的题干", options, "专业能力"
        )
        assert result.reference_answer in options

    def test_single_choice_empty_options_raises(self, provider):
        with pytest.raises(AIProviderError):
            provider.generate_reference_answer(
                "single_choice", "某道单选题的题干", [], "专业能力"
            )


# ======================= MVP-2：刷题判分 =======================


class TestGradePracticeAnswer:
    def test_empty_answer_scores_zero(self, provider):
        result = provider.grade_practice_answer(
            "short_answer", "题干", "参考答案", "   "
        )
        assert result.score == 0.0
        assert result.is_correct is False
        assert result.explanation == "未作答"

    def test_identical_answer_scores_full(self, provider):
        text = "参考答案的完整文本内容"
        result = provider.grade_practice_answer("short_answer", "题干", text, text)
        assert result.score == 10.0
        assert result.is_correct is True

    def test_disjoint_answer_scores_zero(self, provider):
        result = provider.grade_practice_answer("short_answer", "题干", "wxyz", "abcd")
        assert result.score == 0.0
        assert result.is_correct is False

    def test_score_has_at_most_one_decimal(self, provider):
        result = provider.grade_practice_answer(
            "short_answer", "题干", "abcdefghijklmnopqrstuvwxyz", "abcxyz"
        )
        assert round(result.score, 1) == result.score

    def test_is_deterministic(self, provider):
        args = ("short_answer", "题干", "参考答案内容", "考生作答内容")
        assert provider.grade_practice_answer(*args) == (
            provider.grade_practice_answer(*args)
        )

    def test_normalizes_whitespace(self, provider):
        result = provider.grade_practice_answer(
            "short_answer", "题干", "参考答案文本", "参考 答案 文本"
        )
        assert result.score == 10.0

    def test_single_char_answer_does_not_raise(self, provider):
        assert provider.grade_practice_answer(
            "short_answer", "题干", "x", "y"
        ).score == 0.0
        # 单字符退化路径不抛异常，公式仍成立
        assert provider.grade_practice_answer(
            "short_answer", "题干", "x", "x"
        ).score == 10.0

    def test_single_choice_equal(self, provider):
        result = provider.grade_practice_answer(
            "single_choice", "题干", "选项甲", " 选项甲 "
        )
        assert result.score == 10.0
        assert result.is_correct is True

    def test_single_choice_not_equal(self, provider):
        result = provider.grade_practice_answer(
            "single_choice", "题干", "选项甲", "选项乙"
        )
        assert result.score == 0.0
        assert result.is_correct is False

    def test_short_answer_empty_reference_raises(self, provider):
        with pytest.raises(AIProviderError):
            provider.grade_practice_answer("short_answer", "题干", "", "考生作答")


class TestGradeThresholdBoundary:
    """阈值边界（PASS_THRESHOLD = 6.5）。

    用「短串是长串前缀」构造精确的 Jaccard 比值：此时短串的二元组集合是长串的
    子集，故 overlap = (len(短) - 1) / (len(长) - 1)。

    两个字符串都取自同一段字符表的前缀，长度由切片给出并断言 —— 手数字符个数
    很容易差一个，那样算出来的就是另一个分数了。
    """

    # 52 个互不相同的字符，保证任意前缀的相邻二元组都不重复
    ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def _grade(self, provider, short_len: int, long_len: int):
        user = self.ALPHABET[:short_len]
        reference = self.ALPHABET[:long_len]
        assert len(user) == short_len and len(reference) == long_len
        return provider.grade_practice_answer(
            "short_answer", "题干", reference, user
        )

    def test_just_below_threshold_is_incorrect(self, provider):
        # 16 / 25 = 0.64 → 6.4
        result = self._grade(provider, short_len=17, long_len=26)
        assert result.score == pytest.approx(6.4)
        assert result.is_correct is False

    def test_at_threshold_is_correct(self, provider):
        # 13 / 20 = 0.65 → 6.5（边界必须判对）
        result = self._grade(provider, short_len=14, long_len=21)
        assert result.score == pytest.approx(6.5)
        assert result.is_correct is True

    def test_just_above_threshold_is_correct(self, provider):
        # 33 / 50 = 0.66 → 6.6
        result = self._grade(provider, short_len=34, long_len=51)
        assert result.score == pytest.approx(6.6)
        assert result.is_correct is True

    def test_is_correct_consistent_with_score(self, provider):
        """遍历多组输入，is_correct 恒等于 score >= PASS_THRESHOLD。"""
        from app.ai.base import PASS_THRESHOLD

        reference = self.ALPHABET[:26]
        for user in (
            "",
            "zzzz",
            "abc",
            self.ALPHABET[:2],
            self.ALPHABET[:10],
            self.ALPHABET[:17],
            self.ALPHABET[:14],
            self.ALPHABET[:26],
        ):
            result = provider.grade_practice_answer(
                "short_answer", "题干", reference, user
            )
            assert result.is_correct == (result.score >= PASS_THRESHOLD)


# ==================== MVP-2：候选人脱敏反馈 ====================


class TestGenerateCandidateFeedback:
    """候选人脱敏反馈（PRD §4.9）。"""

    def test_summary_hides_score(self, provider):
        result = provider.generate_candidate_feedback(
            "summary", 7.3, ["优点一"], ["待改进一"], FEEDBACK_DIMS
        )
        assert result.overall_score is None

    def test_full_keeps_score(self, provider):
        result = provider.generate_candidate_feedback(
            "full", 7.3, ["优点一"], ["待改进一"], FEEDBACK_DIMS
        )
        assert result.overall_score == 7.3

    def test_unknown_level_defaults_to_summary(self, provider):
        result = provider.generate_candidate_feedback(
            "detailed", 7.3, ["优点一"], ["待改进一"], FEEDBACK_DIMS
        )
        assert result.overall_score is None

    def test_preserves_item_count_and_order(self, provider):
        strengths = ["优点一", "优点二", "优点三"]
        weaknesses = ["待改进一", "待改进二"]
        result = provider.generate_candidate_feedback(
            "summary", 5.0, strengths, weaknesses, FEEDBACK_DIMS
        )
        assert len(result.strengths) == len(strengths)
        assert len(result.weaknesses) == len(weaknesses)
        assert result.strengths[0] == "优点一"
        assert result.strengths[2] == "优点三"

    def test_is_deterministic(self, provider):
        args = ("summary", 7.3, ["优点一"], ["待改进一"], FEEDBACK_DIMS)
        assert provider.generate_candidate_feedback(*args) == (
            provider.generate_candidate_feedback(*args)
        )

    def test_conclusion_names_strong_and_weak_dimensions(self, provider):
        """结论只点出**是哪几个维度**，理由交给那两条列表 —— 免得逐字重复。"""
        result = provider.generate_candidate_feedback(
            "summary",
            6.2,
            ["沟通能力（7.3）：表现较好"],
            ["文化契合（5.1）：有待提升"],
            _dims(("沟通能力", 7.3), ("文化契合", 5.1)),
        )
        assert "沟通能力" in result.conclusion
        assert "文化契合" in result.conclusion

    def test_conclusion_carries_no_hiring_verdict(self, provider):
        """PRD §4.9（2026-09-21 修正）：结论不带招聘方的去留判断。

        `_conclusion` 在**每个**分数段给的都是去留建议，所以逐段扫一遍 ——
        只要有人把报告结论接回来，这个断言立刻失败。
        """
        verdicts = (
            "建议暂不推进",
            "建议针对薄弱维度追加考察",
            "建议结合岗位要求综合评估",
            "建议进入下一轮",
        )
        for overall in (2.0, 5.0, 7.0, 9.0):
            result = provider.generate_candidate_feedback(
                "summary", overall, ["优点一"], ["待改进一"], FEEDBACK_DIMS
            )
            for verdict in verdicts:
                assert verdict not in result.conclusion

    def test_interface_does_not_accept_report_conclusion(self):
        """结构性保证：接口上就没有「报告结论」这个入参。

        不是靠叮嘱「不要复述」，而是根本不给它 —— 与 `CandidateFeedbackOut`
        用白名单保证分数不下发是同一手法（PRD §4.9）。
        """
        params = inspect.signature(AIProvider.generate_candidate_feedback).parameters
        assert "conclusion" not in params


# ========================= 契约一致性 =========================


def test_mock_provider_implements_all_nine_methods():
    """守门测试：漏实现任何抽象方法时，MockProvider() 会以 TypeError 失败。"""
    from app.ai.base import AIProvider

    assert len(AIProvider.__abstractmethods__) == 9
    assert not MockProvider.__abstractmethods__


def test_mock_provider_is_ai_provider(provider):
    from app.ai.base import AIProvider

    assert isinstance(provider, AIProvider)


# ========================= 按简历匹配题目 =========================


def _brief(qid: int, content: str, dimension: str = "沟通能力", category: str = "通用"):
    from app.ai.base import QuestionBrief

    return QuestionBrief(
        question_id=qid, content=content, dimension=dimension, category=category
    )


# 一段与下面所有题干都没有字符重合的简历，用于构造「全零分」场景
UNRELATED_RESUME = "甲乙丙丁戊己庚辛壬癸"
UNRELATED_CONTENT = "子丑寅卯辰巳午未申酉"


class TestMatchQuestionsByResume:
    def _match(self, provider, resume=UNRELATED_RESUME, candidates=(), count=3):
        return provider.match_questions_by_resume(
            resume, "后端工程师", "JD", DIMS, list(candidates), count
        )

    def test_same_input_same_output(self, provider):
        candidates = [
            _brief(1, "请描述一次性能优化的经历", dimension="专业能力"),
            _brief(2, "如何与非技术同事沟通", dimension="沟通能力"),
        ]
        first = self._match(provider, "简历里提到专业能力与沟通能力", candidates, 2)
        second = self._match(provider, "简历里提到专业能力与沟通能力", candidates, 2)

        assert first == second

    def test_blank_resume_raises(self, provider):
        with pytest.raises(AIProviderError):
            self._match(provider, resume="   ", candidates=[_brief(1, "题干")], count=1)

    def test_empty_dims_raises(self, provider):
        with pytest.raises(AIProviderError):
            provider.match_questions_by_resume(
                "一段简历", "岗位", "JD", [], [_brief(1, "题干")], 1
            )

    def test_count_zero_returns_empty(self, provider):
        assert self._match(provider, candidates=[_brief(1, "题干")], count=0) == []

    def test_empty_candidates_returns_empty(self, provider):
        """题库里没有可匹配的题是**正常业务状态**，不是错误。"""
        assert self._match(provider, candidates=[], count=3) == []

    def test_dimension_hit_ranks_first(self, provider):
        candidates = [
            _brief(1, "同一段题干内容", dimension="沟通能力"),
            _brief(2, "同一段题干内容", dimension="专业能力"),
        ]
        result = self._match(
            provider, resume="简历里写了专业能力相关经历", candidates=candidates, count=2
        )

        assert [item.question_id for item in result] == [2, 1]

    def test_respects_count(self, provider):
        candidates = [_brief(i, f"第{i}题的题干内容描述") for i in range(1, 11)]

        assert len(self._match(provider, candidates=candidates, count=3)) == 3

    def test_ids_all_from_pool(self, provider):
        candidates = [_brief(i, f"第{i}题的题干内容描述") for i in range(1, 6)]
        pool = {item.question_id for item in candidates}

        result = self._match(provider, "一份普通简历内容描述", candidates, 4)
        assert {item.question_id for item in result} <= pool

    def test_tie_break_by_question_id(self, provider):
        """完全同分的两题必须按 question_id 升序 —— 否则结果依赖传入顺序。"""
        candidates = [
            _brief(20, "完全相同的题干内容描述"),
            _brief(10, "完全相同的题干内容描述"),
        ]
        result = self._match(provider, candidates=candidates, count=2)

        assert [item.question_id for item in result] == [10, 20]

    def test_reason_mentions_dimension_when_hit(self, provider):
        result = self._match(
            provider,
            resume="简历里写了专业能力相关经历",
            candidates=[_brief(1, "一道与简历无关的题干", dimension="专业能力")],
            count=1,
        )
        assert "专业能力" in result[0].reason

    def test_all_zero_scores_is_deterministic(self, provider):
        """简历与所有题都无交集 → 退化为「按 id 升序的前 count 条」，理由走通用文案。"""
        candidates = [
            _brief(3, UNRELATED_CONTENT),
            _brief(1, UNRELATED_CONTENT),
            _brief(2, UNRELATED_CONTENT),
        ]
        result = self._match(provider, candidates=candidates, count=3)

        assert [item.question_id for item in result] == [1, 2, 3]
        assert all(item.reason == "本题与岗位评估维度相关，作为通用考察项。" for item in result)

    def test_overlap_uses_question_denominator(self):
        """⚠️ 本模块最重要的一条：分母必须是**题干**，不是 Jaccard 的并集。

        若有人「顺手复用」`_similarity`，长简历会把并集完全主导，该值塌到
        1e-3 量级 —— 断言会失败，从而把「用对分母」这个非显然的决策钉住。
        """
        from app.ai.mock_provider import _resume_overlap, _similarity

        question = "熟悉 Python 与 MySQL 数据库设计"
        # 用 1200 个互不相同的汉字构造一份高基数的长简历 —— 真实简历的用词分布
        # 就是这样散的。若用「其他经历描述」这类重复短语，二元组集合会很小，
        # 两种口径就区分不开了，测试也就失去了钉住能力。
        filler = "".join(chr(0x4E00 + i) for i in range(1200))
        resume = question + "。" + filler

        assert _resume_overlap(question, resume) > 0.9
        assert _similarity(question, resume) < 0.05  # 两种口径确实不同


# ========================= 面试前准备提纲 =========================


PREP_RESUME = (
    "五年 Python 后端开发经验，主导过订单系统重构与支付链路拆分，"
    "熟悉 FastAPI 与 MySQL。"
)


class TestGenerateInterviewPrep:
    def _prep(self, provider, resume=None, candidate="张三", questions=()):
        return provider.generate_interview_prep(
            "后端工程师", "JD", DIMS, candidate, resume, list(questions)
        )

    def test_same_input_same_output(self, provider):
        questions = [_brief(1, "请描述一次性能优化的经历", dimension="专业能力")]
        first = self._prep(provider, PREP_RESUME, questions=questions)
        second = self._prep(provider, PREP_RESUME, questions=questions)

        assert first == second

    def test_empty_dims_raises(self, provider):
        with pytest.raises(AIProviderError):
            provider.generate_interview_prep("岗位", "JD", [], "张三", None, [])

    def test_without_resume_ok(self, provider):
        result = self._prep(provider, resume=None)

        assert result.outline
        assert result.focus_points
        assert result.question_plan

    def test_without_resume_has_no_resume_focus(self, provider):
        result = self._prep(provider, resume=None)

        assert all(point.dimension != "简历核对" for point in result.focus_points)

    def test_with_resume_adds_resume_focus(self, provider):
        result = self._prep(provider, resume=PREP_RESUME)

        resume_points = [p for p in result.focus_points if p.dimension == "简历核对"]
        assert len(resume_points) == 1
        assert PREP_RESUME[:40] in resume_points[0].reason

    def test_without_candidate_name_uses_default(self, provider):
        result = self._prep(provider, resume=None, candidate="")

        assert "候选人" in result.outline[0].notes

    def test_outline_total_duration(self, provider):
        result = self._prep(provider, resume=PREP_RESUME)

        assert [stage.seq for stage in result.outline] == [1, 2, 3, 4]
        assert sum(stage.duration_min for stage in result.outline) == 45
        assert all(stage.duration_min > 0 for stage in result.outline)

    def test_focus_points_cover_all_dims(self, provider):
        result = self._prep(provider, resume=None)

        assert [point.dimension for point in result.focus_points] == DIMS

    def test_question_plan_uses_existing_questions_first(self, provider):
        questions = [
            _brief(1, "本场第一道题", dimension="专业能力"),
            _brief(2, "本场第二道题", dimension="沟通能力"),
        ]
        result = self._prep(provider, resume=None, questions=questions)

        assert [item.question for item in result.question_plan[:2]] == [
            "本场第一道题",
            "本场第二道题",
        ]

    def test_question_plan_pads_to_max(self, provider):
        result = self._prep(provider, resume=None, questions=[])

        assert len(result.question_plan) == 4
        assert all("关于" in item.question for item in result.question_plan)

    def test_question_plan_capped(self, provider):
        questions = [_brief(i, f"第{i}道本场题目") for i in range(1, 11)]

        assert len(self._prep(provider, resume=None, questions=questions).question_plan) == 4

    def test_without_questions_ok(self, provider):
        result = self._prep(provider, resume=None, questions=[])

        assert result.outline and result.focus_points and result.question_plan

    def test_follow_ups_are_non_empty_lists(self, provider):
        result = self._prep(provider, resume=PREP_RESUME)

        assert all(item.follow_ups for item in result.question_plan)
        assert all(
            isinstance(text, str) and text.strip()
            for item in result.question_plan
            for text in item.follow_ups
        )
