"""短信通道契约：抽象基类 + 日志掩码工具。

与 `ai` 包**同构**的可切换 Provider（PRD §3.3、§6）。

设计要点与 `ai/base.py` 一致：本模块**只接收原始值**（字符串），不接收任何 ORM
对象；它也**不感知验证码的业务语义** —— 生成、落库、比对、作废全在 auth
（PRD §6）。因此换短信通道不会触碰任何业务规则。
"""

from abc import ABC, abstractmethod


def mask_phone(phone: str) -> str:
    """`13800138000` → `138****8000`。

    手机号是 PII，日志里一律用掩码（PRD §6）。

    短于 7 位时**整体掩码**而不是切片：正常输入不会这么短，但这是唯一一个
    把手机号写到日志的公共入口，切片越界或原样漏出去都是不可接受的失败方向。
    """
    if len(phone) < 7:
        return "*" * len(phone)
    return f"{phone[:3]}****{phone[-4:]}"


class SmsProvider(ABC):
    """短信通道抽象基类。"""

    #: 是否把验证码回显给调用方 —— 仅 Mock 为 True（PRD §6）。
    #:
    #: ⚠️ 用**能力标志**而非 `isinstance` 判断：auth.service 因此不需要 import
    #: 任何具体 Provider 类，也就不会有「service 认识 mock」这条隐性耦合。
    #: 将来新增一个会回显的实现（如测试用的假实现）不需要动 service 一行。
    echoes_code: bool = False

    @abstractmethod
    def send_code(self, phone: str, code: str) -> None:
        """把验证码发到 phone。失败抛 `SmsProviderError`。

        实现须**自行掩码**后再记日志 —— 本方法拿到的是明文手机号，
        日志安全是每个实现自己的职责，不能指望调用方代劳。
        """
