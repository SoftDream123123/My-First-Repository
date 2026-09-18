/**
 * 登录页（module-07 §5.1）。
 *
 * 不套用外壳。左侧是英雄区 —— 不用"大数字 + 渐变"的默认套路，
 * 而是直接展示产品真实产出的一个片段：一次评估的结论。
 * 这是最能说明"这东西干什么用"的东西。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import * as auth from '../auth.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { navigate } from '../components/shell.js';

const SAMPLE_BARS = [
  { label: '沟通能力', score: 8.0 },
  { label: '专业能力', score: 7.5 },
  { label: '逻辑思维', score: 7.0 },
  { label: '文化契合', score: 6.3 },
];

function buildIntro() {
  return el(
    'section',
    { class: 'login-intro' },
    el('div', { class: 'login-brand', text: '面试助手' }),

    // 句式落到用户视角：AI 做的是出题、记录、评估；决定由人来做
    el('h1', {
      class: 'login-claim',
      style: 'margin-bottom:0',
    }, 'AI 出题、记录、评估，', el('em', { text: '你来决定' }), '。'),

    el(
      'div',
      { class: 'login-sample' },
      el(
        'div',
        { class: 'login-sample-head' },
        el('span', { class: 'score score--hero', text: '7.2' }),
        el(
          'div',
          {},
          el('span', { class: 'login-sample-name', text: '张书宁' }),
          el('span', { class: 'login-sample-note', text: '后端工程师，8 道题' }),
        ),
      ),
      el(
        'div',
        { class: 'login-bars' },
        SAMPLE_BARS.map((bar) =>
          el(
            'div',
            { class: 'login-bar' },
            el('span', { text: bar.label }),
            el(
              'div',
              { class: 'login-bar-track' },
              el('div', { class: 'login-bar-fill', style: `width:${bar.score * 10}%` }),
            ),
            el('span', { class: 'num', text: bar.score.toFixed(1) }),
          ),
        ),
      ),
    ),
  );
}

function buildForm(onSubmit) {
  const username = el('input', {
    class: 'input',
    id: 'login-username',
    name: 'username',
    maxlength: '50',
    autocomplete: 'username',
  });
  const usernameError = fieldError();

  const password = el('input', {
    class: 'input',
    id: 'login-password',
    name: 'password',
    type: 'password',
    maxlength: '128',
    autocomplete: 'current-password',
  });
  const passwordError = fieldError();

  const errors = fieldErrors({ username: usernameError, password: passwordError });

  const submit = el('button', {
    class: 'btn btn--primary btn--wide',
    type: 'submit',
    text: '登录',
  });

  const form = el(
    'form',
    {
      class: 'login-form',
      onSubmit: async (event) => {
        event.preventDefault();
        errors.clear();

        if (!username.value.trim()) {
          errors.show('username', '请填写用户名');
          username.focus();
          return;
        }
        if (!password.value) {
          errors.show('password', '请填写密码');
          password.focus();
          return;
        }

        submit.disabled = true;
        submit.textContent = '登录中…';
        try {
          await onSubmit(username.value, password.value);
        } catch (error) {
          // 400 落到字段；「用户名或密码错误」这类业务错误仍用后端文案提示
          if (!errors.fromServer(error)) toast.error(error.message);
        } finally {
          submit.disabled = false;
          submit.textContent = '登录';
        }
      },
    },
    el('h2', { class: 'login-form-title', text: '登录' }),
    el('p', { class: 'hint', style: 'margin-bottom:24px' }, '用管理员分配给你的账号登录。'),

    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'login-username', text: '用户名' }),
      username,
      usernameError,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'login-password', text: '密码' }),
      password,
      passwordError,
    ),

    submit,
  );

  return form;
}

export function render(container) {
  const root = el(
    'div',
    { class: 'login' },
    buildIntro(),
    el(
      'section',
      { class: 'login-form-side' },
      // 错误交给 buildForm 统一处理：400 落到字段，其余用后端 message
      buildForm(async (username, password) => {
        const result = await api.post('/auth/login', { username, password });
        auth.saveToken(result.token, result.user);
        navigate('/interviews');
      }),
    ),
  );

  mount(container, root);
}
