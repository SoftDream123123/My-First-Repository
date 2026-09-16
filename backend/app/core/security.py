"""安全原语：密码哈希 / 校验、JWT 签发 / 解码。

设计要点：
- 密码盐由 bcrypt 内嵌在哈希串中，不单独存储
- JWT 载荷中不放角色 —— 角色每次请求从数据库读取，
  保证「改角色 / 禁用账号」立即生效，不必等 token 过期
- decode_token 不做数据库查询，保持纯函数，便于单测
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError

# bcrypt 只使用前 72 字节，超出部分必须显式截断，否则 bcrypt>=4 会直接抛错。
# 截断在哈希与校验两侧行为一致，因此不影响正确性。
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    """把明文编码为 bcrypt 可接受的字节串。"""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(raw: str) -> str:
    """用 bcrypt 哈希明文密码，返回可直接入库的哈希串。"""
    settings = get_settings()
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(_prepare(raw), salt).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    """校验明文密码是否匹配哈希串。

    哈希串格式非法时返回 False 而非抛异常 —— 调用方（登录流程）
    只需区分「匹配 / 不匹配」两种情况。
    """
    try:
        return bcrypt.checkpw(_prepare(raw), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    """签发 access token。载荷：sub / iat / exp。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # JWT 规范要求 sub 为字符串
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> int:
    """解码 token，返回 user_id。

    过期 / 签名错误 / 格式错误 / sub 非法，一律抛 InvalidTokenError（401）。
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    sub = payload.get("sub")
    if sub is None:
        raise InvalidTokenError()

    try:
        return int(sub)
    except (TypeError, ValueError) as exc:
        raise InvalidTokenError() from exc
