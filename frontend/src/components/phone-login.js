/**
 * components/phone-login.js —— 手机验证码登录表单（MVP-5，PRD §4.16）
 *
 * 两个登录页（HR 端与候选人端）共用这一份。它**只负责拿到 `{token, user}`**，
 * 不决定去哪一端 —— 「去哪一端」是两个页面各自的知识：
 * HR 页收到 candidate 角色要写成 `candidate.*` 并跳候选人端；候选人页收到
 * 非 candidate 要**拒绝**而不是跳走（行为不同，不能共用一个分流函数）。
 *
 * ⚠️ 本文件里所有**判定**都抽成了导出函数（normalizePhone / isValidPhone /
 * validatePhoneLogin / resendLabel / retryAfterSeconds）。原因见 module-32 §Global
 * Constraints：本工程的前端测试**只能测纯函数**（无 DOM 环境），留在组件内部的
 * 判定等于永远不会被测到 —— 而它们错起来很安静：`resendLabel` 返回负数秒、
 * `retryAfterSeconds` 返回 NaN，都不会报错，只会让按钮上显示一个荒唐的值。
 */

import { el } from '../dom.js';
import * as api from '../api.js';
import { toast } from './toast.js';
import { fieldError, fieldErrors } from './form.js';

/** 与后端 6 位验证码一致。前端无法 import 后端配置，只能各写一份，因此有常量守门测试。 */
export const PHONE_CODE_LENGTH = 6;

/**
 * 与后端 `PHONE_CODE_RESEND_INTERVAL_SECONDS` 默认值一致。
 *
 * ⚠️ 若它**小于**后端的值，用户会点了重发却吃 429 —— 一个纯前端配错导致的假故障。
 * 测试里有常量守门断言把它钉住。
 */
export const PHONE_CODE_RESEND_SECONDS = 60;

const SEPARATORS = /[\s\-()]/g;
const PHONE_RE = /^1[3-9]\d{9}$/;

/**
 * 归一化手机号：去空格 / 连字符 / 括号，去 `+86` 与 `86` 前缀。
 *
 * 必须与后端 `auth/schemas.py::normalize_phone` **行为一致**。前端先归一化再发请求，
 * 后端还会再归一化一次（纵深，不是重复）。两边不一致的症状是「前端说格式对、
 * 后端说格式错」—— 一条谁也想不到去查前端的错误。
 *
 * 只剥**一层**国家码前缀：`"868613800138000"` 这类叠了两层的脏数据应当判为非法，
 * 而不是被反复剥成一个合法号码。
 */
export function normalizePhone(raw) {
  let cleaned = String(raw ?? '').replace(SEPARATORS, '');
  for (const prefix of ['+86', '86']) {
    if (cleaned.startsWith(prefix) && cleaned.length > prefix.length) {
      cleaned = cleaned.slice(prefix.length);
      break;
    }
  }
  return cleaned;
}

/** 是否 11 位大陆手机号。 */
export function isValidPhone(raw) {
  return PHONE_RE.test(normalizePhone(raw));
}

/** 表单校验 → `{ phone?, code? }`。空对象表示通过。 */
export function validatePhoneLogin({ phone, code }) {
  const errors = {};

  if (!isValidPhone(phone)) {
    errors.phone = '请填写 11 位手机号';
  }

  const codeRaw = String(code ?? '').trim();
  if (codeRaw.length !== PHONE_CODE_LENGTH || !/^\d+$/.test(codeRaw)) {
    errors.code = `请填写 ${PHONE_CODE_LENGTH} 位数字验证码`;
  }

  return errors;
}

/**
 * 重发按钮的显示态 → `{ disabled, text }`。
 *
 * 负数与非法值一律当 0 处理：这个数字来自 `retry_after_seconds`（后端）或
 * 本地倒计时，任何一个环节算出负数都会让按钮显示「-3 秒后重发」。
 */
export function resendLabel(remainingSeconds) {
  const remaining = Math.max(0, Math.ceil(Number(remainingSeconds) || 0));
  if (remaining <= 0) return { disabled: false, text: '获取验证码' };
  return { disabled: true, text: `${remaining} 秒后重发` };
}

/**
 * 从 429 错误里取重试秒数；取不到则回落到 `PHONE_CODE_RESEND_SECONDS`。
 *
 * 回落到一个**正常值**而不是 0 或 NaN：0 会让用户立刻重试、再吃一次 429；
 * NaN 会让按钮显示「NaN 秒后重发」。
 */
export function retryAfterSeconds(error) {
  const value = Number(error?.detail?.retry_after_seconds);
  if (!Number.isFinite(value) || value <= 0) return PHONE_CODE_RESEND_SECONDS;
  return Math.ceil(value);
}

/**
 * 构建手机验证码登录表单。
 *
 * @param {{ onSubmit: (result: {token: string, user: object}) => any,
 *           title?: string, lede?: string }} options
 *   `onSubmit` 由调用方负责分流与跳转。
 * @returns {HTMLFormElement}
 */
export function buildPhoneLoginForm({ onSubmit, title, lede }) {
  const phone = el('input', {
    class: 'input', id: 'phone-input', maxlength: '20',
    autocomplete: 'tel', inputmode: 'numeric', placeholder: '例如 13800138000',
  });
  const phoneError = fieldError();

  const code = el('input', {
    class: 'input', id: 'phone-code-input', maxlength: '10',
    autocomplete: 'one-time-code', inputmode: 'numeric', placeholder: '6 位数字',
  });
  const codeError = fieldError();

  const errors = fieldErrors({ phone: phoneError, code: codeError });

  const sendBtn = el('button', {
    class: 'btn btn--quiet btn--sm', type: 'button', text: '获取验证码',
  });
  const note = el('div', {});
  const submit = el('button', {
    class: 'btn btn--primary btn--wide', type: 'submit', text: '登录',
  });

  let timer = null;
  let remaining = 0;

  function paintResend() {
    const { disabled, text } = resendLabel(remaining);
    sendBtn.disabled = disabled;
    sendBtn.textContent = text;
  }

  function stopTimer() {
    if (timer !== null) { clearInterval(timer); timer = null; }
  }

  function startCountdown(seconds) {
    stopTimer();
    remaining = seconds;
    paintResend();
    // 归零时**自行清掉** interval，否则页面停留一小时后会攒下几十个永不停歇的定时器。
    timer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) { remaining = 0; stopTimer(); }
      paintResend();
    }, 1000);
  }

  /**
   * 发码成功后的提示。
   *
   * `dev_code` 出现与否**完全由后端 `SMS_PROVIDER` 决定**（mock 才回显），前端
   * 只是把它显示出来 —— 这里不判断、也不知道当前是不是 mock，判据只有「字段是否非空」。
   * 生产换上真实 Provider 后这个分支自然永不进入。
   */
  function showSent(devCode) {
    note.replaceChildren();
    if (devCode) {
      code.value = devCode;
      note.append(el('p', { class: 'note-box', text: `演示环境：验证码 ${devCode}` }));
    } else {
      note.append(el('p', { class: 'field-note', text: '验证码已发送，请查看短信。' }));
    }
  }

  sendBtn.addEventListener('click', async () => {
    errors.clear();
    note.replaceChildren();

    if (!isValidPhone(phone.value)) {
      errors.show('phone', '请填写 11 位手机号');
      phone.focus();
      return;
    }

    sendBtn.disabled = true;
    sendBtn.textContent = '发送中…';
    try {
      const result = await api.post('/auth/phone/code', {
        phone: normalizePhone(phone.value),
      });
      showSent(result.dev_code);
      startCountdown(PHONE_CODE_RESEND_SECONDS);
    } catch (error) {
      if (error.status === 429) {
        // 倒计时本身就是提示，不再弹 toast —— 同一条信息不该播报两次
        startCountdown(retryAfterSeconds(error));
        return;
      }
      // 其余（含 502 短信通道故障）：**立刻恢复可点**。通道故障不是用户的问题，
      // 不该把他锁在 60 秒之外 —— 那样他重试的愿望与能力都被前端拿走了。
      stopTimer();
      remaining = 0;
      paintResend();
      if (!errors.fromServer(error)) toast.error(error.message);
    }
  });

  return el(
    'form',
    {
      class: 'login-form',
      onSubmit: async (event) => {
        event.preventDefault();
        errors.clear();

        const found = validatePhoneLogin({ phone: phone.value, code: code.value });
        if (found.phone) { errors.show('phone', found.phone); phone.focus(); return; }
        if (found.code) { errors.show('code', found.code); code.focus(); return; }

        submit.disabled = true;
        const original = submit.textContent;
        submit.textContent = '登录中…';
        try {
          const result = await api.post('/auth/phone/login', {
            phone: normalizePhone(phone.value),
            code: code.value.trim(),
          });
          await onSubmit(result);
        } catch (error) {
          // 两种错误的**位置不同**，靠 `detail.reason` 判别而不是靠文案 ——
          // 文案是给用户看的，随时可能改；判据必须是机器可读的（与登录页
          // 处理 `self_register_disabled` 同一手法）。
          if (error.detail?.reason === 'account_disabled') {
            toast.error(error.message);
          } else if (error.status === 401) {
            // 「验证码错误或已失效」落到验证码框 —— 它指向的就是用户刚填错的那个框
            errors.show('code', error.message);
            code.focus();
          } else if (!errors.fromServer(error)) {
            toast.error(error.message);
          }
        } finally {
          submit.disabled = false;
          submit.textContent = original;
        }
      },
    },
    el('h2', { text: title ?? '手机验证码登录' }),
    el('p', { class: 'login-card-lede', text: lede ?? '用手机号接收验证码登录，首次登录会自动为你创建账号。' }),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'phone-input', text: '手机号' }),
      phone,
      phoneError),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'phone-code-input', text: '验证码' }),
      el('div', { class: 'field-row' }, code, sendBtn),
      codeError),
    note,
    submit,
  );
}
