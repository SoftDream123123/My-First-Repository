"""OpenAIProvider 测试 —— **全部使用 httpx.MockTransport，不打真实 API**。"""

import json

import httpx
import pytest

from app.ai.base import CANDIDATE_FEEDBACK_LEAD, DimensionScoreResult, QAPair, QuestionBrief
from app.ai.openai_provider import OpenAIProvider
from app.core.config import get_settings
from app.core.exceptions import AIProviderError


@pytest.fixture(autouse=True)
def _openai_settings(monkeypatch):
    monkeypatch.setenv("PROVIDER_NAME", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("AI_MAX_RETRIES", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def _provider(handler) -> OpenAIProvider:
    return OpenAIProvider(transport=httpx.MockTransport(handler))


def _json_reply(payload) -> httpx.Response:
    return _reply(json.dumps(payload, ensure_ascii=False))


# ---------------------------- 配置校验 ----------------------------


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(AIProviderError):
        OpenAIProvider()


# ---------------------------- 解析容错 ----------------------------


class TestParsingTolerance:
    def test_strips_markdown_fence(self):
        def handler(request):
            return _reply(
                '```json\n{"score": 8.0, "comment": "不错"}\n```'
            )

        result = _provider(handler).evaluate_answer("沟通", "题", "答" * 50)
        assert result.score == 8.0
        assert result.comment == "不错"

    def test_extracts_json_from_prose(self):
        def handler(request):
            return _reply(
                '好的，以下是评分结果：{"score": 6.5, "comment": "尚可"} 希望有帮助。'
            )

        result = _provider(handler).evaluate_answer("沟通", "题", "答" * 50)
        assert result.score == 6.5

    def test_clamps_out_of_range_score(self):
        def handler(request):
            return _reply('{"score": 15, "comment": "超范围"}')

        assert _provider(handler).evaluate_answer("沟通", "题", "答").score == 10.0

    def test_clamps_negative_score(self):
        def handler(request):
            return _reply('{"score": -5, "comment": "负数"}')

        assert _provider(handler).evaluate_answer("沟通", "题", "答").score == 0.0

    def test_non_numeric_score_becomes_zero(self):
        def handler(request):
            return _reply('{"score": "excellent", "comment": "非数值"}')

        assert _provider(handler).evaluate_answer("沟通", "题", "答").score == 0.0

    def test_empty_strengths_gets_placeholder(self):
        def handler(request):
            return _json_reply(
                {
                    "overall_score": 8.0,
                    "conclusion": "不错",
                    "strengths": [],
                    "weaknesses": [],
                }
            )

        report = _provider(handler).summarize_report([], [], [])
        assert report.strengths == ["本次面试暂无明显优势维度"]
        assert report.weaknesses == ["本次面试暂无明显薄弱维度"]

    def test_strengths_as_string_is_tolerated(self):
        def handler(request):
            return _json_reply(
                {
                    "overall_score": 8.0,
                    "conclusion": "不错",
                    "strengths": "不是数组",
                    "weaknesses": None,
                }
            )

        report = _provider(handler).summarize_report([], [], [])
        assert report.strengths == ["本次面试暂无明显优势维度"]


# ---------------------------- 重试逻辑 ----------------------------


class TestRetry:
    def test_retries_once_then_succeeds(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(500, json={"error": "boom"})
            return _reply('{"score": 7.0, "comment": "重试后成功"}')

        result = _provider(handler).evaluate_answer("沟通", "题", "答")
        assert result.score == 7.0
        assert calls["n"] == 2

    def test_retries_on_parse_failure_then_raises(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _reply("这不是 JSON")

        with pytest.raises(AIProviderError):
            _provider(handler).evaluate_answer("沟通", "题", "答")
        assert calls["n"] == 2  # 1 次初始 + 1 次重试

    def test_timeout_raises_provider_error(self):
        def handler(request):
            raise httpx.TimeoutException("timeout")

        with pytest.raises(AIProviderError):
            _provider(handler).evaluate_answer("沟通", "题", "答")

    def test_http_error_raises_provider_error(self):
        def handler(request):
            return httpx.Response(401, json={"error": "unauthorized"})

        with pytest.raises(AIProviderError):
            _provider(handler).evaluate_answer("沟通", "题", "答")

    def test_error_message_mentions_attempts(self):
        def handler(request):
            return httpx.Response(500)

        with pytest.raises(AIProviderError) as exc:
            _provider(handler).evaluate_answer("沟通", "题", "答")
        assert "2 次" in str(exc.value)


# ------------------------------- 出题 -------------------------------


class TestGenerateQuestions:
    def test_parses_question_array(self):
        def handler(request):
            return _json_reply(
                [
                    {
                        "content": "题目一",
                        "dimension": "沟通能力",
                        "difficulty": "hard",
                        "category": "行为",
                        "tags": ["沟通"],
                    },
                    {"content": "题目二", "dimension": "专业能力"},
                ]
            )

        result = _provider(handler).generate_questions(
            "后端工程师", "JD", ["沟通能力", "专业能力"], [], 2
        )
        assert len(result) == 2
        assert result[0].content == "题目一"
        assert result[0].difficulty == "hard"
        assert result[1].difficulty == "medium"  # 缺省值
        assert all(q.source == "ai" for q in result)

    def test_drops_item_with_unmappable_dimension(self):
        def handler(request):
            return _json_reply(
                [
                    {"content": "有效题", "dimension": "沟通能力"},
                    {"content": "无效题", "dimension": "完全无关的维度"},
                ]
            )

        result = _provider(handler).generate_questions(
            "岗位", "JD", ["沟通能力"], [], 2
        )
        assert len(result) == 1
        assert result[0].content == "有效题"

    def test_maps_dimension_by_substring(self):
        def handler(request):
            return _json_reply([{"content": "题", "dimension": "沟通"}])

        result = _provider(handler).generate_questions(
            "岗位", "JD", ["沟通能力"], [], 1
        )
        assert result[0].dimension == "沟通能力"

    def test_empty_dims_raises_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _reply("[]")

        with pytest.raises(AIProviderError):
            _provider(handler).generate_questions("岗位", "JD", [], [], 2)
        assert calls["n"] == 0

    def test_count_zero_returns_empty_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _reply("[]")

        assert _provider(handler).generate_questions("岗位", "JD", ["A"], [], 0) == []
        assert calls["n"] == 0


# ----------------------------- 多维评分 -----------------------------


class TestEvaluateDimensions:
    def test_returns_in_input_order(self):
        def handler(request):
            return _json_reply(
                [
                    {"dimension": "专业能力", "score": 8.0, "comment": "b"},
                    {"dimension": "沟通能力", "score": 6.0, "comment": "a"},
                ]
            )

        result = _provider(handler).evaluate_dimensions(
            ["沟通能力", "专业能力"], [QAPair("沟通能力", "题", "答")]
        )
        assert [r.dimension for r in result] == ["沟通能力", "专业能力"]
        assert result[0].score == 6.0

    def test_missing_dimension_filled_with_zero(self):
        def handler(request):
            return _json_reply([{"dimension": "沟通能力", "score": 6.0, "comment": "a"}])

        result = _provider(handler).evaluate_dimensions(
            ["沟通能力", "专业能力"], [QAPair("沟通能力", "题", "答")]
        )
        assert len(result) == 2
        assert result[1].dimension == "专业能力"
        assert result[1].score == 0.0

    def test_empty_dims_returns_empty_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _reply("[]")

        assert _provider(handler).evaluate_dimensions([], []) == []
        assert calls["n"] == 0


# ------------------------------ 请求体 ------------------------------


def test_request_contains_model_and_auth_header():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return _reply('{"score": 5.0, "comment": "ok"}')

    _provider(handler).evaluate_answer("沟通", "题", "答")

    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["messages"][0]["role"] == "system"


# ======================= MVP-2：补参考答案 =======================


class TestGenerateReferenceAnswer:
    def test_parses_json(self):
        def handler(request):
            return _json_reply(
                {"reference_answer": "标准答案文本", "explanation": "因为……"}
            )

        result = _provider(handler).generate_reference_answer(
            "short_answer", "题干", [], "沟通能力"
        )
        assert result.reference_answer == "标准答案文本"
        assert result.explanation == "因为……"

    def test_bad_json_raises(self):
        def handler(request):
            return _reply("这不是 JSON")

        with pytest.raises(AIProviderError):
            _provider(handler).generate_reference_answer(
                "short_answer", "题干", [], "沟通能力"
            )

    def test_missing_field_raises(self):
        """缺 reference_answer 不填默认值，直接失败。"""

        def handler(request):
            return _json_reply({"explanation": "只有解析没有答案"})

        with pytest.raises(AIProviderError):
            _provider(handler).generate_reference_answer(
                "short_answer", "题干", [], "沟通能力"
            )

    def test_single_choice_empty_options_makes_no_request(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply({"reference_answer": "x", "explanation": "y"})

        with pytest.raises(AIProviderError):
            _provider(handler).generate_reference_answer(
                "single_choice", "题干", [], "沟通能力"
            )
        assert calls["n"] == 0

    def test_answer_outside_options_is_returned_verbatim(self):
        """不在选项内**不纠正** —— 静默吸附等于伪造正确答案（module-10 §5.2）。"""

        def handler(request):
            return _json_reply(
                {"reference_answer": "选项之外的臆造答案", "explanation": "因为……"}
            )

        result = _provider(handler).generate_reference_answer(
            "single_choice", "题干", ["选项甲", "选项乙"], "沟通能力"
        )
        assert result.reference_answer == "选项之外的臆造答案"


# ======================= MVP-2：刷题判分 =======================


class TestGradePracticeAnswer:
    def _grade(self, handler, user_answer="考生作答内容"):
        return _provider(handler).grade_practice_answer(
            "short_answer", "题干", "参考答案内容", user_answer
        )

    def test_clamps_score_above_max(self):
        def handler(request):
            return _json_reply({"score": 15.0, "explanation": "越界"})

        assert self._grade(handler).score == 10.0

    def test_clamps_score_below_min(self):
        def handler(request):
            return _json_reply({"score": -3, "explanation": "越界"})

        assert self._grade(handler).score == 0.0

    def test_derives_is_correct_locally(self):
        """模型说 false，但 7.0 >= 6.5 → 后端仍判 True。阈值必须唯一。"""

        def handler(request):
            return _json_reply(
                {"score": 7.0, "is_correct": False, "explanation": "模型乱说"}
            )

        result = self._grade(handler)
        assert result.score == 7.0
        assert result.is_correct is True

    def test_empty_reference_short_circuits_without_request(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply({"score": 5.0, "explanation": "x"})

        with pytest.raises(AIProviderError):
            _provider(handler).grade_practice_answer(
                "short_answer", "题干", "   ", "考生作答内容"
            )
        assert calls["n"] == 0

    def test_empty_answer_short_circuits_without_request(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply({"score": 5.0, "explanation": "x"})

        result = _provider(handler).grade_practice_answer(
            "short_answer", "题干", "参考答案内容", "   "
        )
        assert result.score == 0.0
        assert result.is_correct is False
        assert result.explanation == "未作答"
        assert calls["n"] == 0

    def test_missing_score_field_raises(self):
        def handler(request):
            return _json_reply({"explanation": "没有分数"})

        with pytest.raises(AIProviderError):
            self._grade(handler)

    def test_retries_then_raises(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(500, json={"error": "boom"})

        with pytest.raises(AIProviderError):
            self._grade(handler)
        assert calls["n"] == 2  # 1 次初始 + 1 次重试


# ==================== MVP-2：候选人脱敏反馈 ====================


class TestGenerateCandidateFeedback:
    def _feedback(self, handler, level="summary"):
        return _provider(handler).generate_candidate_feedback(
            level,
            7.3,
            ["优点一"],
            ["待改进一"],
            [DimensionScoreResult("沟通能力", 7.3, "评语")],
        )

    def test_summary_omits_score(self):
        def handler(request):
            return _json_reply(
                {"conclusion": "改写后的结论", "strengths": ["优点一"], "weaknesses": ["待改进一"]}
            )

        result = self._feedback(handler, level="summary")
        assert result.overall_score is None

    def test_full_keeps_score(self):
        def handler(request):
            return _json_reply(
                {"conclusion": "改写后的结论", "strengths": ["优点一"], "weaknesses": ["待改进一"]}
            )

        result = self._feedback(handler, level="full")
        assert result.overall_score == 7.3

    def test_unknown_level_defaults_to_summary(self):
        def handler(request):
            return _json_reply(
                {"conclusion": "改写后的结论", "strengths": ["优点一"], "weaknesses": ["待改进一"]}
            )

        result = self._feedback(handler, level="detailed")
        assert result.overall_score is None

    def test_non_list_items_fall_back_to_empty(self):
        """模型把数组写成字符串时，回落为空列表而不是抛错。"""

        def handler(request):
            return _json_reply(
                {"conclusion": "结论", "strengths": "优点一", "weaknesses": None}
            )

        result = self._feedback(handler)
        assert result.strengths == []
        assert result.weaknesses == []

    def test_missing_conclusion_falls_back_without_verdict(self):
        """模型没给结论时兜一句没有信息量的话。

        **不能**退回报告那句结论 —— 那里面有招聘方的去留判断（PRD §4.9）。
        """

        def handler(request):
            return _json_reply({"strengths": ["优点一"], "weaknesses": []})

        assert self._feedback(handler).conclusion == CANDIDATE_FEEDBACK_LEAD


# ------------------------- 按简历匹配题目 -------------------------

MATCH_DIMS = ["沟通能力", "专业能力"]
MATCH_POOL = [
    QuestionBrief(question_id=1, content="请描述一次性能优化的经历", dimension="专业能力", category="技术"),
    QuestionBrief(question_id=2, content="如何与非技术同事沟通", dimension="沟通能力", category="通用"),
]


def _match(handler, count=3, resume="五年 Python 后端开发经验"):
    return _provider(handler).match_questions_by_resume(
        resume, "后端工程师", "JD", MATCH_DIMS, MATCH_POOL, count
    )


class TestMatchQuestionsByResume:
    def test_parses_valid_response(self):
        def handler(request):
            return _json_reply([{"question_id": 1, "reason": "与简历中的性能优化经历相关"}])

        result = _match(handler)
        assert len(result) == 1
        assert result[0].question_id == 1
        assert result[0].reason == "与简历中的性能优化经历相关"

    def test_drops_unknown_ids(self):
        """池外 id 一律丢弃 —— 「只挑不生成」的第二层保证。"""

        def handler(request):
            return _json_reply(
                [
                    {"question_id": 1, "reason": "有效"},
                    {"question_id": 999, "reason": "编造的题"},
                ]
            )

        result = _match(handler)
        assert [item.question_id for item in result] == [1]

    def test_dedupes_ids(self):
        def handler(request):
            return _json_reply(
                [
                    {"question_id": 1, "reason": "第一次"},
                    {"question_id": 1, "reason": "重复"},
                ]
            )

        result = _match(handler)
        assert len(result) == 1
        assert result[0].reason == "第一次"

    def test_all_ids_invalid_raises(self):
        """非空数组但 id 全无效 = 输出不合格，**不能**静默当作「无匹配」。"""

        def handler(request):
            return _json_reply([{"question_id": 888, "reason": "编造的题"}])

        with pytest.raises(AIProviderError):
            _match(handler)

    def test_empty_array_returns_empty(self):
        """空数组是正当结论：确实没有相关题目。与上一条必须可区分。"""

        def handler(request):
            return _json_reply([])

        assert _match(handler) == []

    def test_truncates_to_count(self):
        def handler(request):
            return _json_reply(
                [
                    {"question_id": 1, "reason": "一"},
                    {"question_id": 2, "reason": "二"},
                ]
            )

        assert len(_match(handler, count=1)) == 1

    def test_strips_code_fence(self):
        def handler(request):
            return _reply(
                '```json\n[{"question_id": 2, "reason": "沟通经历相关"}]\n```'
            )

        assert _match(handler)[0].question_id == 2

    def test_blank_resume_raises_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply([])

        with pytest.raises(AIProviderError):
            _match(handler, resume="   ")
        assert calls["n"] == 0

    def test_count_zero_returns_empty_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply([])

        assert _match(handler, count=0) == []
        assert calls["n"] == 0


# ------------------------- 面试前准备提纲 -------------------------


def _prep_payload() -> dict:
    return {
        "outline": [
            {"seq": 1, "phase": "开场", "duration_min": 5, "notes": "自我介绍"},
            {"seq": 2, "phase": "能力考察", "duration_min": 40, "notes": "逐项验证"},
        ],
        "focus_points": [
            {"dimension": "沟通能力", "point": "验证沟通", "reason": "岗位需要跨部门协作"}
        ],
        "question_plan": [
            {
                "question": "请做一下自我介绍",
                "intent": "了解背景",
                "follow_ups": ["为什么选择这行"],
            }
        ],
    }


def _prep(handler, dims=None, resume="五年 Python 后端开发经验", questions=()):
    return _provider(handler).generate_interview_prep(
        "后端工程师",
        "JD",
        dims if dims is not None else MATCH_DIMS,
        "张三",
        resume,
        list(questions),
    )


class TestGenerateInterviewPrep:
    def test_parses_valid_response(self):
        def handler(request):
            return _json_reply(_prep_payload())

        result = _prep(handler)
        assert [stage.phase for stage in result.outline] == ["开场", "能力考察"]
        assert result.focus_points[0].dimension == "沟通能力"
        assert result.question_plan[0].follow_ups == ["为什么选择这行"]

    def test_empty_section_raises(self):
        """三部分任一为空即整批失败 —— 缺一块的提纲不具备可用性。"""

        payload = _prep_payload()
        payload["outline"] = []

        def handler(request):
            return _json_reply(payload)

        with pytest.raises(AIProviderError):
            _prep(handler)

    @pytest.mark.parametrize("bad", ["十分钟", 0, -3, None])
    def test_invalid_duration_falls_back(self, bad):
        payload = _prep_payload()
        payload["outline"][0]["duration_min"] = bad

        def handler(request):
            return _json_reply(payload)

        assert _prep(handler).outline[0].duration_min == 5

    def test_seq_filled_when_missing(self):
        payload = _prep_payload()
        for stage in payload["outline"]:
            stage.pop("seq")

        def handler(request):
            return _json_reply(payload)

        assert [stage.seq for stage in _prep(handler).outline] == [1, 2]

    def test_coerces_dimension(self):
        payload = _prep_payload()
        payload["focus_points"][0]["dimension"] = "沟通"

        def handler(request):
            return _json_reply(payload)

        assert _prep(handler).focus_points[0].dimension == "沟通能力"

    def test_follow_ups_sanitized(self):
        payload = _prep_payload()
        payload["question_plan"][0]["follow_ups"] = ["有效的追问", "", "   ", 123]

        def handler(request):
            return _json_reply(payload)

        assert _prep(handler).question_plan[0].follow_ups == ["有效的追问", "123"]

    def test_non_dict_raises(self):
        def handler(request):
            return _json_reply([{"outline": []}])

        with pytest.raises(AIProviderError):
            _prep(handler)

    def test_empty_dims_raises_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply(_prep_payload())

        with pytest.raises(AIProviderError):
            _prep(handler, dims=[])
        assert calls["n"] == 0

    def test_without_resume_still_calls_api(self):
        """与 match 相反：无简历是**正常输入**，照常生成，不得短路成异常。"""

        def handler(request):
            return _json_reply(_prep_payload())

        assert _prep(handler, resume=None).outline


# ---------------------- 简历与岗位匹配度评估 ----------------------

REVIEW_DIMS = ["沟通能力", "专业能力", "逻辑思维"]
REVIEW_RESUME = "沟通能力：主导跨部门沟通。专业能力：五年 Python 后端开发。"
REVIEW_JD = "负责后端服务的设计与开发。"


def _review_payload(**overrides):
    payload = {
        "match_score": 7.4,
        "conclusion": "简历与岗位要求有较好重合，个别维度可再补充。",
        "strengths": ["沟通能力相关经历清晰"],
        "gaps": ["专业能力缺少可核对的项目数据"],
    }
    payload.update(overrides)
    return payload


class TestEvaluateResume:
    def _review(
        self,
        handler,
        resume=REVIEW_RESUME,
        dims=REVIEW_DIMS,
        jd=REVIEW_JD,
        position="后端开发",
    ):
        return _provider(handler).evaluate_resume(
            position_name=position, jd=jd, dims=dims, resume_text=resume
        )

    def test_parses_all_fields(self):
        result = self._review(lambda request: _json_reply(_review_payload()))

        assert result.match_score == 7.4
        assert result.conclusion == "简历与岗位要求有较好重合，个别维度可再补充。"
        assert result.strengths == ["沟通能力相关经历清晰"]
        assert result.gaps == ["专业能力缺少可核对的项目数据"]

    @pytest.mark.parametrize(
        "raw,expected", [(42, 10.0), (-3, 0.0), ("6.75", 6.8), ("不是数字", 0.0)]
    )
    def test_score_is_clamped_and_rounded(self, raw, expected):
        result = self._review(
            lambda request: _json_reply(_review_payload(match_score=raw))
        )

        assert result.match_score == expected

    def test_items_are_capped(self):
        payload = _review_payload(
            strengths=[f"亮点{i}" for i in range(1, 10)],
            gaps=[f"差距{i}" for i in range(1, 10)],
        )
        result = self._review(lambda request: _json_reply(payload))

        assert len(result.strengths) == 5
        assert len(result.gaps) == 5

    def test_empty_strengths_raises(self):
        """与 Mock 同款前置：亮点为空说明这次评估没有可用产出，不能静默给差评。"""
        payload = _review_payload(strengths=[])

        with pytest.raises(AIProviderError):
            self._review(lambda request: _json_reply(payload))

    def test_non_object_response_raises(self):
        with pytest.raises(AIProviderError):
            self._review(lambda request: _json_reply([1, 2, 3]))

    def test_missing_conclusion_falls_back_without_hire_judgement(self):
        payload = _review_payload(conclusion="")

        conclusion = self._review(lambda request: _json_reply(payload)).conclusion

        assert conclusion.strip()
        for word in ("下一轮", "不建议", "淘汰", "录用"):
            assert word not in conclusion

    def test_blank_resume_raises_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply(_review_payload())

        for resume in ("", "   "):
            with pytest.raises(AIProviderError):
                self._review(handler, resume=resume)
        assert calls["n"] == 0

    def test_empty_dims_raises_without_calling_api(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return _json_reply(_review_payload())

        with pytest.raises(AIProviderError):
            self._review(handler, dims=[])
        assert calls["n"] == 0

    def test_blank_position_name_and_jd_are_tolerated(self):
        """岗位名与 JD 允许为空：简历是被评估的对象，JD 只是依据之一。"""
        result = self._review(
            lambda request: _json_reply(_review_payload()), position="", jd=""
        )

        assert result.strengths

    def test_input_validation_matches_mock_provider(self):
        """两个 Provider 的入参校验必须一致，否则「同输入不同行为」会在换
        Provider 时暴露成线上故障（module-27 §5.5 用例 10）。"""
        from app.ai.mock_provider import MockProvider

        mock = MockProvider()
        handler = lambda request: _json_reply(_review_payload())  # noqa: E731

        for kwargs in ({"resume": ""}, {"resume": "  "}, {"dims": []}):
            with pytest.raises(AIProviderError):
                mock.evaluate_resume(
                    position_name="后端开发",
                    jd=REVIEW_JD,
                    dims=kwargs.get("dims", REVIEW_DIMS),
                    resume_text=kwargs.get("resume", REVIEW_RESUME),
                )
            with pytest.raises(AIProviderError):
                self._review(handler, **kwargs)
