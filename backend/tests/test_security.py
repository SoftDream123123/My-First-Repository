"""core.security 单元测试：密码哈希与 JWT。"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify_password(self):
        hashed = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-battery", hashed) is True
        assert verify_password("wrong-password", hashed) is False

    def test_hash_not_plaintext(self):
        raw = "plaintext-password"
        assert hash_password(raw) != raw

    def test_hash_produces_different_salts(self):
        """同一明文两次哈希结果不同 —— 盐已生效。"""
        assert hash_password("same-input") != hash_password("same-input")

    def test_hash_is_bcrypt_format(self):
        assert hash_password("x").startswith("$2b$")

    def test_verify_password_bad_hash_returns_false(self):
        """非法哈希串返回 False 而非抛异常。"""
        assert verify_password("x", "not-a-bcrypt-hash") is False
        assert verify_password("x", "") is False

    def test_verify_long_password_is_truncated_consistently(self):
        """超过 bcrypt 72 字节上限的密码不应抛错，且校验两侧行为一致。"""
        long_password = "a" * 200
        hashed = hash_password(long_password)
        assert verify_password(long_password, hashed) is True


class TestJwt:
    def test_create_and_decode_token_roundtrip(self):
        token = create_access_token(42)
        assert decode_token(token) == 42

    def test_decode_expired_token_raises(self):
        settings = get_settings()
        past = datetime.now(UTC) - timedelta(hours=1)
        expired = jwt.encode(
            {"sub": "1", "iat": past, "exp": past + timedelta(seconds=1)},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(InvalidTokenError):
            decode_token(expired)

    def test_decode_tampered_token_raises(self):
        token = create_access_token(1)
        head, payload, signature = token.split(".")
        tampered = f"{head}.{payload}.{signature[:-4]}AAAA"
        with pytest.raises(InvalidTokenError):
            decode_token(tampered)

    def test_decode_garbage_raises(self):
        with pytest.raises(InvalidTokenError):
            decode_token("not-a-jwt-at-all")

    def test_decode_token_wrong_secret_raises(self):
        other = jwt.encode({"sub": "1"}, "another-secret", algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_token(other)

    def test_token_payload_has_no_role(self):
        """角色不缓存于 JWT —— 保证改角色 / 禁用立即生效。"""
        settings = get_settings()
        token = create_access_token(7)
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        assert "role" not in payload
        assert payload["sub"] == "7"
