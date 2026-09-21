/**
 * pages/users.js —— 用户管理（仅 admin）
 *
 * 若前端没有这个页面，admin 就没有任何途径创建 HR 账号，该功能实际不可用。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import * as auth from '../auth.js';
import { toast } from '../components/toast.js';
import { confirmModal, openModal } from '../components/modal.js';
import { contextTitle, createShell, emptyState, formatDate, loadingBlock } from '../components/shell.js';

const ROLE_LABELS = { admin: '管理员', hr: 'HR' };

function openCreateModal(onSaved) {
  const usernameInput = el('input', {
    class: 'input', id: 'user-username', maxlength: '50', autocomplete: 'off',
  });
  const usernameError = el('p', { class: 'field-error', hidden: true });

  // maxlength 与后端的 8–128 对齐：超长输入在浏览器里就被挡住，
  // 而不是提交后才拿一个「请求参数不合法」——后者说不清是哪个字段。
  const passwordInput = el('input', {
    class: 'input', id: 'user-password', type: 'password', maxlength: '128', autocomplete: 'new-password',
  });
  const passwordError = el('p', { class: 'field-error', hidden: true });

  // role 只接受 hr / admin —— candidate 不在枚举里（API 文档 §5.3）
  const roleSelect = el(
    'select',
    { class: 'select', id: 'user-role' },
    el('option', { value: 'hr', text: 'HR（只能看到自己创建的数据）' }),
    el('option', { value: 'admin', text: '管理员（可看全部数据、管理用户）' }),
  );
  const roleError = el('p', { class: 'field-error', hidden: true });

  const errors = { username: usernameError, password: passwordError, role: roleError };

  function clearErrors() {
    for (const node of Object.values(errors)) { node.textContent = ''; node.hidden = true; }
  }
  function showError(field, message) {
    const node = errors[field];
    if (!node) return false;
    node.textContent = message;
    node.hidden = false;
    return true;
  }
  function applyServerFieldErrors(error) {
    const fields = error.detail?.fields;
    if (error.code !== 'VALIDATION_ERROR' || !Array.isArray(fields)) return false;
    let matched = false;
    for (const item of fields) if (showError(item.field, item.message)) matched = true;
    return matched;
  }

  const body = el(
    'div',
    {},
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'user-username', text: '用户名' }),
      usernameInput,
      usernameError,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'user-password', text: '初始密码' }),
      passwordInput,
      el('p', { class: 'field-note', text: '8–128 位。创建后请让本人尽快修改。' }),
      passwordError,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'user-role', text: '角色' }),
      roleSelect,
      roleError,
    ),
  );

  const submit = el('button', { class: 'btn btn--primary', text: '创建用户' });

  const handle = openModal({
    title: '创建用户',
    body,
    footer: [
      el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }),
      submit,
    ],
  });

  submit.addEventListener('click', async () => {
    clearErrors();
    const username = usernameInput.value.trim();
    if (!username) { showError('username', '请填写用户名'); usernameInput.focus(); return; }
    if (passwordInput.value.length < 8) { showError('password', '密码长度不能少于 8 位'); passwordInput.focus(); return; }

    handle.setBusy(true);
    try {
      await api.post('/users', { username, password: passwordInput.value, role: roleSelect.value });
      handle.close();
      toast.success('用户已创建');
      onSaved();
    } catch (error) {
      handle.setBusy(false);
      // 400 定位到字段；409（用户名已存在）等仍用后端文案提示
      if (!applyServerFieldErrors(error)) toast.error(error.message);
    }
  });
}

export async function render(container) {
  const { root, main } = createShell(contextTitle('用户管理'));
  mount(container, root);
  mount(main, loadingBlock('正在加载用户…'));

  let users;
  try {
    users = await api.get('/users');
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('用户加载失败', error.message)));
    return;
  }

  const me = auth.getUser();

  async function mutate(userId, payload, successMessage) {
    try {
      await api.patch(`/users/${userId}`, payload);
      toast.success(successMessage);
      render(container);
    } catch (error) {
      toast.error(error.message);
    }
  }

  /**
   * 降级与禁用都先二次确认 —— 二者都会立刻拿走对方已有的东西：
   * 降级后对方看不到他人数据，禁用则当场把人踢下线。误点的代价由被
   * 操作的人承担。升为管理员与启用不确认：它们是给回权限，不拿走东西。
   */
  async function changeRole(user) {
    const toHr = user.role === 'admin';
    if (toHr) {
      const ok = await confirmModal({
        title: `将「${user.username}」降为 HR？`,
        message: '降级后对方将只能看到自己创建的数据，左侧「用户管理」入口也会消失。随时可以再升回来。',
        confirmLabel: '降为 HR',
      });
      if (!ok) return;
    }
    mutate(user.id, { role: toHr ? 'hr' : 'admin' }, '角色已更新');
  }

  async function toggleActive(user) {
    if (user.is_active) {
      const ok = await confirmModal({
        title: `禁用「${user.username}」？`,
        message: '禁用后对方会立即被登出（已签发的登录态同时失效），在重新启用前无法登录。',
        confirmLabel: '禁用',
      });
      if (!ok) return;
    }
    mutate(user.id, { is_active: !user.is_active }, user.is_active ? '账号已禁用' : '账号已启用');
  }

  function buildRow(user) {
    // 当前登录用户那一行禁用操作 —— 后端也会拒绝（409），前端提前避免误操作
    const isSelf = user.id === me?.id;
    return el(
      'tr',
      {},
      el(
        'td',
        {},
        el('strong', { text: user.username }),
        isSelf ? el('span', { class: 'mine-badge', text: '（你自己）' }) : null,
      ),
      el('td', {}, el('span', { class: 'tag tag--dim', text: ROLE_LABELS[user.role] ?? user.role })),
      el('td', {}, el('span', {
        class: `tag ${user.is_active ? 'tag--evaluated' : 'tag--off'}`,
        text: user.is_active ? '已启用' : '已禁用',
      })),
      el('td', { class: 'meta', text: formatDate(user.created_at) }),
      el(
        'td',
        { class: 'cell-actions' },
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: user.role === 'admin' ? '降为 HR' : '升为管理员',
          disabled: isSelf,
          title: isSelf ? '不能修改自己的角色' : '',
          onClick: () => changeRole(user),
        }),
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: user.is_active ? '禁用' : '启用',
          disabled: isSelf,
          title: isSelf ? '不能禁用自己的账号' : '',
          onClick: () => toggleActive(user),
        }),
      ),
    );
  }

  mount(
    main,
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', { text: '用户管理' }),
        el('p', { class: 'page-lede' }, 'HR 只能看到自己创建的岗位、题目和面试；管理员可以看到全部数据。'),
      ),
      el(
        'div',
        { class: 'page-head-actions' },
        el('button', {
          class: 'btn btn--primary',
          text: '创建用户',
          onClick: () => openCreateModal(() => render(container)),
        }),
      ),
    ),
    el(
      'div',
      { class: 'panel' },
      el(
        'table',
        { class: 'table' },
        el(
          'thead',
          {},
          el(
            'tr',
            {},
            el('th', { text: '用户名' }),
            el('th', { text: '角色' }),
            el('th', { text: '状态' }),
            el('th', { text: '创建时间' }),
            el('th', {}),
          ),
        ),
        el('tbody', {}, users.map(buildRow)),
      ),
    ),
  );
}
