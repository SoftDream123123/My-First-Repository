"""Mock 短信通道：**不真的发短信**（PRD §6）。

存在的意义只有一条：让开发与演示**无需任何运营商账号**即可走通手机验证码
全流程。因此它把验证码写进日志，并经由 `echoes_code = True` 让发码端点
把码回显给前端。

⚠️ 正因如此，**生产部署必须把 `SMS_PROVIDER` 配成真实值** —— 否则验证码会被
写进生产日志并回给浏览器。这一条已进部署清单（PRD §6、§9）。
"""

import logging

from app.sms.base import SmsProvider, mask_phone

logger = logging.getLogger(__name__)


class MockSmsProvider(SmsProvider):
    """把验证码写进日志。"""

    echoes_code = True

    def send_code(self, phone: str, code: str) -> None:
        # 这里**记验证码本身**是 Mock 的唯一职责；真实 Provider 不得这么做（§6）。
        # 手机号仍走掩码 —— 日志里的验证码是这台机器上的演示凭据，手机号是 PII，
        # 两者的取舍不同，不能因为「反正码都打了」就顺手把号也打全。
        logger.info("Mock 短信已发送：%s 验证码 %s", mask_phone(phone), code)
