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


class TooManyRequestsError(AppError):
    """限流。detail 里带 retry_after_seconds，前端据此显示倒计时（PRD §7）。

    ⚠️ **与 practice 的限流刻意不一致**：`practice.service._check_rate_limit`
    超限时抛的是 `BusinessError`（409），因为它只需要一个「过一会儿再来」的
    提示、且该契约已随既有测试与前端固化。而发码限流**有明确的重试时机**，
    `Retry-After` / 429 是 HTTP 为该场景预定义的语义，合并进 400/409 会让前端
    **永久失去**「还要等几秒」这个信息（PRD §7 已把这条与「不新增 413」的取舍
    对照说明）。

    **不要为了「统一」把两者改成一样**：改 practice 是超范围的破坏性契约变更
    （收益接近于零，它的窗口只有 60 秒且前端没做倒计时），改这里则会让发码
    按钮失去倒计时依据。
    """

    code = "TOO_MANY_REQUESTS"
    status_code = 429
    default_message = "操作过于频繁，请稍后再试"


class SmsProviderError(AppError):
    """短信通道调用失败（发送失败 / Provider 取值非法）。

    与 `AIProviderError` 同一档：502 + 不降级 —— 发送失败就告诉用户失败了，
    由他去重试。**注意失败时验证码已落库且仍然有效**（service 刻意不回滚，
    理由见 auth.service.send_phone_code）。
    """

    code = "SMS_PROVIDER_ERROR"
    status_code = 502
    default_message = "短信服务发送失败，请稍后重试"


class AIProviderError(AppError):
    code = "AI_PROVIDER_ERROR"
    status_code = 502
    default_message = "AI 服务调用失败，请稍后重试"


class InternalError(AppError):
    code = "INTERNAL_ERROR"
    status_code = 500
    default_message = "服务器内部错误"
