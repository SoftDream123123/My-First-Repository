/**
 * 用户管理（module-07 §5.7，仅 admin）。
 *
 * PRD §4.1 与 §8 定义了 /users 端点；若前端没有这个页面，
 * admin 就没有任何途径创建 HR 账号，该功能实际不可用。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import * as auth from '../auth.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';
import {
  contextTitle,
  createShell,
  emptyState,
  formatDate,
  loadingBlock,
} from '../components/shell.js';

const ROLE_LABELS = { admin: '管理员', hr: 'HR' };

function openCreateModal(onSaved) {
  const usernameInput = el('input', {
    class: 'input',
    id: 'user-username',
    maxlength: '50',
    autocomplete: 'off',
  });

  const passwordInput = el('input', {
    class: 'input',
    id: 'user-password',
    type: 'password',
    autocomplete: 'new-password',
  });

  const roleSelect = el(
    'select',
    { class: 'select', id: 'user-role' },
    el('option', { value: 'hr', text: 'HR（只能看到自己创建的数据）' }),
    el('option', { value: 'admin', text: '管理员（可看全部数据、管理用户）' }),
  );

  const body = el(
    'div',
    {},
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'user-username', text: '用户名' }),
      usernameInput,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'user-password', text: '初始密码' }),
      passwordInput,
      el('p', { class: 'field-note', text: '至少 8 位。创建后请让本人尽快修改。' }),
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'user-role', text: '角色' }),
      roleSelect,
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
    if (!usernameInput.value.trim()) {
      toast.error('请填写用户名');
      usernameInput.focus();
      return;
    }
    if (passwordInput.value.length < 8) {
      toast.error('密码长度不能少于 8 位');
      passwordInput.focus();
      return;
    }

    handle.setBusy(true);
    try {
      await api.post('/users', {
        username: usernameInput.value.trim(),
        password: passwordInput.value,
        role: roleSelect.value,
      });
      handle.close();
      toast.success('用户已创建');
      onSaved();
    } catch (error) {
      handle.setBusy(false);
      toast.error(error.message);
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

  function buildRow(user) {
    // 当前登录用户那一行禁用操作 —— 后端也会拒绝，前端提前避免误操作
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
      el(
        'td',
        {},
        el('span', { class: 'tag tag--dim', text: ROLE_LABELS[user.role] ?? user.role }),
      ),
      el(
        'td',
        {},
        el('span', {
          class: `tag ${user.is_active ? 'tag--evaluated' : 'tag--completed'}`,
          text: user.is_active ? '已启用' : '已禁用',
        }),
      ),
      el('td', { class: 'meta', text: formatDate(user.created_at) }),
      el(
        'td',
        { class: 'cell-actions' },
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: user.role === 'admin' ? '降为 HR' : '升为管理员',
          disabled: isSelf,
          title: isSelf ? '不能修改自己的角色' : '',
          onClick: () =>
            mutate(
              user.id,
              { role: user.role === 'admin' ? 'hr' : 'admin' },
              '角色已更新',
            ),
        }),
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: user.is_active ? '禁用' : '启用',
          disabled: isSelf,
          title: isSelf ? '不能禁用自己的账号' : '',
          onClick: () =>
            mutate(
              user.id,
              { is_active: !user.is_active },
              user.is_active ? '账号已禁用' : '账号已启用',
            ),
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
        el('h1', { class: 'h-page', text: '用户管理' }),
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
