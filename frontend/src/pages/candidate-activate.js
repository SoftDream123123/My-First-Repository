/**
 * pages/candidate-activate.js —— 凭邀请码激活并绑定面试
 *
 * 这一页**登录与否都要能进**（路由表里标 `open`）：拿码的人往往还没有账号，
 * 要求他先登录才能激活会让邀请链自相矛盾。因此 `accept` 是全项目**唯一的
 * `/api/candidate` 前缀下的公开端点**（API 文档 §10.2）。
 *
 * ⚠️ **绑定到哪个账号由请求体里的 `username` 决定，与调用者身份无关。**
 * 而账号已存在时**必须密码对得上**（2026-09-21 修正）：缺了这条校验，
 * 「知道对方用户名」就等于能把自己的邀请码绑到对方账号上，进而读到对方的面试。
 *
 * ⚠️ 激活**不签发 token**，因此成功后还要再登录一次 —— 与本端登录页的注册流程
 * 同一手法。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import * as auth from '../auth.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { navigate } from '../router.js';

function buildCard() {
  const signedIn = auth.isLoggedIn() && auth.isCandidate();
  const currentUser = auth.getUser();

  const code = el('input', {
    class: 'input', id: 'activate-code', maxlength: '64', autocomplete: 'off',
    placeholder: '例如 hT9rQ2xLm4ZbN1vCk8sPwA',
  });
  const codeError = fieldError();

  const username = el('input', {
    class: 'input', id: 'activate-username', maxlength: '50', autocomplete: 'username',
    value: signedIn ? (currentUser?.username ?? '') : '',
    readOnly: signedIn,
  });
  const usernameError = fieldError();

  const password = el('input', {
    class: 'input', id: 'activate-password', type: 'password', maxlength: '128',
    autocomplete: 'current-password',
  });
  const passwordError = fieldError();

  // 已登录时**整块隐藏**（MVP-5，PRD §4.1 的免密分支）：身份已由当前 JWT 证明，
  // 后端会跳过密码比对，再要一次密码是对同一事实的重复索取。
  //
  // 这是手机验证码登录能走通邀请链的前提 —— 手机号自动建号的账号没有可用密码，
  // 若无免密分支，用手机号注册的候选人拿到邀请码后将永远无法激活。
  //
  // 前端只做「不发 password」这一件事，**不自己判断**该不该要密码
  // （那是后端的知识；前端猜错会退化成「必填却不填」）。
  const passwordField = el('div', { class: 'field', hidden: signedIn },
    el('label', { class: 'field-label', for: 'activate-password', text: '密码' }),
    password,
    // 这句必须跟着**真实契约**走：账号已存在时要校验密码，不是「忽略」
    el('p', { class: 'field-note', text: '账号已存在时用它核对身份；新建账号时它就是新密码。' }),
    passwordError);

  const errors = fieldErrors({
    code: codeError, username: usernameError, password: passwordError,
  });

  const submit = el('button', {
    class: 'btn btn--primary btn--wide', type: 'submit', text: '激活并进入面试',
  });

  const form = el(
    'form',
    { class: 'login-form' },
    el('h2', { text: '凭邀请码激活' }),
    el('p', { class: 'login-card-lede' },
      signedIn
        ? `激活后会绑定到当前账号 ${currentUser?.username ?? ''}。`
        : '填邀请码与你要用的账号，激活后就能进入这场面试。'),

    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'activate-code', text: '邀请码' }),
      code,
      el('p', { class: 'field-note', text: '招聘方发给你的那串字符，7 天内有效、只能用一次。' }),
      codeError),

    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'activate-username', text: '用户名' }),
      username,
      signedIn
        ? el('p', { class: 'field-note', text: '已登录，固定为当前账号 —— 无需再输入密码。' })
        : el('p', { class: 'field-note', text: '已经注册过就填原来的用户名 —— 会复用那个账号，不会新建。' }),
      usernameError),

    passwordField,

    submit,
    el('div', { class: 'login-alt-row' },
      el('button', {
        class: 'btn btn--quiet btn--sm',
        type: 'button',
        text: '返回登录',
        onClick: () => navigate('/candidate/login'),
      })),
  );

  /** 激活成功但拿不到 token 时的收场：说清事实，把人送回登录页，不留在半登录状态。 */
  function loginFailed() {
    toast.error('已绑定该面试，但自动登录失败，请用这个账号手动登录。');
    navigate('/candidate/login');
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errors.clear();

    const codeValue = code.value.trim();
    const name = username.value.trim();
    if (!codeValue) { errors.show('code', '请填写邀请码'); code.focus(); return; }
    if (!name) { errors.show('username', '请填写用户名'); username.focus(); return; }
    if (!signedIn && !password.value) { errors.show('password', '请填写密码'); password.focus(); return; }

    submit.disabled = true;
    submit.textContent = '激活中…';
    try {
      // 已登录 → **不发 password**，由后端的免密分支处理（PRD §4.1）。
      // 独立成变量是为了让「发什么」这件事一眼可见：漏掉这层分支会退化成
      // 「隐藏了密码框却仍必填」，症状是点了按钮没反应（静默 return）。
      const payload = signedIn
        ? { username: name }
        : { username: name, password: password.value };

      const result = await api.post(
        `/candidate/invitations/${encodeURIComponent(codeValue)}/accept`,
        payload,
      );

      // 已经在本端登录时 token 就在手上，不必再登一次
      if (!(auth.isLoggedIn() && auth.isCandidate())) {
        let fresh;
        try {
          fresh = await api.post('/auth/login', { username: name, password: password.value });
        } catch {
          loginFailed();
          return;
        }
        auth.saveToken(fresh.token, fresh.user);
      }

      toast.success(`已绑定面试：${result.interview?.position_name ?? ''}`);
      navigate(`/candidate/interviews/${result.interview_id}`);
    } catch (error) {
      // 这个端点只在一个地方返回 401：账号已是候选人但**身份不成立**
      // （API 文档 §10.2）。文案仍用后端那一句，不自己另写。
      //
      // ⚠️ 已登录时密码框是隐藏的，把 401 写到那里等于**报错报给了一个看不见的
      // 元素**（用户点了按钮、什么都没发生）—— 那种情况下改用 toast。
      if (error.status === 401 && !signedIn && errors.show('password', error.message)) {
        password.focus();
      } else if (!errors.fromServer(error)) {
        // 409 的三种原因（码失效 / 用户名被 HR 占用 / 已接受过）**原样展示**：
        // 后端刻意让码失效的四种情形共用同一句话，前端不替它推断（module-12 §5.3）
        toast.error(error.message);
      }
    } finally {
      submit.disabled = false;
      submit.textContent = '激活并进入面试';
    }
  });

  return form;
}

export function render(container) {
  mount(container, el('div', { class: 'login' },
    el('section', { class: 'login-aside' },
      el('div', { class: 'login-mark', text: '面试助手' }),
      el('div', { class: 'login-mark-sub', text: '候选人端' }),
      el('h1', { class: 'login-claim' },
        el('span', { text: '一张邀请码，' }),
        el('span', { text: '换一场在线面试。' })),
      el('p', { class: 'login-aside-foot', text: '数据与模型调用都留在本机，不经过外部服务。' })),
    el('section', { class: 'login-main' }, el('div', { class: 'login-card' }, buildCard()))));
}
