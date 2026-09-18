/**
 * 弹窗（module-07 §6）。
 * Esc 关闭；提交中禁用关闭 —— 避免重复提交。
 */

import { el, mount } from '../dom.js';

/**
 * 打开弹窗。
 * 返回 { close, setBusy, root }。
 *
 * 关于 `busy` 与 `close` 的分工（这里踩过一次坑）：
 * `setBusy(true)` 会禁用弹窗内所有控件，用于「提交中」防止重复提交。
 * 但**返回出去的 `close()` 不受 busy 影响** —— 调用方在请求成功后必须能关掉弹窗。
 * 早期版本让 close() 在 busy 时直接 return，于是「提交中锁住」变成了
 * 「提交成功后也关不掉」：弹窗连同被禁用的按钮一起卡在页面上，只能刷新。
 * 四个页面（用户 / 岗位 / 题库 / 面试）都受影响。
 *
 * 用户自己发起的关闭（Esc、点遮罩）另走 closeByUser()，那才是该挡的：
 * 提交期间不该让弹窗消失，否则请求的结果无处安放。
 * footer 里的「取消」按钮不需要在这里挡 —— setBusy(true) 已经把它禁用了。
 */
export function openModal({ title, body, footer, wide = false, onClose }) {
  const overlay = el('div', { class: 'modal-overlay' });
  let busy = false;

  function onKeydown(event) {
    if (event.key === 'Escape') closeByUser();
  }

  function dismiss() {
    document.removeEventListener('keydown', onKeydown);
    overlay.remove();
    if (onClose) onClose();
  }

  function closeByUser() {
    if (busy) return; // 提交中，用户不能关
    dismiss();
  }

  const panel = el(
    'div',
    { class: `modal${wide ? ' modal--wide' : ''}`, role: 'dialog', 'aria-modal': 'true' },
    el('div', { class: 'modal-head' }, el('div', { class: 'modal-title', text: title })),
    el('div', { class: 'modal-body' }, body),
    footer ? el('div', { class: 'modal-foot' }, footer) : null,
  );

  overlay.append(panel);
  overlay.addEventListener('mousedown', (event) => {
    if (event.target === overlay) closeByUser();
  });
  document.addEventListener('keydown', onKeydown);
  document.body.append(overlay);

  // 焦点进第一个可交互元素，键盘用户不必手动 Tab 进来
  const firstField = panel.querySelector('input, select, textarea, button');
  if (firstField) firstField.focus();

  return {
    root: panel,
    close: dismiss,
    setBusy(value) {
      busy = value;
      overlay.querySelectorAll('button, input, select, textarea').forEach((node) => {
        node.disabled = value;
      });
    },
  };
}

/** 二次确认。返回 Promise<boolean>。 */
export function confirmModal({ title, message, confirmLabel = '删除', danger = true }) {
  return new Promise((resolve) => {
    let settled = false;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      handle.close();
      resolve(value);
    };

    const handle = openModal({
      title,
      body: el('p', { class: 'prose', text: message }),
      footer: [
        el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => finish(false) }),
        el('button', {
          class: `btn ${danger ? 'btn--danger' : 'btn--primary'}`,
          text: confirmLabel,
          onClick: () => finish(true),
        }),
      ],
      onClose: () => finish(false),
    });
  });
}
