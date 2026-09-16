"""统一异常体系。

所有业务异常继承 AppError，由 main.py 的全局处理器统一转换为三字段响应：
    {code, message, detail}
"""

from typing import Any


class AppError(Exception):
    """业务异常基类。"""

    code: str = "APP_ERROR"
    status_code: int = 400
    default_message: str = "请求处理失败"

    def __init__(self, message: str | None = None, detail: Any = None) -> None:
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 400
    default_message = "请求参数不合法"


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = 401
    default_message = "未认证"


class InvalidTokenError(UnauthorizedError):
    code = "INVALID_TOKEN"
    status_code = 401
    default_message = "登录状态已失效，请重新登录"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403
    default_message = "无权限执行此操作"


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404
    default_message = "资源不存在"


class BusinessError(AppError):
    code = "BUSINESS_ERROR"
    status_code = 409
    default_message = "业务规则冲突"


class AIProviderError(AppError):
    code = "AI_PROVIDER_ERROR"
    status_code = 502
    default_message = "AI 服务调用失败，请稍后重试"


class InternalError(AppError):
    code = "INTERNAL_ERROR"
    status_code = 500
    default_message = "服务器内部错误"
