"""auth 手机验证码登录测试（计划书 module-31 §8、PRD §4.16）。

全部在 **service 层**跑，Provider 用假实现注入 —— 这样验证码的明文就在测试手里
（`fake.sent[-1][1]`），不必去猜一个随机码，也不必让它可预测。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.auth import repository, service
from app.auth.models import ROLE_ADMIN, ROLE_CANDIDATE, ROLE_HR
from app.core.config import get_settings
from app.core.exceptions import SmsProviderError, TooManyRequestsError, UnauthorizedError
from app.sms.base import SmsProvider

PHONE = "13800138000"
IP = "127.0.0.1"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FakeSms(SmsProvider):
    """记录发出的验证码，供断言取用。`echoes_code` / `fail` 可控。"""

    def __init__(self, *, echoes_code: bool = True, fail: bool = False) -> None:
        self.echoes_code = echoes_code
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def send_code(self, phone: str, code: str) -> None:
        if self.fail:
            raise SmsProviderError("模拟通道故障")
        self.sent.append((phone, code))


@pytest.fixture
def fake_sms(monkeypatch) -> FakeSms:
    """注入假 Provider。

    打的是 **auth.service 里的那个名字**（`from app.sms.factory import get_provider
    as get_sms_provider` 绑定出的模块级名字），与既有的 ai Provider 注入手法一致 ——
    改 `sms.factory.get_provider` 是没用的，service 早已持有自己的引用。
    """
    fake = FakeSms()
    monkeypatch.setattr("app.auth.service.get_sms_provider", lambda: fake)
    return fake


def _send(db, phone: str = PHONE, ip: str | None = IP):
    return service.send_phone_code(db, phone, ip)


def _age_codes(db, phone: str, seconds: int = 120) -> None:
    """把该号已有验证码的发码时间往前推，绕开 60 秒重发间隔。

    ⚠️ 不能用 `invalidate_codes` 代替：重发间隔看的是 `get_latest_code`，而它
    **不论码是否已消费** —— 它回答的是「上次发码是什么时候」。作废一个码不等于
    「没发过」，两者是不同的事实（这正是 repository 里把两个查询函数分开的理由）。
    """
    db.execute(
        text("UPDATE phone_verification_code SET created_at = :t WHERE phone = :p"),
        {"t": _now() - timedelta(seconds=seconds), "p": phone},
    )
    db.commit()


def _seed_code(
    db,
    phone: str,
    *,
    created_at: datetime,
    ip: str | None = None,
    consumed: bool = False,
):
    """直接落一条历史验证码。

    限流用例需要「过去 24 小时内已发 10 条」这类前置，而真的调 10 次
    `send_phone_code` 会被 60 秒重发间隔挡住 —— 只能绕过 service 直接造数据。
    """
    row = repository.create_code(
        db,
        phone=phone,
        code_hash="0" * 64,
        code_salt="seed",
        expires_at=created_at + timedelta(seconds=300),
        request_ip=ip,
    )
    row.created_at = created_at
    if consumed:
        row.consumed_at = created_at
    db.commit()
    return row


# ------------------------------ 发码 ------------------------------


class TestSendCode:
    def test_first_send_returns_ttl_and_dev_code(self, db, fake_sms):
        result = _send(db)

        assert result.expires_in == 300
        assert result.dev_code is not None
        assert len(result.dev_code) == 6 and result.dev_code.isdigit()
        assert fake_sms.sent == [(PHONE, result.dev_code)]

    def test_dev_code_absent_when_provider_does_not_echo(self, db, fake_sms):
        """`dev_code` 的判据是 Provider 的能力标志，不是配置开关（PRD §6）。"""
        fake_sms.echoes_code = False

        result = _send(db)

        assert result.dev_code is None
        assert fake_sms.sent  # 码确实发出去了，只是不回显

    def test_response_identical_whether_phone_registered_or_not(self, db, fake_sms, admin_user):
        """发码响应不区分手机号是否已注册（PRD §4.16）。

        否则这个端点就是一个手机号枚举接口 —— 攻击者能借它判断某个号码是不是
        本系统用户。

        （响应**结构**的逐字段相等在 API 层断言 —— 那里才看得见 JSON 键集合；
        服务层只能断言两者的 TTL 与 dev_code 出现与否一致。）
        """
        service.update_user(db, admin_user, admin_user.id, phone=PHONE)

        registered = _send(db)
        unregistered = service.send_phone_code(db, "13900139000", IP)

        assert registered.expires_in == unregistered.expires_in
        assert (registered.dev_code is None) == (unregistered.dev_code is None)
        assert len(registered.dev_code) == len(unregistered.dev_code) == 6

    def test_resend_interval_rejected(self, db, fake_sms):
        _send(db)

        with pytest.raises(TooManyRequestsError) as exc:
            _send(db)

        retry_after = exc.value.detail["retry_after_seconds"]
        assert 1 <= retry_after <= 60

    def test_daily_limit_per_phone_rejected(self, db, fake_sms):
        now = _now()
        # 10 条历史码，最晚的一条在 5 分钟前 —— 大于 60 秒的重发间隔，
        # 因此命中②（日上限）而不是①（重发间隔）。
        for i in range(10):
            _seed_code(db, PHONE, created_at=now - timedelta(minutes=5 + i), ip=IP)

        with pytest.raises(TooManyRequestsError) as exc:
            _send(db)

        assert exc.value.detail["retry_after_seconds"] >= 1

    def test_hourly_limit_per_ip_rejected(self, db, fake_sms):
        now = _now()
        # 20 个**不同号码**、同一个 IP —— 单号上限挡不住这种「换号刷」，
        # 这正是 IP 那一层存在的理由。
        for i in range(20):
            _seed_code(
                db, f"1380013{i:04d}", created_at=now - timedelta(minutes=5), ip=IP
            )

        with pytest.raises(TooManyRequestsError) as exc:
            _send(db, phone="13911112222")

        assert exc.value.detail["retry_after_seconds"] >= 1

    def test_missing_ip_skips_only_the_ip_layer(self, db, fake_sms):
        """拿不到 IP 不该让用户完全无法发码 —— 只跳过 IP 那一层。"""
        now = _now()
        for i in range(20):
            _seed_code(db, f"1380013{i:04d}", created_at=now - timedelta(minutes=5), ip=IP)

        result = service.send_phone_code(db, "13911112222", None)

        assert result.dev_code is not None

    def test_new_code_invalidates_old_ones(self, db, fake_sms):
        """新码发出即作废旧码（PRD §4.16）—— 否则多条码同时有效，攻击面乘以 N。"""
        _send(db)
        first_code = fake_sms.sent[-1][1]

        # 绕过重发间隔再发一次
        _age_codes(db, PHONE)
        _send(db)
        second_code = fake_sms.sent[-1][1]
        assert second_code != first_code

        with pytest.raises(UnauthorizedError):
            service.login_by_phone(db, PHONE, first_code)

        assert service.login_by_phone(db, PHONE, second_code).user.role == ROLE_CANDIDATE

    def test_send_failure_keeps_code_valid(self, db, fake_sms):
        """发送失败**不回滚落库**的码（PRD §7）。

        真实运营商接口的失败往往是超时而非未送达 —— 回滚会制造「码已作废」的
        假象：用户手机上收到一条永远用不了的验证码，而库里查不到它。
        """
        fake_sms.fail = True

        with pytest.raises(SmsProviderError):
            _send(db)

        row = repository.get_latest_code(db, PHONE)
        assert row is not None
        assert row.consumed_at is None  # 仍然可用


# ------------------------------ 登录 ------------------------------


class TestLoginByPhone:
    def test_unknown_phone_creates_candidate_account(self, db, fake_sms):
        """⚠️ 安全红线：手机号路径**不得**产出 hr / admin（PRD §4.16）。

        若这条路径能产出特权账号，那么「知道某个手机号」就等于「拿到 HR 身份」。
        """
        code = _send(db).dev_code

        result = service.login_by_phone(db, PHONE, code)

        assert result.user.role == ROLE_CANDIDATE
        assert result.user.role not in (ROLE_HR, ROLE_ADMIN)  # 反向断言
        assert result.user.phone == PHONE
        assert result.user.username == f"phone_{PHONE}"
        assert result.token

    def test_same_phone_twice_reuses_the_same_account(self, db, fake_sms):
        first = service.login_by_phone(db, PHONE, _send(db).dev_code)
        _age_codes(db, PHONE)
        second = service.login_by_phone(db, PHONE, _send(db).dev_code)

        assert first.user.id == second.user.id

    def test_auto_created_account_has_no_usable_password(self, db, fake_sms):
        """`password_hash` 是不可知随机值的原像 —— 密码登录路径必然拒绝它。"""
        service.login_by_phone(db, PHONE, _send(db).dev_code)
        username = f"phone_{PHONE}"

        for guess in ("", PHONE, "password", "password123"):
            with pytest.raises(UnauthorizedError):
                service.login(db, username, guess)

    def test_phone_bound_to_hr_logs_in_as_hr(self, db, fake_sms, admin_user):
        """「全部角色可用」的正解：角色由**绑定**决定，不由手机号路径决定。"""
        hr = service.create_user(db, "hr_by_phone", "hr12345678", ROLE_HR)
        service.update_user(db, admin_user, hr.id, phone=PHONE)

        code = _send(db).dev_code
        result = service.login_by_phone(db, PHONE, code)

        assert result.user.id == hr.id
        assert result.user.role == ROLE_HR

    def test_phone_bound_to_admin_logs_in_as_admin(self, db, fake_sms, admin_user):
        service.update_user(db, admin_user, admin_user.id, phone=PHONE)

        result = service.login_by_phone(db, PHONE, _send(db).dev_code)

        assert result.user.role == ROLE_ADMIN

    def test_normalization_creates_only_one_account(self, db, fake_sms, admin_user):
        """四种写法必须归一到同一个号码，否则唯一约束挡不住「一个号占两行」。"""
        from app.auth.schemas import normalize_phone

        for raw in (" 138 0013 8000 ", "+8613800138000", "8613800138000", "138-0013-8000"):
            assert normalize_phone(raw) == PHONE

        service.login_by_phone(db, PHONE, _send(db).dev_code)

        from app.auth.models import User

        assert db.query(User).filter(User.phone == PHONE).count() == 1

    def test_wrong_code_increments_attempts(self, db, fake_sms):
        code = _send(db).dev_code
        wrong = "000000" if code != "000000" else "111111"

        with pytest.raises(UnauthorizedError):
            service.login_by_phone(db, PHONE, wrong)

        assert repository.get_latest_code(db, PHONE).attempts == 1

    def test_code_voided_after_max_attempts(self, db, fake_sms):
        """错满 5 次后该码作废 —— 即使改填正确的码也只会得到同一句 401。"""
        code = _send(db).dev_code
        wrong = "000000" if code != "000000" else "111111"

        for _ in range(get_settings().phone_code_max_attempts):
            with pytest.raises(UnauthorizedError):
                service.login_by_phone(db, PHONE, wrong)

        assert repository.get_latest_code(db, PHONE).consumed_at is not None

        with pytest.raises(UnauthorizedError):
            service.login_by_phone(db, PHONE, code)

    def test_code_is_single_use(self, db, fake_sms):
        code = _send(db).dev_code
        service.login_by_phone(db, PHONE, code)

        with pytest.raises(UnauthorizedError):
            service.login_by_phone(db, PHONE, code)

    def test_expired_code_rejected(self, db, fake_sms):
        code = _send(db).dev_code
        db.execute(
            text(
                "UPDATE phone_verification_code SET expires_at = :past WHERE phone = :phone"
            ),
            {"past": _now() - timedelta(seconds=1), "phone": PHONE},
        )
        db.commit()

        with pytest.raises(UnauthorizedError):
            service.login_by_phone(db, PHONE, code)

    def test_four_failure_modes_share_one_message(self, db, fake_sms):
        """不存在 / 已过期 / 已消费 / 不匹配 —— 四类**不得有任何可区分差异**。

        文案分叉会让这个端点变成验证码状态探测器。
        """
        code = _send(db).dev_code
        wrong = "000000" if code != "000000" else "111111"
        messages = []

        # ① 不匹配
        with pytest.raises(UnauthorizedError) as exc:
            service.login_by_phone(db, PHONE, wrong)
        messages.append(exc.value.message)

        # ② 码存在但已过期
        _seed_code(db, "13900000001", created_at=_now() - timedelta(days=1))
        db.execute(
            text("UPDATE phone_verification_code SET expires_at = :past WHERE phone = :p"),
            {"past": _now() - timedelta(seconds=1), "p": "13900000001"},
        )
        db.commit()
        with pytest.raises(UnauthorizedError) as exc:
            service.login_by_phone(db, "13900000001", "123456")
        messages.append(exc.value.message)

        # ③ 已消费
        service.login_by_phone(db, PHONE, code)
        with pytest.raises(UnauthorizedError) as exc:
            service.login_by_phone(db, PHONE, code)
        messages.append(exc.value.message)

        # ④ 压根没有码
        with pytest.raises(UnauthorizedError) as exc:
            service.login_by_phone(db, "13900000002", "123456")
        messages.append(exc.value.message)

        assert messages == ["验证码错误或已失效"] * 4

    def test_disabled_account_rejected_and_code_not_consumed(self, db, fake_sms, admin_user):
        hr = service.create_user(db, "hr_disabled", "hr12345678", ROLE_HR)
        service.update_user(db, admin_user, hr.id, phone=PHONE, is_active=False)

        code = _send(db).dev_code
        with pytest.raises(UnauthorizedError) as exc:
            service.login_by_phone(db, PHONE, code)

        assert exc.value.message == "账号已禁用，请联系管理员"
        # 禁用的原因与验证码无关，没必要把人仅有的一次正确输入判成「已用完」
        assert repository.get_latest_code(db, PHONE).consumed_at is None

    def test_no_code_at_all_rejected(self, db, fake_sms):
        with pytest.raises(UnauthorizedError):
            service.login_by_phone(db, PHONE, "123456")
