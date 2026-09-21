/**
 * pages/login.js —— HR 工作台登录
 *
 * 不套用外壳。左栏展示产品的真实流程（出题 → 记录 → 评估 → 报告）——
 * 这是最能说明「这东西干什么用」的东西，而且它本身就是产品的结构。
 *
 * ⚠️ **登录端点三个角色共用一个**（API 文档 §5.1）。返回的 `user.role` 决定该去
 * 哪一端，因此这里必须按角色分流，不能默认来者都是 HR。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import * as auth from '../auth.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { navigate, defaultRoute } from '../router.js';

const FLOW = [
  { label: '出题', text: '选岗位，从题库按评估维度抽题，AI 再按 JD 补几道。' },
  { label: '记录', text: '逐题录入候选人的回答；也可以发一张邀请码，让候选人自己在线作答。' },
  { label: '评估', text: '逐题打分、按维度打分，结果流式返回，边评边看。' },
  { label: '报告', text: '汇总总分、结论与优劣势，导出 DOCX，或打印成 PDF。' },
];

function buildAside() {
  return el(
    'section',
    { class: 'login-aside' },
    el('div', { class: 'login-mark', text: '面试助手' }),
    el('div', { class: 'login-mark-sub', text: 'HR 工作台' }),
    el('h1', { class: 'login-claim' },
      el('span', { text: '一场面试，从出题到报告，' }),
      el('span', { text: '在同一处走完。' }),
    ),
    el(
      'ol',
      { class: 'login-flow' },
      FLOW.map((item, index) =>
        el(
          'li',
          { class: 'login-flow-item' },
          el('span', { class: 'login-flow-index', text: String(index + 1) }),
          el(
            'div',
            {},
            el('div', { class: 'login-flow-label', text: item.label }),
            el('p', { class: 'login-flow-text', text: item.text }),
          ),
        ),
      ),
    ),
    el('p', { class: 'login-aside-foot', text: '数据与模型调用都留在本机，不经过外部服务。' }),
  );
}

function buildForm() {
  const username = el('input', {
    class: 'input', id: 'login-username', maxlength: '50', autocomplete: 'username',
  });
  const usernameError = fieldError();

  const password = el('input', {
    class: 'input', id: 'login-password', type: 'password', maxlength: '128',
    autocomplete: 'current-password',
  });
  const passwordError = fieldError();

  const errors = fieldErrors({ username: usernameError, password: passwordError });

  const submit = el('button', { class: 'btn btn--primary btn--wide', type: 'submit', text: '登录' });

  return el(
    'form',
    {
      class: 'login-form',
      onSubmit: async (event) => {
        event.preventDefault();
        errors.clear();

        if (!username.value.trim()) { errors.show('username', '请填写用户名'); username.focus(); return; }
        if (!password.value) { errors.show('password', '请填写密码'); password.focus(); return; }

        submit.disabled = true;
        submit.textContent = '登录中…';
        try {
          const result = await api.post('/auth/login', {
            username: username.value.trim(),
            password: password.value,
          });

          // 候选人账号在 HR 登录页登录：本页只发 HR 工作台的入口。
          // 这里**不保存登录态** —— 候选人端页面尚未落地，存下来也无处可去，
          // 反而会让人以为自己已经进了某个界面。
          if (result.user?.role === 'candidate') {
            toast.error('这是 HR 工作台。候选人端尚未上线，暂时无法进入。');
            return;
          }

          auth.saveToken(result.token, result.user);
          navigate(defaultRoute('hr', auth.isAdmin()));
        } catch (error) {
          // 400 落到字段；「用户名或密码错误」这类业务错误用后端文案提示
          if (!errors.fromServer(error)) toast.error(error.message);
        } finally {
          submit.disabled = false;
          submit.textContent = '登录';
        }
      },
    },
    el('h2', { text: '登录' }),
    el('p', { class: 'login-card-lede', text: '用管理员分配给你的账号登录。' }),
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
    el('p', { class: 'note-box' }, '演示账号：admin / admin12345'),
  );
}

export function render(container) {
  mount(
    container,
    el('div', { class: 'login' }, buildAside(), el('section', { class: 'login-main' }, el('div', { class: 'login-card' }, buildForm()))),
  );
}
