"""MockProvider 测试。

特点：**不需要数据库、不需要 HTTP**，纯函数调用即可 ——
这是「ai 不依赖业务模块」这一约束带来的直接收益。
"""

import pytest

from app.ai.base import QAPair
from app.ai.mock_provider import MockProvider
from app.core.exceptions import AIProviderError

DIMS = ["沟通能力", "专业能力", "逻辑思维"]


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
    def test_summary_hides_score(self, provider):
        result = provider.generate_candidate_feedback(
            "summary", "结论", ["优点一"], ["待改进一"], 7.3
        )
        assert result.overall_score is None

    def test_full_keeps_score(self, provider):
        result = provider.generate_candidate_feedback(
            "full", "结论", ["优点一"], ["待改进一"], 7.3
        )
        assert result.overall_score == 7.3

    def test_unknown_level_defaults_to_summary(self, provider):
        result = provider.generate_candidate_feedback(
            "detailed", "结论", ["优点一"], ["待改进一"], 7.3
        )
        assert result.overall_score is None

    def test_preserves_item_count_and_order(self, provider):
        strengths = ["优点一", "优点二", "优点三"]
        weaknesses = ["待改进一", "待改进二"]
        result = provider.generate_candidate_feedback(
            "summary", "结论", strengths, weaknesses, 5.0
        )
        assert len(result.strengths) == len(strengths)
        assert len(result.weaknesses) == len(weaknesses)
        assert result.strengths[0] == "优点一"
        assert result.strengths[2] == "优点三"

    def test_is_deterministic(self, provider):
        args = ("summary", "结论", ["优点一"], ["待改进一"], 7.3)
        assert provider.generate_candidate_feedback(*args) == (
            provider.generate_candidate_feedback(*args)
        )


# ========================= 契约一致性 =========================


def test_mock_provider_implements_all_seven_methods():
    """守门测试：漏实现任何抽象方法时，MockProvider() 会以 TypeError 失败。"""
    from app.ai.base import AIProvider

    assert len(AIProvider.__abstractmethods__) == 7
    assert not MockProvider.__abstractmethods__


def test_mock_provider_is_ai_provider(provider):
    from app.ai.base import AIProvider

    assert isinstance(provider, AIProvider)
