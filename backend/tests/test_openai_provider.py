"""OpenAIProvider 测试 —— **全部使用 httpx.MockTransport，不打真实 API**。"""

import json

import httpx
import pytest

from app.ai.base import QAPair
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
