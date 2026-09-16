"""core.exceptions 与全局异常处理器测试。"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.core.exceptions import (
    AIProviderError,
    AppError,
    BusinessError,
    ForbiddenError,
    InternalError,
    InvalidTokenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

# (异常类, 期望 code, 期望 HTTP 状态)
_EXPECTED = [
    (AppError, "APP_ERROR", 400),
    (ValidationError, "VALIDATION_ERROR", 400),
    (UnauthorizedError, "UNAUTHORIZED", 401),
    (InvalidTokenError, "INVALID_TOKEN", 401),
    (ForbiddenError, "FORBIDDEN", 403),
    (NotFoundError, "NOT_FOUND", 404),
    (BusinessError, "BUSINESS_ERROR", 409),
    (AIProviderError, "AI_PROVIDER_ERROR", 502),
    (InternalError, "INTERNAL_ERROR", 500),
]


@pytest.mark.parametrize("exc_class,expected_code,expected_status", _EXPECTED)
def test_exception_code_and_status(exc_class, expected_code, expected_status):
    assert exc_class.code == expected_code
    assert exc_class.status_code == expected_status


@pytest.mark.parametrize("exc_class,_code,_status", _EXPECTED)
def test_exception_has_non_empty_chinese_message(exc_class, _code, _status):
    """默认 message 必须是非空中文，可直接展示给用户。"""
    message = exc_class().message
    assert message
    assert any("一" <= ch <= "鿿" for ch in message)


def test_invalid_token_inherits_unauthorized():
    assert issubclass(InvalidTokenError, UnauthorizedError)


def test_all_exceptions_inherit_app_error():
    for exc_class, _code, _status in _EXPECTED:
        assert issubclass(exc_class, AppError)


def test_exception_accepts_custom_message_and_detail():
    exc = BusinessError("自定义文案", detail={"from": "a", "to": "b"})
    assert exc.message == "自定义文案"
    assert exc.detail == {"from": "a", "to": "b"}


class TestConfig:
    def test_missing_required_fields_raises(self, monkeypatch):
        """必填项缺失时构造 Settings 即报错（fail fast）。"""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(PydanticValidationError):
            Settings(_env_file=None)

    def test_defaults_are_applied(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@127.0.0.1:3306/db")
        monkeypatch.setenv("JWT_SECRET", "s")
        settings = Settings(_env_file=None)
        assert settings.provider_name == "mock"
        assert settings.question_count_from_bank == 5
        assert settings.question_count_from_ai == 3
        assert settings.ai_max_retries == 1
        assert settings.jwt_expire_minutes == 720
