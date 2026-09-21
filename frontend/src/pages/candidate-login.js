/**
 * pages/candidate-login.js —— 候选人登录 / 注册
 *
 * 登录与注册是**同一张卡片的两个模式**，不新增路由：候选人心里装的是
 * 「我要进去」，而不是「我走的是哪条接口」。切换成本低于跳转成本。
 *
 * 左栏换成本人视角的闭环：HR 那条「出题 → 记录 → 评估 → 报告」对候选人
 * 毫无意义 —— 他在这里做的事只有一件：把题练到答得出来。
 *
 * ⚠️ **登录端点是三个角色共用的**（API 文档 §5.1）。本页只发候选人端的入口，
 * 但若有 HR / admin 账号在这里登录，必须明确拒绝 —— 把 HR 的登录态写进
 * `candidate.*` 会让这个人下一次进 HR 页时反而「未登录」，而症状（进去了却是空的）
 * 与原因离得很远。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import * as auth from '../auth.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { navigate, defaultRoute } from '../router.js';

const FLOW = [
  { label: '受邀', text: '拿到招聘方发来的邀请码，激活后这场面试就出现在「我的面试」里。' },
  { label: '作答', text: '一题一题往下答，离开输入框会自动保存；交卷之后不能再改。' },
  { label: '反馈', text: '招聘方评估完成后，可以看到不含分数的脱敏反馈：结论、优点与待改进。' },
  { label: '练手', text: '没有面试时也能自己刷题：单选当场判分，简答给解析，答错的进错题本。' },
];

const PASSWORD_MIN = 8;
const PASSWORD_MAX = 128;

function buildAside() {
  return el(
    'section',
    { class: 'login-aside' },
    el('div', { class: 'login-mark', text: '面试助手' }),
    el('div', { class: 'login-mark-sub', text: '候选人端' }),
    el('h1', { class: 'login-claim' },
      el('span', { text: '面试在这里答，' }),
      el('span', { text: '题在这里练。' })),
    el('ol', { class: 'login-flow' }, FLOW.map((item, index) =>
      el('li', { class: 'login-flow-item' },
        el('span', { class: 'login-flow-index', text: String(index + 1) }),
        el('div', {},
          el('div', { class: 'login-flow-label', text: item.label }),
          el('p', { class: 'login-flow-text', text: item.text }))))),
    el('p', { class: 'login-aside-foot', text: '数据与模型调用都留在本机，不经过外部服务。' }),
  );
}

function buildCard() {
  let mode = 'login';
  // 自助注册被后端关掉时翻成 true：那时「注册」这条路不存在，
  // 该给的不是一句报错，而是另一条能走通的路（凭邀请码激活）
  let registerClosed = false;

  const username = el('input', {
    class: 'input', id: 'cand-username', maxlength: '50', autocomplete: 'username',
  });
  const usernameError = fieldError();

  const password = el('input', {
    class: 'input', id: 'cand-password', type: 'password', maxlength: '128',
    autocomplete: 'current-password',
  });
  const passwordError = fieldError();
  const passwordNote = el('p', { class: 'field-note' });

  const errors = fieldErrors({ username: usernameError, password: passwordError });

  const title = el('h2', {});
  const lede = el('p', { class: 'login-card-lede' });
  const switcher = el('div', { class: 'seg' });
  const submit = el('button', { class: 'btn btn--primary btn--wide', type: 'submit' });
  const note = el('div', {});

  function paint() {
    const isLogin = mode === 'login';
    title.textContent = isLogin ? '登录' : '注册';
    lede.textContent = isLogin
      ? '用你的候选人账号登录。'
      : '注册一个账号就能开始刷题；收到邀请码的话，注册完再去激活面试。';
    submit.textContent = isLogin ? '登录' : '注册并登录';
    passwordNote.textContent = isLogin ? '' : `密码至少 ${PASSWORD_MIN} 位`;

    // 这两个字段的内容在两种模式之间是共用的，不重画（重画会把已输入的内容清掉）。
    // 只有密码的 `autocomplete` 跟着模式走：注册时不该让浏览器填一个旧密码进去
    password.setAttribute('autocomplete', isLogin ? 'current-password' : 'new-password');

    switcher.replaceChildren();
    [['login', '登录'], ['register', '注册']].forEach(([key, label]) => {
      switcher.append(el('button', {
        class: `seg-btn${mode === key ? ' is-on' : ''}`,
        type: 'button',
        text: label,
        onClick: () => { mode = key; errors.clear(); paint(); },
      }));
    });

    note.replaceChildren();
    if (registerClosed) {
      note.append(
        el('p', { class: 'note-box' }, '自助注册已关闭。拿到邀请码的话，凭邀请码就能进。'),
        el('div', { class: 'login-alt-row' },
          el('button', {
            class: 'btn btn--primary btn--sm',
            type: 'button',
            text: '凭邀请码进入',
            onClick: () => navigate('/candidate/activate'),
          })),
      );
      return;
    }
    note.append(
      el('div', { class: 'login-alt-row' },
        el('span', { text: '拿到邀请码了？' }),
        el('button', {
          class: 'btn btn--quiet btn--sm',
          type: 'button',
          text: '去激活',
          onClick: () => navigate('/candidate/activate'),
        })),
    );
  }

  const form = el(
    'form',
    {
      class: 'login-form',
      onSubmit: async (event) => {
        event.preventDefault();
        errors.clear();

        const name = username.value.trim();
        if (!name) { errors.show('username', '请填写用户名'); username.focus(); return; }
        if (!password.value) { errors.show('password', '请填写密码'); password.focus(); return; }
        if (mode === 'register'
            && (password.value.length < PASSWORD_MIN || password.value.length > PASSWORD_MAX)) {
          errors.show('password', `密码长度需在 ${PASSWORD_MIN}–${PASSWORD_MAX} 位之间`);
          password.focus();
          return;
        }

        submit.disabled = true;
        const original = submit.textContent;
        submit.textContent = mode === 'login' ? '登录中…' : '注册中…';
        try {
          // 注册**不签发 token**（API 文档 §5.6），因此注册成功后必须再登录一次。
          // 两步都成功才算完成 —— 只成功第一步时不能把人留在「以为进去了」的状态。
          if (mode === 'register') {
            await api.post('/auth/register', { username: name, password: password.value });
          }

          const result = await api.post('/auth/login', { username: name, password: password.value });

          if (result.user?.role !== 'candidate') {
            // HR / admin 账号走错了入口。不写登录态：写进 candidate.* 会让他在
            // HR 页上变成「未登录」，而症状与原因离得很远
            toast.error('这是候选人端，HR 账号请从 HR 工作台登录。');
            return;
          }

          auth.saveToken(result.token, result.user);
          navigate(defaultRoute('candidate'));
        } catch (error) {
          // 自助注册被关闭：翻成「给出激活入口」那一版，而不是弹一句报错
          if (error.detail?.reason === 'self_register_disabled') {
            mode = 'login';
            registerClosed = true;
            errors.clear();
            paint();
          } else if (!errors.fromServer(error)) {
            // 其余一律原样展示后端文案：注册重名（409 用户名已被占用）、
            // 密码错（401）、账号被禁用（401）都是后端写好的中文，前端不重写
            toast.error(error.message);
          }
        } finally {
          submit.disabled = false;
          submit.textContent = original;
        }
      },
    },
    title,
    lede,
    switcher,
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'cand-username', text: '用户名' }),
      username,
      usernameError),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'cand-password', text: '密码' }),
      password,
      passwordNote,
      passwordError),
    submit,
    note,
  );

  paint();
  return form;
}

export function render(container) {
  mount(container, el('div', { class: 'login' },
    buildAside(),
    el('section', { class: 'login-main' }, el('div', { class: 'login-card' }, buildCard()))));
}
