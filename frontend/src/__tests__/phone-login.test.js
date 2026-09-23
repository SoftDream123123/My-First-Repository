/**
 * 手机验证码登录的纯函数单测（module-32 §6）。
 *
 * 为什么要抽成纯函数：本工程的**前端测试只能测纯函数**（无 DOM 环境，
 * module-07 §8.1 的既有决策）。把判定留在 `buildPhoneLoginForm` 里，
 * 就等于**它永远不会被测到** —— 而它们错起来很安静：`resendLabel` 返回负数秒、
 * `retryAfterSeconds` 返回 NaN，都不会报错，只会让按钮显示一个荒唐的值。
 */

import { describe, expect, it } from 'vitest';
import {
  PHONE_CODE_LENGTH, PHONE_CODE_RESEND_SECONDS, isValidPhone, normalizePhone,
  resendLabel, retryAfterSeconds, validatePhoneLogin,
} from '../components/phone-login.js';

const CANONICAL = '13800138000';

describe('normalizePhone —— 归一化', () => {
  it('四种写法全部归一到同一个号码', () => {
    // 这四种写法必须归一到一起：否则同一个号会占两行，
    // 而 `user.phone` 的唯一约束挡不住它 —— 这个号的主人会拿到两个账号。
    for (const raw of [' 138 0013 8000 ', '+8613800138000', '8613800138000', CANONICAL]) {
      expect(normalizePhone(raw)).toBe(CANONICAL);
    }
  });

  it('连字符与括号也被剔除', () => {
    expect(normalizePhone('138-0013-8000')).toBe(CANONICAL);
    expect(normalizePhone('(138)00138000')).toBe(CANONICAL);
  });

  it('只剥一层国家码前缀', () => {
    // 叠了两层的是脏数据，应当判为非法，而不是被反复剥成一个合法号码
    expect(normalizePhone('868613800138000')).toBe('8613800138000');
  });

  it('`86` 单独出现时不剥成空串', () => {
    expect(normalizePhone('86')).toBe('86');
  });

  it('空值与 null 不炸', () => {
    expect(normalizePhone('')).toBe('');
    expect(normalizePhone(null)).toBe('');
    expect(normalizePhone(undefined)).toBe('');
  });

  it('合法号码本身以 1 开头，不会被误当国家码剥掉', () => {
    expect(normalizePhone('18600138000')).toBe('18600138000');
  });
});

describe('isValidPhone —— 格式判定', () => {
  it('合法号码', () => {
    expect(isValidPhone(CANONICAL)).toBe(true);
    expect(isValidPhone('19912345678')).toBe(true);
    expect(isValidPhone('+8613800138000')).toBe(true);
  });

  it('非法号码', () => {
    for (const bad of ['', '1380013800', '138001380000', '12800138000', 'aaaaa', '13800138000x']) {
      expect(isValidPhone(bad), bad).toBe(false);
    }
  });
});

describe('validatePhoneLogin —— 表单校验', () => {
  it('两者皆空时**两个**字段都报错（不是只报第一个）', () => {
    const errors = validatePhoneLogin({ phone: '', code: '' });
    expect(errors.phone).toBeTruthy();
    expect(errors.code).toBeTruthy();
  });

  it('手机号合法、验证码非 6 位数字 → 只有 code 有错', () => {
    for (const bad of ['', '12345', '1234567', 'abcdef', '12345x']) {
      const errors = validatePhoneLogin({ phone: CANONICAL, code: bad });
      expect(errors.phone, bad).toBeUndefined();
      expect(errors.code, bad).toBeTruthy();
    }
  });

  it('全合法 → 空对象', () => {
    expect(validatePhoneLogin({ phone: CANONICAL, code: '123456' })).toEqual({});
    // 带空格的手机号与验证码也应通过（归一化 + trim）
    expect(validatePhoneLogin({ phone: ' 138 0013 8000 ', code: ' 123456 ' })).toEqual({});
  });
});

describe('resendLabel —— 重发按钮显示态', () => {
  it('倒计时中 → 禁用 + 剩余秒数', () => {
    expect(resendLabel(60)).toEqual({ disabled: true, text: '60 秒后重发' });
    expect(resendLabel(1)).toEqual({ disabled: true, text: '1 秒后重发' });
  });

  it('归零 → 可点 + 「获取验证码」', () => {
    expect(resendLabel(0)).toEqual({ disabled: false, text: '获取验证码' });
  });

  it('负数与非法值都当 0 处理，**不显示负数秒**', () => {
    // 这是「安静错」的典型：算出 -3 不会报错，只会在界面上写「-3 秒后重发」
    for (const bad of [-5, -0.5, NaN, null, undefined, 'abc', {}]) {
      expect(resendLabel(bad), String(bad)).toEqual({ disabled: false, text: '获取验证码' });
    }
  });

  it('小数向上取整', () => {
    expect(resendLabel(59.2)).toEqual({ disabled: true, text: '60 秒后重发' });
  });
});

describe('retryAfterSeconds —— 从 429 里取重试秒数', () => {
  it('正常取值', () => {
    expect(retryAfterSeconds({ detail: { retry_after_seconds: 42 } })).toBe(42);
  });

  it('缺失或非法 → **回落到 60**，绝不返回 NaN / 0', () => {
    // 返回 0 会让用户立刻重试、再吃一次 429；
    // 返回 NaN 会让按钮显示「NaN 秒后重发」。
    for (const bad of [
      null, {}, { detail: null }, { detail: {} },
      { detail: { retry_after_seconds: 'abc' } },
      { detail: { retry_after_seconds: -1 } },
      { detail: { retry_after_seconds: 0 } },
    ]) {
      expect(retryAfterSeconds(bad), JSON.stringify(bad)).toBe(PHONE_CODE_RESEND_SECONDS);
    }
  });
});

describe('常量守门', () => {
  it('与后端默认值一致', () => {
    // 前端无法 import 后端配置，这两个数只能各写一份。用断言把值钉住，
    // 至少让改动成为一个**需要显式修改测试的动作**，而不是静默漂移。
    //
    // 尤其是重发间隔：若它小于后端值，用户会点了重发却吃 429 ——
    // 一个纯前端配错导致的假故障。
    expect(PHONE_CODE_RESEND_SECONDS).toBe(60);
    expect(PHONE_CODE_LENGTH).toBe(6);
  });
});
